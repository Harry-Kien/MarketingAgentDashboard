"""Gói chuyển nhà: mã hoá đúng, và mọi kiểu hỏng đều NỔ chứ không cho ra nửa gói."""
from __future__ import annotations

import io
import os

import pytest

from scripts import goi_ma_hoa as g


@pytest.fixture(autouse=True)
def _khoi_nho(monkeypatch):
    monkeypatch.setattr(g, "KHOI", 1024)       # nhiều khối với dữ liệu nhỏ


def _goi(du_lieu: bytes, mk: str = "mat-khau-thu") -> bytes:
    ra = io.BytesIO()
    assert g.ma_hoa(io.BytesIO(du_lieu), ra, mk) == len(du_lieu)
    return ra.getvalue()


@pytest.mark.parametrize("n", [0, 1, 1023, 1024, 1025, 5000])
def test_khu_hoi_dung_moi_kich_thuoc(n):
    du = os.urandom(n)
    ra = io.BytesIO()
    g.giai_ma(io.BytesIO(_goi(du)), ra, "mat-khau-thu")
    assert ra.getvalue() == du


def test_ban_ma_khong_chua_ban_ro():
    du = b"CREDENTIAL_MASTER_KEYS=1:bi-mat-rat-dai " * 50
    assert b"CREDENTIAL_MASTER_KEYS" not in _goi(du)


def test_sai_mat_khau_thi_no():
    with pytest.raises(g.LoiGoi, match="sai mật khẩu"):
        g.giai_ma(io.BytesIO(_goi(b"x" * 3000)), io.BytesIO(), "sai")


def test_cat_cut_mat_khoi_cuoi_thi_no():
    """Lỗi hay gặp nhất khi chép tệp lớn: tệp ngắn hơn bản gốc."""
    goi = _goi(os.urandom(5000))
    # Cắt đúng ở ranh giới khối: mọi khối còn lại đều hợp lệ, chỉ thiếu khối cuối.
    bo = len(g.MAGIC) + 16
    vi_tri = [bo]
    while bo < len(goi):
        n = int.from_bytes(goi[bo:bo + 4], "big")
        bo += 4 + 12 + n
        vi_tri.append(bo)
    cut = goi[:vi_tri[-2]]
    with pytest.raises(g.LoiGoi, match="cắt cụt"):
        g.giai_ma(io.BytesIO(cut), io.BytesIO(), "mat-khau-thu")


def test_cat_giua_khoi_thi_no():
    goi = _goi(os.urandom(5000))
    with pytest.raises(g.LoiGoi):
        g.giai_ma(io.BytesIO(goi[:-7]), io.BytesIO(), "mat-khau-thu")


def test_sua_mot_byte_thi_no():
    goi = bytearray(_goi(os.urandom(3000)))
    goi[60] ^= 1
    with pytest.raises(g.LoiGoi):
        g.giai_ma(io.BytesIO(bytes(goi)), io.BytesIO(), "mat-khau-thu")


def test_du_lieu_thua_sau_khoi_cuoi_thi_no():
    with pytest.raises(g.LoiGoi, match="thừa"):
        g.giai_ma(io.BytesIO(_goi(b"abc") + b"rac"), io.BytesIO(), "mat-khau-thu")


def test_khong_phai_goi_thi_no():
    with pytest.raises(g.LoiGoi, match="định dạng"):
        g.giai_ma(io.BytesIO(b"PK\x03\x04 khong phai"), io.BytesIO(), "x")
