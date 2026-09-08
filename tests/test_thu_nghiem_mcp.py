"""
Công cụ MCP GHI: trong sandbox không gọi thật; ngoài sandbox chưa cho phép
thì chuyển người. Bộ dò AST của test_thu_nghiem chỉ thấy tên tĩnh, nên chốt
động này có test riêng.
"""
from __future__ import annotations

import asyncio

import pytest

from agent.core import thu_nghiem, tools
from agent.ky_nang import kho_ky_nang
from agent.ky_nang.ban_mo_ta import doc_ban_mo_ta


def chay(coro):
    return asyncio.run(coro)


def _bm(ghi: bool, ghi_cho_phep: bool = False):
    return doc_ban_mo_ta({
        "ten": "mcp_kho_ghi_don", "loai": "mcp",
        "mo_ta": "Tạo đơn thử trên máy chủ kho. Chỉ dùng khi khách chốt rõ.",
        "tham_so": [],
        "cau_hinh": {"may_chu": "kho", "cong_cu_goc": "ghi_don",
                     "luoc_do": {"type": "object", "properties": {}}, "ghi": ghi, "ghi_cho_phep": ghi_cho_phep},
    })


@pytest.fixture
def san(monkeypatch):
    goi = []

    async def goi_cong_cu(bm, args):
        goi.append(bm.ten); return {"ket_qua": "đã ghi", "du_lieu": None, "ghi_chu": "x"}

    async def dang_tat(ten): return False
    async def log_event(kind, **kw): return None

    from agent.ky_nang import kho_mcp
    monkeypatch.setattr(kho_mcp, "goi_cong_cu", goi_cong_cu)
    monkeypatch.setattr(kho_ky_nang, "dang_tat", dang_tat)
    monkeypatch.setattr(tools.db, "log_event", log_event)
    return goi


def test_ghi_trong_sandbox_khong_goi_that(san, monkeypatch):
    async def tim(ten): return _bm(ghi=True, ghi_cho_phep=True)
    monkeypatch.setattr(kho_ky_nang, "tim_plugin", tim)
    with thu_nghiem.bat_thu():
        kq = chay(tools.run_tool("mcp_kho_ghi_don", {"ma": "x"}))
    assert kq["thu_nghiem"] is True and kq["mo_phong"] is True and san == []


def test_ghi_ngoai_sandbox_chua_cho_phep_thi_chuyen_nguoi(san, monkeypatch):
    async def tim(ten): return _bm(ghi=True, ghi_cho_phep=False)
    monkeypatch.setattr(kho_ky_nang, "tim_plugin", tim)
    kq = chay(tools.run_tool("mcp_kho_ghi_don", {"ma": "x"}))
    assert kq["can_chuyen_nhan_vien"] is True and san == []


def test_ghi_da_cho_phep_thi_goi_that(san, monkeypatch):
    async def tim(ten): return _bm(ghi=True, ghi_cho_phep=True)
    monkeypatch.setattr(kho_ky_nang, "tim_plugin", tim)
    kq = chay(tools.run_tool("mcp_kho_ghi_don", {"ma": "x"}))
    assert kq["ket_qua"] == "đã ghi" and san == ["mcp_kho_ghi_don"]


def test_doc_trong_sandbox_van_goi_that(san, monkeypatch):
    async def tim(ten): return _bm(ghi=False)
    monkeypatch.setattr(kho_ky_nang, "tim_plugin", tim)
    with thu_nghiem.bat_thu():
        kq = chay(tools.run_tool("mcp_kho_ghi_don", {}))
    assert kq["ket_qua"] == "đã ghi"
