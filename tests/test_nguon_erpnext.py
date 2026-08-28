"""Adapter ERPNext (REST của Frappe).

CHƯA XÁC MINH TRÊN INSTANCE THẬT. Test ở đây chạy trên fixture dựng theo
tài liệu Frappe, nên nó canh được LOGIC nhưng không canh được rằng tên
trường khớp với bản ERPNext của bạn. Dùng `python -m scripts.thu_erp` để
kiểm phần đó khi có instance.

Ba cái bẫy được canh riêng, vì cả ba đều hỏng IM LẶNG:

1. **Phân trang.** Frappe mặc định trả 20 bản ghi. Không đặt
   `limit_page_length=0` thì cửa hàng có 60 SKU chỉ thấy 20, agent tư vấn
   trên một danh mục bị cắt cụt, và không có lỗi nào.

2. **`ban_duoc` phải trừ phần giữ chỗ.** `actual_qty` là hàng trong kho;
   phần đã bị đơn khác đặt nằm ở `reserved_qty`. Lấy nhầm `actual_qty` là
   hứa bán món đã có người mua.

3. **Rỗng khác 0.** Không có bản ghi `Bin` nghĩa là chưa biết, không phải
   hết hàng. Trả 0 là nói dối một cách tự tin.
"""
from __future__ import annotations

import json

import httpx
import pytest

from agent.erp.hop_dong import LoiERP, NguonERP
from agent.erp.erpnext import NguonErpNext
from tests.erp_gia import chay


def _ds_item(**ghi_de):
    return {
        "data": [
            {
                "item_code": "AS-CL01",
                "item_name": "Sữa rửa mặt",
                "item_group": "Làm sạch",
                "stock_uom": "Chai",
                "is_sales_item": 1,
                **ghi_de,
            }
        ]
    }


def _nguon(xu_ly, **kw) -> NguonErpNext:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(xu_ly), base_url="https://erp.thu"
    )
    return NguonErpNext(
        goc="https://erp.thu",
        api_key="k",
        api_secret="s",
        ma_kho=kw.pop("ma_kho", "KHO-HN"),
        pricelist=kw.pop("pricelist", "Bán lẻ"),
        client=client,
        **kw,
    )


def _bo_dinh_tuyen(ghi_lai: list | None = None):
    """Trả phản hồi hợp lệ cho cả ba DocType, và ghi lại request nếu cần."""

    def xu_ly(req: httpx.Request) -> httpx.Response:
        if ghi_lai is not None:
            ghi_lai.append(req)
        duong = req.url.path
        if duong.endswith("/Item"):
            return httpx.Response(200, json=_ds_item())
        if duong.endswith("/Item Price"):
            return httpx.Response(200, json={"data": [{
                "price_list_rate": 245000.0,
                "currency": "VND",
                "price_list": "Bán lẻ",
                "valid_upto": None,
            }]})
        if duong.endswith("/Bin"):
            return httpx.Response(200, json={"data": [{
                "actual_qty": 10.0, "reserved_qty": 3.0, "warehouse": "KHO-HN",
            }]})
        if "get_logged_user" in duong:
            return httpx.Response(200, json={"message": "he-thong@thu.vn"})
        return httpx.Response(404, json={"data": []})

    return xu_ly


# --- Hợp đồng --------------------------------------------------------

def test_la_nguon_erp_hop_le():
    assert isinstance(_nguon(_bo_dinh_tuyen()), NguonERP)


def test_doc_duoc_san_pham():
    ds = chay(_nguon(_bo_dinh_tuyen()).danh_sach_san_pham())
    assert [sp.ma for sp in ds] == ["AS-CL01"]
    assert ds[0].ten == "Sữa rửa mặt"
    assert ds[0].loai == "Làm sạch"


def test_gia_giu_lai_nguon_de_truy_vet():
    g = chay(_nguon(_bo_dinh_tuyen()).gia("AS-CL01"))
    assert g.gia_ban == 245000
    assert g.don_vi == "VND"
    assert g.nguon == "Bán lẻ"


# --- Bẫy 1: phân trang cắt ngầm --------------------------------------

def test_luon_tat_phan_trang():
    # Frappe mặc định trả 20 bản ghi. Cửa hàng 60 SKU sẽ chỉ thấy 20, agent
    # tư vấn trên danh mục cụt, và KHÔNG có lỗi nào được ném.
    reqs: list[httpx.Request] = []
    chay(_nguon(_bo_dinh_tuyen(reqs)).danh_sach_san_pham())
    item = [r for r in reqs if r.url.path.endswith("/Item")][0]
    assert item.url.params.get("limit_page_length") == "0"


# --- Bẫy 2: bán được ≠ tồn kho ---------------------------------------

def test_ban_duoc_tru_phan_da_giu_cho():
    t = chay(_nguon(_bo_dinh_tuyen()).ton_kho("AS-CL01"))
    assert t.ban_duoc == 7          # 10 actual − 3 reserved
    assert t.ma_kho == "KHO-HN"


def test_ban_duoc_khong_bao_gio_am():
    # reserved > actual xảy ra thật khi kho đang lệch. Trả số âm thì mọi
    # phép so sánh "đủ hàng không" phía trên đều hành xử kỳ quặc.
    def xu_ly(req):
        if req.url.path.endswith("/Bin"):
            return httpx.Response(200, json={"data": [
                {"actual_qty": 2.0, "reserved_qty": 5.0, "warehouse": "KHO-HN"}
            ]})
        return _bo_dinh_tuyen()(req)

    assert chay(_nguon(xu_ly).ton_kho("AS-CL01")).ban_duoc == 0


