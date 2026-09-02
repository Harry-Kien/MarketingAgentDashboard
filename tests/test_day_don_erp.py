"""Điều phối đẩy đơn — công tắc, ba kết cục, và ranh giới "được nói đã chốt".

Ranh giới quan trọng nhất của cả module nằm ở `duoc_noi_da_chot`. Khi ta
KHÔNG BIẾT ERP đã nhận đơn hay chưa, nói với khách "đã chốt" là hứa một thứ
có thể không tồn tại — và khách chỉ phát hiện khi không nhận được hàng.
"""
from __future__ import annotations

import pytest

from agent.config import settings
from agent.erp.day_don import KetQuaDay, day_don
from agent.erp.hop_dong import KetQuaDon, LoiERP, TuChoiERP
from agent.erp.tep import NguonTep
from tests.erp_gia import chay

_ITEMS = [{"ma": "AS-CL01", "ten": "Sữa rửa mặt", "so_luong": 2,
           "don_gia": 245000, "thanh_tien": 490000}]


class NguonGhiGia:
    ten = "gia_ghi"

    def __init__(self, don_da_co=None, khach="KH-1", tao=None, nem=None):
        self.don_da_co = don_da_co
        self.khach = khach
        self._tao = tao or KetQuaDon(thanh_cong=True, erp_ma_don="SO-1")
        self._nem = nem
        self.da_goi: list[str] = []

    async def tim_don(self, khoa: str):
        self.da_goi.append("tim_don")
        if self._nem and self._nem[0] == "tim_don":
            raise self._nem[1]
        return self.don_da_co

    async def bao_dam_khach(self, ten: str, sdt: str, dia_chi: str) -> str:
        self.da_goi.append("bao_dam_khach")
        if self._nem and self._nem[0] == "bao_dam_khach":
            raise self._nem[1]
        return self.khach

    async def an_danh_khach(self, sdt: str) -> int:
        # Có mặt để thoả `NguonGhiERP`. Thiếu nó thì isinstance() trả False
        # và day_don coi nguồn này là "không ghi được" — đúng thiết kế.
        self.da_goi.append("an_danh_khach")
        return 0

    async def trang_thai_giao(self, erp_ma_don: str) -> str | None:
        return None

    async def tao_don(self, khoa, khach_id, dong, ghi_chu=""):
        self.da_goi.append("tao_don")
        if self._nem and self._nem[0] == "tao_don":
            raise self._nem[1]
        self.dong_nhan = dong
        return self._tao


def _day(monkeypatch, nguon, bat: bool = True, **kw):
    monkeypatch.setattr(settings, "erp_ghi_don", bat)
    return chay(day_don(
        ma_don=kw.pop("ma_don", "AS260828120000"),
        khach_ten="Nguyễn Văn A",
        khach_sdt="0901234567",
        khach_dia_chi="12 Nguyễn Trãi, Thanh Xuân, Hà Nội",
        items=kw.pop("items", _ITEMS),
        nguon=nguon,
        **kw,
    ))


# --- Công tắc --------------------------------------------------------

def test_mac_dinh_TAT():
    # Bật lên là hành động có hậu quả không rút lại được — phải là quyết
    # định rõ ràng của người vận hành, không phải hệ quả của cập nhật mã.
    from agent.config import Settings
    assert Settings(_env_file=None).erp_ghi_don is False


def test_tat_thi_khong_cham_vao_erp(monkeypatch):
    n = NguonGhiGia()
    kq = _day(monkeypatch, n, bat=False)
    assert kq.ket_cuc == "tat"
    assert n.da_goi == []


def test_tat_thi_van_duoc_noi_da_chot(monkeypatch):
    # Tính năng tắt nghĩa là hệ thống chạy đúng như trước khi có nó: đơn nằm
    # trong Postgres và đã chốt thật. Không được làm khách hoang mang.
    assert _day(monkeypatch, NguonGhiGia(), bat=False).duoc_noi_da_chot is True


# --- Kết cục: xong ---------------------------------------------------

def test_day_thanh_cong(monkeypatch):
    kq = _day(monkeypatch, NguonGhiGia())
    assert kq.ket_cuc == "xong"
    assert kq.erp_ma_don == "SO-1"
    assert kq.duoc_noi_da_chot is True


def test_truyen_dung_dong_hang_sang_erp(monkeypatch):
    n = NguonGhiGia()
    _day(monkeypatch, n)
    assert [(d.ma, d.so_luong, d.don_gia) for d in n.dong_nhan] == [
        ("AS-CL01", 2, 245000)
    ]


# --- Lưới chống đơn trùng --------------------------------------------

