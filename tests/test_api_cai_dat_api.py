"""
API Cài đặt API: không lộ bí mật, kiểm không lưu, quản trị mới được ghi.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from agent import cau_hinh_dong as cd
from agent.api import cai_dat_api
from agent.api.routes import bat_buoc_dang_nhap, bat_buoc_quan_tri
from agent.security.credential_vault import CredentialVault


class _KhoGia:
    """Bản sao của kho giả trong test_cau_hinh_dong — thư mục tests không phải package."""

    def __init__(self):
        self.dong: dict[str, dict] = {}
        self.kiem: list = []

    async def doc_tat_ca(self):
        return [dict(khoa=k, **v) for k, v in self.dong.items()]

    async def ghi(self, khoa, sealed, sua_boi):
        self.dong[khoa] = dict(
            key_version=sealed.key_version, nonce=sealed.nonce,
            ciphertext=sealed.ciphertext, sua_boi=sua_boi, sua_luc=None,
            kiem_luc=None, kiem_ket_qua=None,
        )

    async def xoa(self, khoa):
        self.dong.pop(khoa, None)

    async def ghi_kiem(self, khoa, ket_qua):
        self.kiem.append((khoa, ket_qua))


@pytest.fixture
def kho(monkeypatch):
    k = _KhoGia()
    monkeypatch.setattr(cd, "_kho", k)
    monkeypatch.setattr(cd, "_vault", lambda: CredentialVault({1: bytes.fromhex("04" * 32)}, active_version=1))

    async def log_event(kind, **kw):
        pass

    monkeypatch.setattr(cd.db, "log_event", log_event)
    monkeypatch.setattr(cd, "_sau_khi_doi", lambda khoa: None)
    cd._gia_tri.clear(); cd._meta.clear()
    return k


def _app(*, admin: bool):
    app = FastAPI()
    app.include_router(cai_dat_api.router)
    user = {"id": uuid4(), "ten_dang_nhap": "a", "vai_tro": "quan_tri" if admin else "nhan_vien"}
    app.dependency_overrides[bat_buoc_dang_nhap] = lambda: user
    if admin:
        app.dependency_overrides[bat_buoc_quan_tri] = lambda: user
    else:
        def deny():
            raise HTTPException(403, "Việc này cần quyền quản trị")
        app.dependency_overrides[bat_buoc_quan_tri] = deny
    return TestClient(app)


def test_luu_roi_liet_ke_khong_lo_khoa(kho):
    c = _app(admin=True)
    r = c.put("/api/cai-dat-api/GEMINI_API_KEY", json={"gia_tri": "AIzaSyBIMAT-wxyz"})
    assert r.status_code == 204
    ds = c.get("/api/cai-dat-api")
    assert ds.status_code == 200
    assert "AIzaSyBIMAT-wxyz" not in ds.text
    muc = {m["khoa"]: m for m in ds.json()["muc"]}
    assert muc["GEMINI_API_KEY"]["hien"] == "···wxyz"
    assert muc["GEMINI_API_KEY"]["nguon"] == "csdl"


def test_nhan_vien_xem_duoc_nhung_khong_ghi_duoc(kho):
    c = _app(admin=False)
    assert c.get("/api/cai-dat-api").status_code == 200
    assert c.put("/api/cai-dat-api/GEMINI_API_KEY", json={"gia_tri": "x" * 20}).status_code == 403
    assert c.delete("/api/cai-dat-api/GEMINI_API_KEY").status_code == 403
    assert c.post("/api/cai-dat-api/kiem-tra", json={"nhom": "model"}).status_code == 403


def test_khoa_la_va_gia_tri_sai_bi_422(kho):
    c = _app(admin=True)
    assert c.put("/api/cai-dat-api/ERP_LOAI", json={"gia_tri": "erpnext"}).status_code == 422
    assert c.put("/api/cai-dat-api/LLM_PROVIDER", json={"gia_tri": "openai"}).status_code == 422


def test_kiem_tra_dung_gia_tri_gui_len_va_khong_luu(kho, monkeypatch):
    nhan = {}

    async def kiem_khoa(*, provider_name, api_key="", model="", project="", timeout=45.0):
        nhan.update(provider_name=provider_name, api_key=api_key, model=model)
        return True, f"{model} · 12ms", 12

    monkeypatch.setattr(cai_dat_api.llm, "kiem_khoa", kiem_khoa)
    c = _app(admin=True)
    r = c.post("/api/cai-dat-api/kiem-tra", json={
        "nhom": "model",
        "gia_tri": {"LLM_PROVIDER": "gemini_api", "GEMINI_API_KEY": "CHUA-LUU", "MODEL_CHEAP": "gemini-2.5-flash-lite"},
    })
    assert r.status_code == 200 and r.json()["ok"] is True
    assert nhan["api_key"] == "CHUA-LUU" and nhan["provider_name"] == "gemini_api"
    assert kho.dong == {}, "kiểm tra không được lưu gì"


def test_kiem_tra_tu_dashboard_van_ghi_ket_qua(kho, monkeypatch):
    """
    Body ĐÚNG như trình duyệt gửi: `giaTriApiDangGo()` gom mọi ô có giá trị,
    nên ô chọn provider và các ô không bí mật đã điền sẵn luôn đi kèm — ô bí
    mật thì trống vì máy chủ không bao giờ gửi giá trị xuống để mà điền.

    Bản trước chỉ ghi khi `gia_tri` RỖNG, tức là không bao giờ ghi khi lời
    gọi đến từ dashboard: `ghi_ket_qua_kiem` là mã chết và không ai biết, vì
    test cũ post một payload trình duyệt không dựng được.
    """
    async def kiem_khoa(**kw):
        return False, "HẾT HẠN MỨC", 5

    monkeypatch.setattr(cai_dat_api.llm, "kiem_khoa", kiem_khoa)
    c = _app(admin=True)
    c.put("/api/cai-dat-api/LLM_PROVIDER", json={"gia_tri": "gemini_api"})
    c.put("/api/cai-dat-api/GEMINI_API_KEY", json={"gia_tri": "k" * 20})
    r = c.post("/api/cai-dat-api/kiem-tra", json={
        "nhom": "model",
        "gia_tri": {"LLM_PROVIDER": "gemini_api", "MODEL_CHEAP": "gemini-2.5-flash-lite"},
    })
    assert r.json()["ok"] is False
    assert any(k == "GEMINI_API_KEY" and "HẾT HẠN MỨC" in kq for k, kq in kho.kiem)
    # Chỉ khoá THỰC SỰ được probe (Gemini, vì provider = gemini_api) mới được
    # ghi kết quả — ANTHROPIC_API_KEY không hề tham gia lệnh gọi thì không
    # được phép ăn theo, dù cùng nhóm "model" (xem finding Critical round 1).
    assert not any(k == "ANTHROPIC_API_KEY" for k, _ in kho.kiem)


def test_kiem_tra_bang_khoa_vua_go_thi_khong_dong_dau_len_khoa_da_luu(kho, monkeypatch):
    """
    Người dán một khoá KHÁC vào ô rồi bấm Kiểm tra: kết quả nói về khoá vừa
    gõ, không nói gì về khoá đang lưu. Đóng dấu "đạt" lên khoá đã lưu lúc
    này là nói dối trên dashboard.
    """
    async def kiem_khoa(**kw):
        return True, "gemini-2.5-flash-lite · 12ms", 12

    monkeypatch.setattr(cai_dat_api.llm, "kiem_khoa", kiem_khoa)
    c = _app(admin=True)
    c.put("/api/cai-dat-api/LLM_PROVIDER", json={"gia_tri": "gemini_api"})
    c.put("/api/cai-dat-api/GEMINI_API_KEY", json={"gia_tri": "k" * 20})
    r = c.post("/api/cai-dat-api/kiem-tra", json={
        "nhom": "model",
        "gia_tri": {"LLM_PROVIDER": "gemini_api", "GEMINI_API_KEY": "m" * 20},
    })
    assert r.json()["ok"] is True
    assert kho.kiem == [], "khoá vừa gõ khác khoá đang lưu thì không được ghi gì"


def test_kiem_tra_che_khoa_neu_provider_echo_lai(kho, monkeypatch):
    """Phòng thân: dù provider (hay lỗi thư viện HTTP) lỡ echo khoá vào
    thông báo lỗi, `chi_tiet` trả về dashboard/log không được chứa nó."""
    khoa_that = "AIzaSyBIMAT-secret-value-xyz"

    async def kiem_khoa(*, api_key, **kw):
        return False, f"AuthenticationError: khoá {api_key} bị từ chối", 5

    monkeypatch.setattr(cai_dat_api.llm, "kiem_khoa", kiem_khoa)
    c = _app(admin=True)
    r = c.post("/api/cai-dat-api/kiem-tra", json={
        "nhom": "model",
        "gia_tri": {"LLM_PROVIDER": "gemini_api", "GEMINI_API_KEY": khoa_that},
    })
    chi_tiet = r.json()["chi_tiet"]
    assert khoa_that not in chi_tiet
    assert "AuthenticationError" in chi_tiet


def test_kiem_tra_provider_vertex_khong_gui_khoa(kho, monkeypatch):
    """provider gemini/vertex xác thực qua gcloud trên máy, không qua API
    key — gửi khoá cho llm.kiem_khoa trong trường hợp này là dữ liệu thừa,
    có thể lẫn khoá của provider khác đang lưu trong cấu hình."""
    nhan = {}

    async def kiem_khoa(*, provider_name, api_key="", model="", project="", timeout=45.0):
        nhan.update(provider_name=provider_name, api_key=api_key)
        return True, "vertex ok", 8

    monkeypatch.setattr(cai_dat_api.llm, "kiem_khoa", kiem_khoa)
    c = _app(admin=True)
    r = c.post("/api/cai-dat-api/kiem-tra", json={"nhom": "model", "gia_tri": {"LLM_PROVIDER": "vertex"}})
    assert r.status_code == 200
    assert nhan["api_key"] == ""
    assert r.json()["khoa_da_kiem"] == []


def test_vault_chua_san_sang_thi_503_khi_ghi(kho, monkeypatch):
    def hong():
        raise cd.VaultChuaSanSang("chưa có CREDENTIAL_MASTER_KEYS")

    monkeypatch.setattr(cd, "_vault", hong)
    c = _app(admin=True)
    r = c.put("/api/cai-dat-api/GEMINI_API_KEY", json={"gia_tri": "x" * 20})
    assert r.status_code == 503 and "CREDENTIAL_MASTER_KEYS" in r.json()["detail"]
    assert c.get("/api/cai-dat-api").json()["vault_san_sang"] is False


def test_kiem_nhom_erp_dung_gia_tri_chua_luu(kho, monkeypatch):
    dung = {}

    class _Nguon:
        def __init__(self, **kw):
            dung.update(kw)

        async def suc_khoe(self):
            return True

    monkeypatch.setattr(cai_dat_api, "NguonErpNext", _Nguon)
    kq = asyncio.run(cai_dat_api.kiem_nhom("erp", {"ERPNEXT_URL": "https://e", "ERPNEXT_API_KEY": "k", "ERPNEXT_API_SECRET": "s"}))
    assert kq["ok"] and dung["goc"] == "https://e" and dung["api_secret"] == "s"


def test_router_duoc_gan_vao_app():
    from fastapi.openapi.utils import get_openapi
    from agent import main

    spec = get_openapi(title="x", version="1", routes=main.app.routes)
    assert "/api/cai-dat-api" in spec["paths"]
    assert "/api/cai-dat-api/kiem-tra" in spec["paths"]


def test_lifespan_nap_cau_hinh_dong_sau_runtime():
    import inspect

    from agent import main

    than = inspect.getsource(main.lifespan)
    assert "cau_hinh_dong.nap()" in than
    assert than.index("runtime.nap()") < than.index("cau_hinh_dong.nap()")
