"""Cổng kho/ERP phải HIỆN RA trên dashboard, không chỉ nằm trong log.

VÌ SAO TEST NÀY TỒN TẠI
-----------------------
Cả cổng ERP ghi `log_event` cho mọi thứ: ngắt mạch, lệch tồn kho, đơn kẹt,
ánh xạ mã lệch. Nhưng `log_event` ghi vào bảng `events`, và **không có màn
hình nào của dashboard đọc bảng đó**.

Nghĩa là toàn bộ hệ thống báo động đang reo trong một căn phòng không ai
bước vào — đúng cái khuôn hỏng im lặng mà CLAUDE.md cảnh báo, chỉ khác là
lần này nó nằm ở tầng vận hành chứ không phải tầng mã.

`/api/suc-khoe` là màn hình người trực thật sự bấm. Dashboard render danh
sách `muc` một cách tổng quát, nên thêm phép kiểm vào đó là nó tự hiện.
"""
from __future__ import annotations

import pytest

from agent import suc_khoe
from agent.config import settings
from agent.erp import nha_may
from agent.erp.cong import Cong
from agent.erp.hop_dong import TonKho
from tests.erp_gia import NguonGia, chay


@pytest.fixture(autouse=True)
def _sach():
    nha_may.dat_lai()
    yield
    nha_may.dat_lai()


def _dat_cong(monkeypatch, hong: bool = False, mach_mo: bool = False):
    # Phải đặt `erp_loai` khác "tep", nếu không `_kiem_erp` rẽ nhánh sớm và
    # test hoá ra chỉ đang kiểm nhánh "chưa nối ERP".
    monkeypatch.setattr(settings, "erp_loai", "erpnext")
    n = NguonGia(ton={"A": TonKho(ban_duoc=1)}, hong=hong)
    c = Cong(n, ttl_ton=0.0, ngat_mach_so_lan=1, ngat_mach_giay=30.0)
    if mach_mo:
        chay(c.ton_kho("A"))     # một lần hỏng là đủ mở mạch
    nha_may._cong = c
    return n, c


def test_co_muc_kho_erp_trong_bo_kiem(monkeypatch):
    _dat_cong(monkeypatch)
    m = chay(suc_khoe._kiem_erp())
    assert "kho" in m["ten"].lower() or "erp" in m["ten"].lower()


def test_nguon_song_thi_bao_tot(monkeypatch):
    _dat_cong(monkeypatch)
    m = chay(suc_khoe._kiem_erp())
    assert m["trang_thai"] == suc_khoe.TOT
    assert "gia" in m["ghi_chu"]          # nói rõ đang nối nguồn nào


def test_nguon_chet_thi_bao_HONG_chu_khong_im(monkeypatch):
    # ERP chết mà dashboard vẫn xanh là tệ hơn không có dashboard: người
    # trực tin vào một màn hình đang nói dối.
    _dat_cong(monkeypatch, hong=True)
    assert chay(suc_khoe._kiem_erp())["trang_thai"] == suc_khoe.HONG


def test_mach_mo_thi_it_nhat_la_canh_bao(monkeypatch):
    # Mạch mở nghĩa là mọi câu hỏi về giá và tồn đang trả "không biết", và
    # agent đang chuyển người nhiều bất thường. Người trực phải thấy.
    _dat_cong(monkeypatch, hong=True, mach_mo=True)
    m = chay(suc_khoe._kiem_erp())
    assert m["trang_thai"] in (suc_khoe.CANH_BAO, suc_khoe.HONG)
    assert "mạch" in m["ghi_chu"].lower()


def test_dang_doc_tep_thi_noi_thang_ra_la_chua_noi_erp(monkeypatch):
    # Chạy bằng `tep` là hợp lệ, nhưng KHÔNG được hiện ra như "Tốt" trống
    # trơn: người vận hành sẽ tưởng đã nối ERP.
    monkeypatch.setattr(settings, "erp_loai", "tep")
    nha_may.dat_lai()
    m = chay(suc_khoe._kiem_erp())
    assert m["trang_thai"] == suc_khoe.CANH_BAO
    assert "tệp" in m["ghi_chu"].lower() or "chưa nối" in m["ghi_chu"].lower()


def test_muc_erp_nam_trong_tong_kiem():
    # Viết phép kiểm rồi quên đăng ký là phép kiểm không bao giờ chạy — và
    # nó trông y hệt như đang chạy và luôn xanh.
    import inspect

    ma = inspect.getsource(suc_khoe.tong_kiem)
    assert "_kiem_erp()" in ma
    assert "_kiem_don_ket_erp()" in ma


def test_ghi_don_tat_thi_khong_canh_bao_don_ket(monkeypatch):
    # Tính năng tắt thì không có đơn nào chờ đồng bộ. Cảnh báo lúc đó là
    # báo động giả, và báo động giả nhiều thì người ta tắt báo động.
    monkeypatch.setattr(settings, "erp_ghi_don", False)
    m = chay(suc_khoe._kiem_don_ket_erp())
    assert m["trang_thai"] == suc_khoe.TOT
