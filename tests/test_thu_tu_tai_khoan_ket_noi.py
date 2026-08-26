"""
Thứ tự tài khoản trên màn hình Kết nối, và nút thu gọn phải mở được cả hai chiều.

VÌ SAO THỨ TỰ QUAN TRỌNG
------------------------
Một tài khoản Facebook quản lý 26 Trang. Danh sách theo thứ tự Meta trả về
nghĩa là Trang ĐANG CHẠY THẬT có thể nằm ở vị trí thứ 19, dưới 18 Trang chưa
bao giờ nhận tin nào.

Người trực mở màn hình này để xem "kênh của mình có sống không". Câu trả lời
phải nằm ở dòng đầu.

VÌ SAO TRANG GIÁN ĐOẠN CŨNG PHẢI LÊN TRÊN
------------------------------------------
`degraded` và `reauth_required` là Trang ĐÃ từng chạy rồi hỏng — chúng đang
mất tin của khách ngay lúc này. Chôn chúng dưới hai mươi Trang `pending` là
giấu đúng thứ cần xử lý gấp nhất.

`pending` thì ngược lại: chưa bao giờ nhận tin, nên chưa mất gì.

VÌ SAO PHẢI THU GỌN LẠI ĐƯỢC
-----------------------------
Bản trước bấm "Xem thêm" là nút tự xoá — mở ra rồi không đóng lại được, phải
tải lại cả trang. Mở rộng mà không thu lại được thì lần sau người ta ngại bấm.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")


def test_co_bang_uu_tien_thu_tu():
    assert "UU_TIEN_TRANG_THAI" in JS, "chưa có bảng thứ tự trạng thái"


def test_active_len_dau_pending_xuong_duoi():
    """Đọc thẳng bảng ưu tiên trong mã, không đoán theo thứ tự dòng."""
    khoi = JS.split("UU_TIEN_TRANG_THAI", 1)[1].split("}", 1)[0]
    import re

    diem = dict(re.findall(r"(\w+):\s*(\d+)", khoi))
    assert diem.get("active") is not None, "thiếu active"
    assert diem.get("pending") is not None, "thiếu pending"
    assert int(diem["active"]) < int(diem["pending"]), "active phải lên trên pending"


def test_trang_gian_doan_khong_bi_chon_duoi_pending():
    """Trang đang mất tin của khách phải nổi lên, không nằm dưới Trang chưa dùng."""
    import re

    khoi = JS.split("UU_TIEN_TRANG_THAI", 1)[1].split("}", 1)[0]
    diem = dict(re.findall(r"(\w+):\s*(\d+)", khoi))
    for hong in ("degraded", "reauth_required"):
        assert diem.get(hong) is not None, f"thiếu {hong}"
        assert int(diem[hong]) < int(diem["pending"]), (
            f"{hong} đang bị chôn dưới các Trang chưa kết nối"
        )


def test_da_tam_ngat_xuong_cuoi():
    """Tài khoản người ta chủ động tắt thì không cần chiếm chỗ trên cùng."""
    import re

    khoi = JS.split("UU_TIEN_TRANG_THAI", 1)[1].split("}", 1)[0]
    diem = dict(re.findall(r"(\w+):\s*(\d+)", khoi))
    assert int(diem["disabled"]) > int(diem["pending"])


def _than_load_ket_noi() -> str:
    """
    Thân hàm dựng màn hình Kết nối.

    Cắt theo `async function` chứ không theo tên trần: tên hàm xuất hiện ở
    các chỗ GỌI nó trước cả chỗ định nghĩa, nên cắt trần là soi nhầm đoạn và
    đỏ vì lý do không liên quan.
    """
    return JS.split("async function loadKetNoi", 1)[1]


def test_thuc_su_sap_xep_truoc_khi_ve():
    """Có bảng ưu tiên mà không gọi sort là bảng chết."""
    assert ".sort(" in _than_load_ket_noi()[:2500], (
        "loadKetNoi không sắp xếp danh sách"
    )


def test_cung_trang_thai_thi_xep_theo_ten():
    """
    Thứ tự phải ỔN ĐỊNH giữa các lần tải.

    Không có tiêu chí phụ thì hai Trang cùng trạng thái đổi chỗ nhau mỗi lần
    làm mới, và mắt người trực phải tìm lại từ đầu.
    """
    assert "localeCompare" in _than_load_ket_noi()[:2500]


def test_nut_thu_gon_doi_duoc_hai_chieu():
    """Mở ra mà không đóng lại được thì lần sau người ta ngại bấm."""
    assert "Thu gọn" in JS, "chưa có đường thu gọn lại"


def test_nut_khong_tu_xoa_sau_khi_mo():
    khoi = JS.split('$$("[data-mo]")', 1)[1][:900]
    assert "button.remove()" not in khoi, "nút tự xoá thì không thu gọn lại được"


def test_dem_dung_so_tai_khoan_con_an():
    """Nút nói "Xem thêm 21" thì phải đúng 21, không phải tổng số."""
    assert "SO_HIEN_SAN" in JS
    assert "items.length - SO_HIEN_SAN" in JS


def test_css_van_khai_bao_kieu_thu_gon():
    assert ".channel-card__body.is-thu-gon" in CSS
