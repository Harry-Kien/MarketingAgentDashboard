"""Transactional outbox: idempotency, claim, retry và dead-letter."""
from __future__ import annotations

import asyncio
import inspect
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from agent.channels.base import Delivery
from agent.omnichannel.outbox import (
    OutboxJob,
    OutboxStatus,
    PostgresOutboxRepository,
    retry_decision,
)
from agent.workers.outbox_worker import OutboxProcessor, outbox_loop


def _job(**overrides):
    base = OutboxJob(
        id=uuid4(),
        account_id=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        kind="send_text",
        payload={"conversation_ref": "customer-1", "text": "Xin chào"},
        idempotency_key="reply:1",
        status=OutboxStatus.PENDING,
        attempts=0,
        max_attempts=3,
        available_at=datetime.now(timezone.utc),
        locked_at=None,
        locked_by=None,
        last_error=None,
    )
    return replace(base, **overrides)


def test_retry_backoff_co_gioi_han_va_den_max_thi_dead():
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)

    first = retry_decision(attempts=1, max_attempts=3, now=now)
    second = retry_decision(attempts=2, max_attempts=3, now=now)
    final = retry_decision(attempts=3, max_attempts=3, now=now)

    assert first.status == OutboxStatus.RETRY
    assert first.available_at == now + timedelta(seconds=2)
    assert second.available_at == now + timedelta(seconds=4)
    assert final.status == OutboxStatus.DEAD
    assert final.available_at == now


class _Repository:
    def __init__(self, jobs, *, authorized=True):
        self.jobs = list(jobs)
        self.authorized = authorized
        self.sent = []
        self.failed = []
        self.heartbeats = []
        self.authorization_checks = []

    async def heartbeat(self, worker_id):
        self.heartbeats.append(worker_id)

    async def claim(self, *, worker_id, limit, stale_after_seconds):
        claimed = self.jobs[:limit]
        self.jobs = self.jobs[limit:]
        return [
            replace(
                job,
                status=OutboxStatus.PROCESSING,
                attempts=job.attempts + 1,
                locked_by=worker_id,
            )
            for job in claimed
        ]

    async def mark_sent(self, job_id, provider_result):
        self.sent.append((job_id, provider_result))

    async def mark_failed(self, job, error):
        self.failed.append((job.id, error))

    @asynccontextmanager
    async def delivery_guard(self, job):
        self.authorization_checks.append(job.id)
        yield self.authorized


class _Adapter:
    def __init__(self, delivery=Delivery(True)):
        self.delivery = delivery
        self.calls = []

    async def send_text(self, conversation_ref, text):
        self.calls.append((conversation_ref, text))
        return self.delivery

    async def send_file(self, conversation_ref, path, caption=""):
        self.calls.append((conversation_ref, path, caption))
        return self.delivery


def test_worker_gui_bang_dung_account_va_mark_sent():
    job = _job()
    repository = _Repository([job])
    adapter = _Adapter()
    resolved = []

    async def resolver(account_id):
        resolved.append(account_id)
        return adapter

    count = asyncio.run(OutboxProcessor(repository, resolver).process_once("worker-1"))

    assert count == 1
    assert resolved == [job.account_id]
    assert adapter.calls == [("customer-1", "Xin chào")]
    assert repository.sent[0][0] == job.id
    assert repository.failed == []


def test_worker_chan_ai_job_neu_human_takeover_xay_ra_sau_khi_claim():
    job = _job()
    repository = _Repository([job], authorized=False)
    adapter = _Adapter()
    resolved = []

    async def resolver(account_id):
        resolved.append(account_id)
        return adapter

    asyncio.run(OutboxProcessor(repository, resolver).process_once("worker-1"))

    assert repository.authorization_checks == [job.id]
    assert resolved == []
    assert adapter.calls == []
    assert repository.sent == []
    assert repository.failed == []


def test_worker_ghi_ket_qua_trong_cung_delivery_fence_voi_provider_call():
    class GuardRepository(_Repository):
        def __init__(self, jobs):
            super().__init__(jobs)
            self.guard_active = False
            self.finalized_while_guarded = []

        @asynccontextmanager
        async def delivery_guard(self, job):
            self.guard_active = True
            try:
                yield True
            finally:
                self.guard_active = False

        async def mark_sent(self, job_id, provider_result):
            self.finalized_while_guarded.append(self.guard_active)
            await super().mark_sent(job_id, provider_result)

    repository = GuardRepository([_job()])

    async def resolver(_account_id):
        return _Adapter()

    asyncio.run(OutboxProcessor(repository, resolver).process_once("worker-1"))

    assert repository.finalized_while_guarded == [True]


def test_worker_delivery_false_di_vao_retry_khong_bao_sent():
    job = _job()
    repository = _Repository([job])
    adapter = _Adapter(Delivery(False, "provider timeout"))

    async def resolver(account_id):
        return adapter

    asyncio.run(OutboxProcessor(repository, resolver).process_once("worker-1"))

    assert repository.sent == []
    assert repository.failed == [(job.id, "provider timeout")]


