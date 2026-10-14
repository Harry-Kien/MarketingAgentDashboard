"""
Giải quyết hội thoại, mở lại khi khách nhắn tiếp, và khảo sát CSAT.

LỖ ĐO ĐƯỢC 15.10.2026
---------------------
Luồng native KHÔNG có thao tác "đã giải quyết" nào. `resolved_at` không bao
giờ được ghi, nên bộ canh SLA (`sla.py`) coi MỌI hội thoại có hạn giải quyết
là trễ — sớm muộn cái nào cũng thành `resolution_breached`. Một con số sai
trên báo cáo hiệu suất của từng nhân viên, và không gì báo nó sai.

CSAT HỎI SAU KHI GIẢI QUYẾT, ĐỌC TRƯỚC KHI AGENT TRẢ LỜI
-------------------------------------------------------
Khách trả lời "5" thì tin ấy là ĐIỂM, không phải câu hỏi mới — không được
để agent trả lời "Dạ 5 là gì ạ?". Chỉ một tin gồm đúng một chữ số 1–5
(cho phép thêm chữ "sao"), trong 24 giờ sau khi hỏi, mới tính là điểm.
"""
from __future__ import annotations

import re
import time
from typing import Any
from uuid import UUID

from agent import cau_hinh_dong, db

CAU_HOI = ("Dạ shop cảm ơn anh/chị đã nhắn ạ. Anh/chị chấm giúp shop mức hài lòng "
           "từ 1 đến 5 nhé (5 là rất hài lòng) — chỉ cần nhắn một con số ạ.")
CAM_ON = "Dạ shop cảm ơn anh/chị đã đánh giá ạ!"
GIO_CHO = 24
_DIEM = re.compile(r"^\s*([1-5])\s*(sao|⭐)?\s*[.!]?\s*$", re.IGNORECASE)


def doc_diem(text: str) -> int | None:
    m = _DIEM.match(text or "")
    return int(m.group(1)) if m else None


async def giai_quyet(cid: UUID, nguoi_id: UUID | None) -> dict[str, Any]:
    """Đánh dấu đã giải quyết. Trả `{da_truoc, csat}`; 404 do chỗ gọi lo."""
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            r = await conn.fetchrow(
                "UPDATE conversations SET state = 'resolved', status = 'closed', "
                "outcome = 'resolved', resolved_at = now(), version = version + 1, "
                "updated_at = now() WHERE id = $1 AND state <> 'resolved' "
                "RETURNING id, assigned_to, resolution_due_at, external_id", cid)
            if r is None:
                return {"da_truoc": True, "csat": None}
            # Kết thúc lượt giao đang mở: hội thoại đã xong, người ấy rảnh tay.
            await conn.execute(
                "UPDATE conversation_assignments SET ended_at = now() "
                "WHERE conversation_id = $1 AND ended_at IS NULL", cid)
            await conn.execute(
                "INSERT INTO sla_events (conversation_id, kind, due_at) "
                "SELECT $1, 'resolution_met', $2::timestamptz "
                "WHERE $2::timestamptz IS NULL OR now() <= $2::timestamptz "
                "ON CONFLICT (conversation_id, kind) DO NOTHING",
                cid, r["resolution_due_at"])
    await db.log_event("conversation.resolved", ref_id=cid,
                       boi=str(nguoi_id) if nguoi_id else None)
    csat = await _hoi_csat(cid, str(r["external_id"]), r["assigned_to"] or nguoi_id)
    return {"da_truoc": False, "csat": csat}


