"""
Mock ERP Client phục vụ kiểm thử tích hợp và môi trường phát triển offline.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import BaseERPClient
from .models import (
    ERPCustomer,
    ERPItem,
    ERPSalesOrder,
    ERPSalesOrderItem,
    ERPSalesOrderStatus,
    ERPStockBalance,
    ERPWebhookEvent,
)


class MockERPClient(BaseERPClient):
    """
    Giả lập máy chủ NextERP / ERPNext hoàn chỉnh:
      - Quản lý danh mục Items & Stock
      - Tạo mã Sales Order chuẩn ERP: SO-YYYY-XXXXX
      - Khóa tồn kho khi lên đơn và hoàn kho khi hủy đơn
    """

    def __init__(self) -> None:
        self._provider_name = "mock"
        self._items: dict[str, ERPItem] = {}
        self._stock: dict[str, int] = {}
        self._customers: dict[str, ERPCustomer] = {}
        self._sales_orders: dict[str, ERPSalesOrder] = {}
        self._so_counter = 1000
        self._load_seed_data()

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def _load_seed_data(self) -> None:
        catalog_path = Path("data/catalog.json")
        if not catalog_path.exists():
            catalog_path = Path("data/catalog.example.json")
        if catalog_path.exists():
            try:
                data = json.loads(catalog_path.read_text(encoding="utf-8"))
                for sp in data.get("san_pham", []):
                    code = str(sp.get("ma") or "")
                    if not code:
                        continue
                    item = ERPItem(
                        item_code=code,
                        item_name=str(sp.get("ten") or code),
                        standard_rate=int(sp.get("gia") or 0),
                        stock_qty=int(sp.get("ton_kho") or 50),
                        item_group=str(sp.get("loai") or "Mỹ phẩm"),
                        description=str(sp.get("luu_y") or ""),
                    )
                    self._items[code] = item
                    self._stock[code] = item.stock_qty
            except Exception:
                pass

    async def get_items(self, item_group: str | None = None) -> list[ERPItem]:
        items = list(self._items.values())
        if item_group:
            items = [it for it in items if it.item_group.lower() == item_group.lower()]
        for it in items:
            it.stock_qty = self._stock.get(it.item_code, 0)
        return items

    async def get_stock(self, item_code: str, warehouse: str | None = None) -> ERPStockBalance:
        wh = warehouse or "Kho Tổng - Aurora Skin"
        qty = self._stock.get(item_code, 0)
        return ERPStockBalance(
            item_code=item_code,
            warehouse=wh,
            actual_qty=qty,
            reserved_qty=0,
            available_qty=qty,
        )

    async def get_all_stock(self, warehouse: str | None = None) -> dict[str, int]:
        return dict(self._stock)

    async def create_or_update_customer(
        self, name: str, phone: str, address: str = ""
    ) -> ERPCustomer:
        cust_id = f"CUST-{phone}"
        cust = ERPCustomer(
            customer_id=cust_id,
            customer_name=name,
            phone=phone,
            address_line=address,
        )
        self._customers[phone] = cust
        return cust

    async def create_sales_order(
        self,
        customer: ERPCustomer,
        items: list[dict[str, Any]],
        shipping_fee: int = 0,
        notes: str = "",
    ) -> ERPSalesOrder:
        self._so_counter += 1
        year = datetime.now(timezone.utc).year
        so_name = f"SO-{year}-{self._so_counter:05d}"

        so_items: list[ERPSalesOrderItem] = []
        total = 0
        for it in items:
            code = str(it.get("item_code") or it.get("ma") or "")
            qty = int(it.get("qty") or it.get("so_luong") or 1)
            item_info = self._items.get(code)
            rate = int(it.get("rate") or (item_info.standard_rate if item_info else 0))
            name = item_info.item_name if item_info else code

            # Trừ kho giả lập trên ERP
            current = self._stock.get(code, 0)
            self._stock[code] = max(0, current - qty)

            so_item = ERPSalesOrderItem(
                item_code=code,
                item_name=name,
                qty=qty,
                rate=rate,
                amount=rate * qty,
            )
            so_items.append(so_item)
            total += so_item.amount

        sales_order = ERPSalesOrder(
            name=so_name,
            customer_name=customer.customer_name,
            customer_phone=customer.phone,
            customer_address=customer.address_line,
            items=so_items,
            total_amount=total,
            shipping_fee=shipping_fee,
            grand_total=total + shipping_fee,
            status=ERPSalesOrderStatus.TO_DELIVER_AND_BILL,
        )
        self._sales_orders[so_name] = sales_order
        return sales_order

    async def update_sales_order_tracking(
        self, sales_order_id: str, tracking_number: str, carrier: str
    ) -> bool:
        if sales_order_id in self._sales_orders:
            so = self._sales_orders[sales_order_id]
            so.tracking_number = tracking_number
            so.carrier = carrier
            return True
        return False

    async def get_sales_order(self, sales_order_id: str) -> ERPSalesOrder | None:
        return self._sales_orders.get(sales_order_id)

    async def cancel_sales_order(self, sales_order_id: str, reason: str = "") -> bool:
        if sales_order_id in self._sales_orders:
            so = self._sales_orders[sales_order_id]
            so.status = ERPSalesOrderStatus.CANCELLED
            # Hoàn lại tồn kho trên ERP
            for it in so.items:
                self._stock[it.item_code] = self._stock.get(it.item_code, 0) + it.qty
            return True
        return False

    def parse_webhook(self, payload: dict[str, Any], headers: dict[str, Any]) -> ERPWebhookEvent | None:
        event_type = str(payload.get("event") or payload.get("event_type") or "stock_updated")
        doc_type = str(payload.get("doctype") or payload.get("doc_type") or "Stock")
        doc_name = str(payload.get("docname") or payload.get("doc_name") or "")
        return ERPWebhookEvent(
            event_type=event_type,
            doc_type=doc_type,
            doc_name=doc_name,
            data=payload.get("data") or payload,
        )
