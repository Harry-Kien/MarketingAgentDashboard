"""
Màn hình Kho phải hiện ẢNH sản phẩm, không chỉ mã và số.

VÌ SAO
------
Người trực đối chiếu bằng mắt khi khách mô tả sản phẩm bằng lời — "cái chai
xanh xanh ấy", "hộp tròn nắp vàng". Chỉ có mã `AS-SR03` và tên dài thì họ
phải mở thư mục ảnh ra tìm, hoặc đoán.

Và cùng tấm ảnh đó là thứ agent gửi cho khách. Nhìn thấy nó ở màn hình Kho
nghĩa là biết trước khách sẽ thấy gì.
"""
from __future__ import annotations

import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")


def test_co_duong_phuc_vu_anh_san_pham():
    from agent.api.routes import router

    duong = {getattr(r, "path", "") for r in router.routes}
    assert "/api/san-pham/{ma}/anh" in duong


def test_duong_anh_doi_dang_nhap():
    """Mọi thứ dưới `/api` đều sau cổng đăng nhập; mở ngoại lệ là mở đường dò."""
    from agent.api import routes

    assert "bat_buoc_dang_nhap" in inspect.getsource(routes.anh_san_pham_file)


def test_duong_dan_do_MAY_CHU_dung_khong_do_client():
    """
    Client chỉ gửi MÃ, không gửi đường dẫn. Một mã dạng `../../.env` không
    đi tới đâu cả — nó đơn giản không có trong danh mục.
    """
    from agent.api import routes

    nguon = inspect.getsource(routes.anh_san_pham_file)
    assert "_anh_san_pham" in nguon
    assert "FileResponse" in nguon


def test_api_kho_bao_co_anh_hay_khong():
    from agent.api import routes

    nguon = inspect.getsource(routes.kho_tong_quan)
    assert "co_anh" in nguon


def test_api_kho_tra_them_mo_ta():
    """Dung tích và loại da phù hợp là thứ người trực hay phải tra lại."""
    from agent.api import routes

    nguon = inspect.getsource(routes.kho_tong_quan)
    assert "dung_tich" in nguon
    assert "da_phu_hop" in nguon


def test_dashboard_hien_anh():
    assert "kho__anh" in JS
    assert "/api/san-pham/" in JS


def test_anh_tai_lazy():
    """
    Màn hình có thể hàng trăm mã. Tải hết cùng lúc là mở hàng trăm kết nối
    cho một lần cuộn.
    """
    khoi = JS.split("kho__anh", 1)[1][:400]
    assert 'loading="lazy"' in khoi


def test_anh_KHONG_nam_trong_cot_thanh_trang_thai():
    """
    Đây đúng lỗi đè chữ đã sửa ở danh sách Khách hàng: cột đầu của `.row`
    rộng 3px, dành cho thanh màu. Nhét ảnh 46px vào đó là nó tràn ra và nằm
    lên tên sản phẩm.
    """
    assert ".row--kho" in CSS
    khoi = CSS.split(".row--kho", 1)[1].split("}", 1)[0]
    assert "grid-template-columns" in khoi
    assert "auto" in khoi


def test_ma_khong_co_anh_van_hien_duoc():
    """Mã mới nhập chưa có ảnh không được làm vỡ cả dòng."""
    assert "kho__anh--trong" in JS
    assert "kho__anh--trong" in CSS
