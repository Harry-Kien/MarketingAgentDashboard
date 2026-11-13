"""Smoke test ghi/đọc vận đơn trên ERPNext development localhost.

Chỉ chạy khi có ``--apply``. Script tái dùng một Sales Order Draft mang
``po_no=DEV02-SHIPPING-SMOKE`` nên chạy lại không tạo chứng từ trùng.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timezone
from urllib.parse import urlparse

from agent.erp.erpnext import NguonErpNext
from agent.erp.hop_dong import DongDon


async def run(apply: bool) -> int:
    nguon = NguonErpNext()
    host = (urlparse(nguon._goc).hostname or "").lower()
    if not apply:
        print("Chỉ kiểm tra cấu hình. Thêm --apply để chạy smoke test localhost.")
        return 1
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print("Từ chối ghi: smoke test chỉ cho phép ERPNext localhost.")
        return 2

    khoa = "DEV02-SHIPPING-SMOKE"
    erp_ma_don = await nguon.tim_don(khoa)
    if not erp_ma_don:
        customers = await nguon._lay("Customer", [], ["name"])
        items = await nguon._lay(
            "Item", [["disabled", "=", 0], ["is_sales_item", "=", 1]],
            ["item_code"],
        )
        if not customers or not items:
            print("ERP development thiếu Customer hoặc Item để dựng Sales Order Draft.")
            return 2
        result = await nguon.tao_don(
            khoa,
            str(customers[0]["name"]),
            [DongDon(ma=str(items[0]["item_code"]), so_luong=1, don_gia=1)],
            ghi_chu=f"DEV-02 integration smoke {date.today().isoformat()}",
        )
        if not result.thanh_cong or not result.erp_ma_don:
            print(f"Không tạo được Sales Order Draft: {result.ly_do}")
            return 2
        erp_ma_don = result.erp_ma_don

    now = datetime.now(timezone.utc).replace(microsecond=0)
    await nguon.dong_bo_van_don(
        erp_ma_don=erp_ma_don,
        ma_van_don="GHN-DEV02-SMOKE",
        don_vi="ghn",
        trang_thai="delivering",
        dong_bo_luc=now,
        tham_chieu=khoa,
    )
    # Lần hai phải chỉ GET, chứng minh lost-response/retry không PUT trùng.
    second_write = await nguon.dong_bo_van_don(
        erp_ma_don=erp_ma_don,
        ma_van_don="GHN-DEV02-SMOKE",
        don_vi="ghn",
        trang_thai="delivering",
        dong_bo_luc=now,
        tham_chieu=khoa,
    )
    doc = await nguon.doc_van_don(erp_ma_don)
    ok = (
        doc.get("custom_shipping_tracking_number") == "GHN-DEV02-SMOKE"
        and doc.get("custom_shipping_reference") == khoa
        and second_write is False
    )
    print(f"{'PASS' if ok else 'FAIL'}: {erp_ma_don}; idempotent={not second_write}")
    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
