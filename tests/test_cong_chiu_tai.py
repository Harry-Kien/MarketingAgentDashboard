"""
Ba lớp chịu tải của cổng ERP: mạch theo thao tác, cache có trần, chống
giẫm đạp.

Ba thứ này không đau khi một cửa hàng chạy vài chục hội thoại một ngày.
Chúng đau khi có tải thật — và lúc đó thì đã muộn để thêm.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.erp.cong import Cong  # noqa: E402
from agent.erp.hop_dong import Gia, LoiERP, SanPhamERP, TonKho  # noqa: E402


class Nguon:
    """Nguồn giả: hỏng riêng từng thao tác, đếm số lời gọi thật."""

    ten = "thu"

    def __init__(self, hong_gia=False, hong_ton=False, cham=0.0):
        self.hong_gia = hong_gia
        self.hong_ton = hong_ton
        self.cham = cham
        self.dem = {"gia": 0, "ton_kho": 0}

    async def gia(self, ma: str):
        self.dem["gia"] += 1
        if self.cham:
            await asyncio.sleep(self.cham)
        if self.hong_gia:
            raise LoiERP("giá hỏng")
        return Gia(gia_ban=1000, nguon="thu")

    async def ton_kho(self, ma: str):
        self.dem["ton_kho"] += 1
        if self.cham:
            await asyncio.sleep(self.cham)
        if self.hong_ton:
            raise LoiERP("tồn hỏng")
        return TonKho(ban_duoc=5, ma_kho="K")

    async def danh_sach_san_pham(self, chi_ban_duoc: bool = True):
        return [SanPhamERP(ma="A", ten="X")]

    async def suc_khoe(self):
        return True


def chay(coro):
    return asyncio.run(coro)


# =====================================================================
#  1. Ngắt mạch TÁCH theo thao tác
# =====================================================================

def test_ton_kho_hong_KHONG_giet_tra_gia():
    """
    Đây là cả lý do tách mạch.

    Sai quyền kho hay `Bin` chưa có bản ghi làm `ton_kho` hỏng liên tục.
    Bản trước dùng chung một bộ đếm, nên 3 lần hỏng tồn là tra GIÁ cũng
    chết — khách hỏi giá nhận "không biết" vì một sự cố ở chỗ khác.
    """
    n = Nguon(hong_ton=True)
    c = Cong(n, ttl_gia=0.0, ttl_ton=0.0, ngat_mach_so_lan=2, so_lan_thu=1)

    for _ in range(3):
        assert chay(c.ton_kho("A")) is None

    tt = c.trang_thai()
    assert tt["theo_thao_tac"]["ton_kho"]["mach_mo"] is True
    assert tt["theo_thao_tac"]["gia"]["mach_mo"] is False

    # Giá vẫn đọc được bình thường.
    assert chay(c.gia("A")).gia_ban == 1000


def test_trang_thai_gop_bi_quan_mot_thao_tac_mo_la_bao_mo():
    """
    Ba nơi đang đọc `mach_mo` dạng gộp. Người vận hành mở màn hình ra để
    biết "có gì đang hỏng không", nên câu trả lời an toàn là CÓ.
    """
    n = Nguon(hong_ton=True)
    c = Cong(n, ttl_ton=0.0, ngat_mach_so_lan=1, so_lan_thu=1)

    chay(c.ton_kho("A"))

    assert c.trang_thai()["mach_mo"] is True


def test_giu_nguyen_ba_khoa_cu_cho_ba_noi_dang_doc():
    """
    `agent/api/erp.py`, `agent/mcp_server.py`, `agent/suc_khoe.py` và
    dashboard đều đọc ba khoá này. Đổi hình dạng là hỏng ba màn hình.
    """
    tt = Cong(Nguon()).trang_thai()
    for khoa in ("nguon", "mach_mo", "hong_lien_tiep"):
        assert khoa in tt, khoa


# =====================================================================
#  2. Cache có trần
# =====================================================================

def test_cache_khong_lon_qua_tran():
    """
    `dict` thuần lớn mãi: với danh mục vài chục nghìn mã thì đó là rò bộ
    nhớ chạy suốt đời tiến trình — không nổ, chỉ phình.
    """
    n = Nguon()
    c = Cong(n, ttl_gia=9999.0, cache_toi_da=10)

    for i in range(50):
        chay(c.gia(f"MA-{i}"))

    assert c.trang_thai()["so_o_cache"]["gia"] == 10


def test_bo_o_CU_NHAT_chu_khong_bo_bua():
    """LRU: mã vừa được hỏi phải còn lại, mã lâu không ai hỏi thì ra đi."""
    n = Nguon()
    c = Cong(n, ttl_gia=9999.0, cache_toi_da=3)

    for ma in ("A", "B", "C"):
        chay(c.gia(ma))
    chay(c.gia("A"))          # chạm A -> A thành mới nhất
    chay(c.gia("D"))          # đầy -> phải bỏ B (cũ nhất)

    truoc = n.dem["gia"]
    chay(c.gia("A"))          # A còn trong cache -> không gọi ERP
    assert n.dem["gia"] == truoc

    chay(c.gia("B"))          # B đã bị bỏ -> phải gọi lại
    assert n.dem["gia"] == truoc + 1


def test_tran_cache_0_hoac_am_khong_lam_cache_chet():
    """Cấu hình lạ không được biến cache thành vô dụng hoặc ném lỗi."""
    for xau in (0, -5):
        c = Cong(Nguon(), ttl_gia=9999.0, cache_toi_da=xau)
        chay(c.gia("A"))
        assert c.trang_thai()["so_o_cache"]["gia"] >= 1, xau


# =====================================================================
#  3. Chống giẫm đạp cache (single-flight)
# =====================================================================

def test_hai_muoi_khach_cung_hoi_mot_ma_chi_MOT_loi_goi_ERP():
    """
    TTL tồn là 60s. Hết hạn đúng lúc 20 khách cùng hỏi một mã thì bản
    trước bắn 20 lời gọi song song cho CÙNG một câu hỏi.
    """
    async def m():
        n = Nguon(cham=0.15)
        c = Cong(n, ttl_ton=0.0)
        kq = await asyncio.gather(*(c.ton_kho("A") for _ in range(20)))
        return n, kq

    n, kq = chay(m())

    assert n.dem["ton_kho"] == 1
    assert all(x is not None and x.ban_duoc == 5 for x in kq)


def test_hai_ma_khac_nhau_van_di_song_song():
    """Chống giẫm đạp là gộp CÙNG một câu hỏi, không phải xếp hàng tất cả."""
    async def m():
        n = Nguon(cham=0.1)
        c = Cong(n, ttl_ton=0.0)
        await asyncio.gather(c.ton_kho("A"), c.ton_kho("B"), c.ton_kho("C"))
        return n

    assert chay(m()).dem["ton_kho"] == 3


def test_goi_chung_hong_thi_ca_nhom_nhan_None_va_chi_dem_MOT_lan_hong():
    """
    Cả nhóm dùng chung đúng một lời gọi, nên đó là MỘT sự cố. Đếm 20 lần
    là ngắt mạch mở ngay lập tức vì một cú chớp.
    """
    async def m():
        n = Nguon(hong_ton=True, cham=0.05)
        c = Cong(n, ttl_ton=0.0, ngat_mach_so_lan=5, so_lan_thu=1)
        kq = await asyncio.gather(*(c.ton_kho("A") for _ in range(20)))
        return n, c, kq

    n, c, kq = chay(m())

    assert all(x is None for x in kq)
    assert n.dem["ton_kho"] == 1
    assert c.trang_thai()["theo_thao_tac"]["ton_kho"]["hong_lien_tiep"] == 1


def test_khong_ke_dong_lai_sau_khi_loi_goi_xong():
    """
    Rò khoá trong `_dang_bay` thì mã đó vĩnh viễn chờ một future đã xong —
    và triệu chứng là agent treo, không phải báo lỗi.
    """
    async def m():
        n = Nguon()
        c = Cong(n, ttl_ton=0.0)
        await c.ton_kho("A")
        await c.ton_kho("A")
        return n, c

    n, c = chay(m())

    assert n.dem["ton_kho"] == 2          # TTL=0 nên phải gọi lại thật
    assert c._dang_bay == {}