# --- Bẫy 3: rỗng khác không ------------------------------------------

def test_khong_co_ban_ghi_bin_thi_tra_none_chu_khong_phai_0():
    # Không có Bin nghĩa là CHƯA BIẾT, không phải hết hàng. Trả 0 là nói dối
    # một cách tự tin, và tầng trên không có cách nào phân biệt.
    def xu_ly(req):
        if req.url.path.endswith("/Bin"):
            return httpx.Response(200, json={"data": []})
        return _bo_dinh_tuyen()(req)

    assert chay(_nguon(xu_ly).ton_kho("AS-CL01")) is None


def test_khong_co_gia_thi_tra_none():
    def xu_ly(req):
        if req.url.path.endswith("/Item Price"):
            return httpx.Response(200, json={"data": []})
        return _bo_dinh_tuyen()(req)

    assert chay(_nguon(xu_ly).gia("AS-CL01")) is None


# --- Lọc đúng thứ được phép bán --------------------------------------

def test_chi_lay_hang_duoc_phep_ban():
    reqs: list[httpx.Request] = []
    chay(_nguon(_bo_dinh_tuyen(reqs)).danh_sach_san_pham())
    loc = json.loads([r for r in reqs if r.url.path.endswith("/Item")][0]
                     .url.params["filters"])
    assert ["disabled", "=", 0] in loc
    assert ["is_sales_item", "=", 1] in loc


def test_co_ban_duoc_phep_doc_tu_du_lieu_chu_khong_suy_tu_tham_so():
    # Suy từ tham số lọc thì gọi với chi_ban_duoc=False sẽ gắn cờ True cho
    # mọi món — sai, và sai một cách không phát hiện được từ bên ngoài.
    def xu_ly(req):
        if req.url.path.endswith("/Item"):
            return httpx.Response(200, json={"data": [
                {"item_code": "AS-CL01", "item_name": "Bán được",
                 "is_sales_item": 1},
                {"item_code": "AS-SR9", "item_name": "Không bán",
                 "is_sales_item": 0},
            ]})
        return _bo_dinh_tuyen()(req)

    ds = chay(_nguon(xu_ly).danh_sach_san_pham(chi_ban_duoc=False))
    assert {sp.ma: sp.ban_duoc_phep for sp in ds} == {
        "AS-CL01": True, "AS-SR9": False,
    }


def test_xin_ca_hang_khong_ban_thi_bo_loc():
    reqs: list[httpx.Request] = []
    chay(_nguon(_bo_dinh_tuyen(reqs)).danh_sach_san_pham(chi_ban_duoc=False))
    loc = json.loads([r for r in reqs if r.url.path.endswith("/Item")][0]
                     .url.params["filters"])
    assert ["is_sales_item", "=", 1] not in loc


def test_loc_ton_kho_theo_dung_kho_da_cau_hinh():
    reqs: list[httpx.Request] = []
    chay(_nguon(_bo_dinh_tuyen(reqs), ma_kho="KHO-SG").ton_kho("AS-CL01"))
    loc = json.loads([r for r in reqs if r.url.path.endswith("/Bin")][0]
                     .url.params["filters"])
    assert ["warehouse", "=", "KHO-SG"] in loc


# --- Hỏng thì phải nghe thấy -----------------------------------------

def test_xac_thuc_sai_thi_nem_loi_ro_rang():
    def xu_ly(req):
        return httpx.Response(401, json={"message": "Not permitted"})

    with pytest.raises(LoiERP, match="401"):
        chay(_nguon(xu_ly).danh_sach_san_pham())


def test_may_chu_500_thi_nem():
    def xu_ly(req):
        return httpx.Response(500, text="boom")

    with pytest.raises(LoiERP):
        chay(_nguon(xu_ly).danh_sach_san_pham())


def test_thieu_ma_kho_thi_nem_ngay_luc_dung_khong_doi_toi_luc_goi():
    # Thiếu mã kho mà vẫn dựng được thì lời gọi Bin sẽ trả về tồn của MỌI
    # kho cộng lại — một con số trông hợp lý và sai.
    with pytest.raises(ValueError, match="ERP_MA_KHO"):
        NguonErpNext(goc="https://x", api_key="k", api_secret="s",
                     ma_kho="", pricelist="Bán lẻ")


def test_thieu_khoa_api_thi_nem_ngay():
    with pytest.raises(ValueError, match="ERPNEXT_API_KEY"):
        NguonErpNext(goc="https://x", api_key="", api_secret="s",
                     ma_kho="KHO-HN", pricelist="Bán lẻ")


def test_header_xac_thuc_dung_khuon_frappe():
    reqs: list[httpx.Request] = []
    chay(_nguon(_bo_dinh_tuyen(reqs)).danh_sach_san_pham())
    assert reqs[0].headers["authorization"] == "token k:s"


def test_suc_khoe():
    assert chay(_nguon(_bo_dinh_tuyen()).suc_khoe()) is True

    def hong(req):
        raise httpx.ConnectError("không nối được")

    assert chay(_nguon(hong).suc_khoe()) is False
