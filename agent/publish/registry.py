"""
Chọn adapter cho từng kênh — một chỗ duy nhất quyết định đường đi.

Thứ tự ưu tiên cho mỗi kênh, dừng ở adapter đầu tiên sẵn sàng:
    n8n  ->  API chính thức  ->  manual

Nghĩa là hệ thống KHÔNG BAO GIỜ chết vì thiếu quyền: xấu nhất thì bài rơi
vào hàng đợi thủ công và người bấm đăng. Nhưng khi n8n hoặc App Review có
rồi thì tự động lên bậc, không phải sửa mã.
"""
from __future__ import annotations

from .base import PublishAdapter
from .manual import ManualPublisher
from .meta import MetaPublisher
from .n8n import N8nPublisher
from .tiktok import TikTokPublisher

KENH_HO_TRO = ("facebook", "instagram", "tiktok", "youtube")

_cache: dict[str, PublishAdapter] = {}


def _get(cls) -> PublishAdapter:
    key = cls.__name__
    if key not in _cache:
        _cache[key] = cls()
    return _cache[key]


def _uu_tien(kenh: str) -> list[PublishAdapter]:
    thu_tu: list[PublishAdapter] = [_get(N8nPublisher)]
    if kenh in ("facebook", "instagram"):
        thu_tu.append(_get(MetaPublisher))
    elif kenh == "tiktok":
        thu_tu.append(_get(TikTokPublisher))
    thu_tu.append(_get(ManualPublisher))
    return thu_tu


async def chon(kenh: str) -> PublishAdapter:
    for ad in _uu_tien(kenh):
        ok, _ = await ad.san_sang()
        if ok:
            return ad
    return _get(ManualPublisher)


async def trang_thai_kenh() -> list[dict]:
    """Dashboard hiển thị: kênh nào đang đi đường nào, vì sao."""
    out = []
    for kenh in KENH_HO_TRO:
        chi_tiet = []
        chon_duoc = None
        for ad in _uu_tien(kenh):
            ok, ly_do = await ad.san_sang()
            chi_tiet.append({"adapter": ad.name, "san_sang": ok, "ly_do": ly_do})
            if ok and chon_duoc is None:
                chon_duoc = ad.name
        out.append({"kenh": kenh, "dang_dung": chon_duoc, "duong_di": chi_tiet})
    return out


async def dong_tat_ca() -> None:
    for ad in list(_cache.values()):
        await ad.aclose()
    _cache.clear()