def test_don_da_co_ben_erp_thi_KHONG_tao_them(monkeypatch):
    # ERP đã nhận nhưng lần trước ta mất phản hồi. Không tra trước là khách
    # bị lên hai đơn và bị tính tiền hai lần.
    n = NguonGhiGia(don_da_co="SO-CU")
    kq = _day(monkeypatch, n)
    assert kq.ket_cuc == "xong"
    assert kq.erp_ma_don == "SO-CU"
    assert "tao_don" not in n.da_goi
    assert "bao_dam_khach" not in n.da_goi


def test_tra_don_truoc_khi_tao_khach(monkeypatch):
    # Thứ tự quan trọng: tra đơn TRƯỚC. Tạo khách trước rồi mới phát hiện đơn
    # đã tồn tại là đẻ ra một bản ghi khách thừa mỗi lần thử lại.
    n = NguonGhiGia()
    _day(monkeypatch, n)
    assert n.da_goi.index("tim_don") < n.da_goi.index("bao_dam_khach")


# --- Kết cục: từ chối ------------------------------------------------

def test_erp_tu_choi_thi_KHONG_duoc_noi_da_chot(monkeypatch):
    n = NguonGhiGia(tao=KetQuaDon(thanh_cong=False, ly_do="hết hàng"))
    kq = _day(monkeypatch, n)
    assert kq.ket_cuc == "tu_choi"
    assert kq.duoc_noi_da_chot is False
    assert "hết hàng" in kq.ly_do


def test_tu_choi_dang_ngoai_le_cung_ra_tu_choi(monkeypatch):
    n = NguonGhiGia(nem=("tao_don", TuChoiERP("Odoo từ chối: sai thuế")))
    kq = _day(monkeypatch, n)
    assert kq.ket_cuc == "tu_choi"
    assert "sai thuế" in kq.ly_do


# --- Kết cục: chờ lại ------------------------------------------------

def test_mat_mang_thi_cho_lai_va_KHONG_duoc_noi_da_chot(monkeypatch):
    # Đây là ranh giới quan trọng nhất. Ta không biết ERP có đơn hay không;
    # nói "đã chốt" là hứa một thứ có thể không tồn tại.
    n = NguonGhiGia(nem=("tao_don", LoiERP("đứt mạng")))
    kq = _day(monkeypatch, n)
    assert kq.ket_cuc == "cho_lai"
    assert kq.duoc_noi_da_chot is False


def test_loi_ngoai_du_kien_cung_la_cho_lai(monkeypatch):
    n = NguonGhiGia(nem=("tao_don", ZeroDivisionError("bất ngờ")))
    kq = _day(monkeypatch, n)
    assert kq.ket_cuc == "cho_lai"
    assert kq.duoc_noi_da_chot is False


def test_khong_bao_gio_nem_ra_ngoai(monkeypatch):
    # Ném ra ngoài là để một lỗi ERP làm hỏng luồng chốt đơn vốn đã chạy
    # đúng. Đơn đã nằm trong Postgres; ERP biết hay không là việc khác.
    for loi in (LoiERP("x"), TuChoiERP("y"), RuntimeError("z"),
                KeyError("w"), TimeoutError()):
        n = NguonGhiGia(nem=("tim_don", loi))
        assert isinstance(_day(monkeypatch, n), KetQuaDay)


def test_erp_khong_tra_ma_khach_thi_cho_lai(monkeypatch):
    kq = _day(monkeypatch, NguonGhiGia(khach=""))
    assert kq.ket_cuc == "cho_lai"


# --- Cấu hình mâu thuẫn ----------------------------------------------

def test_bat_ghi_don_nhung_nguon_la_tep_thi_noi_ra(monkeypatch, tmp_path):
    # Im lặng coi như đã đẩy là tệ nhất: người vận hành tin ERP có đơn.
    p = tmp_path / "catalog.json"
    p.write_text('{"san_pham": []}', encoding="utf-8")
    kq = _day(monkeypatch, NguonTep(p))
    assert kq.ket_cuc == "tu_choi"
    assert "ERP_LOAI" in kq.ly_do


# --- Đơn rỗng --------------------------------------------------------

def test_don_khong_co_dong_hang(monkeypatch):
    n = NguonGhiGia(nem=("tao_don", ValueError("Đơn không có dòng hàng nào")))
    kq = _day(monkeypatch, n, items=[])
    assert kq.ket_cuc == "cho_lai"


@pytest.mark.parametrize("ket_cuc,noi_duoc", [
    ("tat", True), ("xong", True), ("tu_choi", False), ("cho_lai", False),
])
def test_bang_quyet_dinh_duoc_noi_da_chot(ket_cuc, noi_duoc):
    assert KetQuaDay(ket_cuc=ket_cuc).duoc_noi_da_chot is noi_duoc
