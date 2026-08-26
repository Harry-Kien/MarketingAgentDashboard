"""Sổ nhận webhook idempotent; chỉ giữ hash và metadata đã lọc."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Protocol
from uuid import UUID

from agent import db


class WebhookStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class WebhookReceipt:
    id: UUID
    account_id: UUID
    dedupe_key: str
    raw_sha256: str
    signature_valid: bool
    status: WebhookStatus
    attempts: int
    metadata: Mapping[str, Any]
    last_error: str | None


@dataclass(frozen=True, slots=True)
class WebhookClaimRequest:
    account_id: UUID
    dedupe_key: str
    raw_sha256: str
    signature_valid: bool
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class WebhookClaim:
    receipt: WebhookReceipt
    should_process: bool
    collision: bool = False


class WebhookLedgerRepository(Protocol):
    async def claim(self, request: WebhookClaimRequest) -> WebhookClaim: ...

    async def mark_processed(self, receipt_id: UUID) -> None: ...

    async def mark_failed(self, receipt_id: UUID, error: str) -> None: ...


_SECRET_MARKERS = ("token", "secret", "password", "cookie", "authorization")


def sanitize_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Giữ metadata chẩn đoán nhỏ và loại trường có khả năng chứa bí mật."""
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized = str(key).lower()
        if any(marker in normalized for marker in _SECRET_MARKERS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[str(key)] = value[:500] if isinstance(value, str) else value
    return safe


class WebhookLedger:
    def __init__(self, repository: WebhookLedgerRepository):
        self._repository = repository

    async def claim(
        self,
        *,
        account_id: UUID,
        dedupe_key: str,
        raw_body: bytes,
        signature_valid: bool,
        metadata: Mapping[str, Any],
    ) -> WebhookClaim:
        if not dedupe_key.strip():
            raise ValueError("webhook dedupe_key không được để trống")
        request = WebhookClaimRequest(
            account_id=account_id,
            dedupe_key=dedupe_key,
            raw_sha256=hashlib.sha256(raw_body).hexdigest(),
            signature_valid=signature_valid,
            metadata=sanitize_metadata(metadata),
        )
        return await self._repository.claim(request)

    async def mark_processed(self, receipt_id: UUID) -> None:
        await self._repository.mark_processed(receipt_id)

    async def mark_failed(self, receipt_id: UUID, error: str) -> None:
        await self._repository.mark_failed(receipt_id, error[:500])


def _receipt_from_row(row: Mapping[str, Any]) -> WebhookReceipt:
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return WebhookReceipt(
        id=row["id"],
        account_id=row["account_id"],
        dedupe_key=row["dedupe_key"],
        raw_sha256=row["raw_sha256"],
        signature_valid=row["signature_valid"],
        status=WebhookStatus(row["status"]),
        attempts=row["attempts"],
        metadata=dict(metadata or {}),
        last_error=row["last_error"],
    )


class PostgresWebhookLedgerRepository:
    """Claim ledger trong transaction để hai worker không xử lý cùng webhook."""

    def __init__(self, pool_provider: Callable[[], Any] = db.pool):
        self._pool_provider = pool_provider

    async def claim(self, request: WebhookClaimRequest) -> WebhookClaim:
        initial_status = (
            WebhookStatus.PROCESSING
            if request.signature_valid
            else WebhookStatus.REJECTED
        )
        attempts = 1 if request.signature_valid else 0
        async with self._pool_provider().acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO webhook_deliveries (
                        account_id, dedupe_key, raw_sha256, signature_valid,
                        status, attempts, metadata
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7)
                    ON CONFLICT (account_id, dedupe_key) DO NOTHING
                    RETURNING *
                    """,
                    request.account_id,
                    request.dedupe_key,
                    request.raw_sha256,
                    request.signature_valid,
                    initial_status.value,
                    attempts,
                    dict(request.metadata),
                )
                if row is not None:
                    receipt = _receipt_from_row(row)
                    return WebhookClaim(
                        receipt,
                        should_process=receipt.status == WebhookStatus.PROCESSING,
                    )

                current_row = await conn.fetchrow(
                    """
                    SELECT * FROM webhook_deliveries
                    WHERE account_id = $1 AND dedupe_key = $2
                    FOR UPDATE
                    """,
                    request.account_id,
                    request.dedupe_key,
                )
                current = _receipt_from_row(current_row)
                if current.raw_sha256 != request.raw_sha256:
                    return WebhookClaim(current, should_process=False, collision=True)
                if (
                    request.signature_valid
                    and current.status in {WebhookStatus.RECEIVED, WebhookStatus.FAILED}
                ):
                    retried_row = await conn.fetchrow(
                        """
                        UPDATE webhook_deliveries
                        SET status = 'processing', attempts = attempts + 1,
                            signature_valid = true, last_error = NULL,
                            updated_at = now()
                        WHERE id = $1
                        RETURNING *
                        """,
                        current.id,
                    )
                    return WebhookClaim(
                        _receipt_from_row(retried_row),
                        should_process=True,
                    )
                return WebhookClaim(current, should_process=False)

    async def mark_processed(self, receipt_id: UUID) -> None:
        async with self._pool_provider().acquire() as conn:
            await conn.execute(
                """
                UPDATE webhook_deliveries
                SET status = 'processed', processed_at = now(),
                    last_error = NULL, updated_at = now()
                WHERE id = $1 AND status = 'processing'
                """,
                receipt_id,
            )

    async def mark_failed(self, receipt_id: UUID, error: str) -> None:
        async with self._pool_provider().acquire() as conn:
            await conn.execute(
                """
                UPDATE webhook_deliveries
                SET status = 'failed', last_error = $2, updated_at = now()
                WHERE id = $1 AND status = 'processing'
                """,
                receipt_id,
                error[:500],
            )
