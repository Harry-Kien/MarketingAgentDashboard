"""
Route hội thoại CŨ (`agent/api/routes.py`) phải tôn trọng thành viên kênh.

LỖ ĐO ĐƯỢC 14.10.2026
---------------------
Màn inbox mới (`agent/api/inbox.py`) lọc hội thoại theo `account_memberships`:
nhân viên chỉ thấy hội thoại của tài khoản kênh mình được giao. Nhưng route
cũ `GET /api/conversations` và `GET /api/conversations/{id}` trả MỌI hội
thoại — kèm toàn bộ tin nhắn — cho ai có `hoi_thoai.doc`. `send`,
`send-file`, `approve` và ghim nick cũng không hỏi tới thành viên.

Bộ lọc ở màn mới vì thế chỉ là một lớp sơn: dashboard chính nó còn gọi
route cũ cho hàng đợi "Chờ người xử lý", và ai gọi thẳng API là đọc được
hội thoại của kênh không được giao.

Ngoài phạm vi trả 404, không 403: 403 xác nhận hội thoại tồn tại.
"""
from __future__ import annotations

import asyncio
import json
import re
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
    from agent.api.routes import nguoi_da_dang_nhap, router
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


async def _hoi_thoai(conn, ext: str) -> tuple[UUID, UUID]:
    tk = await conn.fetchval(
        "INSERT INTO channel_accounts (channel, display_name, status, "
        "external_account_id) VALUES ('webchat',$1,'active',$1) RETURNING id",
        f"web-{ext}")
    kh = await conn.fetchval(
        "INSERT INTO contacts (display_name) VALUES ($1) RETURNING id", ext)
    diem = await conn.fetchval(
        "INSERT INTO contact_points (contact_id, channel_account_id, "
        "external_user_id) VALUES ($1,$2,$3) RETURNING id", kh, tk, ext)
    cid = await conn.fetchval(
        "INSERT INTO conversations (account_id, channel, external_id, "
        "customer_ref, customer_name, contact_id, contact_point_id, status) "
        "VALUES ($1,'webchat',$2,$2,$2,$3,$4,'escalated') RETURNING id",
        tk, ext, kh, diem)
    await conn.execute(
        "INSERT INTO messages (conversation_id, role, content) "
        "VALUES ($1,'customer',$2)", cid, f"tin bí mật của {ext}")
    return tk, cid


def _dung(url: str) -> dict:
    """Kênh A (người thử là thành viên) và kênh B (không)."""
    async def chay():
        conn = await asyncpg.connect(url)
        try:
            await conn.execute(
                "INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, ho_ten) "
                "VALUES ($1,'kt','x','kt')", UUID(UID))
            tk_a, cid_a = await _hoi_thoai(conn, "khach-a")
            _, cid_b = await _hoi_thoai(conn, "khach-b")
            await conn.execute(
                "INSERT INTO account_memberships (account_id, user_id) VALUES ($1,$2)",
                tk_a, UUID(UID))
            return {"a": str(cid_a), "b": str(cid_b)}
        finally:
            await conn.close()
    return asyncio.run(chay())


QUYEN_NV = ("hoi_thoai.doc", "hoi_thoai.tra_loi", "hoi_thoai.nhan")


def test_danh_sach_chi_co_kenh_duoc_giao(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QUYEN_NV))) as k:
        hoi = _dung(csdl_kiem_thu)
        ids = {c["id"] for c in k.get("/api/conversations?status=all").json()}
        assert hoi["a"] in ids
        assert hoi["b"] not in ids, "route cũ lộ hội thoại của kênh không được giao"
        hang_doi = {c["id"] for c in k.get("/api/conversations?status=can_nguoi").json()}
        assert hoi["b"] not in hang_doi


def test_chi_tiet_ngoai_kenh_la_404(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QUYEN_NV))) as k:
        hoi = _dung(csdl_kiem_thu)
        assert k.get(f"/api/conversations/{hoi['a']}").status_code == 200
        r = k.get(f"/api/conversations/{hoi['b']}")
        assert r.status_code == 404
        assert "bí mật" not in r.text


def test_gui_tin_ngoai_kenh_la_404_va_khong_xep_hang(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QUYEN_NV))) as k:
        hoi = _dung(csdl_kiem_thu)
        r = k.post(f"/api/conversations/{hoi['b']}/send", json={"text": "chào"})
        assert r.status_code == 404

        async def dem():
            conn = await asyncpg.connect(csdl_kiem_thu)
            try:
                return await conn.fetchval("SELECT count(*) FROM outbox_jobs")
            finally:
                await conn.close()
        assert asyncio.run(dem()) == 0


def test_xem_tat_ca_thay_ca_hai_kenh(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu,
                         nguoi_thu(*QUYEN_NV, "hoi_thoai.xem_tat_ca"))) as k:
        hoi = _dung(csdl_kiem_thu)
        ids = {c["id"] for c in k.get("/api/conversations?status=all").json()}
        assert {hoi["a"], hoi["b"]} <= ids
        assert k.get(f"/api/conversations/{hoi['b']}").status_code == 200


def test_moi_route_co_conv_id_deu_chot_pham_vi():
    """
    Canh cấu trúc: route mới thêm vào tầng API có `{conv_id}` mà quên chốt
    là lỗ cũ quay lại. Hoặc gọi thẳng, hoặc đi qua chốt mức tầm nhìn (đã gọi
    chốt phạm vi bên trong), hoặc đi qua routing service (tự kiểm thành viên).
    """
    from tests.nguon_api import nguon_api

    khoi = re.split(r"\n(?=@router\.)", nguon_api())
    thieu, da_xet = [], 0
    for k in khoi:
        m = re.match(r'@router\.\w+\("(/conversations/\{conv_id\}[^"]*)"', k)
        if not m:
            continue
        da_xet += 1
        than = k.split("\n\n\n", 1)[0]
        if not any(x in than for x in ("chan_neu_ngoai_kenh(",
                                       "chan_neu_khong_duoc_tra_loi(",
                                       "ConversationRoutingService(")):
            thieu.append(m.group(1))
    # Không xét route nào là xanh giả — đã xảy ra khi routes.py được tách (23.10.2026).
    assert da_xet >= 6, f"chỉ xét được {da_xet} route — bộ đọc nguồn hỏng?"
    assert not thieu, f"route chưa chốt phạm vi kênh: {thieu}"
