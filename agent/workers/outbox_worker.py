"""Claim outbox, gọi provider ngoài transaction rồi cập nhật kết quả."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import UUID

from agent.omnichannel.outbox import OutboxJob


class OutboxRepository(Protocol):
    async def heartbeat(self, worker_id: str) -> None: ...

    async def claim(
        self,
        *,
        worker_id: str,
        limit: int,
        stale_after_seconds: int,
    ) -> list[OutboxJob]: ...

    async def mark_sent(self, job_id: UUID, provider_result: dict) -> None: ...

    async def mark_failed(self, job: OutboxJob, error: str) -> None: ...

    def delivery_guard(self, job: OutboxJob): ...


class OutboxProcessor:
    def __init__(
        self,
        repository: OutboxRepository,
        adapter_resolver: Callable[[UUID], Awaitable[Any]],
        *,
        batch_size: int = 20,
        stale_after_seconds: int = 120,
    ):
        self._repository = repository
        self._adapter_resolver = adapter_resolver
        self._batch_size = batch_size
        self._stale_after_seconds = stale_after_seconds

    async def process_once(self, worker_id: str) -> int:
        jobs = await self._repository.claim(
            worker_id=worker_id,
            limit=self._batch_size,
            stale_after_seconds=self._stale_after_seconds,
        )
        for job in jobs:
            try:
                # Kiểm ngay trước provider call để đóng race: người thật có thể
                # takeover sau lúc claim nhưng trước lúc worker gửi. Guard giữ
                # khóa conversation tới khi provider call kết thúc; takeover
                # dùng cùng khóa nên không thể commit chen giữa check và send.
                async with self._repository.delivery_guard(job) as authorized:
                    if not authorized:
                        continue
                    try:
                        adapter = await self._adapter_resolver(job.account_id)
                        delivery = await self._deliver(adapter, job)
                    except Exception as exc:  # noqa: BLE001
                        await self._repository.mark_failed(
                            job,
                            f"{type(exc).__name__}: {exc}"[:500],
                        )
                        continue
                    if getattr(delivery, "ok", False):
                        await self._repository.mark_sent(
                            job.id,
                            {
                                "detail": str(
                                    getattr(delivery, "detail", "")
                                )[:200],
                                "provider_message_id": str(
                                    getattr(delivery, "provider_message_id", "")
                                )[:240]
                                or None,
                            },
                        )
                    else:
                        await self._repository.mark_failed(
                            job,
                            str(
                                getattr(delivery, "detail", "provider từ chối")
                            )[:500],
                        )
            except Exception as exc:  # noqa: BLE001 — một job không làm chết batch
                await self._repository.mark_failed(
                    job,
                    f"{type(exc).__name__}: {exc}"[:500],
                )
        await self._repository.heartbeat(worker_id)
        return len(jobs)

    @staticmethod
    async def _deliver(adapter, job: OutboxJob):
        if job.kind == "send_text":
            return await adapter.send_text(
                str(job.payload["conversation_ref"]),
                str(job.payload["text"]),
            )
        if job.kind == "send_file":
            return await adapter.send_file(
                str(job.payload["conversation_ref"]),
                str(job.payload["path"]),
                caption=str(job.payload.get("caption", "")),
            )
        raise ValueError(f"outbox kind chưa hỗ trợ: {job.kind}")


async def outbox_loop(
    processor: OutboxProcessor,
    *,
    worker_id: str,
    interval_seconds: float = 0.5,
    log_error: Callable[[str], Awaitable[None]] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Chạy outbox bền bỉ; lỗi claim không được làm chết worker nền."""
    while True:
        try:
            await processor.process_once(worker_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — worker phải tự hồi phục
            if log_error is not None:
                await log_error(f"{type(exc).__name__}: {exc}"[:500])
        await sleep(interval_seconds)
