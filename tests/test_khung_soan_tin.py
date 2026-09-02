"""
Khung soạn tin: không được xoá bản nháp, và Enter phải gửi.

HAI LỖI NGƯỜI DÙNG BÁO
----------------------
1. Đang gõ dở thì chữ biến mất.
2. Bấm Enter không gửi được, phải với chuột sang nút "Gửi".

VÌ SAO XOÁ CHỮ
--------------
`veChiTiet()` dựng lại TOÀN BỘ panel bằng `innerHTML = ...`, và trong khối
HTML đó có luôn `<textarea>`. Mỗi lần refresh — SSE báo tin mới, hoặc nhịp
6 giây — thẻ textarea cũ bị vứt đi và thay bằng thẻ mới rỗng.

Nghĩa là: KHÁCH CÀNG NHẮN NHIỀU thì nhân viên càng hay mất chữ. Đúng lúc
hội thoại đang nóng thì khung soạn tin xoá sạch. Không có lỗi nào hiện ra —
chữ chỉ biến mất.

VÌ SAO ENTER KHÔNG GỬI
----------------------
`<textarea>` trong form: Enter là xuống dòng, không phải submit. Đó là hành
vi mặc định của trình duyệt, không phải lỗi — nhưng mọi công cụ chat đều
đảo lại: Enter gửi, Shift+Enter xuống dòng. Người trực gõ theo phản xạ từ
Zalo và Messenger, nên mặc định của trình duyệt ở đây là sai với thói quen.

LỖI THỨ BA, NGƯỜI DÙNG CHƯA NHẮC
--------------------------------
`thread.scrollTop = thread.scrollHeight` chạy mỗi lần dựng lại. Đang cuộn
lên đọc lại đoạn cũ mà có tin mới về là bị giật xuống đáy. Cùng một gốc:
dựng lại mù, không nhớ người dùng đang ở đâu.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _khoi_ve_chi_tiet() -> str:
    """Chỉ phần dựng chi tiết hội thoại, để không bắt nhầm chỗ khác."""
    return JS.split("#convdetail", 1)[1].split("/* ---------------- Customer 360", 1)[0]


def test_giu_ban_nhap_qua_moi_lan_dung_lai():
    khoi = _khoi_ve_chi_tiet()
    assert "nhap" in khoi.lower() or "draft" in khoi.lower(), (
        "không thấy chỗ nào giữ bản nháp — chữ đang gõ sẽ bị xoá mỗi lần refresh"
    )


def test_ban_nhap_gan_theo_TUNG_hoi_thoai():
    """
    Giữ chung một bản nháp là dán chữ của hội thoại A sang hội thoại B.

    Tệ hơn mất chữ nhiều: gửi nhầm nội dung cho nhầm khách.
    """
    assert "nhapTheoHoiThoai" in JS or "nhap[" in JS or "nhap.set" in JS, (
        "bản nháp phải gắn theo id hội thoại"
    )


def test_enter_gui_tin():
    khoi = _khoi_ve_chi_tiet()
    assert "Enter" in khoi, "chưa bắt phím Enter"


def test_shift_enter_van_xuong_dong():
    """Bỏ mất xuống dòng là không soạn được tin nhiều đoạn."""
    khoi = _khoi_ve_chi_tiet()
    assert "shiftKey" in khoi, "Shift+Enter phải xuống dòng, không được gửi"


def test_khong_giat_xuong_day_khi_dang_doc_o_tren():
    khoi = _khoi_ve_chi_tiet()
    assert "scrollHeight" in khoi
    assert "clientHeight" in khoi or "o_day" in khoi or "oDay" in khoi, (
        "phải kiểm người dùng có đang ở đáy không trước khi cuộn"
    )


def test_giu_luon_vi_tri_con_tro():
    """
    Khôi phục chữ mà không khôi phục con trỏ là con trỏ nhảy về đầu dòng.

    Người đang gõ giữa câu sẽ gõ tiếp vào đầu tin — vẫn là mất công.
    """
    khoi = _khoi_ve_chi_tiet()
    assert "selectionStart" in khoi, "chưa giữ vị trí con trỏ"


def test_van_con_nut_gui():
    """Enter là lối tắt, không phải lối duy nhất — máy tính bảng cần nút."""
    khoi = _khoi_ve_chi_tiet()
    assert 'type="submit"' in khoi


def test_khong_gui_khi_bo_go_tieng_viet_dang_chot_tu():
    """
    Bộ gõ tiếng Việt dùng Enter để chốt từ đang gõ dở.

    Không kiểm `isComposing` thì gõ "phường" bị gửi mất nửa chừng thành
    "phươn" — và tin đó đã đi tới khách, không rút lại được. Đây là lỗi chỉ
    lộ ra với người gõ tiếng Việt, tức là toàn bộ người dùng của hệ thống này.
    """
    khoi = _khoi_ve_chi_tiet()
    assert "isComposing" in khoi, "chưa chặn Enter của bộ gõ dấu"


def test_gui_xong_thi_xoa_ban_nhap():
    """Không xoá thì lần dựng lại kế tiếp chép bản nháp trở vào khung."""
    khoi = _khoi_ve_chi_tiet()
    assert "delete state.nhapTheoHoiThoai" in khoi
