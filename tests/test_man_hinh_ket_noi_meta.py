"""
Màn hình Kết nối với NHIỀU Trang Meta: gom việc chung, đừng nhân lên 26 lần.

VẤN ĐỀ ĐO ĐƯỢC
--------------
Sau khi nối OAuth, người dùng có 26 Trang Facebook. Màn hình cũ hiện, cho
MỖI Trang:

  - một URL callback riêng dài hơn 100 ký tự
  - nút "Verify token"
  - nút "Nhận tin"
  - nút "Xác minh provider"

Tức 26 URL và 78 nút. Nhưng hai trong ba thứ đó KHÔNG hề riêng theo Trang:

  URL callback  -> Meta chỉ cho khai MỘT cho mỗi app. Hệ thống đã có đường
                   dùng chung `/webhook/native/meta` tự phân phát về đúng
                   Trang. 26 URL kia không ai cần tới.
  verify token  -> dùng CHUNG cho mọi Trang của cùng một app — chính
                   `oauth_meta` ghi vậy khi tạo chúng.

Hiện 26 bản của một thứ duy nhất không chỉ rối: nó khiến người dùng tin rằng
phải khai 26 lần bên Meta, rồi bỏ dở giữa chừng.

Chỉ `Xác minh provider` là thật sự theo từng Trang — mỗi Trang một token
riêng, và token có thể hỏng riêng.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def test_meta_dung_MOT_url_callback_chung():
    """
    Đường dùng chung đã tồn tại. Không dùng nó là bắt người ta khai 26 lần
    một thứ Meta chỉ nhận một lần.
    """
    assert "/webhook/native/meta`" in JS or '"/webhook/native/meta"' in JS, (
        "chưa dùng đường callback chung cho Meta"
    )


def test_khong_hien_url_rieng_cho_tung_trang_meta():
    from agent.omnichannel.accounts import Channel

    assert Channel.FACEBOOK.value == "facebook"
    # URL riêng theo account chỉ còn dành cho kênh KHÔNG phải Meta.
    khoi = JS.split("function connectionCallback", 1)[1].split("\n}", 1)[0]
    assert "webhook/native/meta/${account.id}" not in khoi, (
        "vẫn dựng URL riêng cho từng Trang Meta"
    )


def test_co_nut_nhan_tin_cho_TAT_CA():
    """26 Trang × bấm tay từng cái là việc không ai làm hết được."""
    assert "data-subwebhook-all" in JS, "thiếu nút đăng ký webhook hàng loạt"


def test_bao_ket_qua_tung_trang_khi_lam_hang_loat():
    """
    Làm hàng loạt mà chỉ báo "xong" là che mất Trang hỏng.

    Đúng kiểu xanh giả: người dùng đóng màn hình, yên tâm, rồi vài ngày sau
    mới biết bốn Trang chưa từng nhận tin nào.
    """
    # Lấy khối XỬ LÝ (nơi gắn sự kiện), không phải khối DỰNG HTML — chuỗi
    # "data-subwebhook-all" xuất hiện ở cả hai chỗ.
    khoi = JS.split('$$("[data-subwebhook-all]")', 1)[1][:3000]
    assert "hong" in khoi, "không tách được Trang thành công và Trang hỏng"
    assert "HỎNG" in khoi, "không báo ra số Trang hỏng cho người dùng"


def test_verify_token_gom_ve_muc_kenh():
    """Một verify token cho cả app — 26 nút mở ra cùng một chuỗi là vô nghĩa."""
    assert "data-verifytoken-kenh" in JS


def test_van_giu_xac_minh_provider_theo_TUNG_trang():
    """
    Đây là thứ DUY NHẤT thật sự riêng: mỗi Trang một token, hỏng riêng.

    Gom nó lại là mất khả năng biết Trang nào hỏng.
    """
    assert "data-verify=" in JS


def test_thu_gon_khi_qua_nhieu_tai_khoan():
    """
    Một tài khoản Facebook quản lý được hàng chục Trang. Đổ hết ra thì Zalo
    và Webchat bị đẩy khỏi tầm nhìn, và người trực cuộn rất lâu mới tới.
    """
    assert "SO_HIEN_SAN" in JS, "chưa có ngưỡng thu gọn"
    assert "is-thu-gon" in JS


def test_co_duong_mo_lai_phan_da_thu_gon():
    """Thu gọn mà không mở lại được là giấu mất tài khoản."""
    assert "data-mo=" in JS
    assert "Xem thêm" in JS


def test_css_khai_bao_kieu_thu_gon():
    """Có class trong JS mà không có CSS thì thu gọn chẳng xảy ra gì."""
    css = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")
    assert ".channel-card__body.is-thu-gon" in css
    assert ".channel-card__them" in css
