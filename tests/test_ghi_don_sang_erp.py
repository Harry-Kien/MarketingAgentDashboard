"""Đẩy đơn sang ERP — bộ khẳng định CHUNG cho mọi adapter ghi được.

Đường GHI khác hẳn đường đọc về mức rủi ro. Đọc sai thì agent trả lời sai,
sửa được. Ghi sai thì đơn trùng và bản ghi khách rác nằm VĨNH VIỄN trong ERP
của cửa hàng — không rút lại được.

Nên bộ này canh bốn thứ, và cả bốn đều là chuyện tiền bạc thật:

1. Adapter chỉ đọc KHÔNG được vô tình mang khả năng ghi.
2. Khách được tra trước khi tạo — một người không được thành mười bản ghi.
3. Đơn được tra trước khi tạo — mạng đứt sau khi ERP đã nhận thì lần thử
   lại KHÔNG tạo đơn thứ hai.
4. ERP từ chối thì nói ra, không nuốt.
"""
from __future__ import annotations

import json

import httpx
import pytest

from agent.erp.erpnext import NguonErpNext
from agent.erp.hop_dong import DongDon, LoiERP, NguonGhiERP
from agent.erp.odoo import NguonOdoo
from agent.erp.tep import NguonTep
from tests.erp_gia import chay

_KHOA = "AS260828120000"
_SDT = "0901234567"
_DONG = [DongDon(ma="AS-CL01", so_luong=2, don_gia=245000)]


# =====================================================================
#  ERPNext
# =====================================================================

def _erpnext(ghi_lai: list, **kw):
    khach_co = kw.pop("khach_co", False)
    don_co = kw.pop("don_co", None)
    tao_hong = kw.pop("tao_hong", False)

    def xu_ly(req: httpx.Request) -> httpx.Response:
        ghi_lai.append(req)
        duong = req.url.path
        if req.method == "GET" and duong.endswith("/Customer"):
            return httpx.Response(200, json={"data": (
                [{"name": "KH-0001"}] if khach_co else []
            )})
        if req.method == "GET" and duong.endswith("/Sales Order"):
            return httpx.Response(200, json={"data": (
                [{"name": don_co}] if don_co else []
            )})
        if req.method == "POST" and duong.endswith("/Customer"):
            return httpx.Response(200, json={"data": {"name": "KH-MOI"}})
        if req.method == "POST" and duong.endswith("/Sales Order"):
            if tao_hong:
                return httpx.Response(417, json={
                    "exception": "ValidationError: hết hàng"})
            return httpx.Response(200, json={"data": {"name": "SO-0009"}})
        return httpx.Response(200, json={"data": []})

    return NguonErpNext(
        goc="https://erp.thu", api_key="k", api_secret="s",
        ma_kho="KHO-HN", pricelist="Bán lẻ",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(xu_ly), base_url="https://erp.thu"
        ),
    )


# =====================================================================
#  Odoo
# =====================================================================

def _odoo(ghi_lai: list, **kw):
    khach_co = kw.pop("khach_co", False)
    don_co = kw.pop("don_co", None)
    tao_hong = kw.pop("tao_hong", False)

    def xu_ly(req: httpx.Request) -> httpx.Response:
        ghi_lai.append(req)
        p = json.loads(req.content)["params"]
        if p["service"] == "common":
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": 7})
        model, method = p["args"][3], p["args"][4]
        if model == "res.partner" and method == "search_read":
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": (
                [{"id": 11}] if khach_co else []
            )})
        if model == "res.partner" and method == "create":
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": 12})
        if model == "sale.order" and method == "search_read":
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": (
                [{"name": don_co}] if don_co else []
            )})
        if model == "sale.order" and method == "create":
            if tao_hong:
                return httpx.Response(200, json={"jsonrpc": "2.0", "error": {
                    "code": 200, "message": "Odoo Server Error",
                    "data": {"message": "ValidationError: hết hàng"}}})
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": 99})
        if model == "sale.order" and method == "read":
            return httpx.Response(200, json={"jsonrpc": "2.0",
                                             "result": [{"name": "SO0099"}]})
        if model == "product.product":
            return httpx.Response(200, json={"jsonrpc": "2.0",
                                             "result": [{"id": 5}]})
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": []})

    return NguonOdoo(
        goc="https://odoo.thu", db="thu", dang_nhap="a@b.vn", api_key="k",
        ma_kho="KHO-HN",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(xu_ly), base_url="https://odoo.thu"
        ),
    )


NHA_MAY_GHI = {"erpnext": _erpnext, "odoo": _odoo}


@pytest.fixture(params=sorted(NHA_MAY_GHI))
def ten(request):
    return request.param


# --- 1. Ranh giới đọc/ghi --------------------------------------------

def test_adapter_tep_KHONG_ghi_duoc(tmp_path):
    # `tep` đọc một file JSON trên đĩa. Nó tuyệt đối không được vô tình mang
    # khả năng ghi chỉ vì nằm chung một hợp đồng.
    p = tmp_path / "catalog.json"
    p.write_text('{"san_pham": []}', encoding="utf-8")
    assert not isinstance(NguonTep(p), NguonGhiERP)


