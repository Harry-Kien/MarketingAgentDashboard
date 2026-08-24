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

import asyncio
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import main as app_main  # noqa: E402
from agent.api import tich_hop  # noqa: E402
from agent.api.routes import TEN_COOKIE  # noqa: E402
from agent.core import xac_thuc  # noqa: E402


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
    assert tich_hop.ung_dung_tu_referer(
        "http://localhost:8000/tich-hop/n8n/workflow/1") == "n8n"
    assert tich_hop.ung_dung_tu_referer(
        "http://localhost:8000/tich-hop/minio/browser") == "minio"


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


# ---------------------------------------------------------------------
#  Điều kiện 1, VẾ WEBSOCKET — chỗ chốt đăng nhập KHÔNG với tới
# ---------------------------------------------------------------------

class _WSGia:
    """WebSocket giả, đủ dùng cho phần `cau_websocket` chạm tới."""

    def __init__(self, cookies=None, query=""):
        self.cookies = cookies or {}
        self.headers = {}
        self.url = type("U", (), {"query": query})()
        self.da_accept = False
        self.ma_dong = None

    async def accept(self):
        self.da_accept = True

    async def close(self, code=1000):
        self.ma_dong = code


def test_middleware_http_KHONG_cham_toi_websocket():
    """
    Ca này canh một sự thật của THƯ VIỆN, không phải của mã ta viết.

    Cả lớp bảo vệ `/tich-hop` dựa trên middleware trong `main.py`. Nếu
    middleware đó cũng chặn WebSocket thì hàm `phien_hop_le` là thừa. Nó
    KHÔNG chặn — và ngày nào Starlette đổi điều đó, ca này đỏ để ta biết mà
    đọc lại, thay vì giữ mãi một lớp kiểm không còn cần.
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    src = inspect.getsource(BaseHTTPMiddleware.__call__)
    assert 'scope["type"] != "http"' in src


def test_websocket_khong_co_phien_bi_tu_choi():
    """Không phiên dashboard thì không có kênh nào được mở."""
    ws = _WSGia()
    asyncio.run(tich_hop.cau_websocket(ws, "chatwoot", "cable"))
    assert ws.da_accept is False, "đã accept trước khi kiểm phiên"
    assert ws.ma_dong == 1008


def test_websocket_phien_hong_cung_bi_tu_choi(monkeypatch):
    """Cookie có mặt nhưng phiên hết hạn cũng phải bị chặn."""
    async def het_han(_token):
        return None
    monkeypatch.setattr(xac_thuc, "doc_phien", het_han)

    ws = _WSGia(cookies={TEN_COOKIE: "token-da-het-han"})
    asyncio.run(tich_hop.cau_websocket(ws, "chatwoot", "cable"))
    assert ws.da_accept is False
    assert ws.ma_dong == 1008


def test_websocket_co_phien_thi_di_tiep(monkeypatch):
    """
    Vế còn lại: siết chặt quá tay thì người trực mất hộp thư mà không ai
    biết vì sao. Có phiên hợp lệ là phải đi qua được.
    """
    async def hop_le(_token):
        return {"id": 1, "ten_dang_nhap": "an", "vai_tro": "quan_tri"}
    monkeypatch.setattr(xac_thuc, "doc_phien", hop_le)

    ws = _WSGia(cookies={TEN_COOKIE: "token-tot"})
    # Nối lên thượng nguồn sẽ hỏng (không có Chatwoot nào đang chạy) và
    # `cau_websocket` nuốt lỗi đó — nhưng nó chỉ tới được chỗ ấy sau khi
    # đã accept, nên `da_accept` là bằng chứng chốt phiên đã cho qua.
    asyncio.run(tich_hop.cau_websocket(ws, "chatwoot", "cable"))
    assert ws.da_accept is True
    assert ws.ma_dong != 1008


def test_websocket_ten_app_la_thi_tu_choi_chu_khong_no():
    """
    `_dich` ném HTTPException — hợp lý cho route HTTP, vô nghĩa cho
    WebSocket: không có gì biến nó thành 404, nó chỉ thành lỗi chưa bắt.
    """
    async def hop_le(_token):
        return {"id": 1, "ten_dang_nhap": "an", "vai_tro": "quan_tri"}
    tich_hop_xac_thuc = xac_thuc.doc_phien
    xac_thuc.doc_phien = hop_le
    try:
        ws = _WSGia(cookies={TEN_COOKIE: "token-tot"})
        asyncio.run(tich_hop.cau_websocket(ws, "evil.com", "cable"))
    finally:
        xac_thuc.doc_phien = tich_hop_xac_thuc
    assert ws.da_accept is False
    assert ws.ma_dong == 1008


# =====================================================================
#  Bốn ứng dụng, và chỉ bốn
# =====================================================================

def test_dung_bon_ung_dung():
    assert set(tich_hop.UNG_DUNG) == {"zalocrm", "chatwoot", "n8n", "minio"}


def test_moi_ung_dung_deu_co_dia_chi():
    for ten in tich_hop.UNG_DUNG:
        assert tich_hop._dich(ten).startswith("http"), ten


def test_danh_sach_trang_va_referer_dung_chung_mot_nguon():
    """
    Hai chỗ kiểm tên app phải đọc cùng một danh sách. Lệch nhau thì một tên
    qua được cửa này mà chặn ở cửa kia — và cái lệch đó chính là loại lỗ
    hổng người ta chỉ phát hiện sau khi bị lợi dụng.
    """
    src = inspect.getsource(tich_hop.ung_dung_tu_referer)
    assert "UNG_DUNG" in src


def test_dich_vu_khai_nhung_duoc():
    """
    Màn Hệ thống quyết định mở trong dashboard hay mở tab mới dựa vào cờ
    này. Thiếu cờ thì mặc định mở tab mới — thận trọng đúng hướng, vì một
    iframe trắng khó lần ra hơn một tab mới.
    """
    from agent.he_thong import DICH_VU

    theo_ma = {d["ma"]: d for d in DICH_VU}
    for ten in tich_hop.UNG_DUNG:
        assert theo_ma[ten].get("nhung_duoc") is True, ten
    # Chính dashboard KHÔNG được tự nhúng vào chính nó.
    assert not theo_ma["dashboard"].get("nhung_duoc")
