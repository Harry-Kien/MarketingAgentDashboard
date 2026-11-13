"""Không giữ pool nửa khởi tạo sau lỗi schema/migration."""
import asyncio
from contextlib import asynccontextmanager

import pytest

from agent import db


def test_migration_hong_phai_dong_pool_va_thu_lai(monkeypatch):
    cac_pool = []

    class Pool:
        da_dong = False

        @asynccontextmanager
        async def acquire(self):
            yield self

        async def execute(self, sql):
            pass

        async def close(self):
            self.da_dong = True

    async def tao(*a, **k):
        p = Pool()
        cac_pool.append(p)
        return p

    async def migrate(conn):
        if len(cac_pool) == 1:
            raise RuntimeError("migration hỏng")

    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db.asyncpg, "create_pool", tao)
    monkeypatch.setattr(db, "apply_all", migrate)

    async def thu():
        with pytest.raises(RuntimeError, match="migration hỏng"):
            await db.init_db()
        assert db._pool is None
        assert cac_pool[0].da_dong
        pool = await db.init_db()
        assert pool is cac_pool[1] and db.pool() is pool
        await db.close_db()

    asyncio.run(thu())

