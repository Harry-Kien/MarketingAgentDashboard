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

# Giữ lại bản THẬT trước khi fixture `kho` thay nó bằng no-op: có test cần
# chạy đúng hàm này để chứng minh cache client được xoá.
_SAU_KHI_DOI_THAT = cd._sau_khi_doi


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


def test_moi_khoa_trong_danh_muc_deu_co_duong_lui_env():
    """Thêm khoá vào DANH_MUC mà quên ánh xạ .env thì lay() nổ KeyError lúc chạy thật."""
    assert set(cd._DOC_ENV) == set(cd.DANH_MUC)


def test_kho_hong_thi_nap_khong_chan_khoi_dong_va_lui_ve_env(kho, monkeypatch):
    """
    Bảng cau_hinh_bi_mat chưa tồn tại hoặc không đọc được: nap() phải trả bình thường
    (không chặn khởi động) và lay() phải lui về .env.
    """
    class KhoBiBao:
        async def doc_tat_ca(self):
            raise RuntimeError("relation cau_hinh_bi_mat does not exist")

    monkeypatch.setattr(cd, "_kho", KhoBiBao())
    monkeypatch.setattr(settings, "anthropic_api_key", "tu-env")
    # nap() không được nổ lỗi
    asyncio.run(cd.nap())
    # lay() phải trả giá trị .env
    assert cd.lay("ANTHROPIC_API_KEY") == "tu-env"
    assert cd.nguon("ANTHROPIC_API_KEY") == "env"


def test_vault_chua_san_sang_luc_nap_thi_chay_bang_env(kho, monkeypatch):
    """
    Có khoá trong CSDL nhưng vault chưa cấu hình lúc nap(): nap() phải trả bình thường
    (không nổ VaultChuaSanSang) và lay() phải lui về .env.
    """
    monkeypatch.setattr(settings, "gemini_api_key", "tu-env")
    # Lưu một khoá vào CSDL
    asyncio.run(cd.dat("GEMINI_API_KEY", "x" * 20, sua_boi="admin"))
    # Giờ vault không sẵn sàng
    def hong():
        raise cd.VaultChuaSanSang("chưa cấu hình")

    monkeypatch.setattr(cd, "_vault", hong)
    # Xoá bộ nhớ tiến trình để buộc nap() đọc lại
    cd._gia_tri.clear()
    cd._meta.clear()
    # nap() không được nổ lỗi
    asyncio.run(cd.nap())
    # lay() phải trả giá trị .env vì vault lỗi
    assert cd.lay("GEMINI_API_KEY") == "tu-env"
    assert cd.nguon("GEMINI_API_KEY") in ("env", "trong")


def test_ghi_ket_qua_kiem_cho_khoa_da_luu(kho):
    """
    Khoá được lưu trong CSDL: ghi_ket_qua_kiem() phải gọi kho.ghi_kiem() với
    "đạt: " hoặc "hỏng: " prefix, và chi_tiet bị cắt tối đa 200 ký tự.
    liet_ke() phải hiển thị kiem_ket_qua và kiem_luc cho khoá đó.
    """
    # Lưu một khoá vào CSDL
    asyncio.run(cd.dat("GEMINI_API_KEY", "x" * 20, sua_boi="admin"))
    # Ghi kết quả kiểm (ok)
    asyncio.run(cd.ghi_ket_qua_kiem("GEMINI_API_KEY", True, "gemini-2.5-flash-lite · 12ms"))
    # Ghi kết quả kiểm (hỏng) với chi_tiet dài
    chi_tiet_dai = "y" * 500
    asyncio.run(cd.ghi_ket_qua_kiem("GEMINI_API_KEY", False, chi_tiet_dai))
    # Kiểm kho.kiem
    assert len(kho.kiem) == 2
    assert kho.kiem[0] == ("GEMINI_API_KEY", "đạt: gemini-2.5-flash-lite · 12ms")
    assert kho.kiem[1][0] == "GEMINI_API_KEY"
    assert kho.kiem[1][1].startswith("hỏng: ")
    # "hỏng: " là 6 ký tự + 200 ký tự chi_tiet tối đa = 206
    assert len(kho.kiem[1][1]) <= 6 + 200
    # liet_ke() phải hiển thị kiem_ket_qua và kiem_luc
    ds = {m["khoa"]: m for m in cd.liet_ke()}
    assert ds["GEMINI_API_KEY"]["kiem_ket_qua"] == "hỏng: " + "y" * 200
    assert ds["GEMINI_API_KEY"]["kiem_luc"] is not None


