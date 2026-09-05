"""
Cấu hình động: CSDL trước, .env sau — và không bao giờ lộ giá trị.
Không cần Postgres: kho giả trong bộ nhớ, vault thật với khoá test.
"""
from __future__ import annotations

import asyncio

import pytest

from agent import cau_hinh_dong as cd
from agent.config import settings
from agent.security.credential_vault import CredentialVault


class _KhoGia:
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
    monkeypatch.setattr(
        cd, "_vault",
        lambda: CredentialVault({1: bytes.fromhex("02" * 32)}, active_version=1),
    )
    su_kien = []

    async def log_event(kind, **kw):
        su_kien.append((kind, kw))

    monkeypatch.setattr(cd.db, "log_event", log_event)
    monkeypatch.setattr(cd, "_sau_khi_doi", lambda khoa: None)
    cd._gia_tri.clear(); cd._meta.clear()
    k.su_kien = su_kien
    return k


def test_chua_dat_thi_lui_ve_env(kho, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "tu-env")
    asyncio.run(cd.nap())
    assert cd.lay("ANTHROPIC_API_KEY") == "tu-env"
    assert cd.nguon("ANTHROPIC_API_KEY") == "env"


def test_dat_roi_thi_csdl_thang_env(kho, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "tu-env")
    asyncio.run(cd.dat("ANTHROPIC_API_KEY", "tu-csdl", sua_boi="admin"))
    assert cd.lay("ANTHROPIC_API_KEY") == "tu-csdl"
    assert cd.nguon("ANTHROPIC_API_KEY") == "csdl"
    # Sống qua khởi động lại: nạp lại từ kho phải ra đúng giá trị.
    cd._gia_tri.clear()
    asyncio.run(cd.nap())
    assert cd.lay("ANTHROPIC_API_KEY") == "tu-csdl"


def test_xoa_thi_lui_ve_env(kho, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "tu-env")
    asyncio.run(cd.dat("ANTHROPIC_API_KEY", "tu-csdl", sua_boi="admin"))
    asyncio.run(cd.xoa("ANTHROPIC_API_KEY", sua_boi="admin"))
    assert cd.lay("ANTHROPIC_API_KEY") == "tu-env"


def test_nhat_ky_ghi_ten_khoa_khong_ghi_gia_tri(kho):
    asyncio.run(cd.dat("GEMINI_API_KEY", "bi-mat-rat-dai-123", sua_boi="admin"))
    assert kho.su_kien and kho.su_kien[0][0] == "cau_hinh_api.doi"
    assert "bi-mat-rat-dai-123" not in repr(kho.su_kien)


def test_khoa_ngoai_danh_muc_bi_tu_choi(kho):
    with pytest.raises(cd.KhoaKhongHopLe):
        asyncio.run(cd.dat("ERP_LOAI", "erpnext", sua_boi="admin"))
    with pytest.raises(cd.KhoaKhongHopLe):
        cd.lay("KHOA_LA")


def test_provider_ngoai_danh_sach_bi_tu_choi(kho):
    with pytest.raises(cd.KhoaKhongHopLe):
        asyncio.run(cd.dat("LLM_PROVIDER", "openai", sua_boi="admin"))


def test_model_phai_co_trong_bang_gia(kho):
    with pytest.raises(cd.KhoaKhongHopLe):
        asyncio.run(cd.dat("MODEL_CHAT", "gpt-9", sua_boi="admin"))
    asyncio.run(cd.dat("MODEL_CHAT", "gemini-2.5-flash", sua_boi="admin"))


def test_liet_ke_khong_lo_bi_mat_chi_lo_duoi(kho):
    asyncio.run(cd.dat("GEMINI_API_KEY", "AIzaSyDUMMY-abcd", sua_boi="admin"))
    asyncio.run(cd.dat("ERPNEXT_URL", "https://erp.example", sua_boi="admin"))
    ds = {m["khoa"]: m for m in cd.liet_ke()}
    assert ds["GEMINI_API_KEY"]["hien"] == "···abcd"
    assert ds["GEMINI_API_KEY"]["da_dat"] is True
    assert ds["ERPNEXT_URL"]["hien"] == "https://erp.example"
    assert "AIzaSyDUMMY-abcd" not in repr(cd.liet_ke())


def test_vault_chua_san_sang_thi_dat_nem_ro_rang(kho, monkeypatch):
    def hong():
        raise cd.VaultChuaSanSang("chưa có CREDENTIAL_MASTER_KEYS")

    monkeypatch.setattr(cd, "_vault", hong)
    with pytest.raises(cd.VaultChuaSanSang):
        asyncio.run(cd.dat("GEMINI_API_KEY", "x", sua_boi="admin"))


def test_giai_ma_hong_thi_bao_va_bo_qua_khong_chet(kho, monkeypatch):
    asyncio.run(cd.dat("GEMINI_API_KEY", "x" * 20, sua_boi="admin"))
    # Đổi khoá chủ: bản mã cũ không mở được nữa.
    monkeypatch.setattr(
        cd, "_vault",
        lambda: CredentialVault({1: bytes.fromhex("03" * 32)}, active_version=1),
    )
    cd._gia_tri.clear()
    asyncio.run(cd.nap())
    assert cd.nguon("GEMINI_API_KEY") in ("env", "trong")
    assert any(k == "cau_hinh_api.giai_ma_hong" for k, _ in kho.su_kien)


def test_danh_muc_khong_chua_cong_tac_nguy_hiem():
    """ERP_LOAI và SHIPPING_PROVIDER cố ý ở .env: bật sai là dữ liệu không xoá được."""
    assert "ERP_LOAI" not in cd.DANH_MUC
    assert "SHIPPING_PROVIDER" not in cd.DANH_MUC
