"""
`delivery_guard` phải chạy được trên PostgreSQL thật.

LỖI ĐÃ XẢY RA THẬT
------------------
Câu lệnh trong guard viết:

    FROM outbox_jobs job
    LEFT JOIN messages message ...
    LEFT JOIN conversations conversation ...
    FOR UPDATE OF job, message, conversation

PostgreSQL CẤM `FOR UPDATE` trên nhánh nullable của outer join. Đây là lỗi
lúc LẬP KẾ HOẠCH truy vấn — nó nổ kể cả khi không có dòng nào khớp.

Nghĩa là mọi lượt gửi đều chết ngay tại chốt, trước khi chạm tới provider.
Log sidecar trống trơn, khách không nhận được gì, và tin đứng mãi ở
`queued` trên dashboard.

Khoá theo hội thoại đã do `pg_advisory_xact_lock` ngay phía trên đảm nhiệm —
đó mới là fence thật mà docstring nói tới. Khoá dòng trên `message` và
`conversation` vừa thừa vừa phạm luật.

Không fake nào bắt được lỗi này: nó là luật của chính Postgres.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from agent.omnichannel.outbox import (
    OutboxJob,
    OutboxStatus,
    PostgresOutboxRepository,
)


def test_delivery_guard_khong_vi_pham_luat_for_update_cua_postgres():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("chưa cấp TEST_DATABASE_URL cho integration PostgreSQL")

    import asyncpg

    job = OutboxJob(
        id=uuid4(),
        account_id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        kind="send_text",
        payload={"conversation_ref": "x", "text": "y"},
        idempotency_key="guard-thu-nghiem",
        status=OutboxStatus.PROCESSING,
        attempts=1,
        max_attempts=3,
        available_at=datetime.now(timezone.utc),
        locked_at=None,
        locked_by=None,
        last_error=None,
    )

    async def kiem():
        pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2)
        try:
            repository = PostgresOutboxRepository(lambda: pool)
            # Job không tồn tại -> guard phải trả False một cách bình thường.
            # Trước bản vá, dòng này ném FeatureNotSupportedError ngay khi
            # Postgres lập kế hoạch truy vấn.
            async with repository.delivery_guard(job) as duoc_phep:
                return duoc_phep
        finally:
            await pool.close()

    assert asyncio.run(kiem()) is False