def test_adapter_erp_that_thi_ghi_duoc(ten):
    assert isinstance(NHA_MAY_GHI[ten]([]), NguonGhiERP)


# --- 2. Khách được tra trước khi tạo ---------------------------------

def test_khach_da_co_thi_dung_lai_khong_tao_moi(ten):
    # Tạo mới mỗi đơn thì một người thành mười bản ghi, và báo cáo bán hàng
    # bên ERP thành vô nghĩa.
    reqs: list[httpx.Request] = []
    n = NHA_MAY_GHI[ten](reqs, khach_co=True)
    ma_kh = chay(n.bao_dam_khach("Nguyễn Văn A", _SDT, "12 Nguyễn Trãi"))
    assert ma_kh
    assert not _co_tao_khach(ten, reqs)


def test_khach_chua_co_thi_tao_moi(ten):
    reqs: list[httpx.Request] = []
    n = NHA_MAY_GHI[ten](reqs, khach_co=False)
    assert chay(n.bao_dam_khach("Nguyễn Văn A", _SDT, "12 Nguyễn Trãi"))
    assert _co_tao_khach(ten, reqs)


def _co_tao_khach(ten: str, reqs: list[httpx.Request]) -> bool:
    if ten == "erpnext":
        return any(r.method == "POST" and r.url.path.endswith("/Customer")
                   for r in reqs)
    for r in reqs:
        p = json.loads(r.content)["params"]
        if p["service"] == "object" and p["args"][3] == "res.partner" \
                and p["args"][4] == "create":
            return True
    return False


# --- 3. Đơn được tra trước khi tạo -----------------------------------

def test_don_da_ton_tai_thi_tra_lai_ma_cu_khong_tao_them(ten):
    # ERP có thể đã nhận nhưng mạng đứt trước khi ta thấy phản hồi. Lần thử
    # lại mà không tra trước là khách bị lên hai đơn.
    reqs: list[httpx.Request] = []
    n = NHA_MAY_GHI[ten](reqs, don_co="SO-DA-CO")
    assert chay(n.tim_don(_KHOA)) == "SO-DA-CO"


def test_don_chua_ton_tai_thi_tim_don_tra_None(ten):
    n = NHA_MAY_GHI[ten]([], don_co=None)
    assert chay(n.tim_don(_KHOA)) is None


def test_tao_don_gui_kem_khoa_idempotency(ten):
    reqs: list[httpx.Request] = []
    n = NHA_MAY_GHI[ten](reqs)
    chay(n.tao_don(_KHOA, "KH-0001" if ten == "erpnext" else "11", _DONG))
    assert _khoa_da_gui(ten, reqs) == _KHOA


def _khoa_da_gui(ten: str, reqs: list[httpx.Request]) -> str | None:
    if ten == "erpnext":
        for r in reqs:
            if r.method == "POST" and r.url.path.endswith("/Sales Order"):
                return json.loads(r.content).get("po_no")
        return None
    for r in reqs:
        p = json.loads(r.content)["params"]
        if p["service"] == "object" and p["args"][3] == "sale.order" \
                and p["args"][4] == "create":
            return p["args"][5][0].get("client_order_ref")
    return None


def test_tao_don_thanh_cong_tra_ma_don_erp(ten):
    n = NHA_MAY_GHI[ten]([])
    kq = chay(n.tao_don(_KHOA, "KH-0001" if ten == "erpnext" else "11", _DONG))
    assert kq.thanh_cong is True
    assert kq.erp_ma_don


# --- 4. ERP từ chối thì nói ra ---------------------------------------

def test_erp_tu_choi_thi_bao_that_bai_kem_ly_do(ten):
    # Nuốt lỗi ở đây là báo khách "đã chốt" cho một đơn ERP không nhận.
    n = NHA_MAY_GHI[ten]([], tao_hong=True)
    kq = chay(n.tao_don(_KHOA, "KH-0001" if ten == "erpnext" else "11", _DONG))
    assert kq.thanh_cong is False
    assert "hết hàng" in kq.ly_do


def test_mat_mang_giua_chung_thi_nem_chu_khong_bao_thanh_cong(ten):
    # Ném thì tầng trên đưa đơn về `cho_dong_bo` và thử lại. Báo thành công
    # là mất đơn vĩnh viễn: bên này tưởng xong, bên ERP không có gì.
    def hong(_req):
        raise httpx.ConnectError("đứt")

    if ten == "erpnext":
        n = NguonErpNext(
            goc="https://x", api_key="k", api_secret="s",
            ma_kho="KHO-HN", pricelist="Bán lẻ",
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(hong), base_url="https://x"),
        )
    else:
        n = NguonOdoo(
            goc="https://x", db="d", dang_nhap="a", api_key="k",
            ma_kho="KHO-HN",
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(hong), base_url="https://x"),
        )
    with pytest.raises(LoiERP):
        chay(n.tao_don(_KHOA, "KH", _DONG))


def test_don_khong_co_dong_nao_thi_tu_choi(ten):
    n = NHA_MAY_GHI[ten]([])
    with pytest.raises(ValueError):
        chay(n.tao_don(_KHOA, "KH-0001", []))
