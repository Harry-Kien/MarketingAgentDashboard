"""
`san_sang` phải bắt được sidecar đang chạy với bí mật khác `.env`. Không cần CSDL.

LỖI ĐÃ XẢY RA THẬT (04.09.2026)
-------------------------------
`sinh_token ZALO_SIDECAR_SECRET` chạy SAU khi sidecar đã bật và tài khoản
đã lưu vào vault. Sidecar ký bằng bí mật cũ, app bằng bí mật mới: gửi 401,
callback 401, sidecar báo `disconnected`. Vòng giữ phiên ghi "cần quét QR
lại" 1866 lần — sai bệnh — nút Quét QR báo "sidecar chưa chạy" — cũng sai
bệnh — và `san_sang` vẫn báo kênh "đã xác minh". Tám ngày không tin khách.

Phép kiểm hỏi THẲNG sidecar bằng bí mật `.env`, vì đó là cách duy nhất để
biết hai tiến trình có đang nói cùng một thứ tiếng không.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import san_sang  # noqa: E402


def test_sai_chu_ky_thi_CHAN_va_bao_khoi_dong_lai_sidecar():
    kq = san_sang.doc_tham_do_sidecar("Chữ ký sidecar không hợp lệ", True)
    assert kq["muc"] == san_sang.CHAN
    assert "chay_sidecar_zalo" in kq["sua"]
    # Đây là bệnh mà nút Quét QR từng chẩn sai; bản kiểm phải nói ngược lại.
    assert "ĐANG CHẠY" in kq["ghi"]


def test_khong_phan_hoi_ma_co_tai_khoan_thi_CANH_BAO():
    kq = san_sang.doc_tham_do_sidecar("ConnectError: sidecar không phản hồi", True)
    assert kq["muc"] == san_sang.CANH_BAO
    assert "chay_sidecar_zalo" in kq["sua"]


def test_khong_phan_hoi_ma_khong_co_tai_khoan_thi_DU():
    """Máy chưa nối Zalo cá nhân không được bị bắt bật một sidecar vô dụng."""
    kq = san_sang.doc_tham_do_sidecar("ConnectError: sidecar không phản hồi", False)
    assert kq["muc"] == san_sang.DU


def test_tra_loi_duoc_thi_DU():
    assert san_sang.doc_tham_do_sidecar(None, True)["muc"] == san_sang.DU


def test_phep_kiem_nam_trong_bang_tong():
    """Viết hàm mà quên đưa vào `chay()` thì bảng readiness vẫn xanh giả."""
    nguon = (ROOT / "scripts" / "san_sang.py").read_text(encoding="utf-8")
    than_chay = nguon.split("async def chay()", 1)[1]
    assert "kiem_bi_mat_sidecar()" in than_chay
