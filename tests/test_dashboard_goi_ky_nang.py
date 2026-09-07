from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _than_ham(ten):
    m = re.search(r"(?:async )?function " + ten + r"\(.*?\n\}\n", JS, re.S)
    assert m, ten
    return m.group(0)


def test_panel_va_form_co_mat():
    assert 'id="goi-ds"' in HTML and 'id="goiform"' in HTML and 'id="goi-tep"' in HTML
    assert 'id="goi-kiem"' in HTML and 'id="goi-cai"' in HTML


def test_goi_dung_api():
    src = _than_ham("loadGoiKyNang")
    assert "/goi-ky-nang" in src and "esc(" in src
    for f in ("g.ten", "g.phien_ban", "g.mo_ta"):
        assert f"${{{f}}}" not in src, f
    cai = _than_ham("caiGoiKyNang")
    assert "/goi-ky-nang/kiem" in cai and "FormData" in cai and '"/goi-ky-nang/tep"' in cai


def test_cot_so_lan_goi_o_ky_nang_viet_san():
    src = _than_ham("loadKyNang")
    assert "so_lan_7_ngay" in src and "loadGoiKyNang()" in src


def test_xuat_lich_su_khoi_phuc_co_nut():
    src = _than_ham("loadGoiKyNang")
    assert "data-goi-xuat" in src and "data-goi-lichsu" in src and "data-goi-battat" in src and "data-goi-xoa" in src
    assert "data-goi-khoiphuc" in JS
