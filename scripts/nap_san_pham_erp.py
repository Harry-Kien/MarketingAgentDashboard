"""
Script tự động nạp danh mục sản phẩm BLANICA từ data/catalog.json lên NextERP/ERPNext.

Cách dùng:
    python scripts/nap_san_pham_erp.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# Thêm thư mục gốc vào sys.path
GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

import httpx
from agent.config import settings


async def main():
    catalog_path = GOC / "data" / "catalog.json"
    if not catalog_path.exists():
        print(f"❌ Không tìm thấy file {catalog_path}")
        return

    with open(catalog_path, encoding="utf-8") as f:
        catalog = json.load(f)

    san_phams = catalog.get("san_pham", [])
    print(f"📦 Tìm thấy {len(san_phams)} sản phẩm trong catalog.")

    base_url = settings.nexterp_base_url.rstrip("/")
    api_key = settings.nexterp_api_key
    api_secret = settings.nexterp_api_secret

    if not api_key or not api_secret:
        print("⚠️ Chưa cấu hình NEXTERP_API_KEY hoặc NEXTERP_API_SECRET trong .env!")
        print("   Vui lòng tạo API Key trong NextERP (User: Administrator -> API Access) và dán vào .env.")
        return

    headers = {
        "Authorization": f"token {api_key}:{api_secret}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        # Kiểm tra kết nối
        try:
            r = await client.get(f"{base_url}/api/method/frappe.auth.get_logged_user", headers=headers)
            if r.status_code != 200:
                print(f"❌ Không thể xác thực với NextERP ({r.status_code}): {r.text}")
                return
            user = r.json().get("message")
            print(f"✅ Đã kết nối NextERP thành công với tài khoản: {user}")
        except Exception as e:
            print(f"❌ Lỗi kết nối tới {base_url}: {e}")
            return

        # Nạp Item Group mặc định nếu chưa có
        try:
            await client.post(
                f"{base_url}/api/resource/Item Group",
                headers=headers,
                json={"item_group_name": "Mỹ phẩm", "parent_item_group": "All Item Groups", "is_group": 0},
            )
        except Exception:
            pass

        # Nạp từng sản phẩm
        success_count = 0
        for sp in san_phams:
            ma = sp.get("ma")
            ten = sp.get("ten")
            gia = sp.get("gia", 0)
            loai = sp.get("loai", "Mỹ phẩm")
            
            payload = {
                "item_code": ma,
                "item_name": ten,
                "item_group": "Mỹ phẩm",
                "stock_uom": "Unit",
                "is_stock_item": 1,
                "standard_rate": gia,
                "description": f"{ten} - Dung tích: {sp.get('dung_tich', '')}",
            }

            # Kiểm tra xem sản phẩm đã có chưa
            r_check = await client.get(f"{base_url}/api/resource/Item/{ma}", headers=headers)
            if r_check.status_code == 200:
                # Cập nhật giá
                r_update = await client.put(f"{base_url}/api/resource/Item/{ma}", headers=headers, json={"standard_rate": gia, "item_name": ten})
                if r_update.status_code in (200, 201):
                    print(f"  🔄 Cập nhật: {ma} - {ten} ({gia:,}đ)")
                    success_count += 1
            else:
                # Tạo mới
                r_create = await client.post(f"{base_url}/api/resource/Item", headers=headers, json=payload)
                if r_create.status_code in (200, 201):
                    print(f"  ✨ Tạo mới: {ma} - {ten} ({gia:,}đ)")
                    success_count += 1
                else:
                    print(f"  ⚠️ Thất bại ({ma}): {r_create.status_code} - {r_create.text[:100]}")

    print(f"\n🎉 Hoàn tất! Đã đồng bộ {success_count}/{len(san_phams)} sản phẩm lên NextERP.")


if __name__ == "__main__":
    asyncio.run(main())
