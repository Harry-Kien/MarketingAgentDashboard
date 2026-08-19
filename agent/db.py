"""Kết nối Postgres. Một pool duy nhất, khởi tạo lược đồ khi app start."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import asyncpg

from agent.config import settings

_pool: asyncpg.Pool | None = None


async def init_db() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool

    async def _setup(conn: asyncpg.Connection) -> None:
        # Mặc định asyncpg trả JSONB về dạng CHUỖI. Không đặt codec thì
        # `sources` và `scenes` sang tới dashboard là string, và mọi thao tác
        # mảng phía JS sẽ hỏng. Đặt một lần ở đây cho toàn hệ thống.
        await conn.set_type_codec(
            "jsonb",
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )

    _pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=1,
        max_size=10,
        command_timeout=30,
        init=_setup,
    )
    schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    async with _pool.acquire() as conn:
        await conn.execute(schema)
    return _pool


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Chưa gọi init_db()")
    return _pool


async def fetch(sql: str, *args: Any) -> list[dict]:
    async with pool().acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return [dict(r) for r in rows]


async def fetchrow(sql: str, *args: Any) -> dict | None:
    async with pool().acquire() as conn:
        row = await conn.fetchrow(sql, *args)
    return dict(row) if row else None


async def execute(sql: str, *args: Any) -> str:
    async with pool().acquire() as conn:
        return await conn.execute(sql, *args)


async def log_event(kind: str, *, actor: str = "system", ref_id=None, **detail) -> None:
    """Ghi nhật ký kiểm toán. Không bao giờ để lỗi log làm hỏng luồng chính."""
    try:
        await execute(
            "INSERT INTO events (kind, actor, ref_id, detail) VALUES ($1,$2,$3,$4)",
            kind,
            actor,
            ref_id,
            detail,   # codec JSONB tu ma hoa — KHONG dumps thu cong
        )
    except Exception:  # noqa: BLE001
        pass


async def seen_webhook(key: str) -> bool:
    """Chống trùng: ZaloCRM có thể gửi lại cùng một tin nhắn."""
    async with pool().acquire() as conn:
        inserted = await conn.fetchval(
            "INSERT INTO processed_webhooks (message_key) VALUES ($1) "
            "ON CONFLICT DO NOTHING RETURNING message_key",
            key,
        )
    return inserted is None
