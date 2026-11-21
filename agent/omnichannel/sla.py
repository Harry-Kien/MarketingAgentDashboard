"""Worker SLA idempotent: đánh dấu warning/breach, phát event và heartbeat."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
import json
from typing import Any, Protocol

from agent import db
from agent.config import settings
from agent.core.gio_lam_viec import VN

_DEFAULT_FIRST_RESPONSE_MINUTES = {
    "urgent": 5,
    "high": 10,
    "normal": 30,
    "low": 120,
}


def thoi_gian_sla_da_tieu_thu(started_at: datetime, scan_at: datetime) -> timedelta:
    """Tính thời gian SLA đã tiêu thụ giữa started_at và scan_at theo giờ làm việc."""
    if scan_at <= started_at:
        return timedelta(0)
    # Cùng công tắc với hạn SLA (`agent/omnichannel/sla_gio.py`): hạn tính
    # 24/7 mà cảnh báo đếm theo giờ làm việc thì cảnh báo tới SAU vi phạm.
    if not settings.sla_theo_gio_lam_viec or not settings.gio_lam_viec_bat:
        return scan_at - started_at
    bat_dau_gio = settings.gio_lam_viec_bat_dau
    ket_thuc_gio = settings.gio_lam_viec_ket_thuc
    if ket_thuc_gio <= bat_dau_gio:
        return timedelta(0)

    start_vn = started_at.astimezone(VN)
    end_vn = scan_at.astimezone(VN)

    def _window(ngay: date) -> tuple[datetime, datetime]:
        goc = datetime(ngay.year, ngay.month, ngay.day, tzinfo=VN)
        return goc + timedelta(hours=bat_dau_gio), goc + timedelta(hours=ket_thuc_gio)

    s0, s1 = _window(start_vn.date())
    e0, e1 = _window(end_vn.date())
    if start_vn.date() == end_vn.date():
        return max(timedelta(0), min(end_vn, s1) - max(start_vn, s0))

    ngay_dau = max(timedelta(0), s1 - max(start_vn, s0))
    ngay_cuoi = max(timedelta(0), min(end_vn, e1) - e0)
    so_ngay_tron = max(0, (end_vn.date() - start_vn.date()).days - 1)
    return ngay_dau + so_ngay_tron * timedelta(hours=ket_thuc_gio - bat_dau_gio) + ngay_cuoi


def _warning_threshold(priority: str | None, policy_minutes: int | None) -> timedelta:
    minutes = policy_minutes or _DEFAULT_FIRST_RESPONSE_MINUTES.get(
        (priority or "normal").lower(), 30
    )
    return timedelta(minutes=minutes) / 2


class SlaRepository(Protocol):
    async def mark_breaches(
        self, *, at: datetime | None = None
    ) -> dict[str, int]: ...

    async def heartbeat(self, worker_id: str) -> None: ...


class SlaMonitor:
    def __init__(self, repository: SlaRepository):
        self._repository = repository

    async def scan_once(
        self, worker_id: str, *, at: datetime | None = None
    ) -> dict[str, int]:
        if at is None:
            result = await self._repository.mark_breaches()
        else:
            result = await self._repository.mark_breaches(at=at)
        await self._repository.heartbeat(worker_id)
        return result


class PostgresSlaRepository:
    def __init__(self, pool_provider: Callable[[], Any] = db.pool):
        self._pool_provider = pool_provider

    async def mark_breaches(
        self, *, at: datetime | None = None
    ) -> dict[str, int]:
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                scan_at = (
                    at
                    if at is not None
                    else await connection.fetchval("SELECT now()")
                )
                if scan_at.tzinfo is None:
                    scan_at = scan_at.replace(tzinfo=timezone.utc)

                candidates = await connection.fetch(
                    """
                    SELECT conversation.id AS conversation_id,
                           conversation.first_response_due_at,
                           conversation.priority,
                           COALESCE(started_event.created_at, conversation.created_at) AS started_at,
                           (
                               SELECT policy.first_response_minutes
                               FROM sla_policies policy
                               WHERE policy.active
                                 AND policy.priority = conversation.priority
                                 AND (
                                     policy.account_id = conversation.account_id
                                     OR policy.account_id IS NULL
                                 )
                               ORDER BY (policy.account_id = conversation.account_id) DESC NULLS LAST
                               LIMIT 1
                           ) AS first_response_minutes
                    FROM conversations conversation
                    LEFT JOIN LATERAL (
                        SELECT event.created_at
                        FROM sla_events event
                        WHERE event.conversation_id = conversation.id
                          AND event.kind = 'started'
                          AND event.chu_ky = conversation.sla_chu_ky
                        ORDER BY event.created_at DESC
                        LIMIT 1
                    ) started_event ON TRUE
                    WHERE conversation.state IN ('open', 'pending')
                      AND conversation.first_responded_at IS NULL
                      AND conversation.first_response_due_at IS NOT NULL
                      AND conversation.first_response_due_at >= $1
                      AND NOT EXISTS (
                          SELECT 1 FROM sla_events done_event
                          WHERE done_event.conversation_id = conversation.id
                            AND done_event.chu_ky = conversation.sla_chu_ky
                            AND done_event.kind IN (
                                'first_response_warning',
                                'first_response_met',
                                'first_response_breached'
                            )
                      )
                    """,
                    scan_at,
                )

                warn_ids: list[Any] = []
                warn_dues: list[datetime] = []
                warn_details: list[str] = []
                for row in candidates:
                    threshold = _warning_threshold(
                        row["priority"], row["first_response_minutes"]
                    )
                    elapsed = thoi_gian_sla_da_tieu_thu(row["started_at"], scan_at)
                    if elapsed >= threshold:
                        warn_ids.append(row["conversation_id"])
                        warn_dues.append(row["first_response_due_at"])
                        warn_details.append(
                            json.dumps(
                                {
                                    "threshold_ratio": 0.5,
                                    "threshold_minutes": round(
                                        threshold.total_seconds() / 60.0, 2
                                    ),
                                    "elapsed_minutes": round(
                                        elapsed.total_seconds() / 60.0, 2
                                    ),
                                }
                            )
                        )

                warning_rows = []
                if warn_ids:
                    warning_rows = await connection.fetch(
                        """
                        INSERT INTO sla_events (conversation_id, chu_ky, kind, due_at, detail)
                        SELECT c.id, c.sla_chu_ky, 'first_response_warning', c.first_response_due_at,
                               d.detail::jsonb
                        FROM unnest($1::uuid[], $2::timestamptz[], $3::text[])
                             AS d(conversation_id, due_at, detail)
                        JOIN conversations c ON c.id = d.conversation_id
                        WHERE c.state IN ('open', 'pending')
                          AND c.first_responded_at IS NULL
                          AND c.first_response_due_at = d.due_at
                        ON CONFLICT (conversation_id, chu_ky, kind) DO NOTHING
                        RETURNING conversation_id
                        """,
                        warn_ids,
                        warn_dues,
                        warn_details,
                    )

                first_rows = await connection.fetch(
                    """
                    INSERT INTO sla_events (conversation_id, chu_ky, kind, due_at, detail)
                    SELECT conversation.id, conversation.sla_chu_ky, 'first_response_breached',
                           conversation.first_response_due_at, '{}'
                    FROM conversations conversation
                    WHERE conversation.state IN ('open', 'pending')
                      AND conversation.first_responded_at IS NULL
                      AND conversation.first_response_due_at < $1
                    ON CONFLICT (conversation_id, chu_ky, kind) DO NOTHING
                    RETURNING conversation_id
                    """,
                    scan_at,
                )
                resolution_rows = await connection.fetch(
                    """
                    INSERT INTO sla_events (conversation_id, chu_ky, kind, due_at, detail)
                    SELECT conversation.id, conversation.sla_chu_ky, 'resolution_breached',
                           conversation.resolution_due_at, '{}'
                    FROM conversations conversation
                    WHERE conversation.state IN ('open', 'pending')
                      AND conversation.resolved_at IS NULL
                      AND conversation.resolution_due_at < $1
                    ON CONFLICT (conversation_id, chu_ky, kind) DO NOTHING
                    RETURNING conversation_id
                    """,
                    scan_at,
                )
                for topic, rows in (
                    ("sla.first_response_warning", warning_rows),
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
            # Chuông nội bộ — SAU khi giao dịch đã chốt, nên chuông hỏng
            # không cuộn ngược sự kiện SLA. Mỗi sự kiện chỉ chèn được một lần
            # (khoá hội thoại, chu kỳ, loại), nên chỉ báo một lần.
            from agent.core import thong_bao_noi_bo

            await thong_bao_noi_bo.bao_sla(connection, [
                (row["conversation_id"], kind)
                for kind, rows in (
                    ("first_response_warning", warning_rows),
                    ("first_response_breached", first_rows),
                    ("resolution_breached", resolution_rows),
                )
                for row in rows
            ])
        return {
            "first_response": len(first_rows),
            "resolution": len(resolution_rows),
            "warning": len(warning_rows),
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
