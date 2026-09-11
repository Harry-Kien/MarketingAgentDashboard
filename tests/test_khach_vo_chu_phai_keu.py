"""
Khách chưa có chủ phải nhìn thấy được.

Chủ dự án chọn "khách chưa giao là của chung, không tự gán chủ". Hệ quả đã
biết trước ngay lúc chọn: phần lớn khách sẽ ở mãi trạng thái vô chủ.

Một hàng chờ không ai đếm thì không ai thấy. File này canh rằng con số ấy
tồn tại, khớp với danh sách, và chỉ hiện khi CÓ chuyện.

Cùng khuôn với `tests/test_tin_chet_phai_keu.py` — cùng một loại lỗi.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

ROUTES = (ROOT / "agent" / "api" / "routes.py").read_text(encoding="utf-8")
CONTACTS = (ROOT / "agent" / "api" / "contacts.py").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def test_overview_tra_so_khach_vo_chu():
    assert '"khach_vo_chu"' in ROUTES
    assert '"lau_nhat"' in ROUTES


def test_chi_so_va_bo_loc_dung_CHUNG_mot_dinh_nghia():
    """
    Hai định nghĩa "vô chủ" lệch nhau là con số nói một đằng, danh sách hiện
    một nẻo — rồi người ta thôi tin cả hai, và thôi nhìn cả hai.

    Cả hai phải là `owner_user_id IS NULL AND status = 'active'`.
    """
    mau = "owner_user_id IS NULL AND status = 'active'"
    assert mau in ROUTES, "chỉ số trong overview dùng định nghĩa khác"
    assert mau in CONTACTS, "endpoint /khach-vo-chu dùng định nghĩa khác"


def test_khong_cat_theo_24_gio():
    """
    Khách vô chủ từ tháng trước vẫn là khách không ai phụ trách.

    Cắt theo 24 giờ là để họ tự biến mất khỏi màn hình sau một đêm — đúng
    cái đã xảy ra với tin chết trước đây.
    """
    vt = ROUTES.index("owner_user_id IS NULL AND status = 'active'")
    doan = ROUTES[max(0, vt - 400):vt + 200]
    assert "$1" not in doan.split("FROM contacts")[-1], (
        "truy vấn khách vô chủ không được nhận mốc thời gian"
    )


def test_o_chi_hien_khi_CO_khach_vo_chu():
    """
    Một ô luôn hiện "0" là một ô người ta thôi nhìn sau tuần đầu. Ô chỉ xuất
    hiện khi có chuyện thì sự xuất hiện của nó CHÍNH LÀ tín hiệu.
    """
    m = re.search(r"o\.khach_vo_chu && o\.khach_vo_chu\.so", JS)
    assert m, "dashboard phải kiểm có khách vô chủ trước khi vẽ ô"


def test_o_hien_ca_TUOI_khong_chi_so_luong():
    """
    "412 khách" là con số người ta quen mắt sau một tuần. "lâu nhất 62 ngày"
    thì không — nó nói rằng có người đã chờ hai tháng.
    """
    vt = JS.index("Khách chưa có chủ")
    doan = JS[vt:vt + 400]
    assert "lau_nhat" in doan
    assert "ngày" in doan


def test_co_ham_doi_ngay():
    assert "function ngayTu(" in JS
