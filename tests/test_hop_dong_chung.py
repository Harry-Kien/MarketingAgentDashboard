"""Bộ khẳng định CHUNG, chạy trên MỌI adapter.

VÌ SAO CẦN
----------
`tep` và `erpnext` được viết cách nhau, bởi hai vòng suy nghĩ khác nhau, dựa
trên hai nguồn dữ liệu hình dạng khác hẳn. Không có bộ test dùng chung thì
chúng sẽ trôi ra xa nhau một cách âm thầm: một cái trả `None` khi không biết,
cái kia trả `0`; một cái ném khi hỏng, cái kia nuốt lỗi.

Lúc đó đổi `ERP_LOAI` không còn là đổi nguồn dữ liệu nữa — nó đổi cả HÀNH VI
của hệ thống, và không ai được báo.

Mỗi adapter mới thêm vào `_LOAI_HOP_LE` phải xuất hiện ở đây. Có một test
canh đúng việc đó.
"""
from __future__ import annotations

import json

import httpx
import pytest

from agent.erp import nha_may
from agent.erp.erpnext import NguonErpNext
from agent.erp.hop_dong import Gia, LoiERP, NguonERP, SanPhamERP, TonKho
from agent.erp.odoo import NguonOdoo
from agent.erp.tep import NguonTep
from tests.erp_gia import chay

# Cùng một cửa hàng, mô tả bằng hai hình dạng dữ liệu khác nhau.
_MA = "AS-CL01"
_TEN = "Sữa rửa mặt"
_GIA = 245000
_BAN_DUOC = 7


def _dung_tep(tmp_path, rong: bool = False, hong: bool = False) -> NguonTep:
    p = tmp_path / "catalog.json"
    if hong:
        p.write_text("{ hỏng", encoding="utf-8")
    elif rong:
        p.write_text('{"san_pham": []}', encoding="utf-8")
    else:
        p.write_text(
            json.dumps(
                {"san_pham": [{"ma": _MA, "ten": _TEN, "gia": _GIA,
                               "ton_kho": _BAN_DUOC}]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return NguonTep(p)


def _dung_erpnext(_tmp_path, rong: bool = False, hong: bool = False):
    def _hoi_ma(req: httpx.Request) -> str | None:
        """Mã sản phẩm trong tham số `filters`, nếu có.

        Bộ giả PHẢI tôn trọng bộ lọc như ERPNext thật, nếu không nó trả giá
        cho mọi mã và test 'mã không tồn tại' hoá ra chỉ đang kiểm bộ giả.
        """
        for dieu_kien in json.loads(req.url.params.get("filters", "[]")):
            if dieu_kien[0] == "item_code":
                return dieu_kien[2]
        return None

    def xu_ly(req: httpx.Request) -> httpx.Response:
        if hong:
            return httpx.Response(500, text="boom")
        duong = req.url.path
        khong_co = rong or (_hoi_ma(req) not in (None, _MA))
        if duong.endswith("/Item"):
            return httpx.Response(200, json={"data": [] if rong else [
                {"item_code": _MA, "item_name": _TEN, "is_sales_item": 1}
            ]})
        if duong.endswith("/Item Price"):
            return httpx.Response(200, json={"data": [] if khong_co else [
                {"price_list_rate": float(_GIA), "currency": "VND",
                 "price_list": "Bán lẻ"}
            ]})
        if duong.endswith("/Bin"):
            return httpx.Response(200, json={"data": [] if khong_co else [
                {"actual_qty": float(_BAN_DUOC), "reserved_qty": 0.0,
                 "warehouse": "KHO-HN"}
            ]})
        return httpx.Response(200, json={"message": "ok"})

    return NguonErpNext(
        goc="https://erp.thu", api_key="k", api_secret="s",
        ma_kho="KHO-HN", pricelist="Bán lẻ",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(xu_ly), base_url="https://erp.thu"
        ),
    )


def _dung_odoo(_tmp_path, rong: bool = False, hong: bool = False):
    def xu_ly(req: httpx.Request) -> httpx.Response:
        if hong:
            return httpx.Response(200, json={"jsonrpc": "2.0", "error": {
                "code": 200, "message": "Odoo Server Error",
                "data": {"message": "hỏng"}}})
        than = json.loads(req.content)
        p = than["params"]
        if p["service"] == "common":
            # `authenticate` trả uid; `version` trả dict. Cả hai đều hợp lệ
            # ở đây vì bộ giả không phân biệt — adapter mới là bên phân biệt.
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": 7})
        model, args = p["args"][3], p["args"][5]
        if model == "stock.warehouse":
            return httpx.Response(200, json={"jsonrpc": "2.0",
                                             "result": [{"id": 3}]})
        ma_hoi = None
        for dk in args[0]:
            if isinstance(dk, list) and dk[0] == "default_code":
                ma_hoi = dk[2]
        if rong or (ma_hoi is not None and ma_hoi != _MA):
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": []})
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": [{
            "default_code": _MA, "name": _TEN,
            "categ_id": False, "uom_id": False,
            "list_price": float(_GIA), "free_qty": float(_BAN_DUOC),
            "sale_ok": True,
        }]})

    return NguonOdoo(
        goc="https://odoo.thu", db="thu", dang_nhap="a@b.vn", api_key="k",
        ma_kho="KHO-HN",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(xu_ly), base_url="https://odoo.thu"
        ),
    )


