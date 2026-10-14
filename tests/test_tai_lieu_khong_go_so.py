"""
Số lần chạy eval và số test KHÔNG được gõ tay ngoài tài liệu sinh tự động.

Đợt rà 14.10.2026 tìm ra ba con số mâu thuẫn, cả ba đều gõ tay:

- `co-so-ly-thuyet.md` và `dua-vao-doanh-nghiep.md` ghi "13 lần chạy";
  `thuc-nghiem.md` — sinh từ dữ liệu — ghi 4. Không có lần thứ năm nào.
- `README.md` ghi "732 test pass" khi bộ test đã hơn ba nghìn ca.
- `co-so-ly-thuyet.md` ghi "tám công cụ kia" khi có mười một công cụ.

Con số thật đã có chỗ ở: `thuc-nghiem.md` (sinh ra) và kết quả `pytest`.
Văn xuôi chỉ được trỏ sang đó.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIET_TAY = ["README.md", "docs/co-so-ly-thuyet.md", "docs/dua-vao-doanh-nghiep.md"]


def _doc(f: str) -> str:
    return (ROOT / f).read_text(encoding="utf-8")


def test_khong_go_so_lan_chay():
    for f in VIET_TAY:
        assert not re.search(r"\b\d+ lần chạy", _doc(f)), f


def test_khong_go_so_test():
    for f in VIET_TAY:
        assert not re.search(r"\b\d{3,} test (pass|đạt|xanh)", _doc(f)), f


def test_khong_go_so_cong_cu():
    so = r"(một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|\d+)"
    for f in VIET_TAY:
        assert not re.search(rf"\b{so} công cụ (kia|còn lại)", _doc(f)), f


def test_tai_lieu_tham_khao_khong_con_ghi_chu_chua_xu_ly():
    """Ghi chú "tự kiểm tra lại" nộp nguyên trạng là tự nhận chưa kiểm."""
    assert "tự kiểm tra lại thông tin xuất" not in _doc("docs/co-so-ly-thuyet.md")


def test_moi_tai_lieu_tham_khao_tra_lai_duoc():
    """Mỗi mục có DOI, arXiv hoặc URL — hội đồng phải tra lại được."""
    md = _doc("docs/co-so-ly-thuyet.md")
    muc = md.split("## Tài liệu tham khảo", 1)[1].split("\n---", 1)[0]
    cac_muc = re.split(r"\n(?=\[\d+\])", muc.strip())
    cac_muc = [m for m in cac_muc if m.startswith("[")]
    assert len(cac_muc) >= 9
    for m in cac_muc:
        assert re.search(r"doi:|arXiv:|https?://", m), m[:80]
