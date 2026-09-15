"""
Sales Order gửi sang ERPNext phải có ngày giao.

LỖI THẬT, ĐO ĐƯỢC 15.09.2026 — lỗi THỨ HAI trong cùng một luồng
---------------------------------------------------------------
Sửa xong chuyện nhóm khách, đẩy đơn thật lần hai, ERPNext lại từ chối:

    frappe.exceptions.ValidationError: Please enter Delivery Date

`delivery_date` là trường BẮT BUỘC của Sales Order trong ERPNext, và
`tao_don()` không gửi nó. Cũng như lỗi trước, nó nằm im vì `ERP_GHI_DON`
mặc định tắt và ERP giả trong test nhận mọi payload.

Hai lỗi liên tiếp trong một luồng nói lên một điều: đường ghi sang ERP
CHƯA TỪNG chạy thật lần nào. Test giả kiểm được hình dạng lời gọi, không
kiểm được ERPNext có chịu nhận hay không.

VÌ SAO NGÀY GIAO LÀ HÔM NAY CỘNG MỘT SỐ NGÀY, KHÔNG PHẢI HÔM NAY
---------------------------------------------------------------
Đặt đúng hôm nay là hứa giao trong ngày với mọi đơn, kể cả đơn nhận lúc
23h. ERPNext dùng ngày này để tính đơn trễ, nên đặt sai là mọi đơn đều đỏ
trong báo cáo của cửa hàng ngay từ hôm sau.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.erp.erpnext import NguonErpNext  # noqa: E402
from agent.erp.hop_dong import DongDon  # noqa: E402


class _Gia(NguonErpNext):
    def __init__(self, **kw):
        # `submit_don=False` rõ ràng: để mặc định thì test đọc .env của máy
        # đang chạy, và trên máy đã bật ERP_SUBMIT_DON nó đi gọi mạng thật.
        kw.setdefault("submit_don", False)
        super().__init__(goc="http://x", api_key="k", api_secret="s",
                         ma_kho="Stores", pricelist="Standard Selling", **kw)
        self.than: dict = {}

    async def _tao(self, doctype, than):
        if doctype == "Sales Order":
            self.than = than
        return {"name": "SO-0001"}


def _tao_don(**kw) -> dict:
    e = _Gia(**kw)
    asyncio.run(e.tao_don("KEY-1", "KH-1", [DongDon(ma="A", so_luong=1, don_gia=1000)]))
    return e.than


def test_co_ngay_giao():
    assert _tao_don().get("delivery_date"), \
        "thiếu delivery_date thì ERPNext từ chối MỌI đơn"


def test_ngay_giao_dung_dinh_dang_erpnext():
    d = _tao_don()["delivery_date"]
    assert date.fromisoformat(d), "ERPNext đọc YYYY-MM-DD"


def test_ngay_giao_khong_phai_hom_nay():
    """Đặt đúng hôm nay là hứa giao trong ngày với cả đơn nhận lúc 23h, và
    ERPNext dùng ngày này để tính đơn trễ."""
    d = date.fromisoformat(_tao_don()["delivery_date"])
    assert d > date.today()


def test_so_ngay_cau_hinh_duoc():
    d = date.fromisoformat(_tao_don(ngay_giao_sau=5)["delivery_date"])
    assert d == date.today() + timedelta(days=5)


def test_van_giu_nguyen_cac_truong_cu():
    """Thêm một trường không được làm rơi trường nào đang chạy."""
    than = _tao_don()
    for k in ("customer", "po_no", "set_warehouse", "selling_price_list", "items"):
        assert k in than, k
