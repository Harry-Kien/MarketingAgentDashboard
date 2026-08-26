"""
Bản sao lưu phải PHỤC HỒI được — không chỉ tạo ra được.

CHUYỆN ĐÃ XẢY RA
----------------
`scripts/sao_luu.py` chạy xong báo OK, và `scripts/san_sang` chuyển mục
"Sao lưu" sang xanh. Nhưng lần thử phục hồi đầu tiên cho ra 41/42 bảng:
bảng `chunks` — toàn bộ kho tri thức RAG — KHÔNG dựng lại được.

Nguyên nhân: `pg_dump` khi phục hồi đặt `search_path` về rỗng cho an toàn.
Hàm `bo_dau()` gọi `unaccent(...)` và `translate(...)` không kèm schema, nên
không phân giải được; `bo_dau` hỏng kéo theo cột sinh `chunks.tim_kiem`
hỏng, kéo theo cả bảng `chunks` không tạo được.

Hội thoại, đơn hàng, contact phục hồi bình thường — nên mất mát không lộ ra
ngay. Đúng nghĩa xanh giả: chỉ số báo có sao lưu, mà thứ được sao lưu thì
không dùng lại được.

Test này kiểm ĐÚNG cơ chế đó bằng cách ép `search_path` rỗng, thay vì chạy
cả vòng dump/restore mất vài chục giây.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_bo_dau_chay_duoc_khi_search_path_rong():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("chưa cấp TEST_DATABASE_URL cho integration PostgreSQL")

    import asyncpg

    async def kiem():
        conn = await asyncpg.connect(database_url)
        try:
            schema = (ROOT / "agent" / "schema.sql").read_text(encoding="utf-8")
            await conn.execute(schema)
            # Đúng điều kiện pg_dump dựng lúc phục hồi.
            await conn.execute("SELECT pg_catalog.set_config('search_path', '', false)")
            return await conn.fetchval("SELECT public.bo_dau($1)", "Tiếng Việt Đẹp")
        finally:
            await conn.execute(
                "SELECT pg_catalog.set_config('search_path', 'public', false)"
            )
            await conn.close()

    assert asyncio.run(kiem()) == "Tieng Viet Dep"
