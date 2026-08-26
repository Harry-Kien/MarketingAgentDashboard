"""
Kiểm thử xác thực và phân quyền. Không gọi API model, không cần CSDL.

Đây là lớp bảo vệ duy nhất đứng giữa Internet và: tên/số điện thoại/địa chỉ
khách hàng, toàn bộ nội dung hội thoại, quyền gửi tin nhân danh doanh
nghiệp, và quyền XOÁ VĨNH VIỄN dữ liệu khách.

Sai ở đây thì mọi thứ khác trong hệ thống không còn nghĩa lý gì.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import main as app_main  # noqa: E402
from agent.api import routes  # noqa: E402
from agent.core import xac_thuc  # noqa: E402


# =====================================================================
#  Băm mật khẩu
# =====================================================================

def test_bam_roi_khong_doc_nguoc_duoc():
    bam = xac_thuc.bam_mat_khau("MatKhauCuaToi123")
    assert "MatKhauCuaToi123" not in bam
    assert bam.startswith("scrypt$")


def test_cung_mat_khau_ra_hai_ban_bam_khac_nhau():
    """
    Muối riêng từng người: hai người đặt cùng mật khẩu vẫn ra hai bản băm
    khác nhau, nên lộ một bản không suy ra được bản kia.
    """
    a = xac_thuc.bam_mat_khau("giongnhau")
    b = xac_thuc.bam_mat_khau("giongnhau")
    assert a != b
    assert xac_thuc.kiem_mat_khau("giongnhau", a)
    assert xac_thuc.kiem_mat_khau("giongnhau", b)


def test_sai_mat_khau_thi_khong_qua():
    bam = xac_thuc.bam_mat_khau("dung")
    assert not xac_thuc.kiem_mat_khau("sai", bam)
    assert not xac_thuc.kiem_mat_khau("", bam)


@pytest.mark.parametrize("hong", [
    "", "khong-phai-dinh-dang", "scrypt$x$y$z", "md5$1$1$1$aa$bb",
])
def test_ban_bam_hong_thi_tu_choi_chu_khong_no(hong):
    """Bản băm hỏng trong CSDL không được làm sập luồng đăng nhập."""
    assert xac_thuc.kiem_mat_khau("bat_ky", hong) is False


def test_so_sanh_bang_compare_digest():
    """
    So bằng `==` để lộ độ dài tiền tố đúng qua thời gian phản hồi; với đủ
    lần thử, đó là một đường dò mật khẩu.
    """
    src = inspect.getsource(xac_thuc.kiem_mat_khau)
    assert "compare_digest" in src
    assert "==" not in src.split("return")[-1]


def test_dung_scrypt_khong_dung_ham_bam_nhanh():
    """
    SHA-256 trần dò được hàng tỉ lần mỗi giây trên GPU. scrypt chậm và tốn
    bộ nhớ có chủ đích.
    """
    src = inspect.getsource(xac_thuc.bam_mat_khau)
    assert "scrypt" in src
    for nhanh in ("sha256(", "md5(", "sha1("):
        assert nhanh not in src


# =====================================================================
#  Chặn theo mặc định — điểm quan trọng nhất
# =====================================================================

def test_chan_bang_middleware_khong_phai_gan_tung_endpoint():
    """
    Gắn Depends từng endpoint là cơ chế HỎNG-MỞ: hơn bốn mươi endpoint,
    quên một cái là cái đó phơi ra và không có gì báo.

    Middleware là HỎNG-ĐÓNG: endpoint mới được bảo vệ theo mặc định.
    """
    src = inspect.getsource(app_main)
    assert '@app.middleware("http")' in src
    assert 'duong.startswith("/api/")' in src


# Mỗi đường mở phải có tên và một CHỐT KHÁC gánh thay chỗ đăng nhập.
# Thêm dòng vào đây là việc phải cân nhắc, không phải thao tác dọn dẹp.
_DUONG_MO_DUOC_PHEP = {
    "/api/dang-nhap": "phải vào được mới đăng nhập được",
    "/api/dang-xuat": "đăng xuất phải chạy kể cả khi phiên đã hỏng",
    # Meta gọi vào và không mang cookie của ta. Chốt thay thế là `state`
    # dùng một lần, sinh ở /start — nơi VẪN đòi quyền quản trị.
    "/api/connect/meta/callback": "state dùng một lần thay cho cookie",
}


def test_danh_sach_duong_mo_ngan_va_co_chu_dich():
    """
    Mỗi mục trong danh sách mở là một lỗ hổng tiềm năng.

    Phép kiểm cũ chỉ đòi tên bắt đầu bằng `/api/dang-`. Quy tắc đó chặt về
    hình thức nhưng không nói được điều thật sự quan trọng: đường này được
    mở VÌ CÁI GÌ, và cái gì gánh thay chỗ đăng nhập.

    Nay mỗi đường mở phải có tên trong bảng trên kèm lý do — người thêm
    đường mới buộc phải viết ra chốt thay thế, thay vì đặt tên khéo cho lọt.
    """
    assert len(app_main._MO) <= 4, "danh sách đường mở đang phình ra"
    la = set(app_main._MO) - set(_DUONG_MO_DUOC_PHEP)
    assert not la, f"đường mở chưa được biện minh: {sorted(la)}"


def test_moi_duong_mo_deu_thuc_su_ton_tai():
    """
    Đường mở trỏ vào endpoint đã bị xoá là rác — và rác trong danh sách bảo
    vệ khiến người đọc sau tưởng nó vẫn có ý nghĩa.
    """
    # Đọc từ OpenAPI chứ không từ `app.routes`: router gắn bằng
    # `include_router` không được trải phẳng vào `app.routes`, nên duyệt
    # danh sách đó sẽ thấy RỖNG và test xanh giả — nó sẽ không bao giờ bắt
    # được đường mở trỏ vào hư không.
    duong_that = set(app_main.app.openapi().get("paths", {}))
    for d in app_main._MO:
        assert d in duong_that, f"đường mở {d} không còn endpoint nào"


def test_webhook_khong_di_qua_lop_dang_nhap():
    """
    Webhook do Chatwoot gọi, không phải người. Nó tự xác thực bằng
    WEBHOOK_SECRET. Bắt nó đăng nhập là chặn luôn kênh.
    """
    src = inspect.getsource(app_main.webhook)
    assert "webhook_secret" in src and "compare_digest" in src


# =====================================================================
#  Không rò rỉ tài khoản nào có thật
# =====================================================================

def test_khong_noi_sai_ten_hay_sai_mat_khau():
    """
    Soi CHUỖI ĐƯỢC NÉM RA, không soi cả mã nguồn: chú thích giải thích vì
    sao không tách hai trường hợp cũng chứa đúng những chữ đó, và một test
    soi chú thích thì đỏ vì lý do sai.
    """
    src = inspect.getsource(routes.dang_nhap)
    nem = [d for d in src.split("HTTPException(401,")[1:]]
    assert nem, "không thấy chỗ ném lỗi 401"
    thong_bao = nem[0].split(")")[0]
    assert "Tên đăng nhập hoặc mật khẩu không đúng" in thong_bao
    for lo in ("không tồn tại", "sai mật khẩu", "chưa đăng ký", "bị khoá"):
        assert lo not in thong_bao, f"thông báo lộ {lo!r}"

    # Và chỉ có MỘT thông báo — hai thông báo khác nhau là tách trường hợp.
    assert len(nem) == 1, "có nhiều hơn một thông báo lỗi đăng nhập"


def test_van_bam_mot_lan_du_khong_co_tai_khoan():
    """
    Trả lời ngay lập tức cho tên không tồn tại là chỉ ra tên nào CÓ tồn
    tại — thời gian phản hồi tự nó là một kênh rò rỉ.
    """
    src = inspect.getsource(xac_thuc.dang_nhap)
    khoi = src.split("if nd is None:", 1)[1][:300]
    assert "kiem_mat_khau" in khoi


# =====================================================================
#  Phiên
# =====================================================================

def test_phien_trong_csdl_khong_phai_jwt():
    """
    JWT không thu hồi được. Nhân viên nghỉ việc lúc 9 giờ sáng thì token
    của họ vẫn dùng được tới lúc hết hạn.
    """
    src = inspect.getsource(xac_thuc)
    assert "INSERT INTO phien" in src
    # Soi IMPORT chứ không soi cả văn bản: chú thích giải thích vì sao
    # không dùng JWT cũng chứa chữ "jwt".
    for dong in src.splitlines():
        thap = dong.strip().lower()
        if thap.startswith(("import ", "from ")):
            for thu_vien in ("jwt", "jose", "authlib"):
                assert thu_vien not in thap, f"đang import {thu_vien}"


def test_cookie_httponly_va_samesite():
    src = inspect.getsource(routes.dang_nhap)
    assert "httponly=True" in src, "JavaScript đọc được phiên -> XSS lấy được"
    assert 'samesite="lax"' in src


def test_cookie_secure_theo_cau_hinh():
    """Bật cứng thì đăng nhập trên http://localhost hỏng; phải cấu hình được."""
    src = inspect.getsource(routes.dang_nhap)
    assert "settings.cookie_bao_mat" in src


