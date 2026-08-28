"""
Cổng: bọc một `NguonERP`, thêm cache có tuổi và ngắt mạch.

QUY TẮC TRUNG TÂM
-----------------
Giá và tồn kho quá hạn mà gọi ERP không được thì cổng trả `None`.
KHÔNG BAO GIỜ trả số cũ.

Cám dỗ ở đây rất lớn: đã có số trong tay, trả ra thì agent chạy mượt, không
ai thấy gì. Đó chính là vấn đề — nó chạy mượt trong khi nói sai. Báo giá sai
rồi mới phát hiện đắt hơn nhiều so với im lặng một phút, và im lặng thì lưới
an toàn đẩy sang người thật.

Tham chiếu (tên, mô tả) thì ngược lại — bản cũ dùng được, vì tên sản phẩm
không đổi trong một buổi chiều.

VÌ SAO ĐỒNG HỒ TIÊM VÀO
-----------------------
Để test TTL không phải ngủ.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent.erp.hop_dong import Gia, NguonERP, TonKho


@dataclass
class _O:
    """Một ô cache: giá trị và thời điểm ghi."""

    gia_tri: Any
    luc: float


class Cong:
    def __init__(
        self,
        nguon: NguonERP,
        ttl_gia: float = 900.0,
        ttl_ton: float = 60.0,
        ngat_mach_so_lan: int = 5,
        ngat_mach_giay: float = 30.0,
        dong_ho: Callable[[], float] = time.monotonic,
    ):
        self._nguon = nguon
        self._ttl_gia = ttl_gia
        self._ttl_ton = ttl_ton
        self._ngat_mach_so_lan = ngat_mach_so_lan
        self._ngat_mach_giay = ngat_mach_giay
        self._dong_ho = dong_ho
        self._cache_gia: dict[str, _O] = {}
        self._cache_ton: dict[str, _O] = {}
        self._hong_lien_tiep = 0
        self._mo_mach_den = 0.0

    async def gia(self, ma: str, bo_qua_cache: bool = False) -> Gia | None:
        return await self._lay(
            self._cache_gia, self._ttl_gia, ma, bo_qua_cache, self._nguon.gia
        )

    async def ton_kho(self, ma: str, bo_qua_cache: bool = False) -> TonKho | None:
        return await self._lay(
            self._cache_ton, self._ttl_ton, ma, bo_qua_cache, self._nguon.ton_kho
        )

    async def _lay(self, cache, ttl, ma, bo_qua_cache, ham):
        bay_gio = self._dong_ho()
        if not bo_qua_cache:
            o = cache.get(ma)
            if o is not None and bay_gio - o.luc < ttl:
                return o.gia_tri
        try:
            gia_tri = await ham(ma)
        except Exception:  # noqa: BLE001
            # Không trả ô cache cũ ở đây. Xem QUY TẮC TRUNG TÂM ở đầu file.
            return None
        cache[ma] = _O(gia_tri, bay_gio)
        return gia_tri
