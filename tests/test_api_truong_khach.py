"""
API trường khách tuỳ biến — chạy thật trên Postgres.

Ràng buộc nguy hiểm nhất ở đây là XOÁ TRƯỜNG.

Xoá định nghĩa mà để giá trị nằm lại trong `contacts.profile` là dữ liệu cá
nhân không còn hiện ở đâu trên màn hình, không ai gỡ được, và không ai biết
mình đang giữ. Với Nghị định 13/2023/NĐ-CP thì đó không phải bất tiện, đó
là giữ dữ liệu quá hạn trong im lặng.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
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
    from agent.api.contacts import router, router_vo_chu
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.migrations.runner import apply_all

    app = FastAPI()
    app.include_router(router)
    app.include_router(router_vo_chu)
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
        await conn.set_type_codec("jsonb", encoder=json.dumps,
                                  decoder=json.loads, schema="pg_catalog")
        try:
            return await conn.fetchval(cau, *args)
        finally:
            await conn.close()

    return asyncio.run(chay())


def _sep() -> dict:
    return nguoi_thu("khach.doc", "khach.sua", "cau_hinh.sua",
                     id=SEP_ID, ten="sep")


def _tao_khach(url: str, ten: str = "Chị Hoa"):
    return _sql(url, "INSERT INTO contacts (display_name) VALUES ($1) "
                     "RETURNING id", ten)


LOAI_DA = {"ma": "loai_da", "nhan": "Loại da", "kieu": "chon",
           "lua_chon": ["dầu", "khô", "hỗn hợp"], "hien_danh_sach": True}


def test_them_liet_ke_sua_truong(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        assert khach.post("/api/truong-khach", json=LOAI_DA).status_code == 201

        d = khach.get("/api/truong-khach").json()
        assert [t["ma"] for t in d["truong"]] == ["loai_da"]
        assert d["truong"][0]["lua_chon"] == ["dầu", "khô", "hỗn hợp"]
        # Danh mục kiểu phải đi kèm, có nhãn tiếng Việt — dashboard vẽ ô
        # nhập theo nó.
        assert {k["ma"] for k in d["kieu"]} == set(
            __import__("agent.core.truong_khach", fromlist=["x"]).KIEU)

        r = khach.put("/api/truong-khach/loai_da", json={
            "nhan": "Loại da (khảo sát)", "lua_chon": ["dầu", "khô"],
            "bat_buoc": True, "hien_danh_sach": False, "thu_tu": 5})
        assert r.status_code == 200, r.text
        assert khach.get("/api/truong-khach").json()["truong"][0]["nhan"] \
            == "Loại da (khảo sát)"


def test_ma_sai_dinh_dang_thi_422(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        r = khach.post("/api/truong-khach",
                       json=dict(LOAI_DA, ma="Loại Da"))
        assert r.status_code == 422
        assert "chữ thường" in r.text


def test_kieu_chon_khong_co_lua_chon_thi_422(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        r = khach.post("/api/truong-khach",
                       json=dict(LOAI_DA, lua_chon=[]))
        assert r.status_code == 422


def test_trung_ma_thi_409(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        assert khach.post("/api/truong-khach", json=LOAI_DA).status_code == 201
        assert khach.post("/api/truong-khach", json=LOAI_DA).status_code == 409


def test_ghi_gia_tri_va_kiem_kieu_o_MAY_CHU(csdl_kiem_thu):
    """
    Dashboard vẽ ô chọn, nhưng máy chủ vẫn phải từ chối giá trị ngoài danh
    sách — một tab cũ còn mở là đủ để gửi lên thứ không còn hợp lệ.
    """
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        khach.post("/api/truong-khach", json=LOAI_DA)
        kh = _tao_khach(csdl_kiem_thu)

        r = khach.put(f"/api/contacts/{kh}/truong",
                      json={"gia_tri": {"loai_da": "dầu"}})
        assert r.status_code == 200, r.text
        assert r.json()["profile"]["loai_da"] == "dầu"

        r = khach.put(f"/api/contacts/{kh}/truong",
                      json={"gia_tri": {"loai_da": "da cá sấu"}})
        assert r.status_code == 422
        assert "dầu" in r.text, "thông báo phải nói ra danh sách hợp lệ"
        # Và giá trị cũ KHÔNG bị đụng tới.
        assert _sql(csdl_kiem_thu,
                    "SELECT profile->>'loai_da' FROM contacts WHERE id=$1",
                    kh) == "dầu"


def test_khoa_la_thi_422_chu_khong_bo_qua(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        kh = _tao_khach(csdl_kiem_thu)
        r = khach.put(f"/api/contacts/{kh}/truong",
                      json={"gia_tri": {"truong_khong_ton_tai": "x"}})
        assert r.status_code == 422
        assert "truong_khong_ton_tai" in r.text


def test_sua_mot_o_khong_xoa_cac_o_con_lai(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        khach.post("/api/truong-khach", json=LOAI_DA)
        khach.post("/api/truong-khach", json={
            "ma": "ghi_chu", "nhan": "Ghi chú", "kieu": "chu"})
        kh = _tao_khach(csdl_kiem_thu)
        khach.put(f"/api/contacts/{kh}/truong", json={
            "gia_tri": {"loai_da": "khô", "ghi_chu": "hay hỏi giá"}})

        khach.put(f"/api/contacts/{kh}/truong",
                  json={"gia_tri": {"ghi_chu": "đã chốt đơn"}})
        ho_so = _sql(csdl_kiem_thu,
                     "SELECT profile FROM contacts WHERE id=$1", kh)
        if isinstance(ho_so, str):
            ho_so = json.loads(ho_so)
        assert ho_so == {"loai_da": "khô", "ghi_chu": "đã chốt đơn"}


def test_gui_o_RONG_thi_xoa_o_do(csdl_kiem_thu):
    """
    Không xoá được ô đã điền nhầm thì người dùng sẽ điền một dấu chấm vào
    cho xong — và dữ liệu rác trông hệt dữ liệu thật.
    """
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        khach.post("/api/truong-khach", json={
            "ma": "ghi_chu", "nhan": "Ghi chú", "kieu": "chu"})
        kh = _tao_khach(csdl_kiem_thu)
        khach.put(f"/api/contacts/{kh}/truong",
                  json={"gia_tri": {"ghi_chu": "nhầm"}})
        khach.put(f"/api/contacts/{kh}/truong",
                  json={"gia_tri": {"ghi_chu": ""}})
        ho_so = _sql(csdl_kiem_thu,
                     "SELECT profile FROM contacts WHERE id=$1", kh)
        if isinstance(ho_so, str):
            ho_so = json.loads(ho_so)
        assert ho_so == {}


def test_xoa_truong_con_gia_tri_thi_409_va_NOI_RA_SO(csdl_kiem_thu):
    """
    "Bạn có chắc không" là câu hỏi không mang thông tin — người ta bấm OK
    theo phản xạ. "3 hồ sơ đang có giá trị" thì họ dừng lại.
    """
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        khach.post("/api/truong-khach", json=LOAI_DA)
        for ten in ("A", "B", "C"):
            kh = _tao_khach(csdl_kiem_thu, ten)
            khach.put(f"/api/contacts/{kh}/truong",
                      json={"gia_tri": {"loai_da": "dầu"}})

        r = khach.delete("/api/truong-khach/loai_da")
        assert r.status_code == 409
        assert "3 hồ sơ" in r.text
        # Chưa xoá gì cả.
        assert _sql(csdl_kiem_thu,
                    "SELECT count(*) FROM truong_khach") == 1


def test_xoa_truong_keo_theo_gia_tri_khi_da_khang_dinh(csdl_kiem_thu):
    """
    Giá trị nằm lại sau khi xoá định nghĩa là dữ liệu cá nhân không hiện ở
    đâu, không ai gỡ được, và không ai biết mình đang giữ.
    """
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        khach.post("/api/truong-khach", json=LOAI_DA)
        kh = _tao_khach(csdl_kiem_thu)
        khach.put(f"/api/contacts/{kh}/truong",
                  json={"gia_tri": {"loai_da": "dầu"}})

        r = khach.delete("/api/truong-khach/loai_da?xoa_ca_gia_tri=true")
        assert r.status_code == 200, r.text
        assert r.json()["so_ho_so_da_xoa_gia_tri"] == 1

        ho_so = _sql(csdl_kiem_thu,
                     "SELECT profile FROM contacts WHERE id=$1", kh)
        if isinstance(ho_so, str):
            ho_so = json.loads(ho_so)
        assert ho_so == {}, "giá trị mồ côi vẫn còn nằm trong hồ sơ khách"


def test_them_truong_can_quyen_cau_hinh_sua(csdl_kiem_thu):
    chi_doc = nguoi_thu("khach.doc", "khach.sua", id=SEP_ID, ten="sep")
    with TestClient(_app(csdl_kiem_thu, chi_doc)) as khach:
        assert khach.get("/api/truong-khach").status_code == 200
        r = khach.post("/api/truong-khach", json=LOAI_DA)
        assert r.status_code == 403
        assert "cau_hinh.sua" in r.json()["detail"]
