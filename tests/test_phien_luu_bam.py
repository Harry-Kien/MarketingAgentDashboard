"""
Bảng `phien` chỉ giữ BẢN BĂM của token, không giữ token.

VÌ SAO
------
Token phiên là thứ duy nhất đứng giữa người lạ và quyền quản trị. Bản trước
lưu nguyên văn: ai cầm được một bản sao lưu CSDL — `backup_loop` tạo mỗi
ngày, `scripts/sao_luu.py` tạo theo lệnh, và người ta mang chúng đi khắp nơi
— là dán token vào cookie rồi vào thẳng dashboard, không cần mật khẩu.

Băm SHA-256 là đủ, không cần scrypt như mật khẩu: token là 32 byte ngẫu
nhiên, không có gì để dò bằng từ điển.

Không cần migration. Phiên cũ lưu token gốc sẽ không còn khớp với bản băm
của chính nó, nên người đang đăng nhập phải đăng nhập lại MỘT lần — rồi
`don_phien_het_han` dọn dần các dòng ấy.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.core import xac_thuc  # noqa: E402


def test_bam_token_tat_dinh_va_khac_goc():
    t = "token-thu"
    assert xac_thuc.bam_token(t) == xac_thuc.bam_token(t)
    assert xac_thuc.bam_token(t) != t
    assert len(xac_thuc.bam_token(t)) == 64


async def _chay(url: str, kich_ban):
    import asyncpg

    from agent import db
    from agent.migrations.runner import apply_all

    async def _codec(conn):
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

    pool = await asyncpg.create_pool(url, min_size=1, max_size=2, init=_codec)
    cu = db._pool
    db._pool = pool
    try:
        async with pool.acquire() as conn:
            await conn.execute((ROOT / "agent" / "schema.sql").read_text(encoding="utf-8"))
            await apply_all(conn)
        return await kich_ban(pool)
    finally:
        db._pool = cu
        await pool.close()


def test_bang_phien_khong_chua_token_goc(csdl_kiem_thu):
    async def kich_ban(pool):
        await xac_thuc.tao_nguoi_dung("bam.phien", "mat-khau-thu-nghiem-dai")
        token = await xac_thuc.dang_nhap("bam.phien", "mat-khau-thu-nghiem-dai")
        assert token
        async with pool.acquire() as conn:
            luu = [r["token"] for r in await conn.fetch(
                "SELECT p.token FROM phien p JOIN nguoi_dung n "
                "ON n.id = p.nguoi_dung_id WHERE n.ten_dang_nhap = 'bam.phien'")]
        assert luu == [xac_thuc.bam_token(token)], "CSDL phải giữ bản băm, không giữ token"

        # Cầm đúng thứ nằm trong CSDL thì KHÔNG vào được.
        assert await xac_thuc.doc_phien(luu[0]) is None
        # Cầm token thật (cookie) thì vào được.
        assert (await xac_thuc.doc_phien(token))["ten_dang_nhap"] == "bam.phien"

        await xac_thuc.dang_xuat(token)
        assert await xac_thuc.doc_phien(token) is None

    asyncio.run(_chay(csdl_kiem_thu, kich_ban))
