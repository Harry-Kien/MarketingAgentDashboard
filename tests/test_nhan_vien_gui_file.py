"""
Nhân viên phải gửi được ảnh và tài liệu cho khách, như mọi công cụ chat thật.

VÌ SAO THIẾU LÂU NHƯ VẬY
------------------------
`OutboundService.queue_file` đã có từ trước — agent dùng nó để gửi ảnh sản
phẩm, và đường đó chạy được. Nhưng KHÔNG có route API nào cho nhân viên, và
khung soạn tin chỉ có ô chữ.

Nghĩa là: agent gửi được ảnh, người thật thì không. Khách hỏi "cho xem ảnh
thật cái đã mở nắp" thì người trực phải mở Zalo riêng ra gửi — và tin đó
không nằm trong hội thoại, không ai truy được về sau.

Đây là lần thứ năm trong dự án này gặp khuôn "khả năng có sẵn nhưng không
nối vào đường chạy".

HAI ĐƯỜNG GỬI, VÀ VÌ SAO CẢ HAI
-------------------------------
  theo MÃ SẢN PHẨM  ảnh đã có sẵn trong kho, không tải lên gì cả. Đây là
                    việc người trực làm nhiều nhất, và nó không mở thêm bề
                    mặt tấn công nào.
  TẢI FILE LÊN      cho ảnh chụp thật, hoá đơn, hướng dẫn dùng. Cần thiết,
                    nhưng mỗi lần nhận file từ trình duyệt là một lần phải
                    tự bảo vệ.
"""
from __future__ import annotations

import inspect

import pytest


def test_co_duong_gui_file_cho_nhan_vien():
    from agent.api.routes import router

    duong = {getattr(r, "path", "") for r in router.routes}
    assert "/api/conversations/{conv_id}/send-file" in duong


def test_doi_dang_nhap():
    """Gửi tin nhân danh doanh nghiệp — không thể để ngỏ."""
    from agent.api import routes

    assert "bat_buoc_dang_nhap" in inspect.getsource(routes.staff_send_file)


# ---------------------------------------------------------------
#  Tên file: chỗ nguy hiểm nhất khi nhận tệp từ trình duyệt
# ---------------------------------------------------------------

@pytest.mark.parametrize("ten_ac", [
    "../../../../etc/passwd",
    "..\\..\\windows\\system32\\config\\sam",
    "/etc/shadow",
    "anh.jpg/../../.env",
    "....//....//.env",
])
def test_ten_file_doc_hai_khong_thoat_ra_khoi_thu_muc(ten_ac):
    """
    KHÔNG BAO GIỜ dùng tên file client gửi lên.

    Một tên như `../../../.env` mà đem nối vào đường dẫn là ghi đè file bí
    mật của chính hệ thống. Đây là lỗ hổng kinh điển nhất của mọi tính năng
    tải tệp, và cách chặn chắc chắn nhất không phải là lọc tên xấu — mà là
    KHÔNG dùng tên đó, tự sinh tên mới.
    """
    from agent.api.routes import _ten_file_an_toan

    ra = _ten_file_an_toan(ten_ac, "image/jpeg")
    assert "/" not in ra
    assert "\\" not in ra
    assert ".." not in ra


def test_ten_file_giu_duoc_duoi_dung_kieu():
    from agent.api.routes import _ten_file_an_toan

    assert _ten_file_an_toan("anh.jpg", "image/jpeg").endswith(".jpg")
    assert _ten_file_an_toan("tai-lieu.pdf", "application/pdf").endswith(".pdf")


def test_duoi_file_lay_theo_MIME_khong_theo_ten():
    """
    Tên `virus.exe` gửi kèm `Content-Type: image/png` thì tin MIME, không tin
    tên. Ngược lại cũng vậy: kiểu do máy chủ ta tự quyết, không do client.
    """
    from agent.api.routes import _ten_file_an_toan

    assert _ten_file_an_toan("virus.exe", "image/png").endswith(".png")


def test_moi_lan_tai_len_mot_ten_khac_nhau():
    """Hai người cùng gửi `anh.jpg` không được đè lên nhau."""
    from agent.api.routes import _ten_file_an_toan

    assert _ten_file_an_toan("a.jpg", "image/jpeg") != _ten_file_an_toan("a.jpg", "image/jpeg")


# ---------------------------------------------------------------
#  Chỉ nhận thứ đáng nhận
# ---------------------------------------------------------------

@pytest.mark.parametrize("mime", [
    "image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf",
])
def test_nhan_anh_va_pdf(mime):
    from agent.api.routes import MIME_GUI_DUOC

    assert mime in MIME_GUI_DUOC


@pytest.mark.parametrize("mime", [
    "application/x-msdownload", "text/html", "application/zip",
    "application/javascript", "image/svg+xml",
])
def test_tu_choi_kieu_nguy_hiem(mime):
    """
    Danh sách CHO PHÉP, không phải danh sách cấm.

    `image/svg+xml` trông như ảnh nhưng SVG chạy được mã trong trình duyệt.
    `text/html` cũng vậy. Danh sách cấm thì luôn thiếu một mục.
    """
    from agent.api.routes import MIME_GUI_DUOC

    assert mime not in MIME_GUI_DUOC


def test_co_gioi_han_dung_luong():
    from agent.api.routes import TOI_DA_BYTE_GUI

    assert 0 < TOI_DA_BYTE_GUI <= 25 * 1024 * 1024


# ---------------------------------------------------------------
#  Gửi theo mã sản phẩm — đường dùng nhiều nhất
# ---------------------------------------------------------------

def test_gui_duoc_theo_ma_san_pham():
    """Ảnh đã có trong kho: không tải lên gì, không mở thêm bề mặt tấn công."""
    from agent.api import routes

    nguon = inspect.getsource(routes.staff_send_file)
    assert "ma_san_pham" in nguon


def test_dung_lai_kho_anh_san_pham_co_san():
    from agent.api import routes

    nguon = inspect.getsource(routes.staff_send_file)
    assert "_anh_san_pham" in nguon or "anh_san_pham" in nguon


# ---------------------------------------------------------------
#  Đi qua outbox, không gọi thẳng provider
# ---------------------------------------------------------------

def test_di_qua_outbox_nhu_moi_tin_khac():
    """
    Gọi thẳng provider ở API là mất mọi thứ outbox đang giữ: thử lại, chống
    trùng, dead-letter, và thứ tự tin.
    """
    from agent.api import routes

    nguon = inspect.getsource(routes.staff_send_file)
    assert "queue_file" in nguon


def test_co_khoa_chong_trung():
    from agent.api import routes

    assert "idempotency_key" in inspect.getsource(routes.staff_send_file)


# ---------------------------------------------------------------
#  Giao diện
# ---------------------------------------------------------------

def test_khung_soan_tin_co_nut_dinh_kem():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "dashboard" / "app.js").read_text(
        encoding="utf-8")
    assert "send-file" in js, "dashboard chưa gọi đường gửi file"
    assert "data-dinhkem" in js, "chưa có nút đính kèm"


def test_thu_muc_tai_len_khong_len_repo():
    """Ảnh khách và hoá đơn là dữ liệu vận hành, không phải mã nguồn."""
    from pathlib import Path

    gi = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(
        encoding="utf-8")
    assert "data/uploads" in gi
