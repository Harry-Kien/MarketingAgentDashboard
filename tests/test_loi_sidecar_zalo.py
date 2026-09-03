"""
Sidecar tắt phải ra thông điệp hành động được, không phải `500`.

NGƯỜI DÙNG BÁO BẰNG ẢNH CHỤP (03.09.2026)

Bấm "Quét QR" trên Zalo cá nhân và nhận:

    Không xin được mã: Internal Server Error

Ba đường `zalo-personal/{qr,restore,status}` để `RuntimeError` lọt thẳng ra
ngoài, và FastAPI biến nó thành `500 Internal Server Error`. Người dùng
nhận đúng bốn chữ đó — trong khi ngoại lệ đã nói rõ:

    "ConnectError: sidecar không phản hồi"

Sidecar là TIẾN TRÌNH RIÊNG, không nằm trong repo và không nằm trong
docker-compose. Nó tắt là chuyện thường: máy khởi động lại, người vận hành
đóng nhầm cửa sổ. Một sự cố thường gặp mà báo bằng `500` thì mỗi lần gặp
lại tốn một vòng hỏi–đáp.

503 CHỨ KHÔNG PHẢI 500

Đây là dịch vụ phụ thuộc chưa sẵn sàng, không phải lỗi lập trình. Mã đúng
giúp người đọc log phân biệt hai loại — và giúp máy giám sát không báo động
nhầm là ứng dụng hỏng.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import HTTPException  # noqa: E402

from agent.api.channel_accounts import _loi_sidecar  # noqa: E402

NGUON = (ROOT / "agent" / "api" / "channel_accounts.py").read_text(encoding="utf-8")
BA_DUONG = ("start_zalo_personal_qr", "restore_zalo_personal_session",
            "zalo_personal_status")


# ---------------------------------------------------------------
#  Dịch lỗi thành việc phải làm
# ---------------------------------------------------------------

def test_sidecar_tat_ra_503_va_noi_phai_lam_gi():
    """Tái hiện đúng ngoại lệ người dùng gặp."""
    e = _loi_sidecar(RuntimeError("ConnectError: sidecar không phản hồi"))
    assert isinstance(e, HTTPException)
    assert e.status_code == 503, "503 = dịch vụ phụ thuộc, không phải lỗi lập trình"
    assert "3210" in e.detail, "phải nói rõ cổng nào"
    assert "chưa chạy" in e.detail


def test_giu_lai_ly_do_goc():
    """
    Người vận hành cần câu hướng dẫn; người gỡ lỗi cần chuỗi gốc. Giữ cả
    hai — bỏ chuỗi gốc là mất đường tra khi lỗi hoá ra không phải sidecar.
    """
    assert "ConnectError" in _loi_sidecar(
        RuntimeError("ConnectError: sidecar không phản hồi")
    ).detail


@pytest.mark.parametrize("exc", [ConnectionError("mat mang"), OSError("cong dong")])
def test_loi_mang_cung_ra_503(exc):
    assert _loi_sidecar(exc).status_code == 503


def test_loi_KHAC_thi_502_chu_khong_gop_chung():
    """
    Sidecar CHẠY nhưng trả lỗi là chuyện khác hẳn sidecar TẮT. Gộp cả hai
    thành "chưa chạy" là bảo người ta đi bật một thứ đang chạy.
    """
    e = _loi_sidecar(ValueError("Tham số không hợp lệ"))
    assert e.status_code == 502
    assert "Tham số không hợp lệ" in e.detail


def test_cat_bot_thong_diep_qua_dai():
    """Traceback nội bộ đổ nguyên vào toast là bức tường chữ không ai đọc."""
    assert len(_loi_sidecar(RuntimeError("x" * 5000)).detail) < 400


def test_ngoai_le_khong_co_thong_diep_van_ra_duoc_gi_do():
    assert _loi_sidecar(RuntimeError()).detail


# ---------------------------------------------------------------
#  Cả BA đường đều phải bọc
# ---------------------------------------------------------------

def _ham(ten: str) -> ast.AsyncFunctionDef:
    for node in ast.walk(ast.parse(NGUON)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == ten:
            return node
    raise AssertionError(f"không tìm thấy {ten}")


@pytest.mark.parametrize("ten", BA_DUONG)
def test_moi_duong_deu_bat_loi_sidecar(ten):
    """
    Ba đường cùng gọi sidecar. Bọc hai quên một thì đúng đường bị quên vẫn
    trả `500`, và không ai biết cho tới lúc bấm phải nó.
    """
    assert "_loi_sidecar" in ast.unparse(_ham(ten)), f"{ten} chưa bọc lỗi sidecar"


@pytest.mark.parametrize("ten", BA_DUONG)
def test_khong_nuot_HTTPException_da_co_y_nghia(ten):
    """
    `restore_session` tự ném `409 Chưa có session`. Bắt trần rồi bọc lại
    thành 503 là đổi một thông điệp đúng thành một thông điệp sai.
    """
    than = ast.unparse(_ham(ten))
    if "try:" not in than:
        pytest.skip("đường này không có khối try")
    assert "except HTTPException:" in than, (
        f"{ten} phải cho HTTPException đi qua, không bọc lại"
    )


def test_khong_con_de_ngoai_le_lot_thanh_500():
    """
    Canh chiều ngược lại: ai đó gỡ khối try là quay lại `500 Internal
    Server Error` — và người dùng lại nhận đúng bốn chữ vô nghĩa ấy.
    """
    for ten in BA_DUONG:
        than = ast.unparse(_ham(ten))
        assert "except Exception" in than, (
            f"{ten} không còn bắt ngoại lệ chung — sẽ lọt thành 500"
        )
