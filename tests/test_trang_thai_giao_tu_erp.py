"""Trạng thái giao hàng đi NGƯỢC từ ERP về.

VÌ SAO
------
Đơn đẩy sang ERP xong là hết đường một chiều. Kho xuất hàng, ERP ghi Delivery
Note / validate stock.picking — còn bên này vẫn thấy đơn ở trạng thái `da_chot`
mãi mãi.

Hệ quả: khách hỏi "đơn tới đâu rồi", agent tra `tra_cuu_van_chuyen` và trả
lời bằng thứ nó biết — tức là không biết gì. Người trực nhìn màn Đơn hàng
cũng vậy.

ÁNH XẠ VÀO BỘ TRẠNG THÁI ĐÃ CÓ
------------------------------
`agent/shipping/models.InternalShippingStatus` là bộ trạng thái giao hàng
DUY NHẤT của hệ thống, và `tools._LOI_TRANG_THAI_GIAO` đã có sẵn lời lẽ cho
từng giá trị. Đẻ bộ thứ hai cho ERP là hai nguồn sự thật cho cùng một thứ,
và sớm muộn chúng lệch.
"""
from __future__ import annotations

import json

import httpx
import pytest

from agent.erp.erpnext import NguonErpNext
from agent.erp.odoo import NguonOdoo
from agent.shipping.models import InternalShippingStatus
from tests.erp_gia import chay


def _erpnext(trang_thai_dn=None, co_dn=True):
    def xu_ly(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/Delivery Note"):
            return httpx.Response(200, json={"data": [
                {"name": "DN-01", "status": trang_thai_dn, "docstatus": 1}
            ] if co_dn else []})
        return httpx.Response(200, json={"data": []})

    return NguonErpNext(
        goc="https://erp.thu", api_key="k", api_secret="s",
        ma_kho="KHO-HN", pricelist="Bán lẻ",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(xu_ly), base_url="https://erp.thu"),
    )


def _odoo(state=None, co_picking=True):
    def xu_ly(req: httpx.Request) -> httpx.Response:
        p = json.loads(req.content)["params"]
        if p["service"] == "common":
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": 7})
        model = p["args"][3]
        if model == "stock.picking":
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": [
                {"id": 1, "state": state}] if co_picking else []})
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": []})

    return NguonOdoo(
        goc="https://odoo.thu", db="thu", dang_nhap="a@b.vn", api_key="k",
        ma_kho="KHO-HN",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(xu_ly), base_url="https://odoo.thu"),
    )


# --- Hợp đồng --------------------------------------------------------

def test_ca_hai_adapter_deu_tra_duoc_trang_thai_giao():
    for lop in (NguonErpNext, NguonOdoo):
        assert hasattr(lop, "trang_thai_giao"), f"{lop.__name__} thiếu"


# --- ERPNext ---------------------------------------------------------

@pytest.mark.parametrize("erp,noi_bo", [
    ("To Deliver", InternalShippingStatus.DELIVERING),
    ("To Bill", InternalShippingStatus.DELIVERED),
    ("Completed", InternalShippingStatus.DELIVERED),
    ("Return Issued", InternalShippingStatus.RETURNED),
])
def test_erpnext_anh_xa_dung(erp, noi_bo):
    assert chay(_erpnext(erp).trang_thai_giao("SO-1")) == noi_bo.value


def test_erpnext_chua_co_phieu_giao_thi_None():
    # Chưa xuất kho KHÔNG phải "đang giao". Trả None để tầng trên biết là
    # chưa có gì để nói với khách.
    assert chay(_erpnext(co_dn=False).trang_thai_giao("SO-1")) is None


def test_erpnext_trang_thai_la_thi_None_chu_khong_doan():
    # ERP mỗi bản một bộ trạng thái. Gặp giá trị lạ thì nói không biết,
    # đừng đoán — đoán sai là báo khách hàng đã giao khi chưa giao.
    assert chay(_erpnext("Trạng thái nào đó mới").trang_thai_giao("SO-1")) is None


# --- Odoo ------------------------------------------------------------

@pytest.mark.parametrize("state,noi_bo", [
    ("assigned", InternalShippingStatus.DELIVERING),
    ("confirmed", InternalShippingStatus.DELIVERING),
    ("done", InternalShippingStatus.DELIVERED),
    ("cancel", InternalShippingStatus.RETURNED),
])
def test_odoo_anh_xa_dung(state, noi_bo):
    assert chay(_odoo(state).trang_thai_giao("SO-1")) == noi_bo.value


def test_odoo_chua_co_picking_thi_None():
    assert chay(_odoo(co_picking=False).trang_thai_giao("SO-1")) is None


def test_odoo_state_la_thi_None():
    assert chay(_odoo("trang_thai_moi_toanh").trang_thai_giao("SO-1")) is None


# --- Không đẻ bộ trạng thái thứ hai ----------------------------------

def test_chi_tra_gia_tri_thuoc_bo_noi_bo():
    hop_le = {s.value for s in InternalShippingStatus}
    for ham, gt in ((_erpnext, "Completed"), (_odoo, "done")):
        kq = chay(ham(gt).trang_thai_giao("SO-1"))
        assert kq in hop_le, (
            f"{kq!r} không thuộc InternalShippingStatus — đẻ bộ trạng thái "
            "thứ hai là hai nguồn sự thật cho cùng một thứ"
        )


def test_moi_gia_tri_noi_bo_deu_co_loi_le_cho_agent():
    # `tools._LOI_TRANG_THAI_GIAO` là chỗ agent lấy câu chữ. Ánh xạ ra một
    # giá trị không có lời lẽ thì agent im lặng, không ai biết vì sao.
    from agent.core.tools import _LOI_TRANG_THAI_GIAO

    thieu = {s.value for s in InternalShippingStatus} - set(_LOI_TRANG_THAI_GIAO)
    assert not thieu, f"thiếu lời lẽ cho trạng thái {sorted(thieu)}"
