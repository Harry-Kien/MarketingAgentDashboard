"""
Provider `gemini_api`: chỉ cần API key, không cần GCP. Không gọi API thật.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from agent import cau_hinh_dong as cd
from agent.config import settings
from agent.core import llm


@pytest.fixture(autouse=True)
def _sach(monkeypatch):
    cd._gia_tri.clear()
    llm.xoa_cache_client()
    monkeypatch.setattr(settings, "llm_provider", "gemini_api")
    monkeypatch.setattr(settings, "gcp_project_id", "your-gcp-project-id")


def test_dich_gemini_api_dung_url_va_header(monkeypatch):
    cd._gia_tri["GEMINI_API_KEY"] = "AIzaTEST"
    url, headers = asyncio.run(llm._gemini_dich("gemini-2.5-flash"))
    assert url == f"{llm.GEMINI_API_GOC}/models/gemini-2.5-flash:generateContent"
    assert headers["x-goog-api-key"] == "AIzaTEST"
    assert "Authorization" not in headers


def test_thieu_khoa_thi_noi_ro_cho_nhap():
    with pytest.raises(RuntimeError) as e:
        asyncio.run(llm._gemini_dich("gemini-2.5-flash"))
    assert "GEMINI_API_KEY" in str(e.value)
    assert "Cài đặt API" in str(e.value)


def test_provider_doc_tu_cau_hinh_dong():
    cd._gia_tri["LLM_PROVIDER"] = "anthropic"
    assert llm.provider() == "anthropic"
    cd._gia_tri.clear()
    assert llm.provider() == "gemini_api"


def test_complete_gemini_api_khong_can_gcp(monkeypatch):
    """Điều kiện `GCP_PROJECT_ID` từng chặn ngay đầu hàm — với API key nó vô nghĩa."""
    cd._gia_tri["GEMINI_API_KEY"] = "AIzaTEST"
    goi = {}

    async def post(self, url, headers=None, json=None):
        goi["url"], goi["headers"] = url, headers
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
        }, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    r = asyncio.run(llm.complete(
        system=llm.cached_system("x"), messages=[{"role": "user", "content": "ok?"}],
        model="gemini-2.5-flash-lite", max_tokens=8,
    ))
    assert r.text == "ok"
    assert goi["headers"]["x-goog-api-key"] == "AIzaTEST"


def test_kiem_khoa_dung_gia_tri_truyen_vao_khong_dung_cau_hinh(monkeypatch):
    cd._gia_tri["GEMINI_API_KEY"] = "KHOA-DANG-LUU"
    goi = {}

    async def post(self, url, headers=None, json=None):
        goi["key"] = headers["x-goog-api-key"]
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
        }, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    ok, chi_tiet, ms = asyncio.run(llm.kiem_khoa(
        provider_name="gemini_api", api_key="KHOA-MOI-CHUA-LUU", model="gemini-2.5-flash-lite",
    ))
    assert ok and goi["key"] == "KHOA-MOI-CHUA-LUU"
    assert "gemini-2.5-flash-lite" in chi_tiet


def test_kiem_khoa_het_han_muc_noi_ro(monkeypatch):
    async def post(self, url, headers=None, json=None):
        return httpx.Response(429, text="RESOURCE_EXHAUSTED", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr(llm, "MAX_RETRIES", 1)
    ok, chi_tiet, _ = asyncio.run(llm.kiem_khoa(
        provider_name="gemini_api", api_key="k", model="gemini-2.5-flash-lite",
    ))
    assert not ok and "HẾT HẠN MỨC" in chi_tiet


def test_kiem_khoa_anthropic_khong_de_khoa_chua_luu_lai_trong_cache(monkeypatch):
    """
    Thử một khoá rồi KHÔNG bấm Lưu: khoá ấy không được nằm lại trong cache
    client của tiến trình. `xoa_cache_client()` chỉ chạy khi có người đổi
    cấu hình, nên "rớt lại" ở đây nghĩa là có thể rớt lại mãi mãi.
    """
    class _Anthropic:
        def __init__(self, api_key):
            self.api_key = api_key

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _Anthropic)

    async def _complete_claude(**kw):
        return llm.LLMResult(text="ok", model="claude", latency_ms=1)

    monkeypatch.setattr(llm, "_complete_claude", _complete_claude)
    khoa_chua_luu = "k-chua-luu" + "x" * 20
    ok, _, _ = asyncio.run(llm.kiem_khoa(
        provider_name="anthropic", api_key=khoa_chua_luu, model="claude-sonnet-4-5",
    ))
    assert ok
    assert khoa_chua_luu not in repr(llm._ANTHROPIC_CACHE)


def test_xoa_cache_client_lam_dung_lai_client_anthropic(monkeypatch):
    dung = []

    class _Anthropic:
        def __init__(self, api_key):
            dung.append(api_key)

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _Anthropic)
    cd._gia_tri["LLM_PROVIDER"] = "anthropic"
    cd._gia_tri["ANTHROPIC_API_KEY"] = "k1"
    llm._anthropic_client()
    llm._anthropic_client()
    assert dung == ["k1"]
    cd._gia_tri["ANTHROPIC_API_KEY"] = "k2"
    llm.xoa_cache_client()
    llm._anthropic_client()
    assert dung == ["k1", "k2"]
