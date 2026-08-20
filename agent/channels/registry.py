"""
Bộ đăng ký kênh — một chỗ duy nhất biết hệ thống đang nối vào những đâu.

Trước khi có file này, `main.py` giữ đúng một adapter ZaloCRM. Thêm kênh
thứ hai mà không có lớp này thì mọi chỗ gửi tin phải viết `if channel ==
"zalocrm" ... elif ...`, và mỗi kênh mới lại thêm một nhánh nữa ở bốn năm
chỗ khác nhau.

Giờ chỉ cần: `await registry.get(conv["channel"]).send_text(...)`.

Hai kênh đang chạy theo hai cơ chế ngược nhau:
    zalocrm  — KÉO (polling), vì chốt SSRF của nó chặn webhook về localhost
    chatwoot — ĐẨY (webhook), vì Chatwoot không có chốt đó
`poll_loop` chỉ hỏi những adapter khai `dung_polling = True`.
"""
from __future__ import annotations

from .base import ChannelAdapter
from .chatwoot import ChatwootAdapter
from .zalocrm import ZaloCRMAdapter

_ADAPTERS: dict[str, ChannelAdapter] = {}


def _dung() -> dict[str, ChannelAdapter]:
    if not _ADAPTERS:
        _ADAPTERS["zalocrm"] = ZaloCRMAdapter()
        _ADAPTERS["chatwoot"] = ChatwootAdapter()
    return _ADAPTERS


def get(name: str) -> ChannelAdapter:
    """
    Adapter cho một kênh. Tên lạ thì trả ZaloCRM.

    Trả về mặc định thay vì ném lỗi là cố ý: dữ liệu cũ trong CSDL có thể
    mang tên kênh không còn tồn tại, và một hội thoại lịch sử không được
    phép làm sập màn hình.
    """
    return _dung().get(name, _dung()["zalocrm"])


def tat_ca() -> dict[str, ChannelAdapter]:
    return dict(_dung())


def dang_bat() -> list[str]:
    """Kênh đã cấu hình đủ để dùng — dashboard hiển thị danh sách này."""
    from ..config import settings
    bat = []
    if settings.zalocrm_api_key:
        bat.append("zalocrm")
    cw = _dung()["chatwoot"]
    if getattr(cw, "cau_hinh_du", lambda: False)():
        bat.append("chatwoot")
    return bat


async def keo_tin_moi() -> list:
    """Gom tin mới từ mọi kênh đi bằng polling."""
    from ..config import settings
    out = []
    if settings.zalocrm_api_key:
        out.extend(await _dung()["zalocrm"].fetch_new())
    return out


async def dong_tat_ca() -> None:
    for ad in _dung().values():
        await ad.aclose()
    _ADAPTERS.clear()
