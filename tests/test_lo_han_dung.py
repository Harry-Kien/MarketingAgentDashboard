"""
Lô hàng và hạn dùng.

Khẳng định trung tâm: `so_luong = None` KHÁC `so_luong = 0`.

  None  ERPNext không trả về số lượng lô (v15 chuyển sang Serial and Batch
        Bundle). Ta KHÔNG BIẾT lô còn hàng hay không.
  0     ta biết chắc lô đã bán hết.

Gộp hai thứ ấy làm một theo hướng "coi None là còn hàng" thì agent báo hạn
của một lô đã bán sạch — khách nghe "hạn tới 2027", nhận lọ hết hạn tháng
sau. Đó là kiểu sai tệ nhất: tự tin, cụ thể, và không ai kiểm được.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.erp.cong import Cong  # noqa: E402
from agent.erp.hop_dong import Gia, Lo, LoiERP, SanPhamERP, TonKho  # noqa: E402


class NguonCoLo:
    """Adapter giả CÓ quản lô."""

    ten = "gia_lap_co_lo"

    def __init__(self, lo: list[Lo] | Exception):
        self._lo = lo
        self.so_lan_goi = 0

    async def danh_sach_san_pham(self, chi_ban_duoc: bool = True):
        return [SanPhamERP(ma="A", ten="A")]

    async def gia(self, ma: str):
        return Gia(gia_ban=100_000)

    async def ton_kho(self, ma: str):
        return TonKho(ban_duoc=5)

    async def suc_khoe(self) -> bool:
        return True

    async def lo_hang(self, ma: str) -> list[Lo]:
        self.so_lan_goi += 1
        if isinstance(self._lo, Exception):
            raise self._lo
        return self._lo


class NguonKhongLo:
    """Adapter giả KHÔNG quản lô — ngành không có hạn dùng."""

    ten = "gia_lap_khong_lo"

    async def danh_sach_san_pham(self, chi_ban_duoc: bool = True):
        return [SanPhamERP(ma="A", ten="A")]

    async def gia(self, ma: str):
        return Gia(gia_ban=100_000)

    async def ton_kho(self, ma: str):
        return TonKho(ban_duoc=5)

    async def suc_khoe(self) -> bool:
        return True


def chay(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------
#  Năng lực tuỳ chọn
# ---------------------------------------------------------------

def test_adapter_khong_quan_lo_thi_tra_None():
    cong = Cong(NguonKhongLo())
    assert chay(cong.lo_hang("A")) is None
    assert chay(cong.han_dung("A")) is None


def test_adapter_khong_quan_lo_KHONG_lam_tang_bo_dem_ngat_mach():
    """
    Cửa hàng đồ thể thao không có hạn dùng. Tính việc đó là "hỏng" thì
    mạch mở liên tục và mọi thứ khác chết theo — một sự cố tự tạo ra.
    """
    cong = Cong(NguonKhongLo(), ngat_mach_so_lan=2)
    for _ in range(10):
        assert chay(cong.lo_hang("A")) is None
    tt = cong.trang_thai()
    assert tt["mach_mo"] is False
    assert tt["hong_lien_tiep"] == 0


# ---------------------------------------------------------------
#  None KHÁC 0 — khẳng định trung tâm
# ---------------------------------------------------------------

def test_lo_khong_biet_so_luong_thi_KHONG_duoc_dung_lam_han():
    """
    ERPNext không trả `batch_qty` → `so_luong=None`. Lô ấy có thể đã bán
    sạch. Không được lấy hạn của nó nói với khách.
    """
    cong = Cong(NguonCoLo([Lo(ma_lo="L1", het_han="2027-01-01", so_luong=None)]))
    assert chay(cong.han_dung("A")) is None


def test_lo_da_ban_het_thi_khong_duoc_dung_lam_han():
    cong = Cong(NguonCoLo([Lo(ma_lo="L1", het_han="2027-01-01", so_luong=0)]))
    assert chay(cong.han_dung("A")) is None


def test_chon_lo_het_han_SOM_NHAT_trong_so_lo_con_hang():
    cong = Cong(NguonCoLo([
        Lo(ma_lo="L-xa", het_han="2028-01-01", so_luong=10),
        Lo(ma_lo="L-gan", het_han="2026-10-01", so_luong=3),
        Lo(ma_lo="L-giua", het_han="2027-05-01", so_luong=7),
    ]))
    lo = chay(cong.han_dung("A"))
    assert lo is not None
    assert lo.ma_lo == "L-gan"


def test_lo_het_hang_khong_keo_han_ve_som_hon():
    """
    Lô sắp hết hạn nhưng ĐÃ BÁN SẠCH thì không liên quan tới khách đang
    hỏi. Lấy nó là báo một hạn sớm hơn thực tế — sai theo hướng an toàn,
    nhưng vẫn là sai, và nó làm khách bỏ mua hàng còn tốt.
    """
    cong = Cong(NguonCoLo([
        Lo(ma_lo="L-het", het_han="2026-09-05", so_luong=0),
        Lo(ma_lo="L-con", het_han="2027-06-01", so_luong=12),
    ]))
    assert chay(cong.han_dung("A")).ma_lo == "L-con"


def test_lo_khong_co_ngay_het_han_thi_bo_qua():
    """Lô không quản hạn (`expiry_date` trống) không phải là hạn bằng None."""
    cong = Cong(NguonCoLo([
        Lo(ma_lo="L1", het_han=None, so_luong=10),
        Lo(ma_lo="L2", het_han="2027-03-01", so_luong=4),
    ]))
    assert chay(cong.han_dung("A")).ma_lo == "L2"


def test_khong_co_lo_nao_thi_tra_None():
    assert chay(Cong(NguonCoLo([])).han_dung("A")) is None


# ---------------------------------------------------------------
#  Cổng: cache và ngắt mạch vẫn áp cho lô
# ---------------------------------------------------------------

def test_lo_hang_duoc_cache():
    nguon = NguonCoLo([Lo(ma_lo="L1", het_han="2027-01-01", so_luong=5)])
    cong = Cong(nguon, ttl_ton=999.0)

    async def hai_lan():
        await cong.lo_hang("A")
        await cong.lo_hang("A")

    chay(hai_lan())
    assert nguon.so_lan_goi == 1, "lượt thứ hai phải lấy từ cache"


def test_erp_hong_thi_tra_None_chu_khong_tra_lo_cu():
    """
    Quy tắc trung tâm của cả cổng: KHÔNG BAO GIỜ phục vụ số liệu cũ. Hạn
    dùng cũ còn nguy hiểm hơn giá cũ — hàng đã đổi lô mà vẫn báo hạn của
    lô trước là sai về an toàn, không chỉ sai về thương mại.
    """
    nguon = NguonCoLo(LoiERP("ERP sập"))
    cong = Cong(nguon, so_lan_thu=1)
    assert chay(cong.lo_hang("A")) is None


def test_ngat_mach_cua_lo_KHONG_giet_tra_gia():
    """
    Ngắt mạch theo từng thao tác. `Batch` sai quyền không được làm chết
    đường tra giá — khách hỏi giá sẽ nhận "không biết" vì một sự cố ở chỗ
    hoàn toàn khác.
    """
    nguon = NguonCoLo(LoiERP("không có quyền đọc Batch"))
    cong = Cong(nguon, ngat_mach_so_lan=2, so_lan_thu=1)

    async def kich():
        for _ in range(5):
            await cong.lo_hang("A")
        return await cong.gia("A")

    g = chay(kich())
    assert g is not None and g.gia_ban == 100_000


# ---------------------------------------------------------------
#  Adapter ERPNext: lùi khi bản không có `batch_qty`
# ---------------------------------------------------------------

def test_adapter_lui_ve_bo_truong_khong_so_luong():
    """
    v15 bỏ `batch_qty` → Frappe trả 417. Phải lùi về bộ không số lượng,
    và `so_luong` phải là None chứ KHÔNG phải 0.
    """
    from agent.erp import erpnext as mod

    goi: list[list[str]] = []

    class GiaLap(mod.NguonErpNext):
        def __init__(self):  # noqa: D107 — không gọi __init__ thật
            pass

        async def _lay(self, doctype, loc, truong):
            goi.append(truong)
            if "batch_qty" in truong:
                raise LoiERP("417: batch_qty không tồn tại")
            return [{"name": "L1", "expiry_date": "2027-01-01"}]

    ds = chay(GiaLap().lo_hang("A"))
    assert len(goi) == 2, "phải thử bộ có batch_qty trước rồi mới lùi"
    assert ds == [Lo(ma_lo="L1", het_han="2027-01-01", so_luong=None)]


def test_adapter_doc_duoc_so_luong_khi_ban_ERPNext_co():
    from agent.erp import erpnext as mod

    class GiaLap(mod.NguonErpNext):
        def __init__(self):  # noqa: D107
            pass

        async def _lay(self, doctype, loc, truong):
            return [{"name": "L1", "expiry_date": "2027-01-01", "batch_qty": 8.0}]

    assert chay(GiaLap().lo_hang("A"))[0].so_luong == 8


def test_adapter_bo_qua_lo_da_vo_hieu_hoa():
    """
    Lô `disabled=1` vẫn nằm trong bảng. Lấy cả chúng là báo cho khách hạn
    của một lô cửa hàng đã ngừng bán.
    """
    from agent.erp import erpnext as mod

    loc_da_dung: list = []

    class GiaLap(mod.NguonErpNext):
        def __init__(self):  # noqa: D107
            pass

        async def _lay(self, doctype, loc, truong):
            loc_da_dung.extend(loc)
            return []

    chay(GiaLap().lo_hang("A"))
    assert ["disabled", "=", 0] in loc_da_dung


@pytest.mark.parametrize("tho", [None, ""])
def test_adapter_bo_ban_ghi_khong_co_ma_lo(tho):
    from agent.erp import erpnext as mod

    class GiaLap(mod.NguonErpNext):
        def __init__(self):  # noqa: D107
            pass

        async def _lay(self, doctype, loc, truong):
            return [{"name": tho, "expiry_date": "2027-01-01", "batch_qty": 5}]

    assert chay(GiaLap().lo_hang("A")) == []


# ---------------------------------------------------------------
#  Công cụ: không bịa khoá `han_su_dung`
# ---------------------------------------------------------------

def test_tra_cuu_san_pham_khong_bia_khoa_han_su_dung(monkeypatch):
    """
    Không biết hạn thì KHÔNG có khoá `han_su_dung` trong kết quả — không
    phải một chuỗi "không rõ".

    Chuỗi đó nằm trong ngữ cảnh là model sẽ nhắc lại với khách, và "hạn
    dùng: không rõ" nghe như một sự thật về sản phẩm chứ không phải một
    khoảng trống trong dữ liệu.
    """
    from agent.core import tools

    async def khong_biet(ma):
        return None

    monkeypatch.setattr(tools, "_han_dung", khong_biet)

    async def catalog_gia():
        return {"san_pham": [{"ma": "A", "ten": "Serum X", "ton_kho": 5,
                              "gia": 100_000, "duoc_gioi_thieu": True}]}

    monkeypatch.setattr(tools, "_catalog_song", catalog_gia)
    ra = chay(tools.run_tool("tra_cuu_san_pham", {"ten_san_pham": "Serum X"}))
    assert ra["tim_thay"] is True
    assert "han_su_dung" not in ra


def test_tra_cuu_san_pham_kem_han_khi_biet(monkeypatch):
    from agent.core import tools

    async def biet(ma):
        return Lo(ma_lo="L9", het_han="2027-04-01", so_luong=6)

    monkeypatch.setattr(tools, "_han_dung", biet)

    async def catalog_gia():
        return {"san_pham": [{"ma": "A", "ten": "Serum X", "ton_kho": 5,
                              "gia": 100_000, "duoc_gioi_thieu": True}]}

    monkeypatch.setattr(tools, "_catalog_song", catalog_gia)
    ra = chay(tools.run_tool("tra_cuu_san_pham", {"ten_san_pham": "Serum X"}))
    assert ra["han_su_dung"] == "2027-04-01"
    assert ra["ma_lo"] == "L9"


def test_loi_khi_tra_lo_khong_lam_hong_luot_tra_gia(monkeypatch):
    """
    Hạn dùng là thông tin THÊM. ERP quản lô hỏng không được làm chết cả
    lượt tra giá, vốn là việc chính của công cụ này.
    """
    from agent.core import tools
    from agent.erp import nha_may

    class CongHong:
        async def han_dung(self, ma):
            raise LoiERP("Batch sập")

    monkeypatch.setattr(nha_may, "cong", lambda: CongHong())

    async def catalog_gia():
        return {"san_pham": [{"ma": "A", "ten": "Serum X", "ton_kho": 5,
                              "gia": 100_000, "duoc_gioi_thieu": True}]}

    monkeypatch.setattr(tools, "_catalog_song", catalog_gia)
    ra = chay(tools.run_tool("tra_cuu_san_pham", {"ten_san_pham": "Serum X"}))
    assert ra["tim_thay"] is True
    assert ra["gia"] == 100_000
    assert "han_su_dung" not in ra
