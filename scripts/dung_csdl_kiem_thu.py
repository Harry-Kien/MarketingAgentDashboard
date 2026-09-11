"""
Dựng lược đồ vào CSDL kiểm thử trỏ bởi `TEST_DATABASE_URL`.

VÌ SAO CẦN MỘT SCRIPT RIÊNG THAY VÌ DÙNG `db.init_db()`
-------------------------------------------------------
`init_db()` đọc `settings.database_url` — CSDL THẬT của máy đang chạy. Gọi
nó để dựng CSDL kiểm thử là mời một nhầm lẫn đúng kiểu không ai muốn gặp
hai lần: chạy nhầm trên CSDL có dữ liệu khách.

Ở đây URL đến từ đối số, và chỉ từ `TEST_DATABASE_URL`.

Chạy:
    TEST_DATABASE_URL=postgresql://... python -m scripts.dung_csdl_kiem_thu
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg

from agent.migrations.runner import apply_all

LUOC_DO = Path(__file__).resolve().parent.parent / "agent" / "schema.sql"


async def _tao_neu_thieu(url: str) -> None:
    """
    Tạo CSDL nếu chưa có.

    Trong CI, service container đã tạo sẵn. Trên máy lập trình thì không —
    và không có bước này thì người muốn chạy test tích hợp tại chỗ gặp
    `InvalidCatalogNameError`, đoán là mình cấu hình sai, rồi quay lại chạy
    không có CSDL. Tức là test tích hợp vẫn không ai chạy.
    """
    goc, _, ten = url.rpartition("/")
    ten = ten.split("?")[0]
    if not ten:
        return
    conn = await asyncpg.connect(f"{goc}/postgres")
    try:
        co = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", ten
        )
        if not co:
            await conn.execute(f'CREATE DATABASE "{ten}"')
            print(f"Đã tạo CSDL {ten}.")
    finally:
        await conn.close()


async def dung(url: str) -> None:
    await _tao_neu_thieu(url)
    conn = await asyncpg.connect(url)
    try:
        # Cùng codec với `agent/db.py`: lược đồ có cột JSONB, và không đặt
        # codec thì câu chèn mẫu trong migration nhận chuỗi thay vì dict.
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )
        await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
        await apply_all(conn)
    finally:
        await conn.close()


def main() -> int:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        print("Thiếu TEST_DATABASE_URL — không dựng gì cả.", file=sys.stderr)
        return 1
    asyncio.run(dung(url))
    print("Đã dựng lược đồ và áp dụng migration vào CSDL kiểm thử.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
