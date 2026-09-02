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


def _chuan_hoa(noi_dung: bytes) -> bytes:
    """
    Bỏ CR trước khi băm: checksum phải nói về NỘI DUNG SQL, không về cách
    xuống dòng.

    LỖI THẬT ĐÃ GẶP. Git trên Windows mặc định `core.autocrlf=true`, và
    repo này không có `.gitattributes`. Một lệnh `git checkout` bình thường
    viết lại mọi tệp .sql từ LF sang CRLF — nội dung SQL không đổi một ký
    tự nào, nhưng sha256 đổi hoàn toàn.

    Hệ quả: `apply_migrations` ném MigrationError và ứng dụng KHÔNG KHỞI
    ĐỘNG ĐƯỢC. Thông báo lỗi lại nói "checksum migration đã áp dụng không
    khớp" — nghe như có người sửa một migration đã chạy, tức là chỉ đúng
    hướng điều tra sai. Người mới clone repo trên Windows gặp đúng bức
    tường này ngay lần chạy đầu tiên.

    Chuẩn hoá TƯƠNG THÍCH NGƯỢC: tệp gốc vốn dùng LF, nên bỏ CR cho ra
    đúng chuỗi byte đã băm lần đầu — mọi CSDL đang chạy giữ nguyên giá trị
    trong `schema_migrations`, không cần vá tay dòng nào.

    Chốt vẫn còn nguyên tác dụng: sửa MỘT KÝ TỰ SQL trong migration đã áp
    dụng thì checksum vẫn lệch và vẫn bị chặn. Chỉ riêng cách xuống dòng là
    thôi được tính.
    """
    return noi_dung.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


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
                checksum=hashlib.sha256(_chuan_hoa(path.read_bytes())).hexdigest(),
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
