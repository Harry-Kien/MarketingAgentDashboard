"""
Công việc: giao việc cho nhân viên và theo dõi tới khi xong.

VÌ SAO KHỐI NÀY TỒN TẠI
------------------------
Trước bản này, agent chuyển người xong thì để lại một dòng nhật ký và một
hội thoại đổi màu. Không ai được GIAO gì cả.

Nếu người trực đang bận lúc ấy, việc không nằm ở đâu. Nó chỉ được nhớ tới
nếu tình cờ có người mở đúng hội thoại — và "tình cờ" không phải một cơ chế.
Đây đúng loại hỏng mà `CLAUDE.md` liệt kê: không nổ, không ghi nhật ký báo
động, và triệu chứng duy nhất là một khách hàng thôi nhắn lại.

VÌ SAO TASK TỰ SINH CHỈ MỘT LẦN MỖI HỘI THOẠI
----------------------------------------------
Không chặn thì mỗi tin khách nhắn thêm vào một hội thoại đã chuyển người
lại đẻ một việc mới. Cuối ngày màn Công việc có bốn mươi dòng cho cùng một
chuyện, không ai đọc nữa, và việc thật nằm lẫn trong đó.

Ràng buộc nằm ở CSDL (`idx_cong_viec_agent_mot_viec`) chứ không chỉ ở đây:
hai tin khách về cùng lúc thì hai tiến trình cùng kiểm "đã có việc chưa",
cùng thấy chưa, và cùng chèn.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from agent import db

TRANG_THAI = ("moi", "dang_lam", "xong", "huy")
UU_TIEN = ("thap", "thuong", "cao", "gap")
NGUON = ("nguoi", "agent", "tu_dong", "van_chuyen")

NHAN_TRANG_THAI = {
    "moi": "Mới",
    "dang_lam": "Đang làm",
    "xong": "Xong",
    "huy": "Đã huỷ",
}
NHAN_UU_TIEN = {
    "thap": "Thấp", "thuong": "Thường", "cao": "Cao", "gap": "Gấp",
}

CHUA_XONG = ("moi", "dang_lam")


class CongViecHong(ValueError):
    """Dữ liệu công việc không hợp lệ."""


def kiem_trang_thai(gia_tri: str) -> str:
    if gia_tri not in TRANG_THAI:
        raise CongViecHong(
            f"Trạng thái không hợp lệ: {gia_tri!r}. "
            f"Chỉ nhận: {', '.join(TRANG_THAI)}")
    return gia_tri


def kiem_uu_tien(gia_tri: str) -> str:
    if gia_tri not in UU_TIEN:
        raise CongViecHong(
            f"Mức ưu tiên không hợp lệ: {gia_tri!r}. "
            f"Chỉ nhận: {', '.join(UU_TIEN)}")
    return gia_tri


def qua_han(viec: dict, bay_gio: datetime | None = None) -> bool:
    """
    Việc này đã quá hạn chưa.

    Việc đã `xong` hoặc `huy` thì KHÔNG bao giờ quá hạn, dù hạn đã qua. Đếm
    chúng vào là con số quá hạn chỉ tăng và không bao giờ giảm — và một con
    số chỉ tăng là con số người ta thôi nhìn.
    """
    han = viec.get("han")
    if not han or viec.get("trang_thai") not in CHUA_XONG:
        return False
    if isinstance(han, str):
        han = datetime.fromisoformat(han)
    moc = bay_gio or datetime.now(timezone.utc)
    if han.tzinfo is None:
        han = han.replace(tzinfo=timezone.utc)
    return han < moc


def dieu_kien_pham_vi(*, nguoi: dict, so_tham_so: int,
                      bi_danh: str = "cong_viec") -> tuple[str, list[Any]]:
    """
    Mệnh đề WHERE lọc công việc theo phạm vi của người này.

    Ai có `cong_viec.xem_tat_ca` thì thấy hết. Còn lại chỉ thấy việc mình
    NHẬN, việc mình GIAO, và việc CHƯA GIAO cho ai.

    Vế "chưa giao cho ai" là cố ý, cùng lý lẽ với khách vô chủ: việc chưa
    giao mà không ai thấy thì nó không tồn tại — và việc do agent đẩy sang
    luôn ra đời ở trạng thái chưa giao.
    """
    if "cong_viec.xem_tat_ca" in (nguoi.get("quyen") or ()):
        return "TRUE", []
    n = so_tham_so + 1
    return (
        f"({bi_danh}.nguoi_nhan = ${n} OR {bi_danh}.nguoi_giao = ${n} "
        f"OR {bi_danh}.nguoi_nhan IS NULL)",
        [str(nguoi["id"])],
    )


async def tao_tu_chuyen_nguoi(
    conversation_id: UUID | str, *, ly_do: str, contact_id=None,
    ten_khach: str = "",
) -> str | None:
    """
    Agent vừa chuyển người -> tạo một việc để có ai đó chịu trách nhiệm.

    Trả id việc vừa tạo, hoặc None nếu hội thoại này đã có một việc tự động
    đang mở.

    KHÔNG ném khi hỏng. Hàm này chạy trên đường xử lý tin khách, và một
    ngoại lệ ở đây làm chết cả lượt trả lời — tức là để cứu một việc bị
    thiếu, ta đánh mất luôn câu trả lời cho khách.

    Nhưng cũng KHÔNG im lặng: hỏng thì ghi nhật ký ở mức lỗi. Nuốt không
    dấu vết là cách khối này trở nên vô dụng mà không ai biết.
    """
    try:
        # Tên và khách lấy từ CHÍNH hội thoại khi người gọi không có trong
        # tay — `handle_inbound` chỉ cầm id. Trước 23.10.2026 nó truyền tên
        # từ một dict không có khoá ấy, nên mọi việc tự sinh đều vô danh và
        # không gắn khách. Gộp vào một câu SQL: không thêm lượt khứ hồi nào
        # trên đường xử lý tin khách.
        dong = await db.fetchrow(
            "INSERT INTO cong_viec (tieu_de, mo_ta, nguon, uu_tien, "
            "                       conversation_id, contact_id) "
            "SELECT 'Khách cần người trả lời' || coalesce(': ' || coalesce("
            "           nullif($1, ''), nullif(c.customer_name, '')), ''), "
            "       $2, 'agent', 'cao', $3::uuid, coalesce($4::uuid, c.contact_id) "
            "FROM (SELECT 1) _ LEFT JOIN conversations c ON c.id = $3::uuid "
            # Đụng `idx_cong_viec_agent_mot_viec` thì bỏ qua — hội thoại này
            # đã có việc đang mở, không cần việc thứ hai.
            "ON CONFLICT DO NOTHING RETURNING id",
            (ten_khach or "").strip(), ly_do, str(conversation_id),
            str(contact_id) if contact_id else None,
        )
        if dong is None:
            return None
        # Việc MỚI thì báo nhân viên ra ngoài dashboard — ở MỌI kênh. Chỉ
        # khi việc mới: khách nhắn thêm mười tin vào hội thoại đã chuyển
        # người không được thành mười tin báo (chốt một-việc-mỗi-hội-thoại
        # ở trên làm luôn việc chống trùng cho đường báo này).
        await _bao_viec_moi_cho_nhan_vien(conversation_id)
        return str(dong["id"])
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("agent.cong_viec").error(
            "KHÔNG tạo được công việc từ chuyển người (hội thoại %s): %s: %s",
            conversation_id, type(exc).__name__, exc,
        )
        return None


TEN_KENH = {
    "zalo_personal": "Zalo cá nhân", "zalo_oa": "Zalo OA",
    "facebook": "Facebook", "instagram": "Instagram",
    "whatsapp": "WhatsApp", "webchat": "Chat web",
}


async def _bao_viec_moi_cho_nhan_vien(conversation_id: UUID | str) -> None:
    """
    Gửi một tin ngắn tới nhóm nhân viên (xem `canh_gac.bao_nhan_vien`).

    Chỉ nói KÊNH, không nói lý do hay lời khách: lý do chuyển người có thể
    là "mang thai", "bệnh da" — dữ liệu sức khoẻ, thuộc loại nhạy cảm theo
    Luật 91/2025, không được đi sang Telegram chỉ để báo "có việc".
    """
    from agent import canh_gac

    dong = await db.fetchrow(
        "SELECT ca.channel FROM conversations c "
        "LEFT JOIN channel_accounts ca ON ca.id = c.account_id WHERE c.id = $1::uuid",
        str(conversation_id))
    kenh = (dong or {}).get("channel") or ""
    canh_gac.bao_nhan_vien_nen(
        "Khách cần người trả lời",
        f"Kênh {TEN_KENH.get(kenh, kenh or 'không rõ')}: agent đã chuyển hội thoại "
        "cho người. Mở dashboard → Ca trực để nhận.")


async def tao_tu_van_chuyen(
    ma_don: str, *, tieu_de: str, mo_ta: str, khoa: str,
    conversation_id=None, uu_tien: str = "cao",
) -> str | None:
    """
    Hãng vận chuyển báo một chuyện cần NGƯỜI làm: giao thất bại, mã trạng
    thái lạ. Trả id việc vừa tạo, hoặc None khi đã có việc cùng `khoa`.

    Trước bản này hai chuyện ấy chỉ là một dòng nhật ký: kiện giao hỏng
    không ai gọi khách hẹn lại, hãng hoàn hàng về sau ba lần thử, shop chịu
    phí hoàn — mà không có gì báo lỗi ở đâu (rà soát 29.10.2026).

    `khoa` gắn theo mã vận đơn + trạng thái: hãng phát lại webhook không đẻ
    việc thứ hai (chỉ mục duy nhất ở CSDL, migration 0038). Không ném khi
    hỏng — webhook vẫn phải trả lời hãng — nhưng ghi nhật ký mức lỗi.
    """
    try:
        dong = await db.fetchrow(
            "INSERT INTO cong_viec (tieu_de, mo_ta, nguon, uu_tien, conversation_id, "
            "                       contact_id, khoa_chong_trung) "
            "SELECT $1, $2, 'van_chuyen', $3, $4::uuid, c.contact_id, $5 "
            "FROM (SELECT 1) _ LEFT JOIN conversations c ON c.id = $4::uuid "
            "ON CONFLICT DO NOTHING RETURNING id",
            tieu_de[:200], mo_ta, kiem_uu_tien(uu_tien),
            str(conversation_id) if conversation_id else None, khoa[:300],
        )
        if dong is None:
            return None
        from agent import canh_gac

        # Mã đơn là mã nội bộ của cửa hàng, không phải dữ liệu của khách.
        canh_gac.bao_nhan_vien_nen(tieu_de, f"Đơn {ma_don}. Mở dashboard → Công việc.")
        return str(dong["id"])
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("agent.cong_viec").error(
            "KHÔNG tạo được công việc vận chuyển (đơn %s): %s: %s",
            ma_don, type(exc).__name__, exc,
        )
        return None
