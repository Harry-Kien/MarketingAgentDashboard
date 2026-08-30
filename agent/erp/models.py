"""
Các mô hình dữ liệu cho phân hệ tích hợp NextERP / ERPNext.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ERPSalesOrderStatus(str, Enum):
    """
    Trạng thái chuẩn của Sales Order trên ERP:
      - DRAFT: Bản nháp
      - TO_DELIVER_AND_BILL: Đã xác nhận, chờ xuất kho & hóa đơn
      - TO_BILL: Đã giao, chờ đối soát/thanh toán
      - COMPLETED: Hoàn thành trọn vẹn
      - CANCELLED: Đã hủy
    """
    DRAFT = "Draft"
    TO_DELIVER_AND_BILL = "To Deliver and Bill"
    TO_BILL = "To Bill"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


@dataclass
class ERPItem:
    """Sản phẩm đồng bộ từ ERP."""
    item_code: str                  # Mã định danh ERP (ví dụ: AS-SR01)
    item_name: str                  # Tên sản phẩm
    standard_rate: int              # Giá niêm yết (VND)
    stock_qty: int = 0              # Số lượng tồn kho thực tế
    item_group: str = "Products"    # Nhóm sản phẩm
    description: str = ""           # Mô tả công dụng, thành phần
    image_url: str = ""             # Ảnh sản phẩm


@dataclass
class ERPStockBalance:
    """Số dư tồn kho của một sản phẩm."""
    item_code: str
    warehouse: str                  # Tên kho trên ERP (ví dụ: Kho Tổng - AS)
    actual_qty: int                 # Tồn kho thực tế
    reserved_qty: int = 0           # Tồn kho đang giữ cho các đơn chưa xuất
    available_qty: int = 0          # Tồn kho khả dụng (= actual - reserved)


@dataclass
class ERPCustomer:
    """Khách hàng đồng bộ trên CRM của ERP."""
    customer_name: str
    phone: str
    customer_group: str = "Individual"
    territory: str = "Vietnam"
    customer_id: str | None = None
    address_line: str = ""


@dataclass
class ERPSalesOrderItem:
    """Chi tiết từng sản phẩm trong Sales Order."""
    item_code: str
    item_name: str
    qty: int
    rate: int
    amount: int = 0

    def __post_init__(self) -> None:
        if not self.amount:
            self.amount = self.qty * self.rate


@dataclass
class ERPSalesOrder:
    """Đơn bán hàng trên NextERP."""
    name: str                       # Mã đơn ERP (ví dụ: SO-2026-00001)
    customer_name: str
    customer_phone: str
    customer_address: str
    items: list[ERPSalesOrderItem]
    total_amount: int
    shipping_fee: int = 0
    grand_total: int = 0
    status: ERPSalesOrderStatus = ERPSalesOrderStatus.TO_DELIVER_AND_BILL
    tracking_number: str = ""       # Mã vận đơn GHN liên kết
    carrier: str = ""               # Đơn vị vận chuyển
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.grand_total:
            self.grand_total = self.total_amount + self.shipping_fee


@dataclass
class ERPWebhookEvent:
    """Sự kiện gửi từ NextERP sang Agent."""
    event_type: str                 # "stock_updated", "order_status_changed", "item_created"
    doc_type: str                   # "Stock Ledger Entry", "Sales Order", "Item"
    doc_name: str
    data: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
