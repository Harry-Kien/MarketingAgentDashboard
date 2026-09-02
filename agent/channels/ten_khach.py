"""
Lấy tên thật của khách từ Meta, thay cho chữ "Khách" chung chung.

VÌ SAO CẦN
----------
Webhook Meta CHỈ gửi mã người dùng (PSID), không gửi tên. Muốn có tên phải
gọi Graph API riêng.

Người trực nhìn danh sách hội thoại thấy bốn dòng "Khách" thì không phân
biệt được ai với ai — phải mở từng cái ra đọc. Và gọi đúng tên khách là
khác biệt giữa một quầy dịch vụ và một cái máy.

VÌ SAO KHÔNG GỌI MỖI TIN
------------------------
Mỗi lượt gọi Graph là thêm một chặng mạng nằm trên đường trả lời khách, và
đốt hạn mức API. Tên người thì gần như không đổi — lấy một lần là đủ.
"""
from __future__ import annotations

from collections.abc import Mapping

# Những giá trị các adapter đặt khi chưa biết tên. Khớp bằng danh sách chứ
# không đoán theo tiền tố "Khách": khách tên thật là "Khách" (hiếm nhưng có)
# thì cũng chỉ tốn một lượt gọi thừa, không sai gì.
TEN_MAC_DINH = frozenset({
    "", "Khách", "Khách Zalo", "Khách Instagram", "Khách WhatsApp",
    "Khách Facebook",
})


def can_lay_ten(ten_hien_tai: str) -> bool:
    """Có cần gọi Graph để lấy tên không."""
    return str(ten_hien_tai or "").strip() in TEN_MAC_DINH


def ghep_ten(ho_so: Mapping[str, object]) -> str:
    """
    Lấy tên hiển thị của khách từ hồ sơ Graph trả về.

    ƯU TIÊN `name` — ĐÚNG TÊN FACEBOOK
    ----------------------------------
    `name` là tên khách tự đặt và Facebook đang hiển thị, đã xếp đúng thứ tự
    theo ngôn ngữ của họ. Dùng lại nó thì tên trong hội thoại khớp y hệt tên
    khách nhìn thấy trên Messenger — người trực đối chiếu được ngay.

    Tự ghép từ `first_name`/`last_name` là ta ĐOÁN quy ước đặt tên: người
    Việt đọc họ trước, người Mỹ đọc tên trước, và không ít người để cả biệt
    danh hoặc emoji trong `first_name`. Facebook đã giải quyết chuyện đó rồi.

    VẪN GIỮ ĐƯỜNG GHÉP LÀM DỰ PHÒNG
    -------------------------------
    Vài hồ sơ không trả `name` (tuỳ quyền đã cấp và loại tài khoản). Rơi về
    ghép tay theo thứ tự Việt Nam — họ trước — còn hơn để trống thành "Khách".

    TRẢ RỖNG KHI KHÔNG CÓ GÌ, KHÔNG TRẢ "Khách"
    -------------------------------------------
    Chỗ gọi sẽ giữ nguyên tên đang có. Trả một giá trị mặc định ở đây là ghi
    đè mất tên thật đã lấy được lần trước — Graph hỏng một lần là khách mất
    tên vĩnh viễn.
    """
    ten_fb = str(ho_so.get("name") or "").strip()
    if ten_fb:
        return ten_fb

    ten = str(ho_so.get("first_name") or "").strip()
    ho = str(ho_so.get("last_name") or "").strip()
    return " ".join(phan for phan in (ho, ten) if phan)
