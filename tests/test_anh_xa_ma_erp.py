"""Ánh xạ mã nội bộ <-> mã ERP.

Giả định "mã nội bộ trùng item_code bên ERP" là giả định không ai kiểm, và
khi nó sai thì việc hợp nhất hai nửa dữ liệu IM LẶNG TRẢ RỖNG: agent thấy
sản phẩm nhưng không có thông tin tư vấn nào, không lỗi nào được ném.
"""
import json

import pytest

from agent.erp.anh_xa import AnhXa, doc_anh_xa, kiem
from tests.erp_gia import chay


def test_khong_co_bang_thi_coi_la_dong_nhat():
    a = AnhXa()
    assert a.sang_erp("AS-CL01") == "AS-CL01"
    assert a.ve_noi_bo("AS-CL01") == "AS-CL01"


def test_co_bang_thi_dich_hai_chieu():
    a = AnhXa({"AS-CL01": "ITEM-0001"})
    assert a.sang_erp("AS-CL01") == "ITEM-0001"
    assert a.ve_noi_bo("ITEM-0001") == "AS-CL01"


def test_ma_ngoai_bang_thi_giu_nguyen():
    a = AnhXa({"AS-CL01": "ITEM-0001"})
    assert a.sang_erp("AS-XX99") == "AS-XX99"


def test_doc_file_khong_co_thi_tra_anh_xa_dong_nhat(tmp_path):
    a = doc_anh_xa(tmp_path / "khong-co.json")
    assert a.sang_erp("AS-CL01") == "AS-CL01"


def test_doc_file_co_that(tmp_path):
    p = tmp_path / "anh_xa_ma.json"
    p.write_text(json.dumps({"AS-CL01": "ITEM-1"}), encoding="utf-8")
    assert doc_anh_xa(p).sang_erp("AS-CL01") == "ITEM-1"


def test_kiem_bao_ty_le_khop():
    kq = chay(kiem(
        ma_noi_bo=["A", "B", "C", "D"],
        ma_erp=["A", "B", "C", "Z"],
        anh_xa=AnhXa(),
    ))
    assert kq["tong"] == 4
    assert kq["khop"] == 3
    assert kq["ty_le"] == pytest.approx(0.75)
    assert kq["thieu"] == ["D"]


def test_kiem_dung_anh_xa_chu_khong_so_sanh_tho():
    kq = chay(kiem(
        ma_noi_bo=["AS-CL01"],
        ma_erp=["ITEM-1"],
        anh_xa=AnhXa({"AS-CL01": "ITEM-1"}),
    ))
    assert kq["ty_le"] == pytest.approx(1.0)


def test_kiem_danh_muc_rong_khong_chia_cho_khong():
    kq = chay(kiem(ma_noi_bo=[], ma_erp=[], anh_xa=AnhXa()))
    assert kq["tong"] == 0
    assert kq["ty_le"] == 0.0
