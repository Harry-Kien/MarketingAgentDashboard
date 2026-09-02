"""Dashboard chính chỉ dùng surface native của repo và không lộ branding demo."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_index_co_unified_inbox_customer360_va_multi_account_native():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert 'data-view="hoithoai"' in html
    assert 'data-view="khachhang"' in html
    assert 'data-view="ketnoi"' in html
    assert 'id="connectiongrid"' in html
    assert 'id="contactlist"' in html
    assert "<iframe" not in html.lower()
    for foreign_brand in ("ZaloCRM", "Chatwoot", "Aurora Skin"):
        assert foreign_brand not in html
    assert "Nick Zalo trả lời" not in html
    assert "Tài khoản trả lời" in html


def test_javascript_goi_api_native_thay_vi_iframe_he_thong_tham_khao():
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    for endpoint in (
        "/inbox/conversations",
        "/contacts",
        "/channel-accounts",
        "/verify",
    ):
        assert endpoint in js
    assert "/tich-hop/" not in js
    assert "knFrames" not in js
    for foreign_brand in ("ZaloCRM", "Chatwoot", "Aurora Skin"):
        assert foreign_brand not in js


def test_customer360_co_thao_tac_tag_ghi_chu_va_consent():
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    for endpoint_fragment in ("/tags", "/notes", "/consents/"):
        assert endpoint_fragment in js
    for form_id in ("contact-tag-form", "contact-note-form", "contact-consent-form"):
        assert form_id in js


def test_inbox_dung_sse_va_van_giu_polling_fallback():
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert 'new EventSource("/api/inbox/events")' in js
    assert "setInterval(refresh, 6000)" in js


def test_quet_qr_zalo_ca_nhan_hien_duoc_anh_va_hoi_lai_trang_thai():
    """
    Bấm "Quét QR" mà không có gì để quét thì nút đó vô dụng.

    Sidecar trả `qr_image` KHÔNG kèm phản hồi của `login-qr`: lúc endpoint ấy
    trả về, sự kiện QR từ Zalo còn chưa tới, nên `qr_image` vẫn null. Ảnh chỉ
    xuất hiện ở lần hỏi `/status` sau đó.

    Trước lớp này, dashboard gọi `/qr` đúng một lần rồi hiện toast "chờ
    sidecar cập nhật trạng thái" — và không bao giờ hỏi lại. Người dùng nhìn
    một dòng chữ đen rồi không biết làm gì tiếp.

    Ba thứ phải có: gọi /status, đọc qr_image, và dựng thẻ ảnh để quét.
    """
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert "zalo-personal/status" in js, "phải hỏi lại trạng thái để lấy QR"
    assert "qr_image" in js, "phải đọc ảnh QR sidecar trả về"
    assert "<img" in js, "phải dựng thẻ ảnh để quét được bằng điện thoại"
