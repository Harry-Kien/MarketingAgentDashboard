"""
Giờ làm việc — để agent thôi hứa một điều không ai giữ được.

VẤN ĐỀ
------
Khi agent chuyển người, khách nhận câu cố định trong cấu hình:

    "Bạn ấy sẽ nhắn lại cho mình sớm nhé."

Lúc 2 giờ sáng, câu đó là một lời nói dối. Không ai đang trực. "Sớm" nghĩa
là sáu tiếng nữa, và khách nằm chờ một tin không tới.

Cả hệ thống được xây quanh nguyên tắc "không phát ngôn không có căn cứ" —
giá phải từ tool, tồn kho phải từ tool, thiếu căn cứ thì chuyển người. Rồi
ở đúng bước cuối, nó hứa một điều mà không có gì bảo đảm. Đây là chỗ hở
duy nhất còn lại trong nguyên tắc đó.

VÌ SAO KHÔNG TẮT AGENT NGOÀI GIỜ
--------------------------------
Cách đơn giản hơn là ngoài giờ thì im lặng. Nhưng phần lớn câu khách hỏi
ban đêm — giá, còn hàng, chính sách đổi trả — agent trả lời được ngay và
trả lời đúng. Tắt đi là mất khách vì một lý do không cần thiết.

Thứ sai không phải việc agent trả lời ban đêm. Thứ sai là câu HỨA CÓ NGƯỜI.
Nên chỉ đổi đúng câu đó.

MÚI GIỜ: CỘNG TAY, KHÔNG DÙNG zoneinfo
--------------------------------------
`zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")` cần cơ sở dữ liệu múi giờ IANA, thứ
Windows KHÔNG có sẵn — thiếu gói `tzdata` là ném `ZoneInfoNotFoundError`.
Một chốt nghiệp vụ không được phép hỏng vì lý do đó.

Việt Nam ở UTC+7 cố định, không có giờ mùa hè, và chưa từng đổi kể từ 1975.
Cộng tay bảy tiếng là đúng, đơn giản, và không phụ thuộc gói nào.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..config import settings

# Việt Nam: UTC+7 cố định, không có giờ mùa hè.
VN = timezone(timedelta(hours=7))


def gio_vn(bay_gio: datetime | None = None) -> datetime:
    """Giờ Việt Nam. Nhận `bay_gio` để kiểm thử không phụ thuộc đồng hồ máy."""
    t = bay_gio or datetime.now(timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(VN)


def dang_trong_gio(bay_gio: datetime | None = None) -> bool:
    """
    Giờ này có người trực không.

    Khoảng đóng-mở: `[bat_dau, ket_thuc)`. Đặt `ket_thuc = 21` nghĩa là
    20:59 còn trong giờ, 21:00 thì hết — người trực cuối ca cần biết chính
    xác lúc nào mình được về.
    """
    if not settings.gio_lam_viec_bat:
        return True
    g = gio_vn(bay_gio).hour
    dau = int(settings.gio_lam_viec_bat_dau)
    cuoi = int(settings.gio_lam_viec_ket_thuc)
    if dau >= cuoi:
        # Cấu hình vô lý (ví dụ 21 → 8). Coi như trực suốt ngày thay vì
        # coi như đóng cửa suốt ngày: hỏng theo hướng phục vụ khách.
        return True
    return dau <= g < cuoi


def tin_chuyen_nguoi(bay_gio: datetime | None = None) -> str:
    """
    Câu báo cho khách khi chuyển người — đổi theo giờ.

    Trong giờ  giữ nguyên câu cũ, vì lúc đó "sẽ nhắn lại sớm" là thật.
    Ngoài giờ  nói rõ MẤY GIỜ có người. Khách biết mình chờ tới bao giờ thì
               chờ được; khách không biết thì bỏ đi.

    Vẫn là chuỗi CỐ ĐỊNH trong cấu hình, không phải lời model sinh — lúc
    agent tự nhận không đủ thẩm quyền chính là lúc không nên để nó chọn chữ.
    """
    if dang_trong_gio(bay_gio):
        return settings.tin_chuyen_nguoi
    return settings.tin_chuyen_nguoi_ngoai_gio.format(
        gio_mo=f"{int(settings.gio_lam_viec_bat_dau)} giờ"
    )
