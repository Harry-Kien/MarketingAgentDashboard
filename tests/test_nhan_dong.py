"""
Nhãn động (migration 0056) — danh mục chung, hai loại độc lập.

Ràng buộc canh ở đây, mỗi cái một lý do đã ghi trong mã:
  · chuyển dữ liệu chữ tự do cũ sang danh mục, gộp không phân biệt hoa
    thường, đổi quy tắc tự động sang id — và chữ không chuyển được thì
    ĐẾM vào nhật ký, không mất im lặng;
  · trùng tên (kể cả nhãn đã ngừng), ngừng dùng thay vì xoá, xoá chỉ khi
    chưa từng dùng — chốt ở API VÀ ở khoá ngoại;
  · nhãn khách không gắn được lên hội thoại và ngược lại (API VÀ CSDL);
  · gắn/gỡ đòi đúng quyền, đúng phạm vi kênh, và để lại dòng `events`;
  · gộp khách gộp nhãn, hoàn tác gỡ đúng phần đã chép;
  · dữ liệu cá nhân: tra cứu kể tên nhãn, xoá thì xoá liên kết;
  · không mã nào còn GHI vào hai bảng chữ tự do cũ.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import nguoi_thu

ROOT = Path(__file__).resolve().parent.parent
LUOC_DO = ROOT / "agent" / "schema.sql"
MIG = ROOT / "agent" / "migrations" / "versions" / "0056_danh_muc_nhan.sql"
UID = "00000000-0000-0000-0000-000000000001"


# ------------------------------------------------------------------ thuần

def test_chuan_ten_gop_khoang_trang_va_NFC():
    import unicodedata

    from agent.core import nhan

    assert nhan.chuan_ten("  Chờ   hàng  ") == "Chờ hàng"
    to_hop = unicodedata.normalize("NFD", "đổi trả")
    assert to_hop != "đổi trả" and nhan.chuan_ten(to_hop) == "đổi trả"
    for xau in ("", "   ", "x" * 81, None):
        with pytest.raises(nhan.NhanHong):
            nhan.chuan_ten(xau)


def test_chuan_mau():
    from agent.core import nhan

    assert nhan.chuan_mau(" #1D4ED8 ") == "#1d4ed8"
    for xau in ("1d4ed8", "#fff", "#12345g", "red", None):
        with pytest.raises(nhan.NhanHong):
            nhan.chuan_mau(xau)


def test_bang_mau_du_tuong_phan_va_khop_migration():
    """
    Migration chép bảng màu thành mảng SQL; lệch nhau thì nhãn chuyển đổi và
    nhãn tạo mới dùng hai bảng màu khác nhau — và một màu nhạt lọt vào là
    chip chữ trắng không ai đọc được.
    """
    from agent.core import nhan

    for m in nhan.BANG_MAU:
        assert nhan.ti_le_tuong_phan(m, "#ffffff") >= 4.5, m
        assert nhan.mau_chu(m) == "#ffffff"
    mang = re.search(r"ARRAY\[([^\]]+)\]", MIG.read_text(encoding="utf-8")).group(1)
    assert tuple(re.findall(r"'(#[0-9a-f]{6})'", mang)) == nhan.BANG_MAU
    # Màu nhạt do người dùng chọn -> chữ đậm.
    assert nhan.mau_chu("#fde68a") == "#111827"


def test_sql_nhan_da_gan_chi_nhan_bang_hang():
    from agent.core import nhan

    with pytest.raises(ValueError):
        nhan.sql_nhan_da_gan("users; DROP TABLE x", "contact_id", "$1")


def test_migration_khoa_ngoai_dung_chieu():
    sql = MIG.read_text(encoding="utf-8")
    for bang, chu in (("hoi_thoai_gan_nhan", "conversations"), ("khach_gan_nhan", "contacts")):
        than = re.search(rf"CREATE TABLE IF NOT EXISTS {bang} \((.*?)\n\);", sql, re.S).group(1)
        # Xoá hội thoại/khách thì liên kết đi theo; xoá NHÃN đang gắn thì không.
        assert re.search(rf"REFERENCES {chu}\(id\) ON DELETE CASCADE", than), bang
        assert re.search(r"REFERENCES nhan \(id, loai\) ON DELETE RESTRICT", than), bang


def test_khong_nhan_ban_vao_schema_sql():
    """`schema.sql` chạy TRƯỚC migration: bảng mới chỉ đặt trong 0056."""
    sql = LUOC_DO.read_text(encoding="utf-8")
    for bang in ("nhan", "hoi_thoai_gan_nhan", "khach_gan_nhan"):
        assert f"CREATE TABLE IF NOT EXISTS {bang} " not in sql


def test_khong_ma_nao_con_ghi_bang_chu_tu_do_cu():
    """
    `contact_tags`/`hoi_thoai_nhan` là ảnh chụp lúc chuyển đổi. Một đường
    còn ghi vào đó là có HAI nguồn nhãn lệch nhau mà không ai biết — trừ
    xoá dữ liệu cá nhân, phải xoá cả chữ cũ viết về người ấy.
    """
    ghi = re.compile(r"(INSERT\s+INTO|UPDATE)\s+(contact_tags|hoi_thoai_nhan)\b", re.I)
    vi_pham = []
    for p in (ROOT / "agent").rglob("*.py"):
        for m in ghi.finditer(p.read_text(encoding="utf-8")):
            vi_pham.append(f"{p.relative_to(ROOT)}: {m.group(0)}")
    assert not vi_pham, vi_pham
    xoa_cu = re.compile(r"DELETE\s+FROM\s+(contact_tags|hoi_thoai_nhan)\b", re.I)
    for p in (ROOT / "agent").rglob("*.py"):
        if xoa_cu.search(p.read_text(encoding="utf-8")):
            assert p.name == "du_lieu_ca_nhan.py", p


# ------------------------------------------------------------------ migration (Postgres thật)

async def _ket_noi(url: str):
    conn = await asyncpg.connect(url)
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads,
                              schema="pg_catalog")
    return conn


async def _khach_va_hoi_thoai(conn, ext: str, tk=None):
    if tk is None:
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
    return tk, kh, cid


def test_migration_chuyen_du_lieu_cu(csdl_kiem_thu):
    from agent.migrations.runner import apply_migrations, discover_migrations

    async def chay():
        conn = await _ket_noi(csdl_kiem_thu)
        try:
            await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
            ms = discover_migrations()
            await apply_migrations(conn, [m for m in ms if m.version < "0056"])
            _, a, ca = await _khach_va_hoi_thoai(conn, "a")
            _, b, cb = await _khach_va_hoi_thoai(conn, "b")
            await conn.execute(
                "INSERT INTO contact_tags (contact_id, tag, created_at) VALUES "
                "($1,'VIP', now() - interval '2 days'), ($2,' vip ', now()), "
                "($2,'Khách   sỉ', now()), ($2,'   ', now())", a, b)
            await conn.execute(
                "INSERT INTO hoi_thoai_nhan (conversation_id, nhan) VALUES "
                "($1,'chờ hàng'), ($2,'chờ hàng')", ca, cb)
            q1 = await conn.fetchval(
                "INSERT INTO quy_tac_tu_dong (ten, su_kien, dieu_kien, hanh_dong) VALUES "
                "('cũ', 'tin_khach', $1::jsonb, $2::jsonb) RETURNING id",
                {"nhan_co": "chờ hàng", "chua_tu": ["ship"]},
                [{"loai": "gan_nhan", "nhan": "đã chào"}, {"loai": "chuyen_nguoi"}])
            # Dữ liệu cũ mã hoá hai lần (chuỗi JSON trong JSONB) vẫn phải đổi được.
            q2 = await conn.fetchval(
                "INSERT INTO quy_tac_tu_dong (ten, su_kien, dieu_kien, hanh_dong) VALUES "
                "('chuỗi', 'tin_khach', to_jsonb($1::text), to_jsonb($2::text)) RETURNING id",
                json.dumps({"nhan_khong": "Đã Chào"}),
                json.dumps([{"loai": "gan_nhan", "nhan": "chờ hàng"}]))
            await apply_migrations(conn, ms)
            return {
                "nhan": [dict(r) for r in await conn.fetch(
                    "SELECT loai, ten, mau FROM nhan ORDER BY loai, lower(ten)")],
                "gan_khach": await conn.fetchval("SELECT count(*) FROM khach_gan_nhan"),
                "gan_ht": await conn.fetchval("SELECT count(*) FROM hoi_thoai_gan_nhan"),
                "vip_cua_b": await conn.fetchval(
                    "SELECT count(*) FROM khach_gan_nhan g JOIN nhan n ON n.id = g.nhan_id "
                    "WHERE g.contact_id = $1 AND n.ten = 'VIP'", b),
                "q1": dict(await conn.fetchrow(
                    "SELECT dieu_kien, hanh_dong FROM quy_tac_tu_dong WHERE id = $1", q1)),
                "q2": dict(await conn.fetchrow(
                    "SELECT dieu_kien, hanh_dong FROM quy_tac_tu_dong WHERE id = $1", q2)),
                "id": {r["ten"]: str(r["id"]) for r in await conn.fetch("SELECT id, ten FROM nhan")},
                "tong_ket": await conn.fetchval(
                    "SELECT detail FROM events WHERE kind = 'nhan.chuyen_doi'"),
                "su_kien_qt": await conn.fetchval(
                    "SELECT count(*) FROM events WHERE kind = 'nhan.chuyen_quy_tac'"),
                "cu_con": await conn.fetchval("SELECT count(*) FROM contact_tags"),
            }
        finally:
            await conn.close()

    kq = asyncio.run(chay())
    # "VIP" và " vip " là MỘT nhãn, tên lấy từ biến thể gắn sớm nhất.
    assert [(n["loai"], n["ten"]) for n in kq["nhan"]] == [
        ("hoi_thoai", "chờ hàng"), ("hoi_thoai", "đã chào"),
        ("khach", "Khách sỉ"), ("khach", "VIP")]
    assert all(re.fullmatch(r"#[0-9a-f]{6}", n["mau"]) for n in kq["nhan"])
    assert kq["gan_khach"] == 3 and kq["vip_cua_b"] == 1 and kq["gan_ht"] == 2
    i = kq["id"]
    assert kq["q1"]["dieu_kien"] == {"chua_tu": ["ship"], "nhan_hoi_thoai_co": [i["chờ hàng"]]}
    assert kq["q1"]["hanh_dong"] == [
        {"loai": "gan_nhan_hoi_thoai", "nhan_id": i["đã chào"]}, {"loai": "chuyen_nguoi"}]
    assert kq["q2"]["dieu_kien"] == {"nhan_hoi_thoai_khong": [i["đã chào"]]}
    assert kq["q2"]["hanh_dong"] == [{"loai": "gan_nhan_hoi_thoai", "nhan_id": i["chờ hàng"]}]
    assert kq["su_kien_qt"] == 2
    # Nhãn chỉ có khoảng trắng không chuyển được — ĐẾM ra, không mất im lặng,
    # và bảng cũ vẫn giữ nguyên.
    assert kq["tong_ket"]["contact_tags_bo_qua"] == 1
    assert kq["tong_ket"]["hoi_thoai_nhan_bo_qua"] == 0
    assert kq["cu_con"] == 4


def test_csdl_chan_sai_loai_va_xoa_nhan_dang_gan(csdl_kiem_thu):
    """Chốt thứ hai, ở CSDL: mã gọi thẳng SQL cũng không lách được."""
    from agent.migrations.runner import apply_all

    async def chay():
        conn = await _ket_noi(csdl_kiem_thu)
        try:
            await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
            await apply_all(conn)
            _, kh, cid = await _khach_va_hoi_thoai(conn, "a")
            nk = await conn.fetchval("INSERT INTO nhan (loai, ten) VALUES ('khach','VIP') RETURNING id")
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await conn.execute("INSERT INTO hoi_thoai_gan_nhan (conversation_id, nhan_id) "
                                   "VALUES ($1,$2)", cid, nk)
            await conn.execute("INSERT INTO khach_gan_nhan (contact_id, nhan_id) VALUES ($1,$2)",
                               kh, nk)
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await conn.execute("DELETE FROM nhan WHERE id = $1", nk)
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute("INSERT INTO nhan (loai, ten) VALUES ('khach','vip')")
            # Cùng tên KHÁC loại là hai nhãn độc lập.
            await conn.execute("INSERT INTO nhan (loai, ten) VALUES ('hoi_thoai','VIP')")
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute("INSERT INTO nhan (loai, ten) VALUES ('khach','a  b')")
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute("INSERT INTO nhan (loai, ten, mau) VALUES ('khach','x','red')")
        finally:
            await conn.close()

    asyncio.run(chay())


# ------------------------------------------------------------------ API (Postgres thật)

def _app(url: str, nguoi: dict) -> FastAPI:
    from agent import db
    from agent.api.contacts import router as contacts_router
    from agent.api.hoi_thoai_nhan import router as ht_router
    from agent.api.inbox import router as inbox_router
    from agent.api.nhan import router as nhan_router
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.api.tu_dong_api import router as tu_dong_router
    from agent.migrations.runner import apply_all

    app = FastAPI()
    for r in (inbox_router, ht_router, nhan_router, contacts_router, tu_dong_router):
        app.include_router(r)
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
                "VALUES ($1,'kt','x','Kiểm Thử') ON CONFLICT DO NOTHING", UUID(UID))

    @app.on_event("shutdown")
    async def _dong():
        if db._pool is not None:
            await db._pool.close()
            db._pool = None

    return app


def _sql(url: str, sql: str, *a):
    async def chay():
        conn = await _ket_noi(url)
        try:
            return await conn.fetch(sql, *a)
        finally:
            await conn.close()
    return [dict(r) for r in asyncio.run(chay())]


def _dung(url: str) -> dict:
    """Kênh A (người thử là thành viên) có khách a; kênh B thì không."""
    async def chay():
        conn = await _ket_noi(url)
        try:
            tk_a, a, ca = await _khach_va_hoi_thoai(conn, "khach-a")
            _, b, cb = await _khach_va_hoi_thoai(conn, "khach-b")
            _, a2, ca2 = await _khach_va_hoi_thoai(conn, "khach-a2", tk=tk_a)
            await conn.execute("INSERT INTO account_memberships (account_id, user_id) "
                               "VALUES ($1,$2)", tk_a, UUID(UID))
            return {k: str(v) for k, v in dict(a=a, b=b, ca=ca, cb=cb, a2=a2, ca2=ca2).items()}
        finally:
            await conn.close()
    return asyncio.run(chay())


QT = ("cau_hinh.doc", "cau_hinh.sua", "hoi_thoai.doc", "hoi_thoai.tra_loi",
      "khach.doc", "khach.sua")


def _tao(k, loai, ten, **them) -> str:
    r = k.post("/api/nhan", json={"loai": loai, "ten": ten, **them})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_danh_muc_tao_sua_trung_ten_ngung_xoa(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QT))) as k:
        h = _dung(csdl_kiem_thu)
        vip = _tao(k, "khach", "  VIP ")
        assert k.post("/api/nhan", json={"loai": "khach", "ten": "vip"}).status_code == 409
        # Khác loại: hợp lệ.
        _tao(k, "hoi_thoai", "VIP")
        assert k.post("/api/nhan", json={"loai": "khac", "ten": "x"}).status_code == 422
        assert k.post("/api/nhan", json={"loai": "khach", "ten": "x", "mau": "đỏ"}).status_code == 422

        r = k.put(f"/api/nhan/{vip}", json={"ten": "Khách VIP", "mau": "#B91C1C", "mo_ta": "chi > 5tr"})
        assert r.status_code == 200 and r.json()["mau"] == "#b91c1c"
        assert r.json()["mau_chu"] == "#ffffff"

        # Đã dùng -> không xoá được, ngừng thì được; chỗ đã gắn còn nguyên.
        assert k.post(f"/api/contacts/{h['a']}/nhan", json={"nhan_id": vip}).status_code == 201
        r = k.delete(f"/api/nhan/{vip}")
        assert r.status_code == 409 and "Ngừng sử dụng" in r.json()["detail"]
        assert k.post(f"/api/nhan/{vip}/ngung").status_code == 200
        assert vip not in [x["id"] for x in k.get("/api/nhan/khach").json()["nhan"]]
        ds = k.get("/api/nhan?loai=khach").json()["nhan"]
        assert [(x["ten"], x["dang_dung"], x["so_khach"]) for x in ds] == [("Khách VIP", False, 1)]
        chi_tiet = k.get(f"/api/contacts/{h['a']}").json()
        assert [(x["ten"], x["dang_dung"]) for x in chi_tiet["nhan"]] == [("Khách VIP", False)]
        # Nhãn đã ngừng không gắn MỚI được.
        r = k.post(f"/api/contacts/{h['a2']}/nhan", json={"nhan_id": vip})
        assert r.status_code == 422 and "ngừng" in r.json()["detail"]
        # Tạo lại cùng tên khi bản cũ đang ngừng -> chỉ đường «Dùng lại».
        r = k.post("/api/nhan", json={"loai": "khach", "ten": "khách vip"})
        assert r.status_code == 409 and "Dùng lại" in r.json()["detail"]
        assert k.post(f"/api/nhan/{vip}/dung-lai").json()["dang_dung"] is True

        nham = _tao(k, "khach", "gõ nhầm")
        assert k.delete(f"/api/nhan/{nham}").status_code == 204

    su_kien = [r["kind"] for r in _sql(
        csdl_kiem_thu, "SELECT kind FROM events WHERE kind LIKE 'nhan.%' "
        "AND actor <> 'migration_0056' ORDER BY id")]
    assert su_kien == ["nhan.tao", "nhan.tao", "nhan.sua", "nhan.gan_khach", "nhan.ngung",
                       "nhan.dung_lai", "nhan.tao", "nhan.xoa"]
    sua = _sql(csdl_kiem_thu, "SELECT detail FROM events WHERE kind = 'nhan.sua'")[0]["detail"]
    assert sua["doi"]["ten"] == {"cu": "VIP", "moi": "Khách VIP"}


def test_quyen_danh_muc(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("hoi_thoai.doc", "khach.doc"))) as k:
        assert k.post("/api/nhan", json={"loai": "khach", "ten": "x"}).status_code == 403
        assert k.get("/api/nhan").status_code == 403
        assert k.get("/api/nhan/hoi-thoai").status_code == 200
        assert k.get("/api/nhan/khach").status_code == 200
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("hoi_thoai.doc"))) as k:
        assert k.get("/api/nhan/khach").status_code == 403


def test_nhan_hoi_thoai_gan_go_loc_quyen_va_pham_vi(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QT))) as k:
        h = _dung(csdl_kiem_thu)
        cho = _tao(k, "hoi_thoai", "Chờ hàng")
        vip_khach = _tao(k, "khach", "VIP")

        r = k.post(f"/api/inbox/conversations/{h['ca']}/nhan", json={"nhan_id": cho})
        assert r.status_code == 201 and r.json()["moi_gan"] is True
        # Đường cũ theo TÊN vẫn chạy (khác hoa thường, khoảng trắng thừa)...
        r = k.post(f"/api/inbox/conversations/{h['ca']}/nhan", json={"nhan": " chờ  HÀNG "})
        assert r.status_code == 201 and r.json()["moi_gan"] is False
        # ...nhưng KHÔNG tự tạo nhãn mới.
        r = k.post(f"/api/inbox/conversations/{h['ca']}/nhan", json={"nhan": "lạ hoắc"})
        assert r.status_code == 422 and "Quản lý nhãn" in r.json()["detail"]
        # Nhãn KHÁCH không gắn lên hội thoại.
        r = k.post(f"/api/inbox/conversations/{h['ca']}/nhan", json={"nhan_id": vip_khach})
        assert r.status_code == 422 and "nhãn khách" in r.json()["detail"].lower()
        # Ngoài kênh: 404, không xác nhận hội thoại tồn tại.
        assert k.post(f"/api/inbox/conversations/{h['cb']}/nhan",
                      json={"nhan_id": cho}).status_code == 404
        assert k.get(f"/api/inbox/conversations/{h['cb']}/nhan").status_code == 404

        items = k.get("/api/inbox/conversations").json()["items"]
        dong = next(x for x in items if x["id"] == h["ca"])
        assert dong["nhan"] == ["Chờ hàng"]
        assert [x["ten"] for x in dong["nhan_chi_tiet"]] == ["Chờ hàng"]
        loc = k.get("/api/inbox/conversations", params={"nhan_id": cho}).json()["items"]
        assert [x["id"] for x in loc] == [h["ca"]]
        loc = k.get("/api/inbox/conversations", params={"nhan": "chờ hàng"}).json()["items"]
        assert [x["id"] for x in loc] == [h["ca"]]
        chi_tiet = k.get(f"/api/inbox/conversations/{h['ca']}").json()
        assert [x["id"] for x in chi_tiet["nhan_chi_tiet"]] == [cho]
        assert k.get("/api/inbox/nhan").json()["nhan"][0]["so"] == 1

        assert k.delete(f"/api/inbox/conversations/{h['ca']}/nhan/{cho}").status_code == 204
        assert k.get("/api/inbox/conversations", params={"nhan_id": cho}).json()["items"] == []

    with TestClient(_app(csdl_kiem_thu, nguoi_thu("hoi_thoai.doc"))) as k:
        assert k.post(f"/api/inbox/conversations/{h['ca']}/nhan",
                      json={"nhan_id": cho}).status_code == 403

    su_kien = _sql(csdl_kiem_thu, "SELECT kind, ref_id, actor, detail FROM events "
                                  "WHERE kind LIKE 'nhan.%hoi_thoai' ORDER BY id")
    assert [(r["kind"], str(r["ref_id"]), r["actor"]) for r in su_kien] == [
        ("nhan.gan_hoi_thoai", h["ca"], "kt"), ("nhan.go_hoi_thoai", h["ca"], "kt")]
    assert su_kien[0]["detail"] == {"nhan_id": cho, "ten": "Chờ hàng"}


def test_nhan_khach_gan_go_loc_quyen_va_pham_vi(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QT))) as k:
        h = _dung(csdl_kiem_thu)
        si = _tao(k, "khach", "Khách sỉ")
        cho = _tao(k, "hoi_thoai", "Chờ hàng")
        assert k.post(f"/api/contacts/{h['a']}/nhan", json={"nhan_id": si}).status_code == 201
        r = k.post(f"/api/contacts/{h['a']}/nhan", json={"nhan_id": cho})
        assert r.status_code == 422 and "nhãn hội thoại" in r.json()["detail"].lower()
        # Khách kênh B: ngoài phạm vi -> 404.
        assert k.post(f"/api/contacts/{h['b']}/nhan", json={"nhan_id": si}).status_code == 404

        ds = k.get("/api/contacts", params={"nhan_id": si}).json()
        assert [x["id"] for x in ds] == [h["a"]]
        assert [x["ten"] for x in ds[0]["nhan"]] == ["Khách sỉ"]
        # Đường `/tags` cũ: tra danh mục theo tên, không tạo mới.
        assert k.post(f"/api/contacts/{h['a']}/tags", json={"tag": "chưa có"}).status_code in (403, 422)

        assert k.delete(f"/api/contacts/{h['a']}/nhan/{si}").status_code == 204
        assert k.get("/api/contacts", params={"nhan_id": si}).json() == []

    with TestClient(_app(csdl_kiem_thu, nguoi_thu("khach.doc"))) as k:
        assert k.post(f"/api/contacts/{h['a']}/nhan", json={"nhan_id": si}).status_code == 403

    su_kien = [r["kind"] for r in _sql(
        csdl_kiem_thu, "SELECT kind FROM events WHERE kind LIKE 'nhan.%khach' ORDER BY id")]
    assert su_kien == ["nhan.gan_khach", "nhan.go_khach"]


def test_duong_tags_cu_tra_danh_muc(csdl_kiem_thu):
    from conftest import toan_quyen

    with TestClient(_app(csdl_kiem_thu, toan_quyen(id=UID, ten="kt"))) as k:
        h = _dung(csdl_kiem_thu)
        r = k.post(f"/api/contacts/{h['a']}/tags", json={"tag": "VIP"})
        assert r.status_code == 422 and "Quản lý nhãn" in r.json()["detail"]
        _tao(k, "khach", "VIP")
        assert k.post(f"/api/contacts/{h['a']}/tags", json={"tag": " vip "}).status_code == 201
        assert k.get(f"/api/contacts/{h['a']}").json()["tags"][0]["tag"] == "VIP"
    assert _sql(csdl_kiem_thu, "SELECT count(*) AS n FROM contact_tags")[0]["n"] == 0


# ------------------------------------------------------------------ gộp khách

def test_gop_khach_gop_nhan_va_hoan_tac_go_dung_phan_chep(csdl_kiem_thu):
    from agent import db
    from agent.migrations.runner import apply_all
    from agent.omnichannel.identity import IdentityService, PostgresIdentityRepository

    async def chay():
        async def _codec(conn):
            await conn.set_type_codec("jsonb", encoder=json.dumps,
                                      decoder=json.loads, schema="pg_catalog")
        db._pool = await asyncpg.create_pool(csdl_kiem_thu, min_size=1, max_size=3, init=_codec)
        try:
            async with db._pool.acquire() as conn:
                await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
                await apply_all(conn)
                await conn.execute(
                    "INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam) "
                    "VALUES ($1,'kt','x')", UUID(UID))
                _, nguon, _ = await _khach_va_hoi_thoai(conn, "nguon")
                _, dich, _ = await _khach_va_hoi_thoai(conn, "dich")
                si, vip = [await conn.fetchval(
                    "INSERT INTO nhan (loai, ten) VALUES ('khach',$1) RETURNING id", t)
                    for t in ("Khách sỉ", "VIP")]
                await conn.executemany(
                    "INSERT INTO khach_gan_nhan (contact_id, nhan_id) VALUES ($1,$2)",
                    [(nguon, si), (nguon, vip), (dich, vip)])
            ver = {r["id"]: r["version"] for r in await db.fetch(
                "SELECT id, version FROM contacts")}
            dv = IdentityService(PostgresIdentityRepository())
            kq = await dv.merge_contacts(
                source_id=nguon, target_id=dich, actor_id=UUID(UID), reason="cùng người",
                expected_source_version=ver[nguon], expected_target_version=ver[dich])

            async def nhan_cua(kh):
                return sorted(r["ten"] for r in await db.fetch(
                    "SELECT n.ten FROM khach_gan_nhan g JOIN nhan n ON n.id = g.nhan_id "
                    "WHERE g.contact_id = $1", kh))
            sau_gop = await nhan_cua(dich), await nhan_cua(nguon)
            await dv.unmerge_contact(merge_id=kq.merge_id, actor_id=UUID(UID), reason="nhầm")
            return sau_gop, (await nhan_cua(dich), await nhan_cua(nguon))
        finally:
            await db._pool.close()
            db._pool = None

    (dich_gop, nguon_gop), (dich_hoan, nguon_hoan) = asyncio.run(chay())
    assert dich_gop == ["Khách sỉ", "VIP"] and nguon_gop == ["Khách sỉ", "VIP"]
    # Hoàn tác: đích mất ĐÚNG nhãn đã chép sang; "VIP" vốn có thì giữ.
    assert dich_hoan == ["VIP"] and nguon_hoan == ["Khách sỉ", "VIP"]


# ------------------------------------------------------------------ dữ liệu cá nhân

def test_pdpd_tra_cuu_ke_ten_nhan_va_xoa_lien_ket(csdl_kiem_thu):
    from agent import db
    from agent.core import du_lieu_ca_nhan
    from agent.migrations.runner import apply_all

    async def chay():
        async def _codec(conn):
            await conn.set_type_codec("jsonb", encoder=json.dumps,
                                      decoder=json.loads, schema="pg_catalog")
        db._pool = await asyncpg.create_pool(csdl_kiem_thu, min_size=1, max_size=3, init=_codec)
        try:
            async with db._pool.acquire() as conn:
                await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
                await apply_all(conn)
                _, kh, _ = await _khach_va_hoi_thoai(conn, "pdpd")
                await conn.execute("UPDATE contacts SET phone = '0912345678' WHERE id = $1", kh)
                nid = await conn.fetchval(
                    "INSERT INTO nhan (loai, ten) VALUES ('khach','Khó tính') RETURNING id")
                await conn.execute("INSERT INTO khach_gan_nhan (contact_id, nhan_id) "
                                   "VALUES ($1,$2)", kh, nid)
                # Chữ cũ trước 0056 vẫn phải bị xoá theo khách.
                await conn.execute("INSERT INTO contact_tags (contact_id, tag) "
                                   "VALUES ($1,'khó tính')", kh)
            tra = await du_lieu_ca_nhan.tra_cuu("0912345678")
            kq = await du_lieu_ca_nhan._xoa_ho_so_crm(tra["ho_so_khach"])
            con = (await db.fetchrow("SELECT count(*) AS n FROM khach_gan_nhan"))["n"]
            cu = (await db.fetchrow("SELECT count(*) AS n FROM contact_tags"))["n"]
            danh_muc = (await db.fetchrow("SELECT count(*) AS n FROM nhan"))["n"]
            return tra, kq, con, cu, danh_muc
        finally:
            await db._pool.close()
            db._pool = None

    tra, kq, con, cu, danh_muc = asyncio.run(chay())
    hs = tra["ho_so_khach"][0]
    assert hs["nhan"] == 1 and hs["nhan_ten"] == ["Khó tính"]
    assert kq["nhan"] == 2 and con == 0 and cu == 0
    assert danh_muc == 1, "tên nhãn là từ vựng của cửa hàng, không phải dữ liệu của khách"


# ------------------------------------------------------------------ quy tắc tự động (API)

def test_quy_tac_tach_nhan_khach_va_nhan_hoi_thoai(csdl_kiem_thu):
    quyen = (*QT, "dinh_tuyen.doc", "dinh_tuyen.sua")
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*quyen))) as k:
        ht = _tao(k, "hoi_thoai", "Chờ hàng")
        kh = _tao(k, "khach", "VIP")
        ok = {"ten": "VIP chờ hàng",
              "dieu_kien": {"nhan_hoi_thoai_co": [ht], "nhan_khach_co": [kh]},
              "hanh_dong": [{"loai": "gan_nhan_khach", "nhan_id": kh}]}
        assert k.post("/api/tu-dong", json=ok).status_code == 201
        # Nhãn khách đặt vào ô nhãn hội thoại: không bao giờ khớp mà trông
        # vẫn đúng — phải bị chặn lúc lưu.
        sai = {**ok, "dieu_kien": {"nhan_hoi_thoai_co": [kh]}}
        r = k.post("/api/tu-dong", json=sai)
        assert r.status_code == 422 and "nhãn khách" in r.json()["detail"].lower()
        sai = {**ok, "hanh_dong": [{"loai": "gan_nhan_hoi_thoai", "nhan_id": kh}]}
        assert k.post("/api/tu-dong", json=sai).status_code == 422
        assert k.post("/api/tu-dong", json={**ok, "dieu_kien": {"nhan_khach_co": ["khong-phai-id"]}}
                      ).status_code == 422

        # Khoá chữ cũ: đổi sang id lúc lưu nếu tên có trong danh mục...
        cu = {"ten": "cũ", "dieu_kien": {"nhan_co": "CHỜ HÀNG"},
              "hanh_dong": [{"loai": "gan_nhan", "nhan": "chờ hàng"}]}
        r = k.post("/api/tu-dong", json=cu)
        assert r.status_code == 201, r.text
        assert r.json()["dieu_kien"] == {"nhan_hoi_thoai_co": [ht]}
        assert r.json()["hanh_dong"] == [{"loai": "gan_nhan_hoi_thoai", "nhan_id": ht}]
        # ...không có thì 422, không tạo nhãn chữ.
        r = k.post("/api/tu-dong", json={**cu, "dieu_kien": {"nhan_co": "không có"}})
        assert r.status_code == 422 and "Quản lý nhãn" in r.json()["detail"]

        # Nhãn đã ngừng: quy tắc BẬT không gắn được; TẮT thì lưu được.
        k.post(f"/api/nhan/{kh}/ngung")
        assert k.post("/api/tu-dong", json=ok).status_code == 422
        assert k.post("/api/tu-dong", json={**ok, "bat": False}).status_code == 201
        # Ngừng một nhãn quy tắc đang dùng -> cảnh báo ngay.
        r = k.post(f"/api/nhan/{ht}/ngung")
        assert "quy tắc" in r.json()["canh_bao"]


# ------------------------------------------------------------------ giao diện (đọc mã nguồn)

SRC = ROOT / "dashboard" / "src"


def _src(ten: str) -> str:
    return (SRC / ten).read_text(encoding="utf-8")


def test_quan_ly_nhan_dang_ky_mo_dun_va_khung_tab_co_khe():
    """
    Màn Cài đặt & Quản trị gọi `GAN_TAB['cc-nhan'](khung)` (01b-dieu-huong.js
    `ganKhe`). Thiếu một trong hai đầu là tính năng có mã mà không có đường
    vào — đúng kiểu "có endpoint mà không có màn hình".
    """
    nhan = _src("21-nhan.js")
    assert "window.GAN_TAB = window.GAN_TAB || {};" in nhan
    assert 'GAN_TAB["cc-nhan"] = (el) => moQuanLyNhan(el);' in nhan
    assert 'data-gan="cc-nhan"' in (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")


def test_dau_hoi_thoai_chi_co_nhan_hoi_thoai():
    """Mục 6.3/6.4: nhãn khách KHÔNG nằm ở đầu hội thoại, chỉ ở Customer 360."""
    ht = _src("03-hoi-thoai.js")
    assert "${nhanHoiThoaiHtml(c)}" in ht
    assert "nhanKhachHtml" not in ht
    assert "${nhanKhachHtml(contact)}" in _src("04-khach-hang.js")
    nhan = _src("21-nhan.js")
    dau = nhan[nhan.index("function nhanHoiThoaiHtml"):nhan.index("function nhanKhachHtml")]
    assert 'data-nhan-them="hoi_thoai"' in dau and "+ Nhãn" in dau


def test_o_chon_chi_lay_nhan_dang_dung_va_chip_nhan_da_ngung_hien_xam():
    nhan = _src("21-nhan.js")
    # Ô chọn đọc hai đường chỉ trả nhãn ĐANG DÙNG.
    assert 'duong: "/nhan/khach"' in nhan and 'duong: "/nhan/hoi-thoai"' in nhan
    assert "is-ngung" in nhan[nhan.index("function chipNhan"):]
    css = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")
    assert ".nhan.is-ngung" in css and ".nhan--mau" in css
    # Màu vào `style` phải qua bộ lọc #rrggbb.
    assert "_mauNhan(n.mau)" in nhan


def test_khong_con_o_go_nhan_chu_tu_do():
    tat_ca = "".join(p.read_text(encoding="utf-8") for p in SRC.glob("*.js"))
    assert "contact-tag-form" not in tat_ca
    assert 'name: "nhan", label: "Nhãn", required: true' not in tat_ca
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    for ten in ('name="nhan_co"', 'name="nhan_khong"', 'name="hd_gan_nhan"'):
        assert ten not in html


def test_bieu_mau_quy_tac_tach_hai_loai_nhan():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    for ten, loai in (("nhan_hoi_thoai_co", "hoi_thoai"), ("nhan_hoi_thoai_khong", "hoi_thoai"),
                      ("nhan_khach_co", "khach"), ("nhan_khach_khong", "khach"),
                      ("hd_gan_nhan_hoi_thoai", "hoi_thoai"), ("hd_gan_nhan_khach", "khach")):
        assert f'<select name="{ten}" data-qt-nhan="{loai}">' in html, ten
    td = _src("15-tu-dong.js")
    assert 'loai: "gan_nhan_khach", nhan_id' in td and 'loai: "gan_nhan_hoi_thoai", nhan_id' in td
