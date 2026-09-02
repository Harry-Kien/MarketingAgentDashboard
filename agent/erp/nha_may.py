"""
Dựng cổng theo cấu hình. Một chỗ duy nhất biết `ERP_LOAI` nghĩa là gì.

VÌ SAO NÉM KHI `ERP_LOAI` LẠ
----------------------------
Cám dỗ là rơi về `tep` cho "an toàn". Nhưng gõ sai `ERP_LOAI=odooo` rồi lặng
lẽ đọc file là chạy suốt tháng với giá cũ mà tưởng đang nối ERP — hỏng im
lặng, đúng khuôn đã cắn repo này bốn lần. Nổ to lúc khởi động rẻ hơn nhiều.
"""
from __future__ import annotations

from agent.config import settings
from agent.erp.cong import Cong
from agent.erp.hop_dong import NguonERP

# Thêm "mcp" khi có ERP nào ship sẵn máy chủ MCP.
_LOAI_HOP_LE = ("tep", "erpnext", "odoo")

_cong: Cong | None = None


def tao_nguon() -> NguonERP:
    loai = (settings.erp_loai or "tep").strip().lower()
    if loai == "tep":
        from agent.erp.tep import NguonTep

        return NguonTep()
    if loai == "erpnext":
        from agent.erp.erpnext import NguonErpNext

        # Adapter tự kiểm cấu hình và NÉM ngay lúc dựng nếu thiếu. Để nó nổ
        # ở đây, lúc khởi động, chứ không bắt lại thành đường lui im lặng.
        return NguonErpNext()
    if loai == "odoo":
        from agent.erp.odoo import NguonOdoo

        return NguonOdoo()
    raise ValueError(
        f"ERP_LOAI={loai!r} không nhận ra. Hợp lệ: {', '.join(_LOAI_HOP_LE)}"
    )


def cong() -> Cong:
    global _cong
    if _cong is None:
        _cong = Cong(
            tao_nguon(),
            ttl_gia=settings.erp_ttl_gia,
            ttl_ton=settings.erp_ttl_ton,
            ngat_mach_so_lan=settings.erp_ngat_mach_so_lan,
            ngat_mach_giay=settings.erp_ngat_mach_giay,
            han_cho_giay=settings.erp_han_cho_giay,
            so_lan_thu=settings.erp_so_lan_thu,
        )
    return _cong


def dat_lai() -> None:
    """Chỉ dùng trong test."""
    global _cong
    _cong = None
