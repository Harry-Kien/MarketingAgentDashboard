"""
Migration 0020 — chủ sở hữu khách.

Một cột trên `contacts`, không phải một bảng riêng như
`conversation_assignments`. Lý do: hội thoại đổi người liên tục và lịch sử
là dữ liệu chính, còn sở hữu khách thì đọc ở MỌI truy vấn danh sách khách
và đổi thì hiếm. JOIN thêm một bảng ở mọi truy vấn là chi phí thường trực
để phục vụ một cột.
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

SQL = ROOT / "agent" / "migrations" / "versions" / "0020_chu_so_huu_khach.sql"
LUOC_DO = ROOT / "agent" / "schema.sql"


def _sql() -> str:
    return SQL.read_text(encoding="utf-8")


def test_them_cot_chu_so_huu():
    noi_dung = _sql()
    assert "ADD COLUMN IF NOT EXISTS owner_user_id" in noi_dung


def test_chu_so_huu_la_ON_DELETE_SET_NULL():
    """
    KHÔNG được là RESTRICT.

    RESTRICT thì không xoá nổi tài khoản người đã nghỉ việc, và người vận
    hành sẽ đi KHOÁ tài khoản thay vì xoá — khách vẫn hiện "có chủ" là một
    người không còn đi làm, và không ai nhận ra vì nó trông vẫn bình thường.

    SET NULL thì khách thành vô chủ và hiện ngay trên chỉ số vô chủ.
    """
    noi_dung = _sql()
    vt = noi_dung.index("owner_user_id")
    doan = noi_dung[vt:vt + 400]
    assert "ON DELETE SET NULL" in doan
    assert "ON DELETE RESTRICT" not in doan


def test_co_bang_lich_su():
    noi_dung = _sql()
    assert "CREATE TABLE IF NOT EXISTS contact_owner_history" in noi_dung
    # `owner_user_id` NULL trong lịch sử nghĩa là THU HỒI — phải cho phép.
    assert "ly_do" in noi_dung


def test_co_chi_muc_cho_khach_vo_chu():
    """
    Chỉ số "khách chưa có chủ" chạy ở MỌI lần tải trang Ca trực. Thiếu chỉ
    mục thì mỗi lần tải là một lần quét toàn bảng `contacts`.
    """
    noi_dung = _sql()
    assert "owner_user_id IS NULL" in noi_dung
    assert "CREATE INDEX IF NOT EXISTS" in noi_dung


def test_khong_nhan_ban_vao_schema_sql():
    """
    `contacts` KHÔNG nằm trong `schema.sql` — nó ra đời ở migration 0004.

    Nên 0020 cũng không được nhân bản vào đó: một câu `ALTER TABLE contacts`
    trong `schema.sql` sẽ chạy TRƯỚC 0004 trên bản clone sạch và nổ ngay ở
    lần khởi động đầu tiên.

    Khác với 0019: ba bảng vai trò tham chiếu `nguoi_dung`, mà `nguoi_dung`
    thì CÓ trong `schema.sql` — nên nhân bản ở đó là đúng.
    """
    noi_dung = LUOC_DO.read_text(encoding="utf-8")
    assert "owner_user_id" not in noi_dung
    assert "contact_owner_history" not in noi_dung
    assert "CREATE TABLE IF NOT EXISTS contacts (" not in noi_dung


def test_0020_dung_sau_migration_tao_bang_contacts():
    """
    Runner áp dụng theo thứ tự phiên bản. 0020 sửa một bảng do 0004 tạo ra,
    nên đặt số nhỏ hơn 0004 là nổ — và nổ ở máy mới, không ở máy đang chạy.
    """
    thu_muc = SQL.parent
    tao_contacts = [p.name for p in sorted(thu_muc.glob("*.sql"))
                    if "CREATE TABLE IF NOT EXISTS contacts (" in
                    p.read_text(encoding="utf-8")]
    assert tao_contacts, "không migration nào tạo bảng contacts"
    assert max(tao_contacts) < SQL.name


def test_chay_that_tren_postgres(csdl_kiem_thu):
    """
    Sáu test trên đọc CHỮ. Chúng không bắt được một câu ALTER sai cú pháp,
    cũng không bắt được khoá ngoại trỏ nhầm bảng.
    """
    import asyncpg

    from agent.migrations.runner import apply_all

    async def chay():
        conn = await asyncpg.connect(csdl_kiem_thu)
        await conn.set_type_codec("jsonb", encoder=json.dumps,
                                  decoder=json.loads, schema="pg_catalog")
        try:
            await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
            await apply_all(conn)
            cot = await conn.fetchrow(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'contacts' AND column_name = 'owner_user_id'")
            quy_tac = await conn.fetchval(
                "SELECT rc.delete_rule FROM information_schema.referential_constraints rc "
                "JOIN information_schema.key_column_usage k "
                "  ON k.constraint_name = rc.constraint_name "
                "WHERE k.table_name = 'contacts' AND k.column_name = 'owner_user_id'")
            co_bang = await conn.fetchval(
                "SELECT to_regclass('public.contact_owner_history') IS NOT NULL")
            return cot, quy_tac, co_bang
        finally:
            await conn.close()

    cot, quy_tac, co_bang = asyncio.run(chay())
    assert cot is not None, "chưa có cột owner_user_id"
    assert cot["is_nullable"] == "YES", "khách vô chủ phải hợp lệ"
    assert quy_tac == "SET NULL", f"quy tắc xoá là {quy_tac}"
    assert co_bang
