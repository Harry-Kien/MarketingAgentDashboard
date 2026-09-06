"""Màn Phòng thử: có, gọi đúng API, esc mọi chuỗi máy chủ, không tự tải lại."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _than_ham(ten: str) -> str:
    m = re.search(r"(?:async )?function " + ten + r"\(.*?\n\}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}"
    return m.group(0)


def test_rail_va_view_co_mat():
    assert 'data-view="phongthu"' in HTML
    assert HTML.count('data-view="phongthu"') >= 2  # nút rail + section


def test_goi_dung_api():
    src = _than_ham("hoiPhongThu")
    assert "/phong-thu/phien/" in src and "/hoi" in src and "method: \"POST\"" in src
    assert "ky_vong" in src


def test_ve_ben_trong_qua_esc():
    src = _than_ham("veBenTrongPhongThu")
    for ten in ("tra_loi", "escalate_reason", "nhan_luoi", "model", "sources"):
        assert f"${{{ten}" not in src and f"${{d.{ten}" not in src, ten
    assert "esc(" in src and 'class="pre"' in src
    assert "JSON.stringify" in src and "esc(JSON.stringify" in src


def test_khong_tu_tai_lai_theo_vong_refresh():
    src = _than_ham("refresh")
    assert "phongthu" in src
    assert "loadPhongThu()" in src and "state.phongThuDaTai" in src


def test_goi_y_dien_cau_va_ky_vong():
    assert "data-goiy" in JS and "phongThuKyVong" in JS


def test_an_toan_nhap_lieu():
    src = _than_ham("hoiPhongThu")
    assert ".trim()" in src
