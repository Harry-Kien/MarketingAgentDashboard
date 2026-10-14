"""
Giải quyết hội thoại, mở lại khi khách nhắn tiếp, và CSAT — Postgres thật.

Lỗ được bịt: luồng native không có thao tác "đã giải quyết", `resolved_at`
không bao giờ được ghi, và bộ canh SLA coi mọi hội thoại là trễ giải quyết.
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
    from agent.api.hoi_thoai_nhan import router
    from agent.api.routes import nguoi_da_dang_nhap
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
def csat_bat(monkeypatch):
    from agent import cau_hinh_dong
    gia = {"CSAT_BAT": "bat"}
    monkeypatch.setattr(cau_hinh_dong, "lay", lambda k: gia.get(k, ""))
    return gia


def _dung(url: str, *, thanh_vien: bool = True) -> str:
    async def chay():
        conn = await asyncpg.connect(url)
        try:
            await conn.execute(
                "INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, ho_ten) "
                "VALUES ($1,'kt','x','kt') ON CONFLICT DO NOTHING", UID)
            tk = await conn.fetchval(
                "INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
                "VALUES ('webchat','Web','active','web-gq') RETURNING id")
            kh = await conn.fetchval("INSERT INTO contacts (display_name) VALUES ('Lan') RETURNING id")
            d = await conn.fetchval(
                "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
                "VALUES ($1,$2,'lan') RETURNING id", kh, tk)
            cid = await conn.fetchval(
                "INSERT INTO conversations (account_id, channel, external_id, customer_ref, "
                "customer_name, contact_id, contact_point_id, assigned_to, resolution_due_at) "
                "VALUES ($1,'webchat','lan','lan','Lan',$2,$3,$4, now() + interval '1 hour') "
                "RETURNING id", tk, kh, d, UID)
            await conn.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES ($1,'customer','hỏi')", cid)
            await conn.execute(
                "INSERT INTO conversation_assignments (conversation_id, assigned_user_id, source, reason) "
                "VALUES ($1,$2,'manual','kt')", cid, UID)
            if thanh_vien:
                await conn.execute(
                    "INSERT INTO account_memberships (account_id, user_id) VALUES ($1,$2)", tk, UID)
            return str(cid)
        finally:
            await conn.close()
    return asyncio.run(chay())


async def _mot(url: str, sql: str, *a):
    conn = await asyncpg.connect(url)
    try:
        return await conn.fetchrow(sql, *a)
    finally:
        await conn.close()


Q = ("hoi_thoai.nhan", "hoi_thoai.doc")


def _goi(url: str, ham, *a):
    """Chạy một hàm của giai_quyet với pool RIÊNG — pool của TestClient thuộc loop khác."""
    from agent import db

    async def chay():
        async def _codec(conn):
            await conn.set_type_codec("jsonb", encoder=json.dumps,
                                      decoder=json.loads, schema="pg_catalog")
        pool = await asyncpg.create_pool(url, min_size=1, max_size=2, init=_codec)
        cu = db._pool
        db._pool = pool
        try:
            return await ham(*a)
        finally:
            db._pool = cu
            await pool.close()
    return asyncio.run(chay())


def test_giai_quyet_ghi_resolved_at_ket_thuc_giao_va_sla_dat(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*Q))) as k:
        cid = _dung(csdl_kiem_thu)
        r = k.post(f"/api/inbox/conversations/{cid}/giai-quyet")
        assert r.status_code == 200, r.text
        assert r.json() == {"da_truoc": False, "csat": "tắt"}
        assert k.post(f"/api/inbox/conversations/{cid}/giai-quyet").json()["da_truoc"] is True
    c = asyncio.run(_mot(csdl_kiem_thu, "SELECT state, status, resolved_at FROM conversations"))
    assert c["state"] == "resolved" and c["status"] == "closed" and c["resolved_at"]
    gq = asyncio.run(_mot(csdl_kiem_thu,
                          "SELECT count(*) FILTER (WHERE ended_at IS NULL) AS mo FROM conversation_assignments"))
    assert gq["mo"] == 0
    sla = asyncio.run(_mot(csdl_kiem_thu, "SELECT kind FROM sla_events"))
    assert sla["kind"] == "resolution_met"


def test_ngoai_kenh_la_404(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*Q))) as k:
        cid = _dung(csdl_kiem_thu, thanh_vien=False)
        assert k.post(f"/api/inbox/conversations/{cid}/giai-quyet").status_code == 404


def test_csat_hoi_ghi_diem_va_cam_on(csdl_kiem_thu, csat_bat):
    from agent.omnichannel import giai_quyet
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*Q))) as k:
        cid = _dung(csdl_kiem_thu)
        assert k.post(f"/api/inbox/conversations/{cid}/giai-quyet").json()["csat"] == "đã hỏi"
    # Khách trả lời "5 sao" -> là ĐIỂM, không phải câu hỏi mới.
    assert _goi(csdl_kiem_thu, giai_quyet.ghi_diem_neu_la_csat, UUID(cid), "5 sao") is True
    # Lần thứ hai không còn phiếu chờ -> không phải điểm.
    assert _goi(csdl_kiem_thu, giai_quyet.ghi_diem_neu_la_csat, UUID(cid), "4") is False
    c = asyncio.run(_mot(csdl_kiem_thu, "SELECT diem, nguoi_xu_ly FROM csat"))
    assert c["diem"] == 5 and c["nguoi_xu_ly"] == UID
    jobs = asyncio.run(_mot(csdl_kiem_thu,
                            "SELECT count(*) AS n FROM outbox_jobs"))
    assert jobs["n"] == 2                      # câu hỏi + lời cảm ơn
    st = asyncio.run(_mot(csdl_kiem_thu, "SELECT state FROM conversations"))
    assert st["state"] == "resolved"


def test_khach_nhan_tiep_thi_mo_lai_cho_agent(csdl_kiem_thu):
    from agent.omnichannel import giai_quyet
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*Q))) as k:
        cid = _dung(csdl_kiem_thu)
        k.post(f"/api/inbox/conversations/{cid}/giai-quyet")
    assert _goi(csdl_kiem_thu, giai_quyet.mo_lai_neu_da_giai_quyet, UUID(cid)) is True
    assert _goi(csdl_kiem_thu, giai_quyet.mo_lai_neu_da_giai_quyet, UUID(cid)) is False
    c = asyncio.run(_mot(csdl_kiem_thu,
                         "SELECT state, status, mode, resolved_at FROM conversations"))
    assert (c["state"], c["status"], c["mode"], c["resolved_at"]) == ("open", "auto", "auto", None)


@pytest.mark.parametrize("cau,diem", [
    ("5", 5), (" 4 ", 4), ("3 sao", 3), ("1.", 1), ("5 ⭐", 5),
    ("5 cái", None), ("15", None), ("0", None), ("6", None), ("size 5", None), ("", None),
])
def test_doc_diem(cau, diem):
    from agent.omnichannel.giai_quyet import doc_diem
    assert doc_diem(cau) == diem
