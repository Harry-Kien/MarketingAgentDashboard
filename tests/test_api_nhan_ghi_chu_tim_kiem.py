"""
Nhãn, ghi chú nội bộ theo hội thoại, và tìm theo nội dung tin — Postgres thật.

Ba ràng buộc canh ở đây:
1. Ghi chú KHÔNG BAO GIỜ đi ra kênh (không sinh outbox_jobs).
2. Tìm kiếm bỏ dấu + chữ thường, và `%`/`_` không thành ký tự đại diện.
3. Mọi thứ tôn trọng phạm vi kênh: hội thoại kênh không được giao thì 404,
   và không lọt vào kết quả tìm.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID

import asyncpg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import nguoi_thu

ROOT = Path(__file__).resolve().parent.parent
LUOC_DO = ROOT / "agent" / "schema.sql"
UID = "00000000-0000-0000-0000-000000000001"


def _app(url: str, nguoi: dict) -> FastAPI:
    from agent import db
    from agent.api.hoi_thoai_nhan import router as nhan_router
    from agent.api.inbox import router as inbox_router
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.migrations.runner import apply_all

    app = FastAPI()
    app.include_router(inbox_router)
    app.include_router(nhan_router)
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


async def _hoi_thoai(conn, ext: str, tin: str) -> tuple[UUID, UUID]:
    tk = await conn.fetchval(
        "INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
        "VALUES ('webchat',$1,'active',$1) RETURNING id", f"web-{ext}")
    kh = await conn.fetchval("INSERT INTO contacts (display_name) VALUES ($1) RETURNING id", ext)
    d = await conn.fetchval(
        "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
        "VALUES ($1,$2,$3) RETURNING id", kh, tk, ext)
    cid = await conn.fetchval(
        "INSERT INTO conversations (account_id, channel, external_id, customer_ref, "
        "customer_name, contact_id, contact_point_id) "
        "VALUES ($1,'webchat',$2,$2,$2,$3,$4) RETURNING id", tk, ext, kh, d)
    await conn.execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES ($1,'customer',$2)",
        cid, tin)
    return tk, cid


def _dung(url: str) -> dict:
    async def chay():
        conn = await asyncpg.connect(url)
        try:
            await conn.execute(
                "INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, ho_ten) "
                "VALUES ($1,'kt','x','Kiểm Thử') ON CONFLICT DO NOTHING", UUID(UID))
            tk_a, a = await _hoi_thoai(conn, "khach-a", "Kem Chống Nắng còn hàng không 100%?")
            _, b = await _hoi_thoai(conn, "khach-b", "Kem chống nắng bên B")
            await conn.execute(
                "INSERT INTO account_memberships (account_id, user_id) VALUES ($1,$2)",
                tk_a, UUID(UID))
            return {"a": str(a), "b": str(b)}
        finally:
            await conn.close()
    return asyncio.run(chay())


async def _dem(url: str, sql: str) -> int:
    conn = await asyncpg.connect(url)
    try:
        return await conn.fetchval(sql)
    finally:
        await conn.close()


NV = ("hoi_thoai.doc", "hoi_thoai.tra_loi")


def _ids(k, **qs) -> set[str]:
    r = k.get("/api/inbox/conversations", params=qs)
    assert r.status_code == 200, r.text
    return {str(x["id"]) for x in r.json()["items"]}


def test_nhan_gan_go_va_loc(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*NV))) as k:
        h = _dung(csdl_kiem_thu)
        r = k.post(f"/api/inbox/conversations/{h['a']}/nhan", json={"nhan": "  Chờ   Hàng "})
        assert r.status_code == 201 and r.json()["nhan"] == "chờ hàng"
        # Gắn lại cùng nhãn (khác hoa thường) không nhân đôi.
        k.post(f"/api/inbox/conversations/{h['a']}/nhan", json={"nhan": "chờ hàng"})
        dong = k.get("/api/inbox/conversations").json()["items"][0]
        assert dong["nhan"] == ["chờ hàng"]
        assert _ids(k, nhan="chờ hàng") == {h["a"]}
        assert k.get("/api/inbox/nhan").json()["nhan"] == [{"nhan": "chờ hàng", "so": 1}]
        assert k.delete(f"/api/inbox/conversations/{h['a']}/nhan/Chờ Hàng").status_code == 204
        assert _ids(k, nhan="chờ hàng") == set()


def test_ghi_chu_khong_bao_gio_ra_kenh(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*NV))) as k:
        h = _dung(csdl_kiem_thu)
        r = k.post(f"/api/inbox/conversations/{h['a']}/ghi-chu",
                   json={"noi_dung": "Khách hẹn chiều mai gọi lại, đừng nhắc giá"})
        assert r.status_code == 201
        ds = k.get(f"/api/inbox/conversations/{h['a']}/ghi-chu").json()["ghi_chu"]
        assert ds[0]["noi_dung"].startswith("Khách hẹn") and ds[0]["nguoi"] == "Kiểm Thử"
    assert asyncio.run(_dem(csdl_kiem_thu, "SELECT count(*) FROM outbox_jobs")) == 0
    assert asyncio.run(_dem(
        csdl_kiem_thu, "SELECT count(*) FROM messages WHERE content LIKE 'Khách hẹn%'")) == 0


def test_ngoai_kenh_la_404(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*NV))) as k:
        h = _dung(csdl_kiem_thu)
        assert k.post(f"/api/inbox/conversations/{h['b']}/nhan",
                      json={"nhan": "x"}).status_code == 404
        assert k.get(f"/api/inbox/conversations/{h['b']}/ghi-chu").status_code == 404
        assert k.post(f"/api/inbox/conversations/{h['b']}/ghi-chu",
                      json={"noi_dung": "x"}).status_code == 404


def test_tim_khong_dau_khong_hoa_thuong(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*NV))) as k:
        h = _dung(csdl_kiem_thu)
        assert _ids(k, q="kem chong nang") == {h["a"]}, "B ngoài kênh không được lọt"
        assert _ids(k, q="CHỐNG") == {h["a"]}
        assert _ids(k, q="khach-a") == {h["a"]}           # theo tên khách
        assert _ids(k, q="khong co dau nay") == set()


def test_ky_tu_dai_dien_khong_thanh_moi_thu(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*NV, "hoi_thoai.xem_tat_ca"))) as k:
        h = _dung(csdl_kiem_thu)
        assert _ids(k, q="%%") == set()
        assert _ids(k, q="__") == set()
        # "100%" có thật trong tin A — tìm đúng chuỗi ấy phải ra A.
        assert _ids(k, q="100%") == {h["a"]}


def test_q_mot_ky_tu_bi_bo_qua(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*NV, "hoi_thoai.xem_tat_ca"))) as k:
        h = _dung(csdl_kiem_thu)
        assert _ids(k, q="k") == {h["a"], h["b"]}


def test_chi_muc_trigram_khop_bieu_thuc_truy_van():
    """Viết lệch biểu thức là Postgres quét cả bảng messages — chậm im lặng."""
    mig = (ROOT / "agent/migrations/versions/0029_tim_noi_dung_tin.sql").read_text(encoding="utf-8")
    src = (ROOT / "agent/api/inbox.py").read_text(encoding="utf-8")
    assert "lower(public.bo_dau(content))" in mig
    assert "lower(public.bo_dau(tim_tin.content))" in src
