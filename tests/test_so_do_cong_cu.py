# tests/test_so_do_cong_cu.py
"""run_tool ghi một sự kiện `cong_cu.goi` mỗi lần gọi; ghi hỏng không hỏng kết quả."""
from __future__ import annotations

import asyncio

import pytest

from agent.core import thu_nghiem, tools


def chay(coro):
    return asyncio.run(coro)


def test_moi_lan_goi_ghi_su_kien(monkeypatch):
    ghi = []

    async def log_event(kind, **kw): ghi.append((kind, kw))
    async def that(name, args, conversation_id=None): return {"tim_thay": True}

    monkeypatch.setattr(tools.db, "log_event", log_event)
    monkeypatch.setattr(tools, "_run_tool_that", that)
    monkeypatch.setattr(tools, "_goi_cua", lambda name: "goi-a")
    kq = chay(tools.run_tool("bang_thanh_phan_ne", {"thanh_phan": "cồn"}))
    assert kq == {"tim_thay": True}
    kind, kw = ghi[0]
    assert kind == "cong_cu.goi" and kw["ten"] == "bang_thanh_phan_ne" and kw["goi"] == "goi-a"
    assert kw["ok"] is True and kw["ms"] >= 0 and kw["thu_nghiem"] is False


def test_loi_cong_cu_ghi_ok_false_va_sandbox_danh_dau(monkeypatch):
    ghi = []

    async def log_event(kind, **kw): ghi.append(kw)
    async def that(name, args, conversation_id=None): return {"loi": "hỏng", "ghi_chu": "x"}

    monkeypatch.setattr(tools.db, "log_event", log_event)
    monkeypatch.setattr(tools, "_run_tool_that", that)
    monkeypatch.setattr(tools, "_goi_cua", lambda name: None)
    with thu_nghiem.bat_thu():
        chay(tools.run_tool("x", {}))
    assert ghi[0]["ok"] is False and ghi[0]["thu_nghiem"] is True and ghi[0]["goi"] is None


def test_ghi_so_do_hong_khong_lam_hong_ket_qua(monkeypatch):
    async def log_event(kind, **kw): raise RuntimeError("CSDL sập")
    async def that(name, args, conversation_id=None): return {"tim_thay": True}

    monkeypatch.setattr(tools.db, "log_event", log_event)
    monkeypatch.setattr(tools, "_run_tool_that", that)
    monkeypatch.setattr(tools, "_goi_cua", lambda name: None)
    assert chay(tools.run_tool("x", {})) == {"tim_thay": True}


def test_cong_cu_nem_van_ghi_so_do_roi_nem_lai(monkeypatch):
    """
    `_run_tool_that` trả `{"loi": ...}` ở những đường hỏng nó lường trước,
    nhưng nó cũng NÉM (plugin http hết giờ, CSDL sập, lỗi lập trình). Nhánh
    ném không ghi dòng nào thì bảng số đo hiện "0 lỗi" cho đúng công cụ đang
    hỏng ở mọi lần gọi — xanh giả, và không ai đi kiểm cái đang xanh.
    """
    ghi = []

    async def log_event(kind, **kw): ghi.append(kw)
    async def that(name, args, conversation_id=None): raise TimeoutError("plugin không trả lời")

    monkeypatch.setattr(tools.db, "log_event", log_event)
    monkeypatch.setattr(tools, "_run_tool_that", that)
    monkeypatch.setattr(tools, "_goi_cua", lambda name: "goi-a")

    with pytest.raises(TimeoutError):
        chay(tools.run_tool("bang_thanh_phan_ne", {}))

    assert len(ghi) == 1
    assert ghi[0]["ok"] is False and ghi[0]["loi"] == "TimeoutError"
    assert ghi[0]["ten"] == "bang_thanh_phan_ne" and ghi[0]["goi"] == "goi-a"


def test_ghi_so_do_hong_o_nhanh_nem_khong_che_loi_goc(monkeypatch):
    """Số đo hỏng không được nuốt mất lỗi thật của công cụ."""
    async def log_event(kind, **kw): raise RuntimeError("CSDL sập")
    async def that(name, args, conversation_id=None): raise ValueError("tham số sai")

    monkeypatch.setattr(tools.db, "log_event", log_event)
    monkeypatch.setattr(tools, "_run_tool_that", that)
    monkeypatch.setattr(tools, "_goi_cua", lambda name: None)

    with pytest.raises(ValueError, match="tham số sai"):
        chay(tools.run_tool("x", {}))


def test_chay_py_van_khong_ghi_csdl():
    """Số đo phải nằm ở run_tool, không ở chay.py — test AST hiện có canh, đây là nhắc."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "agent" / "ky_nang" / "chay.py").read_text(encoding="utf-8")
    assert "log_event" not in src
