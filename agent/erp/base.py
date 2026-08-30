"""
Interface trừu tượng cho mọi hệ thống ERP (NextERP / ERPNext, Odoo, MockERP).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import (
    ERPCustomer,
    ERPItem,
    ERPSalesOrder,
    ERPStockBalance,
    ERPWebhookEvent,
)


class BaseERPClient(ABC):
    """
    Hợp đồng giao tiếp giữa AI Agent và hệ thống ERP Doanh nghiệp.
    Mọi ERP Adapter bắt buộc phải cài đặt đầy đủ các phương thức này.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Tên nhà cung cấp (ví dụ: 'nexterp', 'odoo', 'mock')."""
        ...

    @abstractmethod
    async def get_items(self, item_group: str | None = None) -> list[ERPItem]:
        """Lấy danh mục sản phẩm kèm giá niêm yết từ ERP."""
        ...

    @abstractmethod
    async def get_stock(self, item_code: str, warehouse: str | None = None) -> ERPStockBalance:
        """Lấy số lượng tồn kho thực tế và khả dụng của sản phẩm."""
        ...

    @abstractmethod
    async def get_all_stock(self, warehouse: str | None = None) -> dict[str, int]:
        """Lấy bản đồ tồn kho khả dụng {item_code: available_qty} của toàn bộ sản phẩm."""
        ...

    @abstractmethod
    async def create_or_update_customer(
        self, name: str, phone: str, address: str = ""
    ) -> ERPCustomer:
        """Tạo hoặc cập nhật khách hàng trên CRM của ERP."""
        ...

    @abstractmethod
    async def create_sales_order(
        self,
        customer: ERPCustomer,
        items: list[dict[str, Any]],
        shipping_fee: int = 0,
        notes: str = "",
    ) -> ERPSalesOrder:
        """
        Tạo đơn bán hàng (Sales Order) trên ERP.
        - Khóa tồn kho (Reserved Qty)
        - Tính tổng tiền & phí giao hàng
        - Trả về mã đơn ERP (ví dụ SO-2026-00001)
        """
        ...

    @abstractmethod
    async def update_sales_order_tracking(
        self, sales_order_id: str, tracking_number: str, carrier: str
    ) -> bool:
        """Đính kèm mã vận đơn của hãng vận chuyển vào Sales Order trên ERP."""
        ...

    @abstractmethod
    async def get_sales_order(self, sales_order_id: str) -> ERPSalesOrder | None:
        """Tra cứu chi tiết Sales Order từ ERP."""
        ...

    @abstractmethod
    async def cancel_sales_order(self, sales_order_id: str, reason: str = "") -> bool:
        """Hủy Sales Order trên ERP và giải phóng tồn kho đã giữ."""
        ...

    @abstractmethod
    def parse_webhook(self, payload: dict[str, Any], headers: dict[str, Any]) -> ERPWebhookEvent | None:
        """Phân tích dữ liệu Webhook gửi từ ERP."""
        ...
