"""
Sinh tài liệu hướng dẫn dùng từng sản phẩm TỪ CATALOG.

    python -m scripts.sinh_tai_lieu_san_pham

VÌ SAO SINH RA CHỨ KHÔNG VIẾT TAY
---------------------------------
Giá, dung tích, pH, thành phần, cách dùng đã nằm trong `data/catalog.json`.
Chép tay sang tài liệu là tạo ra nguồn thứ hai — và hai nguồn thì sớm muộn
lệch nhau. Khi đó agent tra tài liệu ra một giá, gọi công cụ ra giá khác,
và khách nhận số sai.

Sinh ra thì mỗi lần đổi danh mục chỉ cần chạy lại một lệnh:

    python -m scripts.sinh_tai_lieu_san_pham && python -m scripts.ingest

CỐ Ý KHÔNG ĐƯA GIÁ VÀO TÀI LIỆU
-------------------------------
Giá và tồn kho phải đến từ `tra_cuu_san_pham` — dữ liệu sống. Đưa giá vào
tài liệu RAG là mời agent đọc một con số có thể đã cũ. Tài liệu này chỉ
chứa thứ ÍT ĐỔI: cách dùng, thời điểm, thành phần, chống chỉ định.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "catalog.json"
RA = ROOT / "data" / "knowledge" / "huong-dan-dung-tung-san-pham.md"


def _muc(sp: dict) -> str:
    d = [f"## {sp['ten']} ({sp['ma']})", ""]
    d.append(f"Nhóm: {sp.get('loai', '—')} · Dung tích: {sp.get('dung_tich', '—')}")
    if sp.get("do_pH"):
        d.append(f"Độ pH: {sp['do_pH']}")
    if sp.get("so_cong_bo"):
        d.append(f"Số công bố: {sp['so_cong_bo']}")
    if sp.get("hsd_thang"):
        d.append(f"Hạn dùng sau mở nắp: {sp['hsd_thang']} tháng")
    d.append("")

    if sp.get("cach_dung"):
        d += ["**Cách dùng:** " + sp["cach_dung"], ""]
    if sp.get("thoi_diem"):
        d += ["**Dùng vào:** " + ", ".join(sp["thoi_diem"]), ""]
    if sp.get("da_phu_hop"):
        d += ["**Hợp với:** " + ", ".join(sp["da_phu_hop"]), ""]
    if sp.get("van_de_ho_tro"):
        d += ["**Hỗ trợ cho:** " + ", ".join(sp["van_de_ho_tro"]), ""]
    if sp.get("thanh_phan_chinh"):
        d += ["**Thành phần chính:** " + ", ".join(sp["thanh_phan_chinh"]), ""]
    if sp.get("khong_chua"):
        d += ["**Không chứa:** " + ", ".join(sp["khong_chua"]), ""]
    return "\n".join(d)


def main() -> int:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    sp = data.get("san_pham", [])
    if not sp:
        print("Danh mục rỗng.")
        return 1

    dau = [
        "# Hướng dẫn dùng từng sản phẩm Aurora Skin",
        "",
        "Tài liệu này được SINH RA từ `data/catalog.json`, không viết tay.",
        "Đổi danh mục thì chạy lại `python -m scripts.sinh_tai_lieu_san_pham`.",
        "",
        "Cố ý không có giá và tồn kho: hai thứ đó đến từ công cụ",
        "`tra_cuu_san_pham` để luôn là số mới nhất. Tài liệu chỉ giữ phần ít",
        "đổi — cách dùng, thời điểm, thành phần, độ pH.",
        "",
    ]

    theo_nhom: dict[str, list[dict]] = {}
    for p in sp:
        theo_nhom.setdefault(p.get("loai", "Khác"), []).append(p)

    than = []
    for nhom, ds in theo_nhom.items():
        than.append(f"# {nhom}\n")
        than += [_muc(p) for p in ds]

    RA.write_text("\n".join(dau + than), encoding="utf-8")
    tu = len(RA.read_text(encoding="utf-8").split())
    print(f"Đã sinh {RA.name}: {len(sp)} sản phẩm, {tu} từ, {len(theo_nhom)} nhóm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