# Mỗi adapter một hàm dựng. Thêm adapter mới thì thêm một dòng ở đây.
NHA_MAY_THU = {"tep": _dung_tep, "erpnext": _dung_erpnext, "odoo": _dung_odoo}


@pytest.fixture(params=sorted(NHA_MAY_THU))
def ten_adapter(request):
    return request.param


def test_moi_adapter_duoc_khai_deu_co_trong_bo_test_nay():
    # Thêm adapter vào nhà máy mà quên thêm ở đây thì nó không bao giờ được
    # đối chiếu với các adapter khác, và sẽ trôi xa dần trong im lặng.
    thieu = sorted(set(nha_may._LOAI_HOP_LE) - set(NHA_MAY_THU))
    assert not thieu, (
        f"Adapter {thieu} có trong nha_may._LOAI_HOP_LE nhưng thiếu ở "
        "NHA_MAY_THU của tests/test_hop_dong_chung.py"
    )


def test_hop_le_voi_protocol(ten_adapter, tmp_path):
    assert isinstance(NHA_MAY_THU[ten_adapter](tmp_path), NguonERP)


def test_co_ten_rieng(ten_adapter, tmp_path):
    assert NHA_MAY_THU[ten_adapter](tmp_path).ten == ten_adapter


def test_tra_dung_kieu_du_lieu(ten_adapter, tmp_path):
    n = NHA_MAY_THU[ten_adapter](tmp_path)
    ds = chay(n.danh_sach_san_pham())
    assert all(isinstance(sp, SanPhamERP) for sp in ds)
    assert isinstance(chay(n.gia(_MA)), Gia)
    assert isinstance(chay(n.ton_kho(_MA)), TonKho)


def test_doc_ra_cung_mot_cua_hang(ten_adapter, tmp_path):
    n = NHA_MAY_THU[ten_adapter](tmp_path)
    assert [sp.ma for sp in chay(n.danh_sach_san_pham())] == [_MA]
    assert chay(n.gia(_MA)).gia_ban == _GIA
    assert chay(n.ton_kho(_MA)).ban_duoc == _BAN_DUOC


def test_ma_khong_ton_tai_thi_None_khong_phai_0(ten_adapter, tmp_path):
    # Ràng buộc quan trọng nhất của bộ này. `0` nghĩa là hết hàng; `None`
    # nghĩa là chưa biết. Hai adapter trả hai thứ khác nhau cho cùng một
    # tình huống là hai hệ thống khác nhau đội chung một tên.
    n = NHA_MAY_THU[ten_adapter](tmp_path)
    assert chay(n.gia("KHONG-CO-MA-NAY")) is None
    assert chay(n.ton_kho("KHONG-CO-MA-NAY")) is None


def test_danh_muc_rong_thi_tra_rong_chu_khong_nem(ten_adapter, tmp_path):
    n = NHA_MAY_THU[ten_adapter](tmp_path, rong=True)
    assert chay(n.danh_sach_san_pham()) == []


def test_nguon_hong_thi_NEM_LoiERP_chu_khong_tra_rong(ten_adapter, tmp_path):
    # Trả rỗng nghĩa là "cửa hàng không có hàng nào" — agent tin, chuyển hết
    # cho người, không ai biết vì sao. Và bộ đếm ngắt mạch không bao giờ tăng.
    n = NHA_MAY_THU[ten_adapter](tmp_path, hong=True)
    with pytest.raises(LoiERP):
        chay(n.danh_sach_san_pham())


def test_suc_khoe_bao_chet_khi_nguon_hong(ten_adapter, tmp_path):
    n = NHA_MAY_THU[ten_adapter](tmp_path, hong=True)
    assert chay(n.suc_khoe()) is False


def test_suc_khoe_bao_song_khi_nguon_binh_thuong(ten_adapter, tmp_path):
    assert chay(NHA_MAY_THU[ten_adapter](tmp_path).suc_khoe()) is True
