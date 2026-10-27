"""
`san_sang` phải nói khi vận chuyển đang chạy bằng nhà cung cấp GIẢ.

LỖI THẬT, ĐO ĐƯỢC 15.09.2026
---------------------------
`SHIPPING_PROVIDER=mock`, `GHN_TOKEN` rỗng, `GHN_SHOP_ID` rỗng — và KHÔNG
mục nào trong `san_sang`, `suc_khoe`, hay dashboard nói ra. Bảng vẫn xanh
hết.

`MockShippingProvider.tao_van_don()` trả về một mã vận đơn trông như thật.
Nhân viên bấm tạo vận đơn, nhận mã, nhắn mã ấy cho khách — và hãng vận
chuyển chưa bao giờ nghe nói tới đơn này. Khách tra mã trên web GHN thì
không thấy gì. Không lỗi, không nhật ký, và chỉ vỡ ra khi khách hỏi "sao
mã này không tra được".

Đúng khuôn của `ERP_LOAI=tep`: một nhà cung cấp giả rất hữu ích lúc dựng
hệ thống, và rất nguy hiểm khi không ai nhớ là nó đang bật.

VÌ SAO LÀ CẢNH BÁO CHỨ KHÔNG PHẢI CHẶN
--------------------------------------
Cửa hàng tự đi gửi hàng, không dùng hãng nào, là một cách vận hành hợp lệ.
Chặn ở đó là bắt họ cấu hình một thứ họ không dùng. Cảnh báo thì nói đúng
sự thật và để người quyết.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.san_sang import CANH_BAO, CHAN, DU, doc_van_chuyen  # noqa: E402


def test_nha_cung_cap_gia_thi_canh_bao():
    m = doc_van_chuyen(provider="mock", co_token=False, co_shop_id=False, url="")
    assert m["muc"] == CANH_BAO
    assert "giả" in m["ghi"].lower() or "mock" in m["ghi"].lower()


def test_noi_ro_hau_qua_chu_khong_chi_neu_ten_cau_hinh():
    """
    "SHIPPING_PROVIDER=mock" là một sự thật kỹ thuật. Người trực cần biết
    HẬU QUẢ: mã vận đơn phát ra không tra được ở đâu cả.
    """
    m = doc_van_chuyen(provider="mock", co_token=False, co_shop_id=False, url="")
    chu = (m["ghi"] + " " + m.get("sua", "")).lower()
    assert "vận đơn" in chu


def test_ghn_du_cau_hinh_thi_du():
    m = doc_van_chuyen(provider="ghn", co_token=True, co_shop_id=True,
                       url="https://online-gateway.ghn.vn/shiip/public-api/v2")
    assert m["muc"] == DU


def test_ghn_thieu_token_thi_chan():
    """Bật GHN mà thiếu khoá là cấu hình MÂU THUẪN: mỗi lần tạo vận đơn sẽ
    hỏng, và đơn nào cũng hỏng."""
    m = doc_van_chuyen(provider="ghn", co_token=False, co_shop_id=True, url="x")
    assert m["muc"] == CHAN


def test_ghn_thieu_shop_id_thi_chan():
    m = doc_van_chuyen(provider="ghn", co_token=True, co_shop_id=False, url="x")
    assert m["muc"] == CHAN


def test_ghn_tro_vao_moi_truong_thu_thi_canh_bao():
    """
    `dev-online-gateway` là sandbox của GHN. Đủ khoá, gọi thành công, trả
    mã vận đơn — nhưng không có kiện hàng nào được lấy. Xanh hoàn toàn và
    sai hoàn toàn.
    """
    m = doc_van_chuyen(provider="ghn", co_token=True, co_shop_id=True,
                       url="https://dev-online-gateway.ghn.vn/shiip/public-api/v2")
    assert m["muc"] == CANH_BAO
    chu = (m["ghi"] + " " + m.get("sua", "")).lower()
    assert "thử" in chu or "sandbox" in chu or "dev" in chu


@pytest.mark.parametrize("provider", ["", "khong_dung"])
def test_khong_dung_hang_nao_thi_khong_bat_loi(provider):
    """Cửa hàng tự đi gửi hàng là cách vận hành hợp lệ — đừng bắt họ cấu
    hình thứ họ không dùng."""
    m = doc_van_chuyen(provider=provider, co_token=False, co_shop_id=False, url="")
    assert m["muc"] in (DU, CANH_BAO)


def test_muc_nay_co_trong_bang_san_sang():
    """Viết hàm mà không gọi thì bảng vẫn xanh y như cũ."""
    import inspect

    from scripts import san_sang

    # Bảng nằm trong `chay()`; `main()` chỉ bọc asyncio.run quanh nó.
    assert "kiem_van_chuyen" in inspect.getsource(san_sang.chay)


# ------------------------------------------------------------------ GHTK

def test_ghtk_staging_thi_canh_bao():
    m = doc_van_chuyen(provider="ghtk", co_token=True, co_shop_id=True,
                       url="https://services-staging.ghtklab.com",
                       ten_token="GHTK_TOKEN", ten_shop="GHTK_KHO_ID")
    assert m["muc"] == CANH_BAO


def test_ghtk_that_du_khoa_thi_du():
    m = doc_van_chuyen(provider="ghtk", co_token=True, co_shop_id=True,
                       url="https://services.giaohangtietkiem.vn",
                       ten_token="GHTK_TOKEN", ten_shop="GHTK_KHO_ID")
    assert m["muc"] == DU


def _gia_lap(monkeypatch, provider: str, khoa: dict[str, str]):
    from agent import cau_hinh_dong
    from scripts import san_sang

    monkeypatch.setattr(san_sang.settings, "shipping_provider", provider)
    monkeypatch.setattr(cau_hinh_dong, "lay", lambda k: khoa.get(k, ""))
    return san_sang.kiem_van_chuyen()


def test_ghtk_thieu_token_chi_dung_ten_khoa_GHTK(monkeypatch):
    m = _gia_lap(monkeypatch, "ghtk", {"GHTK_KHO_ID": "1"})
    assert m["muc"] == CHAN and "GHTK_TOKEN" in m["ghi"] and "GHN" not in m["ghi"]


def test_ghtk_dia_chi_lay_hang_thay_cho_ma_kho(monkeypatch):
    from agent.shipping.ghtk import KHOA_LAY_HANG

    m = _gia_lap(monkeypatch, "ghtk", {"GHTK_TOKEN": "t", **dict.fromkeys(KHOA_LAY_HANG, "x")})
    assert m["muc"] != CHAN


def test_khoa_dien_tren_dashboard_duoc_tinh(monkeypatch):
    """
    Token điền trên dashboard nằm trong CSDL, không trong .env. Đọc thẳng
    settings là báo CHẶN "thiếu token" cho cửa hàng đã cấu hình đúng — đỏ
    giả, và một bảng đỏ giả là bảng người ta thôi đọc.
    """
    monkeypatch.setattr("scripts.san_sang.settings.ghn_token", "")
    m = _gia_lap(monkeypatch, "ghn", {"GHN_TOKEN": "tu-dashboard", "GHN_SHOP_ID": "1"})
    assert m["muc"] != CHAN
