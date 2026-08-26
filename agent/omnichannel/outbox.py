"""Domain và PostgreSQL repository cho transactional outbox."""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from agent import db


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    RETRY = "retry"
    SENT = "sent"
    DEAD = "dead"
    CANCELLED = "cancelled"


# Trạng thái JOB không dùng lại được làm trạng thái TIN NHẮN.
#
# `messages.delivery_status` có CHECK riêng và KHÔNG nhận 'retry' — nó là
# thứ người trực và khách nhìn thấy, không phải chi tiết vận hành hàng đợi.
# Ghi thẳng `status.value` sang đó là: lần gửi hỏng đầu tiên -> CheckViolation
# -> rollback -> job kẹt ở `processing` vĩnh viễn, và lý do hỏng thật cũng bị
# rollback theo nên không ai biết vì sao.
#
# `retry` -> `queued` vì đó là sự thật: tin đang chờ lượt gửi tiếp theo.
_TRANG_THAI_GIAO_TIN = {
    OutboxStatus.PENDING: "queued",
    OutboxStatus.PROCESSING: "sending",
    OutboxStatus.RETRY: "queued",
    OutboxStatus.SENT: "sent",
    OutboxStatus.DEAD: "dead",
    OutboxStatus.CANCELLED: "cancelled",
}


def trang_thai_giao_tin(trang_thai: OutboxStatus) -> str:
    """Trạng thái job -> trạng thái hợp lệ cho `messages.delivery_status`."""
    # Không dùng `.get(..., mặc_định)`: thêm trạng thái job mới mà quên ánh xạ
    # thì phải đỏ ngay ở test, không được lặng lẽ rơi vào một giá trị nào đó.
    return _TRANG_THAI_GIAO_TIN[trang_thai]


@dataclass(frozen=True, slots=True)
class OutboxJob:
    id: UUID
    account_id: UUID
    conversation_id: UUID | None
    message_id: UUID | None
    kind: str
    payload: Mapping[str, Any]
    idempotency_key: str
    status: OutboxStatus
    attempts: int
    max_attempts: int
    available_at: datetime
    locked_at: datetime | None
    locked_by: str | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class RetryDecision:
    status: OutboxStatus
    available_at: datetime


def retry_decision(
    *,
    attempts: int,
    max_attempts: int,
    now: datetime | None = None,
) -> RetryDecision:
    """Exponential backoff tối đa 15 phút, đủ lượt thì dead-letter."""
    current = now or datetime.now(timezone.utc)
    if attempts >= max_attempts:
        return RetryDecision(OutboxStatus.DEAD, current)
    delay_seconds = min(2**attempts, 900)
    return RetryDecision(
        OutboxStatus.RETRY,
        current + timedelta(seconds=delay_seconds),
    )


def _job_from_row(row: Mapping[str, Any]) -> OutboxJob:
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return OutboxJob(
        id=row["id"],
        account_id=row["account_id"],
        conversation_id=row["conversation_id"],
        message_id=row["message_id"],
        kind=row["kind"],
        payload=dict(payload or {}),
        idempotency_key=row["idempotency_key"],
        status=OutboxStatus(row["status"]),
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        available_at=row["available_at"],
        locked_at=row["locked_at"],
        locked_by=row["locked_by"],
        last_error=row["last_error"],
    )


