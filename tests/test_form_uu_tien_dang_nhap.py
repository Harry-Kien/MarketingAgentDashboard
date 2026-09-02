"""
Kênh nối được bằng đăng nhập thì form KHÔNG được đòi dán token.

MÂU THUẪN ĐO ĐƯỢC TRÊN MÀN HÌNH
--------------------------------
Trang "Thêm tài khoản" có nút lớn "Kết nối Facebook / Instagram bằng đăng
nhập — hệ thống tự nhận token, không phải dán tay". Ngay dưới nó, chọn kênh
Instagram thì form hiện bốn ô bắt buộc: Instagram business ID, Access token,
App secret, Verify token.

Hai thứ nói ngược nhau trên cùng một màn hình. Người dùng đọc cái nào trước
thì làm theo cái đó — và cái dễ đọc hơn là form ngay trước mắt.

Hậu quả không phải chỉ mất thời gian. Đi đường dán tay nghĩa là:

  - phải tự tạo ứng dụng Meta, tự sinh Page token, tự đặt verify token
  - token dán tay là token dài hạn KHÔNG tự gia hạn — vài tuần sau nó hết
    hạn và kênh chết câm, không ai biết cho tới khi khách kêu
  - `app_secret` đi qua trình duyệt, trong khi đường đăng nhập giữ nó ở máy
    chủ suốt

VÌ SAO KHÔNG XOÁ HẲN Ô NHẬP TAY
--------------------------------
Vẫn có ca cần: app Meta chưa được duyệt, tài khoản đặc biệt, hoặc gỡ lỗi.
Nên nó chuyển thành đường phụ — đóng sẵn, mở ra khi thật sự cần — chứ không
biến mất.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")


def _khoi_kenh(ten: str) -> str:
    return JS.split(f"  {ten}: {{", 1)[1].split("\n  },", 1)[0]


def test_facebook_va_instagram_duoc_danh_dau_co_dang_nhap():
    for kenh in ("facebook", "instagram"):
        assert "dang_nhap: true" in _khoi_kenh(kenh), (
            f"{kenh} chưa được đánh dấu là nối được bằng đăng nhập"
        )


def test_kenh_khong_co_oauth_thi_khong_bi_danh_dau():
    """
    Zalo OA và WhatsApp thật sự phải nhập tay — đánh dấu nhầm là giấu mất
    những ô người dùng bắt buộc phải điền.
    """
    for kenh in ("zalo_oa", "whatsapp"):
        assert "dang_nhap: true" not in _khoi_kenh(kenh)


def test_co_loi_nhac_dung_nut_dang_nhap():
    assert "khuyen-dang-nhap" in JS, "chưa có lời nhắc dùng đường đăng nhập"


def test_o_nhap_tay_dong_san_cho_kenh_co_oauth():
    """Đóng sẵn, không xoá: vẫn có ca cần nhập tay khi app chưa được duyệt."""
    assert "nhap-tay" in JS
    assert "<details" in HTML or "details" in JS


def test_khong_bat_buoc_o_nao_khi_dang_dong():
    """
    Ô `required` nằm trong khối đang đóng thì trình duyệt CHẶN gửi form mà
    không hiện được lỗi ở đâu cả — người dùng bấm Lưu và không có gì xảy ra.

    Đây là lỗi kinh điển của `<details>` + `required`.
    """
    khoi = JS.split("function veFormKenh", 1)[1][:2600]
    assert "required = " in khoi
    assert "dang_nhap" in khoi, "veFormKenh chưa xét cờ dang_nhap"


def test_van_giu_goi_y_lay_gia_tri_o_dau():
    """Mở phần nâng cao ra thì vẫn phải biết lấy từng giá trị ở đâu."""
    assert "goi_y" in JS


def test_nut_dang_nhap_van_ton_tai():
    assert "btn-oauth-meta" in JS
