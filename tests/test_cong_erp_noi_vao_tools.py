"""Nối cổng vào `tools._catalog_song()` mà không đổi chữ ký của `_catalog()`.

Giữ chữ ký `-> dict` là điều kiện để bộ test hiện có vẫn là lưới an toàn
thật, chứ không phải lưới đã bị tháo trong lúc thay nguồn dữ liệu.
"""
import typing

import pytest

from agent.config import settings
from agent.core import tools
from agent.erp import nha_may
from agent.erp.hop_dong import NguonERP
from agent.erp.tep import NguonTep
from tests.erp_gia import chay


@pytest.fixture(autouse=True)
def _sach():
    nha_may.dat_lai()
    yield
    nha_may.dat_lai()


def test_mac_dinh_la_nguon_tep(monkeypatch):
    # Máy vừa clone về, không .env, không ERP: vẫn phải chạy được.
    from agent.config import Settings
    assert Settings(_env_file=None).erp_loai == "tep"
    monkeypatch.setattr(settings, "erp_loai", "tep")
    assert isinstance(nha_may.tao_nguon(), NguonTep)


def test_nguon_nao_cung_phai_hop_le_voi_protocol():
    assert isinstance(nha_may.tao_nguon(), NguonERP)


def test_erp_loai_la_rac_thi_no_chu_khong_im_lang(monkeypatch):
    # Gõ sai `ERP_LOAI=odooo` rồi lặng lẽ rơi về tệp là chạy suốt tháng với
    # giá trong file mà tưởng đang nối ERP.
    monkeypatch.setattr(settings, "erp_loai", "odooo")
    with pytest.raises(ValueError, match="odooo"):
        nha_may.tao_nguon()


def test_cong_dung_lai_mot_lan():
    assert nha_may.cong() is nha_may.cong()


def test_chu_ky_catalog_khong_doi():
    # `get_type_hints` chứ không phải `signature`: tools.py có
    # `from __future__ import annotations` nên annotation là chuỗi "dict",
    # và so sánh `is dict` sẽ luôn sai bất kể mã đúng hay hỏng.
    assert typing.get_type_hints(tools._catalog)["return"] is dict


def test_catalog_van_tra_ve_san_pham():
    d = tools._catalog()
    assert isinstance(d, dict)
    assert len(d.get("san_pham", [])) > 0


def test_catalog_song_van_tra_ve_san_pham():
    d = chay(tools._catalog_song())
    assert isinstance(d, dict)
    assert len(d.get("san_pham", [])) > 0
    assert all("gia" in sp for sp in d["san_pham"])
