"""
Sổ yêu cầu của chủ thể dữ liệu — Luật BVDLCN 91/2025, NĐ 356/2025 Điều 5.

Ràng buộc then chốt: hạn tính đúng (về phía SỚM khi không chắc), quá hạn thì
nói ra, và sổ không giữ chính dữ liệu nó đang giúp xoá.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.core import yeu_cau_chu_the as yc
from conftest import nguoi_thu

ROOT = Path(__file__).resolve().parent.parent
VN = timezone(timedelta(hours=7))
UID = UUID("00000000-0000-0000-0000-000000000001")


def vn(y, m, d, h=10, mi=0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=VN)


# ------------------------------------------------------------------ hạn (thuần)

def test_phan_hoi_hai_ngay_lam_viec_bo_cuoi_tuan():
    # 30.10.2026 là thứ Sáu: hai ngày làm việc sau là thứ Hai 2.11 và thứ Ba 3.11.
    assert vn(2026, 10, 30).isoweekday() == 5
    assert yc.han_phan_hoi(vn(2026, 10, 30, 23, 50)) == vn(2026, 11, 4, 0)
    # Nhận thứ Bảy: thứ Hai, thứ Ba.
    assert yc.han_phan_hoi(vn(2026, 10, 31)) == vn(2026, 11, 4, 0)
    # Nhận thứ Hai: thứ Ba, thứ Tư.
    assert yc.han_phan_hoi(vn(2026, 11, 2)) == vn(2026, 11, 5, 0)


def test_phan_hoi_tinh_theo_GIO_VIET_NAM_khong_theo_UTC():
    """23:30 thứ Sáu giờ VN là 16:30 UTC cùng ngày — ngày nhận vẫn là thứ Sáu."""
    utc = datetime(2026, 10, 30, 16, 30, tzinfo=timezone.utc)
    assert yc.han_phan_hoi(utc) == vn(2026, 11, 4, 0)
    # 00:30 thứ Bảy giờ VN là 17:30 UTC thứ Sáu — ngày nhận là thứ Bảy.
    assert yc.han_phan_hoi(datetime(2026, 10, 30, 17, 30, tzinfo=timezone.utc)) == vn(2026, 11, 4, 0)


@pytest.mark.parametrize("loai,ngay,ngay_3", [
    ("xem", 10, 15), ("sua", 10, 15), ("xoa", 20, 30),
    ("rut_dong_y", 15, 20), ("han_che", 15, 20), ("phan_doi", 15, 20), ("bao_ve", 15, 15),
])
def test_han_xu_ly_theo_nd_356_dieu_5(loai, ngay, ngay_3):
    # Nhận 15:00 ngày 2.11 → hạn là CUỐI ngày (2.11 + N), tức 00:00 ngày (3.11 + N).
    nhan = vn(2026, 11, 2, 15)
    assert yc.han_xu_ly(loai, nhan) - vn(2026, 11, 3, 0) == timedelta(days=ngay)
    assert yc.han_xu_ly(loai, nhan, co_ben_thu_ba=True) - vn(2026, 11, 3, 0) == timedelta(days=ngay_3)


def test_tinh_trang():
    r = {"trang_thai": "moi", "han_phan_hoi": vn(2026, 11, 4, 0), "han_xu_ly": vn(2026, 11, 23, 0),
         "gia_han_den": None}
    assert yc.tinh_trang(r, vn(2026, 11, 3)) == "dung_han"
    assert yc.tinh_trang(r, vn(2026, 11, 4, 0)) == "qua_han_phan_hoi"
    assert yc.tinh_trang({**r, "trang_thai": "da_phan_hoi"}, vn(2026, 11, 4, 1)) == "dung_han"
    assert yc.tinh_trang({**r, "trang_thai": "da_phan_hoi"}, vn(2026, 11, 21, 1)) == "sap_het_han"
    assert yc.tinh_trang(r, vn(2026, 11, 23, 0)) == "qua_han"
    assert yc.tinh_trang({**r, "gia_han_den": vn(2026, 12, 13)}, vn(2026, 11, 25)) != "qua_han"
    assert yc.tinh_trang({**r, "trang_thai": "da_xong"}, vn(2027, 1, 1)) == "xong"


def test_san_sang_qua_han_la_chan():
    from scripts.san_sang import CANH_BAO, CHAN, DU, doc_yeu_cau_chu_the as doc

    assert doc({"qua_han": 1, "qua_han_phan_hoi": 0, "sap_het_han": 0, "dang_mo": 1})["muc"] == CHAN
    assert doc({"qua_han": 0, "qua_han_phan_hoi": 2, "sap_het_han": 0, "dang_mo": 2})["muc"] == CHAN
    assert doc({"qua_han": 0, "qua_han_phan_hoi": 0, "sap_het_han": 1, "dang_mo": 1})["muc"] == CANH_BAO
    assert doc({"qua_han": 0, "qua_han_phan_hoi": 0, "sap_het_han": 0, "dang_mo": 0})["muc"] == DU
    # Không đọc được sổ thì KHÔNG được coi là "không có yêu cầu nào".
    assert doc(None)["muc"] == CANH_BAO


def test_muc_nay_co_trong_bang_san_sang():
    import inspect

    from scripts import san_sang

    assert "kiem_yeu_cau_chu_the" in inspect.getsource(san_sang.chay)


# ------------------------------------------------------------------ CSDL + API

def _app(url: str, nguoi: dict) -> FastAPI:
    from agent import db
    from agent.api.pdpd_api import router
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.migrations.runner import apply_all

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[nguoi_da_dang_nhap] = lambda: nguoi

    async def _codec(conn):
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

    @app.on_event("startup")
    async def _mo():
        db._pool = await asyncpg.create_pool(url, min_size=1, max_size=3, init=_codec)
        async with db._pool.acquire() as conn:
            await conn.execute((ROOT / "agent" / "schema.sql").read_text(encoding="utf-8"))
            await apply_all(conn)
            await conn.execute("INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, ho_ten) "
                               "VALUES ($1,'kt','x','kt') ON CONFLICT DO NOTHING", UID)

    @app.on_event("shutdown")
    async def _dong():
        if db._pool is not None:
            await db._pool.close()
            db._pool = None

    return app


def test_vong_doi_yeu_cau(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("khach.pii"))) as k:
        r = k.post("/api/pdpd/yeu-cau", json={"loai": "xoa", "sdt": "+84 967 627 336",
                                              "noi_dung": "xin xoá sau khi huỷ đơn"})
        assert r.status_code == 201, r.text
        y = r.json()
        assert y["co_dau_van_tay"] and y["trang_thai"] == "moi" and y["tinh_trang"] == "dung_han"

        # Route khai TRƯỚC /pdpd/{sdt}: "yeu-cau" không bị hiểu là số điện thoại.
        ds = k.get("/api/pdpd/yeu-cau").json()
        assert [x["id"] for x in ds["yeu_cau"]] == [y["id"]] and ds["dem"]["dang_mo"] == 1

        assert k.post(f"/api/pdpd/yeu-cau/{y['id']}/phan-hoi").json()["trang_thai"] == "da_phan_hoi"
        assert k.post(f"/api/pdpd/yeu-cau/{y['id']}/phan-hoi").status_code == 422

        # Gia hạn: một lần, tối đa 20 ngày cho xoá.
        assert k.post(f"/api/pdpd/yeu-cau/{y['id']}/gia-han",
                      json={"so_ngay": 21, "ly_do": "chờ ERP"}).status_code == 422
        r = k.post(f"/api/pdpd/yeu-cau/{y['id']}/gia-han", json={"so_ngay": 5, "ly_do": "chờ ERP mở lại"})
        assert r.status_code == 200 and r.json()["da_gia_han"]
        assert k.post(f"/api/pdpd/yeu-cau/{y['id']}/gia-han",
                      json={"so_ngay": 1, "ly_do": "lần hai"}).status_code == 422

        assert k.post(f"/api/pdpd/yeu-cau/{y['id']}/dong", json={"ket_qua": "đã xoá"}).json()["trang_thai"] == "da_xong"
        assert k.post(f"/api/pdpd/yeu-cau/{y['id']}/dong", json={"ket_qua": "x"}).status_code == 422
        assert k.get("/api/pdpd/yeu-cau").json()["yeu_cau"] == []
        assert len(k.get("/api/pdpd/yeu-cau?ca_da_xong=true").json()["yeu_cau"]) == 1


def test_khong_luu_so_dien_thoai(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("khach.pii"))) as k:
        k.post("/api/pdpd/yeu-cau", json={"loai": "xem", "sdt": "0967627336"})

    async def doc():
        conn = await asyncpg.connect(csdl_kiem_thu)
        try:
            return [dict(r) for r in await conn.fetch("SELECT * FROM yeu_cau_chu_the")]
        finally:
            await conn.close()
    for r in asyncio.run(doc()):
        assert not any("967627336" in str(v) for v in r.values())


def test_tu_choi_phai_co_can_cu(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("khach.pii"))) as k:
        y = k.post("/api/pdpd/yeu-cau", json={"loai": "xoa"}).json()
        assert k.post(f"/api/pdpd/yeu-cau/{y['id']}/dong", json={"tu_choi": True, "ket_qua": ""}).status_code == 422
        r = k.post(f"/api/pdpd/yeu-cau/{y['id']}/dong",
                   json={"tu_choi": True, "ket_qua": "đơn hàng giữ 10 năm — Luật Kế toán Điều 41"})
        assert r.json()["trang_thai"] == "tu_choi"


def test_nhan_luc_ghi_lui_va_qua_han(csdl_kiem_thu):
    """Khách nhắn 25 ngày trước mà hôm nay mới vào sổ: đã QUÁ HẠN, không được tặng ngày."""
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("khach.pii"))) as k:
        cu = (datetime.now(VN) - timedelta(days=25)).isoformat()
        y = k.post("/api/pdpd/yeu-cau", json={"loai": "xoa", "nhan_luc": cu}).json()
        assert y["tinh_trang"] == "qua_han"
        assert k.get("/api/pdpd/yeu-cau").json()["dem"]["qua_han"] == 1
        # Quá hạn rồi thì không gia hạn để hợp thức hoá.
        assert k.post(f"/api/pdpd/yeu-cau/{y['id']}/gia-han",
                      json={"so_ngay": 5, "ly_do": "muộn rồi"}).status_code == 422
        assert k.post("/api/pdpd/yeu-cau", json={"loai": "xoa", "nhan_luc": "2026-11-01T08:00:00"}).status_code == 422
        tuong_lai = (datetime.now(VN) + timedelta(days=1)).isoformat()
        assert k.post("/api/pdpd/yeu-cau", json={"loai": "xoa", "nhan_luc": tuong_lai}).status_code == 422


def test_xoa_xong_thi_tu_dong_dong_yeu_cau_xoa(csdl_kiem_thu):
    from agent import db

    async def chay():
        from agent.migrations.runner import apply_all

        async def _codec(conn):
            await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
        db._pool = await asyncpg.create_pool(csdl_kiem_thu, min_size=1, max_size=2, init=_codec)
        try:
            async with db._pool.acquire() as conn:
                await conn.execute((ROOT / "agent" / "schema.sql").read_text(encoding="utf-8"))
                await apply_all(conn)
            a = await yc.tao(loai="xoa", sdt="0967 627 336")
            b = await yc.tao(loai="xem", sdt="0967627336")          # loại khác: không đóng
            c = await yc.tao(loai="xoa", sdt="0911111111")          # số khác: không đóng
            n = await yc.dong_yeu_cau_xoa_theo_sdt("0967627336", ket_qua="đã xoá")
            mo = {d["id"] for d in await yc.liet_ke()}
            return n, a["id"] in mo, b["id"] in mo, c["id"] in mo
        finally:
            await db._pool.close()
            db._pool = None

    assert asyncio.run(chay()) == (1, False, True, True)


def test_pdpd_xoa_chi_dong_so_khi_xoa_tron():
    """`da_xoa=False` (ERP còn dữ liệu) mà vẫn đóng sổ là ghi đã đáp ứng cho việc còn dở."""
    import inspect

    from agent.api import pdpd_api

    src = inspect.getsource(pdpd_api.pdpd_xoa)
    # Đóng khi xoá TRỌN, hoặc khi số không còn dữ liệu nào — KHÔNG đóng khi
    # xoá dở (da_xoa=False vì ERP còn dữ liệu, khong_con_du_lieu vắng).
    assert 'if kq.get("da_xoa") or kq.get("khong_con_du_lieu"):' in src
    assert "dong_yeu_cau_xoa_theo_sdt" in src


def test_quyen(csdl_kiem_thu):
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("hoi_thoai.doc"))) as k:
        assert k.get("/api/pdpd/yeu-cau").status_code == 403
        assert k.post("/api/pdpd/yeu-cau", json={"loai": "xoa"}).status_code == 403


# ------------------------------------------------------------------ bản nháp hồ sơ

@pytest.mark.parametrize("provider", ["gemini_api", "gemini", "vertex", "anthropic"])
def test_ho_so_luon_khai_chuyen_ra_nuoc_ngoai(monkeypatch, provider):
    """Không nhà cung cấp model nào đặt máy chủ ở Việt Nam — bản nháp nào cũng phải khai."""
    from agent.config import settings
    from scripts import sinh_ho_so_bvdlcn as h

    monkeypatch.setattr(settings, "llm_provider", provider)
    t = h.sinh()
    assert "## 6. Chuyển dữ liệu ra nước ngoài" in t and "- **CÓ.**" in t
    assert "Nhạy cảm" in t and "Điều 4 khoản 1 điểm d" in t
    assert "KHÔNG áp dụng" in t                    # miễn trừ DN nhỏ không áp khi có dữ liệu nhạy cảm
    assert "BẢN NHÁP" in t and "Không phải tư vấn pháp lý" in t


def test_ho_so_khong_in_bi_mat(monkeypatch):
    from agent.config import settings
    from scripts import sinh_ho_so_bvdlcn as h

    for khoa in ("gemini_api_key", "anthropic_api_key", "ghtk_token", "ghn_token"):
        monkeypatch.setattr(settings, khoa, f"BI-MAT-{khoa}-xyz")
    assert "BI-MAT-" not in h.sinh()


def test_ho_so_doc_cau_hinh_that(monkeypatch):
    from agent.config import settings
    from scripts import sinh_ho_so_bvdlcn as h

    monkeypatch.setattr(settings, "luu_hoi_thoai_ngay", 90)
    monkeypatch.setattr(settings, "shipping_provider", "ghtk")
    t = h.sinh()
    assert "**90 ngày**" in t and "Giao Hàng Tiết Kiệm" in t


def test_ho_so_khong_khai_bien_phap_khong_co():
    """Sao lưu hằng ngày chưa mã hoá — hồ sơ khai "mã hoá" là khai sai với cơ quan nhà nước."""
    from scripts import sao_luu, sinh_ho_so_bvdlcn as h
    import inspect

    if not any(k in inspect.getsource(sao_luu) for k in ("encrypt", "Fernet", "AESGCM", "gpg")):
        assert "Sao lưu mã hoá" not in h.sinh()
        assert "chưa mã hoá" in h.sinh()
