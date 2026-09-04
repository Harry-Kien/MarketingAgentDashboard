"""
`san_sang` phải bắt được vault và `.env` lệch bí mật sidecar. Không cần CSDL.

LỖI ĐÃ XẢY RA THẬT (04.09.2026)
-------------------------------
`sinh_token ZALO_SIDECAR_SECRET` chạy SAU khi tài khoản Zalo cá nhân đã lưu
bí mật vào vault. Sidecar khởi động với bí mật mới, app ký bằng bí mật cũ:
gửi bị 401, callback bị 401, sidecar báo `disconnected`. Vòng giữ phiên ghi
"cần quét QR lại" 1866 lần — sai bệnh — và `san_sang` vẫn báo kênh Zalo cá
nhân "đã xác minh". Tám ngày không có tin khách nào vào hệ thống.

Phép kiểm này là thứ lẽ ra đã đỏ ngay ngày đầu.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import san_sang  # noqa: E402


def test_lech_thi_CHAN_va_chi_ro_cach_sua():
    kq = san_sang.so_bi_mat_sidecar([("Mr Kiên", "cu")], "moi")
    assert kq["muc"] == san_sang.CHAN
    assert "Mr Kiên" in kq["ghi"]
    assert "Lưu lại" in kq["sua"]


def test_khong_bao_gio_in_gia_tri_bi_mat():
    kq = san_sang.so_bi_mat_sidecar([("A", "bi-mat-cu-rat-dai")], "bi-mat-moi-rat-dai")
    assert "bi-mat-cu-rat-dai" not in kq["ghi"] + kq["sua"]
    assert "bi-mat-moi-rat-dai" not in kq["ghi"] + kq["sua"]


def test_khop_thi_DU():
    kq = san_sang.so_bi_mat_sidecar([("A", "x"), ("B", "x")], "x")
    assert kq["muc"] == san_sang.DU


def test_khong_co_tai_khoan_thi_DU():
    assert san_sang.so_bi_mat_sidecar([], "x")["muc"] == san_sang.DU


def test_phep_kiem_nam_trong_bang_tong():
    """Viết hàm mà quên đưa vào `chay()` thì bảng readiness vẫn xanh giả."""
    nguon = (ROOT / "scripts" / "san_sang.py").read_text(encoding="utf-8")
    than_chay = nguon.split("async def chay()", 1)[1]
    assert "kiem_bi_mat_sidecar()" in than_chay
