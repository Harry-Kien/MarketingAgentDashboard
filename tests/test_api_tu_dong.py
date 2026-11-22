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
            # MAU dùng khoá chữ cũ `gan_nhan` — API đổi sang id nếu tên có
            # trong danh mục (0056), không thì 422.
            await conn.execute(
                "INSERT INTO nhan (loai, ten) VALUES ('hoi_thoai','ngoài giờ') "
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
        assert ds["quy_tac"][0]["bay_ngay"] == {"da_lam": 0, "hong": 0, "bo_qua": 0,
                                                "lan_cuoi": None}
        assert ds["quy_tac"][0]["lan_chay_cuoi"] is None and ds["quy_tac"][0]["loi_cuoi"] is None
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



def test_tat_duoc_quy_tac_da_hong(csdl_kiem_thu):
    """Mẫu của quy tắc bị xoá: nút Tắt vẫn phải chạy — bản cũ trả 422."""
    import asyncio

    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        qid = k.post("/api/tu-dong", json=MAU).json()["id"]

        async def xoa_mau():
            conn = await asyncpg.connect(csdl_kiem_thu)
            try:
                await conn.execute("DELETE FROM tra_loi_nhanh WHERE ma_tat = 'chao'")
            finally:
                await conn.close()
        asyncio.run(xoa_mau())
        assert k.put(f"/api/tu-dong/{qid}", json={**MAU, "bat": True}).status_code == 422
        r = k.put(f"/api/tu-dong/{qid}", json={**MAU, "bat": False})
        assert r.status_code == 200 and r.json()["bat"] is False


# ------------------------------------------------------------------ thứ tự & xung đột (0060)

def test_co_uu_tien_luu_va_giu_khi_bat_tat(csdl_kiem_thu):
    """
    Hai cờ 0060 lưu được, và nút Bật/Tắt gửi lại quy tắc KHÔNG kèm hai cờ
    thì cờ GIỮ NGUYÊN — thiếu khoá mà hiểu là false thì mỗi lần bấm Tắt là
    cờ lặng lẽ mất.
    """
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        r = k.post("/api/tu-dong", json={**MAU, "dung_xet_sau": True, "cho_ai_tra_loi": True})
        assert r.status_code == 201, r.text
        qid = r.json()["id"]
        assert (r.json()["dung_xet_sau"], r.json()["cho_ai_tra_loi"]) == (True, True)
        r = k.put(f"/api/tu-dong/{qid}", json={**MAU, "bat": False})
        assert (r.json()["bat"], r.json()["dung_xet_sau"], r.json()["cho_ai_tra_loi"]) == (
            False, True, True)
        r = k.put(f"/api/tu-dong/{qid}", json={**MAU, "dung_xet_sau": False})
        assert (r.json()["dung_xet_sau"], r.json()["cho_ai_tra_loi"]) == (False, True)
        # Tạo không gửi cờ -> mặc định an toàn: AI nhường, không dừng xét.
        r = k.post("/api/tu-dong", json={**MAU, "ten": "Khác"})
        assert (r.json()["dung_xet_sau"], r.json()["cho_ai_tra_loi"]) == (False, False)


def test_danh_sach_theo_thu_tu_chay(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        for ten, tt in (("C", 30), ("A", 10), ("B", 10)):
            assert k.post("/api/tu-dong", json={**MAU, "ten": ten, "thu_tu": tt}).status_code == 201
        # A và B cùng 10: tạo trước (A) đứng trước — đúng thứ tự lúc chạy.
        assert [q["ten"] for q in k.get("/api/tu-dong").json()["quy_tac"]] == ["A", "B", "C"]


def test_dieu_kien_va_hanh_dong_mau_thuan_la_422(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        nid = k.post("/api/tu-dong", json=MAU).json()["hanh_dong"][0]["nhan_id"]
        r = k.post("/api/tu-dong", json={**MAU, "dieu_kien": {
            "nhan_hoi_thoai_co": [nid], "nhan_hoi_thoai_khong": [nid]}})
        assert r.status_code == 422 and "mâu thuẫn" in r.text
        r = k.post("/api/tu-dong", json={**MAU, "hanh_dong": [
            {"loai": "gui_mau", "ma_tat": "chao"}, {"loai": "gui_mau", "ma_tat": "chao"}]})
        assert r.status_code == 422


def test_dau_vet_lan_chay_hien_tren_dong_quy_tac(csdl_kiem_thu):
    """
    Mỗi dòng quy tắc mang lần chạy cuối và LỖI cuối; nhật ký lọc được theo
    từng quy tắc. Không có thì "quy tắc của tôi có chạy không, hỏng vì sao"
    chỉ trả lời được bằng cách lục nhật ký chung.
    """
    import asyncio

    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        a = k.post("/api/tu-dong", json={**MAU, "ten": "A"}).json()["id"]
        b = k.post("/api/tu-dong", json={**MAU, "ten": "B"}).json()["id"]

        async def ghi():
            conn = await asyncpg.connect(csdl_kiem_thu)
            try:
                await conn.execute(
                    "INSERT INTO quy_tac_lan_chay (quy_tac_id, ket_qua, chi_tiet, luc) VALUES "
                    "($1,'hong','{\"loi\": \"gui_mau: mẫu bị xoá\"}'::jsonb, now() - interval '1 hour'),"
                    "($1,'da_lam','{\"lam\": [\"gửi mẫu /chao\"], \"ai_nhuong\": true}'::jsonb, now()),"
                    "($2,'bo_qua','{\"bo_qua\": [\"không gửi mẫu: nhân viên đang tiếp hội thoại\"]}'::jsonb, now())",
                    UUID(a), UUID(b))
            finally:
                await conn.close()
        asyncio.run(ghi())
        ds = {q["ten"]: q for q in k.get("/api/tu-dong").json()["quy_tac"]}
        assert ds["A"]["lan_chay_cuoi"]["ket_qua"] == "da_lam"
        assert ds["A"]["lan_chay_cuoi"]["tom_tat"] == "gửi mẫu /chao"
        assert ds["A"]["loi_cuoi"]["loi"] == "gui_mau: mẫu bị xoá"
        assert ds["A"]["bay_ngay"]["hong"] == 1 and ds["A"]["bay_ngay"]["da_lam"] == 1
        assert ds["B"]["lan_chay_cuoi"]["tom_tat"] == "không gửi mẫu: nhân viên đang tiếp hội thoại"
        assert ds["B"]["loi_cuoi"] is None
        loc = k.get(f"/api/tu-dong/lan-chay?quy_tac_id={b}").json()["lan_chay"]
        assert [x["quy_tac"] for x in loc] == ["B"] and loc[0]["quy_tac_id"] == b
        assert len(k.get("/api/tu-dong/lan-chay").json()["lan_chay"]) == 3
