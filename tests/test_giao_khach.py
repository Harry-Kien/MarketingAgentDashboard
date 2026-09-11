"""
Giao khách cho nhân viên — chạy thật trên Postgres.

Ba ràng buộc ở đây, và cả ba đều hỏng im lặng nếu sai:

  Giao cho người không trả lời được  -> khách CHẾT CÂM: có chủ nên người
                                        khác không đụng vào, mà chủ thì
                                        không gửi được tin.
  Ghi cột mà mất lịch sử             -> sáu tháng sau không ai trả lời được
                                        "ai giao khách này, lúc nào".
  Chỉ số vô chủ lệch với bộ lọc      -> con số nói một đằng, danh sách hiện
                                        một nẻo, người ta thôi tin cả hai.
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
            # Người thao tác phải có thật: `contact_owner_history.actor_id`
            # có khoá ngoại, và dấu vết trỏ vào hư không thì không phải dấu
            # vết.
            await conn.execute(
                "INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, ho_ten) "
                "VALUES ($1, 'sep', 'x', 'Sếp') ON CONFLICT DO NOTHING", SEP_ID)

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


def _sep() -> dict:
    return nguoi_thu("khach.doc", "khach.giao", "khach.xem_tat_ca",
                     id=SEP_ID, ten="sep")


def _tao_nhan_vien(url: str, ten: str, tra_loi_duoc: bool):
    """Tạo nhân viên kèm vai trò có (hoặc không có) `hoi_thoai.tra_loi`."""
    nd = _sql(url,
              "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten) "
              "VALUES ($1, 'x', $1) RETURNING id", ten)
    vt = _sql(url, "INSERT INTO vai_tro (ten) VALUES ($1) RETURNING id",
              f"vai-{ten}")
    if tra_loi_duoc:
        _sql(url, "INSERT INTO vai_tro_quyen (vai_tro_id, quyen) "
                  "VALUES ($1, 'hoi_thoai.tra_loi')", vt)
    _sql(url, "INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id) "
              "VALUES ($1, $2)", nd, vt)
    return nd


def _tao_khach(url: str, ten: str):
    return _sql(url, "INSERT INTO contacts (display_name) VALUES ($1) "
                     "RETURNING id", ten)


def test_giao_khach_ghi_du_cot_lich_su_va_nhat_ky(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        nv = _tao_nhan_vien(csdl_kiem_thu, "thao", tra_loi_duoc=True)
        kh = _tao_khach(csdl_kiem_thu, "Chị Hoa")

        r = khach.put(f"/api/contacts/{kh}/chu-so-huu",
                      json={"owner_user_id": str(nv), "ly_do": "Thảo trực ca sáng"})
        assert r.status_code == 200, r.text

        assert _sql(csdl_kiem_thu,
                    "SELECT owner_user_id FROM contacts WHERE id = $1", kh) == nv
        assert _sql(csdl_kiem_thu,
                    "SELECT count(*) FROM contact_owner_history "
                    "WHERE contact_id = $1 AND owner_user_id = $2", kh, nv) == 1
        assert _sql(csdl_kiem_thu,
                    "SELECT count(*) FROM events WHERE kind = 'khach.giao'") == 1


def test_giao_cho_nguoi_khong_tra_loi_duoc_thi_422(csdl_kiem_thu):
    """
    Khách chết câm: có chủ nên người khác không đụng vào, mà chủ thì không
    gửi được tin. Không chặn ở đây thì nó không hỏng — nó chỉ im.
    """
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        ke_toan = _tao_nhan_vien(csdl_kiem_thu, "ketoan", tra_loi_duoc=False)
        kh = _tao_khach(csdl_kiem_thu, "Chị Mai")

        r = khach.put(f"/api/contacts/{kh}/chu-so-huu",
                      json={"owner_user_id": str(ke_toan), "ly_do": "giao nhầm"})
        assert r.status_code == 422, r.text
        assert "hoi_thoai.tra_loi" in r.text
        assert _sql(csdl_kiem_thu,
                    "SELECT owner_user_id FROM contacts WHERE id = $1", kh) is None


def test_thu_hoi_cung_ghi_lich_su(csdl_kiem_thu):
    """
    Thu hồi là một sự kiện thật. Không ghi thì khoảng trống giữa hai lần
    giao trở nên vô hình, và "từ lúc nào khách này không ai phụ trách" là
    câu hỏi không trả lời được.
    """
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        nv = _tao_nhan_vien(csdl_kiem_thu, "minh", tra_loi_duoc=True)
        kh = _tao_khach(csdl_kiem_thu, "Anh Nam")
        khach.put(f"/api/contacts/{kh}/chu-so-huu",
                  json={"owner_user_id": str(nv), "ly_do": "giao ban đầu"})

        r = khach.delete(f"/api/contacts/{kh}/chu-so-huu",
                         params={"ly_do": "Minh nghỉ phép dài"})
        assert r.status_code == 200, r.text
        assert _sql(csdl_kiem_thu,
                    "SELECT owner_user_id FROM contacts WHERE id = $1", kh) is None
        assert _sql(csdl_kiem_thu,
                    "SELECT count(*) FROM contact_owner_history "
                    "WHERE contact_id = $1", kh) == 2


def test_lich_su_tra_theo_thu_tu_moi_truoc(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        a = _tao_nhan_vien(csdl_kiem_thu, "a", tra_loi_duoc=True)
        b = _tao_nhan_vien(csdl_kiem_thu, "b", tra_loi_duoc=True)
        kh = _tao_khach(csdl_kiem_thu, "Chị Vân")
        khach.put(f"/api/contacts/{kh}/chu-so-huu",
                  json={"owner_user_id": str(a), "ly_do": "giao cho a"})
        khach.put(f"/api/contacts/{kh}/chu-so-huu",
                  json={"owner_user_id": str(b), "ly_do": "chuyển sang b"})

        ds = khach.get(f"/api/contacts/{kh}/chu-so-huu/lich-su").json()["lich_su"]
        assert [d["ly_do"] for d in ds] == ["chuyển sang b", "giao cho a"]
        assert ds[0]["owner_ho_ten"] == "b"
        assert ds[0]["actor_ten_dang_nhap"] == "sep"


def test_khach_khong_ton_tai_thi_404(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        la = "00000000-0000-0000-0000-0000000000ff"
        r = khach.put(f"/api/contacts/{la}/chu-so-huu",
                      json={"owner_user_id": SEP_ID, "ly_do": "không có khách này"})
        assert r.status_code == 404


def test_thieu_quyen_giao_thi_403(csdl_kiem_thu):
    chi_doc = nguoi_thu("khach.doc", id=SEP_ID, ten="sep")
    with TestClient(_app(csdl_kiem_thu, chi_doc)) as khach:
        kh = _tao_khach(csdl_kiem_thu, "Chị Tâm")
        r = khach.put(f"/api/contacts/{kh}/chu-so-huu",
                      json={"owner_user_id": SEP_ID, "ly_do": "thử"})
        assert r.status_code == 403
        assert "khach.giao" in r.json()["detail"]


def test_chi_so_vo_chu_dung_cung_dinh_nghia_voi_bo_loc(csdl_kiem_thu):
    """
    Chỉ số và bộ lọc phải đếm CÙNG một tập.

    Hai định nghĩa lệch nhau là con số nói một đằng, danh sách hiện một nẻo
    — và người ta thôi tin cả hai, rồi thôi nhìn cả hai.
    """
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        nv = _tao_nhan_vien(csdl_kiem_thu, "thao", tra_loi_duoc=True)
        _tao_khach(csdl_kiem_thu, "Vô chủ 1")
        _tao_khach(csdl_kiem_thu, "Vô chủ 2")
        co_chu = _tao_khach(csdl_kiem_thu, "Có chủ")
        khach.put(f"/api/contacts/{co_chu}/chu-so-huu",
                  json={"owner_user_id": str(nv), "ly_do": "giao"})

        d = khach.get("/api/khach-vo-chu").json()
        assert d["so"] == 2
        assert d["ngay_lau_nhat"] is not None
        assert len(d["khach"]) == 2
        assert {k["display_name"] for k in d["khach"]} == {"Vô chủ 1", "Vô chủ 2"}
