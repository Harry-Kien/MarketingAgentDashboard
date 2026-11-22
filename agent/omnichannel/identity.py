"""Customer 360: resolve danh tính bảo thủ, merge có version và undo snapshot."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID, uuid4

from agent import db
from agent.channels.ten_khach import la_ten_mac_dinh


class IdentityError(RuntimeError):
    """Lỗi nghiệp vụ Customer 360 an toàn để chuyển thành HTTP response."""


class ContactNotFound(IdentityError):
    pass


class ContactConflict(IdentityError):
    pass


class InvalidMerge(IdentityError):
    pass


@dataclass(frozen=True, slots=True)
class ContactPointResolution:
    contact_id: UUID
    contact_point_id: UUID


@dataclass(frozen=True, slots=True)
class MergeResult:
    merge_id: UUID
    source_contact_id: UUID
    target_contact_id: UUID
    status: str


class IdentityTransaction(Protocol):
    async def resolve_contact_point(self, **kwargs) -> Mapping[str, Any]: ...

    async def lock_contacts(
        self, contact_ids: list[UUID]
    ) -> Mapping[UUID, Mapping[str, Any]]: ...

    async def snapshot_contact_refs(self, source_id: UUID) -> dict[str, list[UUID]]: ...

    async def apply_merge(self, **kwargs) -> None: ...

    async def lock_merge(self, merge_id: UUID) -> Mapping[str, Any] | None: ...

    async def apply_unmerge(self, **kwargs) -> None: ...


class IdentityRepository(Protocol):
    def transaction(self): ...


class IdentityService:
    def __init__(self, repository: IdentityRepository):
        self._repository = repository

    async def resolve_contact_point(
        self,
        *,
        account_id: UUID,
        external_user_id: str,
        display_name: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> ContactPointResolution:
        external = external_user_id.strip()
        if not external:
            raise ValueError("external_user_id không được rỗng")
        async with self._repository.transaction() as tx:
            row = await tx.resolve_contact_point(
                account_id=account_id,
                external_user_id=external,
                display_name=display_name.strip()[:200],
                metadata=dict(metadata or {}),
            )
        return ContactPointResolution(
            contact_id=UUID(str(row["contact_id"])),
            contact_point_id=UUID(str(row["id"])),
        )

    async def merge_contacts(
        self,
        *,
        source_id: UUID,
        target_id: UUID,
        actor_id: UUID,
        reason: str,
        expected_source_version: int,
        expected_target_version: int,
    ) -> MergeResult:
        reason = reason.strip()
        if source_id == target_id:
            raise InvalidMerge("không thể merge một contact vào chính nó")
        if not reason:
            raise InvalidMerge("merge contact bắt buộc có lý do")
        if expected_source_version < 1 or expected_target_version < 1:
            raise InvalidMerge("version contact không hợp lệ")

        merge_id = uuid4()
        async with self._repository.transaction() as tx:
            contacts = await tx.lock_contacts(sorted([source_id, target_id], key=str))
            if source_id not in contacts or target_id not in contacts:
                raise ContactNotFound("không tìm thấy contact nguồn hoặc đích")
            source = contacts[source_id]
            target = contacts[target_id]
            if source["status"] != "active" or target["status"] != "active":
                raise InvalidMerge("chỉ merge được hai contact đang active")
            # Nhóm Zalo không phải một người (mục 9.7). Gộp nhóm vào hồ sơ
            # một thành viên là trộn lịch sử cả nhóm vào trí nhớ riêng của
            # họ. Chặn ở dịch vụ: route nào gọi tới cũng không lọt.
            if source.get("la_nhom") or target.get("la_nhom"):
                raise InvalidMerge(
                    "nhóm Zalo không phải một khách hàng — không gộp được")
            if (
                int(source["version"]) != expected_source_version
                or int(target["version"]) != expected_target_version
            ):
                raise ContactConflict("contact đã thay đổi; tải lại preview trước khi merge")

            snapshot = await tx.snapshot_contact_refs(source_id)
            await tx.apply_merge(
                merge_id=merge_id,
                source_id=source_id,
                target_id=target_id,
                actor_id=actor_id,
                reason=reason,
                source_version=expected_source_version,
                target_version=expected_target_version,
                snapshot=snapshot,
            )
        return MergeResult(merge_id, source_id, target_id, "active")

    async def unmerge_contact(
        self,
        *,
        merge_id: UUID,
        actor_id: UUID,
        reason: str,
    ) -> MergeResult:
        reason = reason.strip()
        if not reason:
            raise InvalidMerge("unmerge bắt buộc có lý do")
        async with self._repository.transaction() as tx:
            merge = await tx.lock_merge(merge_id)
            if merge is None:
                raise ContactNotFound("không tìm thấy lịch sử merge")
            if merge["status"] != "active":
                raise InvalidMerge("merge này đã được hoàn tác")
            source_id = UUID(str(merge["source_contact_id"]))
            target_id = UUID(str(merge["target_contact_id"]))
            contacts = await tx.lock_contacts(sorted([source_id, target_id], key=str))
            if source_id not in contacts or target_id not in contacts:
                raise ContactNotFound("contact của merge không còn tồn tại")
            source = contacts[source_id]
            if source["status"] != "merged" or source.get("merged_into") != target_id:
                raise ContactConflict("trạng thái contact không còn khớp snapshot merge")
            await tx.apply_unmerge(merge=merge, actor_id=actor_id, reason=reason)
        return MergeResult(merge_id, source_id, target_id, "reverted")


class PostgresIdentityTransaction:
    def __init__(self, connection):
        self._connection = connection

    async def resolve_contact_point(
        self,
        *,
        account_id: UUID,
        external_user_id: str,
        display_name: str,
        metadata: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        lock_key = f"contact-point:{account_id}:{external_user_id}"
        await self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", lock_key
        )
        row = await self._connection.fetchrow(
            """
            SELECT point.id, point.contact_id
            FROM contact_points point
            WHERE point.channel_account_id = $1 AND point.external_user_id = $2
            FOR UPDATE
            """,
            account_id,
            external_user_id,
        )
        if row is None:
            contact = await self._connection.fetchrow(
                """
                INSERT INTO contacts (display_name, profile)
                VALUES ($1, $2) RETURNING id
                """,
                display_name or "Khách",
                {"created_from": "inbound"},
            )
            row = await self._connection.fetchrow(
                """
                INSERT INTO contact_points (
                    contact_id, channel_account_id, external_user_id,
                    handle, metadata
                ) VALUES ($1,$2,$3,$4,$5)
                RETURNING id, contact_id
                """,
                contact["id"],
                account_id,
                external_user_id,
                display_name or None,
                dict(metadata),
            )
        else:
            # Tên giữ chỗ ("Khách Zalo", "Nhóm Zalo …ab12") KHÔNG đè tên đã
            # biết — ở cả handle lẫn hồ sơ. Danh sách lấy từ `ten_khach`, một
            # chỗ cho cả hệ thống: bản viết tay trong SQL trước đây thiếu
            # "Khách Facebook", và handle thì bị đè bởi bất cứ chuỗi khác rỗng.
            co_ten_that = not la_ten_mac_dinh(display_name)
            await self._connection.execute(
                """
                UPDATE contact_points
                SET handle = CASE WHEN $5 THEN $3 ELSE handle END,
                    metadata = metadata || $4::jsonb,
                    last_seen = now(), updated_at = now()
                WHERE id = $1 AND channel_account_id = $2
                """,
                row["id"],
                account_id,
                display_name,
                dict(metadata),
                co_ten_that,
            )
            await self._connection.execute(
                """
                UPDATE contacts
                SET display_name = CASE WHEN $3 THEN $2 ELSE display_name END,
                    last_seen = now(), updated_at = now(), version = version + 1
                WHERE id = $1
                """,
                row["contact_id"],
                display_name,
                co_ten_that,
            )
        return row

    async def lock_contacts(self, contact_ids: list[UUID]):
        from agent.core.lien_he_nhom import sql_la_nhom

        rows = await self._connection.fetch(
            f"SELECT *, {sql_la_nhom('contacts')} AS la_nhom FROM contacts "
            "WHERE id = ANY($1::uuid[]) ORDER BY id FOR UPDATE",
            contact_ids,
        )
        return {row["id"]: dict(row) for row in rows}

    async def snapshot_contact_refs(self, source_id: UUID) -> dict[str, list[UUID]]:
        point_rows = await self._connection.fetch(
            "SELECT id FROM contact_points WHERE contact_id = $1 ORDER BY id FOR UPDATE",
            source_id,
        )
        conversation_rows = await self._connection.fetch(
            "SELECT id FROM conversations WHERE contact_id = $1 ORDER BY id FOR UPDATE",
            source_id,
        )
        return {
            "contact_point_ids": [row["id"] for row in point_rows],
            "conversation_ids": [row["id"] for row in conversation_rows],
        }

    @staticmethod
    def _json_snapshot(snapshot: Mapping[str, list[UUID]]) -> dict[str, list[str]]:
        return {
            key: [str(value) for value in values]
            for key, values in snapshot.items()
        }

    async def apply_merge(
        self,
        *,
        merge_id: UUID,
        source_id: UUID,
        target_id: UUID,
        actor_id: UUID,
        reason: str,
        source_version: int,
        target_version: int,
        snapshot: Mapping[str, list[UUID]],
    ) -> None:
        # Nhãn khách đi theo HỒ SƠ (0056): gộp khách là khách giữ lại mang
        # cả nhãn của khách bị gộp. Không chép thì "khách sỉ" của hồ sơ nguồn
        # biến mất khỏi mọi bộ lọc ngay sau khi gộp — không lỗi, không ai báo.
        #
        # Chỉ ghi vào snapshot những nhãn đích CHƯA có, để hoàn tác gỡ đúng
        # những nhãn ấy và không đụng nhãn đích vốn có từ trước. Nguồn giữ
        # nguyên nhãn của nó: hoàn tác là nguồn sống lại đủ như cũ.
        nhan_them = await self._connection.fetch(
            "INSERT INTO khach_gan_nhan (contact_id, nhan_id, gan_boi, gan_luc) "
            "SELECT $2, nhan_id, gan_boi, gan_luc FROM khach_gan_nhan "
            "WHERE contact_id = $1 ON CONFLICT DO NOTHING RETURNING nhan_id",
            source_id,
            target_id,
        )
        snapshot = {**snapshot, "khach_nhan_ids": [row["nhan_id"] for row in nhan_them]}
        await self._connection.execute(
            """
            INSERT INTO contact_merges (
                id, source_contact_id, target_contact_id, actor_id, reason,
                expected_source_version, expected_target_version, snapshot
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            """,
            merge_id,
            source_id,
            target_id,
            actor_id,
            reason,
            source_version,
            target_version,
            self._json_snapshot(snapshot),
        )
        await self._connection.execute(
            "UPDATE contact_points SET contact_id = $2, updated_at = now() "
            "WHERE id = ANY($1::uuid[]) AND contact_id = $3",
            list(snapshot["contact_point_ids"]),
            target_id,
            source_id,
        )
        await self._connection.execute(
            "UPDATE conversations SET contact_id = $2, updated_at = now() "
            "WHERE id = ANY($1::uuid[]) AND contact_id = $3",
            list(snapshot["conversation_ids"]),
            target_id,
            source_id,
        )
        await self._connection.execute(
            """
            UPDATE contacts SET status = 'merged', merged_into = $2,
                version = version + 1, updated_at = now()
            WHERE id = $1
            """,
            source_id,
            target_id,
        )
        await self._connection.execute(
            "UPDATE contacts SET version = version + 1, updated_at = now() WHERE id = $1",
            target_id,
        )
        await self._connection.execute(
            "INSERT INTO events (kind, actor, ref_id, detail) "
            "VALUES ('contact.merged',$1,$2,$3)",
            str(actor_id),
            merge_id,
            {"source_id": str(source_id), "target_id": str(target_id), "reason": reason,
             "nhan_chep": [str(row["nhan_id"]) for row in nhan_them]},
        )

    async def lock_merge(self, merge_id: UUID):
        row = await self._connection.fetchrow(
            "SELECT * FROM contact_merges WHERE id = $1 FOR UPDATE", merge_id
        )
        return dict(row) if row else None

    async def apply_unmerge(
        self,
        *,
        merge: Mapping[str, Any],
        actor_id: UUID,
        reason: str,
    ) -> None:
        source_id = UUID(str(merge["source_contact_id"]))
        target_id = UUID(str(merge["target_contact_id"]))
        snapshot = dict(merge["snapshot"])
        point_ids = [UUID(value) for value in snapshot.get("contact_point_ids", [])]
        conversation_ids = [UUID(value) for value in snapshot.get("conversation_ids", [])]
        current_points = await self._connection.fetch(
            "SELECT id FROM contact_points WHERE id = ANY($1::uuid[]) AND contact_id = $2",
            point_ids,
            target_id,
        )
        current_conversations = await self._connection.fetch(
            "SELECT id FROM conversations WHERE id = ANY($1::uuid[]) AND contact_id = $2",
            conversation_ids,
            target_id,
        )
        if {row["id"] for row in current_points} != set(point_ids) or {
            row["id"] for row in current_conversations
        } != set(conversation_ids):
            raise ContactConflict("một số danh tính/hội thoại đã đổi sau merge")

        await self._connection.execute(
            "UPDATE contact_points SET contact_id = $2, updated_at = now() "
            "WHERE id = ANY($1::uuid[])",
            point_ids,
            source_id,
        )
        await self._connection.execute(
            "UPDATE conversations SET contact_id = $2, updated_at = now() "
            "WHERE id = ANY($1::uuid[])",
            conversation_ids,
            source_id,
        )
        # Gỡ khỏi đích đúng những nhãn lúc gộp đã chép sang (snapshot cũ từ
        # trước 0056 không có khoá này — không gỡ gì).
        nhan_chep = [UUID(value) for value in snapshot.get("khach_nhan_ids", [])]
        if nhan_chep:
            await self._connection.execute(
                "DELETE FROM khach_gan_nhan WHERE contact_id = $1 AND nhan_id = ANY($2::uuid[])",
                target_id,
                nhan_chep,
            )
        await self._connection.execute(
            """
            UPDATE contacts SET status = 'active', merged_into = NULL,
                version = version + 1, updated_at = now() WHERE id = $1
            """,
            source_id,
        )
        await self._connection.execute(
            "UPDATE contacts SET version = version + 1, updated_at = now() WHERE id = $1",
            target_id,
        )
        await self._connection.execute(
            """
            UPDATE contact_merges SET status = 'reverted', reverted_by = $2,
                reverted_at = now(), revert_reason = $3
            WHERE id = $1 AND status = 'active'
            """,
            merge["id"],
            actor_id,
            reason,
        )
        await self._connection.execute(
            "INSERT INTO events (kind, actor, ref_id, detail) "
            "VALUES ('contact.unmerged',$1,$2,$3)",
            str(actor_id),
            merge["id"],
            {"source_id": str(source_id), "target_id": str(target_id), "reason": reason},
        )


class PostgresIdentityRepository:
    def __init__(self, pool_provider: Callable[[], Any] = db.pool):
        self._pool_provider = pool_provider

    @asynccontextmanager
    async def transaction(self):
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                yield PostgresIdentityTransaction(connection)
