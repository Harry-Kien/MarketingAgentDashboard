"""
Canh màn Nhân sự: những thao tác quản lý nhân viên phải CÓ ĐƯỜNG TRÊN MÀN
HÌNH, không chỉ có endpoint.

VÌ SAO CẦN NHÓM TEST NÀY
-------------------------
Ba endpoint quản lý nhân viên đã tồn tại từ lâu và chạy đúng, nhưng không
màn hình nào gọi tới:

    POST /api/nguoi-dung/{ten}/khoa   nhân viên nghỉ việc -> phải vào psql gõ tay
    POST /api/toi/doi-mat-khau        không ai đổi được mật khẩu ban đầu

Endpoint xanh, test API xanh, và tính năng vẫn không dùng được. Đó là xanh
giả ở mức tính năng chứ không phải mức hàm — nguy hiểm hơn, vì không có
dòng đỏ nào để mà đi tìm.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


# ---------------- đếm nhân viên ----------------

def test_man_nhan_su_hien_tong_so_tai_khoan():
    """
    Huy hiệu trên thanh bên đếm số người CHƯA có vai trò — một con số cảnh
    báo. Câu hỏi "có bao nhiêu nhân viên" thì trước đây phải tự đếm bằng mắt.
    """
    assert 'id="nsDem"' in HTML
    assert "tài khoản`" in JS and "đang làm`" in JS


def test_tong_so_dem_ca_nguoi_da_khoa():
    """
    Người đã khoá vẫn là một tài khoản tồn tại. Đếm sót họ thì con số trên
    màn hình lệch với `SELECT count(*)`, và lệch ở đúng chỗ người ta đi tìm
    khi rà soát ai còn quyền vào hệ thống.
    """
    doan = JS[JS.index("const dangLam ="):JS.index("const dangLam =") + 400]
    assert "ds.length" in doan
    assert "!n.khoa" in doan


# ---------------- khoá / mở khoá ----------------

def test_co_nut_khoa_tren_dong_nhan_vien():
    assert "data-khoa=" in JS
    assert "/khoa?khoa=" in JS


def test_loi_xac_nhan_khoa_noi_ro_hau_qua():
    """
    "Có chắc không" là câu không mang thông tin — người ta bấm OK theo phản
    xạ. Phải nói ra rằng phiên đang mở bị đá ngay.
    """
    doan = JS[JS.index("data-dangkhoa") - 200:]
    doan = doan[:doan.index("const xem =")]
    assert "đá ra ngay" in doan


def test_khong_the_tu_khoa_minh_van_con_chan_o_may_chu():
    """
    Màn hình có nút thì càng dễ bấm nhầm vào chính mình. Chốt ở máy chủ phải
    còn — nút trên màn hình KHÔNG được thay thế nó.
    """
    routes = (ROOT / "agent" / "api" / "routes.py").read_text(encoding="utf-8")
    assert "Không tự khoá tài khoản của mình được" in routes


# ---------------- thêm nhân viên ----------------

def test_mat_khau_khong_con_nhap_bang_prompt():
    """
    `prompt()` hiện mật khẩu dạng chữ thường giữa màn hình: ai đứng sau lưng
    cũng đọc được, và ảnh chụp màn hình thì đi khắp nơi.
    """
    assert 'prompt("Mật khẩu' not in JS
    assert "prompt(\"Tên đăng nhập của nhân viên mới" not in JS


def test_o_mat_khau_la_type_password():
    khoi = HTML[HTML.index('id="nsFormNguoi"'):]
    khoi = khoi[:khoi.index("</form>")]
    o = re.search(r'<input name="mat_khau"[^>]*>', khoi)
    assert o is not None, "form thêm nhân viên phải có ô mật khẩu"
    assert 'type="password"' in o.group(0)


def test_tao_nhan_vien_gan_duoc_vai_tro_ngay():
    """
    Tách hai bước để lại một khoảng người vừa tạo chưa có quyền gì: họ đăng
    nhập được, thấy dashboard trống, và không gì nói cho họ biết vì sao.
    """
    assert 'id="nsVaiTroMoi"' in HTML
    assert "/vai-tro`" in JS


def test_gan_vai_tro_hong_thi_van_noi_ra_la_da_tao():
    """
    Tài khoản đã tạo rồi. Báo lỗi chung chung khiến người ta bấm tạo lại và
    gặp "tên đã tồn tại" — rồi không hiểu chuyện gì đang xảy ra.
    """
    assert "CHƯA cấp được vai trò" in JS


# ---------------- đổi mật khẩu ----------------

def test_co_duong_doi_mat_khau_tren_man_hinh():
    """
    Không có nó thì mật khẩu ban đầu do quản trị đặt sống mãi, và quản trị
    biết mật khẩu của mọi nhân viên vĩnh viễn.
    """
    assert 'id="congMk"' in HTML
    assert 'id="doimk"' in JS
    assert '"/toi/doi-mat-khau"' in JS


def test_doi_mat_khau_bat_go_lai():
    """
    Gõ nhầm rồi bị đá khỏi mọi thiết bị là tình huống không lối thoát cho
    người không phải quản trị — họ không tự mở lại được.
    """
    assert 'name="nhac_lai"' in HTML
    assert "d.mat_khau_moi !== d.nhac_lai" in JS


def test_doi_mat_khau_xong_thi_tai_lai_trang():
    """
    Máy chủ xoá mọi phiên kể cả phiên đang dùng. Không tải lại thì người
    dùng gặp 401 ở một thao tác ngẫu nhiên và tưởng hệ thống hỏng.
    """
    doan = JS[JS.index('"/toi/doi-mat-khau"'):]
    assert "location.reload()" in doan[:600]


# ---------------- màn đăng nhập ----------------

def test_man_dang_nhap_noi_ro_nhan_vien_lay_tai_khoan_o_dau():
    """
    Dòng cũ chỉ có lệnh CLI tạo tài khoản quản trị đầu tiên. Nhân viên đọc
    nó sẽ đi tìm terminal — thứ họ không có và không nên có.
    """
    khoi = HTML[HTML.index('id="loginform"'):]
    khoi = khoi[:khoi.index("</form>")]
    assert "Nhân viên:" in khoi
    assert "quản trị cấp" in khoi
    assert "tao_tai_khoan" in khoi      # đường lần đầu vẫn phải còn
