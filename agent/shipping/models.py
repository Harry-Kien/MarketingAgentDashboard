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
<<<<<<< HEAD
=======
    # Không phải lỗi hệ thống — là việc cần người quyết. Ví dụ: địa chỉ khách
    # cho không đủ để xác định quận/phường. Agent phải HỎI LẠI, không thử lại.
    can_nguoi_xac_nhan: bool = False
>>>>>>> origin/main


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
<<<<<<< HEAD
    trang_thai_noi_bo: InternalShippingStatus = InternalShippingStatus.DELIVERING
=======
    # None = KHÔNG nhận ra mã của hãng.
    #
    # Mặc định cũ là DELIVERING, nghĩa là một mã lạ — `lost`, hoặc mã GHN vừa
    # thêm — lặng lẽ thành "đang giao". Khách hỏi "đơn tới đâu rồi" thì agent
    # trả lời "đang giao" cho kiện hàng đã mất.
    trang_thai_noi_bo: InternalShippingStatus | None = None
>>>>>>> origin/main
    mo_ta: str = ""
    thoi_gian: datetime | None = None
    du_lieu_goc: dict[str, Any] = field(default_factory=dict)
    loi: str = ""
