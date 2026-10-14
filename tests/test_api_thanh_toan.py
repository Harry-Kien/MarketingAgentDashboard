"""
API VietQR cho đơn hàng — Postgres thật, không gọi mạng.

Số tiền trong mã phải là tổng hàng + phí ship ĐỌC TỪ CSDL; chưa cấu hình
ngân hàng thì nói rõ thiếu gì; đơn của kênh không được giao thì 404; bấm
"Gửi QR" hai lần không gửi hai mã.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import nguoi_thu

ROOT = Path(__file__).resolve().parent.parent
LUOC_DO = ROOT / "agent" / "schema.sql"
UID = UUID("00000000-0000-0000-0000-000000000001")


def _app(url: str, nguoi: dict) -> FastAPI:
    from agent import db
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.api.thanh_toan import router
    from agent.migrations.runner import apply_all

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[nguoi_da_dang_nhap] = lambda: nguoi

    async def _codec(conn):
        await conn.set_type_codec("jsonb", encoder=json.dumps,
                                  decoder=json.loads, schema="pg_catalog")

    @app.on_event("startup")
    async def _mo():
        db._pool = await asyncpg.create_pool(url, min_size=1, max_size=3, init=_codec)
        async with db._pool.acquire() as conn:
            await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
            await apply_all(conn)

    @app.on_event("shutdown")
    async def _dong():
        if db._pool is not None:
            await db._pool.close()
            db._pool = None

    return app


@pytest.fixture
def ngan_hang(monkeypatch, tmp_path):
    from agent import cau_hinh_dong
    from agent.api import thanh_toan
    gia = {"VIETQR_BIN": "970436", "VIETQR_SO_TK": "0011001234567",
           "VIETQR_TEN_TK": "CUA HANG THU"}
    monkeypatch.setattr(cau_hinh_dong, "lay", lambda k: gia.get(k, ""))
    monkeypatch.setattr(thanh_toan, "THU_MUC_TAI_LEN", tmp_path)
    return gia


def _dung(url: str, *, thanh_vien: bool = True, trang_thai: str = "da_chot") -> str:
    async def chay():
        conn = await asyncpg.connect(url)
        try:
            await conn.execute(
                "INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, ho_ten) "
                "VALUES ($1,'kt','x','kt') ON CONFLICT DO NOTHING", UID)
            tk = await conn.fetchval(
                "INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
                "VALUES ('webchat','Web','active','web-tt') RETURNING id")
            kh = await conn.fetchval("INSERT INTO contacts (display_name) VALUES ('Lan') RETURNING id")
            d = await conn.fetchval(
                "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
                "VALUES ($1,$2,'lan') RETURNING id", kh, tk)
            cid = await conn.fetchval(
                "INSERT INTO conversations (account_id, channel, external_id, customer_ref, "
                "customer_name, contact_id, contact_point_id) "
                "VALUES ($1,'webchat','lan','lan','Lan',$2,$3) RETURNING id", tk, kh, d)
            if thanh_vien:
                await conn.execute(
                    "INSERT INTO account_memberships (account_id, user_id) VALUES ($1,$2)", tk, UID)
            return str(await conn.fetchval(
                "INSERT INTO orders (ma_don, conversation_id, channel, khach_ten, khach_sdt, "
                "khach_dia_chi, items, tong_tien, phi_van_chuyen, trang_thai) "
                "VALUES ('AS251014',$1,'webchat','Lan','0900000000','x','[]'::jsonb,245000,30000,$2) "
                "RETURNING id", cid, trang_thai))
        finally:
            await conn.close()
    return asyncio.run(chay())


Q = ("don.doc", "hoi_thoai.tra_loi")


def test_so_tien_la_tong_hang_cong_ship(csdl_kiem_thu, ngan_hang):
    from agent.thanh_toan.vietqr import tao_payload
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*Q))) as k:
        oid = _dung(csdl_kiem_thu)
        r = k.get(f"/api/orders/{oid}/vietqr")
        assert r.status_code == 200, r.text
        assert r.json()["so_tien"] == 275000
        assert r.json()["payload"] == tao_payload(
            bin_nh="970436", so_tk="0011001234567", so_tien=275000, noi_dung="AS251014")
        svg = k.get(f"/api/orders/{oid}/vietqr.svg")
        assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg+xml")


def test_chua_cau_hinh_thi_noi_ro_thieu_gi(csdl_kiem_thu, monkeypatch):
    from agent import cau_hinh_dong
    monkeypatch.setattr(cau_hinh_dong, "lay", lambda k: "")
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*Q))) as k:
        oid = _dung(csdl_kiem_thu)
        r = k.get(f"/api/orders/{oid}/vietqr")
        assert r.status_code == 409 and "mã BIN" in r.json()["detail"]


def test_don_huy_khong_tao_ma(csdl_kiem_thu, ngan_hang):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*Q))) as k:
        oid = _dung(csdl_kiem_thu, trang_thai="da_huy")
        assert k.get(f"/api/orders/{oid}/vietqr").status_code == 409


def test_don_cua_kenh_khong_duoc_giao_la_404(csdl_kiem_thu, ngan_hang):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*Q))) as k:
        oid = _dung(csdl_kiem_thu, thanh_vien=False)
        assert k.get(f"/api/orders/{oid}/vietqr").status_code == 404
        assert k.post(f"/api/orders/{oid}/vietqr/gui").status_code == 404


def test_gui_qr_xep_hang_mot_lan(csdl_kiem_thu, ngan_hang):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*Q))) as k:
        oid = _dung(csdl_kiem_thu)
        r1 = k.post(f"/api/orders/{oid}/vietqr/gui")
        assert r1.status_code == 200, r1.text
        r2 = k.post(f"/api/orders/{oid}/vietqr/gui")
        assert r2.json()["duplicate"] is True

    async def doc():
        conn = await asyncpg.connect(csdl_kiem_thu)
        try:
            return await conn.fetch("SELECT kind, payload FROM outbox_jobs")
        finally:
            await conn.close()
    jobs = asyncio.run(doc())
    assert len(jobs) == 1 and jobs[0]["kind"] == "send_file"
    p = jobs[0]["payload"]
    p = json.loads(p) if isinstance(p, str) else p
    assert "275.000đ" in p["caption"] and Path(p["path"]).exists()


def test_gui_qr_can_quyen_xem_don(csdl_kiem_thu, ngan_hang):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("hoi_thoai.tra_loi"))) as k:
        oid = _dung(csdl_kiem_thu)
        assert k.post(f"/api/orders/{oid}/vietqr/gui").status_code == 403


def test_cau_hinh_kiem_dinh_dang():
    from agent.cau_hinh_dong import KhoaKhongHopLe, kiem_gia_tri
    assert kiem_gia_tri("VIETQR_BIN", "970436") == "970436"
    for khoa, sai in (("VIETQR_BIN", "97043"), ("VIETQR_BIN", "abcdef"),
                      ("VIETQR_SO_TK", "0011 0012"), ("VIETQR_SO_TK", "12345")):
        with pytest.raises(KhoaKhongHopLe):
            kiem_gia_tri(khoa, sai)
