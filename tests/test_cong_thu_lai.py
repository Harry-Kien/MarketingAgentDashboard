"""
Cổng ERP: thử lại có hạn giờ cho thao tác ĐỌC.

Trước đây một cú chớp mạng là một câu trả lời hỏng — khách hỏi giá đúng lúc
ERP nấc một nhịp thì agent nói "em chưa tra được" rồi chuyển người. Mất một
khách vì sự cố kéo dài 200ms.

Và hạn giờ: adapter để 15 giây (hạn của thư viện HTTP, hợp cho tác vụ nền),
nhưng đây là đường trả lời khách — ERP treo là người ta ngồi nhìn khung chat
15 giây rồi mới nhận lời từ chối.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.erp.cong import Cong  # noqa: E402
from agent.erp.hop_dong import Gia, LoiERP, SanPhamERP, TonKho  # noqa: E402


class NguonDoiTinh:
    """Nguồn giả: hỏng `so_lan_hong` lần đầu rồi mới trả kết quả."""

    ten = "dem"

    def __init__(self, so_lan_hong: int = 0, treo_giay: float = 0.0):
        self.so_lan_hong = so_lan_hong
        self.treo_giay = treo_giay
        self.so_lan_goi = 0

    async def _lam(self):
        self.so_lan_goi += 1
        if self.treo_giay:
            await asyncio.sleep(self.treo_giay)
        if self.so_lan_goi <= self.so_lan_hong:
            raise LoiERP("ERP nấc một nhịp")

    async def gia(self, ma: str):
        await self._lam()
        return Gia(gia_ban=245000, nguon="thu")

    async def ton_kho(self, ma: str):
        await self._lam()
        return TonKho(ban_duoc=7, ma_kho="KHO")

    async def danh_sach_san_pham(self, chi_ban_duoc: bool = True):
        return [SanPhamERP(ma="A", ten="X")]

    async def suc_khoe(self):
        return True


def chay(coro):
    return asyncio.run(coro)


# =====================================================================
#  Thử lại
# =====================================================================

def test_hong_mot_lan_roi_duoc_thi_van_tra_ket_qua():
    """Đây là cả lý do tính năng này tồn tại: cú chớp mạng không giết câu trả lời."""
    n = NguonDoiTinh(so_lan_hong=1)
    cong = Cong(n, so_lan_thu=2)

    kq = chay(cong.gia("A"))

    assert kq is not None
    assert kq.gia_ban == 245000
    assert n.so_lan_goi == 2


def test_hong_het_moi_lan_thu_thi_tra_None_chu_khong_tra_so_cu():
    """QUY TẮC TRUNG TÂM: không bao giờ trả số cũ."""
    n = NguonDoiTinh(so_lan_hong=99)
    cong = Cong(n, so_lan_thu=2)

    assert chay(cong.gia("A")) is None
    assert n.so_lan_goi == 2


def test_dat_so_lan_thu_bang_1_la_tat_han():
    n = NguonDoiTinh(so_lan_hong=1)
    cong = Cong(n, so_lan_thu=1)

    assert chay(cong.gia("A")) is None
    assert n.so_lan_goi == 1


def test_so_lan_thu_0_hoac_am_van_goi_dung_mot_lan():
    """Cấu hình lạ không được biến thành 'không gọi lần nào'."""
    for xau in (0, -3):
        n = NguonDoiTinh()
        cong = Cong(n, so_lan_thu=xau)
        chay(cong.gia("A"))
        assert n.so_lan_goi == 1, xau


# =====================================================================
#  Thử lại KHÔNG được làm ngắt mạch mở sớm
# =====================================================================

def test_mot_chuoi_thu_hong_chi_tinh_LA_MOT_lan_hong():
    """
    Đếm từng lần thử thì ngắt mạch mở nhanh gấp `so_lan_thu` lần so với con
    số người vận hành đặt trong `.env`. Họ viết 5 và nghĩ là 5 sự cố.
    """
    n = NguonDoiTinh(so_lan_hong=99)
    cong = Cong(n, so_lan_thu=3, ngat_mach_so_lan=2)

    chay(cong.gia("A"))
    assert cong.trang_thai()["hong_lien_tiep"] == 1
    assert cong.trang_thai()["mach_mo"] is False

    chay(cong.gia("B"))
    assert cong.trang_thai()["hong_lien_tiep"] == 2
    assert cong.trang_thai()["mach_mo"] is True


def test_mach_mo_thi_khong_goi_ERP_lan_nao_nua():
    """Gọi tiếp là bắt mỗi khách đang chờ ăn trọn thời gian timeout."""
    n = NguonDoiTinh(so_lan_hong=99)
    cong = Cong(n, so_lan_thu=2, ngat_mach_so_lan=1)

    chay(cong.gia("A"))
    da_goi = n.so_lan_goi

    chay(cong.gia("B"))
    assert n.so_lan_goi == da_goi


# =====================================================================
#  Hạn giờ
# =====================================================================

def test_ERP_treo_thi_cat_theo_han_cho_khong_cho_het_timeout_HTTP():
    """
    Khách không ngồi chờ 15 giây. Cắt ở hạn của cổng, không đợi hạn của thư
    viện HTTP.
    """
    n = NguonDoiTinh(treo_giay=5.0)
    cong = Cong(n, so_lan_thu=1, han_cho_giay=0.2)

    import time
    t0 = time.perf_counter()
    kq = chay(cong.gia("A"))
    mat = time.perf_counter() - t0

    assert kq is None
    assert mat < 2.0, f"cắt quá muộn: {mat:.2f}s"


def test_treo_cung_duoc_thu_lai():
    """Treo là một dạng hỏng — cú nấc mạng hay biểu hiện thành treo."""
    n = NguonDoiTinh(treo_giay=5.0)
    cong = Cong(n, so_lan_thu=2, han_cho_giay=0.2)

    chay(cong.gia("A"))

    assert n.so_lan_goi == 2


# =====================================================================
#  Huỷ không phải là ERP hỏng
# =====================================================================

def test_nguoi_goi_huy_thi_KHONG_thu_lai_va_khong_dem_la_hong():
    """
    Khách đóng chat hoặc tiến trình tắt — không phải ERP hỏng. Nuốt nó
    thành lỗi ERP là vừa thử lại vô ích vừa đẩy ngắt mạch mở oan.
    """
    class NguonHuy:
        ten = "huy"
        so_lan_goi = 0

        async def gia(self, ma):
            NguonHuy.so_lan_goi += 1
            raise asyncio.CancelledError()

        async def ton_kho(self, ma):
            return None

        async def danh_sach_san_pham(self, chi_ban_duoc=True):
            return []

        async def suc_khoe(self):
            return True

    n = NguonHuy()
    cong = Cong(n, so_lan_thu=3)

    with pytest.raises(asyncio.CancelledError):
        chay(cong.gia("A"))

    assert NguonHuy.so_lan_goi == 1
    assert cong.trang_thai()["hong_lien_tiep"] == 0


# =====================================================================
#  Không đụng đường GHI
# =====================================================================

def test_cong_khong_boc_thao_tac_ghi_nao():
    """
    Thử lại chỉ an toàn vì cổng chỉ bọc thao tác ĐỌC. Ngày ai đó cho một
    hàm GHI đi qua đây, ca này phải đỏ — thử lại mù khi tạo đơn là nguy cơ
    đơn trùng, một lỗi tốn tiền thật.
    """
    cong_khai = {
        t for t in dir(Cong)
        if not t.startswith("_") and callable(getattr(Cong, t, None))
    }
    # Danh sách này KHÔNG được nới ra cho một thao tác ghi. Thêm tên vào đây
    # là một quyết định có ý thức, và lý do phải viết ra ngay tại chỗ:
    #
    #   lo_hang    đọc DocType `Batch` — lấy hạn dùng
    #   han_dung   thuần tính toán trên kết quả `lo_hang`, không gọi ERP
    assert cong_khai == {
        "gia", "ton_kho", "suc_khoe", "danh_muc", "trang_thai",
        "lo_hang", "han_dung",
    }
