"""
Báo khách đang nói chuyện với AI, và giữ lời hứa "nhắn gặp nhân viên".

CĂN CỨ
------
Nghị định 356/2025/NĐ-CP Điều 10 khoản 3: thông báo cho chủ thể việc xử lý
tự động, và cho họ lựa chọn không bị xử lý tự động. Điều 6 khoản 4: báo cho
chủ thể biết dữ liệu là dữ liệu nhạy cảm. Ảnh vùng da, mô tả mụn, kích ứng
là "tình trạng sức khoẻ" — NĐ 356 Điều 4 khoản 1 điểm d.

HAI NỬA, KHÔNG TÁCH ĐƯỢC
------------------------
Câu thông báo hứa: nhắn "gặp nhân viên" là gặp người. Lời hứa ấy phải được
giữ bằng MÃ — `khach_doi_gap_nguoi()` chạy TRƯỚC agent và chuyển người ngay.
Để model tự hiểu là để nó có lúc trả lời "dạ em hỗ trợ mình luôn ạ" cho
một người vừa nói rõ không muốn nói chuyện với máy.

CHỈ GỬI KHI AGENT THẬT SỰ TRẢ LỜI
---------------------------------
Hàm này được gọi SAU chốt `agent_bat` trong xu_ly_tin_vao. Agent tắt, nhân
viên đang tiếp khách, mà vẫn gửi "em là trợ lý AI" là nói sai sự thật.

MỘT LẦN MỖI HỘI THOẠI
---------------------
Khoá chống trùng của outbox (`thong_bao_ai:<hội thoại>`), kiểm trên bảng
`messages`. Hội thoại bị dọn theo thời hạn lưu trữ thì lần sau khách nhắn
là hội thoại mới — và được báo lại, đúng như phải thế.
"""
from __future__ import annotations

import logging
import unicodedata
import uuid

logger = logging.getLogger(__name__)

# So khớp trên chữ đã bỏ dấu, chữ thường. Cụm NHIỀU từ: "người" trần hay
# "nhân viên" trần quá phổ biến ("nhân viên giao hàng chưa tới").
CUM_GAP_NGUOI = (
    "gap nhan vien", "gap nguoi", "noi chuyen voi nhan vien", "noi chuyen voi nguoi",
    "nguoi that", "nhan vien that", "khong phai bot", "khong noi chuyen voi bot",
    "khong muon noi chuyen voi ai", "khong muon chat voi bot", "cho gap admin",
)


def _chuan(s: str) -> str:
    """Bỏ dấu, chữ thường, mọi ký tự không phải chữ/số thành khoảng trắng."""
    s = unicodedata.normalize("NFD", (s or "").lower()).replace("đ", "d")
    s = "".join(c if c.isalnum() else " " for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def khach_doi_gap_nguoi(van_ban: str) -> bool:
    # So theo RANH GIỚI TỪ: "gặp người" khớp, "gặp người yêu" cũng khớp (cụm
    # đứng đầu) — chấp nhận được, chuyển người thừa còn hơn giữ khách lại
    # với máy khi họ đã đòi gặp người.
    t = f" {_chuan(van_ban)} "
    return any(f" {c} " in t for c in CUM_GAP_NGUOI)


def khoa(cid: uuid.UUID) -> str:
    return f"thong_bao_ai:{cid}"


def cau_thong_bao() -> str:
    from agent.config import settings
    from agent.core import tools

    ten = (tools.ten_thuong_hieu() or "").strip() or "shop"
    return settings.tin_thong_bao_ai.format(ten=ten)


async def gui_neu_chua(msg, cid: uuid.UUID) -> bool:
    """
    Gửi câu thông báo nếu hội thoại này chưa nhận. Trả True nếu vừa xếp hàng.

    Hỏng KHÔNG chặn câu trả lời của agent — nhưng không im lặng: ghi
    `thong_bao_ai.loi` để `san_sang`/nhật ký thấy được.
    """
    from agent import cau_hinh_dong, db

    try:
        if (cau_hinh_dong.lay("THONG_BAO_AI") or "bat") != "bat":
            return False
        if await db.fetchrow("SELECT 1 FROM messages WHERE conversation_id = $1 "
                             "AND client_idempotency_key = $2 LIMIT 1", cid, khoa(cid)):
            return False
        from agent.channels import registry as channels
        from agent.omnichannel.outbound_service import OutboundService, PostgresOutboundRepository

        adapter = await channels.get_for_account(msg.account_id)
        if not await adapter.can_send_now(msg.conversation_ref):
            return False
        await OutboundService(PostgresOutboundRepository()).queue_text(
            conversation_id=cid, role="system", text=cau_thong_bao(), idempotency_key=khoa(cid),
            metadata={"thong_bao_ai": True},
        )
        return True
    except Exception as exc:  # noqa: BLE001 — không chặn lượt trả lời của khách
        logger.exception("thong_bao_ai: không gửi được cho %s", cid)
        try:
            await db.log_event("thong_bao_ai.loi", ref_id=cid, loi=f"{type(exc).__name__}: {exc}"[:200])
        except Exception:  # noqa: BLE001
            pass
        return False