def test_doi_mat_khau_da_moi_phien_dang_mo():
    """
    Người chiếm được tài khoản vẫn ngồi trong đó sau khi chủ đã đổi mật
    khẩu — nếu không xoá phiên.
    """
    src = inspect.getsource(xac_thuc.doi_mat_khau)
    assert "DELETE FROM phien" in src


def test_khoa_tai_khoan_da_phien_ngay():
    src = inspect.getsource(routes.khoa_nguoi_dung)
    assert "DELETE FROM phien" in src, (
        "khoá mà không xoá phiên thì người vừa bị khoá còn bảy ngày trong hệ thống"
    )


def test_khong_tu_khoa_tai_khoan_cua_minh():
    """Quản trị cuối cùng tự khoá mình là không ai vào được nữa."""
    src = inspect.getsource(routes.khoa_nguoi_dung)
    assert 'nguoi["ten_dang_nhap"]' in src and "422" in src


def test_phien_co_han():
    src = inspect.getsource(xac_thuc.doc_phien)
    assert "het_han > now()" in src


# =====================================================================
#  Phân quyền
# =====================================================================

def test_viec_nguy_hiem_chi_danh_cho_quan_tri():
    assert "pdpd.xoa" in xac_thuc.CHI_QUAN_TRI
    assert "runtime" in xac_thuc.CHI_QUAN_TRI
    assert "nguoi_dung" in xac_thuc.CHI_QUAN_TRI


