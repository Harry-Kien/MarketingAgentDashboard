"""
Tạo khách bên ERPNext phải chọn nhóm LÁ, không phải nhóm cha.

LỖI THẬT, ĐO ĐƯỢC 15.09.2026
---------------------------
`bao_dam_khach()` gõ cứng `"All Customer Groups"` và `"All Territories"`.
Cả hai là nhóm CHA trong mọi bản cài ERPNext mặc định, và ERPNext từ chối
thẳng:

    Cannot select a Group type Customer Group.
    Please select a non-group Customer Group.

Hậu quả: bật `ERP_GHI_DON=true` thì MỌI đơn đều bị từ chối ở bước tạo
khách — không đơn nào sang được ERP. Lỗi nằm im từ ngày viết vì cờ ghi đơn
mặc định tắt, nên không test nào và không lần chạy nào chạm tới.

Đây đúng là loại lỗi mà chỉ chạy thật trên ERPNext thật mới thấy: adapter
giả trong test nhận mọi giá trị, kể cả giá trị ERPNext sẽ từ chối.

VÌ SAO TỰ DÒ CHỨ KHÔNG GÕ CỨNG MỘT TÊN KHÁC
-------------------------------------------
Đổi `"All Customer Groups"` thành `"Individual"` là chép lại đúng cái sai:
tên ấy đúng trên bản cài này, và cửa hàng sau có thể đã xoá hoặc đổi tên
nó. Hỏi ERPNext "nhóm nào không phải nhóm cha" thì chạy được trên mọi bản
cài, và vẫn cho phép người vận hành chỉ định rõ qua `.env` khi họ muốn
đơn rơi vào đúng nhóm của họ.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.erp.erpnext import NguonErpNext  # noqa: E402


class _Gia(NguonErpNext):
    """ERPNext giả: ghi lại truy vấn và bản ghi đã tạo."""

    def __init__(self, nhom, khu_vuc, **kw):
        kw.setdefault("submit_don", False)
        super().__init__(goc="http://x", api_key="k", api_secret="s",
                         ma_kho="Stores", pricelist="Standard Selling", **kw)
        self._nhom, self._kv = nhom, khu_vuc
        self.da_tao: list[tuple[str, dict]] = []
        self.so_lan_hoi = 0

    async def _lay(self, doctype, loc=None, truong=None):
        if doctype == "Customer":
            return []
        if doctype == "Customer Group":
            self.so_lan_hoi += 1
            return [{"name": n} for n in self._nhom]
        if doctype == "Territory":
            self.so_lan_hoi += 1
            return [{"name": n} for n in self._kv]
        return []

    async def _tao(self, doctype, than):
        self.da_tao.append((doctype, than))
        return {"name": "KH-001"}


def _tao_khach(nhom=("Individual", "Commercial"), khu_vuc=("Vietnam",), **kw):
    e = _Gia(list(nhom), list(khu_vuc), **kw)
    asyncio.run(e.bao_dam_khach("Chị Lan", "0900000000", "1 Trần Duy Hưng"))
    return e, e.da_tao[0][1]


# --- Không bao giờ gửi nhóm cha --------------------------------------

def test_khong_gui_nhom_cha():
    _, p = _tao_khach()
    assert p["customer_group"] != "All Customer Groups"
    assert p["territory"] != "All Territories"


def test_chon_nhom_la_tu_erp():
    _, p = _tao_khach(nhom=("Individual", "Commercial"), khu_vuc=("Vietnam",))
    assert p["customer_group"] == "Individual"
    assert p["territory"] == "Vietnam"


def test_truy_van_loai_bo_nhom_cha_ngay_tu_dau():
    """Lọc `is_group = 0` trong truy vấn, không lọc sau khi nhận: bản cài
    có 40 nhóm thì kéo cả 40 về rồi bỏ 39 là phí một vòng mạng."""
    import inspect

    # Việc chọn nhóm đã tách sang `_nhom_la`; ràng buộc nằm ở đó.
    src = inspect.getsource(NguonErpNext._nhom_la)
    assert '"is_group", "=", 0' in src or "'is_group', '=', 0" in src


# --- Người vận hành chỉ định được -------------------------------------

def test_cau_hinh_thang_thi_dung_no_khong_do():
    e, p = _tao_khach(nhom_khach="Bán lẻ", khu_vuc_khach="Bình Dương")
    assert p["customer_group"] == "Bán lẻ"
    assert p["territory"] == "Bình Dương"
    assert e.so_lan_hoi == 0, "đã chỉ định rồi thì đừng hỏi ERP thêm lần nào"


# --- Hỏi một lần, dùng lại --------------------------------------------

def test_chi_hoi_erp_mot_lan_cho_nhieu_khach():
    """Mỗi đơn một khách mới mà hỏi lại là hai vòng mạng thừa cho mỗi đơn."""
    e = _Gia(["Individual"], ["Vietnam"])
    for sdt in ("0900000001", "0900000002", "0900000003"):
        asyncio.run(e.bao_dam_khach("Khách", sdt, "địa chỉ"))
    assert e.so_lan_hoi == 2, f"hỏi {e.so_lan_hoi} lần cho 3 khách"


# --- Không có nhóm nào dùng được --------------------------------------

def test_khong_co_nhom_la_thi_noi_ro_phai_lam_gi():
    """
    Im lặng gửi chuỗi rỗng là để ERPNext trả một lỗi khó hiểu hơn nhiều.
    Nói thẳng ở đây, kèm việc cần làm.
    """
    from agent.erp.hop_dong import LoiERP

    e = _Gia([], [])
    with pytest.raises(LoiERP) as loi:
        asyncio.run(e.bao_dam_khach("Chị Lan", "0900000000", "địa chỉ"))
    chu = str(loi.value).lower()
    assert "customer group" in chu or "nhóm khách" in chu
    assert "erp_nhom_khach" in chu, "phải nói biến nào cần điền"
