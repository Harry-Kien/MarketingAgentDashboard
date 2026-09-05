"""
Đổi provider sang gemini_api thì embedding cũng phải đi bằng API key — và
kho tri thức nạp bằng model A mà hỏi bằng model B là tìm sai trong im lặng.
"""
from __future__ import annotations

import asyncio
import inspect

import httpx

from agent import cau_hinh_dong as cd
from agent.config import settings
from agent.core import rag


def test_model_embedding_theo_provider(monkeypatch):
    cd._gia_tri.clear()
    monkeypatch.setattr(settings, "llm_provider", "gemini_api")
    assert rag.embed_model_hien_hanh() == rag.EMBED_MODEL_API
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    assert rag.embed_model_hien_hanh() == rag.EMBED_MODEL


def test_embed_gemini_api_ep_768_chieu_va_dung_api_key(monkeypatch):
    cd._gia_tri.clear()
    cd._gia_tri["GEMINI_API_KEY"] = "AIzaTEST"
    goi = {}

    async def post(self, url, headers=None, json=None):
        goi["url"], goi["headers"], goi["body"] = url, headers, json
        return httpx.Response(200, json={"embeddings": [{"values": [0.1] * 768}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    vec = asyncio.run(rag._embed_gemini_api(["xin chào"], "RETRIEVAL_QUERY"))
    assert len(vec) == 1 and len(vec[0]) == rag.EMBED_DIM
    assert goi["headers"]["x-goog-api-key"] == "AIzaTEST"
    assert ":batchEmbedContents" in goi["url"]
    yeu_cau = goi["body"]["requests"][0]
    assert yeu_cau["outputDimensionality"] == rag.EMBED_DIM
    assert yeu_cau["taskType"] == "RETRIEVAL_QUERY"


def test_embed_tai_lieu_ghi_model_dang_dung(monkeypatch):
    """Ghi lúc nạp tài liệu, không ghi lúc hỏi: hỏi thì không đổi kho."""
    ghi = []

    async def execute(sql, *args):
        ghi.append(args)

    async def gia(texts, task):
        return [[0.0] * rag.EMBED_DIM for _ in texts]

    monkeypatch.setattr(rag.db, "execute", execute)
    monkeypatch.setattr(rag, "_embed_sync", lambda texts, task: [[0.0] * rag.EMBED_DIM for _ in texts])
    monkeypatch.setattr(rag, "_embed_gemini_api", gia)
    rag._da_ghi_model = None
    asyncio.run(rag.embed(["a"], query=True))
    assert ghi == []
    asyncio.run(rag.embed(["a"]))
    assert ghi and ghi[0][0] == rag.embed_model_hien_hanh()
    asyncio.run(rag.embed(["b"]))
    assert len(ghi) == 1, "ghi lặp mỗi lô là tốn một lượt CSDL vô ích"


def test_ghi_model_hong_khong_lam_mat_vector(monkeypatch, caplog):
    """CSDL sập lúc ghi bookkeeping không được vứt mất vector vừa nhúng."""

    async def sap(sql, *args):
        raise RuntimeError("CSDL sập")

    # Ghim provider Vertex TƯỜNG MINH: mặc định xuất xưởng nay là gemini_api,
    # và máy CI không có .env — để mặc định quyết định là test đi nhánh
    # Gemini API rồi gọi mạng thật. Đã đỏ trên CI đúng vì thế (05.09.2026).
    cd._gia_tri.clear()
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(
        rag, "_embed_sync", lambda texts, task: [[0.0] * rag.EMBED_DIM for _ in texts]
    )
    monkeypatch.setattr(rag.db, "execute", sap)
    rag._da_ghi_model = None
    with caplog.at_level("ERROR", logger="agent.rag"):
        vec = asyncio.run(rag.embed(["a"]))
    assert len(vec) == 1 and len(vec[0]) == rag.EMBED_DIM
    assert any(
        "embed_model_dang_dung" in r.message or "CSDL sập" in r.message
        for r in caplog.records
    )


def test_so_vector_lech_so_van_ban_thi_no_to(monkeypatch):
    cd._gia_tri.clear()
    cd._gia_tri["GEMINI_API_KEY"] = "AIzaTEST"
    monkeypatch.setattr(settings, "llm_provider", "gemini_api")
    cd._gia_tri.pop("LLM_PROVIDER", None)
    monkeypatch.setattr(rag, "_LAN_THU_EMBED", 1)

    async def post(self, url, headers=None, json=None):
        return httpx.Response(
            200,
            json={"embeddings": [{"values": [0.1] * 768}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    try:
        asyncio.run(rag.embed(["a", "b"], query=True))
        raise AssertionError("phải raise RuntimeError vì lệch số vector")
    except RuntimeError as exc:
        assert "1" in str(exc) and "2" in str(exc)


def test_suc_khoe_bao_do_khi_kho_nap_bang_model_khac(monkeypatch):
    from agent import suc_khoe

    async def fetchrow(sql, *args):
        return {"gia_tri": "model-cu"}

    monkeypatch.setattr(suc_khoe.db, "fetchrow", fetchrow)
    m = asyncio.run(suc_khoe._kiem_embedding_khop())
    assert m["trang_thai"] == suc_khoe.HONG
    assert "model-cu" in m["ghi_chu"] and "Nạp lại" in m["ghi_chu"]


def test_suc_khoe_chua_ghi_nhan_lan_nap_ma_doi_provider_thi_canh_bao(monkeypatch):
    """
    Không có dòng `embed_model_dang_dung` KHÔNG có nghĩa là yên tâm: kho nạp
    trước khi có bookkeeping không để lại dấu vết, và mọi kho như vậy dùng
    EMBED_MODEL mặc định. Bản trước báo TỐT cho đúng cảnh đổi provider xong
    chưa nạp lại — xanh giả ngay trong mục canh xanh giả.
    """
    from agent import suc_khoe
    from agent.core import rag

    async def fetchrow(sql, *args):
        return None

    monkeypatch.setattr(suc_khoe.db, "fetchrow", fetchrow)
    monkeypatch.setattr(rag, "embed_model_hien_hanh", lambda: rag.EMBED_MODEL_API)
    m = asyncio.run(suc_khoe._kiem_embedding_khop())
    assert m["trang_thai"] == suc_khoe.CANH_BAO
    assert rag.EMBED_MODEL in m["ghi_chu"] and "Nạp lại" in m["ghi_chu"]


def test_suc_khoe_chua_ghi_nhan_lan_nap_va_van_model_mac_dinh_thi_tot(monkeypatch):
    from agent import suc_khoe
    from agent.core import rag

    async def fetchrow(sql, *args):
        return None

    monkeypatch.setattr(suc_khoe.db, "fetchrow", fetchrow)
    monkeypatch.setattr(rag, "embed_model_hien_hanh", lambda: rag.EMBED_MODEL)
    m = asyncio.run(suc_khoe._kiem_embedding_khop())
    assert m["trang_thai"] == suc_khoe.TOT


def test_suc_khoe_kiem_model_di_qua_kiem_khoa():
    from agent import suc_khoe

    assert "kiem_khoa(" in inspect.getsource(suc_khoe._kiem_model)


def test_kiem_embedding_nam_trong_tong_kiem():
    from agent import suc_khoe

    assert "_kiem_embedding_khop()" in inspect.getsource(suc_khoe.tong_kiem)
