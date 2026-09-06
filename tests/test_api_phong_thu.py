"""
API phòng thử: chỉ quản trị, không tác dụng phụ, lỗi model không lộ khoá.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api import phong_thu_agent as api
from agent.api import routes
from agent.core import phong_thu_phien as pp
from agent.core import thu_nghiem
from agent.core.agent import Reply


def _app(quan_tri=True):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[routes.bat_buoc_quan_tri] = (
        (lambda: {"ten_dang_nhap": "qt", "vai_tro": "quan_tri"}) if quan_tri
        else routes.bat_buoc_quan_tri
    )
    return app


@pytest.fixture(autouse=True)
def _sach(monkeypatch):
    pp.xoa_het()
    thu_nghiem.xoa_dem()

    async def fetchrow(sql, *a):
        import uuid
        return {"id": uuid.uuid4()}

    monkeypatch.setattr(pp.db, "fetchrow", fetchrow)
    yield
    pp.xoa_het()
    thu_nghiem.xoa_dem()


@pytest.fixture
def tra_loi(monkeypatch):
    hop = {"trong_sandbox": []}

    async def respond(**kw):
        hop["trong_sandbox"].append(thu_nghiem.dang_thu.get())
        return Reply(text="Dạ sữa rửa mặt giá 245.000đ ạ.", cost_usd=0.02, latency_ms=300,
                     model="m", confidence=0.8, grounded=True, sources=["Bảng giá"],
                     cong_cu=[{"ten": "tra_cuu_san_pham", "tham_so": {}, "ket_qua": {"gia": 245000},
                               "ms": 5, "vong": 1, "thu_nghiem": False}],
                     vong=[{"cost_usd": 0.02, "tokens_in": 1, "tokens_out": 1, "latency_ms": 300, "so_cong_cu": 1}])

    monkeypatch.setattr(api.brain, "respond", respond)
    return hop


def test_nhan_vien_bi_403():
    c = TestClient(_app(quan_tri=False))
    assert c.post("/api/phong-thu/phien").status_code in (401, 403)


def test_tao_phien_hoi_va_xem_lai(tra_loi):
    c = TestClient(_app())
    pid = c.post("/api/phong-thu/phien").json()["id"]
    r = c.post(f"/api/phong-thu/phien/{pid}/hoi", json={"cau_hoi": "giá sữa rửa mặt?"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["tra_loi"].startswith("Dạ") and d["cong_cu"][0]["ten"] == "tra_cuu_san_pham"
    assert d["luoi_bat"] is None and d["phien"]["so_luot"] == 1
    assert d["cham"]["tu_cam"] == [] and "hinh_thuc" in d["cham"]
    assert tra_loi["trong_sandbox"] == [True]
    assert thu_nghiem.da_tieu_hom_nay() == pytest.approx(0.02)
    xem = c.get(f"/api/phong-thu/phien/{pid}").json()
    assert xem["so_luot"] == 1 and xem["luot"][0]["khach"] == "giá sữa rửa mặt?"
    assert c.delete(f"/api/phong-thu/phien/{pid}").status_code == 204
    assert c.get(f"/api/phong-thu/phien/{pid}").status_code == 404


def test_ky_vong_bo_vang_duoc_cham(tra_loi):
    c = TestClient(_app())
    pid = c.post("/api/phong-thu/phien").json()["id"]
    d = c.post(f"/api/phong-thu/phien/{pid}/hoi", json={
        "cau_hoi": "giá?", "ky_vong": {"chuyen_nguoi": False, "phai_co": ["245"],
                                       "phai_co_mot_trong": [], "khong_duoc_co": ["trị dứt điểm"]},
    }).json()
    assert d["cham"]["so_voi_bo_vang"]["dat"] is True


def test_cau_hoi_rong_hoac_qua_dai_422(tra_loi):
    c = TestClient(_app())
    pid = c.post("/api/phong-thu/phien").json()["id"]
    assert c.post(f"/api/phong-thu/phien/{pid}/hoi", json={"cau_hoi": "  "}).status_code == 422
    assert c.post(f"/api/phong-thu/phien/{pid}/hoi", json={"cau_hoi": "x" * 2001}).status_code == 422


def test_ky_vong_sai_hinh_dang_422(tra_loi):
    # `phai_co` sai kiểu (số thay vì danh sách chuỗi) phải bị FastAPI chặn
    # ở tầng validate — TRƯỚC khi ghi_nhan/ghi_luot chạy, nên phiên vẫn sạch.
    c = TestClient(_app())
    pid = c.post("/api/phong-thu/phien").json()["id"]
    r = c.post(f"/api/phong-thu/phien/{pid}/hoi",
               json={"cau_hoi": "giá?", "ky_vong": {"phai_co": 123}})
    assert r.status_code == 422
    assert c.get(f"/api/phong-thu/phien/{pid}").json()["so_luot"] == 0


def test_het_tran_thu_429(tra_loi, monkeypatch):
    from agent import runtime

    monkeypatch.setitem(runtime.STATE, "phong_thu_tran_ngay_usd", 0.01)
    thu_nghiem.ghi_nhan(0.02)
    c = TestClient(_app())
    pid = c.post("/api/phong-thu/phien").json()["id"]
    r = c.post(f"/api/phong-thu/phien/{pid}/hoi", json={"cau_hoi": "giá?"})
    assert r.status_code == 429
    d = r.json()["detail"]
    assert d["tran"] == 0.01 and "trần" in d["ly_do"]


def test_tran_san_xuat_cham_thi_429_khong_phai_tra_loi(monkeypatch):
    async def respond(**kw):
        return Reply(text="Để em chuyển...", escalate=True, luoi_bat="tran_ngay",
                     escalate_reason="Chạm trần chi phí ngày (30.00/25.00 USD)")

    monkeypatch.setattr(api.brain, "respond", respond)
    c = TestClient(_app())
    pid = c.post("/api/phong-thu/phien").json()["id"]
    r = c.post(f"/api/phong-thu/phien/{pid}/hoi", json={"cau_hoi": "giá?"})
    assert r.status_code == 429 and "Chạm trần" in r.json()["detail"]["ly_do"]


def test_model_loi_502_khong_lo_khoa(monkeypatch):
    async def respond(**kw):
        raise RuntimeError("AuthenticationError: key AIzaBIMATTHAT1234567890 bị từ chối")

    monkeypatch.setattr(api.brain, "respond", respond)
    c = TestClient(_app())
    pid = c.post("/api/phong-thu/phien").json()["id"]
    r = c.post(f"/api/phong-thu/phien/{pid}/hoi", json={"cau_hoi": "giá?"})
    assert r.status_code == 502 and "AIzaBIMATTHAT1234567890" not in r.text
    assert "RuntimeError" in r.json()["detail"]
    assert c.get(f"/api/phong-thu/phien/{pid}").json()["so_luot"] == 0


def test_khoa_cat_ngang_ranh_200_van_bi_che(monkeypatch):
    # Khoá nằm vắt ngang mốc cắt 200 ký tự — nếu cắt trước rồi mới che thì
    # phần khoá sau mốc lọt qua nguyên vẹn. Phải che TRÊN THÔNG ĐIỆP ĐẦY ĐỦ.
    khoa = "AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ123456"

    async def respond(**kw):
        raise RuntimeError("x" * 190 + khoa)

    monkeypatch.setattr(api.brain, "respond", respond)
    c = TestClient(_app())
    pid = c.post("/api/phong-thu/phien").json()["id"]
    r = c.post(f"/api/phong-thu/phien/{pid}/hoi", json={"cau_hoi": "giá?"})
    assert r.status_code == 502
    assert "AIzaSy" not in r.text


def test_phien_day_luot_409(tra_loi):
    c = TestClient(_app())
    pid = c.post("/api/phong-thu/phien").json()["id"]
    p = pp.lay_phien(pid)
    for i in range(pp.TOI_DA_LUOT):
        pp.ghi_luot(p, str(i), {"cost_usd": 0}, "ok")
    assert c.post(f"/api/phong-thu/phien/{pid}/hoi", json={"cau_hoi": "x"}).status_code == 409


def test_goi_y_doc_bo_vang(tmp_path):
    f = tmp_path / "g.jsonl"
    f.write_text(json.dumps({"id": "A1", "nhom": "tuan_thu", "hoi": "bầu dùng retinol?",
                             "chuyen_nguoi": True, "phai_co": [], "phai_co_mot_trong": [],
                             "khong_duoc_co": []}, ensure_ascii=False) + "\n", encoding="utf-8")
    goi_y = api.doc_goi_y(f)
    assert goi_y["tuan_thu"][0]["hoi"] == "bầu dùng retinol?"
    assert goi_y["tuan_thu"][0]["ky_vong"]["chuyen_nguoi"] is True


def test_goi_y_bo_qua_dong_hong(tmp_path):
    # Một dòng gõ tay hỏng (không phải JSON) không được kéo sập cả bảng gợi ý.
    f = tmp_path / "g.jsonl"
    f.write_text(
        json.dumps({"id": "A1", "nhom": "tuan_thu", "hoi": "bầu dùng retinol?",
                    "chuyen_nguoi": True, "phai_co": [], "phai_co_mot_trong": [],
                    "khong_duoc_co": []}, ensure_ascii=False)
        + "\n" + "not json" + "\n",
        encoding="utf-8",
    )
    goi_y = api.doc_goi_y(f)
    assert goi_y["tuan_thu"][0]["hoi"] == "bầu dùng retinol?"


def test_goi_y_endpoint_va_ngan_sach(tra_loi):
    c = TestClient(_app())
    assert isinstance(c.get("/api/phong-thu/goi-y").json(), dict)
    ns = c.get("/api/phong-thu/ngan-sach").json()
    assert set(ns) == {"da_tieu", "tran"}


def test_router_duoc_gan_va_cau_hinh_co_tran_thu():
    from fastapi.openapi.utils import get_openapi

    from agent import main

    spec = get_openapi(title="x", version="1", routes=main.app.routes)
    assert "/api/phong-thu/phien" in spec["paths"]
    assert "phong_thu_tran_ngay_usd" in routes._MO_TA_CAU_HINH
    assert "phong_thu_tran_ngay_usd" in routes.RuntimeBody.model_fields


def test_che_khong_dong_gi_khi_khong_co_khoa():
    assert api._che("abc") == "abc"


def test_che_thay_khoa_bang_dau_cham():
    thong_diep = "chuoi AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ123 loi"
    assert "AIzaSy" not in api._che(thong_diep)
