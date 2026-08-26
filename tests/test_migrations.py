"""Kiểm thử bộ chạy migration tiến về phía trước."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent.migrations.runner import (
    MigrationError,
    apply_migrations,
    discover_migrations,
)


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _MigrationDatabase:
    """CSDL bộ nhớ mô phỏng đúng phần giao tiếp migration sử dụng."""

    def __init__(self):
        self.applied: dict[str, tuple[str, str]] = {}
        self.sql_runs: list[str] = []
        self.all_sql: list[str] = []

    def transaction(self):
        return _Transaction()

    async def fetch(self, sql: str):
        assert "schema_migrations" in sql
        return [
            {"version": version, "name": name, "checksum": checksum}
            for version, (name, checksum) in self.applied.items()
        ]

    async def execute(self, sql: str, *args):
        self.all_sql.append(sql)
        if "INSERT INTO schema_migrations" in sql:
            version, name, checksum = args
            self.applied[version] = (name, checksum)
        elif (
            "CREATE TABLE IF NOT EXISTS schema_migrations" not in sql
            and "pg_advisory_xact_lock" not in sql
        ):
            self.sql_runs.append(sql)
        return "OK"


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)

    async def close(self):
        return None


def test_discover_migrations_sap_xep_theo_phien_ban(tmp_path: Path):
    """Đổi thứ tự duyệt file không được đổi thứ tự áp migration."""
    (tmp_path / "0002_second.sql").write_text("SELECT 2", encoding="utf-8")
    (tmp_path / "0001_first.sql").write_text("SELECT 1", encoding="utf-8")

    migrations = discover_migrations(tmp_path)

    assert [migration.version for migration in migrations] == ["0001", "0002"]
    assert [migration.name for migration in migrations] == ["first", "second"]
    assert all(len(migration.checksum) == 64 for migration in migrations)


def test_discover_migrations_tu_choi_trung_phien_ban(tmp_path: Path):
    """Hai file cùng version sẽ gây lịch sử mơ hồ nên phải bị chặn."""
    (tmp_path / "0001_first.sql").write_text("SELECT 1", encoding="utf-8")
    (tmp_path / "0001_second.sql").write_text("SELECT 2", encoding="utf-8")

    with pytest.raises(MigrationError, match="trùng phiên bản"):
        discover_migrations(tmp_path)


def test_apply_migrations_khong_chay_lai_ban_da_ap_dung(tmp_path: Path):
    """Khởi động app lần hai không được chạy lại DDL đã thành công."""
    (tmp_path / "0001_first.sql").write_text("SELECT 1", encoding="utf-8")
    database = _MigrationDatabase()
    migrations = discover_migrations(tmp_path)

    asyncio.run(apply_migrations(database, migrations))
    asyncio.run(apply_migrations(database, migrations))

    assert database.sql_runs == ["SELECT 1"]
    assert set(database.applied) == {"0001"}


def test_apply_migrations_chan_file_da_bi_sua(tmp_path: Path):
    """Sửa migration cũ phải bị phát hiện thay vì làm lệch các môi trường."""
    path = tmp_path / "0001_first.sql"
    path.write_text("SELECT 1", encoding="utf-8")
    database = _MigrationDatabase()
    asyncio.run(apply_migrations(database, discover_migrations(tmp_path)))

    path.write_text("SELECT 2", encoding="utf-8")

    with pytest.raises(MigrationError, match="checksum"):
        asyncio.run(apply_migrations(database, discover_migrations(tmp_path)))
    assert database.sql_runs == ["SELECT 1"]


def test_init_db_luon_ap_migration_sau_baseline(monkeypatch):
    """Khởi động app phải chạy migration, không chỉ chạy schema cũ."""
    from agent import db

    database = _MigrationDatabase()
    fake_pool = _Pool(database)

    async def create_pool(*args, **kwargs):
        return fake_pool

    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db.asyncpg, "create_pool", create_pool)

    asyncio.run(db.init_db())

    assert any(
        "CREATE TABLE IF NOT EXISTS schema_migrations" in sql
        for sql in database.all_sql
    )
