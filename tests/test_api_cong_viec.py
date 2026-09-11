"""
API công việc — chạy thật trên Postgres.

Ràng buộc quan trọng nhất: agent chuyển người thì CÓ AI ĐÓ được giao việc.

Trước khối này, agent chuyển người xong chỉ để lại một dòng nhật ký và một
hội thoại đổi màu. Nếu người trực đang bận lúc ấy thì việc không nằm ở đâu,
và nó chỉ được nhớ tới nếu tình cờ có ai mở đúng hội thoại.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from conftest import nguoi_thu  # noqa: E402

LUOC_DO = ROOT / "agent" / "schema.sql"
SEP_ID = "00000000-0000-0000-0000-0000000000aa"


def _app(url: str, nguoi: dict) -> FastAPI:
    import asyncpg

    from agent import db
    from agent.api.cong_viec import router
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
        db._pool = await asyncpg.create_pool(url, min_size=1, max_size=3,
                                             init=_codec)
        async with db._pool.acquire() as conn:
            await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
            await apply_all(conn)
            await conn.execute(
                "INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, ho_ten) "
                "VALUES ($1,'sep','x','Sếp') ON CONFLICT DO NOTHING", SEP_ID)

    @app.on_event("shutdown")
    async def _dong():
        if db._pool is not None:
            await db._pool.close()
            db._pool = None

    return app


def _sql(url: str, cau: str, *args):
    import asyncpg

    async def chay():
        conn = await asyncpg.connect(url)
        try:
            return await conn.fetchval(cau, *args)
        finally:
            await conn.close()

    return asyncio.run(chay())


def _dung_luoc_do(url: str) -> None:
    """
    Dựng lược đồ TRƯỚC khi test chèn gì.

    Fixture `csdl_kiem_thu` chỉ tạo một CSDL rỗng; lược đồ do startup của app
    dựng. Nhưng vài test cần tạo nhân viên TRƯỚC khi dựng app (để truyền
    người đăng nhập vào), nên phải dựng lược đồ ở đây. Startup chạy lại
    cũng không sao: `schema.sql` dùng IF NOT EXISTS và runner bỏ qua
    migration đã áp dụng.
    """
    import asyncpg

    from agent.migrations.runner import apply_all

    async def chay():
        conn = await asyncpg.connect(url)
        await conn.set_type_codec("jsonb", encoder=json.dumps,
                                  decoder=json.loads, schema="pg_catalog")
        try:
            await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
            await apply_all(conn)
        finally:
            await conn.close()

    asyncio.run(chay())


async def _dung_hoi_thoai(conn, *, ext: str, ten_khach: str = "Khách"):
    """
    Dựng đủ chuỗi tài khoản kênh -> khách -> danh tính -> hội thoại.

    `conversations` có ba khoá ngoại NOT NULL (`account_id`, `contact_id`,
    `contact_point_id`). Chèn thiếu bất kỳ cái nào cũng ném — và ném ở đây
    là ném trong test, may hơn nhiều so với ném trên đường xử lý tin khách.
    """
    tk = await conn.fetchval(
        "INSERT INTO channel_accounts (channel, display_name, status) "
        "VALUES ('webchat','Web','active') RETURNING id")
    kh = await conn.fetchval(
        "INSERT INTO contacts (display_name) VALUES ($1) RETURNING id",
        ten_khach)
    diem = await conn.fetchval(
        "INSERT INTO contact_points (contact_id, channel_account_id, "
        "external_user_id) VALUES ($1,$2,$3) RETURNING id", kh, tk, ext)
    return await conn.fetchval(
        "INSERT INTO conversations (account_id, channel, external_id, "
        "customer_ref, customer_name, contact_id, contact_point_id) "
        "VALUES ($1,'webchat',$2,$2,$3,$4,$5) RETURNING id",
        tk, ext, ten_khach, kh, diem)


def _sep() -> dict:
    return nguoi_thu("cong_viec.doc", "cong_viec.sua", "cong_viec.giao",
                     "cong_viec.xem_tat_ca", id=SEP_ID, ten="sep")


def _nv(url: str, ten: str = "thao") -> dict:
    _dung_luoc_do(url)
    uid = _sql(url, "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, "
                    "ho_ten) VALUES ($1,'x',$1) RETURNING id", ten)
    return nguoi_thu("cong_viec.doc", "cong_viec.sua", id=str(uid), ten=ten)


def test_tao_liet_ke_va_doi_trang_thai(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        r = khach.post("/api/cong-viec", json={
            "tieu_de": "Gọi lại chị Hoa", "mo_ta": "Hỏi về serum",
            "uu_tien": "cao"})
        assert r.status_code == 201, r.text
        vid = r.json()["id"]

        d = khach.get("/api/cong-viec").json()
        assert len(d["cong_viec"]) == 1
        assert d["cong_viec"][0]["tieu_de"] == "Gọi lại chị Hoa"
        # Danh mục trạng thái/ưu tiên đi kèm, có nhãn tiếng Việt.
        assert {t["ma"] for t in d["trang_thai"]} == {"moi", "dang_lam", "xong", "huy"}

        r = khach.put(f"/api/cong-viec/{vid}", json={"trang_thai": "xong"})
        assert r.status_code == 200, r.text
        assert _sql(csdl_kiem_thu,
                    "SELECT xong_luc IS NOT NULL FROM cong_viec WHERE id=$1",
                    vid) is True


def test_danh_dau_lam_lai_thi_xoa_xong_luc(csdl_kiem_thu):
    """
    Ràng buộc CSDL là `(trang_thai='xong') = (xong_luc IS NOT NULL)`. Mở
    lại việc mà quên xoá `xong_luc` thì Postgres ném — và người dùng thấy
    một 500 không nói gì.
    """
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        vid = khach.post("/api/cong-viec",
                         json={"tieu_de": "Kiểm kho"}).json()["id"]
        khach.put(f"/api/cong-viec/{vid}", json={"trang_thai": "xong"})
        r = khach.put(f"/api/cong-viec/{vid}", json={"trang_thai": "dang_lam"})
        assert r.status_code == 200, r.text
        assert _sql(csdl_kiem_thu,
                    "SELECT xong_luc FROM cong_viec WHERE id=$1", vid) is None


def test_trang_thai_la_thi_422(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        vid = khach.post("/api/cong-viec",
                         json={"tieu_de": "Việc thử"}).json()["id"]
        r = khach.put(f"/api/cong-viec/{vid}", json={"trang_thai": "dang_treo"})
        assert r.status_code == 422


def test_giao_cho_nguoi_khac_can_quyen_rieng(csdl_kiem_thu):
    """
    Không tách quyền thì bất kỳ ai tạo được việc cũng đẩy được việc sang
    đầu người khác, và màn Công việc của họ đầy thứ họ không nhận.
    """
    nv = _nv(csdl_kiem_thu)
    with TestClient(_app(csdl_kiem_thu, nv)) as khach:
        # Tạo cho CHÍNH MÌNH: được.
        r = khach.post("/api/cong-viec", json={
            "tieu_de": "Việc của tôi", "nguoi_nhan": nv["id"]})
        assert r.status_code == 201, r.text
        # Đẩy sang người khác: không.
        r = khach.post("/api/cong-viec", json={
            "tieu_de": "Việc của sếp", "nguoi_nhan": SEP_ID})
        assert r.status_code == 403
        assert "cong_viec.giao" in r.json()["detail"]


def test_tu_nhan_viec_chua_ai_nhan_thi_khong_can_quyen_giao(csdl_kiem_thu):
    """
    Việc do agent đẩy sang luôn ra đời chưa giao. Đòi quyền `giao` để tự
    nhận nó là khoá đúng thao tác mà cả khối này sinh ra để khuyến khích.
    """
    nv = _nv(csdl_kiem_thu)
    vid = _sql(csdl_kiem_thu,
               "INSERT INTO cong_viec (tieu_de, nguon) "
               "VALUES ('Khách cần người trả lời', 'agent') RETURNING id")
    with TestClient(_app(csdl_kiem_thu, nv)) as khach:
        r = khach.put(f"/api/cong-viec/{vid}",
                      json={"nguoi_nhan": nv["id"], "trang_thai": "dang_lam"})
        assert r.status_code == 200, r.text


def test_khong_gianh_duoc_viec_cua_nguoi_khac(csdl_kiem_thu):
    nv = _nv(csdl_kiem_thu)
    nv2 = _nv(csdl_kiem_thu, "minh")
    vid = _sql(csdl_kiem_thu,
               "INSERT INTO cong_viec (tieu_de, nguoi_nhan) "
               "VALUES ('Việc của Minh', $1) RETURNING id", nv2["id"])
    with TestClient(_app(csdl_kiem_thu, nv)) as khach:
        r = khach.put(f"/api/cong-viec/{vid}", json={"nguoi_nhan": nv["id"]})
        assert r.status_code == 403
        assert "đã có người nhận" in r.json()["detail"]


def test_pham_vi_nhan_vien_chi_thay_viec_lien_quan(csdl_kiem_thu):
    nv = _nv(csdl_kiem_thu)
    nv2 = _nv(csdl_kiem_thu, "minh")
    _sql(csdl_kiem_thu, "INSERT INTO cong_viec (tieu_de, nguoi_nhan) "
                        "VALUES ('Của Thảo', $1)", nv["id"])
    _sql(csdl_kiem_thu, "INSERT INTO cong_viec (tieu_de, nguoi_nhan) "
                        "VALUES ('Của Minh', $1)", nv2["id"])
    _sql(csdl_kiem_thu, "INSERT INTO cong_viec (tieu_de, nguon) "
                        "VALUES ('Chưa giao ai', 'agent')")
    with TestClient(_app(csdl_kiem_thu, nv)) as khach:
        ten = {v["tieu_de"] for v in khach.get("/api/cong-viec").json()["cong_viec"]}
        assert ten == {"Của Thảo", "Chưa giao ai"}


def test_viec_chua_xong_len_truoc_va_han_gan_len_dau(csdl_kiem_thu):
    """
    Việc KHÔNG có hạn không được chen lên đầu — nó không gấp hơn một việc
    phải xong chiều nay.
    """
    bay_gio = datetime.now(timezone.utc)
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        khach.post("/api/cong-viec", json={"tieu_de": "Không hạn"})
        khach.post("/api/cong-viec", json={
            "tieu_de": "Hạn xa", "han": (bay_gio + timedelta(days=7)).isoformat()})
        khach.post("/api/cong-viec", json={
            "tieu_de": "Hạn gần", "han": (bay_gio + timedelta(hours=2)).isoformat()})
        xong = khach.post("/api/cong-viec",
                          json={"tieu_de": "Đã xong"}).json()["id"]
        khach.put(f"/api/cong-viec/{xong}", json={"trang_thai": "xong"})

        ds = [v["tieu_de"] for v in khach.get("/api/cong-viec").json()["cong_viec"]]
        assert ds[:3] == ["Hạn gần", "Hạn xa", "Không hạn"]
        assert ds[-1] == "Đã xong"


def test_co_qua_han_trong_ket_qua(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        qua = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        vid = khach.post("/api/cong-viec", json={
            "tieu_de": "Quá hạn rồi", "han": qua}).json()["id"]
        ds = {v["id"]: v for v in khach.get("/api/cong-viec").json()["cong_viec"]}
        assert ds[vid]["qua_han"] is True

        khach.put(f"/api/cong-viec/{vid}", json={"trang_thai": "xong"})
        ds = {v["id"]: v for v in khach.get("/api/cong-viec").json()["cong_viec"]}
        assert ds[vid]["qua_han"] is False, "việc xong rồi không còn quá hạn"


def test_thieu_quyen_doc_thi_403(csdl_kiem_thu):
    khong = nguoi_thu(id=SEP_ID, ten="sep")
    with TestClient(_app(csdl_kiem_thu, khong)) as khach:
        r = khach.get("/api/cong-viec")
        assert r.status_code == 403
        assert "cong_viec.doc" in r.json()["detail"]


# =====================================================================
#  Task tự sinh khi agent chuyển người
# =====================================================================

def test_agent_chuyen_nguoi_thi_SINH_MOT_VIEC(csdl_kiem_thu):
    from agent.core import cong_viec as cv

    async def chay(url):
        import asyncpg

        from agent import db
        from agent.migrations.runner import apply_all

        async def _codec(conn):
            await conn.set_type_codec("jsonb", encoder=json.dumps,
                                      decoder=json.loads, schema="pg_catalog")

        pool = await asyncpg.create_pool(url, min_size=1, max_size=2, init=_codec)
        cu = db._pool
        db._pool = pool
        try:
            async with pool.acquire() as conn:
                await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
                await apply_all(conn)
                cid = await _dung_hoi_thoai(conn, ext="ext-1",
                                            ten_khach="Chị Hoa")

            mot = await cv.tao_tu_chuyen_nguoi(
                cid, ly_do="Khách hỏi về thuốc trị mụn", ten_khach="Chị Hoa")
            # Gọi LẠI: cùng hội thoại, không được đẻ việc thứ hai.
            hai = await cv.tao_tu_chuyen_nguoi(
                cid, ly_do="Khách nhắn tiếp", ten_khach="Chị Hoa")

            async with pool.acquire() as conn:
                so = await conn.fetchval("SELECT count(*) FROM cong_viec")
                v = await conn.fetchrow("SELECT * FROM cong_viec LIMIT 1")
            return mot, hai, so, dict(v)
        finally:
            db._pool = cu
            await pool.close()

    mot, hai, so, v = asyncio.run(chay(csdl_kiem_thu))
    assert mot is not None
    assert hai is None, (
        "hội thoại đã có việc đang mở mà vẫn đẻ việc thứ hai — cuối ngày màn "
        "Công việc sẽ có bốn mươi dòng cho cùng một chuyện")
    assert so == 1
    assert v["nguon"] == "agent"
    assert v["nguoi_nhan"] is None, "việc tự sinh phải là việc CHƯA GIAO"
    assert v["uu_tien"] == "cao"
    assert "Chị Hoa" in v["tieu_de"]
    assert "thuốc trị mụn" in v["mo_ta"]


def test_viec_tu_sinh_lai_duoc_sau_khi_viec_cu_da_xong(csdl_kiem_thu):
    """
    Chốt "một việc mỗi hội thoại" chỉ áp cho việc ĐANG MỞ. Khách quay lại
    tuần sau với chuyện khác thì phải sinh việc mới — không thì lần thứ hai
    rơi vào im lặng y như trước khi có khối này.
    """
    from agent.core import cong_viec as cv

    async def chay(url):
        import asyncpg

        from agent import db
        from agent.migrations.runner import apply_all

        async def _codec(conn):
            await conn.set_type_codec("jsonb", encoder=json.dumps,
                                      decoder=json.loads, schema="pg_catalog")

        pool = await asyncpg.create_pool(url, min_size=1, max_size=2, init=_codec)
        cu = db._pool
        db._pool = pool
        try:
            async with pool.acquire() as conn:
                await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
                await apply_all(conn)
                cid = await _dung_hoi_thoai(conn, ext="ext-2")

            await cv.tao_tu_chuyen_nguoi(cid, ly_do="lần một")
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE cong_viec SET trang_thai='xong', xong_luc=now()")
            lan_hai = await cv.tao_tu_chuyen_nguoi(cid, ly_do="lần hai")
            async with pool.acquire() as conn:
                return lan_hai, await conn.fetchval("SELECT count(*) FROM cong_viec")
        finally:
            db._pool = cu
            await pool.close()

    lan_hai, so = asyncio.run(chay(csdl_kiem_thu))
    assert lan_hai is not None
    assert so == 2
