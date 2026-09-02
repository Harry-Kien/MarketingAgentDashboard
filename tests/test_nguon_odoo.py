"""Adapter Odoo (JSON-RPC cổ điển `/jsonrpc`).

CHƯA XÁC MINH TRÊN INSTANCE THẬT — xem `python -m scripts.thu_erp`.

Bốn chỗ được canh riêng, vì Odoo bẫy khác ERPNext:

1. **`free_qty` chứ không phải `qty_available`.** `qty_available` là hàng
   trong kho; `free_qty` đã trừ phần bị đơn khác giữ chỗ. Lấy nhầm là hứa
   bán món đã có người đặt.

2. **Tồn kho phải hỏi theo KHO.** Odoo trả tồn toàn công ty nếu không truyền
   `context={"warehouse": id}`. Con số đó trông hợp lý và sai.

3. **`sale_ok` và `active`.** Odoo giữ cả hàng ngừng bán lẫn hàng đã lưu trữ.

4. **Đăng nhập một lần rồi giữ uid.** Gọi `authenticate` mỗi lần là nhân đôi
   số vòng mạng cho mọi câu hỏi của khách.
"""
from __future__ import annotations

import json

import httpx
import pytest

from agent.erp.hop_dong import LoiERP, NguonERP
from agent.erp.odoo import NguonOdoo
from tests.erp_gia import chay

_UID = 7
_KHO_ID = 3


def _than(req: httpx.Request) -> dict:
    return json.loads(req.content)


def _dich_vu(req: httpx.Request) -> tuple[str, str]:
    p = _than(req)["params"]
    return p["service"], p["method"]


def _goi_execute(req: httpx.Request) -> tuple[str, str, list, dict]:
    """(model, method, args, kwargs) của một lời execute_kw."""
    args = _than(req)["params"]["args"]
    return args[3], args[4], args[5], (args[6] if len(args) > 6 else {})


def _bo_dinh_tuyen(ghi_lai: list | None = None, **kw):
    san_pham = kw.pop("san_pham", [
        {"id": 1, "default_code": "AS-CL01", "name": "Sữa rửa mặt",
         "categ_id": [4, "Làm sạch"], "uom_id": [1, "Chai"],
         "list_price": 245000.0, "free_qty": 7.0, "sale_ok": True},
    ])
    uid = kw.pop("uid", _UID)

    def xu_ly(req: httpx.Request) -> httpx.Response:
        if ghi_lai is not None:
            ghi_lai.append(req)
        dv, pt = _dich_vu(req)
        if dv == "common" and pt == "authenticate":
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": uid})
        if dv == "common" and pt == "version":
            return httpx.Response(200, json={"jsonrpc": "2.0",
                                             "result": {"server_version": "17.0"}})
        model, method, args, _kwargs = _goi_execute(req)
        if model == "stock.warehouse":
            return httpx.Response(200, json={"jsonrpc": "2.0",
                                             "result": [{"id": _KHO_ID}]})
        if model == "product.product":
            ma_hoi = None
            for dk in args[0] if args else []:
                if isinstance(dk, list) and dk[0] == "default_code":
                    ma_hoi = dk[2]
            kq = [sp for sp in san_pham
                  if ma_hoi is None or sp.get("default_code") == ma_hoi]
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": kq})
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": []})

    return xu_ly


def _nguon(xu_ly, **kw) -> NguonOdoo:
    return NguonOdoo(
        goc="https://odoo.thu",
        db=kw.pop("db", "thu"),
        dang_nhap=kw.pop("dang_nhap", "he-thong@thu.vn"),
        api_key=kw.pop("api_key", "khoa"),
        ma_kho=kw.pop("ma_kho", "KHO-HN"),
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(xu_ly), base_url="https://odoo.thu"
        ),
        **kw,
    )


# --- Hợp đồng --------------------------------------------------------

def test_la_nguon_erp_hop_le():
    assert isinstance(_nguon(_bo_dinh_tuyen()), NguonERP)


def test_doc_duoc_san_pham():
    ds = chay(_nguon(_bo_dinh_tuyen()).danh_sach_san_pham())
    assert [sp.ma for sp in ds] == ["AS-CL01"]
    assert ds[0].ten == "Sữa rửa mặt"
    assert ds[0].loai == "Làm sạch"      # categ_id là [id, nhãn]
    assert ds[0].dung_tich == "Chai"     # uom_id cũng vậy


def test_gia_noi_ro_no_den_tu_dau():
    g = chay(_nguon(_bo_dinh_tuyen()).gia("AS-CL01"))
    assert g.gia_ban == 245000
    # Đây là `list_price`, KHÔNG phải giá từ bảng giá. Trường `nguon` phải
    # nói ra điều đó, nếu không người đọc tưởng nó đã qua pricelist.
    assert "list_price" in g.nguon


# --- Bẫy 1: free_qty chứ không phải qty_available --------------------

def test_ton_kho_lay_free_qty_da_tru_phan_giu_cho():
    reqs: list[httpx.Request] = []
    t = chay(_nguon(_bo_dinh_tuyen(reqs)).ton_kho("AS-CL01"))
    assert t.ban_duoc == 7
    truong = [r for r in reqs
              if _than(r)["params"].get("service") == "object"
              and _goi_execute(r)[0] == "product.product"][-1]
    xin = _goi_execute(truong)[3].get("fields", [])
    assert "free_qty" in xin
    assert "qty_available" not in xin


