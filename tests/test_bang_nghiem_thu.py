"""
`docs/nghiem-thu.md` phải khớp bộ nghiệm thu — không được cũ, không được viết tay.

Bảng ấy do `scripts/sinh_nghiem_thu.py` sinh từ kết quả chạy thật. Kiểm ở
đây KHÔNG chạy lại nghiệm thu (cần Postgres, một phút) — chỉ kiểm cấu trúc:
mọi kịch bản trong file test đều có mặt trong bảng, và bảng mang dấu "sinh
tự động". Thêm một kịch bản mà quên sinh lại bảng thì test này đỏ.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOC = ROOT / "docs" / "nghiem-thu.md"
TEST = ROOT / "tests" / "test_nghiem_thu_saas.py"


def _ten_kich_ban() -> list[str]:
    return re.findall(r"^def (test_\d+_\w+)\(", TEST.read_text(encoding="utf-8"), re.M)


def test_bang_ton_tai_va_la_ban_sinh():
    assert DOC.exists(), "chưa có docs/nghiem-thu.md — chạy scripts.sinh_nghiem_thu --ghi"
    assert "SINH TỰ ĐỘNG" in DOC.read_text(encoding="utf-8")


def test_moi_kich_ban_deu_co_trong_bang():
    noi_dung = DOC.read_text(encoding="utf-8")
    thieu = [t for t in _ten_kich_ban() if f"`{t}`" not in noi_dung]
    assert not thieu, (
        "kịch bản chưa vào bảng nghiệm thu — sinh lại bằng "
        f"scripts.sinh_nghiem_thu --ghi: {thieu}")
    assert len(_ten_kich_ban()) >= 10


def test_dung_markdown_thuan_khong_can_csdl():
    """Phần dựng markdown kiểm được mà không chạy nghiệm thu."""
    from scripts.sinh_nghiem_thu import dung_markdown

    md = dung_markdown([
        ("test_01_a", "Đăng nhập.\n\nBƯỚC 1  Mở trang.\nBƯỚC 2  Gõ.", "đạt"),
        ("test_02_b", "Khoá.\n\nBƯỚC 1  Bấm.", "KHÔNG ĐẠT"),
    ])
    assert "1/2 kịch bản đạt" in md
    assert "| 1 | Đăng nhập | đạt |" in md
    assert "**KHÔNG ĐẠT**" in md
    assert "1. Mở trang." in md and "2. Gõ." in md
