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

from agent.omnichannel.account_repository import PostgresAccountRepository
from agent.omnichannel.credential_loader import VaultCredentialLoader
from agent.security.credential_vault import CredentialVault, parse_master_keys

from .base import ChannelAdapter
from .chatwoot import ChatwootAdapter
from .factory import AccountAdapterFactory
from .messenger import MessengerAdapter
from .zalo_oa import ZaloOAAdapter
from .zalocrm import ZaloCRMAdapter

_ADAPTERS: dict[str, ChannelAdapter] = {}
_ACCOUNT_ADAPTERS: dict[str, ChannelAdapter] = {}


def _dung() -> dict[str, ChannelAdapter]:
    if not _ADAPTERS:
        _ADAPTERS["zalocrm"] = ZaloCRMAdapter()
        _ADAPTERS["chatwoot"] = ChatwootAdapter()
        # Zalo OA dựng sẵn nhưng chưa có khoá: `dang_bat()` không liệt kê
        # nó, nên dashboard không hiện và không có gì gọi tới. Vẫn đăng ký ở
        # đây để `/webhook/zalo_oa` tồn tại sẵn — lúc nối OA chỉ cần điền
        # khoá vào .env, không phải sửa mã và triển khai lại.
        _ADAPTERS["zalo_oa"] = ZaloOAAdapter()
        # Messenger đi THẲNG Meta Graph API. Cùng tồn tại với đường qua
        # Chatwoot có chủ ý — hai cách tới cùng một nền tảng, chọn theo
        # việc. Cũng tắt cho tới khi có Page token.
        _ADAPTERS["messenger"] = MessengerAdapter()
    return _ADAPTERS


def get(name: str) -> ChannelAdapter:
    """
    Adapter cho một kênh. Tên lạ thì trả ZaloCRM.

    Trả về mặc định thay vì ném lỗi là cố ý: dữ liệu cũ trong CSDL có thể
    mang tên kênh không còn tồn tại, và một hội thoại lịch sử không được
    phép làm sập màn hình.
    """
    return _dung().get(name, _dung()["zalocrm"])


async def get_for_account(account_id) -> ChannelAdapter:
    """Resolve nghiêm ngặt theo account; ID sai không rơi về nick mặc định."""
    key = str(account_id)
    if key not in _ACCOUNT_ADAPTERS:
        repository = PostgresAccountRepository()
        credential_loader = None
        try:
            from agent.config import settings

            credential_loader = VaultCredentialLoader(
                repository,
                CredentialVault(
                    parse_master_keys(settings.credential_master_keys),
                    active_version=settings.credential_active_key_version,
                ),
            )
        except ValueError:
            # Legacy account không cần vault; native account sẽ fail closed
            # trong factory thay vì rơi về token dùng chung.
            credential_loader = None
        factory = AccountAdapterFactory(repository, credential_loader)
        _ACCOUNT_ADAPTERS[key] = await factory.create(account_id)
    return _ACCOUNT_ADAPTERS[key]


def tat_ca() -> dict[str, ChannelAdapter]:
    return dict(_dung())


def dang_bat() -> list[str]:
    """Kênh đã cấu hình đủ để dùng — dashboard hiển thị danh sách này."""
    from ..config import settings
    bat = []
    if settings.zalocrm_api_key:
        bat.append("zalocrm")
    for ten in ("chatwoot", "zalo_oa", "messenger"):
        ad = _dung()[ten]
        if getattr(ad, "cau_hinh_du", lambda: False)():
            bat.append(ten)
    return bat


async def keo_tin_moi() -> list:
    """Gom tin mới từ mọi kênh đi bằng polling."""
    from ..config import settings
    out = []
    if settings.zalocrm_api_key:
        out.extend(await _dung()["zalocrm"].fetch_new())
    return out


async def dong_tat_ca() -> None:
    for ad in [*_dung().values(), *_ACCOUNT_ADAPTERS.values()]:
        await ad.aclose()
    _ADAPTERS.clear()
    _ACCOUNT_ADAPTERS.clear()
