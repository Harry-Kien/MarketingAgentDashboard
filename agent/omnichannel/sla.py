"""
Worker SLA idempotent: đánh dấu cảnh báo/vi phạm, phát `inbox_events` đủ
thông tin cho chuông thông báo, (tuỳ cấu hình) nâng ưu tiên khi trễ, và
heartbeat.

KHÔNG sinh công việc khi trễ: chủ dự án chốt (20.11.2026) cảnh báo SLA đi
qua chuông thông báo trong ứng dụng. Mỗi sự kiện `sla.*` mang hội thoại,
loại, chu kỳ, người phụ trách, ưu tiên và hạn — đủ để chuông dựng thông báo
mà không phải đọc lại CSDL.

BA MỤC TIÊU, MỖI MỤC TIÊU MỘT CHẾ ĐỘ VÀ MỘT NGƯỠNG (mục 15, 22.11.2026):
phản hồi đầu, phản hồi sau chuyển giao (`sla_chuyen_giao.py`), giải quyết.
Lịch, chế độ và ngưỡng của từng mục tiêu đọc qua `sla_muc_tieu.py` — nạp
lại ở ĐẦU mỗi vòng quét, nên sửa trên dashboard có hiệu lực ở vòng kế.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
import json
from typing import Any, Protocol

from agent import db
from agent.omnichannel import sla_chuyen_giao, sla_muc_tieu

_DEFAULT_FIRST_RESPONSE_MINUTES = {
    "urgent": 5,
    "high": 10,
    "normal": 30,
    "low": 120,
}


def thoi_gian_sla_da_tieu_thu(
    started_at: datetime, scan_at: datetime, muc_tieu: str = "phan_hoi_dau"
) -> timedelta:
    """
    Thời gian SLA đã tiêu thụ giữa started_at và scan_at, theo CHẾ ĐỘ của
    mục tiêu (`sla_muc_tieu`): giờ làm việc của lịch chung, hoặc 24/7.

    Cùng lịch với hạn SLA của mục tiêu ấy (`sla_gio.bieu_thuc_han`): hạn tính
    24/7 mà cảnh báo đếm theo giờ làm việc thì cảnh báo tới SAU vi phạm.
    """
    return sla_muc_tieu.tieu_thu(started_at, scan_at, muc_tieu)


NGUONG_CANH_BAO_MAC_DINH = 80


def ty_le_canh_bao(muc_tieu: str | None = None) -> float:
    """
    Ngưỡng cảnh báo sớm (phần của thời gian cho phép).

    Không nêu mục tiêu: ngưỡng CHUNG `SLA_NGUONG_CANH_BAO` (dashboard → .env
    → 80%). Nêu mục tiêu: ngưỡng riêng của mục tiêu nếu đã đặt trên
    dashboard, không thì ngưỡng chung. Giá trị hỏng lui về 80% chứ không
    ném: worker SLA chết vì một ô cấu hình là mất luôn cả vi phạm.
    """
    if muc_tieu is None:
        return sla_muc_tieu.nguong_chung() / 100
    return sla_muc_tieu.nguong(muc_tieu)


def _warning_threshold(
    priority: str | None, policy_minutes: int | None, ty_le: float
) -> timedelta:
    minutes = policy_minutes or _DEFAULT_FIRST_RESPONSE_MINUTES.get(
        (priority or "normal").lower(), 30
    )
    return timedelta(minutes=minutes) * ty_le


async def _canh_bao_giai_quyet(
    connection: Any, scan_at: datetime, ty_le: float
) -> list[Any]:
    """
    Cảnh báo sớm HẠN GIẢI QUYẾT: đã tiêu hết `ty_le` khoảng từ lúc bắt đầu
    chu kỳ tới hạn (migration 0054).

    Ngưỡng tính trên KHOẢNG THẬT [bắt đầu, hạn] chứ không trên số phút của
    chính sách như cảnh báo phản hồi đầu: hạn có thể đã được rút ngắn khi
    nâng ưu tiên (agent/api/uu_tien.py), và số phút của chính sách khi ấy
    không còn nói hạn ở đâu. Đo bằng `thoi_gian_sla_da_tieu_thu` nên tôn
    trọng công tắc 24/7 (`SLA_THEO_GIO_LAM_VIEC`) y như cảnh báo cũ.
    """
    candidates = await connection.fetch(
        """
        SELECT c.id AS conversation_id, c.resolution_due_at,
               COALESCE(started_event.created_at, c.created_at) AS started_at
        FROM conversations c
        LEFT JOIN LATERAL (
            SELECT event.created_at FROM sla_events event
            WHERE event.conversation_id = c.id AND event.kind = 'started'
              AND event.chu_ky = c.sla_chu_ky
            ORDER BY event.created_at DESC LIMIT 1
        ) started_event ON TRUE
        WHERE c.state IN ('open', 'pending')
          AND c.resolved_at IS NULL
          AND c.resolution_due_at IS NOT NULL
          AND c.resolution_due_at >= $1
          AND NOT EXISTS (
              SELECT 1 FROM sla_events done_event
              WHERE done_event.conversation_id = c.id
                AND done_event.chu_ky = c.sla_chu_ky
                AND done_event.kind IN (
                    'resolution_warning', 'resolution_met', 'resolution_breached'
                )
          )
        """,
        scan_at,
    )
    ids: list[Any] = []
    dues: list[datetime] = []
    details: list[str] = []
    for row in candidates:
        khoang = thoi_gian_sla_da_tieu_thu(
            row["started_at"], row["resolution_due_at"], "giai_quyet")
        threshold = khoang * ty_le
        elapsed = thoi_gian_sla_da_tieu_thu(row["started_at"], scan_at, "giai_quyet")
        if threshold > timedelta(0) and elapsed >= threshold:
            ids.append(row["conversation_id"])
            dues.append(row["resolution_due_at"])
            details.append(json.dumps({
                "threshold_ratio": ty_le,
                "threshold_minutes": round(threshold.total_seconds() / 60.0, 2),
                "elapsed_minutes": round(elapsed.total_seconds() / 60.0, 2),
            }))
    if not ids:
        return []
    return list(await connection.fetch(
        """
        INSERT INTO sla_events (conversation_id, chu_ky, kind, due_at, detail)
        SELECT c.id, c.sla_chu_ky, 'resolution_warning', c.resolution_due_at,
               d.detail::jsonb
        FROM unnest($1::uuid[], $2::timestamptz[], $3::text[])
             AS d(conversation_id, due_at, detail)
        JOIN conversations c ON c.id = d.conversation_id
        WHERE c.state IN ('open', 'pending')
          AND c.resolved_at IS NULL
          AND c.resolution_due_at = d.due_at
        ON CONFLICT (conversation_id, chu_ky, kind) DO NOTHING
        RETURNING conversation_id
        """,
        ids, dues, details,
    ))


async def _nang_uu_tien_khi_tre(connection: Any, ids: list[Any]) -> int:
    """
    `SLA_KHI_TRE = bao_va_nang_uu_tien`: hội thoại VỪA trễ lên một bậc ưu tiên.

    Chạy trên đúng những vi phạm vừa ghi ở lượt quét này (ON CONFLICT nuốt
    vi phạm cũ), nên mỗi vi phạm nâng đúng một lần. KHÔNG rút hạn: máy tự
    rút hạn sau một vi phạm là phạt người trực lần thứ hai cho cùng một lỗi.
    Mỗi lần nâng ghi nhật ký kiểm toán như khi người đổi (actor `sla`).
    """
    from agent import cau_hinh_dong

    if not ids or cau_hinh_dong.lay("SLA_KHI_TRE") != "bao_va_nang_uu_tien":
        return 0
    rows = await connection.fetch(
        """
        WITH cu AS (
            SELECT id, priority FROM conversations
            WHERE id = ANY($1::uuid[]) AND priority <> 'urgent'
              AND state IN ('open', 'pending')
            FOR UPDATE
        )
        UPDATE conversations c
        SET priority = CASE cu.priority WHEN 'low' THEN 'normal'
                                        WHEN 'normal' THEN 'high'
                                        ELSE 'urgent' END,
            version = c.version + 1, updated_at = now()
        FROM cu WHERE c.id = cu.id
        RETURNING c.id, c.account_id, cu.priority AS tu, c.priority AS den
        """,
        list(set(ids)),
    )
    for r in rows:
        detail = {"tu": r["tu"], "den": r["den"], "tu_dong": True,
                  "ly_do": "tự nâng khi trễ SLA (SLA_KHI_TRE)"}
        await connection.execute(
            "INSERT INTO events (kind, actor, ref_id, detail) "
            "VALUES ('conversation.priority_changed', 'sla', $1, $2::text::jsonb)",
            r["id"], json.dumps(detail))
        await connection.execute(
            "INSERT INTO inbox_events (account_id, topic, ref_id, payload) "
            "VALUES ($1, 'conversation.priority_changed', $2, $3::text::jsonb)",
            r["account_id"], r["id"], json.dumps(detail))
    return len(rows)


# Sự kiện SLA cho chuông thông báo: đủ để dựng một dòng "Khách X quá hạn phản
# hồi đầu, đang giao cho Y" mà không phải tra lại. `han` là hạn của ĐÚNG mục
# tiêu bị cảnh báo/vi phạm.
_SQL_SU_KIEN_SLA = """
    INSERT INTO inbox_events (account_id, topic, ref_id, payload)
    SELECT c.account_id, $2, c.id,
           jsonb_build_object(
               'conversation_id', c.id, 'loai', $3::text, 'chu_ky', c.sla_chu_ky,
               'nguoi_phu_trach', c.assigned_to, 'uu_tien', c.priority,
               'han', CASE WHEN $3::text LIKE 'first_response%'
                           THEN c.first_response_due_at ELSE c.resolution_due_at END)
    FROM conversations c WHERE c.id = ANY($1::uuid[])
