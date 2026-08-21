"""
Kiểm thử lớp nhúng ZaloCRM + Chatwoot. Không gọi API, không cần CSDL.

VÌ SAO FILE NÀY QUAN TRỌNG HƠN VẺ NGOÀI CỦA NÓ
----------------------------------------------
Lớp proxy này cố ý XOÁ `X-Frame-Options` của ZaloCRM — tức là tự tay tháo
một lớp chống clickjacking mà nhà phát triển kia đặt ra. Việc đó chỉ chấp
nhận được khi hai điều kiện còn nguyên:

  1. Proxy nằm TRONG chốt đăng nhập của dashboard.
  2. Không chuyển tiếp thứ gì mà Referer không trỏ đúng vào proxy.

Mất điều kiện 1: cổng 8000 thành cửa sau vào cả ZaloCRM lẫn Chatwoot, không
cần mật khẩu của chúng.
Mất điều kiện 2: bất kỳ trang nào cũng lừa được dashboard chuyển request đi
nơi khác.

Hai điều kiện đó là lời hứa, và lời hứa thì phải có người canh.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import main as app_main  # noqa: E402
from agent.api import tich_hop  # noqa: E402


# =====================================================================
#  Điều kiện 1: proxy nằm TRONG chốt đăng nhập
# =====================================================================

def test_proxy_nam_trong_chot_dang_nhap():
    """
    Middleware là cơ chế HỎNG-ĐÓNG, và `/tich-hop` phải nằm trong đó cùng
    với `/api`. Để ngoài là biến cổng 8000 thành cửa sau vào cả hai hệ thống
    — người lạ vào được ZaloCRM mà không cần mật khẩu ZaloCRM.
    """
    src = inspect.getsource(app_main.chan_neu_chua_dang_nhap)
    assert "/tich-hop" in src


def test_duong_tuyet_doi_cung_phai_kiem_phien():
    """
    Middleware bắt asset lạc cũng chuyển request sang app đích — nên nó phải
    tự kiểm phiên. Không kiểm thì nó chính là đường vòng qua chốt ở trên:
    chỉ cần đặt Referer là đi được.
    """
    src = inspect.getsource(app_main.bat_duong_tuyet_doi)
    assert "doc_phien" in src
    assert "401" in src


def test_proxy_khong_nam_trong_danh_sach_mo():
    """`_MO` là danh sách đường KHÔNG cần đăng nhập. Lọt vào đây là hỏng."""
    assert not any("tich-hop" in d for d in app_main._MO)


# =====================================================================
#  Điều kiện 2: chỉ đi theo Referer trỏ đúng vào proxy
# =====================================================================

def test_referer_tro_vao_proxy_thi_nhan_dung_app():
    assert tich_hop.ung_dung_tu_referer(
        "http://localhost:8000/tich-hop/chatwoot/app/accounts/1") == "chatwoot"
    assert tich_hop.ung_dung_tu_referer(
        "http://localhost:8000/tich-hop/zalocrm/") == "zalocrm"


def test_referer_khong_phai_proxy_thi_khong_chuyen_di_dau():
    """
    Request của chính dashboard tuyệt đối không được chuyển sang app khác.
    Nhận nhầm ở đây là dashboard tự gửi dữ liệu của mình đi nơi khác.
    """
    for r in ("", "http://localhost:8000/", "http://localhost:8000/api/overview",
              "https://ke-xau.example/trang-gia"):
        assert tich_hop.ung_dung_tu_referer(r) is None, r


def test_ten_app_la_tren_danh_sach_trang_khong_phai_doan():
    """
    Tên lạ phải trả None. Nếu không, một Referer dựng sẵn kiểu
    `/tich-hop/evil.com/` sẽ biến dashboard thành máy chuyển tiếp mù —
    đúng định nghĩa SSRF.
    """
    for r in ("http://localhost:8000/tich-hop/evil.com/",
              "http://localhost:8000/tich-hop/../etc/",
              "http://localhost:8000/tich-hop/google/"):
        assert tich_hop.ung_dung_tu_referer(r) is None, r


def test_dich_chi_biet_hai_ten():
    import pytest
    from fastapi import HTTPException

    assert tich_hop._dich("zalocrm").startswith("http")
    assert tich_hop._dich("chatwoot").startswith("http")
    with pytest.raises(HTTPException):
        tich_hop._dich("evil.com")


def test_duong_cua_he_thong_luon_duoc_uu_tien():
    """
    Dashboard nằm NGOÀI iframe vẫn phải gọi API của chính nó trong lúc
    iframe đang mở — và lúc đó Referer trỏ vào proxy. Không ưu tiên đường
    nhà thì mở màn Kết nối lên là cả dashboard ngừng hoạt động.
    """
    src = inspect.getsource(app_main.bat_duong_tuyet_doi)
    for duong in ("/api", "/webhook", "/healthz", "/media"):
        assert f'"{duong}"' in src, duong


# =====================================================================
#  Xoá header chặn nhúng — lý do cả lớp này tồn tại
# =====================================================================

def test_xoa_moi_header_chan_nhung():
    """
    ZaloCRM đặt DENY, Chatwoot đặt SAMEORIGIN. Sót một cái là iframe trắng
    trơn, và trắng trơn thì không có thông báo lỗi nào để lần ra.
    """
    for h in ("x-frame-options", "content-security-policy",
              "content-security-policy-report-only"):
        assert h in tich_hop._CHAN_NHUNG


def test_khong_chep_header_tang_van_chuyen():
    """
    Chép `content-length` sang khi nội dung đã giải nén là cách nhanh nhất
    làm trình duyệt treo giữa chừng — nó đợi số byte không bao giờ tới.
    """
    for h in ("content-encoding", "content-length", "transfer-encoding"):
        assert h in tich_hop._BO_QUA


# =====================================================================
#  Chuyển hướng phải ở lại trong proxy
# =====================================================================

def test_chuyen_huong_tuyet_doi_duoc_keo_ve_trong_proxy():
    """
    Chatwoot trả `Location: /app/login`. Không sửa thì trình duyệt nhảy ra
    gốc cổng 8000 và người dùng rơi khỏi iframe vào giữa dashboard.
    """
    assert tich_hop._sua_location("/app/login", "chatwoot",
                                  "http://127.0.0.1:3200") \
        == "/tich-hop/chatwoot/app/login"


def test_chuyen_huong_day_du_cung_duoc_keo_ve():
    assert tich_hop._sua_location("http://127.0.0.1:3200/app/login", "chatwoot",
                                  "http://127.0.0.1:3200") \
        == "/tich-hop/chatwoot/app/login"


def test_khong_keo_ve_hai_lan():
    """Location đã nằm trong proxy rồi thì để yên, nếu không thành
    `/tich-hop/chatwoot/tich-hop/chatwoot/...`."""
    assert tich_hop._sua_location("/tich-hop/chatwoot/app", "chatwoot",
                                  "http://127.0.0.1:3200") \
        == "/tich-hop/chatwoot/app"


def test_khong_dung_toi_lien_ket_ra_ngoai():
    """Chuyển hướng sang OAuth của Facebook phải đi thẳng, không kéo về."""
    ngoai = "https://www.facebook.com/v18.0/dialog/oauth?client_id=1"
    assert tich_hop._sua_location(ngoai, "chatwoot", "http://127.0.0.1:3200") == ngoai


# =====================================================================
#  WebSocket — hộp thư Chatwoot sống nhờ nó
# =====================================================================

def test_co_duong_cable_o_goc():
    """
    ActionCable mở WebSocket bằng đường TUYỆT ĐỐI `/cable`, y như asset.
    Thiếu đường này thì giao diện vẫn mở, vẫn đăng nhập được, nhưng tin mới
    KHÔNG bao giờ tự hiện — người trực phải bấm F5. Đó là kiểu hỏng tệ
    nhất: trông như đang chạy.
    """
    duong = {r.path for r in app_main.app.routes if hasattr(r, "path")}
    assert "/cable" in duong


def test_websocket_mang_theo_cookie():
    """ActionCable xác thực bằng chính phiên Chatwoot. Không gửi cookie thì
    bắt tay xong là bị đá ra ngay."""
    src = inspect.getsource(tich_hop.cau_websocket)
    assert "cookie" in src.lower()
