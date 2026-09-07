from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api import goi_ky_nang as api
from agent.api import routes
from agent.ky_nang import goi as g


def _app(quan_tri=True):
    app = FastAPI(); app.include_router(api.router)
    app.dependency_overrides[routes.bat_buoc_quan_tri] = (
        (lambda: {"ten_dang_nhap": "qt", "vai_tro": "quan_tri"}) if quan_tri else routes.bat_buoc_quan_tri)
    return app


def _goi(**doi):
    d = {"ten": "tu-van-da-nhay-cam", "phien_ban": "1.0.0",
         "mo_ta": "Tư vấn cho khách da nhạy cảm, hỏi tiền sử kích ứng trước.",
         "tu_khoa": ["da nhạy cảm"],
         "huong_dan": "Khi khách nói da nhạy cảm: hỏi đã từng kích ứng với gì, ưu tiên không hương liệu.",
         "cong_cu": [], "tai_lieu": []}
    d.update(doi); return d


@pytest.fixture
def kho(monkeypatch):
    goi_da_luu: dict[str, dict] = {}

    async def cai(tho, *, boi):
        x = g.doc_goi(tho); goi_da_luu[x.ten] = x.tho; return x
    async def bat_tat(ten, bat, *, boi):
        if ten not in goi_da_luu: raise g.GoiKhongTonTai(ten)
    async def xoa(ten, *, boi):
        if ten not in goi_da_luu: raise g.GoiKhongTonTai(ten)
        goi_da_luu.pop(ten); return True
    async def liet_ke(): return [{"ten": t, "phien_ban": v["phien_ban"], "bat": True, "so_cong_cu": 0, "so_tai_lieu": 0, "so_lan_7_ngay": 0, "so_loi_7_ngay": 0, "mo_ta": v["mo_ta"], "tu_khoa": v["tu_khoa"], "sua_luc": None} for t, v in goi_da_luu.items()]
    async def lich_su(ten): return [{"id": 1, "phien_ban": "0.9.0", "thay_luc": None, "thay_boi": "qt"}] if ten in goi_da_luu else []
    async def khoi_phuc(ten, id_lich_su, *, boi):
        if ten not in goi_da_luu or id_lich_su != 1: raise g.GoiKhongTonTai(ten)
        return g.doc_goi(goi_da_luu[ten])
    async def xuat(ten): return goi_da_luu.get(ten)
    async def liet_ke_kn(): return {"co_san": [{"ten": "tra_cuu_san_pham", "so_lan_7_ngay": 3, "so_loi_7_ngay": 0}], "plugin": [], "plugin_toi_da": 12}

    for ten, ham in [("cai", cai), ("bat_tat", bat_tat), ("xoa", xoa), ("liet_ke", liet_ke), ("lich_su", lich_su), ("khoi_phuc", khoi_phuc), ("xuat", xuat)]:
        monkeypatch.setattr(g, ten, ham)
    monkeypatch.setattr(api.kho_ky_nang, "liet_ke", liet_ke_kn)
    return goi_da_luu


def test_nhan_vien_403():
    assert TestClient(_app(False)).get("/api/goi-ky-nang").status_code in (401, 403)


def test_kiem_khong_ghi(kho):
    c = TestClient(_app())
    r = c.post("/api/goi-ky-nang/kiem", json=_goi())
    assert r.status_code == 200 and r.json()["hop_le"] is True and r.json()["tom_tat"]["tu_khoa"] == ["da nhạy cảm"]
    assert kho == {}
    r2 = c.post("/api/goi-ky-nang/kiem", json=_goi(phien_ban="x"))
    assert r2.status_code == 200 and r2.json()["hop_le"] is False and "phien_ban" in r2.json()["loi"]


def test_cai_liet_ke_xuat_xoa(kho):
    c = TestClient(_app())
    assert c.post("/api/goi-ky-nang", json=_goi()).status_code == 201
    d = c.get("/api/goi-ky-nang").json()
    assert d["goi"][0]["ten"] == "tu-van-da-nhay-cam" and d["cong_cu"][0]["ten"] == "tra_cuu_san_pham"
    x = c.get("/api/goi-ky-nang/tu-van-da-nhay-cam/xuat")
    assert x.status_code == 200 and g.doc_goi(x.json()).ten == "tu-van-da-nhay-cam"
    assert "attachment" in x.headers.get("content-disposition", "")
    assert c.delete("/api/goi-ky-nang/tu-van-da-nhay-cam").status_code == 204
    assert c.get("/api/goi-ky-nang/tu-van-da-nhay-cam/xuat").status_code == 404


def test_cai_sai_422_va_kho_day_409(kho, monkeypatch):
    c = TestClient(_app())
    assert c.post("/api/goi-ky-nang", json=_goi(ten="Sai")).status_code == 422
    async def day(tho, *, boi): raise g.KhoDay("đầy")
    monkeypatch.setattr(g, "cai", day)
    assert c.post("/api/goi-ky-nang", json=_goi()).status_code == 409


def test_tai_tep_json_va_zip(kho):
    c = TestClient(_app())
    r = c.post("/api/goi-ky-nang/tep", files={"tep": ("goi.json", json.dumps(_goi()).encode("utf-8"), "application/json")})
    assert r.status_code == 201, r.text
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("goi.json", json.dumps(_goi(ten="goi-zip")))
    r = c.post("/api/goi-ky-nang/tep", files={"tep": ("goi.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 201 and "goi-zip" in kho


def test_tep_qua_lon_413(kho):
    c = TestClient(_app())
    r = c.post("/api/goi-ky-nang/tep", files={"tep": ("goi.zip", b"x" * (g.ZIP_TOI_DA + 1), "application/zip")})
    assert r.status_code == 413


def test_bat_tat_lich_su_khoi_phuc(kho):
    c = TestClient(_app())
    c.post("/api/goi-ky-nang", json=_goi())
    assert c.post("/api/goi-ky-nang/tu-van-da-nhay-cam/bat-tat", json={"bat": False}).status_code == 204
    assert c.post("/api/goi-ky-nang/khong-co/bat-tat", json={"bat": False}).status_code == 404
    assert c.get("/api/goi-ky-nang/tu-van-da-nhay-cam/lich-su").json()[0]["phien_ban"] == "0.9.0"
    assert c.post("/api/goi-ky-nang/tu-van-da-nhay-cam/khoi-phuc/1").status_code == 200
    assert c.post("/api/goi-ky-nang/tu-van-da-nhay-cam/khoi-phuc/9").status_code == 404


def test_router_gan_vao_app():
    from fastapi.openapi.utils import get_openapi
    from agent import main
    assert "/api/goi-ky-nang" in get_openapi(title="x", version="1", routes=main.app.routes)["paths"]
