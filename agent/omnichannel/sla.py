"""
Worker SLA idempotent: đánh dấu warning/breach, phát event, leo thang khi
trễ (việc gấp + báo nhân viên) và heartbeat.
"""
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


async def _canh_bao_giai_quyet(connection: Any, scan_at: datetime) -> list[Any]:
    """
    Cảnh báo sớm HẠN GIẢI QUYẾT: đã tiêu hết một nửa khoảng từ lúc bắt đầu
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
        khoang = thoi_gian_sla_da_tieu_thu(row["started_at"], row["resolution_due_at"])
        threshold = khoang / 2
        elapsed = thoi_gian_sla_da_tieu_thu(row["started_at"], scan_at)
        if threshold > timedelta(0) and elapsed >= threshold:
            ids.append(row["conversation_id"])
            dues.append(row["resolution_due_at"])
            details.append(json.dumps({
                "threshold_ratio": 0.5,
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


# Khoá chống trùng của việc leo thang: một việc cho mỗi (hội thoại, chu kỳ,
# loại vi phạm). `giai_quyet.py` nhận ra việc SLA bằng tiền tố này để không
# chặn nút "Đã giải quyết" và tự đóng nó khi hội thoại xong.
TIEN_TO_VIEC_SLA = "sla:"

_TIEU_DE_VIEC = {
    "first_response_breached": "Trễ SLA phản hồi đầu",
    "resolution_breached": "Trễ SLA giải quyết",
}


async def leo_thang_khi_tre(pool_provider: Callable[[], Any] = db.pool) -> int:
    """
    Vi phạm SLA → một công việc gấp + báo nhân viên (+ nâng ưu tiên nếu bật).

    VÌ SAO
    ------
    Trước bản này vi phạm chỉ là một dòng `sla_events` và một sự kiện SSE:
    không ai mở dashboard thì không ai biết khách đã chờ quá hạn — đúng kiểu
    hỏng im lặng CLAUDE.md cảnh báo.

    CHỈ VI PHẠM CÒN ĐANG TREO
    -------------------------
    Phản hồi đầu: hội thoại vẫn chưa ai trả lời. Sự kiện trễ do outbox ghi
    lúc trả lời MUỘN (detail có `phan_hoi_luc`) không sinh việc — khách đã
    được trả lời, việc ấy không còn gì để làm. Giải quyết: hội thoại còn mở.
    Chỉ xét vi phạm trong 24 giờ: lượt quét đầu sau khi triển khai không
    được đổ việc cho mọi vi phạm cũ trong lịch sử.

    CẤU HÌNH `SLA_KHI_TRE` (agent/cau_hinh_dong.py)
    -----------------------------------------------
    `bao` (mặc định): chỉ tạo việc và báo. `bao_va_nang_uu_tien`: nâng ưu
    tiên một bậc để hội thoại lên đầu hàng chờ — KHÔNG rút hạn: máy tự rút
    hạn sau một vi phạm là phạt người trực lần thứ hai cho cùng một lỗi.

    Trả số việc vừa tạo.
    """
    from agent import cau_hinh_dong, canh_gac
    from agent.core.cong_viec import TEN_KENH

    async with pool_provider().acquire() as connection:
        async with connection.transaction():
            rows = await connection.fetch(
                """
                INSERT INTO cong_viec (tieu_de, mo_ta, nguon, uu_tien,
                                       conversation_id, contact_id, khoa_chong_trung)
                SELECT left(CASE s.kind WHEN 'first_response_breached'
                            THEN 'Trễ SLA phản hồi đầu' ELSE 'Trễ SLA giải quyết' END
                       || coalesce(': ' || nullif(c.customer_name, ''), ''), 200),
                       CASE s.kind WHEN 'first_response_breached'
                            THEN 'Khách chưa được trả lời và đã quá hạn phản hồi đầu. '
                                 'Mở hội thoại để trả lời khách.'
                            ELSE 'Hội thoại đã quá hạn giải quyết. Xử lý xong rồi bấm '
                                 '"Đã giải quyết" — việc này tự đóng theo.' END,
                       'tu_dong', 'gap', c.id, c.contact_id,
                       $1 || c.id::text || ':' || s.chu_ky || ':' || s.kind
                FROM sla_events s
                JOIN conversations c
                  ON c.id = s.conversation_id AND s.chu_ky = c.sla_chu_ky
                WHERE s.created_at > now() - interval '1 day'
                  AND c.state IN ('open', 'pending')
                  AND c.channel <> 'phong_thu'
                  AND (
                      (s.kind = 'first_response_breached'
                       AND c.first_responded_at IS NULL
                       AND NOT (s.detail ? 'phan_hoi_luc'))
                   OR (s.kind = 'resolution_breached' AND c.resolved_at IS NULL)
                  )
                ON CONFLICT DO NOTHING
                RETURNING id, conversation_id, khoa_chong_trung
                """,
                TIEN_TO_VIEC_SLA,
            )
            if not rows:
                return 0
            cids = list({r["conversation_id"] for r in rows})
            if cau_hinh_dong.lay("SLA_KHI_TRE") == "bao_va_nang_uu_tien":
                nang = await connection.fetch(
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
                    cids,
                )
                for r in nang:
                    detail = {"tu": r["tu"], "den": r["den"], "tu_dong": True,
                              "ly_do": "tự nâng khi trễ SLA (SLA_KHI_TRE)"}
                    await connection.execute(
                        "INSERT INTO events (kind, actor, ref_id, detail) "
                        "VALUES ('conversation.priority_changed', 'sla', $1, $2)",
                        r["id"], detail)
                    await connection.execute(
                        "INSERT INTO inbox_events (account_id, topic, ref_id, payload) "
                        "VALUES ($1, 'conversation.priority_changed', $2, $3)",
                        r["account_id"], r["id"], detail)
            kenh = {
                r["id"]: r["channel"]
                for r in await connection.fetch(
                    "SELECT c.id, coalesce(ca.channel, c.channel) AS channel "
                    "FROM conversations c LEFT JOIN channel_accounts ca ON ca.id = c.account_id "
                    "WHERE c.id = ANY($1::uuid[])", cids)
            }

    # Báo SAU khi đã chốt: không báo một việc mà giao dịch rồi lại huỷ.
    # Chỉ nói loại vi phạm và KÊNH — tên khách không đi sang Telegram
    # (cùng lý do với `cong_viec._bao_viec_moi_cho_nhan_vien`).
    if len(rows) > 3:
        canh_gac.bao_nhan_vien_nen(
            f"{len(rows)} hội thoại trễ SLA",
            "Đã tạo việc gấp cho từng hội thoại. Mở dashboard → Công việc.")
    else:
        for r in rows:
            loai = str(r["khoa_chong_trung"]).rsplit(":", 1)[-1]
            ten_kenh = kenh.get(r["conversation_id"]) or ""
            canh_gac.bao_nhan_vien_nen(
                _TIEU_DE_VIEC.get(loai, "Trễ SLA"),
                f"Kênh {TEN_KENH.get(ten_kenh, ten_kenh or 'không rõ')}: hội thoại "
                "đã quá hạn. Mở dashboard → Công việc.")
    return len(rows)


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
                resolution_warning_rows = await _canh_bao_giai_quyet(connection, scan_at)
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
                            """
                            INSERT INTO inbox_events (account_id, topic, ref_id, payload)
                            SELECT account_id, $2, id, '{}'
                            FROM conversations WHERE id = ANY($1::uuid[])
                            """,
                            ids,
                            topic,
                        )
        # Leo thang chạy SAU khi giao dịch đánh dấu đã chốt, trong lời gọi
        # riêng: một việc không tạo được (hội thoại vừa được giải quyết cùng
        # lúc — trigger 0045 từ chối) không được kéo theo cả sự kiện trễ của
        # mọi hội thoại khác. Việc bị lỡ thì lượt quét sau tự bù, vì câu lệnh
        # đi tìm MỌI vi phạm còn mở chưa có việc, không chỉ vi phạm vừa ghi.
        leo = await leo_thang_khi_tre(self._pool_provider)
        return {
            "first_response": len(first_rows),
            "resolution": len(resolution_rows),
            "warning": len(warning_rows),
            "resolution_warning": len(resolution_warning_rows),
            "leo_thang": leo,
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
