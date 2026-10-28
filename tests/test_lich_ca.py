"""
Lịch ca trực — Postgres thật.

Ràng buộc then chốt: bộ định tuyến KHÔNG giao hội thoại cho người đã hết ca
hoặc đang nghỉ. Trước đây chỉ có công tắc `is_available` bật tay — quên tắt
lúc về là khách được giao cho người đã ở nhà, nằm chờ tới sáng.

Và một ràng buộc ngược: người CHƯA xếp ca nào vẫn được giao như cũ. Nâng
cấp không được làm cửa hàng chưa dùng lịch ca mất việc được chia.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from conftest import nguoi_thu

ROOT = Path(__file__).resolve().parent.parent
UID = UUID("00000000-0000-0000-0000-000000000001")
VN = timezone(timedelta(hours=7))
_THU_HAI = date(2026, 10, 26) - timedelta(days=date(2026, 10, 26).weekday())


def luc(thu: int, hh: int, mm: int = 0, tuan: int = 0) -> datetime:
    """Thời điểm giờ Việt Nam: thứ `thu` (1 = thứ Hai) lúc hh:mm."""
    d = _THU_HAI + timedelta(days=thu - 1 + 7 * tuan)
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=VN)


async def _mo(url: str) -> asyncpg.Connection:
    from agent.migrations.runner import apply_all

    conn = await asyncpg.connect(url)
    # Cùng codec với app (agent/db.py): câu chọn ứng viên truyền list vào $3::jsonb.
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.execute((ROOT / "agent" / "schema.sql").read_text(encoding="utf-8"))
    await apply_all(conn)
    return conn


async def _nguoi(conn, ten: str) -> UUID:
    return await conn.fetchval(
        "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten) VALUES ($1,'x',$1) RETURNING id", ten)


async def _ca(conn, uid, thu, a, b):
    await conn.execute("INSERT INTO ca_truc (nguoi_dung_id, thu, bat_dau, ket_thuc) VALUES ($1,$2,$3,$4)",
                       uid, thu, a, b)


# ------------------------------------------------------------------ hàm SQL

def test_dang_trong_ca_cac_bien(csdl_kiem_thu):
    async def chay():
        conn = await _mo(csdl_kiem_thu)
        try:
            ngay = await _nguoi(conn, "ca_ngay")          # thứ Hai 08:00–14:00
            await _ca(conn, ngay, 1, 8 * 60, 14 * 60)
            dem = await _nguoi(conn, "ca_dem")            # Chủ nhật 22:00 → 06:00 thứ Hai
            await _ca(conn, dem, 7, 22 * 60, 6 * 60)
            het_ngay = await _nguoi(conn, "het_ngay")     # thứ Ba 14:00–24:00
            await _ca(conn, het_ngay, 2, 14 * 60, 1440)
            chua_xep = await _nguoi(conn, "chua_xep")

            async def hoi(uid, t):
                return await conn.fetchval("SELECT dang_trong_ca($1, $2)", uid, t)

            return {
                "ngay_8h": await hoi(ngay, luc(1, 8)),
                "ngay_13h59": await hoi(ngay, luc(1, 13, 59)),
                "ngay_14h": await hoi(ngay, luc(1, 14)),           # [bắt đầu, kết thúc)
                "ngay_7h59": await hoi(ngay, luc(1, 7, 59)),
                "ngay_thu_ba": await hoi(ngay, luc(2, 9)),
                "dem_cn_23h": await hoi(dem, luc(7, 23)),
                "dem_t2_5h": await hoi(dem, luc(1, 5, tuan=1)),    # sáng thứ Hai TUẦN SAU
                "dem_t2_6h": await hoi(dem, luc(1, 6, tuan=1)),
                "dem_cn_21h": await hoi(dem, luc(7, 21)),
                "dem_t7_23h": await hoi(dem, luc(6, 23)),
                "het_ngay_23h59": await hoi(het_ngay, luc(2, 23, 59)),
                "het_ngay_t4_0h": await hoi(het_ngay, luc(3, 0)),
                "chua_xep": await hoi(chua_xep, luc(3, 3)),
            }
        finally:
            await conn.close()

    r = asyncio.run(chay())
    assert r == {
        "ngay_8h": True, "ngay_13h59": True, "ngay_14h": False, "ngay_7h59": False,
        "ngay_thu_ba": False,
        "dem_cn_23h": True, "dem_t2_5h": True, "dem_t2_6h": False, "dem_cn_21h": False,
        "dem_t7_23h": False,
        "het_ngay_23h59": True, "het_ngay_t4_0h": False,
        "chua_xep": True,
    }


def test_lich_nghi_thang_ca_truc(csdl_kiem_thu):
    async def chay():
        conn = await _mo(csdl_kiem_thu)
        try:
            a = await _nguoi(conn, "nghi_phep")
            await _ca(conn, a, 1, 8 * 60, 14 * 60)
            b = await _nguoi(conn, "nghi_chua_xep")      # chưa xếp ca nhưng xin nghỉ
            for u in (a, b):
                await conn.execute("INSERT INTO ca_nghi (nguoi_dung_id, tu_luc, den_luc) VALUES ($1,$2,$3)",
                                   u, luc(1, 0), luc(2, 0))
            return [await conn.fetchval("SELECT dang_trong_ca($1, $2)", u, t)
                    for u, t in ((a, luc(1, 9)), (b, luc(1, 9)), (b, luc(2, 0)))]
        finally:
            await conn.close()

    assert asyncio.run(chay()) == [False, False, True]   # den_luc là mốc mở


def test_bo_dinh_tuyen_bo_qua_nguoi_het_ca(csdl_kiem_thu):
    """Trọn câu chọn ứng viên thật của AutoRoutingWorker."""
    from agent.omnichannel.auto_routing import PostgresAutoRoutingTransaction

    async def chay():
        conn = await _mo(csdl_kiem_thu)
        try:
            tk = await conn.fetchval(
                "INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
                "VALUES ('webchat','web','active','web-1') RETURNING id")
            doi = await conn.fetchval("INSERT INTO teams (name) VALUES ('Ca') RETURNING id")
            ra = {}
            for ten in ("dang_ca", "het_ca", "chua_xep"):
                u = await _nguoi(conn, ten)
                ra[u] = ten
                await conn.execute("INSERT INTO team_members (team_id, user_id) VALUES ($1,$2)", doi, u)
                await conn.execute("INSERT INTO account_memberships (account_id, user_id) VALUES ($1,$2)", tk, u)
            ten_ra = {v: k for k, v in ra.items()}
            bay_gio = await conn.fetchval("SELECT now()")
            vn = bay_gio.astimezone(VN)
            phut = vn.hour * 60 + vn.minute
            thu = vn.isoweekday()
            # Ca phủ "bây giờ" ±1 giờ, và một ca của ngày hôm kia (chắc chắn ngoài giờ hiện tại).
            await _ca(conn, ten_ra["dang_ca"], thu, max(0, phut - 60), min(1440, phut + 60))
            await _ca(conn, ten_ra["het_ca"], (thu + 4) % 7 + 1, 8 * 60, 9 * 60)
            rows = await PostgresAutoRoutingTransaction(conn).candidates(
                account_id=tk, team_id=doi, required_skills=[])
            return sorted(ra[r["user_id"]] for r in rows)
        finally:
            await conn.close()

    assert asyncio.run(chay()) == ["chua_xep", "dang_ca"]


# ------------------------------------------------------------------ kiểm lịch (thuần)

def _c(thu, a, b):
    from agent.api.lich_ca import CaIn
    return CaIn(thu=thu, bat_dau=a, ket_thuc=b)


def test_kiem_lich_doi_sang_phut():
    from agent.api.lich_ca import kiem_lich

    assert kiem_lich([_c(1, "08:00", "14:00"), _c(1, "14:00", "21:00"), _c(7, "22:00", "06:00"),
                      _c(2, "18:00", "00:00")]) == [
        (1, 480, 840), (1, 840, 1260), (7, 1320, 360), (2, 1080, 1440)]


@pytest.mark.parametrize("ca", [
    [("1", "08:00", "14:00"), ("1", "13:00", "20:00")],    # gõ nhầm 13 thay 14
    [("7", "22:00", "06:00"), ("1", "05:00", "09:00")],    # ca đêm CN vắt sang sáng thứ Hai
    [("1", "08:00", "08:00")],
    [("1", "8h", "14:00")],
    [("1", "24:00", "02:00")],
    [("1", "25:00", "26:00")],
])
def test_kiem_lich_chan(ca):
    from agent.api.lich_ca import kiem_lich

    with pytest.raises(HTTPException) as e:
        kiem_lich([_c(int(t), a, b) for t, a, b in ca])
    assert e.value.status_code == 422


# ------------------------------------------------------------------ API

def _app(url: str, nguoi: dict) -> FastAPI:
    from agent import db
    from agent.api.lich_ca import router
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.migrations.runner import apply_all

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[nguoi_da_dang_nhap] = lambda: nguoi

    async def _codec(conn):
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

    @app.on_event("startup")
    async def _mo_app():
        db._pool = await asyncpg.create_pool(url, min_size=1, max_size=3, init=_codec)
        async with db._pool.acquire() as conn:
            await conn.execute((ROOT / "agent" / "schema.sql").read_text(encoding="utf-8"))
            await apply_all(conn)
            await conn.execute("INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, ho_ten) "
                               "VALUES ($1,'kt','x','Kiểm Thử') ON CONFLICT DO NOTHING", UID)

    @app.on_event("shutdown")
    async def _dong():
        if db._pool is not None:
            await db._pool.close()
            db._pool = None

    return app


QL = ("dinh_tuyen.doc", "dinh_tuyen.sua")


def test_api_dat_lich_xem_nghi(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL, "hoi_thoai.doc"))) as k:
        r = k.put(f"/api/lich-ca/{UID}", json={"ca": [
            {"thu": 1, "bat_dau": "08:00", "ket_thuc": "14:00"},
            {"thu": 7, "bat_dau": "22:00", "ket_thuc": "06:00"}]})
        assert r.status_code == 200, r.text and r.json()["so_ca"] == 2
        ds = k.get("/api/lich-ca").json()
        toi = next(n for n in ds["nguoi"] if n["id"] == str(UID))
        assert [c["ten_thu"] for c in toi["ca"]] == ["Thứ 2", "Chủ nhật"]
        assert toi["ca"][1]["qua_dem"] is True

        # Đặt lại thay CẢ tuần, không cộng dồn.
        k.put(f"/api/lich-ca/{UID}", json={"ca": [{"thu": 3, "bat_dau": "09:00", "ket_thuc": "17:00"}]})
        assert len(k.get("/api/lich-ca/cua-toi").json()["ca"]) == 1

        bay_gio = datetime.now(VN)
        r = k.post("/api/lich-ca/nghi", json={
            "nguoi_dung_id": str(UID), "tu_luc": (bay_gio - timedelta(hours=1)).isoformat(),
            "den_luc": (bay_gio + timedelta(days=2)).isoformat(), "ly_do": "ốm"})
        assert r.status_code == 201, r.text
        toi = k.get("/api/lich-ca/cua-toi").json()
        assert toi["trong_ca"] is False and len(toi["nghi"]) == 1
        assert k.delete(f"/api/lich-ca/nghi/{r.json()['id']}").status_code == 204
        assert k.delete(f"/api/lich-ca/nghi/{r.json()['id']}").status_code == 404

        # Xoá hết ca = về "chưa xếp ca" = luôn trực.
        assert k.put(f"/api/lich-ca/{UID}", json={"ca": []}).json()["trong_ca"] is True


def test_api_tu_choi_sai(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        assert k.put(f"/api/lich-ca/{uuid4()}", json={"ca": []}).status_code == 404
        assert k.put(f"/api/lich-ca/{UID}", json={"ca": [
            {"thu": 1, "bat_dau": "08:00", "ket_thuc": "14:00"},
            {"thu": 1, "bat_dau": "13:00", "ket_thuc": "20:00"}]}).status_code == 422
        # Không múi giờ thì không đoán: lệch bảy tiếng trên máy chủ UTC.
        assert k.post("/api/lich-ca/nghi", json={"nguoi_dung_id": str(UID), "tu_luc": "2026-11-01T08:00:00",
                                                 "den_luc": "2026-11-02T08:00:00"}).status_code == 422
        assert k.post("/api/lich-ca/nghi", json={"nguoi_dung_id": str(UID),
                                                 "tu_luc": "2026-11-02T08:00:00+07:00",
                                                 "den_luc": "2026-11-01T08:00:00+07:00"}).status_code == 422
        assert k.post("/api/lich-ca/nghi", json={"nguoi_dung_id": str(uuid4()),
                                                 "tu_luc": "2026-11-01T08:00:00+07:00",
                                                 "den_luc": "2026-11-02T08:00:00+07:00"}).status_code == 404


def test_api_quyen(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("hoi_thoai.doc"))) as nv:
        assert nv.get("/api/lich-ca/cua-toi").status_code == 200
        assert nv.get("/api/lich-ca").status_code == 403
        assert nv.put(f"/api/lich-ca/{UID}", json={"ca": []}).status_code == 403
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("dinh_tuyen.doc"))) as doc:
        assert doc.get("/api/lich-ca").status_code == 200
        assert doc.post("/api/lich-ca/nghi", json={}).status_code in (403, 422)


def test_canh_bao_doi_khong_ai_trong_ca(csdl_kiem_thu):
    """Đội có luật định tuyến mà lúc này không ai trong ca → nói ra."""
    async def dung(url):
        conn = await asyncpg.connect(url)
        try:
            doi = await conn.fetchval("INSERT INTO teams (name) VALUES ('Ca đêm') RETURNING id")
            await conn.execute("INSERT INTO routing_rules (team_id) VALUES ($1)", doi)
            u = await _nguoi(conn, "chi_ca_xa")
            await conn.execute("INSERT INTO team_members (team_id, user_id) VALUES ($1,$2)", doi, u)
            vn = datetime.now(VN)
            await _ca(conn, u, (vn.isoweekday() + 2) % 7 + 1, 8 * 60, 9 * 60)   # ca hai ngày sau
        finally:
            await conn.close()

    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        asyncio.run(dung(csdl_kiem_thu))
        cb = k.get("/api/lich-ca").json()["canh_bao"]
    assert [c["doi"] for c in cb] == ["Ca đêm"]
