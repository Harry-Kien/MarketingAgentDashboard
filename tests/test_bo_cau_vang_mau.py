"""
Kiểm thử bộ câu vàng MẪU. Không gọi API, không cần CSDL.

VÌ SAO CÓ FILE MẪU, VÀ VÌ SAO PHẢI CANH NÓ
------------------------------------------
`data/eval/golden.jsonl` cố ý không lên repo (có thể chứa giá thật). Nhưng
`CLAUDE.md` dẫn tới nó, và `tests/test_claude_md.py` đòi mọi đường dẫn
trong đó phải có thật hoặc có bản `.example` — thiếu bản mẫu thì job
`clone-sach` đỏ, mà máy phát triển (luôn có bản thật) không tái hiện được.
Đã xảy ra thật: ba lần CI đỏ liên tiếp vì đúng một dòng trong CLAUDE.md.

Bản mẫu là file SINH RA (từ `catalog.example.json`, bằng cờ `--mau`). Sửa
bộ sinh mà quên sinh lại thì bản mẫu nói dối một cách lặng lẽ — đúng loại
lỗi mà `test_so_do.py` và `test_thuc_nghiem.py` canh cho tài liệu.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAU = ROOT / "data" / "eval" / "golden.example.jsonl"
CATALOG_MAU = ROOT / "data" / "catalog.example.json"


def _doc_mau() -> list[dict]:
    return [
        json.loads(d)
        for d in MAU.read_text(encoding="utf-8").splitlines()
        if d.strip()
    ]


def test_bo_mau_di_theo_repo_va_doc_duoc():
    """Thiếu file là clone sạch đỏ; file hỏng JSON thì `scripts.eval` chết
    ở dòng đầu, y như trước khi có bản mẫu."""
    assert MAU.exists(), "chạy: python -m scripts.sinh_bo_cau_vang --mau"
    ca = _doc_mau()
    assert len(ca) >= 50
    assert {c["nhom"] for c in ca} == {"tuan_thu", "tri_thuc", "cong_cu", "ban_hang"}


def test_bo_mau_khong_mang_gia_that():
    """
    Lý do duy nhất bộ thật bị chặn khỏi repo là giá thật. Bộ mẫu chỉ được
    nhắc tới sản phẩm và giá của `catalog.example.json` — tên sản phẩm thật
    lọt vào đây là dữ liệu kinh doanh đã lên GitHub.
    """
    catalog = json.loads(CATALOG_MAU.read_text(encoding="utf-8"))
    ten_mau = {s["ten"] for s in catalog["san_pham"]}
    that = ROOT / "data" / "catalog.json"
    if not that.exists():
        return  # máy vừa clone: không có bản thật để so
    ten_that = {s["ten"] for s in json.loads(that.read_text(encoding="utf-8"))["san_pham"]}
    chi_co_o_ban_that = ten_that - ten_mau
    noi_dung = MAU.read_text(encoding="utf-8")
    lot = sorted(t for t in chi_co_o_ban_that if t in noi_dung)
    assert not lot, f"tên hàng thật lọt vào bộ mẫu: {lot}"


def test_bo_mau_khop_bo_sinh():
    """
    Chạy lại bộ sinh với `--mau` phải cho ra ĐÚNG file đang commit.

    Chạy bằng tiến trình con vì bộ sinh ghi file ngay khi import; ghi xong
    thì trả file về nguyên trạng để test không để lại thay đổi trong cây
    làm việc — lệch thì báo lệnh sinh lại, không tự sửa hộ.
    """
    # So sau khi chuẩn hoá xuống dòng: `core.autocrlf=true` trên Windows
    # đưa CRLF vào bản làm việc, bộ sinh ghi LF — khác nhau đó không phải
    # "bản mẫu đã cũ".
    truoc = MAU.read_bytes()
    try:
        kq = subprocess.run(
            [sys.executable, "-m", "scripts.sinh_bo_cau_vang", "--mau"],
            cwd=ROOT, capture_output=True, text=True,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        assert kq.returncode == 0, kq.stdout + kq.stderr
        sau = MAU.read_bytes()
    finally:
        MAU.write_bytes(truoc)
    assert sau.replace(b"\r\n", b"\n") == truoc.replace(b"\r\n", b"\n"), (
        "golden.example.jsonl đã cũ so với bộ sinh — chạy: "
        "python -m scripts.sinh_bo_cau_vang --mau"
    )
