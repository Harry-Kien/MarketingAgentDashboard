"""
Nhóm Zalo KHÔNG phải một khách hàng (mục 9.7) — Postgres thật.

Hội thoại nhóm vẫn gắn một contact (khoá `group:<id>`, xem
`agent/core/lien_he_nhom.py`). Contact ấy lọt vào Customer 360 thì không
có gì nổ: danh sách khách chỉ có thêm "Nhóm Sỉ Hà Nội", số "khách mới" tăng
một, hàng "khách chưa có chủ" dài thêm, và một lần gộp nhầm trộn lịch sử
cả nhóm vào hồ sơ riêng của một người. Mỗi chỗ một test, chạy trên dữ liệu
thật — không soi chuỗi SQL.

Thành viên nhóm vẫn là khách riêng theo danh tính CỦA HỌ: "Lan" ở đây là
khách thường, và phải còn nguyên ở mọi chỗ.
"""
from __future__ import annotations

import ast
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

QUYEN = ("khach.doc", "khach.xem_tat_ca", "khach.gop", "bao_cao.doc",
         "hoi_thoai.doc", "hoi_thoai.xem_tat_ca", "hoi_thoai.nhan")


async def _codec(conn):
    await conn.set_type_codec("jsonb", encoder=json.dumps,
                              decoder=json.loads, schema="pg_catalog")


def _app(url: str, nguoi: dict) -> FastAPI:
    from agent import db
    from agent.api.contacts import router as r_kh
    from agent.api.contacts import router_vo_chu as r_vc
    from agent.api.hoi_thoai_nhan import router as r_nhan
    from agent.api.phan_tich import router as r_pt
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.api.tong_quan import router as r_tq
    from agent.migrations.runner import apply_all

    app = FastAPI()
    for r in (r_kh, r_vc, r_pt, r_tq, r_nhan):
        app.include_router(r)
    app.dependency_overrides[nguoi_da_dang_nhap] = lambda: nguoi

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


async def _khach(conn, tk: UUID, ten: str, ext: str, metadata: dict, thread_type: int | None):
    kh = await conn.fetchval("INSERT INTO contacts (display_name) VALUES ($1) RETURNING id", ten)
    dm = await conn.fetchval(
        "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id, metadata) "
        "VALUES ($1,$2,$3,$4) RETURNING id", kh, tk, ext, metadata)
    cid = await conn.fetchval(
        "INSERT INTO conversations (account_id, channel, external_id, customer_ref, customer_name, "
        "contact_id, contact_point_id, thread_type) VALUES ($1,'zalo_personal',$2,$2,$3,$4,$5,$6) "
        "RETURNING id", tk, ext, ten, kh, dm, thread_type)
    await conn.execute(
        "INSERT INTO messages (conversation_id, role, content, direction, delivery_status, "
        "sender_name) VALUES ($1,'customer','còn size M không','inbound','received',$2)",
        cid, "Lan" if thread_type == 1 else None)
    return kh, cid


def _dung(url: str) -> dict:
    async def chay():
        conn = await asyncpg.connect(url)
        await _codec(conn)
        try:
            await conn.execute(
                "INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, ho_ten) "
                "VALUES ('00000000-0000-0000-0000-000000000001','kt','x','Kiểm Thử') "
                "ON CONFLICT DO NOTHING")
            tk = await conn.fetchval(
                "INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
                "VALUES ('zalo_personal','Zalo shop','active','zl') RETURNING id")
            lan, _ = await _khach(conn, tk, "Lan", "u-lan", {"channel": "zalo_personal"}, 0)
            # Nhóm theo bản sửa nhóm: cả hai dấu.
            nhom, cid_nhom = await _khach(conn, tk, "Nhóm Sỉ Hà Nội", "group:g1",
                                          {"channel": "zalo_personal", "loai": "nhom"}, 1)
            # Nhóm tạo TRƯỚC khi có `metadata.loai`: chỉ còn khoá `group:`.
            cu, _ = await _khach(conn, tk, "Nhóm Cũ", "group:g2", {}, 1)
            return {"lan": str(lan), "nhom": str(nhom), "cu": str(cu), "cid_nhom": str(cid_nhom)}
        finally:
            await conn.close()
    return asyncio.run(chay())


def test_danh_sach_va_tim_khach_khong_co_nhom(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QUYEN))) as k:
        d = _dung(csdl_kiem_thu)
        r = k.get("/api/contacts")
        assert r.status_code == 200, r.text
        assert {x["display_name"] for x in r.json()} == {"Lan"}
        assert k.get("/api/contacts", params={"q": "Nhóm"}).json() == []
        # Mở thẳng hồ sơ nhóm: 404, không phải một Customer 360 rỗng.
        assert k.get(f"/api/contacts/{d['nhom']}").status_code == 404
        assert k.get(f"/api/contacts/{d['cu']}").status_code == 404
        assert k.get(f"/api/contacts/{d['lan']}").status_code == 200


def test_khach_vo_chu_va_khach_moi_khong_dem_nhom(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QUYEN))) as k:
        _dung(csdl_kiem_thu)
        vc = k.get("/api/khach-vo-chu").json()
        assert vc["so"] == 1 and [x["display_name"] for x in vc["khach"]] == ["Lan"]
        # Ô thường trực trên Tổng quan dùng CÙNG định nghĩa với danh sách.
        assert k.get("/api/overview").json()["khach_vo_chu"]["so"] == 1
        pt = k.get("/api/phan-tich")
        assert pt.status_code == 200, pt.text
        assert pt.json()["khach"] == {"tong": 1, "moi": 1, "quay_lai": 0}


