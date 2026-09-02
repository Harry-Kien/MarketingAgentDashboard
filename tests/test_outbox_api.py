"""Quản trị dead-letter phải có quyền, state guard và audit."""
from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import HTTPException

from agent.api.outbox import PostgresOutboxAdminRepository


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Connection:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []
        self.calls = []
        self.in_transaction = False

    def transaction(self):
        connection = self

        class Transaction:
            async def __aenter__(self):
                connection.in_transaction = True

            async def __aexit__(self, exc_type, exc, traceback):
                connection.in_transaction = False
                return False

        return Transaction()

    async def fetch(self, sql, *args):
        self.calls.append((sql, args, self.in_transaction))
        return self.rows

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args, self.in_transaction))
        return self.row

    async def execute(self, sql, *args):
        self.calls.append((sql, args, self.in_transaction))
        return "OK"


class _ConnectionTheoThuTu(_Connection):
    """Trả lần lượt từng row — retry() cần nhiều hơn một lượt fetchrow."""

    def __init__(self, rows_theo_thu_tu):
        super().__init__()
        self.hang_doi = list(rows_theo_thu_tu)

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args, self.in_transaction))
        return self.hang_doi.pop(0) if self.hang_doi else None


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


def test_list_dead_letter_khong_tra_payload_secret_va_co_filter_account():
    connection = _Connection(rows=[])
    repository = PostgresOutboxAdminRepository(lambda: _Pool(connection))
    account_id = uuid4()

    rows = asyncio.run(repository.list_jobs(status="dead", account_id=account_id))

    assert rows == []
    sql, args, _ = connection.calls[0]
    assert "job.payload" not in sql
    assert "job.provider_result" not in sql
    assert "job.status = $1" in sql
    assert "job.account_id = $2" in sql
    assert args == ("dead", account_id, 100)


def test_retry_dead_letter_reset_lock_message_va_audit_cung_transaction():
    job_id = uuid4()
    message_id = uuid4()
    conversation_id = uuid4()
    account_id = uuid4()
    connection = _ConnectionTheoThuTu(
        [
            # Lượt 1: retry() đọc trạng thái hội thoại trước khi ghi gì.
            # Hội thoại vẫn ở chế độ AI nên được phép replay.
            {
                "id": job_id,
                "conversation_id": conversation_id,
                "mode": "auto",
                "status": "auto",
            },
            # Lượt 2: UPDATE outbox_jobs ... RETURNING
            {
                "id": job_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "account_id": account_id,
            },
        ]
    )
    repository = PostgresOutboxAdminRepository(lambda: _Pool(connection))

    result = asyncio.run(repository.retry(job_id, actor="admin"))

    assert result["id"] == job_id
    assert all(call[2] for call in connection.calls)
    sql = "\n".join(call[0] for call in connection.calls)
    assert "status = 'pending'" in sql
    assert "attempts = 0" in sql
    assert "WHERE id = $1 AND status = 'dead'" in sql
    assert "UPDATE messages" in sql
    assert "INSERT INTO inbox_events" in sql
    assert "INSERT INTO events" in sql


def test_cancel_khong_duoc_huy_job_processing_hoac_sent():
    connection = _Connection(row=None)
    repository = PostgresOutboxAdminRepository(lambda: _Pool(connection))

    try:
        asyncio.run(repository.cancel(uuid4(), actor="admin"))
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("đã huỷ job không còn ở trạng thái an toàn")

    sql = connection.calls[0][0]
    assert "status IN ('pending', 'retry', 'dead')" in sql


def test_retry_dead_letter_bi_chan_khi_nguoi_that_dang_tiep_quan():
    """
    Replay một job AI đã chết sau khi nhân viên đã trả lời là gửi chồng lên
    câu trả lời của người.

    Khách nhận hai giọng nói mâu thuẫn trong cùng một hội thoại, và bản thân
    job thì không biết gì về việc đã có người tiếp quản — nó chết từ trước
    lúc đó. Nên phép kiểm phải đọc trạng thái hội thoại NGAY LÚC replay,
    không phải tin vào trạng thái đã lưu trong job.
    """
    conversation_id = uuid4()
    job_id = uuid4()
    connection = _ConnectionTheoThuTu(
        [
            {
                "id": job_id,
                "conversation_id": conversation_id,
                "mode": "human",
                "status": "escalated",
            }
        ]
    )
    repository = PostgresOutboxAdminRepository(lambda: _Pool(connection))

    try:
        asyncio.run(repository.retry(job_id, actor="quan-tri"))
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "tiếp quản" in exc.detail
    else:
        raise AssertionError("phải chặn replay khi hội thoại đang do người giữ")

    da_ghi = [c for c in connection.calls if "UPDATE outbox_jobs" in c[0]]
    assert da_ghi == [], "không được đụng vào job khi đã bị chặn"
