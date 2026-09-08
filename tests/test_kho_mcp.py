"""
Kho máy chủ MCP: CSDL giả ghi lại SQL. Không mạng, không Postgres.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def chay(coro):
    return asyncio.run(coro)


def test_migration_0016_tao_bang_mcp_may_chu():
    sql = (ROOT / "agent" / "migrations" / "versions" / "0016_mcp_may_chu.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS mcp_may_chu" in sql
    for cot in ("ten", "nhan", "dia_chi", "bat", "key_version", "nonce", "ciphertext", "suc_khoe", "tao_boi"):
        assert re.search(rf"^\s+{cot}\s", sql, re.M), cot


def test_env_example_va_settings_co_bien_noi_bo():
    from agent.config import Settings

    assert "mcp_may_chu_noi_bo" in Settings.model_fields
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "MCP_MAY_CHU_NOI_BO=" in env
