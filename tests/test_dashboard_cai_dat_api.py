"""
Panel Cài đặt API: ô bí mật không bao giờ mang giá trị, có Kiểm tra và Lưu.
Kiểm bằng đọc mã (regex), cùng cách với tests/test_dashboard_khong_nhap_nhay.py.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _than_ham(ten: str) -> str:
    m = re.search(rf"(?:async )?function {ten}\(.*?\n\}}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}"
    return m.group(0)


def test_panel_nam_trong_man_cau_hinh():
    assert 'id="api-panel"' in HTML
    assert HTML.index('id="api-panel"') > HTML.index('data-view="cauhinh"')
    assert HTML.index('id="api-panel"') < HTML.index('id="cauhinh-ds"')


def test_o_bi_mat_la_password_va_khong_co_value():
    than = _than_ham("oNhapApi")
    the_password = re.search(r'<input type="password"[^>]*>', than, re.S)
    assert the_password, "ô bí mật phải là input type=password"
    # Không dựng thuộc tính value cho ô bí mật: giá trị không có ở client để mà dựng.
    assert "value=" not in the_password.group(0)
    assert 'autocomplete="off"' in the_password.group(0)


def test_co_nut_kiem_tra_va_luu_theo_nhom():
    than = _than_ham("loadCaiDatApi")
    assert "data-api-kiem" in than and "data-api-luu" in than


def test_kiem_tra_gui_gia_tri_dang_go_chua_luu():
    # Kiểm phải gửi thứ đang gõ (giaTriApiDangGo), không gửi cấu hình đã lưu.
    assert re.search(r"/cai-dat-api/kiem-tra[\s\S]{0,300}giaTriApiDangGo\(", JS)


def test_loader_goi_khi_mo_man_cau_hinh():
    assert re.search(r'state\.view === "cauhinh"[\s\S]{0,120}loadCaiDatApi\(\)', JS)


def test_khong_tu_kiem_khi_mo_trang():
    """Mỗi lần kiểm là một lượt gọi tốn tiền; chỉ chạy khi người bấm."""
    than = _than_ham("loadCaiDatApi")
    assert "kiem-tra" not in than
