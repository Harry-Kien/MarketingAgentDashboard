"""
Tài liệu triển khai SaaS không được trỏ tới thứ không tồn tại.

Người đọc tài liệu này đang đứng trước một máy chủ trống. Một lệnh sai tên,
một đường dẫn đã đổi là họ kẹt giữa chừng — và tệ nhất là kẹt ở bước sao lưu
hay khôi phục, đúng lúc không còn đường lui.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MD = (ROOT / "docs" / "trien-khai-saas.md").read_text(encoding="utf-8")


def test_moi_duong_dan_ton_tai():
    sinh_ra = {"trien_khai/.env.nen", "trien_khai/sao_luu/",
               "trien_khai/cua_hang/shopa/quan_tri_lan_dau.txt"}
    thieu = [d for d in set(re.findall(r"`((?:agent|docs|scripts|trien_khai|connectors)/[\w./-]+)`", MD))
             if d not in sinh_ra and not (ROOT / d).exists()]
    assert not thieu, thieu


def test_moi_lenh_cua_hang_deu_co_that():
    """Lệnh con lấy từ CHÍNH mã nguồn script, không gõ lại danh sách."""
    src = (ROOT / "scripts" / "cua_hang.py").read_text(encoding="utf-8")
    co = set(re.findall(r'add_parser\("(\w+)"\)', src))
    co |= {x.strip().strip('"') for x in re.search(r"for ten in \(([^)]*)\)", src).group(1).split(",")}
    dung = set(re.findall(r"scripts\.cua_hang (\w+)", MD)) | set(re.findall(r"`(\w+) shopa`", MD))
    assert dung <= co, dung - co


def test_noi_ro_gioi_han_va_sao_luu_ngoai_may():
    for y in ("Một bản app mỗi cửa hàng", "NGOÀI máy chủ", "Zalo cá nhân", "App Review"):
        assert y in MD, y
