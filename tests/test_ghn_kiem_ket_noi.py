"""GHN: kiểm token và shop id bằng một lời gọi chỉ đọc, không tạo vận đơn."""
from __future__ import annotations

import asyncio

import httpx

from agent import cau_hinh_dong as cd
from agent.config import settings
from agent.shipping import ghn


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_token_dung_shop_dung():
    def handler(req):
        assert req.headers["Token"] == "tok"
        assert req.url.path.endswith("/shop/all")
        return httpx.Response(200, json={"data": {"shops": [{"_id": 123, "name": "Shop"}]}})

    ok, chi_tiet, _ = asyncio.run(ghn.kiem_ket_noi(
        token="tok", shop_id="123", api_url="https://ghn.test/v2", client=_client(handler),
    ))
    assert ok and "1 shop" in chi_tiet


def test_shop_id_khong_thuoc_tai_khoan_thi_noi_ro():
    def handler(req):
        return httpx.Response(200, json={"data": {"shops": [{"_id": 999}]}})

    ok, chi_tiet, _ = asyncio.run(ghn.kiem_ket_noi(
        token="tok", shop_id="123", api_url="https://ghn.test/v2", client=_client(handler),
    ))
    assert not ok and "123" in chi_tiet


def test_token_sai_thi_khong_ok():
    def handler(req):
        return httpx.Response(401, json={"message": "Unauthorized"})

    ok, chi_tiet, _ = asyncio.run(ghn.kiem_ket_noi(
        token="sai", shop_id="1", api_url="https://ghn.test/v2", client=_client(handler),
    ))
    assert not ok and "token" in chi_tiet.lower()


def test_than_200_khong_phai_json_thi_khong_no():
    def handler(req):
        return httpx.Response(200, text="<html>ok</html>")

    ok, chi_tiet, _ = asyncio.run(ghn.kiem_ket_noi(
        token="tok", shop_id="1", api_url="https://ghn.test/v2", client=_client(handler),
    ))
    assert not ok and "JSON" in chi_tiet


def test_provider_ghn_doc_qua_cau_hinh_dong(monkeypatch):
    cd._gia_tri.clear()
    monkeypatch.setattr(settings, "ghn_token", "tu-env")
    assert ghn.GHNShippingProvider()._token == "tu-env"
    cd._gia_tri["GHN_TOKEN"] = "tu-csdl"
    assert ghn.GHNShippingProvider()._token == "tu-csdl"
    cd._gia_tri.clear()


def test_erpnext_doc_qua_cau_hinh_dong(monkeypatch):
    from agent.erp.erpnext import NguonErpNext

    cd._gia_tri.clear()
    cd._gia_tri["ERPNEXT_URL"] = "https://erp.csdl"
    cd._gia_tri["ERPNEXT_API_KEY"] = "k"
    cd._gia_tri["ERPNEXT_API_SECRET"] = "s"
    monkeypatch.setattr(settings, "erp_ma_kho", "KHO")
    monkeypatch.setattr(settings, "erp_pricelist", "Bán lẻ")
    assert NguonErpNext()._goc == "https://erp.csdl"
    cd._gia_tri.clear()