def test_dat_va_xoa_deu_don_dep_cache_va_danh_sach_che(kho, monkeypatch):
    """
    KHÔNG vá `_sau_khi_doi`: đây đúng là thứ cần canh.

    Đổi khoá mà giữ client Anthropic cũ là dashboard báo "đã lưu" trong khi
    model vẫn gọi bằng khoá cũ. Và không quên danh sách bí mật của nhật ký
    thì khoá vừa dán không được che dòng log nào cho tới lần khởi động lại.
    Cả hai đều hỏng im lặng, nên phải có test giữ lời gọi lại.
    """
    from agent import nhat_ky
    from agent.core import llm

    monkeypatch.setattr(cd, "_sau_khi_doi", _SAU_KHI_DOI_THAT)
    goi: list[str] = []
    monkeypatch.setattr(llm, "xoa_cache_client", lambda: goi.append("cache"))
    monkeypatch.setattr(nhat_ky, "quen_bi_mat", lambda: goi.append("che"))

    asyncio.run(cd.dat("GEMINI_API_KEY", "k" * 20, sua_boi="admin"))
    asyncio.run(cd.xoa("GEMINI_API_KEY", sua_boi="admin"))

    assert goi.count("cache") == 2
    assert goi.count("che") == 2


def test_khoa_luu_qua_dashboard_bi_che_trong_nhat_ky(kho):
    """
    Bí mật nhập trên dashboard nằm trong CSDL, KHÔNG có trong `settings` —
    bộ lọc chỉ duyệt `settings` là đúng những khoá mới nhất không được che
    dòng log nào. Không lỗi, không cảnh báo: log lộ khoá trong im lặng.
    """
    import logging

    from agent import nhat_ky

    khoa_that = "AIzaSyRAT-DAI-VA-BI-MAT-999"
    asyncio.run(cd.dat("GEMINI_API_KEY", khoa_that, sua_boi="admin"))
    nhat_ky.quen_bi_mat()   # fixture vá _sau_khi_doi nên phải quên bằng tay
    try:
        loc = nhat_ky.LocBiMat()
        ban_ghi = logging.LogRecord(
            name="httpx", level=logging.INFO, pathname="x", lineno=1,
            msg="POST https://generativelanguage.googleapis.com/?k=%s",
            args=(khoa_that,), exc_info=None,
        )
        loc.filter(ban_ghi)
        assert khoa_that not in ban_ghi.getMessage()
        assert nhat_ky.CHE in ban_ghi.getMessage()
    finally:
        # Danh sách nhớ ở mức LỚP: không quên là test sau thấy bí mật của test này.
        nhat_ky.quen_bi_mat()


def test_ghi_ket_qua_kiem_bo_qua_khoa_chi_co_o_env(kho, monkeypatch):
    """
    Khoá chỉ có ở .env (không lưu trong CSDL): ghi_ket_qua_kiem() phải bỏ qua,
    không gọi kho.ghi_kiem().
    """
    monkeypatch.setattr(settings, "anthropic_api_key", "tu-env")
    # Không lưu vào CSDL, chỉ nạp từ .env
    asyncio.run(cd.nap())
    # Ghi kết quả kiểm
    asyncio.run(cd.ghi_ket_qua_kiem("ANTHROPIC_API_KEY", True, "ok"))
    # kho.kiem phải trống (không gọi ghi_kiem)
    assert kho.kiem == []
