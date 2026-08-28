"""Kho/ERP phải có mặt trong bảng "Hệ thống" của dashboard.

VÌ SAO
------
Bảng đó là chỗ người vận hành nhớ "hệ thống này gồm những gì". Nó liệt kê
ZaloCRM, Chatwoot, n8n, MinIO — và trước đây không có ERP, dù ERP là nơi giữ
giá và tồn kho, thứ quyết định agent nói gì với khách.

Thiếu ở đó thì ERP thành một thành phần vô hình: chạy thì không ai biết, chết
cũng không ai biết, và không có đường một-cú-bấm để mở nó ra xem.

KHÁC MỤC "SỨC KHOẺ"
-------------------
`suc_khoe._kiem_erp` trả lời "nó có CHẠY ĐÚNG không" — gọi thật, xem mạch có
mở không. Bảng này trả lời câu khác: "nó có TỒN TẠI và có mở được không".
Hai câu khác nhau, hai chỗ khác nhau.
"""
from __future__ import annotations

import pytest

from agent import he_thong
from agent.config import settings
from tests.erp_gia import chay


def test_muc_erp_xuat_hien_trong_bang_he_thong():
    # KHÔNG nằm trong danh sách tĩnh `DICH_VU` — nó được dựng theo cấu hình
    # mỗi lần gọi. Nên phép kiểm đúng là nhìn thứ API thật sự trả ra.
    ma = [d["ma"] for d in chay(he_thong.kiem_tat_ca())["dich_vu"]]
    assert "erp" in ma, (
        "Bảng Hệ thống thiếu mục 'erp'. Kho/ERP giữ giá và tồn kho — nó "
        "không được là thành phần vô hình trên dashboard."
    )


def test_muc_erp_du_truong_nhu_cac_muc_khac():
    # Thiếu một khoá thì JavaScript render ra `undefined` chứ không nổ.
    d = he_thong.muc_erp()
    for khoa in ("ma", "ten", "mo_ta", "url", "kiem"):
        assert d.get(khoa) is not None, f"mục erp thiếu khoá {khoa!r}"


def test_muc_erp_dung_dung_bo_khoa_ma_cac_muc_khac_dung():
    # Lệch tên khoá thì giao diện render sai một cách im lặng.
    chuan = set(he_thong.DICH_VU[0]) - {"kiem", "chinh"}
    thieu = chuan - set(he_thong.muc_erp())
    assert not thieu, f"mục erp thiếu khoá mà mục khác có: {sorted(thieu)}"


def test_url_lay_tu_cau_hinh_khong_go_cung(monkeypatch):
    # Bốn dịch vụ kia chạy trên localhost cố định. ERP thì ở máy khác, và
    # gõ cứng một URL là bảo đảm nó sai với mọi cửa hàng.
    monkeypatch.setattr(settings, "erp_loai", "erpnext")
    monkeypatch.setattr(settings, "erpnext_url", "https://erp.cua-hang.vn")
    d = he_thong.muc_erp()
    assert "erp.cua-hang.vn" in d["url"]
    assert "erp.cua-hang.vn" in d["kiem"]


def test_dung_odoo_thi_lay_url_odoo(monkeypatch):
    monkeypatch.setattr(settings, "erp_loai", "odoo")
    monkeypatch.setattr(settings, "odoo_url", "https://odoo.cua-hang.vn")
    assert "odoo.cua-hang.vn" in he_thong.muc_erp()["url"]


def test_chua_noi_erp_thi_noi_thang_ra(monkeypatch):
    # Chạy bằng `tep` là hợp lệ. Nhưng mô tả phải nói rõ, nếu không người
    # vận hành nhìn bảng và tưởng đã nối ERP.
    monkeypatch.setattr(settings, "erp_loai", "tep")
    d = he_thong.muc_erp()
    assert "chưa nối" in d["mo_ta"].lower() or "tệp" in d["mo_ta"].lower()


def test_khong_nhung_erp_vao_iframe(monkeypatch):
    # Odoo và ERPNext đều gửi X-Frame-Options. Bật `nhung_duoc` thì người
    # dùng bấm "Mở" và nhận một khung trắng — hỏng câm, không lỗi nào.
    monkeypatch.setattr(settings, "erp_loai", "erpnext")
    monkeypatch.setattr(settings, "erpnext_url", "https://erp.thu")
    assert not he_thong.muc_erp().get("nhung_duoc")


def test_kiem_tat_ca_khong_nem_khi_chua_cau_hinh_erp(monkeypatch):
    # Chưa điền URL thì mục vẫn phải trả về được, chỉ là "không chạy".
    monkeypatch.setattr(settings, "erp_loai", "tep")
    kq = chay(he_thong.kiem_tat_ca())
    ma = [d["ma"] for d in kq["dich_vu"]]
    assert "erp" in ma
    assert kq["tong"] == len(kq["dich_vu"])


@pytest.mark.parametrize("loai", ["tep", "erpnext", "odoo"])
def test_moi_loai_nguon_deu_tra_ve_muc_hop_le(monkeypatch, loai):
    monkeypatch.setattr(settings, "erp_loai", loai)
    d = he_thong.muc_erp()
    assert d["ma"] == "erp" and d["ten"] and d["mo_ta"]
