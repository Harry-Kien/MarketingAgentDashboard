"""Nguồn ERP giả + helper chạy coroutine. Không gọi mạng, không ngủ.

VÌ SAO CÓ `chay()` THAY VÌ `async def test_...`
-----------------------------------------------
Repo này KHÔNG cài `pytest-asyncio` (xem requirements.txt). Viết
`async def test_...` là hỏng ngay lúc chạy:

    Failed: async def functions are not natively supported.

117 file test hiện có đều dùng `asyncio.run`. Giữ nguyên quy ước đó.

Độ trễ mô phỏng bằng ĐỒNG HỒ TIÊM VÀO chứ không bằng `asyncio.sleep`, vì
toàn bộ bộ test phải chạy dưới 4 giây.
"""
from __future__ import annotations

import asyncio

from agent.erp.hop_dong import Gia, LoiERP, SanPhamERP, TonKho


def chay(coro):
    """Chạy một coroutine trong hàm test đồng bộ."""
    return asyncio.run(coro)


class NguonGia:
    ten = "gia"

    def __init__(
        self,
        san_pham: list[SanPhamERP] | None = None,
        gia: dict[str, Gia] | None = None,
        ton: dict[str, TonKho] | None = None,
        hong: bool = False,
    ):
        self.san_pham = san_pham or []
        self.bang_gia = gia or {}
        self.bang_ton = ton or {}
        self.hong = hong
        self.so_lan_goi: dict[str, int] = {}

    def _dem(self, ten_ham: str) -> None:
        self.so_lan_goi[ten_ham] = self.so_lan_goi.get(ten_ham, 0) + 1
        if self.hong:
            raise LoiERP("ERP giả đang được đặt là hỏng")

    async def danh_sach_san_pham(self, chi_ban_duoc: bool = True):
        self._dem("danh_sach_san_pham")
        if chi_ban_duoc:
            return [sp for sp in self.san_pham if sp.ban_duoc_phep]
        return list(self.san_pham)

    async def gia(self, ma: str):
        self._dem("gia")
        return self.bang_gia.get(ma)

    async def ton_kho(self, ma: str):
        self._dem("ton_kho")
        return self.bang_ton.get(ma)

    async def suc_khoe(self) -> bool:
        try:
            self._dem("suc_khoe")
        except LoiERP:
            return False
        return True
