"""`scripts/thu_erp.py` — script xác minh khi có instance ERP thật.

VÌ SAO SCRIPT NÀY CẦN TEST
--------------------------
Nó chỉ chạy trên máy có ERP thật, nghĩa là gần như không bao giờ chạy ở đây.
Không có test thì nó mục dần: đổi tên một phương thức trong hợp đồng, script
vẫn nằm im, và tới ngày cần nó nhất — ngày cắm ERP — thì nó nổ.

Test canh hai điều: nó CHẶN đúng lúc phải chặn, và nó KHÔNG in bí mật.
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import httpx
import pytest

from agent.config import settings
from agent.erp import nha_may
from agent.erp.erpnext import NguonErpNext
from scripts import thu_erp
from tests.erp_gia import chay

KHOA = "khoa-api-bi-mat-khong-duoc-in"
BI_MAT = "secret-khong-duoc-in"


def _ma_noi_bo() -> list[str]:
    """Đúng bộ mã của danh mục nội bộ.

    Đường-đi-suôn phải dùng bộ này, không phải một mã bịa. Bịa một mã thì
    phép kiểm ánh xạ thấy 1/22 và script chặn — đúng hành vi, nhưng khi đó
    test đang đo fixture chứ không đo script.
    """
    from agent.erp.tep import NguonTep

    return [sp.ma for sp in chay(NguonTep().danh_sach_san_pham())]


def _erpnext_gia(**kw) -> NguonErpNext:
    ma_co = kw.pop("ma_co", None)
    if ma_co is None:
        ma_co = _ma_noi_bo()

    def xu_ly(req: httpx.Request) -> httpx.Response:
        duong = req.url.path
        if duong.endswith("/Item"):
            return httpx.Response(200, json={"data": [
                {"item_code": m, "item_name": f"Món {m}", "is_sales_item": 1}
                for m in ma_co
            ]})
        if duong.endswith("/Item Price"):
            return httpx.Response(200, json={"data": [
                {"price_list_rate": 245000.0, "currency": "VND",
                 "price_list": "Bán lẻ"}
            ]})
        if duong.endswith("/Bin"):
            return httpx.Response(200, json={"data": [
                {"actual_qty": 9.0, "reserved_qty": 2.0, "warehouse": "KHO-HN"}
            ]})
        return httpx.Response(200, json={"message": "he-thong@thu.vn"})

    return NguonErpNext(
        goc="https://erp.thu", api_key=KHOA, api_secret=BI_MAT,
        ma_kho="KHO-HN", pricelist="Bán lẻ",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(xu_ly), base_url="https://erp.thu"
        ),
    )


def _chay(monkeypatch, nguon) -> tuple[int, str]:
    monkeypatch.setattr(settings, "erp_loai", "erpnext")
    monkeypatch.setattr(settings, "erpnext_url", "https://erp.thu")
    monkeypatch.setattr(settings, "erp_ma_kho", "KHO-HN")
    monkeypatch.setattr(settings, "erp_pricelist", "Bán lẻ")
    monkeypatch.setattr(nha_may, "tao_nguon", lambda: nguon)
    dem = io.StringIO()
    with redirect_stdout(dem):
        ma = chay(thu_erp.chay())
    return ma, dem.getvalue()


def test_erp_loai_van_la_tep_thi_chan():
    # Chạy script mà quên đổi ERP_LOAI là đang "xác minh" chính file JSON
    # trên đĩa — kết quả xanh nhưng vô nghĩa.
    ma, ra = _chay_tep()
    assert ma == 1
    assert "chặn" in ra


def _chay_tep() -> tuple[int, str]:
    dem = io.StringIO()
    with redirect_stdout(dem):
        ma = chay(thu_erp.chay())
    return ma, dem.getvalue()


def test_duong_erpnext_chay_tron(monkeypatch):
    ma, ra = _chay(monkeypatch, _erpnext_gia())
    assert ma == 0, ra
    assert "xác thực OK" in ra
    assert f"{len(_ma_noi_bo())} sản phẩm bán được" in ra
    assert "245,000 VND" in ra
    assert "7 bán được tại KHO-HN" in ra   # 9 actual − 2 reserved
    assert "mã nội bộ khớp ERP" in ra


def test_khong_bao_gio_in_khoa_api(monkeypatch):
    # Đầu ra của lệnh này hay bị dán vào chat để nhờ xem hộ.
    _, ra = _chay(monkeypatch, _erpnext_gia())
    assert KHOA not in ra
    assert BI_MAT not in ra


def test_bat_nguoi_xac_nhan_bang_gia(monkeypatch):
    # Máy không tự biết bảng giá nào là bảng giá bán lẻ. Nó phải nói ra chứ
    # không được im lặng coi như đúng.
    _, ra = _chay(monkeypatch, _erpnext_gia())
    assert "BÁN LẺ" in ra


def test_canh_bao_khi_so_san_pham_trung_muc_phan_trang(monkeypatch):
    # Danh mục bị cắt cụt trông y hệt một cửa hàng nhỏ. Con số tròn trịa của
    # Frappe là dấu hiệu đáng ngờ nhất và duy nhất.
    nguon = _erpnext_gia(ma_co=[f"SP-{i:03d}" for i in range(20)])
    _, ra = _chay(monkeypatch, nguon)
    assert "Phân trang" in ra


def test_erp_khong_noi_duoc_thi_chan(monkeypatch):
    def xu_ly(req):
        raise httpx.ConnectError("không nối được")

    nguon = NguonErpNext(
        goc="https://erp.thu", api_key=KHOA, api_secret=BI_MAT,
        ma_kho="KHO-HN", pricelist="Bán lẻ",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(xu_ly), base_url="https://erp.thu"
        ),
    )
    ma, ra = _chay(monkeypatch, nguon)
    assert ma == 1
    assert "Kết nối" in ra


def test_danh_muc_rong_thi_chan(monkeypatch):
    # Đọc được nhưng rỗng KHÔNG phải là thành công. Đó là cấu hình quyền sai
    # hoặc lọc sai, và để nó xanh là để agent chạy với danh mục trống.
    ma, ra = _chay(monkeypatch, _erpnext_gia(ma_co=[]))
    assert ma == 1
    assert "RỖNG" in ra


def test_anh_xa_ma_lech_thi_chan(monkeypatch):
    # Mã nội bộ không khớp mã ERP thì việc hợp nhất hai nửa dữ liệu lặng lẽ
    # trả rỗng — agent thấy sản phẩm mà không có thông tin tư vấn nào.
    nguon = _erpnext_gia(ma_co=["MA-LA-HOAN-TOAN-01", "MA-LA-HOAN-TOAN-02"])
    ma, ra = _chay(monkeypatch, nguon)
    assert ma == 1
    assert "Ánh xạ mã" in ra


def test_script_khong_ghi_gi_vao_erp():
    # Script này CHỈ ĐỌC. Không có lời gọi POST/PUT/DELETE nào.
    from pathlib import Path

    ma_nguon = (Path(thu_erp.__file__)).read_text(encoding="utf-8")
    for cam in (".post(", ".put(", ".delete(", ".patch("):
        assert cam not in ma_nguon, f"thu_erp.py không được ghi vào ERP: {cam}"


def test_json_khong_bi_bo_quen():
    # `json` được import trong test này để dựng fixture; giữ phép kiểm nhỏ
    # để linter không gỡ import và làm hỏng fixture ở lần sửa sau.
    assert json.dumps({"a": 1})
