"""
Màn "Kết nối kênh": mỗi kênh một dòng xanh/vàng/đỏ kèm đúng một việc cần làm.

Canh ba chỗ từng hỏng IM LẶNG (19.11.2026):
- Trang Facebook "Đang chạy" màu xanh trong khi quyền dữ liệu còn 5 ngày —
  vòng canh token đã biết từ hôm trước nhưng chỉ báo vào webhook và nhật ký.
- Zalo OA "active" mà chưa từng có webhook nào tới.
- Địa chỉ công khai là tunnel tạm, đổi tên miền là webhook chết.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.omnichannel import suc_khoe_kenh as skk  # noqa: E402

BAY_GIO = datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc)
CO_TIN = BAY_GIO - timedelta(hours=3)


def _dg(**kw):
    kw.setdefault("bay_gio", BAY_GIO)
    return skk.danh_gia(**kw)


# ------------------------------------------------------------------ luật
def test_trang_xanh_ma_token_con_5_ngay_phai_hien_vang_kem_nut_dang_nhap():
    d = _dg(channel="facebook", status="active", tin_vao_gan_nhat=CO_TIN,
            token={"kind": "meta.token_sap_het", "ngay_con_lai": 5.3,
                   "luc": BAY_GIO - timedelta(hours=2)})
    assert d.muc == skk.VANG and d.hanh_dong == "dang_nhap_meta"
    assert "5 ngày" in d.viec


def test_token_con_duoi_3_ngay_la_do():
    d = _dg(channel="facebook", status="active", tin_vao_gan_nhat=CO_TIN,
            token={"kind": "meta.token_sap_het", "ngay_con_lai": 2,
                   "luc": BAY_GIO - timedelta(hours=1)})
    assert d.muc == skk.DO


def test_token_chet_la_do():
    d = _dg(channel="instagram", status="active", tin_vao_gan_nhat=CO_TIN,
            token={"kind": "meta.token_chet", "ngay_con_lai": None,
                   "luc": BAY_GIO - timedelta(hours=1)})
    assert d.muc == skk.DO and d.hanh_dong == "dang_nhap_meta"


def test_su_kien_token_cu_khong_con_tinh():
    """Quá 2 ngày không có sự kiện mới = đã cấp quyền lại — không báo mãi."""
    d = _dg(channel="facebook", status="active", tin_vao_gan_nhat=CO_TIN,
            token={"kind": "meta.token_sap_het", "ngay_con_lai": 5,
                   "luc": BAY_GIO - timedelta(days=3)})
    assert d.muc == skk.XANH


def test_kenh_webhook_chua_tung_nhan_tin_la_vang():
    d = _dg(channel="zalo_oa", status="active", tin_vao_gan_nhat=None)
    assert d.muc == skk.VANG and d.hanh_dong == "nhan_thu"


def test_webchat_chua_co_tin_van_xanh():
    """Webchat không qua webhook của hãng — chưa có khách không phải là hỏng."""
    assert _dg(channel="webchat", status="active").muc == skk.XANH


@pytest.mark.parametrize("kenh, hanh_dong", [
    ("zalo_personal", "quet_qr"), ("facebook", "dang_nhap_meta"),
    ("zalo_oa", "xac_minh")])
def test_mat_quyen_la_do_kem_dung_nut(kenh, hanh_dong):
    d = _dg(channel=kenh, status="reauth_required")
    assert d.muc == skk.DO and d.hanh_dong == hanh_dong


def test_zalo_ca_nhan_dang_ket_noi_la_do_va_giu_ly_do():
    d = _dg(channel="zalo_personal", status="degraded", ly_do_hong="sidecar không phản hồi")
    assert d.muc == skk.DO and "sidecar" in d.viec and d.hanh_dong == "quet_qr"


def test_trang_cho_nhan_tin_la_vang_nut_nhan_tin():
    d = _dg(channel="facebook", status="pending")
    assert d.muc == skk.VANG and d.hanh_dong == "nhan_tin"


def test_tam_ngat_la_tat():
    assert _dg(channel="facebook", status="disabled").muc == skk.TAT


def test_moi_dong_khong_xanh_deu_co_viec_can_lam():
    """Một dòng đỏ không kèm việc cần làm là dòng người ta thôi đọc."""
    for kenh in ("facebook", "instagram", "whatsapp", "zalo_oa", "zalo_personal", "webchat"):
        for st in ("pending", "degraded", "reauth_required", "disabled", "active"):
            d = _dg(channel=kenh, status=st)
            assert d.viec.strip()
            if d.muc in (skk.DO, skk.VANG) and st != "degraded":
                assert d.hanh_dong, (kenh, st)


@pytest.mark.parametrize("url, muc", [
    ("http://host.docker.internal:8000", skk.DO),
    ("", skk.DO),
    ("https://abc-def.trycloudflare.com", skk.VANG),
    ("https://cskh.blanica.vn", skk.XANH),
])
def test_dia_chi_cong_khai(url, muc):
    assert skk.danh_gia_dia_chi_cong_khai(url).muc == muc


# ------------------------------------------------------------------ route
def test_route_dat_truoc_account_id():
    """Sau `/{account_id}` thì "suc-khoe-tong" bị hiểu là UUID → 422."""
    from agent.api.channel_accounts import router

    duong = [getattr(r, "path", "") for r in router.routes]
    assert duong.index("/api/channel-accounts/suc-khoe-tong") < duong.index(
        "/api/channel-accounts/{account_id}")


def test_route_suc_khoe_tong_tren_app_that(app_that):
    from tests.test_nghiem_thu_saas import _kenh_webchat, _quan_tri_vao

    qt = _quan_tri_vao(app_that)
    _kenh_webchat(qt)
    r = qt.get("/api/channel-accounts/suc-khoe-tong")
    assert r.status_code == 200, r.text
    d = r.json()
    assert {x["ten"] for x in d["dieu_kien"]} >= {"Địa chỉ công khai"}
    assert d["kenh"] and all(k["muc"] in ("xanh", "vang", "do", "tat") for k in d["kenh"])
    assert set(d["dem"]) == {"xanh", "vang", "do", "tat"}


def test_su_kien_token_khop_dung_tai_khoan(app_that):
    """Vòng canh ghi account_id → dòng của đúng tài khoản chuyển vàng."""
    from agent import db
    from tests.test_nghiem_thu_saas import _kenh_webchat, _quan_tri_vao, _sql

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt, ten="Web có token giả")

    async def ghi():
        # Webchat không phải Meta nên luật bỏ qua token — chỉ kiểm khớp số ngày.
        await db.log_event("meta.token_sap_het", account_id=tk, tai_khoan="x",
                           kenh="webchat", ngay_con_lai=4.0)
    _sql(app_that, ghi)
    d = qt.get("/api/channel-accounts/suc-khoe-tong").json()
    dong = next(k for k in d["kenh"] if k["id"] == tk)
    assert dong["token_con_ngay"] == 4.0


# ------------------------------------------------------------------ việc từ vòng canh
def test_tao_viec_kenh_chong_trung_va_bao_nhan_vien(app_that, monkeypatch):
    from agent import canh_gac, db
    from agent.core import cong_viec
    from tests.test_nghiem_thu_saas import _sql

    bao: list = []
    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen", lambda *a, **k: bao.append(a))

    async def tao():
        a = await cong_viec.tao_tu_kenh(tieu_de="Đăng nhập Facebook lại", mo_ta="x",
                                        khoa="kenh:token_meta:abc:2026-11-24")
        b = await cong_viec.tao_tu_kenh(tieu_de="Đăng nhập Facebook lại", mo_ta="x",
                                        khoa="kenh:token_meta:abc:2026-11-24")
        n = await db.fetchrow("SELECT count(*) AS n FROM cong_viec "
                              "WHERE khoa_chong_trung = 'kenh:token_meta:abc:2026-11-24'")
        return a, b, n["n"]
    a, b, n = _sql(app_that, tao)
    assert a is not None and b is None and n == 1
    assert len(bao) == 1, "việc mới phải báo nhân viên đúng một lần"


def test_vong_canh_token_sinh_viec():
    """Nguồn: vòng canh token phải gọi tao_tu_kenh và ghi account_id."""
    import inspect

    from agent import main

    src = inspect.getsource(main)
    khoi = src[src.index('"meta.token_sap_het" if kq["muc"] == "sap_het"'):][:2500]
    assert "account_id=str(acc.id)" in khoi
    assert "tao_tu_kenh(" in khoi
