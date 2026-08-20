"""
Sinh ảnh cho sản phẩm trong catalog và lưu vào kho.

    python -m scripts.sinh_anh_sanpham                 # xem kho đang có gì
    python -m scripts.sinh_anh_sanpham AS-SR01         # sinh cho một mã
    python -m scripts.sinh_anh_sanpham --tat-ca        # sinh cho mọi sản phẩm
    python -m scripts.sinh_anh_sanpham --tat-ca --so-anh 2

Mỗi ảnh mất khoảng 90-100 giây. Cả catalog 22 sản phẩm x 3 ảnh là hơn một
tiếng — nên mặc định script CHỈ LIỆT KÊ, phải nói rõ mã hoặc `--tat-ca` mới
thật sự gọi model. Sản phẩm đã có ảnh thì bỏ qua, trừ khi thêm `--lam-lai`.

Ảnh sinh ra KHÔNG phải ảnh chụp sản phẩm thật — xem ghi chú trong
agent/video/catalog_images.py trước khi dùng cho việc bán hàng.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import ROOT                       # noqa: E402
from agent.video import catalog_images as kho       # noqa: E402

CATALOG = ROOT / "data" / "catalog.json"


def doc_catalog() -> list[dict]:
    if not CATALOG.exists():
        return []
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    return data.get("san_pham", [])


def liet_ke(items: list[dict]) -> None:
    co, chua = [], []
    for sp in items:
        (co if kho.anh_cua(sp.get("ma", "")) else chua).append(sp)

    print(f"Kho ảnh: {len(co)}/{len(items)} sản phẩm đã có ảnh\n")
    if co:
        print("Đã có:")
        for sp in co:
            n = len(kho.anh_cua(sp["ma"]))
            nguon = kho.manifest_cua(sp["ma"]).get("nguon", "?")
            print(f"  {sp['ma']:10s} {n} ảnh ({nguon})  {sp['ten'][:48]}")
    if chua:
        print("\nChưa có ảnh:")
        for sp in chua:
            print(f"  {sp['ma']:10s} {sp['ten'][:60]}")
        print(f"\nSinh cho một mã:  python -m scripts.sinh_anh_sanpham {chua[0]['ma']}")
        print("Sinh cho tất cả:  python -m scripts.sinh_anh_sanpham --tat-ca")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ma", nargs="*", help="Mã sản phẩm cần sinh ảnh")
    ap.add_argument("--tat-ca", action="store_true")
    ap.add_argument("--lam-lai", action="store_true", help="Sinh lại cả mã đã có ảnh")
    ap.add_argument("--so-anh", type=int, default=3)
    args = ap.parse_args()

    items = doc_catalog()
    if not items:
        print(f"Không đọc được sản phẩm nào từ {CATALOG}")
        return 1

    if not args.ma and not args.tat_ca:
        liet_ke(items)
        return 0

    can = {m.strip().upper() for m in args.ma}
    chon = [
        sp for sp in items
        if (args.tat_ca or sp.get("ma", "").upper() in can)
        and (args.lam_lai or not kho.anh_cua(sp.get("ma", "")))
    ]

    if not chon:
        print("Không có sản phẩm nào cần sinh ảnh. Thêm --lam-lai để sinh đè.")
        return 0

    uoc = len(chon) * args.so_anh * 95
    print(f"Sẽ sinh ảnh cho {len(chon)} sản phẩm x {args.so_anh} ảnh")
    print(f"Ước tính khoảng {uoc // 60} phút. Bắt đầu...\n")

    t0 = time.time()
    tong = 0
    for i, sp in enumerate(chon, 1):
        t1 = time.time()
        n, warns = await kho.sinh_cho_san_pham(sp, so_anh=args.so_anh)
        tong += n
        trang_thai = f"{n} ảnh" if n else "THẤT BẠI"
        print(f"[{i}/{len(chon)}] {sp['ma']:10s} {trang_thai:10s} "
              f"{time.time() - t1:5.0f}s  {sp['ten'][:40]}")
        for w in warns:
            print(f"           {w}")

    print(f"\nXong: {tong} ảnh, {(time.time() - t0) / 60:.1f} phút")
    print(f"Kho: {kho.KHO}")
    print("\nẢnh do model sinh, KHÔNG phải ảnh chụp thật.")
    print("Thay bằng ảnh chụp sản phẩm thật trước khi dùng để bán hàng.")
    return 0 if tong else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
