"""
URL công khai chết thì phải KÊU, không được hiện "tốt".

LỖI THẬT, ĐO ĐƯỢC 04.09.2026

Tunnel `trycloudflare` sống được 1,5 tiếng rồi bị Cloudflare huỷ từ phía họ:

    ERR Register tunnel error from server side
        error="Unauthorized: Tunnel not found"

Tiến trình `cloudflared` VẪN CHẠY và vẫn thử lại mãi — nên mọi phép kiểm
kiểu "cloudflared còn sống không" đều trả lời có. Suốt bảy tiếng sau đó URL
công khai chết, không webhook nào tới được, mà `/api/suc-khoe` trả `"tot"`
và cả bốn kênh hiện `active` với `ly_do_hong` rỗng.

Xanh giả — kiểu nguy hiểm nhất, vì đỏ giả thì người ta đi kiểm còn xanh giả
thì không ai kiểm.

CHỈ THÊM MỘT MỤC LÀ ĐỦ

`canh_gac.kiem_mot_lan` gọi `suc_khoe.tong_kiem` định kỳ và báo động khi
trạng thái tổng chuyển sang `hong`. Nên mục mới vừa hiện trên dashboard vừa
đánh thức người — miễn là nó trả `hong` chứ không phải `canh_bao`.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import suc_khoe  # noqa: E402
from agent.config import settings  # noqa: E402

NGUON = (ROOT / "agent" / "suc_khoe.py").read_text(encoding="utf-8")


def chay(coro):
    return asyncio.run(coro)


class _PhanHoi:
    def __init__(self, ma: int, than: str):
        self.status_code = ma
        self.text = than


class _Client:
    """Đứng thay `httpx.AsyncClient` — không chạm mạng thật."""

    def __init__(self, ket):
        self._ket = ket

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        if isinstance(self._ket, BaseException):
            raise self._ket
        return self._ket


def dat_mang(monkeypatch, ket) -> None:
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _Client(ket))


def dat_url(monkeypatch, url: str) -> None:
    monkeypatch.setattr(settings, "public_base_url", url, raising=False)


THAT = '{"ok":true,"runtime":{"mode":"auto"}}'


# ---------------------------------------------------------------
#  Ca trung tâm — tái hiện đúng chuyện đã xảy ra
# ---------------------------------------------------------------

def test_tunnel_chet_thi_HONG(monkeypatch):
    dat_url(monkeypatch, "https://stated-luck-tested-lived.trycloudflare.com")
    dat_mang(monkeypatch, OSError("không phân giải được tên miền"))
    m = chay(suc_khoe._kiem_cong_cong_khai())
    assert m["trang_thai"] == suc_khoe.HONG, (
        "URL công khai chết mà không báo hỏng — đúng cái xanh giả đã xảy ra"
    )
    assert "webhook" in m["ghi_chu"].lower(), "phải nói rõ hậu quả"


def test_HONG_chu_khong_phai_canh_bao(monkeypatch):
    """
    `canh_gac.kiem_mot_lan` CỐ Ý không đánh thức ai vì `canh_bao`. Hạ mục này
    xuống `canh_bao` là biến nó thành một dòng chữ không ai đọc.
    """
    dat_url(monkeypatch, "https://mot-ten-mien-that.example.net")
    dat_mang(monkeypatch, OSError("mất mạng"))
    assert chay(suc_khoe._kiem_cong_cong_khai())["trang_thai"] != suc_khoe.CANH_BAO


def test_song_thi_TOT(monkeypatch):
    dat_url(monkeypatch, "https://co-that.trycloudflare.com")
    dat_mang(monkeypatch, _PhanHoi(200, THAT))
    assert chay(suc_khoe._kiem_cong_cong_khai())["trang_thai"] == suc_khoe.TOT


# ---------------------------------------------------------------
#  Mã 200 CHƯA đủ — phải đúng ứng dụng này
# ---------------------------------------------------------------

@pytest.mark.parametrize("ma,than", [
    (200, "<html>Cloudflare Tunnel error</html>"),
    (200, '{"ok":false}'),
    (530, "Origin DNS error"),
    (502, "Bad gateway"),
    (404, "not found"),
])
def test_khong_phai_ung_dung_nay_thi_HONG(monkeypatch, ma, than):
    """
    Tunnel chết mà DNS còn phân giải được thì Cloudflare trả trang lỗi của
    CHÍNH NÓ. Chỉ xem mã HTTP là có ngày nhận 200 từ một trang báo lỗi.
    """
    dat_url(monkeypatch, "https://co-that.trycloudflare.com")
    dat_mang(monkeypatch, _PhanHoi(ma, than))
    assert chay(suc_khoe._kiem_cong_cong_khai())["trang_thai"] == suc_khoe.HONG


def test_doc_than_phan_hoi_chu_khong_chi_ma():
    """Canh bằng mã nguồn: bỏ phép đọc thân là mất lớp bảo vệ trên."""
    for node in ast.walk(ast.parse(NGUON)):
        if (isinstance(node, ast.AsyncFunctionDef)
                and node.name == "_kiem_cong_cong_khai"):
            than = ast.unparse(node)
            assert "r.text" in than, "không đọc thân phản hồi"
            return
    raise AssertionError("không tìm thấy _kiem_cong_cong_khai")


# ---------------------------------------------------------------
#  Địa chỉ nội bộ: cảnh báo, KHÔNG phải "tốt"
# ---------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://localhost:8000", "http://127.0.0.1:8000",
    "http://host.docker.internal:8000", "http://0.0.0.0:8000", "",
])
def test_dia_chi_noi_bo_KHONG_bao_gio_la_tot(monkeypatch, url):
    """
    Đây là trạng thái phát triển bình thường, không phải sự cố — nên
    `canh_bao`, không `hong`. Gắn nhãn "Hệ thống đang hỏng" cho nó là cách
    nhanh nhất khiến người ta tắt thông báo, và lần sau hỏng thật thì không
    ai thấy.

    Nhưng cũng KHÔNG được là `tot`: Zalo/Meta không gọi vào localhost được.
    """
    dat_url(monkeypatch, url)
    assert chay(suc_khoe._kiem_cong_cong_khai())["trang_thai"] == suc_khoe.CANH_BAO


def test_dia_chi_noi_bo_KHONG_goi_mang(monkeypatch):
    """Gọi ra ngoài cho một URL hiển nhiên nội bộ là tốn 8 giây mỗi lượt."""
    def no(**kw):
        raise AssertionError("không được gọi mạng cho địa chỉ nội bộ")

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", no)
    dat_url(monkeypatch, "http://localhost:8000")
    chay(suc_khoe._kiem_cong_cong_khai())


# ---------------------------------------------------------------
#  Phải NẰM TRONG vòng kiểm, nếu không nó chỉ là mã chết
# ---------------------------------------------------------------

def test_tong_kiem_CO_goi_muc_nay():
    """
    Viết phép kiểm rồi quên cắm vào `tong_kiem` là có đủ mã, đủ test, và
    vẫn không ai được báo — chính xác cái lỗ hổng đang vá.
    """
    for node in ast.walk(ast.parse(NGUON)):
        if (isinstance(node, ast.AsyncFunctionDef) and node.name == "tong_kiem"):
            assert "_kiem_cong_cong_khai()" in ast.unparse(node), (
                "tong_kiem không gọi phép kiểm cổng công khai"
            )
            return
    raise AssertionError("không tìm thấy tong_kiem")


def test_ngoai_le_KHONG_do_nguyen_van_ra_ghi_chu(monkeypatch):
    """
    `httpx` nhét URL đầy đủ vào thông điệp ngoại lệ, và URL ấy đã từng mang
    theo token khi có tham số truy vấn. Giữ TÊN ngoại lệ là đủ để gỡ lỗi.
    """
    dat_url(monkeypatch, "https://co-that.trycloudflare.com")
    dat_mang(monkeypatch, OSError("token=SIEU_BI_MAT_KHONG_DUOC_LO"))
    assert "SIEU_BI_MAT" not in chay(suc_khoe._kiem_cong_cong_khai())["ghi_chu"]


def test_khong_lam_chet_tong_kiem(monkeypatch):
    """
    Một phép kiểm ném ra là `asyncio.gather` biến nó thành ngoại lệ, và
    trang sức khoẻ mất luôn mọi mục khác.
    """
    dat_url(monkeypatch, "https://co-that.trycloudflare.com")
    dat_mang(monkeypatch, RuntimeError("hỏng bất ngờ"))
    m = chay(suc_khoe._kiem_cong_cong_khai())   # không được ném
    assert m["trang_thai"] == suc_khoe.HONG
