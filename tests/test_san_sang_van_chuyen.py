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
