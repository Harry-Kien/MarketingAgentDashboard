"""Hai lỗ hổng tìm được khi rà lại kiến trúc, không phải khi viết mã.

LỖ 1 — SỔ CÁI NỘI BỘ GHI ĐÈ SỐ CỦA ERP
--------------------------------------
`_catalog_song()` lấy danh mục từ cổng (đã có tồn kho ERP), rồi dòng cuối
chồng bảng `ton_kho` nội bộ lên. Nghĩa là toàn bộ đường đọc tồn kho từ ERP
bị vô hiệu ở đúng dòng cuối cùng.

Hậu quả không nổ, nó LỆCH: agent tư vấn bằng số nội bộ ("còn 84"), rồi chốt
đơn đọc tồn sống từ ERP ("hết hàng"). Khách xác nhận xong mới bị từ chối.

Đây đúng là bài toán hai sổ cái mà thiết kế mục 7.2 sinh ra để tránh — và nó
sống sót vì test hợp đồng kiểm `Cong.danh_muc()` trực tiếp, không kiểm dòng
nối ở `tools.py`.

LỖ 2 — N+1 KHI NẠP DANH MỤC
---------------------------
`danh_muc()` gọi `gia()` và `ton_kho()` cho TỪNG sản phẩm, NỐI TIẾP. 22 SKU
= 45 lời gọi. Đo thật với độ trễ 150ms/lời gọi: 6,9 giây cho một lần nạp, và
lặp lại mỗi khi cache tồn kho hết hạn (60 giây).

Ở contact center nghĩa là cứ mỗi phút, một khách phải chờ 7 giây. Cửa hàng
100 SKU thì 31 giây.
"""
from __future__ import annotations

import asyncio
import time

from agent.config import settings
from agent.erp.cong import Cong
from agent.erp.hop_dong import Gia, SanPhamERP, TonKho
from tests.erp_gia import NguonGia, chay


def _nguon(so_sku: int = 22, do_tre: float = 0.0):
    class N(NguonGia):
        async def gia(self, ma):
            if do_tre:
                await asyncio.sleep(do_tre)
            return await super().gia(ma)

        async def ton_kho(self, ma):
            if do_tre:
                await asyncio.sleep(do_tre)
            return await super().ton_kho(ma)

    ma = [f"SP-{i:03d}" for i in range(so_sku)]
    return N(
        san_pham=[SanPhamERP(ma=m, ten=f"Món {m}") for m in ma],
        gia={m: Gia(gia_ban=100_000) for m in ma},
        ton={m: TonKho(ban_duoc=5) for m in ma},
    )


# =====================================================================
#  LỖ 1: sổ cái nội bộ không được ghi đè số của ERP
# =====================================================================

def test_khi_noi_ERP_thi_ton_kho_noi_bo_KHONG_duoc_ghi_de(monkeypatch, tmp_path):
    from agent.core import tools
    from agent.erp import nha_may

    ho_so = tmp_path / "catalog.json"
    ho_so.write_text(
        '{"san_pham": [{"ma": "SP-000", "da_phu_hop": ["da dầu"]}]}',
        encoding="utf-8",
    )
    n = _nguon(1)
    n.bang_ton["SP-000"] = TonKho(ban_duoc=3)      # ERP nói còn 3

    monkeypatch.setattr(settings, "erp_loai", "erpnext")
    nha_may.dat_lai()
    nha_may._cong = Cong(n, duong_dan_tu_van=ho_so)

    async def _kho_noi_bo_noi_khac():
        return {"SP-000": 99}                       # bảng nội bộ nói còn 99

    monkeypatch.setattr("agent.core.kho.lay_tat_ca", _kho_noi_bo_noi_khac)

    d = chay(tools._catalog_song())
    nha_may.dat_lai()

    sp = [x for x in d["san_pham"] if x["ma"] == "SP-000"][0]
    assert sp["ton_kho"] == 3, (
        "Số của ERP bị bảng ton_kho nội bộ ghi đè. Agent sẽ tư vấn bằng số "
        "nội bộ rồi chốt đơn bằng số ERP — hai con số, một khách."
    )


def test_khi_dung_tep_thi_van_chong_ton_kho_song_len(monkeypatch, tmp_path):
    # Với nguồn `tep`, bảng nội bộ CHÍNH LÀ tồn kho sống — file JSON chỉ giữ
    # con số của ngày ai đó sửa nó. Giữ nguyên hành vi cũ ở nhánh này.
    from agent.core import tools
    from agent.erp import nha_may

    monkeypatch.setattr(settings, "erp_loai", "tep")
    nha_may.dat_lai()

    async def _kho_noi_bo():
        return {"AS-CL01": 7}

    monkeypatch.setattr("agent.core.kho.lay_tat_ca", _kho_noi_bo)
    d = chay(tools._catalog_song())
    nha_may.dat_lai()

    sp = [x for x in d["san_pham"] if x["ma"] == "AS-CL01"]
    assert sp and sp[0]["ton_kho"] == 7


# =====================================================================
#  LỖ 2: N+1 khi nạp danh mục
# =====================================================================

def test_nap_danh_muc_goi_song_song_khong_noi_tiep():
    # 22 SKU × 2 lời gọi × 50ms. Nối tiếp là ~2,2 giây; song song phải dưới
    # nửa giây. Ngưỡng đặt rộng để không đỏ vì máy CI chậm.
    c = Cong(_nguon(22, do_tre=0.05), ttl_ton=60.0)
    t0 = time.perf_counter()
    chay(c.danh_muc())
    mat = time.perf_counter() - t0
    assert mat < 1.0, (
        f"Nạp danh mục mất {mat:.1f}s — đang gọi ERP nối tiếp. Ở contact "
        "center, cứ mỗi lần cache hết hạn là một khách phải chờ chừng ấy."
    )


def test_van_gọi_du_moi_san_pham():
    # Song song không được đổi lấy việc bỏ sót sản phẩm.
    n = _nguon(22)
    c = Cong(n, ttl_ton=60.0)
    d = chay(c.danh_muc())
    assert n.so_lan_goi["gia"] == 22
    assert n.so_lan_goi["ton_kho"] == 22
    assert len(d["san_pham"]) == 22


def test_cache_van_hieu_luc_sau_khi_song_song_hoa():
    n = _nguon(5)
    c = Cong(n, ttl_ton=3600.0, ttl_gia=3600.0)
    chay(c.danh_muc())
    n.so_lan_goi.clear()
    chay(c.danh_muc())
    assert "gia" not in n.so_lan_goi
    assert "ton_kho" not in n.so_lan_goi


def test_mot_san_pham_hong_khong_lam_hong_ca_danh_muc():
    n = _nguon(5)
    n.bang_gia.pop("SP-002")          # món này không có giá
    d = chay(Cong(n).danh_muc())
    ma = {sp["ma"] for sp in d["san_pham"]}
    assert "SP-002" not in ma
    assert len(ma) == 4