def test_ban_duoc_khong_bao_gio_am():
    xu_ly = _bo_dinh_tuyen(san_pham=[
        {"id": 1, "default_code": "AS-CL01", "name": "x", "free_qty": -4.0}
    ])
    assert chay(_nguon(xu_ly).ton_kho("AS-CL01")).ban_duoc == 0


# --- Bẫy 2: phải hỏi theo kho ----------------------------------------

def test_ton_kho_hoi_theo_dung_kho():
    # Không truyền context warehouse thì Odoo trả tồn TOÀN CÔNG TY — con số
    # trông hợp lý và sai.
    reqs: list[httpx.Request] = []
    chay(_nguon(_bo_dinh_tuyen(reqs)).ton_kho("AS-CL01"))
    truong = [r for r in reqs
              if _than(r)["params"].get("service") == "object"
              and _goi_execute(r)[0] == "product.product"][-1]
    ctx = _goi_execute(truong)[3].get("context", {})
    assert ctx.get("warehouse") == _KHO_ID


def test_ma_kho_dang_so_thi_dung_thang_khong_tra_lai():
    reqs: list[httpx.Request] = []
    chay(_nguon(_bo_dinh_tuyen(reqs), ma_kho="12").ton_kho("AS-CL01"))
    assert not [r for r in reqs
                if _than(r)["params"].get("service") == "object"
                and _goi_execute(r)[0] == "stock.warehouse"]


def test_ma_kho_khong_tim_thay_thi_nem():
    def xu_ly(req):
        dv, pt = _dich_vu(req)
        if dv == "common":
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": _UID})
        if _goi_execute(req)[0] == "stock.warehouse":
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": []})
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": []})

    with pytest.raises(LoiERP, match="KHO-HN"):
        chay(_nguon(xu_ly).ton_kho("AS-CL01"))


# --- Bẫy 3: lọc hàng được phép bán -----------------------------------

def test_chi_lay_hang_duoc_phep_ban():
    reqs: list[httpx.Request] = []
    chay(_nguon(_bo_dinh_tuyen(reqs)).danh_sach_san_pham())
    mien = _goi_execute([r for r in reqs
                         if _than(r)["params"].get("service") == "object"][-1])[2][0]
    assert ["sale_ok", "=", True] in mien
    assert ["active", "=", True] in mien


def test_xin_ca_hang_khong_ban_thi_bo_loc_sale_ok():
    reqs: list[httpx.Request] = []
    chay(_nguon(_bo_dinh_tuyen(reqs)).danh_sach_san_pham(chi_ban_duoc=False))
    mien = _goi_execute([r for r in reqs
                         if _than(r)["params"].get("service") == "object"][-1])[2][0]
    assert ["sale_ok", "=", True] not in mien


def test_bo_qua_san_pham_khong_co_ma_noi_bo():
    # Odoo cho phép `default_code` rỗng. Không có mã thì không nối được với
    # nửa tư vấn, và đưa vào danh mục là tạo một dòng không ai tra được.
    xu_ly = _bo_dinh_tuyen(san_pham=[
        {"id": 1, "default_code": False, "name": "Không mã"},
        {"id": 2, "default_code": "AS-CL01", "name": "Có mã"},
    ])
    assert [sp.ma for sp in chay(_nguon(xu_ly).danh_sach_san_pham())] == ["AS-CL01"]


# --- Bẫy 4: đăng nhập một lần ----------------------------------------

def test_chi_dang_nhap_mot_lan_cho_nhieu_loi_goi():
    reqs: list[httpx.Request] = []
    n = _nguon(_bo_dinh_tuyen(reqs))
    chay(n.danh_sach_san_pham())
    chay(n.gia("AS-CL01"))
    chay(n.ton_kho("AS-CL01"))
    dang_nhap = [r for r in reqs if _dich_vu(r) == ("common", "authenticate")]
    assert len(dang_nhap) == 1


# --- Rỗng khác không -------------------------------------------------

def test_ma_khong_ton_tai_thi_None_khong_phai_0():
    n = _nguon(_bo_dinh_tuyen())
    assert chay(n.gia("KHONG-CO")) is None
    assert chay(n.ton_kho("KHONG-CO")) is None


# --- Hỏng thì phải nghe thấy -----------------------------------------

def test_dang_nhap_that_bai_thi_nem():
    with pytest.raises(LoiERP, match="đăng nhập"):
        chay(_nguon(_bo_dinh_tuyen(uid=False)).danh_sach_san_pham())


def test_loi_json_rpc_thi_nem_kem_thong_diep():
    def xu_ly(req):
        return httpx.Response(200, json={
            "jsonrpc": "2.0",
            "error": {"code": 200, "message": "Odoo Server Error",
                      "data": {"message": "AccessError: cấm"}},
        })

    with pytest.raises(LoiERP, match="cấm"):
        chay(_nguon(xu_ly).danh_sach_san_pham())


def test_mat_mang_thi_nem():
    def xu_ly(req):
        raise httpx.ConnectError("không nối được")

    with pytest.raises(LoiERP):
        chay(_nguon(xu_ly).danh_sach_san_pham())


def test_thieu_db_thi_nem_ngay_luc_dung():
    with pytest.raises(ValueError, match="ODOO_DB"):
        NguonOdoo(goc="https://x", db="", dang_nhap="a", api_key="k",
                  ma_kho="KHO-HN")


def test_suc_khoe():
    assert chay(_nguon(_bo_dinh_tuyen()).suc_khoe()) is True

    def hong(req):
        raise httpx.ConnectError("x")

    assert chay(_nguon(hong).suc_khoe()) is False
