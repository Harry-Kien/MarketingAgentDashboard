"""SLA worker idempotent, tiếp tục sau lỗi và không phụ thuộc provider."""
from __future__ import annotations

import asyncio

from agent.omnichannel.sla import SlaMonitor, sla_loop


class _Repository:
    def __init__(self):
        self.calls = 0
        self.heartbeats = []

    async def mark_breaches(self):
        self.calls += 1
        return {"first_response": 2, "resolution": 1}

    async def heartbeat(self, worker_id):
        self.heartbeats.append(worker_id)


def test_sla_monitor_mark_breach_va_heartbeat():
    repository = _Repository()

    result = asyncio.run(SlaMonitor(repository).scan_once("sla-1"))

    assert result == {"first_response": 2, "resolution": 1}
    assert repository.heartbeats == ["sla-1"]


def test_sla_loop_tu_phuc_hoi_sau_loi_db():
    class Flaky(_Repository):
        async def mark_breaches(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("db down")
            return {"first_response": 0, "resolution": 0}

    repository = Flaky()
    errors = []
    sleeps = 0

    async def sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 2:
            raise asyncio.CancelledError

    async def log_error(error):
        errors.append(error)

    async def run():
        try:
            await sla_loop(
                SlaMonitor(repository), worker_id="sla-1",
                sleep=sleep, log_error=log_error,
            )
        except asyncio.CancelledError:
            pass

    asyncio.run(run())

    assert repository.calls == 2
    assert errors == ["RuntimeError: db down"]
