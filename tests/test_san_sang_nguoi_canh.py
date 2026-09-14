"""
`san_sang` phải nói khi NGƯỜI CANH BÊN NGOÀI đã ngừng chạy. Không cần CSDL.

Người canh (`scripts/canh_gac_ngoai.py`) là thứ dựng lại app lúc 2 giờ
sáng. Nó chết thì không có gì báo: app vẫn sống, dashboard vẫn xanh, cho
tới lần app chết kế tiếp — lúc đó mới biết là không còn ai dựng lại. Đo
được 14.09.2026: sau khi máy bật lại, không tra được người canh đã chạy
lại chưa và đã làm gì.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import san_sang  # noqa: E402


def test_chua_tung_chay_thi_CANH_BAO_va_chi_cach_dang_ky():
    kq = san_sang.doc_nguoi_canh(None)
    assert kq["muc"] == san_sang.CANH_BAO
    assert "canh_gac_ngoai" in kq["sua"]


def test_qua_15_phut_thi_CANH_BAO():
    kq = san_sang.doc_nguoi_canh(47.0)
    assert kq["muc"] == san_sang.CANH_BAO
    assert "47 phút" in kq["ghi"]


def test_vua_chay_thi_DU():
    assert san_sang.doc_nguoi_canh(3.0)["muc"] == san_sang.DU


def test_doc_tu_file_trang_thai_that(monkeypatch, tmp_path):
    """Đọc mtime của đúng file người canh ghi — không phải file nào khác."""
    monkeypatch.setattr(san_sang, "ROOT", tmp_path)
    assert san_sang.kiem_nguoi_canh()["muc"] == san_sang.CANH_BAO
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / ".canh_gac_ngoai").write_text('{"trang_thai": "tot"}', encoding="utf-8")
    assert san_sang.kiem_nguoi_canh()["muc"] == san_sang.DU


def test_phep_kiem_nam_trong_bang_tong():
    """Viết hàm mà quên đưa vào `chay()` thì bảng readiness vẫn xanh giả."""
    nguon = (ROOT / "scripts" / "san_sang.py").read_text(encoding="utf-8")
    assert "kiem_nguoi_canh()" in nguon.split("async def chay()", 1)[1]


def test_bat_nguoi_canh_ghi_nhat_ky_va_khong_co_dau():
    """
    Task Scheduler nuốt stdout: không ghi ra file thì "đêm qua người canh có
    dựng lại app không" là câu không ai trả lời được. Và file .bat có dấu
    tiếng Việt là Windows đọc sai lệnh mà vẫn báo thành công.
    """
    tho = (ROOT / "scripts" / "canh_gac_ngoai.bat").read_bytes()
    tho.decode("ascii")                       # ném UnicodeDecodeError nếu có dấu
    van_ban = tho.decode("ascii")
    assert "canh_gac_ngoai.log" in van_ban and "2>&1" in van_ban
    assert "%DATE% %TIME%" in van_ban         # mỗi lần chạy một mốc giờ
    assert "canh_gac_ngoai.log.1" in van_ban  # có xoay, không phình vô hạn
