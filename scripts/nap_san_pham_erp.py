"""
Nạp danh mục sản phẩm từ `data/catalog.json` lên ERPNext.

    python -m scripts.nap_san_pham_erp --thu      xem sẽ làm gì, KHÔNG ghi
    python -m scripts.nap_san_pham_erp            ghi thật lên ERPNext

Chỉ đẩy NỬA THƯƠNG MẠI lên ERP: mã, tên, nhóm hàng, giá, dung tích. Nửa tư
vấn — loại da phù hợp, thành phần, cách dùng — ở lại `catalog.json`, đúng
như `agent/erp/ho_so.py` giải thích: chín trường ấy không tồn tại bên ERP,
và để chúng ở ngoài thì đổi ERP không mất gì.

VÌ SAO CÓ `--thu` VÀ VÌ SAO NÓ LÀ MẶC ĐỊNH AN TOÀN
--------------------------------------------------
Script này GHI vào sổ cái của doanh nghiệp. Chạy nhầm trên ERP thật với
danh mục mẫu là đưa hàng không có thật vào hệ thống bán hàng — rồi ai đó
lên đơn từ đó.

VÌ SAO CHẶN DỮ LIỆU MẪU
-----------------------
`catalog.json` đi kèm repo mang cờ `du_lieu_mau: true`. Đẩy nó lên ERP thật
là bước đầu tiên của chuỗi dẫn tới quảng cáo sai sự thật, và cờ ấy tồn tại
đúng để chặn việc này (xem `scripts/san_sang.py`).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Console Windows mac dinh cp1258 khong in duoc tieng Viet.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

import httpx  # noqa: E402

from agent.config import settings  # noqa: E402

NHOM_GOC = "All Item Groups"


async def _kiem_xac_thuc(client: httpx.AsyncClient, goc: str) -> str | None:
    """Trả tên tài khoản nếu xác thực được, None nếu không."""
    try:
        r = await client.get(f"{goc}/api/method/frappe.auth.get_logged_user")
    except httpx.HTTPError as exc:
        print(f"[LỖI] Không nối được tới {goc}: {type(exc).__name__}: {exc}")
        return None
    if r.status_code != 200:
        print(f"[LỖI] ERPNext từ chối xác thực ({r.status_code}): {r.text[:200]}")
        return None
    return str(r.json().get("message") or "")


async def _bao_dam_nhom(
    client: httpx.AsyncClient, goc: str, ten_nhom: str, da_co: set[str]
) -> bool:
    """
    Tạo nhóm hàng nếu chưa có. Trả False nếu không tạo được.

    VÌ SAO KHÔNG `except Exception: pass` NHƯ BẢN TRƯỚC
    ---------------------------------------------------
    Nuốt lỗi ở đây thì mọi sản phẩm thuộc nhóm đó sẽ thất bại ở bước sau
    với một thông báo khó hiểu từ ERPNext, và người chạy đi tìm nguyên nhân
    ở chỗ khác. Nhóm hàng hỏng là một câu trả lời, không phải im lặng.
    """
    if ten_nhom in da_co:
        return True
    try:
        r = await client.get(f"{goc}/api/resource/Item Group/{ten_nhom}")
        if r.status_code == 200:
            da_co.add(ten_nhom)
            return True
        r = await client.post(
            f"{goc}/api/resource/Item Group",
            json={
                "item_group_name": ten_nhom,
                "parent_item_group": NHOM_GOC,
                "is_group": 0,
            },
        )
    except httpx.HTTPError as exc:
        print(f"  [LỖI] nhóm hàng {ten_nhom!r}: {type(exc).__name__}: {exc}")
        return False
    if r.status_code in (200, 201):
        da_co.add(ten_nhom)
        print(f"  [nhóm] tạo mới {ten_nhom!r}")
        return True
    print(f"  [LỖI] không tạo được nhóm {ten_nhom!r}: "
          f"{r.status_code} {r.text[:150]}")
    return False


def _payload(sp: dict) -> dict:
    return {
        "item_code": sp.get("ma"),
        "item_name": sp.get("ten"),
        "item_group": str(sp.get("loai") or "").strip() or "Mỹ phẩm",
        "stock_uom": "Unit",
        "is_stock_item": 1,
        "standard_rate": sp.get("gia") or 0,
        "description": (
            f"{sp.get('ten', '')} — dung tích {sp.get('dung_tich', '')}"
        ).strip(" —"),
    }


async def _day_mot(
    client: httpx.AsyncClient, goc: str, sp: dict
) -> tuple[str, str]:
    """Trả `(ket_qua, ghi_chu)` với ket_qua thuộc {tao, cap_nhat, hong}."""
    ma = sp.get("ma")
    body = _payload(sp)
    try:
        co = await client.get(f"{goc}/api/resource/Item/{ma}")
        if co.status_code == 200:
            r = await client.put(
                f"{goc}/api/resource/Item/{ma}",
                json={
                    "item_name": body["item_name"],
                    "standard_rate": body["standard_rate"],
                    "description": body["description"],
                },
            )
            # Bản trước KHÔNG báo gì khi cập nhật hỏng — sản phẩm lặng lẽ
            # giữ giá cũ, và bản tổng kết vẫn đếm là xong.
            if r.status_code in (200, 201):
                return "cap_nhat", ""
            return "hong", f"cập nhật {r.status_code}: {r.text[:150]}"

        r = await client.post(f"{goc}/api/resource/Item", json=body)
        if r.status_code in (200, 201):
            return "tao", ""
        return "hong", f"tạo mới {r.status_code}: {r.text[:150]}"
    except httpx.HTTPError as exc:
        return "hong", f"{type(exc).__name__}: {exc}"


async def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Nạp danh mục lên ERPNext")
    p.add_argument("--thu", action="store_true",
                   help="chỉ in ra sẽ làm gì, KHÔNG ghi lên ERP")
    p.add_argument("--du-lieu-mau", action="store_true", dest="du_lieu_mau",
                   help="cho phép đẩy cả danh mục còn cờ dữ liệu mẫu")
    a = p.parse_args(argv)

    duong_dan = GOC / "data" / "catalog.json"
    if not duong_dan.exists():
        print(f"[LỖI] Không thấy {duong_dan}")
        return 1
    catalog = json.loads(duong_dan.read_text(encoding="utf-8"))
    san_pham = catalog.get("san_pham", [])
    if not san_pham:
        print("[LỖI] catalog.json không có sản phẩm nào.")
        return 1

    if catalog.get("du_lieu_mau") is True and not a.du_lieu_mau:
        print(
            "[CHẶN] catalog.json vẫn mang cờ du_lieu_mau: true.\n"
            "       Đẩy danh mục mẫu lên ERP thật là đưa hàng không có thật\n"
            "       vào hệ thống bán hàng. Thay bằng danh mục thật rồi bỏ cờ,\n"
            "       hoặc thêm --du-lieu-mau nếu đang cố ý thử trên ERP nháp."
        )
        return 1

    goc = (settings.erpnext_url or "").rstrip("/")

    # CHẾ ĐỘ THỬ THOÁT TRƯỚC KHI ĐÒI THÔNG TIN ĐĂNG NHẬP.
    #
    # `--thu` không kết nối đi đâu cả, nên bắt phải có API key mới xem được
    # payload là chặn đúng lúc người ta cần xem nhất: TRƯỚC khi dựng ERP.
    if a.thu:
        print(f"Danh mục: {len(san_pham)} sản phẩm · CHẾ ĐỘ THỬ, không ghi gì"
              + (f" · đích: {goc}" if goc else ""))
        for sp in san_pham:
            b = _payload(sp)
            print(f"  [thử] {b['item_code']:<10} {b['item_name']} "
                  f"· nhóm {b['item_group']} · {b['standard_rate']:,}đ")
        print("\nChế độ thử — chưa ghi gì lên ERP. Bỏ --thu để chạy thật.")
        return 0

    khoa = settings.erpnext_api_key
    bi_mat = settings.erpnext_api_secret
    thieu = [
        ten for ten, gt in (
            ("ERPNEXT_URL", goc), ("ERPNEXT_API_KEY", khoa),
            ("ERPNEXT_API_SECRET", bi_mat),
        ) if not str(gt or "").strip()
    ]
    if thieu:
        print("[LỖI] Thiếu cấu hình trong .env: " + ", ".join(thieu))
        print("      Xem docs/huong-dan-thiet-lap-erp.md, bước 3 và 4.")
        return 1

    print(f"Danh mục: {len(san_pham)} sản phẩm · ERPNext: {goc}")

    headers = {
        "Authorization": f"token {khoa}:{bi_mat}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
        tai_khoan = await _kiem_xac_thuc(client, goc)
        if tai_khoan is None:
            return 1
        print(f"Đã xác thực với ERPNext, tài khoản: {tai_khoan}\n")

        da_co_nhom: set[str] = set()
        dem = {"tao": 0, "cap_nhat": 0, "hong": 0}
        hong: list[str] = []

        for sp in san_pham:
            ma = sp.get("ma")
            nhom = _payload(sp)["item_group"]
            if not await _bao_dam_nhom(client, goc, nhom, da_co_nhom):
                dem["hong"] += 1
                hong.append(f"{ma}: không tạo được nhóm {nhom!r}")
                continue

            ket_qua, ghi_chu = await _day_mot(client, goc, sp)
            dem[ket_qua] += 1
            nhan = {"tao": "tạo mới", "cap_nhat": "cập nhật",
                    "hong": "HỎNG"}[ket_qua]
            print(f"  [{nhan}] {ma} — {sp.get('ten')}"
                  + (f"  ← {ghi_chu}" if ghi_chu else ""))
            if ket_qua == "hong":
                hong.append(f"{ma}: {ghi_chu}")

    print(f"\nTạo mới {dem['tao']} · cập nhật {dem['cap_nhat']} · "
          f"hỏng {dem['hong']} / tổng {len(san_pham)}")
    if hong:
        # Thoát khác 0 để CI hoặc người chạy KHÔNG coi là xong. Bản trước in
        # dòng "Hoàn tất!" kể cả khi một nửa danh mục thất bại.
        print("\nCác mã chưa lên được ERP:")
        for d in hong:
            print(f"  · {d}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
