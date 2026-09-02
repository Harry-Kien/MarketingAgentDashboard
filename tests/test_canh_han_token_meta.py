"""
Báo TRƯỚC khi Page token Meta hết hạn, thay vì phát hiện sau khi tin ngừng về.

ĐO ĐƯỢC TRÊN TÀI KHOẢN THẬT
---------------------------
    Homeseeker: token CÒN SỐNG
       hạn dùng: VĨNH VIỄN (token dài hạn)
       hạn truy cập dữ liệu: 2026-11-24

Token thì vĩnh viễn — Facebook Login for Business trả token dài hạn ngay,
khác Facebook Login cổ điển vốn cần `fb_exchange_token`. Nhưng
`data_access_expires_at` thì CÓ hạn: sau mốc đó app mất quyền đọc dữ liệu
trừ khi chủ Trang cấp quyền lại.

Và trước file này, không có gì trong hệ thống theo dõi mốc ấy.

KHI TỚI HẠN THÌ HỎNG THẾ NÀO
----------------------------
Trang vẫn hiện xanh trên dashboard. Webhook vẫn đăng ký. Chỉ có Graph bắt
đầu trả `OAuthException`, tin khách không về nữa, tin gửi đi thì hỏng — tất
cả cùng một lúc, không báo trước.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from agent.channels.suc_khoe_token_meta import (
    NGAY_BAO_TRUOC,
    doc_suc_khoe,
    hoi_meta,
)

BAY_GIO = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def _moc(ngay: float) -> int:
    return int((BAY_GIO + timedelta(days=ngay)).timestamp())


def _du_lieu(**doi):
    goc = {"is_valid": True, "expires_at": 0, "data_access_expires_at": 0}
    goc.update(doi)
    return {"data": goc}


def test_token_vinh_vien_va_du_lieu_con_lau_thi_ON():
    kq = doc_suc_khoe(_du_lieu(data_access_expires_at=_moc(90)), bay_gio=BAY_GIO)
    assert kq["muc"] == "on"


def test_sap_het_han_TRUY_CAP_DU_LIEU_van_phai_bao():
    """
    Đây là ca THẬT của hệ thống này: token vĩnh viễn, nhưng quyền truy cập
    dữ liệu hết hạn. Chỉ nhìn `expires_at` là bỏ sót hoàn toàn.
    """
    kq = doc_suc_khoe(_du_lieu(data_access_expires_at=_moc(10)), bay_gio=BAY_GIO)
    assert kq["muc"] == "sap_het"
    assert 9 < kq["ngay_con_lai"] < 11


def test_lay_moc_GAN_NHAT_trong_hai_moc():
    """Cái nào tới trước thì cái đó làm chết kết nối trước."""
    kq = doc_suc_khoe(
        _du_lieu(expires_at=_moc(5), data_access_expires_at=_moc(60)),
        bay_gio=BAY_GIO)
    assert kq["muc"] == "sap_het"
    assert 4 < kq["ngay_con_lai"] < 6


def test_da_qua_han_thi_bao_CHET():
    kq = doc_suc_khoe(_du_lieu(data_access_expires_at=_moc(-1)), bay_gio=BAY_GIO)
    assert kq["muc"] == "chet"


def test_meta_bao_khong_hop_le_thi_CHET_ngay():
    kq = doc_suc_khoe(_du_lieu(is_valid=False), bay_gio=BAY_GIO)
    assert kq["muc"] == "chet"


@pytest.mark.parametrize("ngay,mong", [
    (NGAY_BAO_TRUOC - 1, "sap_het"),
    (NGAY_BAO_TRUOC + 1, "on"),
])
def test_nguong_bao_truoc_dung_chan(ngay, mong):
    kq = doc_suc_khoe(_du_lieu(data_access_expires_at=_moc(ngay)), bay_gio=BAY_GIO)
    assert kq["muc"] == mong


def test_bao_truoc_du_lau_de_hen_duoc_chu_trang():
    """
    Cấp quyền lại cần CHỦ TRANG thao tác, không phải người trực. Báo trước
    một ngày là báo cho người không tự xử lý được.
    """
    assert NGAY_BAO_TRUOC >= 7


def test_phan_hoi_di_dang_khong_lam_no():
    """Meta đổi hình dạng phản hồi thì cũng không được làm chết vòng nền."""
    for xau in ({}, {"data": None}, {"data": {"expires_at": "abc"}}):
        assert doc_suc_khoe(xau)["muc"] in ("on", "chet", "sap_het")


# --- Gọi mạng: không bao giờ ném ---

class _Client:
    def __init__(self, tra=None, no=None):
        self.calls = []
        self._tra = tra
        self._no = no

    async def get(self, duong, params=None):
        self.calls.append((duong, params or {}))
        if self._no:
            raise self._no
        return self._tra

    async def aclose(self):
        return None


class _R:
    def __init__(self, data, status_code=200):
        self._d = data
        self.status_code = status_code

    def json(self):
        return self._d


def test_mang_hong_tra_None_chu_khong_bao_dong_gia():
    """
    Mạng hỏng biến thành "token chết" là người trực đi cấp quyền lại cho một
    token vẫn tốt — rồi lần sau họ bỏ qua cảnh báo thật.
    """
    import asyncio

    kq = asyncio.run(hoi_meta(token="T", app_id="A", app_secret="S",
                              client=_Client(no=RuntimeError("mat mang"))))
    assert kq is None


def test_thieu_bi_mat_thi_khong_goi_mang():
    import asyncio

    c = _Client(_R(_du_lieu()))
    assert asyncio.run(hoi_meta(token="", app_id="A", app_secret="S", client=c)) is None
    assert c.calls == []


def test_dung_app_token_chu_khong_dung_page_token():
    """`debug_token` phải được gọi bằng token của ỨNG DỤNG, không phải token
    đang đi soi — soi bằng chính nó thì Meta từ chối."""
    import asyncio

    c = _Client(_R(_du_lieu()))
    asyncio.run(hoi_meta(token="PAGE", app_id="APP", app_secret="SEC", client=c))
    _duong, params = c.calls[0]
    assert params["input_token"] == "PAGE"
    assert params["access_token"] == "APP|SEC"


# --- Phải nằm trên đường chạy ---

def test_vong_nen_duoc_dung_luc_khoi_dong():
    """Có vòng mà không ai dựng là mã chết — đã gặp bốn lần trong dự án này."""
    from agent import main

    assert "canh_han_token_meta_loop()" in inspect.getsource(main.lifespan)


def test_vong_nen_khong_chet_khi_gap_loi():
    from agent import main

    nguon = inspect.getsource(main.canh_han_token_meta_loop)
    assert "except Exception" in nguon
    assert "while True" in nguon


def test_kiem_ngay_lan_dau_roi_moi_ngu():
    """
    Khởi động lại là lúc người vận hành đang nhìn màn hình. Ngủ 24 giờ trước
    lần kiểm đầu tiên nghĩa là token sắp chết vẫn im lặng thêm một ngày.
    """
    from agent import main

    nguon = inspect.getsource(main.canh_han_token_meta_loop)
    than = nguon.split("while True:", 1)[1]
    assert than.index("asyncio.sleep") > than.index("hoi_meta")


def test_bao_ca_nhat_ky_lan_bao_dong_ra_ngoai():
    from agent import main

    nguon = inspect.getsource(main.canh_han_token_meta_loop)
    assert "log_event" in nguon
    assert "canh_gac.bao_dong" in nguon
