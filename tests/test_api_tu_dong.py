"""
API quy tắc tự động hoá — Postgres thật.

Ràng buộc then chốt: lỗi lộ ra lúc BẤM LƯU, không phải lúc khách nhắn vào.
Quy tắc gửi một mẫu không tồn tại, hay một mẫu dính cụm cấm quảng cáo, thì
không lưu được.
"""
from __future__ import annotations

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
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.api.tu_dong_api import router
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
            await conn.execute(
                "INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, ho_ten) "
                "VALUES ($1,'kt','x','kt') ON CONFLICT DO NOTHING", UUID(UID))
            await conn.execute(
                "INSERT INTO tra_loi_nhanh (ma_tat, noi_dung) VALUES "
                "('chao','Dạ shop chào chị ạ.'), ('xau','Serum này đặc trị mụn ạ') "
                "ON CONFLICT DO NOTHING")

    @app.on_event("shutdown")
    async def _dong():
        if db._pool is not None:
            await db._pool.close()
            db._pool = None

    return app


QL = ("dinh_tuyen.doc", "dinh_tuyen.sua")
MAU = {"ten": "Chào ngoài giờ", "dieu_kien": {"ngoai_gio": True},
       "hanh_dong": [{"loai": "gan_nhan", "nhan": "ngoài giờ"},
                     {"loai": "gui_mau", "ma_tat": "chao"}]}


def test_tao_liet_ke_sua_xoa(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        r = k.post("/api/tu-dong", json=MAU)
        assert r.status_code == 201, r.text
        qid = r.json()["id"]
        ds = k.get("/api/tu-dong").json()
        assert [q["ten"] for q in ds["quy_tac"]] == ["Chào ngoài giờ"]
        assert ds["quy_tac"][0]["bay_ngay"] == {"da_lam": 0, "hong": 0, "lan_cuoi": None}
        assert "gui_mau" in ds["hanh_dong"] and "facebook" in ds["kenh"]

        r = k.put(f"/api/tu-dong/{qid}", json={**MAU, "bat": False, "thu_tu": 5})
        assert r.status_code == 200 and r.json()["bat"] is False and r.json()["thu_tu"] == 5
        assert k.delete(f"/api/tu-dong/{qid}").status_code == 204
        assert k.delete(f"/api/tu-dong/{qid}").status_code == 404
        assert k.get("/api/tu-dong").json()["quy_tac"] == []
        assert k.get("/api/tu-dong/lan-chay").json() == {"lan_chay": []}


def test_mau_khong_ton_tai_hoac_dinh_cum_cam_la_422(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        r = k.post("/api/tu-dong", json={**MAU, "hanh_dong": [{"loai": "gui_mau", "ma_tat": "khongco"}]})
        assert r.status_code == 422 and "khongco" in r.text
        r = k.post("/api/tu-dong", json={**MAU, "hanh_dong": [{"loai": "gui_mau", "ma_tat": "xau"}]})
        assert r.status_code == 422 and "cấm" in r.json()["detail"]
        assert k.get("/api/tu-dong").json()["quy_tac"] == []


def test_danh_sach_dong_la_422(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        for body in ({**MAU, "dieu_kien": {"url": "http://x"}},
                     {**MAU, "hanh_dong": [{"loai": "goi_webhook"}]},
                     {**MAU, "hanh_dong": []},
                     {**MAU, "su_kien": "don_moi"}):
            assert k.post("/api/tu-dong", json=body).status_code == 422, body


def test_quyen(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("dinh_tuyen.doc"))) as doc:
        assert doc.get("/api/tu-dong").status_code == 200
        assert doc.get("/api/tu-dong/lan-chay").status_code == 200
        assert doc.post("/api/tu-dong", json=MAU).status_code == 403
    with TestClient(_app(csdl_kiem_thu, nguoi_thu())) as la:
        assert la.get("/api/tu-dong").status_code == 403


def test_ghi_nhat_ky_kiem_toan(csdl_kiem_thu):
    import asyncio

    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        k.post("/api/tu-dong", json=MAU)

    async def dem():
        conn = await asyncpg.connect(csdl_kiem_thu)
        try:
            return await conn.fetchval("SELECT count(*) FROM events WHERE kind = 'tu_dong.tao'")
        finally:
            await conn.close()
    assert asyncio.run(dem()) == 1