def test_nhan_vien_van_lam_duoc_viec_thuong():
    nv = {"vai_tro": "nhan_vien"}
    assert xac_thuc.duoc_phep(nv, "xem_hoi_thoai")
    assert not xac_thuc.duoc_phep(nv, "pdpd.xoa")


def test_chua_dang_nhap_thi_khong_duoc_gi():
    assert not xac_thuc.duoc_phep(None, "xem_hoi_thoai")


def test_quan_ly_tai_khoan_can_quyen_quan_tri():
    for ham in (routes.danh_sach_nguoi_dung, routes.them_nguoi_dung,
                routes.khoa_nguoi_dung):
        ky = inspect.signature(ham).parameters
        assert any("bat_buoc_quan_tri" in str(v.default) for v in ky.values()), (
            f"{ham.__name__} không đòi quyền quản trị"
        )


# =====================================================================
#  Tạo tài khoản
# =====================================================================

def test_mat_khau_toi_thieu_8_ky_tu():
    import asyncio
    with pytest.raises(ValueError, match="8 ký tự"):
        asyncio.run(xac_thuc.tao_nguoi_dung("abc", "ngan"))


def test_vai_tro_la_o_bi_chan():
    import asyncio
    with pytest.raises(ValueError, match="Vai trò"):
        asyncio.run(xac_thuc.tao_nguoi_dung("abc", "matkhaudaihon8", vai_tro="sieu_admin"))


