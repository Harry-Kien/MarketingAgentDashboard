"""
Dịch vụ điều phối nghiệp vụ ERP: Caching, Khởi tạo đơn và Xử lý sự kiện Webhook.
"""
from __future__ import annotations

import time
from typing import Any

from agent.config import settings
from .base import BaseERPClient
from .mock import MockERPClient
from .models import (
    ERPItem,
    ERPSalesOrder,
    ERPWebhookEvent,
)
from .nexterp import NextERPClient

_CLIENT_INSTANCE: BaseERPClient | None = None
_MOCK_FALLBACK: MockERPClient | None = None
_ITEMS_CACHE: list[ERPItem] | None = None
_ITEMS_CACHE_TIME: float = 0.0
_STOCK_CACHE: dict[str, int] = {}
_STOCK_CACHE_TIME: float = 0.0


def _get_mock_fallback() -> MockERPClient:
    """Trả về MockERPClient dùng chung cho các lần fallback."""
    global _MOCK_FALLBACK
    if _MOCK_FALLBACK is None:
        _MOCK_FALLBACK = MockERPClient()
    return _MOCK_FALLBACK


def get_erp_client() -> BaseERPClient:
    """Factory lấy ERP Client theo cấu hình ERP_PROVIDER trong .env."""
    global _CLIENT_INSTANCE
    provider = (settings.erp_provider or "mock").lower()
    if _CLIENT_INSTANCE is None or _CLIENT_INSTANCE.provider_name != provider:
        if provider == "nexterp":
            _CLIENT_INSTANCE = NextERPClient()
        else:
            _CLIENT_INSTANCE = MockERPClient()
    return _CLIENT_INSTANCE


async def lay_danh_muc_san_pham(force_refresh: bool = False) -> list[ERPItem]:
    """Lấy danh mục sản phẩm từ ERP có đệm RAM (TTL 5 phút)."""
    global _ITEMS_CACHE, _ITEMS_CACHE_TIME
    now = time.time()
    ttl = getattr(settings, "erp_cache_ttl_seconds", 300)

    if _ITEMS_CACHE is not None and not force_refresh and (now - _ITEMS_CACHE_TIME < ttl):
        return _ITEMS_CACHE

    client = get_erp_client()
    try:
        items = await client.get_items()
        if items:
            _ITEMS_CACHE = items
            _ITEMS_CACHE_TIME = now
            return items
    except Exception:
        pass

    # Nếu ERP bên ngoài chưa khởi động hoặc chạy trong CI runner -> nạp dữ liệu Mock
    if client.provider_name != "mock":
        try:
            mock_items = await _get_mock_fallback().get_items()
            if mock_items:
                return mock_items
        except Exception:
            pass

    return _ITEMS_CACHE or []


async def lay_ton_kho_san_pham(item_code: str) -> int:
    """Lấy số lượng tồn kho khả dụng của sản phẩm từ ERP."""
    client = get_erp_client()
    try:
        sb = await client.get_stock(item_code)
        return sb.available_qty
    except Exception:
        if client.provider_name != "mock":
            try:
                sb = await _get_mock_fallback().get_stock(item_code)
                return sb.available_qty
            except Exception:
                pass
        return 0


async def tao_sales_order_erp(
    khach_ten: str,
    khach_sdt: str,
    khach_dia_chi: str,
    items: list[dict[str, Any]],
    shipping_fee: int = 0,
    notes: str = "",
) -> ERPSalesOrder | None:
    """Tạo đơn hàng Sales Order trên ERP."""
    client = get_erp_client()
    try:
        cust = await client.create_or_update_customer(khach_ten, khach_sdt, khach_dia_chi)
        return await client.create_sales_order(cust, items, shipping_fee, notes)
    except Exception:
        if client.provider_name != "mock":
            try:
                mock_client = _get_mock_fallback()
                cust = await mock_client.create_or_update_customer(khach_ten, khach_sdt, khach_dia_chi)
                return await mock_client.create_sales_order(cust, items, shipping_fee, notes)
            except Exception:
                pass
        return None


async def cap_nhat_ma_van_don_erp(
    sales_order_id: str, tracking_number: str, carrier: str
) -> bool:
    """Cập nhật mã vận đơn GHN vào đơn hàng trên ERP."""
    client = get_erp_client()
    try:
        ok = await client.update_sales_order_tracking(sales_order_id, tracking_number, carrier)
        if ok:
            return True
    except Exception:
        pass
    if client.provider_name != "mock":
        try:
            return await _get_mock_fallback().update_sales_order_tracking(sales_order_id, tracking_number, carrier)
        except Exception:
            pass
    return False


def parse_erp_webhook(payload: dict[str, Any], headers: dict[str, Any]) -> ERPWebhookEvent | None:
    """Phân tích Webhook gửi từ ERP."""
    client = get_erp_client()
    return client.parse_webhook(payload, headers)
