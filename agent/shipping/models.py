"""
Các kiểu dữ liệu cho phân hệ vận chuyển.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class InternalShippingStatus(str, Enum):
    """
    4 trạng thái vận chuyển cốt lõi trong hệ thống nội bộ:
      - DELIVERING: Hàng đang được trung chuyển, giao hàng hoặc đang xử lý.
      - DELIVERED: Giao hàng và thu tiền COD thành công -> Đóng đơn.
      - DELIVERY_FAILED: Giao hàng thất bại (khách hẹn lại, không nghe máy) -> Cần người can thiệp.
      - RETURNED: Hàng hoàn về kho -> Tự động hoàn tồn kho.
    """
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"
    RETURNED = "returned"


@dataclass(slots=True)
class ShippingItem:
    ma: str
    ten: str
    so_luong: int = 1
    don_gia: int = 0
    khoi_luong_gram: int = 200


@dataclass(slots=True)
class CreateWaybillRequest:
    ma_don: str
    khach_ten: str
    khach_sdt: str
    khach_dia_chi: str
    items: list[ShippingItem] = field(default_factory=list)
    tong_tien: int = 0
    thu_ho_cod: int = 0
    tong_khoi_luong_gram: int = 500
    ghi_chu: str = ""
    yeu_cau_giao: str = "KHONGCHOXEMHANG"  # CHOXEMHANGKHONGTHU | CHOTHUHANG | KHONGCHOXEMHANG


@dataclass(slots=True)
class CreateWaybillResult:
    ok: bool
    ma_van_don: str = ""
    don_vi: str = ""
    phi_van_chuyen: int = 0
    ngay_du_kien_giao: datetime | None = None
    trang_thai_noi_bo: InternalShippingStatus = InternalShippingStatus.DELIVERING
    thong_tin_them: dict[str, Any] = field(default_factory=dict)
    loi: str = ""


@dataclass(slots=True)
class TrackingTimelineItem:
    thoi_gian: datetime
    trang_thai_hang: str
    trang_thai_noi_bo: InternalShippingStatus
    dia_diem: str = ""
    mo_ta: str = ""


@dataclass(slots=True)
class TrackingResult:
    ok: bool
    ma_van_don: str
    don_vi: str
    trang_thai_noi_bo: InternalShippingStatus
    trang_thai_goc: str
    vi_tri_hien_tai: str = ""
    ngay_du_kien_giao: datetime | None = None
    lich_su: list[TrackingTimelineItem] = field(default_factory=list)
    loi: str = ""


@dataclass(slots=True)
class WebhookEventResult:
    hop_le: bool
    ma_don: str = ""
    ma_van_don: str = ""
    don_vi: str = ""
    trang_thai_goc: str = ""
    trang_thai_noi_bo: InternalShippingStatus = InternalShippingStatus.DELIVERING
    mo_ta: str = ""
    thoi_gian: datetime | None = None
    du_lieu_goc: dict[str, Any] = field(default_factory=dict)
    loi: str = ""