def test_khong_gop_duoc_nhom_vao_mot_nguoi(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QUYEN))) as k:
        d = _dung(csdl_kiem_thu)
        for nguon, dich in ((d["nhom"], d["lan"]), (d["lan"], d["cu"])):
            r = k.post("/api/contacts/merge", json={
                "source_id": nguon, "target_id": dich, "reason": "gộp thử",
                "expected_source_version": 1, "expected_target_version": 1})
            assert r.status_code == 422, r.text
            assert "nhóm" in r.json()["detail"]

    async def dem():
        conn = await asyncpg.connect(csdl_kiem_thu)
        try:
            return await conn.fetchval("SELECT count(*) FROM contact_merges")
        finally:
            await conn.close()
    assert asyncio.run(dem()) == 0


def test_dich_vu_gop_tu_chan_nhom_khong_chi_route():
    """Chặn ở `IdentityService`: route khác gọi dịch vụ cũng không lọt."""
    from agent.omnichannel import identity

    src = Path(identity.__file__).read_text(encoding="utf-8")
    than = src[src.index("async def merge_contacts"):src.index("async def unmerge_contact")]
    assert 'source.get("la_nhom") or target.get("la_nhom")' in than
    pg = src[src.index("class PostgresIdentityTransaction"):]
    lock = pg[pg.index("async def lock_contacts"):pg.index("async def snapshot_contact_refs")]
    assert "sql_la_nhom('contacts')" in lock


def test_bi_danh_la_khong_chen_duoc_sql():
    import pytest

    from agent.core.lien_he_nhom import sql_khong_phai_nhom, sql_la_nhom

    assert "contact.id" in sql_la_nhom("contact")
    assert sql_khong_phai_nhom("ct").startswith("NOT EXISTS")
    with pytest.raises(ValueError):
        sql_la_nhom("ct; DROP TABLE contacts")


# ------------------------------------------------------------ mở lại tay

def test_mo_lai_tay_hoi_thoai_da_giai_quyet(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QUYEN))) as k:
        d = _dung(csdl_kiem_thu)
        cid = d["cid_nhom"]
        assert k.post(f"/api/inbox/conversations/{cid}/mo-lai").json() == {"da_mo": False}

        async def dong_lai():
            conn = await asyncpg.connect(csdl_kiem_thu)
            try:
                await conn.execute("UPDATE conversations SET state = 'resolved', "
                                   "resolved_at = now() WHERE id = $1", UUID(cid))
            finally:
                await conn.close()
        asyncio.run(dong_lai())
        assert k.post(f"/api/inbox/conversations/{cid}/mo-lai").json() == {"da_mo": True}

    async def doc():
        conn = await asyncpg.connect(csdl_kiem_thu)
        try:
            st = await conn.fetchval("SELECT state FROM conversations WHERE id = $1", UUID(cid))
            ev = await conn.fetch("SELECT kind, actor FROM events WHERE ref_id = $1 "
                                  "ORDER BY created_at", UUID(cid))
            return st, [(e["kind"], e["actor"]) for e in ev]
        finally:
            await conn.close()
    st, ev = asyncio.run(doc())
    assert st == "open"
    # Cùng sự kiện màn Phân tích đếm, kèm người mở.
    assert ("conversation.reopened", "system") in ev and ("conversation.mo_lai_tay", "kt") in ev


def test_mo_lai_tay_can_quyen_nhan(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("hoi_thoai.doc", "hoi_thoai.xem_tat_ca"))) as k:
        d = _dung(csdl_kiem_thu)
        assert k.post(f"/api/inbox/conversations/{d['cid_nhom']}/mo-lai").status_code == 403


# ------------------------------------------------------- ghi chú nội bộ

def test_route_ghi_chu_khong_cham_toi_duong_gui():
    """
    Ghi chú KHÔNG BAO GIỜ đi ra kênh. Test Postgres ở
    test_api_nhan_ghi_chu_tim_kiem.py đếm `outbox_jobs` sau khi tạo ghi chú;
    ở đây canh tận gốc: mô-đun route ghi chú không import gì của outbox hay
    đường gửi tin, nên không có cách nào nó vô tình xếp một tin gửi khách.
    """
    tep = ROOT / "agent" / "api" / "hoi_thoai_nhan.py"
    cay = ast.parse(tep.read_text(encoding="utf-8"))
    nhap = set()
    for n in ast.walk(cay):
        if isinstance(n, ast.ImportFrom):
            nhap.add(n.module or "")
            nhap.update(a.name for a in n.names)
        elif isinstance(n, ast.Import):
            nhap.update(a.name for a in n.names)
    cam = [m for m in nhap if any(t in m for t in ("outbox", "outbound", "hoi_thoai_cu", "send"))]
    assert not cam, f"route ghi chú import đường gửi tin: {cam}"
    than = ast.get_source_segment(tep.read_text(encoding="utf-8"), next(
        n for n in cay.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "them_ghi_chu"))
    assert "INSERT INTO hoi_thoai_ghi_chu" in than and "messages" not in than
