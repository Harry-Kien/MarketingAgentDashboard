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

NGUỒN GIỜ: LỊCH CHUNG
---------------------
Giờ mở/đóng, ngày nghỉ và ngày lễ đọc từ `lich_lam_viec.py` — cùng một
lịch với hạn SLA và điều kiện "ngoài giờ" của quy tắc tự động. Thứ tự ưu
tiên (dashboard trước, `.env` sau) ghi ở đầu tệp ấy.

MÚI GIỜ: CỘNG TAY, KHÔNG DÙNG zoneinfo
--------------------------------------
`zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")` cần cơ sở dữ liệu múi giờ IANA, thứ
Windows KHÔNG có sẵn — thiếu gói `tzdata` là ném `ZoneInfoNotFoundError`.
Một chốt nghiệp vụ không được phép hỏng vì lý do đó.

Việt Nam ở UTC+7 cố định, không có giờ mùa hè, và chưa từng đổi kể từ 1975.
Cộng tay bảy tiếng là đúng, đơn giản, và không phụ thuộc gói nào.
"""
from __future__ import annotations

from datetime import datetime

from ..config import settings
from . import lich_lam_viec
from .lich_lam_viec import VN, gio_vn

__all__ = ["VN", "dang_trong_gio", "gio_vn", "tin_chuyen_nguoi"]


def dang_trong_gio(bay_gio: datetime | None = None) -> bool:
    """
    Giờ này có người trực không — theo LỊCH CHUNG (`lich_lam_viec.py`: lịch
    lưu trên dashboard, không có thì `.env`).

    Khoảng đóng-mở: `[mo, dong)`. Đặt đóng 21:00 nghĩa là 20:59 còn trong
    giờ, 21:00 thì hết — người trực cuối ca cần biết chính xác lúc nào mình
    được về. Ngày nghỉ trong tuần và ngày lễ là ngoài giờ cả ngày. Cấu hình
    vô lý (không ngày nào mở) coi như trực suốt: hỏng theo hướng phục vụ
    khách, không theo hướng đóng cửa suốt ngày.
    """
    return lich_lam_viec.hien_hanh().dang_mo(bay_gio)


def _gio_mo(t: datetime) -> str:
    return f"{t.hour} giờ" if not t.minute else f"{t.hour} giờ {t.minute:02d}"


def tin_chuyen_nguoi(bay_gio: datetime | None = None) -> str:
    """
    Câu báo cho khách khi chuyển người — đổi theo giờ.

    Trong giờ  giữ nguyên câu cũ, vì lúc đó "sẽ nhắn lại sớm" là thật.
    Ngoài giờ  nói rõ MẤY GIỜ có người — giờ mở của LẦN MỞ CỬA KẾ TIẾP theo
               lịch chung, không phải một giờ cố định: thứ Hai mở 9 giờ thì
               tối Chủ nhật phải hứa 9 giờ. Khách biết mình chờ tới bao giờ
               thì chờ được; khách không biết thì bỏ đi.

    Vẫn là chuỗi CỐ ĐỊNH trong cấu hình, không phải lời model sinh — lúc
    agent tự nhận không đủ thẩm quyền chính là lúc không nên để nó chọn chữ.
    """
    lich = lich_lam_viec.hien_hanh()
    if lich.dang_mo(bay_gio):
        return settings.tin_chuyen_nguoi
    mo = lich.lan_mo_ke_tiep(bay_gio)
    gio = _gio_mo(mo) if mo is not None else f"{int(settings.gio_lam_viec_bat_dau)} giờ"
    return settings.tin_chuyen_nguoi_ngoai_gio.format(gio_mo=gio)
