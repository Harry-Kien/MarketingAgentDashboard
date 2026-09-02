"""Quản trị yêu cầu lưu trữ/xóa dữ liệu với phê duyệt bốn mắt.

Endpoint trong module này cố ý chỉ thực thi dry-run. Xóa thật là thao tác không
hoàn tác và phải đi qua quy trình pháp lý/vận hành riêng sau khi kiểm tra kết quả.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from agent import db

from .routes import bat_buoc_quan_tri


router = APIRouter(prefix="/api/data-retention", tags=["data-retention"])


class RetentionNotFound(LookupError):
    pass


class RetentionConflict(ValueError):
    pass


class PostgresRetentionRepository:
    def __init__(self, pool_provider=db.pool) -> None:
        self._pool_provider = pool_provider

    async def list_jobs(self) -> list[dict[str, Any]]:
        async with self._pool_provider().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT id, contact_id, kind, status, requested_by, approved_by,
                       reason, dry_run, result, requested_at, approved_at,
                       completed_at
                FROM data_retention_jobs
                ORDER BY requested_at DESC
                LIMIT 200
                """
            )
        return [dict(row) for row in rows]

    async def approve(self, job_id: UUID, *, actor_id: UUID) -> dict[str, Any]:
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    "SELECT * FROM data_retention_jobs WHERE id=$1 FOR UPDATE",
                    job_id,
                )
                if current is None:
                    raise RetentionNotFound("Không tìm thấy yêu cầu lưu trữ")
                if current["status"] != "pending_approval":
                    raise RetentionConflict("Yêu cầu không còn chờ phê duyệt")
                if current["requested_by"] == actor_id:
                    raise RetentionConflict(
                        "Người tạo yêu cầu không được tự phê duyệt"
                    )
                row = await connection.fetchrow(
                    """
                    UPDATE data_retention_jobs
                    SET status='approved', approved_by=$2, approved_at=now()
                    WHERE id=$1
                    RETURNING *
                    """,
                    job_id,
                    actor_id,
                )
                await connection.execute(
                    "INSERT INTO events (kind, actor, ref_id, detail) "
                    "VALUES ('contact.retention_approved',$1,$2,$3)",
                    str(actor_id),
                    job_id,
                    {"dry_run": bool(row["dry_run"]), "kind": row["kind"]},
                )
        return dict(row)

    async def cancel(self, job_id: UUID, *, actor_id: UUID) -> dict[str, Any]:
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    "SELECT * FROM data_retention_jobs WHERE id=$1 FOR UPDATE",
                    job_id,
                )
                if current is None:
                    raise RetentionNotFound("Không tìm thấy yêu cầu lưu trữ")
                if current["status"] not in {"pending_approval", "approved"}:
                    raise RetentionConflict("Yêu cầu không thể hủy ở trạng thái hiện tại")
                row = await connection.fetchrow(
                    """
                    UPDATE data_retention_jobs SET status='cancelled'
                    WHERE id=$1 RETURNING *
                    """,
                    job_id,
                )
                await connection.execute(
                    "INSERT INTO events (kind, actor, ref_id, detail) "
                    "VALUES ('contact.retention_cancelled',$1,$2,$3)",
                    str(actor_id),
                    job_id,
                    {"previous_status": current["status"]},
                )
        return dict(row)

    async def execute_dry_run(
        self, job_id: UUID, *, actor_id: UUID
    ) -> dict[str, Any]:
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    "SELECT * FROM data_retention_jobs WHERE id=$1 FOR UPDATE",
                    job_id,
                )
                if current is None:
                    raise RetentionNotFound("Không tìm thấy yêu cầu lưu trữ")
                if current["status"] != "approved":
                    raise RetentionConflict("Yêu cầu phải được phê duyệt trước")
                if not current["dry_run"]:
                    raise RetentionConflict(
                        "Endpoint này chỉ cho phép yêu cầu dry-run an toàn"
                    )
                if current["contact_id"] is None:
                    raise RetentionConflict("Yêu cầu không còn gắn với khách hàng")

                # Chỉ trả số lượng, không đưa PII vào audit hoặc kết quả job.
                counts = await connection.fetchrow(
                    """
                    SELECT
                      (SELECT count(*) FROM contact_points
                       WHERE contact_id=$1) AS contact_points,
                      (SELECT count(*) FROM conversations
                       WHERE contact_id=$1) AS conversations,
                      (SELECT count(*) FROM messages m
                       JOIN conversations c ON c.id=m.conversation_id
                       WHERE c.contact_id=$1) AS messages,
                      (SELECT count(*) FROM attachments a
                       JOIN messages m ON m.id=a.message_id
                       JOIN conversations c ON c.id=m.conversation_id
                       WHERE c.contact_id=$1) AS attachments,
                      (SELECT count(*) FROM contact_tags
                       WHERE contact_id=$1) AS tags,
                      (SELECT count(*) FROM contact_notes
                       WHERE contact_id=$1) AS notes,
                      (SELECT count(*) FROM contact_consents
                       WHERE contact_id=$1) AS consents
                    """,
                    current["contact_id"],
                )
                result = {name: int(value) for name, value in dict(counts).items()}
                row = await connection.fetchrow(
                    """
                    UPDATE data_retention_jobs
                    SET status='completed', result=$2, completed_at=now()
                    WHERE id=$1 RETURNING *
                    """,
                    job_id,
                    result,
                )
                await connection.execute(
                    "INSERT INTO events (kind, actor, ref_id, detail) "
                    "VALUES ('contact.retention_dry_run_completed',$1,$2,$3)",
                    str(actor_id),
                    job_id,
                    {"counts": result},
                )
        return dict(row)


def get_retention_repository() -> PostgresRetentionRepository:
    return PostgresRetentionRepository()


def _actor(user: dict) -> UUID:
    return UUID(str(user["id"]))


async def _call(operation):
    try:
        return await operation
    except RetentionNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except RetentionConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/jobs")
async def list_retention_jobs(
    _: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresRetentionRepository = Depends(get_retention_repository),
):
    return {"jobs": await repository.list_jobs()}


@router.post("/jobs/{job_id}/approve")
async def approve_retention_job(
    job_id: UUID,
    user: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresRetentionRepository = Depends(get_retention_repository),
):
    return await _call(repository.approve(job_id, actor_id=_actor(user)))


@router.post("/jobs/{job_id}/cancel")
async def cancel_retention_job(
    job_id: UUID,
    user: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresRetentionRepository = Depends(get_retention_repository),
):
    return await _call(repository.cancel(job_id, actor_id=_actor(user)))


@router.post("/jobs/{job_id}/execute-dry-run")
async def execute_retention_dry_run(
    job_id: UUID,
    user: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresRetentionRepository = Depends(get_retention_repository),
):
    return await _call(repository.execute_dry_run(job_id, actor_id=_actor(user)))
