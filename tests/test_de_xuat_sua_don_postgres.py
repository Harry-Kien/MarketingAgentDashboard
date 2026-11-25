"""Real PostgreSQL locks/API/audit, strictly kiemthu and an isolated schema.

Does not run app lifespan, workers, models or ERP writes. Existing migration
0065 is exercised on minimal dependency tables, not production schemas.
"""
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import urlparse
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from agent import db
from agent.api import phu_thuoc, uy_quyen_ai as api
from agent.core import thao_tac_don, thong_bao_noi_bo, uy_quyen
from agent.erp import nha_may


def test_kiemthu_api_race_reject_audit(monkeypatch):
    url = os.getenv("KIEMTHU_URL", "postgresql://agent:agent@127.0.0.1:5433/kiemthu")
    assert urlparse(url).path == "/kiemthu", "Only kiemthu is allowed"

    async def run():
        try:
            admin = await asyncpg.connect(url, timeout=3)
        except (OSError, asyncpg.PostgresError):
            pytest.skip("CSDL kiemthu chưa khả dụng; không thử CSDL khác")
        assert await admin.fetchval("SELECT current_database()") == "kiemthu"
        schema = "test_gap17_" + uuid4().hex
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool = None
        try:
            async def setup(conn):
                await conn.set_type_codec("jsonb", schema="pg_catalog",
                                          encoder=json.dumps, decoder=json.loads)
            pool = await asyncpg.create_pool(url, min_size=1, max_size=5,
                server_settings={"search_path": schema}, init=setup)
            monkeypatch.setattr(db, "_pool", pool)
            await db.execute("""
                CREATE TABLE conversations(id uuid PRIMARY KEY);
                CREATE TABLE messages(id uuid PRIMARY KEY);
                CREATE TABLE nguoi_dung(id uuid PRIMARY KEY, ho_ten text);
                CREATE TABLE orders(id uuid PRIMARY KEY, conversation_id uuid,
                    ma_don text, trang_thai text, items jsonb, updated_at timestamptz DEFAULT now(),
                    erp_ma_don text, ma_van_don text, trang_thai_giao_hang text, yeu_cau_huy_luc timestamptz);
                CREATE TABLE events(id bigserial, kind text, actor text, ref_id uuid, detail jsonb);
            """)
            migration = Path(__file__).parents[1] / "agent/migrations/versions/0065_uy_quyen_ai.sql"
            await db.execute(migration.read_text())
            migration_5b = migration.with_name("0066_de_xuat_sua_don_thu_cong.sql")
            cid, oid, uid = uuid4(), uuid4(), uuid4()
            await db.execute("INSERT INTO conversations VALUES($1)", cid)
            await db.execute("INSERT INTO nguoi_dung VALUES($1,'Tester')", uid)
            await db.execute("INSERT INTO orders(id,conversation_id,ma_don,trang_thai,items,erp_ma_don) "
                             "VALUES($1,$2,'TEST-17','da_chot',$3,'SO-TEST')", oid, cid,
                             [{"ma": "SP1", "ten": "Test", "so_luong": 1}])
            legacy_id = uuid4()
            await db.execute("INSERT INTO ai_de_xuat(id,conversation_id,hanh_dong,che_do_ai," 
                "muc_uy_quyen,ly_do_can_duyet,trang_thai,khoa_trung,het_han_luc,ket_qua) "
                "VALUES($1,$2,'sua_don','goi_y','co_phe_duyet','legacy','loi','legacy',now(),$3)",
                legacy_id, cid, {"can_xu_ly_thu_cong": True, "da_sua": False})
            before = await db.fetchrow("SELECT * FROM ai_de_xuat WHERE id=$1", legacy_id)
            await db.execute(migration_5b.read_text())
            assert before == await db.fetchrow("SELECT * FROM ai_de_xuat WHERE id=$1", legacy_id)
            monkeypatch.setattr(uy_quyen, "han_gio", AsyncMock(return_value=24))
            monkeypatch.setattr(thong_bao_noi_bo, "bao_can_duyet_de_xuat", AsyncMock())
            erp = AsyncMock(return_value=dict(name="SO-TEST", docstatus=1,
                status="To Deliver and Bill", modified="v1"))
            monkeypatch.setattr(nha_may, "cong", lambda: type("ERP", (), {"doc_don": erp})())
            args = dict(ma_don="TEST-17", ma_san_pham="SP1", so_luong=2, ly_do="Thêm hàng")
            proposals = await asyncio.gather(*[
                thao_tac_don.de_xuat_sua_don(args, cid) for _ in range(2)])
            did = proposals[0]["de_xuat_id"]
            assert proposals[1]["de_xuat_id"] == did
            app = FastAPI()
            app.include_router(api.router)
            user = dict(id=uid, ten_dang_nhap="tester", quyen=["ai.duyet", "don.sua"])
            app.dependency_overrides[phu_thuoc.nguoi_da_dang_nhap] = lambda: user
            monkeypatch.setattr(api, "chan_neu_ngoai_kenh", AsyncMock())
            execute = api._thi_hanh

            async def observe_claim(dx, actor):
                assert dx["trang_thai"] == "dang_thuc_thi"
                return await execute(dx, actor)
            monkeypatch.setattr(api, "_thi_hanh", observe_claim)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                path = f"/api/ai-de-xuat/{did}"
                for permission in ("ai.duyet", "don.sua"):
                    user["quyen"].remove(permission)
                    assert (await client.post(path + "/duyet")).status_code == 403
                    user["quyen"].append(permission)
                responses = await asyncio.gather(client.post(path + "/duyet"), client.post(path + "/duyet"))
                assert sorted(r.status_code for r in responses) == [200, 409]
                result = next(r.json() for r in responses if r.status_code == 200)
                assert result["trang_thai"] == "cho_xu_ly_thu_cong" and not result["ok"]
                assert result["ket_qua"]["can_xu_ly_thu_cong"]
                assert (await client.post(path + "/duyet")).status_code == 409
                repeated = await thao_tac_don.de_xuat_sua_don(args, cid)
                assert repeated["de_xuat_id"] == did
                args["so_luong"] = 3
                rejected = await thao_tac_don.de_xuat_sua_don(args, cid)
                reject_path = f'/api/ai-de-xuat/{rejected["de_xuat_id"]}/tu-choi'
                assert (await client.post(reject_path, json={"ly_do": " "})).status_code == 422
                assert (await client.post(reject_path, json={"ly_do": "Khách đổi ý"})).status_code == 200
                assert (await client.post(reject_path, json={"ly_do": "Lặp"})).status_code == 409
            order = await db.fetchrow("SELECT * FROM orders WHERE id=$1", oid)
            assert order["items"][0]["so_luong"] == 1 and order["trang_thai"] == "da_chot"
            audits = await db.fetch("SELECT kind,actor,detail FROM events")
            assert sum(e["kind"] == "ai.de_xuat.duyet" for e in audits) == 1
            for kind, actor in [("tao", "agent"), ("duyet", "tester"),
                                ("cho_xu_ly_thu_cong", "tester"), ("tu_choi", "tester")]:
                assert any(e["kind"] == "ai.de_xuat." + kind and e["actor"] == actor for e in audits)
            saved = await db.fetchrow("SELECT * FROM ai_de_xuat WHERE id=$1", UUID(did))
            assert saved["duyet_boi"] == uid and saved["ket_qua"]["da_sua"] is False
            assert saved["thuc_hien_luc"] is None
        finally:
            if pool:
                await pool.close()
            # Only the randomly named schema created by THIS test is removed.
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()
    asyncio.run(run())