def test_worker_gui_file_qua_exact_account_adapter():
    job = _job(
        kind="send_file",
        payload={
            "conversation_ref": "customer-1",
            "path": "data/products/p1.jpg",
            "caption": "Sản phẩm P1",
        },
    )
    repository = _Repository([job])
    adapter = _Adapter()

    async def resolver(account_id):
        assert account_id == job.account_id
        return adapter

    asyncio.run(OutboxProcessor(repository, resolver).process_once("worker-1"))

    assert adapter.calls == [
        ("customer-1", "data/products/p1.jpg", "Sản phẩm P1")
    ]
    assert repository.sent[0][0] == job.id


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Connection:
    def __init__(self):
        self.sql = ""
        self.args = ()

    def transaction(self):
        return _Transaction()

    async def fetch(self, sql, *args):
        self.sql = sql
        self.args = args
        return []


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


def test_postgres_claim_dung_skip_locked_va_nhat_lai_stale_job():
    connection = _Connection()
    repository = PostgresOutboxRepository(lambda: _Pool(connection))

    jobs = asyncio.run(
        repository.claim(worker_id="worker-1", limit=10, stale_after_seconds=120)
    )

    assert jobs == []
    assert "FOR UPDATE SKIP LOCKED" in connection.sql
    assert "locked_at" in connection.sql
    assert "processing" in connection.sql
    assert connection.args == ("worker-1", 120, 10)


class _SentConnection:
    def __init__(self, link):
        self.link = link
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

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args, self.in_transaction))
        return self.link

    async def execute(self, sql, *args):
        self.calls.append((sql, args, self.in_transaction))
        return "UPDATE 1"


def test_mark_sent_cap_nhat_job_message_va_realtime_event_cung_transaction():
    job_id = uuid4()
    link = {
        "account_id": uuid4(),
        "conversation_id": uuid4(),
        "message_id": uuid4(),
        "message_role": "staff",
    }
    connection = _SentConnection(link)
    repository = PostgresOutboxRepository(lambda: _Pool(connection))

    asyncio.run(repository.mark_sent(job_id, {"provider_message_id": "p1"}))

    assert all(call[2] for call in connection.calls)
    sql = "\n".join(call[0] for call in connection.calls)
    assert "UPDATE outbox_jobs" in sql
    assert "UPDATE messages" in sql
    assert "delivery_status = 'sent'" in sql
    assert "first_responded_at" in sql
    assert "first_response_met" in sql
    assert "INSERT INTO inbox_events" in sql


def test_mark_failed_cap_nhat_job_message_va_event_cung_transaction():
    job = _job(attempts=3, max_attempts=3, status=OutboxStatus.PROCESSING)
    link = {
        "account_id": job.account_id,
        "conversation_id": job.conversation_id,
        "message_id": job.message_id,
    }
    connection = _SentConnection(link)
    repository = PostgresOutboxRepository(lambda: _Pool(connection))

    asyncio.run(repository.mark_failed(job, "provider timeout"))

    assert all(call[2] for call in connection.calls)
    sql = "\n".join(call[0] for call in connection.calls)
    assert "UPDATE outbox_jobs" in sql
    assert "RETURNING account_id, conversation_id, message_id" in sql
    assert "UPDATE messages" in sql
    assert "delivery_status = $2" in sql
    assert "INSERT INTO inbox_events" in sql
    assert any("outbox.dead" in str(call[1]) for call in connection.calls)


def test_outbox_loop_tiep_tuc_sau_loi_claim_va_ghi_nhat_ky():
    class Processor:
        def __init__(self):
            self.calls = 0

        async def process_once(self, worker_id):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("database unavailable")
            return 0

    processor = Processor()
    errors = []
    sleeps = 0

    async def log_error(message):
        errors.append(message)

    async def sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps >= 2:
            raise asyncio.CancelledError

    async def run():
        try:
            await outbox_loop(
                processor,
                worker_id="worker-1",
                interval_seconds=0.01,
                log_error=log_error,
                sleep=sleep,
            )
        except asyncio.CancelledError:
            pass

    asyncio.run(run())

    assert processor.calls == 2
    assert errors == ["RuntimeError: database unavailable"]


def test_app_lifespan_khoi_dong_va_dung_outbox_worker():
    from agent import main

    source = inspect.getsource(main.lifespan)

    assert "OutboxProcessor" in source
    assert "outbox_loop" in source
    # Task nền được gom vào `tasks_nen` và huỷ đồng loạt lúc tắt, thay vì
    # huỷ từng biến một. Nhớ huỷ từng cái là cách bỏ sót: thêm vòng lặp thứ
    # tám mà quên thêm dòng huỷ thì nó sống qua shutdown, và không gì báo.
    assert "_nen(" in source, "outbox worker phải dựng qua _nen()"
    assert "for task in tasks_nen:" in source
    assert "task.cancel()" in source


def test_postgres_worker_heartbeat_upsert_theo_ten_worker():
    connection = _SentConnection(None)
    repository = PostgresOutboxRepository(lambda: _Pool(connection))

    asyncio.run(repository.heartbeat("worker-1"))

    sql, args, _ = connection.calls[0]
    assert "INSERT INTO worker_heartbeats" in sql
    assert "ON CONFLICT (worker_name)" in sql
    assert args == ("outbox", "worker-1")
