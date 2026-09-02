"""API quản trị outbox/dead-letter, không trả payload có dữ liệu nhạy cảm."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from agent import db

from .routes import bat_buoc_quan_tri


router = APIRouter(prefix="/api/outbox", tags=["outbox-admin"])
ALLOWED_STATUSES = {"pending", "processing", "retry", "sent", "dead", "cancelled"}


class PostgresOutboxAdminRepository:
    def __init__(self, pool_provider: Callable[[], Any] = db.pool):
        self._pool_provider = pool_provider

    async def list_jobs(
        self,
        *,
        status: str = "dead",
        account_id: UUID | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if status not in ALLOWED_STATUSES:
            raise HTTPException(422, "Trạng thái outbox không hợp lệ")
        args: list[Any] = [status]
        clauses = ["job.status = $1"]
        if account_id is not None:
            args.append(account_id)
            clauses.append(f"job.account_id = ${len(args)}")
        args.append(max(1, min(limit, 200)))
        sql = f"""
            SELECT job.id, job.account_id, account.display_name AS account_name,
                   account.channel, job.conversation_id, job.message_id,
                   job.kind, job.idempotency_key, job.status, job.attempts,
                   job.max_attempts, job.available_at, job.locked_at,
                   job.locked_by, job.last_error, job.created_at, job.updated_at
            FROM outbox_jobs job
            JOIN channel_accounts account ON account.id = job.account_id
            WHERE {" AND ".join(clauses)}
            ORDER BY job.updated_at DESC, job.id DESC
            LIMIT ${len(args)}
        """
        async with self._pool_provider().acquire() as connection:
            rows = await connection.fetch(sql, *args)
        return [dict(row) for row in rows]

    async def retry(self, job_id: UUID, *, actor: str) -> dict[str, Any]:
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                # Job chết TRƯỚC khi người thật tiếp quản thì bản thân nó
                # không mang thông tin ấy. Phải đọc trạng thái hội thoại ngay
                # lúc replay, khoá luôn cả hai dòng để takeover không chen
                # vào giữa lúc kiểm và lúc ghi.
                hien_trang = await connection.fetchrow(
                    """
                    SELECT job.id, job.conversation_id,
                           conv.mode, conv.status
                    FROM outbox_jobs job
                    LEFT JOIN conversations conv ON conv.id = job.conversation_id
                    WHERE job.id = $1
                    FOR UPDATE OF job
                    """,
                    job_id,
                )
                if hien_trang is None:
                    raise HTTPException(404, "Không tìm thấy job")
                if (
                    hien_trang["mode"] == "human"
                    or hien_trang["status"] == "escalated"
                ):
                    raise HTTPException(
                        409,
                        "Người thật đang tiếp quản hội thoại này. Gửi lại tin "
                        "AI cũ sẽ chồng lên câu trả lời của nhân viên.",
                    )
                link = await connection.fetchrow(
                    """
                    UPDATE outbox_jobs
                    SET status = 'pending', attempts = 0, available_at = now(),
                        locked_at = NULL, locked_by = NULL, last_error = NULL,
                        updated_at = now()
                    WHERE id = $1 AND status = 'dead'
                    RETURNING id, account_id, conversation_id, message_id
                    """,
                    job_id,
                )
                if link is None:
                    raise HTTPException(409, "Job không ở trạng thái dead")
                if link["message_id"] is not None:
                    await connection.execute(
                        """
                        UPDATE messages
                        SET delivered = false, delivery_status = 'queued'
                        WHERE id = $1
                        """,
                        link["message_id"],
                    )
                if link["conversation_id"] is not None:
                    await connection.execute(
                        """
                        INSERT INTO inbox_events (account_id, topic, ref_id, payload)
                        VALUES ($1,'outbox.retried',$2,$3)
                        """,
                        link["account_id"],
                        link["conversation_id"],
                        {"job_id": str(job_id)},
                    )
                await connection.execute(
                    """
                    INSERT INTO events (kind, actor, ref_id, detail)
                    VALUES ('outbox.retried',$2,$1,$3)
                    """,
                    job_id,
                    actor,
                    {"account_id": str(link["account_id"])},
                )
        return dict(link)

    async def cancel(self, job_id: UUID, *, actor: str) -> dict[str, Any]:
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                link = await connection.fetchrow(
                    """
                    UPDATE outbox_jobs
                    SET status = 'cancelled', locked_at = NULL, locked_by = NULL,
                        updated_at = now()
                    WHERE id = $1 AND status IN ('pending', 'retry', 'dead')
                    RETURNING id, account_id, conversation_id, message_id
                    """,
                    job_id,
                )
                if link is None:
                    raise HTTPException(
                        409,
                        "Job đang xử lý, đã gửi hoặc không tồn tại; không thể huỷ an toàn",
                    )
                if link["message_id"] is not None:
                    await connection.execute(
                        """
                        UPDATE messages
                        SET delivered = false, delivery_status = 'cancelled'
                        WHERE id = $1
                        """,
                        link["message_id"],
                    )
                if link["conversation_id"] is not None:
                    await connection.execute(
                        """
                        INSERT INTO inbox_events (account_id, topic, ref_id, payload)
                        VALUES ($1,'outbox.cancelled',$2,$3)
                        """,
                        link["account_id"],
                        link["conversation_id"],
                        {"job_id": str(job_id)},
                    )
                await connection.execute(
                    """
                    INSERT INTO events (kind, actor, ref_id, detail)
                    VALUES ('outbox.cancelled',$2,$1,$3)
                    """,
                    job_id,
                    actor,
                    {"account_id": str(link["account_id"])},
                )
        return dict(link)


def get_outbox_admin_repository() -> PostgresOutboxAdminRepository:
    return PostgresOutboxAdminRepository()


@router.get("/jobs")
async def list_outbox_jobs(
    status: str = "dead",
    account_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=200),
    _: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresOutboxAdminRepository = Depends(
        get_outbox_admin_repository
    ),
) -> dict[str, Any]:
    return {
        "items": await repository.list_jobs(
            status=status,
            account_id=account_id,
            limit=limit,
        )
    }


@router.post("/jobs/{job_id}/retry")
async def retry_outbox_job(
    job_id: UUID,
    user: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresOutboxAdminRepository = Depends(
        get_outbox_admin_repository
    ),
) -> dict[str, Any]:
    job = await repository.retry(job_id, actor=user["ten_dang_nhap"])
    return {"ok": True, "job": job}


@router.post("/jobs/{job_id}/cancel")
async def cancel_outbox_job(
    job_id: UUID,
    user: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresOutboxAdminRepository = Depends(
        get_outbox_admin_repository
    ),
) -> dict[str, Any]:
    job = await repository.cancel(job_id, actor=user["ten_dang_nhap"])
    return {"ok": True, "job": job}
