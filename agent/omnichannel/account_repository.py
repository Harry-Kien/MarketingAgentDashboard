"""Lưu tài khoản kênh, credential đã mã hóa và audit trong PostgreSQL."""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

import asyncpg

from agent import db
from agent.security.credential_vault import SealedCredential

from .account_service import AccountAlreadyExists, AccountNotFound
from .accounts import AccountStatus, Channel, ChannelAccount


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value or {})


def _account_from_row(row: Mapping[str, Any]) -> ChannelAccount:
    return ChannelAccount(
        id=row["id"],
        channel=Channel(row["channel"]),
        display_name=row["display_name"],
        external_account_id=row["external_account_id"],
        status=AccountStatus(row["status"]),
        capabilities=_json_object(row["capabilities"]),
        metadata=_json_object(row["metadata"]),
        is_legacy=row["is_legacy"],
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


class PostgresAccountRepository:
    def __init__(self, pool_provider: Callable[[], Any] = db.pool):
        self._pool_provider = pool_provider

    async def find_by_external(
        self,
        channel: Channel,
        external_account_id: str | None,
    ) -> ChannelAccount | None:
        async with self._pool_provider().acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM channel_accounts
                WHERE channel = $1
                  AND external_account_id IS NOT DISTINCT FROM $2
                """,
                channel.value,
                external_account_id,
            )
        return _account_from_row(row) if row else None

    async def find_active_by_external_ids(
        self,
        channel: Channel,
        external_ids: set[str],
    ) -> list[ChannelAccount]:
        if not external_ids:
            return []
        async with self._pool_provider().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM channel_accounts
                WHERE channel = $1
                  AND external_account_id = ANY($2::text[])
                  AND status IN ('active', 'degraded')
                ORDER BY external_account_id
                """,
                channel.value,
                sorted(external_ids),
            )
        return [_account_from_row(row) for row in rows]

    async def list_active_by_channel(
        self,
        channel: Channel,
    ) -> list[ChannelAccount]:
        """
        Mọi tài khoản đang hoạt động của một kênh.

        Dùng cho những việc phải hỏi TẤT CẢ tài khoản chứ không biết trước
        cái nào — ví dụ xác minh webhook gộp của Meta, nơi chỉ có một URL
        dùng chung cho mọi Trang.

        Gồm cả `degraded`: tài khoản suy giảm vẫn phải nhận được tin, nếu
        không thì một trục trặc tạm thời biến thành mất tin vĩnh viễn.
        """
        async with self._pool_provider().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM channel_accounts
                WHERE channel = $1 AND status IN ('active', 'degraded')
                ORDER BY created_at
                """,
                channel.value,
            )
        return [_account_from_row(row) for row in rows]

    async def create(
        self,
        account: ChannelAccount,
        sealed: SealedCredential | None,
        *,
        actor_id: UUID,
    ) -> ChannelAccount:
        try:
            async with self._pool_provider().acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        INSERT INTO channel_accounts (
                            id, channel, display_name, external_account_id,
                            status, capabilities, metadata, is_legacy
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        """,
                        account.id,
                        account.channel.value,
                        account.display_name,
                        account.external_account_id,
                        account.status.value,
                        dict(account.capabilities),
                        dict(account.metadata),
                        account.is_legacy,
                    )
                    if sealed is not None:
                        await conn.execute(
                            """
                            INSERT INTO credential_secrets (
                                account_id, key_version, nonce, ciphertext
                            ) VALUES ($1,$2,$3,$4)
                            """,
                            account.id,
                            sealed.key_version,
                            sealed.nonce,
                            sealed.ciphertext,
                        )
                    await conn.execute(
                        """
                        INSERT INTO account_memberships (account_id, user_id, role)
                        VALUES ($1,$2,'owner')
                        ON CONFLICT (account_id, user_id) DO UPDATE
                        SET role = 'owner'
                        """,
                        account.id,
                        actor_id,
                    )
                    await conn.execute(
                        """
                        INSERT INTO events (kind, actor, ref_id, detail)
                        VALUES ('channel_account.created', $1, $2, $3)
                        """,
                        str(actor_id),
                        account.id,
                        {
                            "channel": account.channel.value,
                            "external_account_id": account.external_account_id,
                            "has_credentials": sealed is not None,
                        },
                    )
        except asyncpg.UniqueViolationError as exc:
            raise AccountAlreadyExists("tài khoản kênh này đã tồn tại") from exc
        return account

    async def get(self, account_id: UUID) -> ChannelAccount | None:
        async with self._pool_provider().acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM channel_accounts WHERE id = $1",
                account_id,
            )
        return _account_from_row(row) if row else None

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        is_admin: bool,
    ) -> list[ChannelAccount]:
        async with self._pool_provider().acquire() as conn:
            if is_admin:
                rows = await conn.fetch(
                    "SELECT * FROM channel_accounts ORDER BY channel, display_name"
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT account.*
                    FROM channel_accounts AS account
                    JOIN account_memberships AS membership
                      ON membership.account_id = account.id
                    WHERE membership.user_id = $1
                    ORDER BY account.channel, account.display_name
                    """,
                    user_id,
                )
        return [_account_from_row(row) for row in rows]

    async def has_credentials(self, account_id: UUID) -> bool:
        async with self._pool_provider().acquire() as conn:
            return bool(
                await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM credential_secrets WHERE account_id = $1)",
                    account_id,
                )
            )

    async def get_credentials(self, account_id: UUID) -> SealedCredential | None:
        async with self._pool_provider().acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT key_version, nonce, ciphertext
                FROM credential_secrets WHERE account_id = $1
                """,
                account_id,
            )
        if not row:
            return None
        return SealedCredential(row["key_version"], row["nonce"], row["ciphertext"])

    async def store_credentials(
        self,
        account_id: UUID,
        sealed: SealedCredential,
        *,
        actor_id: UUID,
    ) -> None:
        async with self._pool_provider().acquire() as conn:
            async with conn.transaction():
                result = await conn.execute(
                    """
                    INSERT INTO credential_secrets (
                        account_id, key_version, nonce, ciphertext, updated_at
                    ) VALUES ($1,$2,$3,$4,now())
                    ON CONFLICT (account_id) DO UPDATE SET
                        key_version = EXCLUDED.key_version,
                        nonce = EXCLUDED.nonce,
                        ciphertext = EXCLUDED.ciphertext,
                        updated_at = now()
                    """,
                    account_id,
                    sealed.key_version,
                    sealed.nonce,
                    sealed.ciphertext,
                )
                if result not in {"INSERT 0 1", "UPDATE 1", "OK"}:
                    raise AccountNotFound("không tìm thấy tài khoản kênh")
                await conn.execute(
                    """
                    INSERT INTO events (kind, actor, ref_id, detail)
                    VALUES ('channel_account.credentials_rotated', $1, $2, '{}')
                    """,
                    str(actor_id),
                    account_id,
                )

    async def update_status(
        self,
        account_id: UUID,
        status: AccountStatus,
        *,
        actor_id: UUID,
    ) -> ChannelAccount:
        async with self._pool_provider().acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    UPDATE channel_accounts
                    SET status = $2, updated_at = now()
                    WHERE id = $1
                    RETURNING *
                    """,
                    account_id,
                    status.value,
                )
                if row is None:
                    raise AccountNotFound("không tìm thấy tài khoản kênh")
                await conn.execute(
                    """
                    INSERT INTO events (kind, actor, ref_id, detail)
                    VALUES ('channel_account.status_changed', $1, $2, $3)
                    """,
                    str(actor_id),
                    account_id,
                    {"status": status.value},
                )
        return _account_from_row(row)

    async def bind_external_identity(
        self,
        account_id: UUID,
        external_account_id: str,
        *,
        actor_id: UUID,
    ) -> None:
        """Bind ID provider đúng một lần; callback khác không được chiếm account."""
        external_account_id = external_account_id.strip()
        if not external_account_id:
            raise ValueError("provider identity không được để trống")
        try:
            async with self._pool_provider().acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        """
                        UPDATE channel_accounts
                        SET external_account_id = $2, updated_at = now()
                        WHERE id = $1
                          AND (external_account_id LIKE 'pending:%'
                               OR external_account_id = $2)
                        RETURNING id
                        """,
                        account_id,
                        external_account_id,
                    )
                    if row is None:
                        raise AccountAlreadyExists(
                            "tài khoản đã gắn với một provider identity khác"
                        )
                    await conn.execute(
                        """
                        INSERT INTO events (kind, actor, ref_id, detail)
                        VALUES ('channel_account.identity_bound', $1, $2, $3)
                        """,
                        str(actor_id),
                        account_id,
                        {"external_account_id": external_account_id},
                    )
        except asyncpg.UniqueViolationError as exc:
            raise AccountAlreadyExists(
                "provider identity này đã thuộc một tài khoản khác"
            ) from exc

    async def record_health(
        self,
        account_id: UUID,
        *,
        status: AccountStatus,
        code: str,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        async with self._pool_provider().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO account_health_events (account_id, status, code, detail)
                VALUES ($1,$2,$3,$4)
                """,
                account_id,
                status.value,
                code,
                dict(detail or {}),
            )

    async def latest_health(self, account_id: UUID) -> dict[str, Any] | None:
        async with self._pool_provider().acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT status, code, detail, observed_at
                FROM account_health_events
                WHERE account_id = $1
                ORDER BY observed_at DESC
                LIMIT 1
                """,
                account_id,
            )
        return dict(row) if row else None
