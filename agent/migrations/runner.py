"""Khám phá và áp dụng migration SQL theo thứ tự phiên bản."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


VERSIONS_DIR = Path(__file__).parent / "versions"
_MIGRATION_LOCK_ID = 4_265_771_901
_CREATE_HISTORY_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


class MigrationError(RuntimeError):
    """Lược đồ migration không nhất quán và không an toàn để tiếp tục."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    path: Path
    checksum: str


def discover_migrations(directory: Path = VERSIONS_DIR) -> list[Migration]:
    """Đọc các file migration hợp lệ và trả theo thứ tự phiên bản."""
    found: list[Migration] = []
    versions: set[str] = set()
    for path in sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        version, name = path.stem.split("_", 1)
        if version in versions:
            raise MigrationError(f"trùng phiên bản migration: {version}")
        versions.add(version)
        found.append(
            Migration(
                version=version,
                name=name,
                path=path,
                checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    return found


async def apply_migrations(conn, migrations: list[Migration]) -> None:
    """Áp các migration chưa chạy và chặn mọi checksum đã bị thay đổi."""
    await conn.execute(_CREATE_HISTORY_SQL)
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", _MIGRATION_LOCK_ID)
        rows = await conn.fetch(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        )
        applied = {row["version"]: row for row in rows}

        for migration in migrations:
            previous = applied.get(migration.version)
            if previous is not None:
                if previous["checksum"] != migration.checksum:
                    raise MigrationError(
                        "checksum migration đã áp dụng không khớp: "
                        f"{migration.version}_{migration.name}"
                    )
                continue

            await conn.execute(migration.path.read_text(encoding="utf-8"))
            await conn.execute(
                """
                INSERT INTO schema_migrations (version, name, checksum)
                VALUES ($1, $2, $3)
                """,
                migration.version,
                migration.name,
                migration.checksum,
            )


async def apply_all(conn, directory: Path = VERSIONS_DIR) -> None:
    """Khám phá rồi áp toàn bộ migration đóng gói cùng ứng dụng."""
    await apply_migrations(conn, discover_migrations(directory))