async def _hoi_csat(cid: UUID, external_id: str, nguoi_xu_ly: UUID | None) -> str:
    """Gửi câu hỏi CSAT nếu bật. Trả lý do bằng chữ — kể cả khi KHÔNG gửi."""
    if cau_hinh_dong.lay("CSAT_BAT") != "bat":
        return "tắt"
    if external_id.startswith("cmt:"):
        return "bình luận — không hỏi"
    from agent.omnichannel.cua_so_gui import xet_tin_nhan_vien
    from agent.omnichannel.outbound_service import OutboundService, PostgresOutboundRepository

    qd = await xet_tin_nhan_vien(cid)
    if not qd.duoc:
        # Ngoài cửa sổ: không hỏi được. Ghi lại để tỉ lệ phản hồi CSAT không
        # bị hiểu nhầm là "khách lười trả lời".
        await db.log_event("csat.khong_hoi", ref_id=cid, ly_do=qd.ly_do[:200])
        return "ngoài cửa sổ nhắn tin"
    await OutboundService(PostgresOutboundRepository()).queue_text(
        conversation_id=cid, role="system", text=CAU_HOI,
        idempotency_key=f"csat:{cid}:{int(time.time())}", the=qd.the)
    await db.execute("INSERT INTO csat (conversation_id, nguoi_xu_ly) VALUES ($1, $2)",
                     cid, nguoi_xu_ly)
    return "đã hỏi"


async def mo_lai_neu_da_giai_quyet(cid: UUID) -> bool:
    """
    Khách nhắn tiếp vào hội thoại đã giải quyết: mở lại, trả cho agent.

    Lượt phục vụ MỚI: hạn SLA tính lại từ bây giờ, `first_responded_at` xoá
    để đo phản hồi của lượt này. Agent nhận lại — giống đường Chatwoot cũ
    (`open` → `auto`): hội thoại xong rồi thì không còn ai đang cầm.
    """
    r = await db.fetchrow(
        """
        UPDATE conversations SET
            state = 'open', status = 'auto', mode = 'auto', outcome = NULL,
            resolved_at = NULL, first_responded_at = NULL,
            first_response_due_at = (
                SELECT now() + p.first_response_minutes * interval '1 minute'
                FROM sla_policies p WHERE p.active AND p.priority = 'normal'
                  AND (p.account_id = conversations.account_id OR p.account_id IS NULL)
                ORDER BY (p.account_id = conversations.account_id) DESC LIMIT 1),
            resolution_due_at = (
                SELECT now() + p.resolution_minutes * interval '1 minute'
                FROM sla_policies p WHERE p.active AND p.priority = 'normal'
                  AND (p.account_id = conversations.account_id OR p.account_id IS NULL)
                ORDER BY (p.account_id = conversations.account_id) DESC LIMIT 1),
            version = version + 1, updated_at = now()
        WHERE id = $1 AND state = 'resolved'
        RETURNING id
        """, cid)
    return r is not None


async def ghi_diem_neu_la_csat(cid: UUID, text: str) -> bool:
    """
    Tin khách là điểm CSAT đang chờ? Ghi điểm, cảm ơn, đóng lại. True = đã xử lý.

    Gọi SAU khi tin đã lưu và TRƯỚC khi agent trả lời.
    """
    diem = doc_diem(text)
    if diem is None:
        return False
    r = await db.fetchrow(
        f"UPDATE csat SET diem = $2, tra_loi_luc = now() WHERE id = ("
        f"  SELECT id FROM csat WHERE conversation_id = $1 AND diem IS NULL "
        f"  AND gui_luc > now() - interval '{GIO_CHO} hours' "
        f"  ORDER BY gui_luc DESC LIMIT 1) RETURNING id", cid, diem)
    if r is None:
        return False
    # Điểm không phải yêu cầu mới: hội thoại trở về trạng thái đã giải quyết.
    await db.execute(
        "UPDATE conversations SET state = 'resolved', status = 'closed', "
        "outcome = 'resolved', resolved_at = now(), updated_at = now() WHERE id = $1", cid)
    await db.log_event("csat.diem", ref_id=cid, diem=diem)
    from agent.omnichannel.outbound_service import OutboundService, PostgresOutboundRepository
    try:
        await OutboundService(PostgresOutboundRepository()).queue_text(
            conversation_id=cid, role="system", text=CAM_ON,
            idempotency_key=f"csat-cam-on:{r['id']}")
    except Exception:  # noqa: BLE001 — điểm đã ghi; lời cảm ơn hỏng thì ghi lại
        await db.log_event("csat.cam_on_that_bai", ref_id=cid)
    return True