"""


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
            # Lịch, chế độ, ngưỡng của từng mục tiêu: nạp lại MỖI vòng (và
            # ngoài giao dịch — bảng chưa có thì lỗi đọc không làm hỏng giao
            # dịch quét). Không bao giờ ném: hỏng thì giữ bản đã nạp.
            await sla_muc_tieu.nap(connection)
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

                ty_le = ty_le_canh_bao("phan_hoi_dau")
                warn_ids: list[Any] = []
                warn_dues: list[datetime] = []
                warn_details: list[str] = []
                for row in candidates:
                    threshold = _warning_threshold(
                        row["priority"], row["first_response_minutes"], ty_le
                    )
                    elapsed = thoi_gian_sla_da_tieu_thu(row["started_at"], scan_at)
                    if elapsed >= threshold:
                        warn_ids.append(row["conversation_id"])
                        warn_dues.append(row["first_response_due_at"])
                        warn_details.append(
                            json.dumps(
                                {
                                    "threshold_ratio": ty_le,
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
                resolution_warning_rows = await _canh_bao_giai_quyet(
                    connection, scan_at, ty_le_canh_bao("giai_quyet")
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
                    ("sla.resolution_warning", resolution_warning_rows),
                    ("sla.resolution_breached", resolution_rows),
                ):
                    ids = [row["conversation_id"] for row in rows]
                    if ids:
                        await connection.execute(
                            _SQL_SU_KIEN_SLA, ids, topic, topic.split(".", 1)[1]
                        )
                chuyen_giao = await sla_chuyen_giao.quet(connection, scan_at)
                nang = await _nang_uu_tien_khi_tre(
                    connection,
                    [r["conversation_id"] for r in (
                        *first_rows, *resolution_rows, *chuyen_giao["tre"])],
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
                    ("resolution_warning", resolution_warning_rows),
                    ("resolution_breached", resolution_rows),
                    ("handover_response_warning", chuyen_giao["canh_bao"]),
                    ("handover_response_breached", chuyen_giao["tre"]),
                )
                for row in rows
            ])
        return {
            "first_response": len(first_rows),
            "resolution": len(resolution_rows),
            "warning": len(warning_rows),
            "resolution_warning": len(resolution_warning_rows),
            "chuyen_giao_mo": len(chuyen_giao["mo"]),
            "chuyen_giao_canh_bao": len(chuyen_giao["canh_bao"]),
            "chuyen_giao_tre": len(chuyen_giao["tre"]),
            "nang_uu_tien": nang,
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
