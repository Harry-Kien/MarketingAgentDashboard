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
NGUON = ("nguoi", "agent")

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
    tieu_de = f"Khách cần người trả lời: {ten_khach}".strip(": ") or \
        "Khách cần người trả lời"
    try:
        # `agent.db` chỉ có fetch/fetchrow/execute — không có `fetchval`.
        dong = await db.fetchrow(
            "INSERT INTO cong_viec (tieu_de, mo_ta, nguon, uu_tien, "
            "                       conversation_id, contact_id) "
            "VALUES ($1, $2, 'agent', 'cao', $3, $4) "
            # Đụng `idx_cong_viec_agent_mot_viec` thì bỏ qua — hội thoại này
            # đã có việc đang mở, không cần việc thứ hai.
            "ON CONFLICT DO NOTHING RETURNING id",
            tieu_de, ly_do, conversation_id, contact_id,
        )
        return str(dong["id"]) if dong else None
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("agent.cong_viec").error(
            "KHÔNG tạo được công việc từ chuyển người (hội thoại %s): %s: %s",
            conversation_id, type(exc).__name__, exc,
        )
        return None
