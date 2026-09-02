"""Nút "Mở" ở mục Kho/ERP phải đưa tới chỗ làm được việc.

LỖI ĐÃ GẶP
----------
Khi chưa nối ERP, mục này đặt `url` trỏ về chính dashboard. Người dùng bấm
"Mở" và trang quay về trang chính — không có gì xảy ra, không có lời giải
thích. Nhìn như nút hỏng.

Ghi chú lúc viết là "liên kết gãy còn tệ hơn không có liên kết". Đúng, nhưng
bỏ sót lựa chọn thứ ba, và nó mới là lựa chọn đúng: đưa người dùng tới MÀN
KHO, nơi có panel Kết nối kho/ERP và nút Thử kết nối.

Nút chỉ có nghĩa khi bấm xong người dùng ở gần việc hơn trước.

HAI TRẠNG THÁI, HAI ĐÍCH
------------------------
  chưa nối  -> nhảy sang màn Kho trong chính dashboard (để cấu hình)
  đã nối    -> mở ERP thật ở tab mới (để xem hàng, xem đơn)
"""
from __future__ import annotations

import re
from pathlib import Path

from agent import he_thong
from agent.config import settings

ROOT = Path(__file__).resolve().parent.parent


def test_chua_noi_thi_KHONG_tro_ve_chinh_dashboard(monkeypatch):
    monkeypatch.setattr(settings, "erp_loai", "tep")
    d = he_thong.muc_erp()
    assert "localhost:8000" not in (d.get("url") or ""), (
        "URL trỏ về chính dashboard — bấm Mở thì trang quay về trang chính, "
        "nhìn như nút hỏng."
    )


def test_chua_noi_thi_chi_duong_sang_man_kho(monkeypatch):
    monkeypatch.setattr(settings, "erp_loai", "tep")
    d = he_thong.muc_erp()
    assert d.get("di_toi_man") == "kho", (
        "Chưa nối ERP thì nút phải đưa sang màn Kho — nơi có panel Kết nối "
        "và nút Thử kết nối. Đó là chỗ duy nhất làm được việc."
    )


def test_da_noi_thi_mo_dung_erp_that(monkeypatch):
    monkeypatch.setattr(settings, "erp_loai", "erpnext")
    monkeypatch.setattr(settings, "erpnext_url", "https://erp.cua-hang.vn")
    d = he_thong.muc_erp()
    assert d["url"] == "https://erp.cua-hang.vn"
    assert not d.get("di_toi_man"), (
        "Đã nối rồi thì Mở phải sang ERP thật, không nhảy nội bộ nữa"
    )


def test_dashboard_biet_xu_ly_di_toi_man():
    # Backend trả khoá mà giao diện không đọc thì cũng như không trả.
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert "di_toi_man" in js, "app.js chưa đọc khoá di_toi_man"
    assert re.search(r"data-di-toi", js), (
        "phải render nút riêng cho trường hợp nhảy nội bộ, không dùng <a href>"
    )


def test_nut_noi_ro_no_lam_gi():
    # "Mở" cho một thứ chưa nối là nói dối. Nhãn phải nói đúng việc.
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert "Cấu hình" in js or "Thiết lập" in js, (
        "Nút nhảy sang màn Kho phải mang nhãn nói đúng việc nó làm"
    )


def test_van_du_bo_khoa_nhu_cac_muc_khac(monkeypatch):
    for loai in ("tep", "erpnext"):
        monkeypatch.setattr(settings, "erp_loai", loai)
        monkeypatch.setattr(settings, "erpnext_url", "https://x.vn")
        d = he_thong.muc_erp()
        for khoa in ("ma", "ten", "mo_ta", "url", "kiem"):
            assert d.get(khoa) is not None, f"{loai}: thiếu khoá {khoa!r}"
