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


def test_kiem_tra_gia_tri_da_luu_thi_ghi_ket_qua(kho, monkeypatch):
    async def kiem_khoa(**kw):
        return False, "HẾT HẠN MỨC", 5

    monkeypatch.setattr(cai_dat_api.llm, "kiem_khoa", kiem_khoa)
    c = _app(admin=True)
    c.put("/api/cai-dat-api/LLM_PROVIDER", json={"gia_tri": "gemini_api"})
    c.put("/api/cai-dat-api/GEMINI_API_KEY", json={"gia_tri": "k" * 20})
    r = c.post("/api/cai-dat-api/kiem-tra", json={"nhom": "model"})
    assert r.json()["ok"] is False
    assert any(k == "GEMINI_API_KEY" and "HẾT HẠN MỨC" in kq for k, kq in kho.kiem)


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
