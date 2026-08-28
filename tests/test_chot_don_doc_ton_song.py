"""Chốt đơn phải đọc tồn kho SỐNG, không đọc cache 60 giây.

Đọc cache ở đúng khoảnh khắc chốt là để khách xác nhận xong mới bị báo hết
hàng — bắt được, nhưng bắt muộn và mất khách.
"""
import pytest

from agent.core import tools
from agent.erp import nha_may
from agent.erp.cong import Cong
from agent.erp.hop_dong import Gia, SanPhamERP, TonKho
from tests.erp_gia import NguonGia, chay


@pytest.fixture
def nguon(monkeypatch):
    n = NguonGia(
        san_pham=[SanPhamERP(ma="AS-CL01", ten="Sữa rửa mặt dịu nhẹ")],
        gia={"AS-CL01": Gia(gia_ban=245000)},
        ton={"AS-CL01": TonKho(ban_duoc=5)},
    )
    nha_may.dat_lai()
    monkeypatch.setattr(nha_may, "tao_nguon", lambda: n)
    yield n
    nha_may.dat_lai()


def test_bo_qua_cache_thi_goi_erp_that(nguon):
    c = Cong(nguon, ttl_ton=3600.0)
    chay(c.ton_kho("AS-CL01"))
    truoc = nguon.so_lan_goi["ton_kho"]
    chay(c.ton_kho("AS-CL01", bo_qua_cache=True))
    assert nguon.so_lan_goi["ton_kho"] == truoc + 1


def test_ton_song_khong_tra_duoc_thi_khong_chot_don(nguon):
    # Không biết còn bao nhiêu thì KHÔNG được chốt. Chốt liều là bán món có
    # thể đã hết, và khách chỉ biết khi không nhận được hàng.
    nguon.hong = True
    kq = chay(
        tools.run_tool(
            "tao_don_hang",
            {
                "khach_da_xac_nhan": True,
                "khach_ten": "Nguyễn Văn A",
                "khach_sdt": "0901234567",
                "khach_dia_chi": "12 Nguyễn Trãi, Thanh Xuân, Hà Nội",
                "items": [{"ten_san_pham": "sữa rửa mặt", "so_luong": 1}],
            },
            conversation_id=None,
        )
    )
    assert kq.get("tao_duoc") is False
    ly_do = kq.get("ly_do", "").lower()
    assert "tồn kho" in ly_do or "chưa tra được" in ly_do
