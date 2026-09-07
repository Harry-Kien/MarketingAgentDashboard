# tests/test_goi_ky_nang_respond.py
"""Hướng dẫn gói vào khối BIẾN ĐỘNG, không vào SYSTEM; Reply ghi tên gói."""
from __future__ import annotations

import asyncio
import uuid

import pytest

from agent.core import agent as brain
from agent.core.llm import LLMResult
from agent.ky_nang import goi as g


def chay(coro):
    return asyncio.run(coro)


@pytest.fixture
def san(monkeypatch):
    hop = {"system": None}

    async def fetchrow(sql, *a): return {"cost_usd": 0.0}
    async def con_ngan_sach(): return True, 0.0, 0.0
    async def retrieve(q, k=5): return []
    async def cong_cu_dang_bat(tat_ca): return tat_ca
    async def complete(**kw):
        hop["system"] = kw["system"]
        return LLMResult(text="Dạ em hỏi thêm chút ạ.", model="m", cost_usd=0.01)
    async def huong_dan(cau_hoi): return [("tu-van-da-nhay-cam", "Hỏi tiền sử kích ứng trước.")]

    monkeypatch.setattr(brain.db, "fetchrow", fetchrow)
    monkeypatch.setattr(brain.ngan_sach, "con_ngan_sach", con_ngan_sach)
    monkeypatch.setattr(brain.ngan_sach, "ghi_nhan", lambda c: None)
    monkeypatch.setattr(brain.rag, "retrieve", retrieve)
    monkeypatch.setattr(brain.rag, "as_context", lambda p: "NGU CANH RAG")
    monkeypatch.setattr(brain.kho_ky_nang, "cong_cu_dang_bat", cong_cu_dang_bat)
    monkeypatch.setattr(brain.llm, "complete", complete)
    monkeypatch.setattr(g, "huong_dan_cho_luot", huong_dan)
    return hop


def test_huong_dan_vao_khoi_bien_dong(san):
    r = chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="da em nhạy cảm"))
    sys_ = san["system"]
    assert sys_["stable"] == brain.SYSTEM
    assert "Hướng dẫn kỹ năng «tu-van-da-nhay-cam»" in sys_["volatile"]
    assert "Hỏi tiền sử kích ứng trước." in sys_["volatile"] and "NGU CANH RAG" in sys_["volatile"]
    assert r.goi_ky_nang == ["tu-van-da-nhay-cam"]
    # Phải có dòng phân tách: ghép suông thì mô hình đọc hướng dẫn nội bộ như
    # một tài liệu tham chiếu và trích nguyên văn quy trình cho khách.
    vol = sys_["volatile"]
    assert "HƯỚNG DẪN NỘI BỘ (không phải tài liệu để trích dẫn):" in vol
    assert vol.index("NGU CANH RAG") < vol.index("HƯỚNG DẪN NỘI BỘ") < vol.index("Hướng dẫn kỹ năng")


def test_khong_goi_nao_thi_khong_them_gi(san, monkeypatch):
    async def rong(cau_hoi): return []
    monkeypatch.setattr(g, "huong_dan_cho_luot", rong)
    r = chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="giá?"))
    assert "Hướng dẫn kỹ năng" not in san["system"]["volatile"] and r.goi_ky_nang == []


def test_phong_thu_tra_goi_ky_nang():
    from agent.api.phong_thu_agent import reply_thanh_dict
    d = reply_thanh_dict(brain.Reply(text="x", goi_ky_nang=["a"]))
    assert d["goi_ky_nang"] == ["a"]
