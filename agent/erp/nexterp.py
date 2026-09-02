"""
Client kết nối chính thức với hệ thống NextERP / Frappe ERPNext qua REST API.
Tài liệu tham khảo: https://frappeframework.com/docs/user/en/api/rest
"""
from __future__ import annotations

from typing import Any

import httpx

from agent.config import settings
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


class NextERPClient(BaseERPClient):
    """
    Adapter kết nối thực tế tới NextERP / ERPNext:
      - Xác thực qua token API Key : API Secret
      - Đồng bộ Items, Stock Ledger, Customer CRM và Sales Order
    """

    def __init__(self) -> None:
        self._provider_name = "nexterp"
        self._base_url = settings.nexterp_base_url.rstrip("/")
        self._api_key = settings.nexterp_api_key
        self._api_secret = settings.nexterp_api_secret

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._api_key and self._api_secret:
            headers["Authorization"] = f"token {self._api_key}:{self._api_secret}"
        return headers

    async def get_items(self, item_group: str | None = None) -> list[ERPItem]:
        url = f"{self._base_url}/api/resource/Item"
        params: dict[str, Any] = {
            "fields": '["name","item_name","standard_rate","item_group","description","image"]',
            "limit_page_length": 100,
        }
        if item_group:
            params["filters"] = f'[["item_group","=","{item_group}"]]'

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=self._headers(), params=params)
            if resp.status_code != 200:
                return []
            data = resp.json().get("data", [])

        out = []
        for d in data:
            out.append(
                ERPItem(
                    item_code=d.get("name", ""),
                    item_name=d.get("item_name", d.get("name", "")),
                    standard_rate=int(d.get("standard_rate") or 0),
                    item_group=d.get("item_group", "Products"),
                    description=d.get("description", ""),
                    image_url=d.get("image", ""),
                )
            )
        return out

    async def get_stock(self, item_code: str, warehouse: str | None = None) -> ERPStockBalance:
        url = f"{self._base_url}/api/method/erpnext.stock.utils.get_latest_stock_qty"
        params = {"item_code": item_code}
        if warehouse:
            params["warehouse"] = warehouse

        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers=self._headers(), params=params)
            actual_qty = 0
            if resp.status_code == 200:
                actual_qty = int(resp.json().get("message") or 0)

        return ERPStockBalance(
            item_code=item_code,
            warehouse=warehouse or "Stores - AS",
            actual_qty=actual_qty,
            available_qty=actual_qty,
        )

    async def get_all_stock(self, warehouse: str | None = None) -> dict[str, int]:
        items = await self.get_items()
        stock_map = {}
        for it in items:
            sb = await self.get_stock(it.item_code, warehouse)
            stock_map[it.item_code] = sb.available_qty
        return stock_map

    async def create_or_update_customer(
        self, name: str, phone: str, address: str = ""
    ) -> ERPCustomer:
        url = f"{self._base_url}/api/resource/Customer"
        cust_name = f"{name} ({phone})"
        cust_id = cust_name

        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Kiểm tra xem khách hàng đã tồn tại trên NextERP chưa
            check_url = f"{url}?filters=[[\"mobile_no\",\"=\",\"{phone}\"]]"
            r_check = await client.get(check_url, headers=self._headers())
            if r_check.status_code == 200 and r_check.json().get("data"):
                cust_id = r_check.json()["data"][0]["name"]
                return ERPCustomer(
                    customer_name=name,
                    phone=phone,
                    customer_id=cust_id,
                    address_line=address,
                )

            # 2. Tạo mới khách hàng
            payload = {
                "customer_name": cust_name,
                "customer_type": "Individual",
                "customer_group": "Cá nhân",
                "territory": "Vietnam",
                "mobile_no": phone,
            }
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code in (200, 201):
                cust_id = resp.json().get("data", {}).get("name", cust_name)

        return ERPCustomer(
            customer_name=name,
            phone=phone,
            customer_id=cust_id,
            address_line=address,
        )

    async def create_sales_order(
        self,
        customer: ERPCustomer,
        items: list[dict[str, Any]],
        shipping_fee: int = 0,
        notes: str = "",
    ) -> ERPSalesOrder:
        url = f"{self._base_url}/api/resource/Sales Order"
        so_items = []
        for it in items:
            code = str(it.get("item_code") or it.get("ma") or "")
            qty = int(it.get("qty") or it.get("so_luong") or 1)
            rate = int(it.get("rate") or it.get("don_gia") or 0)
            so_items.append({
                "item_code": code,
                "qty": qty,
                "rate": rate,
            })

        payload: dict[str, Any] = {
            "customer": customer.customer_id or customer.customer_name,
            "order_type": "Sales",
            "po_no": notes.split('#')[-1].strip() if '#' in notes else notes,
            "po_date": __import__("datetime").date.today().isoformat(),
            "docstatus": 1,
            "delivery_date": __import__("datetime").date.today().isoformat(),
            "items": so_items,
            "remarks": notes,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"Lỗi tạo Sales Order trên NextERP ({resp.status_code}): {resp.text}")
            data = resp.json().get("data", {})

        order_name = data.get("name", "SO-ERP-UNKNOWN")
        total = int(data.get("net_total") or data.get("grand_total") or 0)

        out_items = [
            ERPSalesOrderItem(
                item_code=it.get("item_code", ""),
                item_name=it.get("item_name", it.get("item_code", "")),
                qty=int(it.get("qty") or 1),
                rate=int(it.get("rate") or 0),
                amount=int(it.get("amount") or 0),
            )
            for it in data.get("items", [])
        ]

        return ERPSalesOrder(
            name=order_name,
            customer_name=customer.customer_name,
            customer_phone=customer.phone,
            customer_address=customer.address_line,
            items=out_items or [ERPSalesOrderItem(item_code="SP", item_name="SP", qty=1, rate=total)],
            total_amount=total,
            shipping_fee=shipping_fee,
            grand_total=total + shipping_fee,
            status=ERPSalesOrderStatus.TO_DELIVER_AND_BILL,
            raw=data,
        )

    async def update_sales_order_tracking(
        self, sales_order_id: str, tracking_number: str, carrier: str
    ) -> bool:
        url = f"{self._base_url}/api/resource/Sales Order/{sales_order_id}"
        payload = {
            "tracking_number": tracking_number,
            "carrier": carrier,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.put(url, headers=self._headers(), json=payload)
                return resp.status_code in (200, 201)
        except Exception:
            return False

    async def get_sales_order(self, sales_order_id: str) -> ERPSalesOrder | None:
        url = f"{self._base_url}/api/resource/Sales Order/{sales_order_id}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=self._headers())
                if resp.status_code != 200:
                    return None
                data = resp.json().get("data", {})
        except Exception:
            return None

        return ERPSalesOrder(
            name=data.get("name", sales_order_id),
            customer_name=data.get("customer_name", ""),
            customer_phone="",
            customer_address=data.get("shipping_address", ""),
            items=[],
            total_amount=int(data.get("grand_total") or 0),
            status=ERPSalesOrderStatus.TO_DELIVER_AND_BILL,
            raw=data,
        )

    async def cancel_sales_order(self, sales_order_id: str, reason: str = "") -> bool:
        url = f"{self._base_url}/api/resource/Sales Order/{sales_order_id}"
        payload = {"docstatus": 2, "cancel_reason": reason}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.put(url, headers=self._headers(), json=payload)
            return resp.status_code in (200, 201)

    def parse_webhook(self, payload: dict[str, Any], headers: dict[str, Any]) -> ERPWebhookEvent | None:
        return ERPWebhookEvent(
            event_type=str(payload.get("event") or "doc_update"),
            doc_type=str(payload.get("doctype") or "Sales Order"),
            doc_name=str(payload.get("docname") or payload.get("name") or ""),
            data=payload.get("data") or payload,
        )