def test_khong_co_trang_tao_tai_khoan_dau_tien_tren_web():
    """
    Trang bootstrap trên web là một cửa mở: giữa lúc cài xong và lúc chủ hệ
    thống kịp vào tạo tài khoản, ai chạm được cổng đó đều tự phong quản trị.
    """
    src = inspect.getsource(routes)
    assert "bootstrap" not in src.lower()
    assert (ROOT / "scripts" / "tao_tai_khoan.py").exists()


# =====================================================================
#  Giới hạn tần suất đăng nhập
# =====================================================================
# scrypt chỉ LÀM CHẬM việc dò mật khẩu (~100ms mỗi lần), không CHẶN nó.
# Không có lớp này thì người dò có thời gian vô hạn.

def _sach_bo_dem():
    xac_thuc._that_bai.clear()


def test_duoi_nguong_thi_van_duoc_thu():
    _sach_bo_dem()
    for _ in range(xac_thuc.DANG_NHAP_TOI_DA - 1):
        xac_thuc.ghi_that_bai("admin")
    assert xac_thuc.bi_khoa_tam("admin") == 0


def test_dat_nguong_thi_bi_khoa():
    _sach_bo_dem()
    for _ in range(xac_thuc.DANG_NHAP_TOI_DA):
        xac_thuc.ghi_that_bai("admin")
    assert xac_thuc.bi_khoa_tam("admin") > 0


def test_khoa_het_han_sau_khi_cua_so_troi_qua():
    """Khoá là tạm thời. Người thật gõ nhầm không bị chặn vĩnh viễn."""
    _sach_bo_dem()
    t = 1000.0
    for _ in range(xac_thuc.DANG_NHAP_TOI_DA):
        xac_thuc.ghi_that_bai("admin", t)
    assert xac_thuc.bi_khoa_tam("admin", t + 1) > 0
    assert xac_thuc.bi_khoa_tam("admin", t + xac_thuc.DANG_NHAP_CUA_SO + 1) == 0


def test_dang_nhap_dung_thi_xoa_lich_su_sai():
    """
    Gõ nhầm bảy lần rồi nhớ ra mật khẩu thì lần sau phải được bắt đầu lại
    từ đầu — nếu không, một người hay quên sẽ tích dần tới ngưỡng và bị
    khoá vì một chuỗi lỗi trải suốt cả ngày.
    """
    _sach_bo_dem()
    for _ in range(xac_thuc.DANG_NHAP_TOI_DA - 1):
        xac_thuc.ghi_that_bai("lan")
    xac_thuc.xoa_that_bai("lan")
    assert xac_thuc.bi_khoa_tam("lan") == 0


def test_dem_rieng_tung_tai_khoan():
    """Người dò khoá được `admin` không có nghĩa là khoá được cả tiệm."""
    _sach_bo_dem()
    for _ in range(xac_thuc.DANG_NHAP_TOI_DA):
        xac_thuc.ghi_that_bai("admin")
    assert xac_thuc.bi_khoa_tam("admin") > 0
    assert xac_thuc.bi_khoa_tam("lan") == 0


def test_ten_khong_ton_tai_cung_bi_dem():
    """
    Bỏ qua tên lạ thì người dò chỉ cần đổi tên mỗi lượt là thoát chốt. Tệ
    hơn: "tên này bị khoá, tên kia không" chính là chỉ ra tên nào có thật.
    """
    _sach_bo_dem()
    for _ in range(xac_thuc.DANG_NHAP_TOI_DA):
        xac_thuc.ghi_that_bai("khong-ton-tai-bao-gio")
    assert xac_thuc.bi_khoa_tam("khong-ton-tai-bao-gio") > 0


