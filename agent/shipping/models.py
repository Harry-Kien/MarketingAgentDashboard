"""
Các kiểu dữ liệu cho phân hệ vận chuyển.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal


class InternalShippingStatus(str, Enum):
    """
    7 trạng thái vận chuyển nội bộ (BUG-17-04):
      - READY_TO_PICK: Đã tạo vận đơn, chờ shipper lấy hàng (hàng chưa rời kho).
      - DELIVERING: Đã lấy hàng, đang trung chuyển hoặc đang giao tới khách.
      - DELIVERED: Giao hàng thành công -> Đóng đơn.
      - DELIVERY_FAILED: Giao thất bại / sự cố (hẹn lại, mất/hư) -> Cần người xử lý.
      - RETURNING: Đang hoàn hàng về kho (hàng chưa về kệ -> KHÔNG cộng kho).
      - RETURNED: Hãng xác nhận đã hoàn hàng về kho -> Sinh việc kiểm tra hàng hoàn, KHÔNG tự cộng kho.
      - CANCELLED: Hãng xác nhận đã huỷ vận đơn.
    """
    READY_TO_PICK = "ready_to_pick"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"
    RETURNING = "returning"
    RETURNED = "returned"
    CANCELLED = "cancelled"


# Các trạng thái chứng minh hàng đã rời kho (bàn giao cho hãng vận chuyển).
TRANG_THAI_DA_LAY_HANG = frozenset({
    InternalShippingStatus.DELIVERING,
    InternalShippingStatus.DELIVERY_FAILED,
    InternalShippingStatus.RETURNING,
    InternalShippingStatus.RETURNED,
    InternalShippingStatus.DELIVERED,
})


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
    client_order_code: str = ""


@dataclass(slots=True)
class CreateWaybillResult:
    ok: bool
    ma_van_don: str = ""
    don_vi: str = ""
    phi_van_chuyen: int = 0
    ngay_du_kien_giao: datetime | None = None
    trang_thai_noi_bo: InternalShippingStatus = InternalShippingStatus.READY_TO_PICK
    thong_tin_them: dict[str, Any] = field(default_factory=dict)
    loi: str = ""
    # Không phải lỗi hệ thống — là việc cần người quyết. Ví dụ: địa chỉ khách
    # cho không đủ để xác định quận/phường. Agent phải HỎI LẠI, không thử lại.
    can_nguoi_xac_nhan: bool = False
    # True khi không xác định được hãng đã tạo đơn hay chưa (timeout, rớt mạng,
    # HTTP 5xx, phản hồi thiếu mã vận đơn). CẤM tự kết luận thất bại và tạo lại.
    khong_ro_ket_qua: bool = False
    client_order_code: str = ""


@dataclass(slots=True)
class ClientCodeLookupResult:
    """Kết quả đối soát vận đơn với hãng qua `client_order_code`."""
    trang_thai: Literal["found", "not_found", "indeterminate", "unsupported"]
    ma_van_don: str = ""
    client_order_code: str = ""
    don_vi: str = ""
    phi_van_chuyen: int = 0
    ngay_du_kien_giao: datetime | None = None
    trang_thai_noi_bo: InternalShippingStatus | None = None
    trang_thai_goc: str = ""
    du_lieu_goc: dict[str, Any] = field(default_factory=dict)
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
    # None = KHÔNG nhận ra mã của hãng.
    #
    # Mặc định cũ là DELIVERING, nghĩa là một mã lạ — `lost`, hoặc mã GHN vừa
    # thêm — lặng lẽ thành "đang giao". Khách hỏi "đơn tới đâu rồi" thì agent
    # trả lời "đang giao" cho kiện hàng đã mất.
    trang_thai_noi_bo: InternalShippingStatus | None = None
    mo_ta: str = ""
    thoi_gian: datetime | None = None
    du_lieu_goc: dict[str, Any] = field(default_factory=dict)
    loi: str = ""
    # Mã hãng nhận ra nhưng không phải trạng thái chính thức — xem
    # `BaseShippingProvider.MA_CHI_THONG_TIN`. Đúng thì chỉ ghi nhật ký.
    chi_thong_tin: bool = False
