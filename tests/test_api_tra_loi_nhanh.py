"""
Mẫu trả lời nhanh — chạy trên Postgres thật.

Ràng buộc then chốt: mẫu dính cụm cấm quảng cáo mỹ phẩm KHÔNG lưu được.
Một mẫu sai là vi phạm nhân lên theo số lần cả cửa hàng bấm dùng nó.
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
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.api.tra_loi_nhanh import router
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

    @app.on_event("shutdown")
    async def _dong():
        if db._pool is not None:
            await db._pool.close()
            db._pool = None

    return app


QL = ("hoi_thoai.tra_loi", "tra_loi_nhanh.sua")


def test_tao_tim_sua_xoa(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        r = k.post("/api/tra-loi-nhanh", json={
            "ma_tat": "ship", "noi_dung": "Dạ shop giao toàn quốc, phí ship 30.000đ ạ."})
        assert r.status_code == 201, r.text
        mid = r.json()["id"]
        k.post("/api/tra-loi-nhanh", json={"ma_tat": "doitra",
                                           "noi_dung": "Dạ đổi trả trong 7 ngày ạ."})

        assert [m["ma_tat"] for m in k.get("/api/tra-loi-nhanh?q=sh").json()["mau"]] == ["ship"]
        # Tìm theo nội dung, không dấu vẫn ra.
        assert [m["ma_tat"] for m in k.get("/api/tra-loi-nhanh?q=doi tra").json()["mau"]] == ["doitra"]
        # "%" không được thành ký tự đại diện.
        assert k.get("/api/tra-loi-nhanh?q=%25").json()["mau"] == []

        r = k.put(f"/api/tra-loi-nhanh/{mid}", json={
            "ma_tat": "ship", "noi_dung": "Dạ phí ship 25.000đ ạ."})
        assert r.status_code == 200 and "25.000" in r.json()["noi_dung"]
        assert k.delete(f"/api/tra-loi-nhanh/{mid}").status_code == 204
        assert len(k.get("/api/tra-loi-nhanh").json()["mau"]) == 1


def test_ma_trung_la_409(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        assert k.post("/api/tra-loi-nhanh", json={"ma_tat": "ship", "noi_dung": "a"}).status_code == 201
        assert k.post("/api/tra-loi-nhanh", json={"ma_tat": "SHIP", "noi_dung": "b"}).status_code == 409


def test_ma_tat_sai_dang_la_422(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        for ma in ("phí ship", "a b", "x" * 33):
            r = k.post("/api/tra-loi-nhanh", json={"ma_tat": ma, "noi_dung": "a"})
            assert r.status_code == 422, ma


def test_cum_cam_quang_cao_khong_luu_duoc(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        for cau in ("Serum này đặc trị mụn ạ",
                    "Dùng 2 tuần là khỏi hẳn ạ",
                    "Sản phẩm chữa\nkhỏi nám"):          # bị xuống dòng cắt đôi
            r = k.post("/api/tra-loi-nhanh", json={"ma_tat": "x", "noi_dung": cau})
            assert r.status_code == 422, cau
            assert r.json()["detail"]["cum"], cau
        assert k.get("/api/tra-loi-nhanh").json()["mau"] == []


def test_nhan_vien_dung_duoc_khong_sua_duoc(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as ql:
        ql.post("/api/tra-loi-nhanh", json={"ma_tat": "ship", "noi_dung": "a"})
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("hoi_thoai.tra_loi"))) as nv:
        assert nv.get("/api/tra-loi-nhanh").status_code == 200
        assert nv.post("/api/tra-loi-nhanh",
                       json={"ma_tat": "x", "noi_dung": "a"}).status_code == 403
    with TestClient(_app(csdl_kiem_thu, nguoi_thu())) as la:
        assert la.get("/api/tra-loi-nhanh").status_code == 403


def test_ghi_nhat_ky_kiem_toan(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        k.post("/api/tra-loi-nhanh", json={"ma_tat": "ship", "noi_dung": "a"})

    async def dem():
        conn = await asyncpg.connect(csdl_kiem_thu)
        try:
            return await conn.fetchval(
                "SELECT count(*) FROM events WHERE kind = 'tra_loi_nhanh.tao'")
        finally:
            await conn.close()
    assert asyncio.run(dem()) == 1
