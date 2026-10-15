"""
Xác thực hai bước (TOTP) và chặn dò mật khẩu theo IP.

Canh:
- mã đúng bước hiện tại hoặc lệch ±1 bước (đồng hồ điện thoại lệch) — không hơn;
- mật khẩu đúng mà thiếu mã → hỏi mã, KHÔNG tạo phiên;
- mã sai → tính là một lần đăng nhập sai;
- một mã chỉ dùng được một lần (replay); mã dự phòng dùng một lần;
- kẻ dò đổi tên mỗi lượt vẫn bị chặn theo IP.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pyotp
import pytest

from agent.core import hai_buoc, xac_thuc

BI_MAT = "JBSWY3DPEHPK3PXP"


def test_buoc_khop_dung_va_lech_mot_buoc():
    t = 1_760_000_000.0
    totp = pyotp.TOTP(BI_MAT)
    b = int(t // 30)
    assert hai_buoc._buoc_khop(BI_MAT, totp.at(t), t) == b
    assert hai_buoc._buoc_khop(BI_MAT, totp.at(t - 30), t) == b - 1
    assert hai_buoc._buoc_khop(BI_MAT, totp.at(t + 30), t) == b + 1
    assert hai_buoc._buoc_khop(BI_MAT, totp.at(t - 90), t) is None
    assert hai_buoc._buoc_khop(BI_MAT, totp.at(t)[:5], t) is None
    assert hai_buoc._buoc_khop(BI_MAT, "abcdef", t) is None


@pytest.fixture
def dang_nhap_gia(monkeypatch):
    xac_thuc._that_bai.clear()
    hop = {"nd": {"id": uuid.uuid4(), "mat_khau_bam": xac_thuc.bam_mat_khau("dung-roi-123"),
                  "vai_tro": "nhan_vien", "khoa": False, "hai_buoc_bat": True},
           "ma_dung": True, "phien": 0}

    async def fetchrow(sql, *a):
        return hop["nd"]

    async def execute(sql, *a):
        if "INSERT INTO phien" in sql:
            hop["phien"] += 1

    async def log_event(*a, **k):
        return None

    async def kiem(uid, ma, t=None):
        return hop["ma_dung"]

    monkeypatch.setattr(xac_thuc.db, "fetchrow", fetchrow)
    monkeypatch.setattr(xac_thuc.db, "execute", execute)
    monkeypatch.setattr(xac_thuc.db, "log_event", log_event)
    monkeypatch.setattr(hai_buoc, "kiem", kiem)
    yield hop
    xac_thuc._that_bai.clear()


def test_thieu_ma_thi_hoi_ma_khong_tao_phien(dang_nhap_gia):
    with pytest.raises(xac_thuc.CanMaHaiBuoc):
        asyncio.run(xac_thuc.dang_nhap("an", "dung-roi-123"))
    assert dang_nhap_gia["phien"] == 0


def test_ma_sai_tinh_la_lan_sai(dang_nhap_gia):
    dang_nhap_gia["ma_dung"] = False
    with pytest.raises(xac_thuc.MaHaiBuocSai):
        asyncio.run(xac_thuc.dang_nhap("an", "dung-roi-123", "123456"))
    assert dang_nhap_gia["phien"] == 0
    assert len(xac_thuc._that_bai.get("an", [])) == 1


def test_ma_dung_thi_tao_phien(dang_nhap_gia):
    assert asyncio.run(xac_thuc.dang_nhap("an", "dung-roi-123", "123456"))
    assert dang_nhap_gia["phien"] == 1


def test_sai_mat_khau_khong_lo_la_co_2fa(dang_nhap_gia):
    """Sai mật khẩu → None như mọi tài khoản; không hỏi mã (lộ 2FA = lộ tên đúng)."""
    assert asyncio.run(xac_thuc.dang_nhap("an", "sai", "")) is None


def test_do_doi_ten_moi_luot_van_bi_chan_theo_ip(dang_nhap_gia):
    dang_nhap_gia["nd"] = None
    for i in range(xac_thuc.DANG_NHAP_TOI_DA_IP):
        asyncio.run(xac_thuc.dang_nhap(f"ten{i}", "x", ip="10.0.0.9"))
    assert xac_thuc.bi_khoa_tam("ip:10.0.0.9", toi_da=xac_thuc.DANG_NHAP_TOI_DA_IP) > 0
    # IP khác không bị vạ lây.
    assert xac_thuc.bi_khoa_tam("ip:10.0.0.10", toi_da=xac_thuc.DANG_NHAP_TOI_DA_IP) == 0


def test_route_tra_can_ma_2fa(dang_nhap_gia):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agent.api.routes import router
    app = FastAPI()
    app.include_router(router)
    r = TestClient(app).post("/api/dang-nhap",
                             json={"ten_dang_nhap": "an", "mat_khau": "dung-roi-123"})
    assert r.status_code == 401 and r.json()["detail"]["can_ma_2fa"] is True


# ---------------- Postgres thật: lưu mã hoá, replay, mã dự phòng ----------------

def test_vong_doi_2fa_tren_csdl_that(csdl_kiem_thu, monkeypatch):
    import base64
    import json

    import asyncpg

    from agent import db
    from agent.migrations.runner import apply_all
    from pathlib import Path

    monkeypatch.setattr(hai_buoc.settings, "credential_master_keys",
                        "1:" + base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setattr(hai_buoc.settings, "credential_active_key_version", 1)

    async def chay():
        async def _codec(conn):
            await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads,
                                      schema="pg_catalog")
        pool = await asyncpg.create_pool(csdl_kiem_thu, min_size=1, max_size=2, init=_codec)
        cu = db._pool
        db._pool = pool
        try:
            async with pool.acquire() as conn:
                await conn.execute((Path(__file__).resolve().parent.parent / "agent" /
                                    "schema.sql").read_text(encoding="utf-8"))
                await apply_all(conn)
            nd = await xac_thuc.tao_nguoi_dung("hai.buoc", "mat-khau-du-dai")
            uid = uuid.UUID(str(nd["id"]))
            uri = await hai_buoc.bat_dau(uid, "hai.buoc")
            bi_mat = pyotp.parse_uri(uri).secret
            async with pool.acquire() as conn:
                tho = await conn.fetchrow("SELECT totp_ma_hoa, hai_buoc_bat FROM nguoi_dung "
                                          "WHERE id = $1", uid)
            assert bi_mat.encode() not in bytes(tho["totp_ma_hoa"]), "bí mật lưu nguyên văn"
            assert tho["hai_buoc_bat"] is False, "chưa xác nhận mà đã bật"

            assert await hai_buoc.xac_nhan(uid, "000000") is None
            t = __import__("time").time()
            du_phong = await hai_buoc.xac_nhan(uid, pyotp.TOTP(bi_mat).at(t))
            assert du_phong and len(du_phong) == hai_buoc.SO_MA_DU_PHONG

            ma_sau = pyotp.TOTP(bi_mat).at(t + 30)
            assert await hai_buoc.kiem(uid, ma_sau, t + 30) is True
            assert await hai_buoc.kiem(uid, ma_sau, t + 30) is False, "dùng lại mã cũ được"

            assert await hai_buoc.kiem(uid, du_phong[0]) is True
            assert await hai_buoc.kiem(uid, du_phong[0]) is False, "mã dự phòng dùng hai lần"
        finally:
            db._pool = cu
            await pool.close()
    asyncio.run(chay())