def test_ten_khong_phan_biet_hoa_thuong_va_khoang_trang():
    """`dang_nhap()` chuẩn hoá tên trước khi tra; bộ đếm phải chuẩn hoá y hệt,
    nếu không người dò đổi `Admin` / ` admin ` là có bộ đếm mới."""
    _sach_bo_dem()
    for _ in range(xac_thuc.DANG_NHAP_TOI_DA):
        xac_thuc.ghi_that_bai("  ADMIN  ")
    assert xac_thuc.bi_khoa_tam("admin") > 0


def test_chot_tan_suat_chan_truoc_khi_cham_csdl():
    """
    Chốt phải nằm TRƯỚC truy vấn CSDL và trước lần băm scrypt. Đặt sau thì
    chính chốt chống dò trở thành đường làm nghẽn máy chủ: mỗi lần thử vẫn
    tốn một lần đọc bảng và 100ms CPU.
    """
    src = inspect.getsource(xac_thuc.dang_nhap)
    assert src.index("bi_khoa_tam") < src.index("db.fetchrow")


def test_moi_nhanh_that_bai_deu_ghi_vao_bo_dem():
    """
    Ba đường ra thất bại: không có tài khoản, tài khoản bị khoá, sai mật
    khẩu. Bỏ sót một đường là để hở đúng đường đó cho người dò.
    """
    src = inspect.getsource(xac_thuc.dang_nhap)
    assert src.count("ghi_that_bai(") == 3
    assert src.count('log_event("auth.that_bai"') == 3


def test_bo_dem_khong_phinh_vo_han():
    """
    Bộ đếm chỉ tự dọn khi chính tên đó bị chạm lại. Người dò đổi tên mỗi
    lượt thì không tên nào bị chạm lần hai — và chốt chống dò tự biến thành
    đường làm cạn bộ nhớ máy chủ.
    """
    _sach_bo_dem()
    t = 1000.0
    for i in range(xac_thuc._TOI_DA_TEN_THEO_DOI + 50):
        xac_thuc.ghi_that_bai(f"ten-gia-{i}", t)
    assert len(xac_thuc._that_bai) <= xac_thuc._TOI_DA_TEN_THEO_DOI + 1

    # Bỏ mục cũ nhất, không bỏ mục mới nhất: tên đang bị nhắm liên tục
    # được chạm nên luôn nằm trong nhóm mới, và bộ đếm của nó không bị
    # người dò xoá đi bằng cách bắn tên rác.
    assert "ten-gia-0" not in xac_thuc._that_bai
    assert f"ten-gia-{xac_thuc._TOI_DA_TEN_THEO_DOI + 49}" in xac_thuc._that_bai
    _sach_bo_dem()


def test_khong_the_xoa_bo_dem_cua_nguoi_dang_bi_nham_bang_ten_rac():
    """
    Nếu dọn theo kiểu bỏ bừa, người dò chỉ cần bắn đủ tên rác là xoá được
    bộ đếm của `admin` rồi dò tiếp từ đầu — chốt trở thành đồ trang trí.
    """
    _sach_bo_dem()
    t = 1000.0
    for i in range(xac_thuc.DANG_NHAP_TOI_DA):
        xac_thuc.ghi_that_bai("admin", t + i)      # nạn nhân, bị chạm liên tục
    for i in range(xac_thuc._TOI_DA_TEN_THEO_DOI + 100):
        xac_thuc.ghi_that_bai(f"rac-{i}", t + 1)   # tên rác, cũ hơn
        xac_thuc.ghi_that_bai("admin", t + 2 + i)  # người dò vẫn đang thử admin
    assert xac_thuc.bi_khoa_tam("admin", t + 200) > 0
    _sach_bo_dem()
