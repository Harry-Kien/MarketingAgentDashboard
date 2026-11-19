"""Kiểm tra/tạo custom fields Sales Order dùng cho DEV-02.

Mặc định chỉ kiểm tra. Thêm ``--apply`` mới ghi và chỉ cho phép localhost;
muốn chạy ở máy từ xa phải thêm rõ ``--allow-remote``.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from urllib.parse import urlparse

import httpx


FIELDS = (
    ("custom_shipping_tracking_number", "Mã vận đơn", "Data", "po_no"),
    ("custom_shipping_carrier", "Đơn vị vận chuyển", "Data",
     "custom_shipping_tracking_number"),
    ("custom_shipping_status", "Trạng thái vận chuyển", "Data",
     "custom_shipping_carrier"),
    ("custom_shipping_synced_at", "Đồng bộ vận chuyển lúc", "Datetime",
     "custom_shipping_status"),
    ("custom_shipping_reference", "Tham chiếu vận chuyển", "Data",
     "custom_shipping_synced_at"),
)


async def run(apply: bool = False, allow_remote: bool = False) -> int:
    from agent import cau_hinh_dong

    goc = str(cau_hinh_dong.lay("ERPNEXT_URL") or "").rstrip("/")
    key = str(cau_hinh_dong.lay("ERPNEXT_API_KEY") or "")
    secret = str(cau_hinh_dong.lay("ERPNEXT_API_SECRET") or "")
    if not all((goc, key, secret)):
        print("Thiếu ERPNEXT_URL/API_KEY/API_SECRET; không thay đổi gì.")
        return 2
    host = (urlparse(goc).hostname or "").lower()
    if apply and host not in {"127.0.0.1", "localhost", "::1"} and not allow_remote:
        print("Từ chối --apply trên ERP từ xa; thêm --allow-remote nếu đã xác nhận.")
        return 2

    headers = {"Authorization": f"token {key}:{secret}"}
    async with httpx.AsyncClient(base_url=goc, headers=headers, timeout=15.0) as client:
        response = await client.get(
            "/api/resource/Custom%20Field",
            params={
                "filters": json.dumps([["dt", "=", "Sales Order"]]),
                "fields": json.dumps(["fieldname"]),
                "limit_page_length": "0",
            },
        )
        response.raise_for_status()
        co = {str(x.get("fieldname")) for x in response.json().get("data", [])}
        thieu = [spec for spec in FIELDS if spec[0] not in co]
        if not thieu:
            print("PASS: Sales Order đã có đủ 5 custom fields vận chuyển.")
            return 0
        print("Thiếu: " + ", ".join(x[0] for x in thieu))
        if not apply:
            print("Chỉ kiểm tra; chạy lại với --apply trên ERP development để tạo.")
            return 1
        for fieldname, label, fieldtype, insert_after in thieu:
            created = await client.post("/api/resource/Custom%20Field", json={
                "dt": "Sales Order",
                "fieldname": fieldname,
                "label": label,
                "fieldtype": fieldtype,
                "insert_after": insert_after,
                "read_only": 1,
                "allow_on_submit": 1,
                "no_copy": 1,
            })
            created.raise_for_status()
            print(f"Đã tạo {fieldname}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(args.apply, args.allow_remote))


if __name__ == "__main__":
    raise SystemExit(main())
