"""
Phiên bị chiếm KHÔNG được gỡ 2FA hay đổi mật khẩu — đo trên app thật.

Rà soát 16.11.2026: `POST /api/toi/hai-buoc/bat-dau` không hỏi gì và đặt
`hai_buoc_bat = false` NGAY khi gọi — một request từ phiên bị chiếm (cookie
lộ, máy quên khoá) là gỡ được lớp bảo vệ mà chính nó sinh ra để chặn.
`POST /api/toi/doi-mat-khau` không hỏi mật khẩu cũ — kẻ cầm cookie đổi mật
khẩu rồi đá chủ thật ra khỏi mọi thiết bị.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pyotp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_nghiem_thu_saas import MK, _dang_nhap, _nhan_vien_moi, _quan_tri_vao, _sql  # noqa: E402


def _trang_thai(app, uid: str) -> dict:
    from agent import db

    async def doc(u):
        return dict(await db.fetchrow(
            "SELECT hai_buoc_bat, totp_ma_hoa IS NOT NULL AS co_bi_mat, "
            "totp_cho_ma_hoa IS NOT NULL AS co_cho FROM nguoi_dung WHERE id = $1::uuid", u))
    return _sql(app, doc, uid)


def _bat_2fa(nv) -> str:
    r = nv.post("/api/toi/hai-buoc/bat-dau", json={"mat_khau": MK})
    assert r.status_code == 200, r.text
    bi_mat = pyotp.parse_uri(r.json()["uri"]).secret
    r = nv.post("/api/toi/hai-buoc/xac-nhan", json={"ma": pyotp.TOTP(bi_mat).now()})
    assert r.status_code == 200, r.text
    return bi_mat


def test_bat_dau_khong_mat_khau_bi_chan(app_that):
    qt = _quan_tri_vao(app_that)
    uid, nv = _nhan_vien_moi(qt, "lan")
    assert nv.post("/api/toi/hai-buoc/bat-dau").status_code == 403
    assert nv.post("/api/toi/hai-buoc/bat-dau", json={"mat_khau": "sai-roi-nhe"}).status_code == 403
    assert _trang_thai(app_that, uid)["co_cho"] is False


def test_phien_bi_chiem_KHONG_go_duoc_2fa_dang_bat(app_that):
    qt = _quan_tri_vao(app_that)
    uid, nv = _nhan_vien_moi(qt, "lan")
    _bat_2fa(nv)
    assert _trang_thai(app_that, uid)["hai_buoc_bat"] is True

    # Kẻ cầm cookie, không mật khẩu, không mã: mọi đường đều đóng.
    assert nv.post("/api/toi/hai-buoc/bat-dau").status_code == 403
    # Có mật khẩu (lộ) nhưng không có điện thoại: vẫn đóng.
    assert nv.post("/api/toi/hai-buoc/bat-dau", json={"mat_khau": MK}).status_code == 403
    assert _trang_thai(app_that, uid)["hai_buoc_bat"] is True, "2FA bị gỡ"


def test_dang_ky_lai_giu_2fa_cu_toi_khi_xac_nhan_bi_mat_moi(app_that):
    """Đổi điện thoại: bí mật mới nằm ở CHỜ; mã cũ vẫn đăng nhập được tới lúc xác nhận."""
    qt = _quan_tri_vao(app_that)
    uid, nv = _nhan_vien_moi(qt, "lan")
    cu = _bat_2fa(nv)
    time.sleep(0)  # (mã dùng một lần theo bước 30 giây — dùng bước kế tiếp)
    ma_cu = pyotp.TOTP(cu).at(time.time() + 30)
    r = nv.post("/api/toi/hai-buoc/bat-dau", json={"mat_khau": MK, "ma": ma_cu})
    assert r.status_code == 200, r.text
    moi = pyotp.parse_uri(r.json()["uri"]).secret
    tt = _trang_thai(app_that, uid)
    assert tt["hai_buoc_bat"] is True and tt["co_cho"] is True, "bat-dau đã tắt 2FA"

    # Bỏ dở giữa chừng: đăng nhập vẫn đòi mã CŨ.
    app_that.cookies.clear()
    r = app_that.post("/api/dang-nhap", json={"ten_dang_nhap": "lan", "mat_khau": MK})
    assert r.status_code == 401 and r.json()["detail"]["can_ma_2fa"] is True

    # Xác nhận bằng bí mật MỚI thì mới thay.
    r = nv.post("/api/toi/hai-buoc/xac-nhan", json={"ma": pyotp.TOTP(moi).now()})
    assert r.status_code == 200, r.text
    tt = _trang_thai(app_that, uid)
    assert tt["hai_buoc_bat"] is True and tt["co_cho"] is False


def test_doi_mat_khau_doi_mat_khau_cu(app_that):
    qt = _quan_tri_vao(app_that)
    _, nv = _nhan_vien_moi(qt, "lan")
    assert nv.post("/api/toi/doi-mat-khau",
                   json={"mat_khau_moi": "moi-dai-hon-tam"}).status_code == 422
    assert nv.post("/api/toi/doi-mat-khau",
                   json={"mat_khau_cu": "sai-roi", "mat_khau_moi": "moi-dai-hon-tam"}).status_code == 403
    # Mật khẩu cũ vẫn dùng được — chưa đổi gì.
    assert _dang_nhap(app_that, "lan", MK)[0] == 200
    _, nv = _dang_nhap(app_that, "lan", MK)
    assert nv.post("/api/toi/doi-mat-khau",
                   json={"mat_khau_cu": MK, "mat_khau_moi": "moi-dai-hon-tam"}).status_code == 200
    assert _dang_nhap(app_that, "lan", "moi-dai-hon-tam")[0] == 200


def test_go_lai_mat_khau_sai_tinh_vao_bo_dem_chong_do(app_that):
    """Không thì phiên bị chiếm biến các route này thành máy dò mật khẩu."""
    from agent.core import xac_thuc

    qt = _quan_tri_vao(app_that)
    _, nv = _nhan_vien_moi(qt, "lan")
    try:
        for _ in range(xac_thuc.DANG_NHAP_TOI_DA):
            nv.post("/api/toi/hai-buoc/tat", json={"mat_khau": "doan-bua"})
        r = nv.post("/api/toi/doi-mat-khau",
                    json={"mat_khau_cu": MK, "mat_khau_moi": "moi-dai-hon-tam"})
        assert r.status_code == 429
    finally:
        xac_thuc.xoa_that_bai("lan")


def test_giao_dien_gui_mat_khau_cu_va_mat_khau_khi_bat_2fa():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    js_tk = (ROOT / "dashboard" / "src" / "08-tai-khoan.js").read_text(encoding="utf-8")
    js_2fa = (ROOT / "dashboard" / "src" / "14-cskh.js").read_text(encoding="utf-8")
    assert 'name="mat_khau_cu"' in html
    assert "mat_khau_cu: d.mat_khau_cu" in js_tk
    doan = js_2fa[js_2fa.index('"/toi/hai-buoc/bat-dau"'):][:200]
    assert "mat_khau" in doan
