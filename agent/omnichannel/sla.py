"""Worker SLA idempotent: đánh dấu breach, phát event và heartbeat."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from agent import db


class SlaRepository(Protocol):
    async def mark_breaches(self) -> dict[str, int]: ...

    async def heartbeat(self, worker_id: str) -> None: ...


class SlaMonitor:
    def __init__(self, repository: SlaRepository):
        self._repository = repository

    async def scan_once(self, worker_id: str) -> dict[str, int]:
        result = await self._repository.mark_breaches()
        await self._repository.heartbeat(worker_id)
        return result


class PostgresSlaRepository:
    def __init__(self, pool_provider: Callable[[], Any] = db.pool):
        self._pool_provider = pool_provider

    async def mark_breaches(self) -> dict[str, int]:
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                first_rows = await connection.fetch(
                    """
                    INSERT INTO sla_events (conversation_id, kind, due_at, detail)
                    SELECT conversation.id, 'first_response_breached',
                           conversation.first_response_due_at, '{}'
                    FROM conversations conversation
                    WHERE conversation.state IN ('open', 'pending')
                      AND conversation.first_responded_at IS NULL
                      AND conversation.first_response_due_at < now()
                    ON CONFLICT (conversation_id, kind) DO NOTHING
                    RETURNING conversation_id
                    """
                )
                resolution_rows = await connection.fetch(
                    """
                    INSERT INTO sla_events (conversation_id, kind, due_at, detail)
                    SELECT conversation.id, 'resolution_breached',
                           conversation.resolution_due_at, '{}'
                    FROM conversations conversation
                    WHERE conversation.state IN ('open', 'pending')
                      AND conversation.resolved_at IS NULL
                      AND conversation.resolution_due_at < now()
                    ON CONFLICT (conversation_id, kind) DO NOTHING
                    RETURNING conversation_id
                    """
                )
                for topic, rows in (
                    ("sla.first_response_breached", first_rows),
                    ("sla.resolution_breached", resolution_rows),
                ):
                    ids = [row["conversation_id"] for row in rows]
                    if ids:
                        await connection.execute(
                            """
                            INSERT INTO inbox_events (account_id, topic, ref_id, payload)
                            SELECT account_id, $2, id, '{}'
                            FROM conversations WHERE id = ANY($1::uuid[])
                            """,
                            ids,
                            topic,
                        )
        return {
            "first_response": len(first_rows),
            "resolution": len(resolution_rows),
        }

    async def heartbeat(self, worker_id: str) -> None:
        async with self._pool_provider().acquire() as connection:
            await connection.execute(
                """
                INSERT INTO worker_heartbeats (
                    worker_name, worker_id, last_seen_at, detail
                ) VALUES ('sla',$1,now(),'{}')
                ON CONFLICT (worker_name) DO UPDATE
                SET worker_id = excluded.worker_id,
                    last_seen_at = excluded.last_seen_at
                """,
                worker_id,
            )


async def sla_loop(
    monitor: SlaMonitor,
    *,
    worker_id: str,
    interval_seconds: float = 15.0,
    log_error: Callable[[str], Awaitable[None]] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    while True:
        try:
            await monitor.scan_once(worker_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — monitor phải tự hồi phục
            if log_error is not None:
                await log_error(f"{type(exc).__name__}: {exc}"[:500])
        await sleep(interval_seconds)
