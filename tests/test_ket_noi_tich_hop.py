"""
Kết nối & Tích hợp: trạng thái kết nối, kiểm không lưu, không lộ bí mật,
thông báo minh bạch AI sửa được mà vẫn giữ lời hứa, MODEL_CHAT có hiệu lực.

Không cần Postgres: kho cấu hình giả trong bộ nhớ, mọi phép kiểm mạng bị vá.
Phần cần CSDL thật ở `test_ket_noi_tich_hop_pg.py`.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent import cau_hinh_dong as cd
from agent import ket_noi_tich_hop as kn
from agent.api import ket_noi_tich_hop as api_kn
from agent.api.routes import nguoi_da_dang_nhap
from agent.security.credential_vault import CredentialVault
from conftest import nguoi_thu

ROOT = Path(__file__).resolve().parent.parent


class _KhoGia:
    def __init__(self):
        self.dong: dict[str, dict] = {}

    async def doc_tat_ca(self):
        return [dict(khoa=k, **v) for k, v in self.dong.items()]

    async def ghi(self, khoa, sealed, sua_boi):
        self.dong[khoa] = dict(key_version=sealed.key_version, nonce=sealed.nonce,
                               ciphertext=sealed.ciphertext, sua_boi=sua_boi, sua_luc=None,
                               kiem_luc=None, kiem_ket_qua=None)

    async def xoa(self, khoa):
        self.dong.pop(khoa, None)

    async def ghi_kiem(self, khoa, ket_qua):
        pass


@pytest.fixture
def kho(monkeypatch):
    k = _KhoGia()
    monkeypatch.setattr(cd, "_kho", k)
    monkeypatch.setattr(cd, "_vault",
                        lambda: CredentialVault({1: bytes.fromhex("05" * 32)}, active_version=1))

    async def log_event(kind, **kw):
        pass

    monkeypatch.setattr(cd.db, "log_event", log_event)
    monkeypatch.setattr(cd, "_sau_khi_doi", lambda khoa: None)
    lich_su: list[dict] = []

    async def ghi_lich_su(**kw):
        lich_su.append(kw)

    monkeypatch.setattr(kn, "ghi_lich_su", ghi_lich_su)
    cd._gia_tri.clear()
    cd._meta.clear()
    k.lich_su = lich_su
    yield k
    cd._gia_tri.clear()
    cd._meta.clear()


@pytest.fixture
def so_kiem(monkeypatch):
    """Sổ kết quả kiểm trong bộ nhớ thay cho bảng ket_noi_kiem_tra."""
    so: dict[str, dict] = {}

    async def doc():
        return dict(so)

    async def ghi(ma, *, ok, chi_tiet, ms, van_tay, boi):
        so[ma] = {"ok": ok, "chi_tiet": chi_tiet, "ms": ms, "dau_van_tay": van_tay,
                  "kiem_boi": boi, "kiem_luc": None}

    monkeypatch.setattr(kn, "doc_ket_qua_kiem", doc)
    monkeypatch.setattr(kn, "ghi_ket_qua_kiem", ghi)
    return so


def _app(*quyen):
    app = FastAPI()
    app.include_router(api_kn.router)
    app.dependency_overrides[nguoi_da_dang_nhap] = lambda: nguoi_thu(*quyen, ten="qt", id=uuid4())
    return TestClient(app)


# ------------------------------------------------------------------ trạng thái

def test_bon_trang_thai_va_doi_khoa_thi_ve_chua_kiem_tra(kho, monkeypatch):
    """Đổi token SAU lần kiểm xanh thì không được giữ màu xanh (xanh giả)."""
    asyncio.run(cd.dat("GHN_TOKEN", "t" * 20, sua_boi="qt"))
    asyncio.run(cd.dat("GHN_SHOP_ID", "12345", sua_boi="qt"))
    assert kn.trang_thai("ghn", None) == kn.CHUA_KIEM_TRA
    kiem = {"ok": True, "dau_van_tay": kn.dau_van_tay("ghn")}
    assert kn.trang_thai("ghn", kiem) == kn.THANH_CONG
    assert kn.trang_thai("ghn", {**kiem, "ok": False}) == kn.LOI
    asyncio.run(cd.dat("GHN_TOKEN", "u" * 20, sua_boi="qt"))
    assert kn.trang_thai("ghn", kiem) == kn.CHUA_KIEM_TRA


def test_chua_cau_hinh_khi_thieu_truong_bat_buoc(kho, monkeypatch):
    monkeypatch.setattr(kn.settings, "ghn_token", "")
    monkeypatch.setattr(kn.settings, "ghn_shop_id", "")
    assert kn.trang_thai("ghn", {"ok": True, "dau_van_tay": kn.dau_van_tay("ghn")}) == kn.CHUA_CAU_HINH
    assert set(kn.thieu("ghn")) == {"GHN_TOKEN", "GHN_SHOP_ID"}


def test_doi_env_lien_quan_cung_lam_cu_ket_qua_kiem(kho, monkeypatch):
    """Sửa `.env` bằng tay (URL máy chủ GHN) cũng phải làm cũ lần kiểm."""
    truoc = kn.dau_van_tay("ghn")
    monkeypatch.setattr(kn.settings, "ghn_api_url", "https://online-gateway.ghn.vn/x")
    assert kn.dau_van_tay("ghn") != truoc


def test_moi_khoa_dich_vu_deu_co_trong_danh_muc():
    for d in kn.DICH_VU.values():
        for k in d.khoa:
            assert k in cd.DANH_MUC, (d.ma, k)


# ------------------------------------------------------------------ API

def test_xem_cung_can_quyen_sua_cau_hinh(kho, so_kiem):
    """Chủ dự án: chỉ quản trị viên mới XEM hoặc đổi cấu hình kết nối."""
    c = _app("cau_hinh.doc")
    for duong in ("/api/ket-noi", "/api/ket-noi/ai", "/api/ket-noi/lich-su",
                  "/api/ket-noi/webhook?dich_vu=ghn"):
        assert c.get(duong).status_code == 403, duong
    assert c.put("/api/ket-noi/dich-vu/ghn", json={"gia_tri": {}}).status_code == 403
    assert c.post("/api/ket-noi/dich-vu/ghn/kiem-tra", json={}).status_code == 403


def test_tong_quan_khong_lo_bi_mat(kho, so_kiem, monkeypatch):
    async def khong_co_kenh():
        return []

    async def thong_ke(_ds):
        return {}

    monkeypatch.setattr(api_kn, "plugin_kenh", khong_co_kenh)
    monkeypatch.setattr(kn, "thong_ke_webhook", thong_ke)
    monkeypatch.setattr(kn.settings, "shipping_webhook_secret", "WHSECRET-rat-dai-0099")
    c = _app("cau_hinh.sua")
    for k, v in (("GHN_TOKEN", "GHN-BIMAT-abcd"), ("ERPNEXT_API_SECRET", "ERP-BIMAT-wxyz"),
                 ("GHTK_TOKEN", "GHTK-BIMAT-1234")):
        asyncio.run(cd.dat(k, v, sua_boi="qt"))
    r = c.get("/api/ket-noi")
    assert r.status_code == 200
    for bi_mat in ("GHN-BIMAT-abcd", "ERP-BIMAT-wxyz", "GHTK-BIMAT-1234", "WHSECRET-rat-dai-0099"):
        assert bi_mat not in r.text, bi_mat
    ghn = next(d for d in r.json()["dich_vu"] if d["ma"] == "ghn")
    assert ghn["webhook"]["url"].endswith("/webhook/shipping/ghn?token=···0099")
    assert next(t for t in ghn["truong"] if t["khoa"] == "GHN_TOKEN")["hien"] == "···abcd"


def test_luu_tu_choi_truong_cua_dich_vu_khac(kho, so_kiem):
    c = _app("cau_hinh.sua")
    r = c.put("/api/ket-noi/dich-vu/ghn", json={"gia_tri": {"ERPNEXT_API_KEY": "x" * 20}})
    assert r.status_code == 422
    assert cd._gia_tri == {}


def test_luu_bo_qua_o_trong_va_bao_tung_truong_hong(kho, so_kiem):
    c = _app("cau_hinh.sua")
    r = c.put("/api/ket-noi/dich-vu/ai", json={"gia_tri": {
        "GEMINI_API_KEY": "", "MODEL_CHAT": "gpt-4o", "MODEL_HARD": "khong-co-model"}})
    assert r.status_code == 200
    assert r.json()["da_luu"] == ["MODEL_CHAT"]
    assert [h["khoa"] for h in r.json()["hong"]] == ["MODEL_HARD"]
    assert "GEMINI_API_KEY" not in cd._gia_tri


def test_kiem_bang_gia_tri_dang_luu_thi_ghi_trang_thai(kho, so_kiem, monkeypatch):
    goi = {}

    async def kiem(ma, ghi_de):
        goi.update(ma=ma, ghi_de=ghi_de)
        return False, "GHN từ chối token", 33

    monkeypatch.setattr(api_kn, "kiem_dich_vu", kiem)
    asyncio.run(cd.dat("GHN_TOKEN", "t" * 20, sua_boi="qt"))
    asyncio.run(cd.dat("GHN_SHOP_ID", "777", sua_boi="qt"))
    r = _app("cau_hinh.sua").post("/api/ket-noi/dich-vu/ghn/kiem-tra", json={"gia_tri": {}})
    assert r.json()["da_ghi"] is True and r.json()["trang_thai"] == kn.LOI
    assert so_kiem["ghn"]["dau_van_tay"] == kn.dau_van_tay("ghn")
    assert so_kiem["ghn"]["kiem_boi"] == "qt"


def test_kiem_bang_gia_tri_vua_go_thi_khong_ghi(kho, so_kiem, monkeypatch):
    """Dán khoá KHÁC vào ô rồi thấy xanh — không được đóng dấu xanh cho khoá đang lưu."""
    nhan = {}

    async def kiem(ma, ghi_de):
        nhan.update(ghi_de)
        return True, "ok", 5

    monkeypatch.setattr(api_kn, "kiem_dich_vu", kiem)
    asyncio.run(cd.dat("GHN_TOKEN", "t" * 20, sua_boi="qt"))
    r = _app("cau_hinh.sua").post("/api/ket-noi/dich-vu/ghn/kiem-tra",
                                  json={"gia_tri": {"GHN_TOKEN": "CHUA-LUU-" + "z" * 12}})
    assert r.json()["ok"] is True and r.json()["da_ghi"] is False
    assert nhan["GHN_TOKEN"].startswith("CHUA-LUU-")
    assert so_kiem == {}
    assert "CHUA-LUU" not in cd.lay("GHN_TOKEN"), "kiểm tra không được lưu gì"


def test_kiem_ghn_va_ghtk_goi_dung_ham_chi_doc_va_che_token(kho, monkeypatch):
    token = "GHN-TOKEN-bi-mat-0001"

    async def ghn_kiem(*, token, shop_id, **kw):
        return False, f"401 token {token} sai", 9

    monkeypatch.setattr(api_kn.ghn, "kiem_ket_noi", ghn_kiem)
    ok, ct, _ = asyncio.run(api_kn.kiem_dich_vu("ghn", {"GHN_TOKEN": token, "GHN_SHOP_ID": "1"}))
    assert not ok and token not in ct

    async def ghtk_kiem(*, token, ma_doi_tac="", **kw):
        return True, "ok", 3

    monkeypatch.setattr(api_kn.ghtk, "kiem_ket_noi", ghtk_kiem)
    assert asyncio.run(api_kn.kiem_dich_vu("ghtk", {"GHTK_TOKEN": "x" * 20}))[0] is True


def test_kiem_ai_dung_model_chat_va_endpoint_vua_go(kho, monkeypatch):
    nhan = {}

    async def kiem_khoa(**kw):
        nhan.update(kw)
        return True, "ok", 1

    monkeypatch.setattr(api_kn.llm, "kiem_khoa", kiem_khoa)
    asyncio.run(api_kn.kiem_dich_vu("ai", {
        "LLM_PROVIDER": "openai", "OPENAI_API_KEY": "sk-" + "a" * 20,
        "OPENAI_BASE_URL": "https://proxy.vi-du.vn/v1", "MODEL_CHAT": "gpt-4o"}))
    assert nhan["model"] == "gpt-4o"           # model khách thật sự gặp, không phải model rẻ
    assert nhan["base_url"] == "https://proxy.vi-du.vn/v1"
    assert nhan["provider_name"] == "openai"


def test_kiem_erpnext_bao_ro_401(kho, monkeypatch):
    import httpx

    def xu_ly(req):
        return httpx.Response(401, json={"exc": "AuthenticationError"})

    goc = httpx.AsyncClient

    class _Client(goc):
        def __init__(self, **kw):
            super().__init__(transport=httpx.MockTransport(xu_ly), **kw)

    monkeypatch.setattr(api_kn.httpx, "AsyncClient", _Client)
    ok, ct, _ = asyncio.run(api_kn.kiem_dich_vu("erpnext", {
        "ERPNEXT_URL": "http://erp.vi-du", "ERPNEXT_API_KEY": "k" * 10, "ERPNEXT_API_SECRET": "s" * 10}))
    assert not ok and "401" in ct and "s" * 10 not in ct


def test_ai_chi_khai_nha_cung_cap_llm_that_su_goi_duoc():
    """Không hứa nhà cung cấp mà `llm.complete` không có nhánh gọi."""
    ma = {n["ma"] for n in api_kn.NHA_CUNG_CAP_AI}
    assert ma == set(cd.PROVIDER_HOP_LE)
    nguon = (ROOT / "agent" / "core" / "llm.py").read_text(encoding="utf-8")
    for m in ma:
        assert f'"{m}"' in nguon[nguon.index("async def complete("):], m
    # Chỉ OpenAI có đường đổi endpoint trong mã.
    assert {n["ma"] for n in api_kn.NHA_CUNG_CAP_AI if n["endpoint"]} == {"openai"}


def test_canh_bao_model_khac_ho_nha_cung_cap(kho):
    asyncio.run(cd.dat("LLM_PROVIDER", "gemini_api", sua_boi="qt"))
    asyncio.run(cd.dat("MODEL_CHAT", "gpt-4o", sua_boi="qt"))
    asyncio.run(cd.dat("MODEL_CHEAP", "gemini-2.5-flash-lite", sua_boi="qt"))
    cb = api_kn.canh_bao_ai()
    assert len(cb) == 1 and "MODEL_CHAT" in cb[0]


def test_lich_su_ghi_ten_truong_khong_ghi_gia_tri(kho):
    asyncio.run(cd.dat("GHTK_TOKEN", "GHTK-gia-tri-bi-mat", sua_boi="lan"))
    asyncio.run(cd.xoa("GHTK_TOKEN", sua_boi="lan"))
    assert [(x["dich_vu"], x["truong"], x["hanh_dong"], x["bi_mat"], x["sua_boi"])
            for x in kho.lich_su] == [("ghtk", "GHTK_TOKEN", "dat", True, "lan"),
                                      ("ghtk", "GHTK_TOKEN", "xoa", True, "lan")]
    assert "GHTK-gia-tri-bi-mat" not in repr(kho.lich_su)


def test_ghi_lich_su_khong_co_tham_so_gia_tri():
    """Chữ ký hàm không có chỗ cho giá trị — nên không có chỗ để lỡ ghi."""
    import inspect

    tham_so = set(inspect.signature(kn.ghi_lich_su.__wrapped__ if hasattr(
        kn.ghi_lich_su, "__wrapped__") else kn.ghi_lich_su).parameters)
    assert not tham_so & {"gia_tri", "value", "gia_tri_cu", "gia_tri_moi"}
    sql = (ROOT / "agent" / "migrations" / "versions" / "0057_ket_noi_tich_hop.sql").read_text(
        encoding="utf-8")
    bang = sql[sql.index("CREATE TABLE IF NOT EXISTS lich_su_ket_noi"):]
    bang = bang[:bang.index(");")]
    assert "gia_tri" not in bang


# ------------------------------------------------------------------ webhook

@pytest.mark.parametrize("duong,ky_vong", [
    ("/webhook/shipping/ghn", ("ghn", None)),
    ("/webhook/shipping/ghtk", ("ghtk", None)),
    ("/webhook/shipping/abc", ("khac", None)),
    ("/webhook/native/meta", ("meta", None)),
    ("/webhook/native/zalo-oa/00000000-0000-0000-0000-00000000000a",
     ("zalo_oa", "00000000-0000-0000-0000-00000000000a")),
    ("/webhook/native/zalo-personal/rac", ("zalo_personal", None)),
    ("/webhook/chatwoot", ("chatwoot", None)),
    ("/webhook", ("zalocrm", None)),
])
def test_phan_loai_webhook(duong, ky_vong):
    dv, tk = kn.phan_loai_webhook(duong)
    assert (dv, str(tk) if tk else None) == ky_vong


def test_middleware_ghi_webhook_bi_tu_choi_va_khong_ghi_token(monkeypatch):
    """
    Trên app THẬT: webhook vận chuyển sai bí mật bị 401 — và lần gọi ấy phải
    vào sổ, kèm lý do đọc được, đường dẫn KHÔNG mang `?token=`.
    """
    from agent import main

    ghi: list[dict] = []

    async def ghi_webhook_nhan(**kw):
        ghi.append(kw)

    monkeypatch.setattr(kn, "ghi_webhook_nhan", ghi_webhook_nhan)
    monkeypatch.setattr(main.settings, "shipping_webhook_secret", "dung-" + "x" * 30)
    c = TestClient(main.app)
    r = c.post("/webhook/shipping/ghn?token=SAI-BI-MAT-123", json={"OrderCode": "A1"})
    assert r.status_code == 401
    assert r.json()["ok"] is False                # thân phản hồi giữ nguyên cho hãng
    assert len(ghi) == 1
    assert ghi[0]["ma_http"] == 401 and ghi[0]["duong"] == "/webhook/shipping/ghn"
    assert "không đúng" in (ghi[0]["loi"] or "")
    assert "SAI-BI-MAT" not in repr(ghi)

    r = c.post("/webhook/shipping/abc", json={})
    assert r.status_code == 404 and "không có" in (ghi[-1]["loi"] or "")


def test_middleware_bo_qua_duong_khong_phai_webhook(monkeypatch):
    from agent import main

    ghi = []

    async def ghi_webhook_nhan(**kw):
        ghi.append(kw)

    monkeypatch.setattr(kn, "ghi_webhook_nhan", ghi_webhook_nhan)
    TestClient(main.app).get("/healthz")
    assert ghi == []


# ------------------------------------------------------------------ thông báo AI

def test_noi_dung_mac_dinh_hop_le():
    from agent.config import Settings
    from agent.omnichannel import thong_bao_ai as tb

    assert tb.kiem_noi_dung(Settings.model_fields["tin_thong_bao_ai"].default) == ""


@pytest.mark.parametrize("cau,loi", [
    ('Dạ em là trợ lý của {ten}. Nhắn "gặp nhân viên" nha. Ảnh da là dữ liệu nhạy cảm.', "AI"),
    ('Dạ ai cũng được hỗ trợ ạ. Nhắn "gặp nhân viên" nha. Ảnh da là dữ liệu nhạy cảm.', "AI"),
    # "cần hỗ trợ" mã KHÔNG nhận ra: khách làm đúng hướng dẫn vẫn nói với máy.
    ('Em là trợ lý AI. Nhắn "cần hỗ trợ" nha. Dữ liệu da là nhạy cảm.', "ngoặc kép"),
    ("Em là trợ lý AI. Muốn gặp nhân viên thì cứ nói. Dữ liệu da là nhạy cảm.", "ngoặc kép"),
    ('Em là trợ lý AI của {ten_shop}. Nhắn "gặp nhân viên". Dữ liệu nhạy cảm.', "{ten}"),
    ('Em là trợ lý AI {. Nhắn "gặp nhân viên". Dữ liệu nhạy cảm.', "{ten}"),
    ('Em là trợ lý AI. Nhắn "gặp nhân viên" nha.', "nhạy cảm"),
    ('Em là trợ lý AI 24/7. Nhắn "gặp nhân viên". Dữ liệu nhạy cảm.', "24/7"),
    ("", "trống"),
])
def test_noi_dung_sai_bi_chan(cau, loi):
    from agent.omnichannel import thong_bao_ai as tb

    kq = tb.kiem_noi_dung(cau)
    assert kq and loi in kq, (cau, kq)


def test_luu_noi_dung_sai_bi_422_va_dung_thi_khach_nhan_cau_moi(kho, so_kiem, monkeypatch):
    from agent.core import tools
    from agent.omnichannel import thong_bao_ai as tb

    monkeypatch.setattr(tools, "ten_thuong_hieu", lambda: "BLANICA")
    c = _app("cau_hinh.sua")
    r = c.put("/api/ket-noi/dich-vu/thong_bao_ai",
              json={"gia_tri": {"TIN_THONG_BAO_AI": 'Em là bot. Nhắn "cần hỗ trợ".'}})
    assert r.json()["da_luu"] == [] and r.json()["hong"]
    moi = ('Chào bạn, mình là trợ lý AI của {ten}. Cần người thật thì nhắn "chuyển nhân viên" '
           'nhé. Ảnh da bạn gửi là dữ liệu nhạy cảm, shop giữ bảo mật.')
    r = c.put("/api/ket-noi/dich-vu/thong_bao_ai", json={"gia_tri": {"TIN_THONG_BAO_AI": moi}})
    assert r.json()["da_luu"] == ["TIN_THONG_BAO_AI"]
    assert tb.cau_thong_bao() == moi.format(ten="BLANICA")
    # Cụm hướng dẫn trong câu MỚI vẫn được mã giữ lời.
    assert tb.khach_doi_gap_nguoi("chuyển nhân viên")


def test_noi_dung_env_hong_thi_lui_ve_mac_dinh_khong_im(monkeypatch, caplog):
    from agent.core import tools
    from agent.omnichannel import thong_bao_ai as tb

    monkeypatch.setattr(tools, "ten_thuong_hieu", lambda: "BLANICA")
    monkeypatch.setattr(cd, "lay", lambda k: "Em là AI của {shop}" if k == "TIN_THONG_BAO_AI" else "")
    cau = tb.cau_thong_bao()
    assert "trợ lý AI của BLANICA" in cau
    assert any("TIN_THONG_BAO_AI" in r.message for r in caplog.records)


# ------------------------------------------------------------------ hiệu lực ngay

def test_model_chat_tren_dashboard_co_hieu_luc(kho, monkeypatch):
    """Đổi MODEL_CHAT trên dashboard mà agent vẫn chạy model cũ là hỏng im lặng."""
    from agent.core import agent as brain
    from agent.core import llm

    asyncio.run(cd.dat("MODEL_CHAT", "gpt-4o-mini", sua_boi="qt"))
    assert brain._model_chat() == "gpt-4o-mini"
    nguon = (ROOT / "agent" / "core" / "agent.py").read_text(encoding="utf-8")
    assert "model=settings.model_chat" not in nguon

    nhan = {}

    async def gia_openai(**kw):
        nhan.update(kw)
        return llm.LLMResult(text="ok", model=kw["model"])

    monkeypatch.setattr(llm, "provider", lambda: "openai")
    monkeypatch.setattr(llm, "_complete_openai", gia_openai)
    asyncio.run(llm.complete(system={"stable": "x"}, messages=[]))
    assert nhan["model"] == "gpt-4o-mini"


def test_token_ghn_doi_tren_dashboard_khong_can_khoi_dong_lai(kho):
    from agent.shipping.ghn import GHNShippingProvider

    p = GHNShippingProvider()                   # dựng TRƯỚC khi đổi, như cache thật
    asyncio.run(cd.dat("GHN_TOKEN", "TOKEN-MOI-" + "9" * 10, sua_boi="qt"))
    asyncio.run(cd.dat("GHN_SHOP_ID", "4242", sua_boi="qt"))
    assert p._token.startswith("TOKEN-MOI-") and p._shop_id == "4242"
    assert GHNShippingProvider(token="co-dinh")._token == "co-dinh"


def test_doi_khoa_erpnext_bo_cong_cu(monkeypatch):
    from agent.erp import nha_may

    monkeypatch.setattr(nha_may, "_cong", object())
    cd._sau_khi_doi("ERPNEXT_API_KEY")
    assert nha_may._cong is None
    monkeypatch.setattr(nha_may, "_cong", "giu")
    cd._sau_khi_doi("GHN_TOKEN")
    assert nha_may._cong == "giu"


# ------------------------------------------------------------------ bình luận theo Trang

@pytest.mark.parametrize("rieng,chung,ky_vong", [
    ("bat", "tat", "bat"), ("tat", "bat", "tat"), (None, "bat", "bat"), (None, "tat", "tat"),
])
def test_tuy_chon_rieng_cua_trang_thang_cau_hinh_chung(monkeypatch, rieng, chung, ky_vong):
    from agent.omnichannel import xu_ly_tin_vao as x

    async def fetchrow(sql, *a):
        assert "metadata->>" in sql
        return {"v": rieng}

    monkeypatch.setattr(x.db, "fetchrow", fetchrow)
    monkeypatch.setattr(x.cau_hinh_dong, "lay", lambda k: chung if k == "AN_BINH_LUAN_CO_SDT" else "")
    assert asyncio.run(x.che_do_an_binh_luan(uuid4())) == ky_vong


def test_tuy_chon_trang_doc_hong_thi_lui_ve_chung_co_canh_bao(monkeypatch, caplog):
    from agent.omnichannel import xu_ly_tin_vao as x

    async def hong(*a, **k):
        raise ConnectionError("CSDL rớt")

    monkeypatch.setattr(x.db, "fetchrow", hong)
    monkeypatch.setattr(x.cau_hinh_dong, "lay", lambda k: "bat")
    assert asyncio.run(x.che_do_an_binh_luan(uuid4())) == "bat"
    assert any("tuỳ chọn riêng" in r.getMessage() for r in caplog.records)


def test_tuy_chon_trang_can_quyen_kenh_sua():
    c = _app("cau_hinh.sua")
    r = c.put(f"/api/ket-noi/kenh/{uuid4()}/tuy-chon", json={"an_binh_luan_co_sdt": "bat"})
    assert r.status_code == 403
    c = _app("kenh.sua")
    assert c.put(f"/api/ket-noi/kenh/{uuid4()}/tuy-chon",
                 json={"an_binh_luan_co_sdt": "co_le"}).status_code == 422


# ------------------------------------------------------------------ giao diện

def test_giao_dien_gan_tab_va_khong_dung_lai_moi_nhip():
    src22 = (ROOT / "dashboard" / "src" / "22-ket-noi-tich-hop.js").read_text(encoding="utf-8")
    src23 = (ROOT / "dashboard" / "src" / "23-ai-co-ban.js").read_text(encoding="utf-8")
    assert 'window.GAN_TAB["cc-ket-noi"]' in src22
    assert 'window.GAN_TAB["ai-co-ban-nha-cung-cap"]' in src23
    # Khung tab (01b-dieu-huong.js `ganKhe`) có đúng hai khe để gắn vào.
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert 'data-gan="cc-ket-noi"' in html and 'data-gan="ai-co-ban-nha-cung-cap"' in html
    vong = (ROOT / "dashboard" / "src" / "10-vong-lam-moi.js").read_text(encoding="utf-8")
    # Gắn MỘT lần (ganKhe), KHÔNG gọi thẳng ganKetNoiTichHop mỗi nhịp 6 giây
    # — làm thế là xoá khoá đang dán dở.
    assert "ganKetNoiTichHop" not in vong
    # Ô bí mật không bao giờ được dựng với value.
    assert 'type="password" autocomplete="off" data-kntt-khoa' in src22