class PostgresOutboxRepository:
    def __init__(self, pool_provider: Callable[[], Any] = db.pool):
        self._pool_provider = pool_provider
        self._guarded_connection: ContextVar[Any | None] = ContextVar(
            f"outbox_guarded_connection_{id(self)}", default=None
        )

    async def claim(
        self,
        *,
        worker_id: str,
        limit: int = 20,
        stale_after_seconds: int = 120,
    ) -> list[OutboxJob]:
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                rows = await connection.fetch(
                    """
                    WITH picked AS (
                        SELECT id
                        FROM outbox_jobs
                        WHERE (
                            status IN ('pending', 'retry')
                            AND available_at <= now()
                        ) OR (
                            status = 'processing'
                            AND locked_at < now() - ($2 * interval '1 second')
                        )
                        ORDER BY available_at, created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT $3
                    )
                    UPDATE outbox_jobs AS job
                    SET status = 'processing',
                        attempts = attempts + 1,
                        locked_at = now(),
                        locked_by = $1,
                        updated_at = now()
                    FROM picked
                    WHERE job.id = picked.id
                    RETURNING job.*
                    """,
                    worker_id,
                    stale_after_seconds,
                    limit,
                )
        return [_job_from_row(row) for row in rows]

    async def heartbeat(self, worker_id: str) -> None:
        async with self._pool_provider().acquire() as connection:
            await connection.execute(
                """
                INSERT INTO worker_heartbeats (
                    worker_name, worker_id, last_seen_at, detail
                ) VALUES ($1,$2,now(),'{}')
                ON CONFLICT (worker_name)
                DO UPDATE SET worker_id = excluded.worker_id,
                              last_seen_at = excluded.last_seen_at
                """,
                "outbox",
                worker_id,
            )

    @asynccontextmanager
    async def delivery_guard(self, job: OutboxJob):
        """Giữ fence conversation xuyên suốt provider call để đóng takeover race."""
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                if job.conversation_id is not None:
                    await connection.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                        f"conversation-send:{job.conversation_id}",
                    )
                row = await connection.fetchrow(
                    """
                    SELECT job.id, job.account_id, job.conversation_id,
                           job.message_id, message.role,
                           conversation.status, conversation.mode
                    FROM outbox_jobs job
                    LEFT JOIN messages message ON message.id = job.message_id
                    LEFT JOIN conversations conversation
                      ON conversation.id = job.conversation_id
                    WHERE job.id = $1 AND job.status = 'processing'
                    -- CHỈ khoá dòng `job`.
                    --
                    -- PostgreSQL CẤM `FOR UPDATE` trên nhánh nullable của
                    -- outer join, và đây là lỗi lúc lập kế hoạch truy vấn:
                    -- nó nổ kể cả khi không có dòng nào khớp. Bản trước ghi
                    -- `FOR UPDATE OF job, message, conversation` nên MỌI lượt
                    -- gửi chết ngay tại đây, trước khi chạm provider.
                    --
                    -- Khoá theo hội thoại đã do `pg_advisory_xact_lock` ngay
                    -- phía trên đảm nhiệm — đó mới là fence mà docstring nói
                    -- tới. Khoá dòng trên hai bảng kia vừa thừa vừa phạm luật.
                    FOR UPDATE OF job
                    """,
                    job.id,
                )
                if row is None:
                    yield False
                    return
                ai_blocked = row["role"] == "agent" and (
                    row["mode"] == "human" or row["status"] == "escalated"
                )
                if not ai_blocked:
                    token = self._guarded_connection.set(connection)
                    try:
                        yield True
                    finally:
                        self._guarded_connection.reset(token)
                    return
                await connection.execute(
                    """
                    UPDATE outbox_jobs
                    SET status = 'cancelled', locked_at = NULL, locked_by = NULL,
                        last_error = 'human_takeover', updated_at = now()
                    WHERE id = $1 AND status = 'processing'
                    """,
                    job.id,
                )
                if row["message_id"] is not None:
                    await connection.execute(
                        """
                        UPDATE messages
                        SET delivery_status = 'cancelled', delivered = false
                        WHERE id = $1
                        """,
                        row["message_id"],
                    )
                if row["conversation_id"] is not None:
                    await connection.execute(
                        """
                        INSERT INTO inbox_events (account_id, topic, ref_id, payload)
                        VALUES ($1,'outbox.cancelled',$2,$3)
                        """,
                        row["account_id"],
                        row["conversation_id"],
                        {
                            "job_id": str(job.id),
                            "message_id": str(row["message_id"]),
                            "reason": "human_takeover",
                        },
                    )
                yield False

    async def mark_sent(
        self,
        job_id: UUID,
        provider_result: Mapping[str, Any],
    ) -> None:
        guarded = self._guarded_connection.get()
        if guarded is not None:
            await self._mark_sent_on_connection(
                guarded, job_id, provider_result
            )
            return
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                await self._mark_sent_on_connection(
                    connection, job_id, provider_result
                )

    @staticmethod
    async def _mark_sent_on_connection(
        connection,
        job_id: UUID,
        provider_result: Mapping[str, Any],
    ) -> None:
        link = await connection.fetchrow(
                    """
                    UPDATE outbox_jobs
                    SET status = 'sent', provider_result = $2,
                        locked_at = NULL, locked_by = NULL,
                        last_error = NULL, updated_at = now()
                    WHERE id = $1 AND status = 'processing'
                    RETURNING account_id, conversation_id, message_id,
                              (SELECT role FROM messages
                               WHERE id = outbox_jobs.message_id) AS message_role
                    """,
                    job_id,
                    dict(provider_result),
                )
        if link is None:
            return
        if link["message_id"] is not None:
            await connection.execute(
                        """
                        UPDATE messages
                        SET delivered = true, delivery_status = 'sent',
                            provider_message_id = coalesce($2, provider_message_id)
                        WHERE id = $1
                        """,
                        link["message_id"],
                        provider_result.get("provider_message_id"),
                    )
        if link["conversation_id"] is not None:
            await connection.execute(
                        """
                        UPDATE conversations
                        SET status = CASE WHEN status = 'assist' THEN 'auto' ELSE status END,
                            updated_at = now()
                        WHERE id = $1
                        """,
                        link["conversation_id"],
                    )
            if link.get("message_role") in {"agent", "staff"}:
                await connection.execute(
                    """
                    WITH responded AS (
                        UPDATE conversations
                        SET first_responded_at = coalesce(first_responded_at, now())
                        WHERE id = $1 AND first_responded_at IS NULL
                        RETURNING id, first_response_due_at
                    )
                    INSERT INTO sla_events (
                        conversation_id, kind, due_at, detail
                    )
                    SELECT id,
                           CASE WHEN first_response_due_at IS NOT NULL
                                     AND first_response_due_at < now()
                                THEN 'first_response_breached'
                                ELSE 'first_response_met' END,
                           first_response_due_at,
                           '{}'
                    FROM responded
                    ON CONFLICT (conversation_id, kind) DO NOTHING
                    """,
                    link["conversation_id"],
                )
            await connection.execute(
                        """
                        INSERT INTO inbox_events (account_id, topic, ref_id, payload)
                        VALUES ($1,'outbox.sent',$2,$3)
                        """,
                        link["account_id"],
                        link["conversation_id"],
                        {
                            "job_id": str(job_id),
                            "message_id": str(link["message_id"]),
                        },
                    )

    async def mark_failed(self, job: OutboxJob, error: str) -> None:
        decision = retry_decision(
            attempts=job.attempts,
            max_attempts=job.max_attempts,
        )
        guarded = self._guarded_connection.get()
        if guarded is not None:
            await self._mark_failed_on_connection(
                guarded, job, error, decision
            )
            return
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                await self._mark_failed_on_connection(
                    connection, job, error, decision
                )

    @staticmethod
    async def _mark_failed_on_connection(
        connection,
        job: OutboxJob,
        error: str,
        decision: RetryDecision,
    ) -> None:
        link = await connection.fetchrow(
                    """
                    UPDATE outbox_jobs
                    SET status = $2, available_at = $3,
                        locked_at = NULL, locked_by = NULL,
                        last_error = $4, updated_at = now()
                    WHERE id = $1 AND status = 'processing'
                    RETURNING account_id, conversation_id, message_id
                    """,
                    job.id,
                    decision.status.value,
                    decision.available_at,
                    error[:500],
                )
        if link is None:
            return
        if link["message_id"] is not None:
            await connection.execute(
                        """
                        UPDATE messages
                        SET delivered = false, delivery_status = $2
                        WHERE id = $1
                        """,
                        link["message_id"],
                        trang_thai_giao_tin(decision.status),
                    )
        if link["conversation_id"] is not None:
            await connection.execute(
                        """
                        INSERT INTO inbox_events (account_id, topic, ref_id, payload)
                        VALUES ($1,$2,$3,$4)
                        """,
                        link["account_id"],
                        f"outbox.{decision.status.value}",
                        link["conversation_id"],
                        {
                            "job_id": str(job.id),
                            "message_id": str(link["message_id"]),
                            "error": error[:200],
                        },
                    )
