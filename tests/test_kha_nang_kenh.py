"""
Khả năng khai báo của từng plugin kênh — dữ liệu màn Kết nối & Tích hợp đọc.

Bảng khả năng chỉ có giá trị nếu nó NÓI THẬT: adapter mới quên khai thì
hiện "không hỗ trợ gì" (đỏ giả), adapter khai "đã xem" mà không có mã đọc
biên nhận thì hứa một dấu tích sẽ không bao giờ hiện (xanh giả).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agent.api.ket_noi_tich_hop import PLUGIN_MO_TA
from agent.channels import factory
from agent.channels.base import KHA_NANG, ChannelAdapter, kha_nang
from agent.omnichannel.accounts import Channel

ROOT = Path(__file__).resolve().parent.parent
_MOI_ADAPTER = {**factory._NATIVE_ADAPTERS, **factory._LEGACY_ADAPTERS}


@pytest.mark.parametrize("kenh", list(_MOI_ADAPTER), ids=lambda k: k.value)
def test_moi_adapter_khai_du_moi_kha_nang(kenh):
    lop = _MOI_ADAPTER[kenh]
    assert lop.KHA_NANG_KENH is not ChannelAdapter.KHA_NANG_KENH, f"{lop.__name__} chưa khai"
    assert set(lop.KHA_NANG_KENH) == set(KHA_NANG), lop.__name__
    assert lop.KHA_NANG_KENH["van_ban"], "kênh nhắn tin mà không gửi được chữ?"


def test_khoa_kha_nang_la_thi_no_ngay():
    with pytest.raises(KeyError):
        kha_nang(gui_anhh=True)


def test_khong_khai_bien_nhan_khi_chua_co_ma_doc_bien_nhan():
    """
    `da_nhan`/`da_xem` chỉ được True khi mã thật sự ghi `delivery_status`
    'delivered'/'read' từ webhook. Hôm nay không có dòng mã nào làm vậy.
    """
    co_ma = any("delivery_status = 'read'" in p.read_text(encoding="utf-8")
                or "delivery_status='read'" in p.read_text(encoding="utf-8")
                for p in (ROOT / "agent").rglob("*.py"))
    for lop in _MOI_ADAPTER.values():
        if not co_ma:
            assert not lop.KHA_NANG_KENH["da_xem"], lop.__name__
            assert not lop.KHA_NANG_KENH["da_nhan"], lop.__name__


def test_chi_kenh_co_ham_an_binh_luan_moi_khai_an_binh_luan():
    for lop in _MOI_ADAPTER.values():
        tu_viet = lop.an_binh_luan is not ChannelAdapter.an_binh_luan
        assert lop.KHA_NANG_KENH["an_binh_luan"] == tu_viet, lop.__name__


def test_chi_kenh_co_dau_dang_go_moi_khai_dang_go():
    for lop in _MOI_ADAPTER.values():
        tu_viet = lop.bao_dang_go is not ChannelAdapter.bao_dang_go
        assert lop.KHA_NANG_KENH["dang_go"] == tu_viet, lop.__name__


def test_moi_kenh_co_mo_ta_tren_man_ket_noi():
    for kenh in _MOI_ADAPTER:
        assert kenh.value in PLUGIN_MO_TA, kenh.value
    for kenh in Channel:
        if kenh in _MOI_ADAPTER:
            m = PLUGIN_MO_TA[kenh.value]
            wh = m["webhook"]()
            if wh:
                assert wh["duong"].startswith("/webhook/"), kenh.value
