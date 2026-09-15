"""
Đơn sang ERPNext ở dạng NHÁP thì không giữ chỗ hàng — phải nói ra.

LỖI THẬT, ĐO ĐƯỢC 15.09.2026 — lỗi THỨ BA trong cùng luồng
----------------------------------------------------------
Sửa xong nhóm khách và ngày giao, đơn thật cuối cùng cũng sang được ERPNext:
`SAL-ORD-2026-00001`. Nhưng `Bin` không đổi — `reserved_qty` vẫn 0, tồn kho
vẫn 100.

ERPNext chỉ giữ chỗ hàng khi Sales Order được SUBMIT (`docstatus=1`). Đơn
tạo qua API mặc định là `Draft` (`docstatus=0`): nó nằm trong ERP, nhìn
thấy được, nhưng với kho thì như chưa tồn tại.

Hậu quả: agent chốt đơn, đơn sang ERP, người vận hành thấy đơn trong danh
sách — và hai khách vẫn mua được cùng một món cuối. Không lỗi, không nhật
ký. Đây là kiểu hỏng im lặng tệ nhất: mọi dấu hiệu đều nói đã xong.

VÌ SAO MẶC ĐỊNH VẪN LÀ NHÁP
---------------------------
Submit là chứng từ CHÍNH THỨC: vào sổ, không sửa được nữa, chỉ huỷ được.
Để agent tự làm việc đó ngay ngày đầu nối ERP là quá nhanh. Mặc định nháp,
bật có chủ ý — cùng khuôn `ERP_GHI_DON`.

Nhưng mặc định an toàn KHÔNG được phép im lặng: `san_sang` phải nói rằng
đơn đang ở dạng nháp và kho chưa được giữ chỗ.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.erp.erpnext import NguonErpNext  # noqa: E402
from agent.erp.hop_dong import DongDon  # noqa: E402


class _Gia(NguonErpNext):
    def __init__(self, **kw):
        super().__init__(goc="http://x", api_key="k", api_secret="s",
                         ma_kho="Stores", pricelist="Standard Selling", **kw)
        self.than: dict = {}
        self.da_submit: list[str] = []

    async def _tao(self, doctype, than):
        if doctype == "Sales Order":
            self.than = than
        return {"name": "SO-1"}

    async def _submit(self, doctype, ten):
        self.da_submit.append(f"{doctype}/{ten}")


def _chay(**kw) -> _Gia:
    e = _Gia(**kw)
    asyncio.run(e.tao_don("K", "KH", [DongDon(ma="A", so_luong=1, don_gia=1000)]))
    return e


def test_mac_dinh_cua_he_thong_van_la_nhap():
    """
    Cùng khuôn ERP_GHI_DON: mặc định an toàn, bật có chủ ý.

    Kiểm mặc định của Settings chứ KHÔNG chạy adapter rồi xem nó làm gì:
    cách sau đọc `.env` của máy đang chạy, nên trên máy đã bật
    ERP_SUBMIT_DON thì test đỏ dù mã hoàn toàn đúng — và người ta sẽ sửa
    test cho hết đỏ.
    """
    from agent.config import Settings

    assert Settings.model_fields["erp_submit_don"].default is False


def test_tat_thi_khong_submit():
    assert _chay(submit_don=False).da_submit == []


def test_bat_thi_gui_don_chinh_thuc():
    assert _chay(submit_don=True).da_submit == ["Sales Order/SO-1"]


def test_khong_gui_docstatus_trong_luc_tao():
    """
    LỖI THẬT: bản đầu đặt `docstatus: 1` ngay trong payload tạo. Frappe BỎ
    QUA nó — đơn vẫn là Draft, `reserved_qty` vẫn 0, và kết cục trả về là
    "xong". Xanh hoàn toàn và sai hoàn toàn. Submit phải là một lời gọi
    riêng sau khi tạo.
    """
    assert "docstatus" not in _chay(submit_don=True).than


def test_san_sang_noi_don_dang_o_dang_nhap():
    """
    Mặc định an toàn không được phép im lặng. Đơn nằm trong ERP, nhìn thấy
    được, mà kho chưa giữ chỗ — mọi dấu hiệu nói đã xong.
    """
    from scripts.san_sang import CANH_BAO, doc_ghi_don

    m = doc_ghi_don(ghi_don=True, submit_don=False)
    assert m["muc"] == CANH_BAO
    chu = (m["ghi"] + " " + m.get("sua", "")).lower()
    assert "nháp" in chu and ("giữ chỗ" in chu or "tồn kho" in chu)


def test_san_sang_du_khi_da_bat_ca_hai():
    from scripts.san_sang import DU, doc_ghi_don

    assert doc_ghi_don(ghi_don=True, submit_don=True)["muc"] == DU


def test_san_sang_noi_khi_chua_bat_ghi_don():
    """Tắt ghi đơn thì ERP không biết gì về đơn nào — kho hai bên lệch dần
    theo từng đơn, và không có gì báo."""
    from scripts.san_sang import CANH_BAO, doc_ghi_don

    m = doc_ghi_don(ghi_don=False, submit_don=False)
    assert m["muc"] == CANH_BAO
    assert "erp_ghi_don" in (m["ghi"] + m.get("sua", "")).lower()


def test_muc_nay_co_trong_bang():
    import inspect

    from scripts import san_sang

    assert "kiem_ghi_don" in inspect.getsource(san_sang.chay)


def test_moi_bien_moi_deu_co_trong_settings():
    """
    LỖI THẬT do chính đợt này gây ra: bốn biến mới ban đầu đọc bằng
    `getattr(settings, ..., mặc_định)`. Pydantic không biết trường nào tên
    thế thì KHÔNG nạp biến môi trường cho nó, và `getattr` trả mặc định —
    đặt `ERP_SUBMIT_DON=true` xong chạy vẫn ra đơn nháp, không một lời báo.

    Khai trong Settings thì tên sai nổ ngay lúc import.
    """
    from agent.config import Settings

    for ten in ("erp_submit_don", "erp_ngay_giao_sau",
                "erp_nhom_khach", "erp_khu_vuc_khach"):
        assert ten in Settings.model_fields, ten


def test_khong_con_getattr_ne_settings():
    import inspect

    from agent.erp import erpnext

    src = inspect.getsource(erpnext)
    assert 'getattr(settings' not in src, \
        "getattr(settings, ...) nuốt biến môi trường một cách im lặng"
