"""
Kiểm thử tích hợp phân hệ NextERP / ERPNext.
"""
from __future__ import annotations

import asyncio

from agent.erp.base import BaseERPClient
from agent.erp.mock import MockERPClient
from agent.erp.models import (
    ERPCustomer,
    ERPItem,
    ERPSalesOrder,
    ERPSalesOrderStatus,
    ERPStockBalance,
    ERPWebhookEvent,
)
from agent.erp.service import (
    cap_nhat_ma_van_don_erp,
    get_erp_client,
    lay_danh_muc_san_pham,
    lay_ton_kho_san_pham,
    parse_erp_webhook,
    tao_sales_order_erp,
)


def test_mock_erp_client_basic() -> None:
    """Kiểm tra MockERPClient khởi tạo danh mục và đọc tồn kho."""
    async def _run():
        client = MockERPClient()
        assert client.provider_name == "mock"

        items = await client.get_items()
        assert len(items) > 0

        first_item = items[0]
        stock = await client.get_stock(first_item.item_code)
        assert isinstance(stock, ERPStockBalance)
        assert stock.available_qty >= 0
    asyncio.run(_run())


def test_mock_erp_sales_order_flow() -> None:
    """Kiểm tra luồng tạo Sales Order, trừ kho và cập nhật vận đơn trên ERP."""
    async def _run():
        client = MockERPClient()
        items = await client.get_items()
        assert len(items) >= 2

        item1 = items[0]
        item2 = items[1]
        initial_stock_1 = (await client.get_stock(item1.item_code)).available_qty

        # 1. Tạo khách hàng trên ERP
        cust = await client.create_or_update_customer(
            name="Hoàng Bảo",
            phone="0912345678",
            address="123 Lê Lợi, Q1, TP.HCM",
        )
        assert cust.customer_name == "Hoàng Bảo"
        assert cust.phone == "0912345678"

        # 2. Tạo Sales Order
        so_items = [
            {"item_code": item1.item_code, "qty": 2, "rate": item1.standard_rate},
            {"item_code": item2.item_code, "qty": 1, "rate": item2.standard_rate},
        ]
        so = await client.create_sales_order(
            customer=cust,
            items=so_items,
            shipping_fee=30000,
            notes="Đơn hàng đặt qua Zalo Agent",
        )

        assert isinstance(so, ERPSalesOrder)
        assert so.name.startswith("SO-")
        assert so.customer_name == "Hoàng Bảo"
        assert len(so.items) == 2
        assert so.shipping_fee == 30000
        assert so.grand_total == (item1.standard_rate * 2 + item2.standard_rate * 1 + 30000)
        assert so.status == ERPSalesOrderStatus.TO_DELIVER_AND_BILL

        # 3. Kiểm tra kho đã được trừ trên ERP
        new_stock_1 = (await client.get_stock(item1.item_code)).available_qty
        assert new_stock_1 == initial_stock_1 - 2

        # 4. Gắn mã vận đơn GHN vào Sales Order
        updated = await client.update_sales_order_tracking(
            sales_order_id=so.name,
            tracking_number="GY8YTRFA",
            carrier="ghn",
        )
        assert updated is True

        fetched_so = await client.get_sales_order(so.name)
        assert fetched_so is not None
        assert fetched_so.tracking_number == "GY8YTRFA"
        assert fetched_so.carrier == "ghn"

        # 5. Hủy đơn và kiểm tra hoàn kho trên ERP
        cancelled = await client.cancel_sales_order(so.name, reason="Khách đổi ý")
        assert cancelled is True
        restored_stock_1 = (await client.get_stock(item1.item_code)).available_qty
        assert restored_stock_1 == initial_stock_1
    asyncio.run(_run())


def test_erp_service_helpers() -> None:
    """Kiểm tra các hàm điều phối nghiệp vụ trong agent.erp.service."""
    async def _run():
        client = get_erp_client()
        assert isinstance(client, BaseERPClient)

        items = await lay_danh_muc_san_pham()
        assert len(items) > 0

        so = await tao_sales_order_erp(
            khach_ten="Nguyễn Văn A",
            khach_sdt="0987654321",
            khach_dia_chi="456 Nguyễn Huệ, Q1",
            items=[{"item_code": items[0].item_code, "qty": 1, "rate": items[0].standard_rate}],
            shipping_fee=0,
        )
        assert so.name.startswith(("SO", "S", "SAL-ORD"))
        assert so.customer_name == "Nguyễn Văn A"

        # Cập nhật mã vận đơn
        ok = await cap_nhat_ma_van_don_erp(so.name, "MOCK-GHN-TEST", "mock")
        assert ok is True

        # Parse webhook
        event = parse_erp_webhook(
            {"event": "stock_updated", "doctype": "Stock Entry", "docname": "STE-2026-001", "data": {"qty": 100}},
            headers={},
        )
        assert isinstance(event, ERPWebhookEvent)
        assert event.event_type == "stock_updated"
        assert event.doc_name == "STE-2026-001"
    asyncio.run(_run())
