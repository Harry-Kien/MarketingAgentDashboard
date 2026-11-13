"""Gõ sai tên hãng hoặc tắt hãng không được tự biến thành vận đơn giả."""
import asyncio

import pytest

from agent.shipping import service
from scripts.san_sang import CHAN, doc_van_chuyen


@pytest.mark.parametrize("ten", ["gnh", "none", "khong_dung", ""])
def test_factory_khong_fallback_mock(ten):
    with pytest.raises(ValueError):
        service.get_provider(ten)


def test_readiness_hang_la_khong_bao_du_du_da_co_khoa():
    assert doc_van_chuyen("gnh", True, True, "https://example.com")["muc"] == CHAN


def test_tao_van_don_cau_hinh_sai_khong_tru_kho(monkeypatch):
    async def cam(*a, **k):
        pytest.fail("không được đụng DB/kho khi cấu hình hãng sai")

    monkeypatch.setattr(service.db, "fetchrow", cam)
    kq = asyncio.run(service.tao_van_don_cho_don("DH1", "gnh"))
    assert not kq.ok and not kq.ma_van_don


@pytest.mark.parametrize("don", [None, {"ma_van_don": "VD1", "don_vi_van_chuyen": "gnh"}])
def test_tra_cuu_hang_sai_tra_loi_khong_no(monkeypatch, don):
    async def doc(*a, **k):
        return don

    monkeypatch.setattr(service.db, "fetchrow", doc)
    monkeypatch.setattr(service.settings, "shipping_provider", "gnh")
    kq = asyncio.run(service.tra_cuu_van_don("VD1"))
    assert not kq.ok and kq.loi

