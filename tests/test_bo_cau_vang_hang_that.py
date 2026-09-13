"""
Bộ sinh câu vàng phải dựng được từ DANH MỤC THẬT — không chỉ từ bản mẫu.

LỖI ĐÃ XẢY RA (13.09.2026)
--------------------------
Nhóm "công cụ" gõ cứng tám mã sản phẩm của `catalog.example.json`
(`AS-SR01`…). Danh mục thật của shop có 13 mã, không mã nào là `AS-*`, nên
`python -m scripts.sinh_bo_cau_vang` nổ `KeyError: 'AS-SR01'` và shop không
dựng được bộ câu vàng của mình. Eval khi ấy lặng lẽ chạy trên bộ cũ từ
27.08 — số đo về một danh mục không còn tồn tại.

CLAUDE.md: mã đọc dữ liệu không đi theo repo phải có đường lui. Ở đây đường
lui là: mã mẫu có trong danh mục thì dùng câu hỏi mẫu (để bản mẫu commit
không đổi một byte), không có thì dựng câu hỏi giá từ chính hàng của shop.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _chay_bo_sinh(tmp_path: Path, san_pham: list[dict]) -> list[dict]:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"san_pham": san_pham}, ensure_ascii=False),
                       encoding="utf-8")
    dich = tmp_path / "golden.jsonl"
    kq = subprocess.run(
        [sys.executable, "-m", "scripts.sinh_bo_cau_vang"],
        # `encoding` nói rõ: Windows mặc định giải mã stdout con bằng cp1258
        # và nổ ở ký tự có dấu đầu tiên — không phải lỗi của bộ sinh.
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONUTF8": "1",
             "BO_CAU_VANG_CATALOG": str(catalog), "BO_CAU_VANG_DICH": str(dich)},
    )
    assert kq.returncode == 0, kq.stderr[-800:]
    return [json.loads(d) for d in dich.read_text(encoding="utf-8").splitlines() if d.strip()]


def _hang_that():
    """Danh mục KHÔNG có mã AS-* — đúng hình dạng hàng của shop."""
    return [
        {"ma": "BLA-BODY-WAX-120G", "ten": "Kem Tẩy Lông BLANICA 120g",
         "gia": 290000, "ton_kho": 12},
        {"ma": "BLA-FACE-CLEAN-120G", "ten": "Sữa Rửa Mặt BLANICA Jeju 120g",
         "gia": 190000, "ton_kho": 0},
        {"ma": "BLA-FACE-SCRUB-120G", "ten": "Tẩy Tế Bào Chết BLANICA Honey",
         "gia": 1150000, "ton_kho": 3},
    ]


def test_danh_muc_that_khong_co_ma_mau_van_dung_duoc(tmp_path):
    ca = _chay_bo_sinh(tmp_path, _hang_that())
    cong_cu = [c for c in ca if c["nhom"] == "cong_cu"]
    assert cong_cu, "nhóm công cụ biến mất"
    # Câu hỏi giá phải nhắc ĐÚNG tên hàng thật và đòi ĐÚNG giá viết kiểu VN.
    hoi = " ".join(c["hoi"] for c in cong_cu)
    assert "BLANICA" in hoi
    phai_co = [p for c in cong_cu for p in c["phai_co"]]
    assert "1.150.000" in phai_co and "290.000" in phai_co
    # Không còn dấu vết hàng mẫu.
    assert "Aurora" not in json.dumps(ca, ensure_ascii=False)


def test_ca_het_hang_chi_sinh_khi_that_su_het(tmp_path):
    """
    Ca "còn hàng không?" mong agent nói HẾT. Đặt ca ấy cho món còn hàng là
    bộ đo chấm agent sai trong khi agent nói đúng — loại lỗi tệ nhất của
    một bộ đo. Chỉ món `ton_kho == 0` mới thành ca hết hàng.
    """
    ca = _chay_bo_sinh(tmp_path, _hang_that())
    het = [c for c in ca if c["nhom"] == "cong_cu" and "còn hàng" in c["hoi"]]
    assert len(het) == 1
    assert "Sữa Rửa Mặt" in het[0]["hoi"]


def test_khong_mon_nao_het_thi_bo_ca_het_hang_chu_khong_bia(tmp_path):
    sp = [dict(s, ton_kho=5) for s in _hang_that()]
    ca = _chay_bo_sinh(tmp_path, sp)
    assert not [c for c in ca if "còn hàng" in c["hoi"]]


def test_cac_nhom_khac_van_du(tmp_path):
    ca = _chay_bo_sinh(tmp_path, _hang_that())
    assert {c["nhom"] for c in ca} == {"tuan_thu", "tri_thuc", "cong_cu", "ban_hang"}
    assert sum(1 for c in ca if c["nhom"] == "tuan_thu") >= 20
