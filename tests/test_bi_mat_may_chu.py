"""
Bí mật của MÁY CHỦ thì máy chủ tự điền — không bắt người dùng đi chép.

VÌ SAO
------
`ZALO_SIDECAR_SECRET` là chuỗi ký HMAC giữa app và sidecar. Nó thuộc về
MÁY CHỦ: mọi tài khoản Zalo dùng chung đúng một giá trị, và giá trị đó nằm
trong `.env` của người vận hành.

Form kết nối trước đây ghi: "Mở file .env trong thư mục dự án, copy giá trị
dòng ZALO_SIDECAR_SECRET". Điều đó có ba cái sai:

  1. Người dùng KHÔNG có `.env` — đó là file của máy chủ. Khi hệ thống chạy
     trên tên miền cho nhiều người thì yêu cầu này bất khả thi.
  2. Bắt chép tay một chuỗi 32 ký tự là mời gọi sai một byte. HMAC sai một
     byte thì sidecar từ chối, và Zalo không bao giờ báo gì cả.
  3. Bí mật máy chủ đi qua trình duyệt là nới rộng vùng lộ mà không đổi lại
     được gì — nó vốn đã nằm sẵn ở máy chủ.

CHẶN HỎNG IM LẶNG
-----------------
Máy chủ chưa cấu hình secret thì phải NÉM, không được điền chuỗi rỗng. Tài
khoản tạo với secret rỗng trông y hệt tài khoản tốt trên dashboard — chỉ có
QR là không bao giờ quét được, và không có dòng lỗi nào ở đâu.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_dien_du_ca_secret_lan_url():
    from agent.omnichannel.bi_mat_may_chu import bo_sung_bi_mat_may_chu
    from agent.omnichannel.accounts import Channel

    ra = bo_sung_bi_mat_may_chu(
        Channel.ZALO_PERSONAL, {}, secret="S-MAY-CHU", url="http://sidecar:3210",
    )
    assert ra["sidecar_secret"] == "S-MAY-CHU"
    assert ra["sidecar_url"] == "http://sidecar:3210"


def test_de_len_gia_tri_client_gui_vao():
    """
    Chỉ có ĐÚNG MỘT giá trị đúng, và máy chủ giữ nó.

    Tôn trọng thứ client gửi lên là để một giá trị sai đi vào vault, rồi
    hỏng ở tận bước quét QR — xa chỗ gây lỗi hàng chục thao tác.
    """
    from agent.omnichannel.bi_mat_may_chu import bo_sung_bi_mat_may_chu
    from agent.omnichannel.accounts import Channel

    ra = bo_sung_bi_mat_may_chu(
        Channel.ZALO_PERSONAL,
        {"sidecar_secret": "RAC", "sidecar_url": "http://ke-tan-cong"},
        secret="S-MAY-CHU", url="http://sidecar:3210",
    )
    assert ra["sidecar_secret"] == "S-MAY-CHU"
    assert ra["sidecar_url"] == "http://sidecar:3210"


def test_may_chu_chua_cau_hinh_thi_NEM_chu_khong_dien_rong():
    from agent.omnichannel.bi_mat_may_chu import (
        ThieuBiMatMayChu,
        bo_sung_bi_mat_may_chu,
    )
    from agent.omnichannel.accounts import Channel

    with pytest.raises(ThieuBiMatMayChu):
        bo_sung_bi_mat_may_chu(Channel.ZALO_PERSONAL, {}, secret="", url="http://x")


def test_khoang_trang_thua_trong_env_bi_cat():
    """Dán vào .env thường dính dấu cách cuối. HMAC sai một byte là hỏng."""
    from agent.omnichannel.bi_mat_may_chu import ThieuBiMatMayChu, bo_sung_bi_mat_may_chu
    from agent.omnichannel.accounts import Channel

    ra = bo_sung_bi_mat_may_chu(
        Channel.ZALO_PERSONAL, {}, secret="  S  ", url="  http://s:1  ")
    assert ra["sidecar_secret"] == "S"
    assert ra["sidecar_url"] == "http://s:1"

    with pytest.raises(ThieuBiMatMayChu):
        bo_sung_bi_mat_may_chu(Channel.ZALO_PERSONAL, {}, secret="   ", url="http://x")


def test_kenh_khac_khong_bi_dung_toi():
    """Facebook có credential riêng của Trang — máy chủ không được chen vào."""
    from agent.omnichannel.bi_mat_may_chu import bo_sung_bi_mat_may_chu
    from agent.omnichannel.accounts import Channel

    goc = {"access_token": "T", "app_secret": "A"}
    ra = bo_sung_bi_mat_may_chu(Channel.FACEBOOK, goc, secret="S", url="U")
    assert ra == goc
    assert "sidecar_secret" not in ra


def test_khong_sua_dict_goc():
    """Sửa tại chỗ là đổi dữ liệu của người gọi sau lưng họ."""
    from agent.omnichannel.bi_mat_may_chu import bo_sung_bi_mat_may_chu
    from agent.omnichannel.accounts import Channel

    goc = {}
    bo_sung_bi_mat_may_chu(Channel.ZALO_PERSONAL, goc, secret="S", url="U")
    assert goc == {}


def test_credentials_None_van_chay_duoc():
    """Form không gửi credentials cho Zalo nữa — None là đường đi bình thường."""
    from agent.omnichannel.bi_mat_may_chu import bo_sung_bi_mat_may_chu
    from agent.omnichannel.accounts import Channel

    ra = bo_sung_bi_mat_may_chu(Channel.ZALO_PERSONAL, None, secret="S", url="U")
    assert ra["sidecar_secret"] == "S"


# --- Ràng buộc phải được GẮN VÀO ĐƯỜNG CHẠY, không chỉ tồn tại ---

def test_route_tao_tai_khoan_co_goi():
    from agent.api import channel_accounts

    assert "bo_sung_bi_mat_may_chu" in inspect.getsource(channel_accounts.create_account)


def test_route_doi_credential_cung_goi():
    """Đổi credential mà không bổ sung là ghi đè secret đúng bằng rỗng."""
    from agent.api import channel_accounts

    nguon = inspect.getsource(channel_accounts.rotate_credentials)
    assert "bo_sung_bi_mat_may_chu" in nguon


def test_form_khong_con_hoi_sidecar_secret():
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    khoi = js.split("zalo_personal:", 1)[1].split("zalo_oa:", 1)[0]
    assert "secondary_secret" not in khoi, "form vẫn hỏi bí mật của máy chủ"


def test_dashboard_khong_con_gan_cung_dia_chi_sidecar():
    """
    Địa chỉ sidecar là cấu hình triển khai. Gán cứng trong trình duyệt thì
    lên tên miền là sai, và sai một cách im lặng.
    """
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert "127.0.0.1:3210" not in js


def test_env_example_khai_bao_dia_chi_sidecar():
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "ZALO_SIDECAR_URL" in env
