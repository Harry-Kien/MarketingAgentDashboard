"""
Kho gói kỹ năng: cài, bật tắt, xoá, khôi phục — CSDL giả ghi lại SQL.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def chay(coro):
    return asyncio.run(coro)


def test_migration_0014_tao_du_bang_va_cot():
    sql = (ROOT / "agent" / "migrations" / "versions" / "0014_goi_ky_nang.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS goi_ky_nang" in sql
    assert "CREATE TABLE IF NOT EXISTS goi_ky_nang_lich_su" in sql
    assert re.search(r"ALTER TABLE ky_nang_cai_dat ADD COLUMN IF NOT EXISTS goi TEXT", sql)


def test_rag_xoa_nguon_theo_tien_to(monkeypatch):
    from agent.core import rag

    sql_da_chay = []

    async def execute(sql, *a):
        sql_da_chay.append((" ".join(sql.split()), a))
        return "DELETE 3"

    monkeypatch.setattr(rag.db, "execute", execute)
    n = chay(rag.xoa_nguon("goi:abc:"))
    assert n == 3
    assert "DELETE FROM documents WHERE source LIKE $1" in sql_da_chay[0][0]
    assert sql_da_chay[0][1] == ("goi:abc:%",)


def test_reply_co_goi_ky_nang_mac_dinh_rong():
    from agent.core.agent import Reply

    assert Reply(text="x").goi_ky_nang == []
