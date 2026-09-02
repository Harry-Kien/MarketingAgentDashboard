"""
Ảnh phải HIỆN RA trong khung chat, như Messenger và Zalo.

LỖI NGƯỜI DÙNG BÁO
------------------
Nhân viên bấm 📎 gửi ảnh cho khách. Ảnh tới nơi — nhưng nhìn lại khung chat
thì thấy biểu tượng ảnh vỡ, và ngay dưới là một bong bóng xanh ghi tên tệp
`WIN_20241105_22_45_28_Pro.jpg`.

NGUYÊN NHÂN
-----------
`queue_file` lưu `storage_key` — đường dẫn TRÊN MÁY CHỦ — và để `url` rỗng:

    url          None
    storage_key  data/uploads/5cb728865aab4070b4d8c00791586d04.jpg

Dashboard vẽ thẳng `a.url`, nên `src` rỗng và trình duyệt hiện ảnh hỏng.

Tin của khách gửi vào thì CÓ `url` (CDN của Zalo/Meta) nên vẫn hiện được —
đó là lý do lỗi này chỉ lộ ra khi chính nhân viên gửi ảnh.
"""
from __future__ import annotations

import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")


def test_co_duong_phuc_vu_tep_dinh_kem():
    from agent.api.routes import router

    duong = {getattr(r, "path", "") for r in router.routes}
    assert "/api/attachments/{attachment_id}/file" in duong


def test_duong_doi_dang_nhap():
    from agent.api import routes

    assert "bat_buoc_dang_nhap" in inspect.getsource(routes.attachment_file)


def test_nhan_ID_khong_nhan_duong_dan():
    """
    Client gửi ID của bản ghi; đường dẫn lấy từ CSDL. Nhận đường dẫn thì
    `?path=../../.env` đọc được mọi tệp trên máy chủ.
    """
    from agent.api import routes

    tham_so = inspect.signature(routes.attachment_file).parameters
    assert "attachment_id" in tham_so
    for cam in ("path", "duong_dan", "file_path"):
        assert cam not in tham_so


def test_van_kiem_tep_nam_trong_thu_muc_du_lieu():
    """
    Một bản ghi hỏng hoặc bị sửa tay không được biến thành đường đọc toàn ổ
    đĩa. Kiểm hai lớp: ID từ CSDL, VÀ đường dẫn phải nằm trong `data/`.
    """
    from agent.api import routes

    nguon = inspect.getsource(routes.attachment_file)
    assert "parents" in nguon
    assert "resolve()" in nguon


def test_kieu_tep_la_thi_KHONG_mo_trong_tab():
    """
    `application/octet-stream` khiến trình duyệt TẢI XUỐNG thay vì mở. Thứ
    lạ mà mở trong tab là thứ chạy được trong phiên đang đăng nhập.
    """
    from agent.api.routes import _MIME_THEO_DUOI

    assert "application/octet-stream" in inspect.getsource(
        __import__("agent.api.routes", fromlist=["x"]).attachment_file)
    for cam in (".html", ".svg", ".js"):
        assert cam not in _MIME_THEO_DUOI


def test_dashboard_ro_ve_duong_phuc_vu_khi_thieu_url():
    assert "/api/attachments/" in JS, "dashboard chưa dùng đường phục vụ tệp"
    assert "a.url ||" in JS, "phải ưu tiên URL nhà cung cấp, rồi mới rơi về"


def test_khong_lap_lai_ten_tep_duoi_anh():
    """
    `queue_file` đặt nội dung tin BẰNG chú thích, mà chú thích mặc định là
    tên tệp. Vẽ cả hai thì dưới ảnh hiện một bong bóng xanh ghi
    `WIN_20241105_22_45_28_Pro.jpg` — Messenger và Zalo đều không làm vậy.
    """
    assert "chuTrung" in JS


def test_anh_bo_goc_khop_bong_bong_chu():
    """Ảnh và chữ là hai dạng của cùng một tin — phải trông cùng một họ."""
    khoi = CSS.split(".msg__anh img", 1)[1].split("}", 1)[0]
    assert "border-radius: 14px" in khoi
    assert ".msg--staff .msg__anh img" in CSS
