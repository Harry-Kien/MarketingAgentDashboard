"""
Hợp đồng dữ liệu giữa hệ thống và kho/ERP.

VÌ SAO CÓ LỚP NÀY
-----------------
Odoo nói XML-RPC và gọi sản phẩm là `product.product`. ERPNext nói REST và
gọi nó là `Item`. Nếu `tools.py` biết điều đó thì đổi ERP là viết lại agent.

Hợp đồng ở đây là thứ DUY NHẤT phần còn lại của hệ thống được biết. Mỗi
adapter tự lo phần bẩn của ERP nó phục vụ.

VÌ SAO `Gia` LÀ MỘT VẬT, KHÔNG PHẢI MỘT `int`
---------------------------------------------
Cả Odoo lẫn ERPNext đều có bảng giá: giá phụ thuộc nhóm khách, số lượng,
ngày, khuyến mãi. Trả về `int` trần là vứt mất `nguon` — và khi khách hỏi
"sao lại báo giá này" thì không ai truy được nó đến từ bảng giá nào.

VÌ SAO `TonKho.ban_duoc` CHỨ KHÔNG PHẢI `ton_kho`
-------------------------------------------------
Hàng có trong kho khác hàng bán được: một phần đã bị đơn khác giữ chỗ.
Odoo gọi phần bán được là `free_qty`; ERPNext là `actual_qty - reserved_qty`.
Lấy nhầm sang tổng tồn là hứa bán món đã có người đặt. Đặt tên trường theo
đúng ý nghĩa để không ai gán nhầm.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class LoiERP(RuntimeError):
    """Gọi ERP không thành. Cổng bắt lỗi này để quyết định trả `None`."""


@dataclass(frozen=True)
class Gia:
    """Giá bán một sản phẩm, kèm nguồn để truy vết."""

    gia_ban: int
    don_vi: str = "VND"
    nguon: str = ""
    hieu_luc_den: str | None = None


@dataclass(frozen=True)
class TonKho:
    """Số lượng BÁN ĐƯỢC (đã trừ phần bị giữ chỗ), tại một kho."""

    ban_duoc: int
    ma_kho: str = ""


@dataclass(frozen=True)
class SanPhamERP:
    """Nửa thương mại của một sản phẩm. Nửa tư vấn nằm ở kho nội bộ."""

    ma: str
    ten: str
    loai: str = ""
    dung_tich: str = ""
    ban_duoc_phep: bool = True


@dataclass(frozen=True)
class KetQuaDon:
    """Kết quả đẩy một đơn sang ERP. Dùng ở giai đoạn 4."""

    thanh_cong: bool
    erp_ma_don: str = ""
    ly_do: str = ""


@runtime_checkable
class NguonERP(Protocol):
    """Bốn việc mọi adapter phải làm được. Không hơn.

    Giữ hợp đồng nhỏ là cố ý: mỗi phương thức thêm vào là một phương thức
    phải hiện thực đúng bốn lần và test đúng bốn lần.
    """

    ten: str

    async def danh_sach_san_pham(
        self, chi_ban_duoc: bool = True
    ) -> list[SanPhamERP]: ...

    async def gia(self, ma: str) -> Gia | None: ...

    async def ton_kho(self, ma: str) -> TonKho | None: ...

    async def suc_khoe(self) -> bool: ...
