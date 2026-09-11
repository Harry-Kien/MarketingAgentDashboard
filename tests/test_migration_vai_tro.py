"""
Migration 0019 — vai trò tự tạo thay hai vai trò cứng.

Migration này chạm thứ nguy hiểm nhất có thể chạm: quyền của người đang
đăng nhập. Sai theo hướng thiếu thì mọi người mất sạch quyền kể cả quản trị
— khoá cứng ngoài hệ thống, và nó KHÔNG nổ: đăng nhập vẫn được, chỉ là mọi
màn đều 403, nên người ta sẽ đi khởi động lại máy chủ thay vì đi xem CSDL.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

SQL = ROOT / "agent" / "migrations" / "versions" / "0019_quyen_va_vai_tro.sql"
LUOC_DO = ROOT / "agent" / "schema.sql"

BANG = ("vai_tro", "vai_tro_quyen", "nguoi_dung_vai_tro")


def _sql() -> str:
    return SQL.read_text(encoding="utf-8")


def test_migration_ton_tai_va_dung_if_not_exists():
    noi_dung = _sql()
    for bang in BANG:
        assert f"CREATE TABLE IF NOT EXISTS {bang}" in noi_dung, bang


def test_nap_san_hai_vai_tro_he_thong():
    noi_dung = _sql()
    assert "Quản trị" in noi_dung
    assert "Nhân viên" in noi_dung
    assert "he_thong" in noi_dung


def test_backfill_moi_nguoi_dung_deu_co_vai_tro():
    """
    Không backfill là mọi người mất sạch quyền sau khi migration chạy — kể
    cả quản trị. Đó là khoá cứng ngoài hệ thống, và nó im lặng.
    """
    noi_dung = _sql()
    assert "INSERT INTO nguoi_dung_vai_tro" in noi_dung
    assert "FROM nguoi_dung" in noi_dung


def test_moi_quyen_nhac_trong_migration_co_that_trong_danh_muc():
    """
    Migration gõ chuỗi quyền bằng tay. Gõ sai thì vai trò nạp sẵn cấp một
    quyền không tồn tại — im lặng, và nhân viên mất đúng màn đó mà không ai
    hiểu vì sao: ô tick trên dashboard vẫn hiện đã bật.
    """
    from agent.core.quyen import QUYEN

    ma = set(re.findall(r"'([a-z_]+\.[a-z_]+)'", _sql()))
    la = ma - set(QUYEN)
    assert not la, f"Migration nhắc quyền không có trong danh mục: {sorted(la)}"


def test_tap_quyen_nhan_vien_khong_nhieu_hon_hom_nay():
    """
    Vai trò `Nhân viên` phải BẰNG ĐÚNG những gì nhân viên làm được trước
    migration này.

    Migration không được là chỗ lặng lẽ nới quyền: người vận hành chạy nó để
    nâng cấp, không để thay đổi ai làm được gì. Việc siết quyền là của các
    việc sau, có chủ ý và có thể nhìn thấy.
    """
    from agent.core.quyen import QUYEN

    ma = set(re.findall(r"'([a-z_]+\.[a-z_]+)'", _sql()))
    cam = {
        "khach.xoa",            # xoá vĩnh viễn dữ liệu cá nhân
        "nguoi_dung.sua",       # tạo/khoá nhân viên
        "agent.dieu_khien",     # bật tắt agent, đổi ngưỡng
        "noi_dung.duyet",       # đăng ra ngoài công ty
        "don.sua",              # duyệt/huỷ đơn, sửa tồn kho
        "cau_hinh.sua",
        "ky_nang.sua",
        "mcp.sua",
        "kenh.sua",
        "kenh.noi",
        "tich_hop.sua",
        "catalog.duyet",
    }
    assert cam <= set(QUYEN)                      # tên quyền còn đúng
    thua = ma & cam
    assert not thua, f"Vai trò nạp sẵn cấp quyền quá tay: {sorted(thua)}"


def test_luoc_do_co_ba_bang_cho_ban_clone_sach():
    """
    Bản clone sạch dựng lược đồ từ `schema.sql`, không chạy migration. Thiếu
    ba bảng ở đó thì máy mới dựng lên là hỏng ngay từ lần đăng nhập đầu.
    """
    noi_dung = LUOC_DO.read_text(encoding="utf-8")
    for bang in BANG:
        assert f"CREATE TABLE IF NOT EXISTS {bang}" in noi_dung, bang


# =====================================================================
#  Chạy thật trên Postgres
# =====================================================================
# Sáu test trên đọc CHỮ trong file SQL. Chúng bắt được lỗi gõ, không bắt
# được lỗi ngữ nghĩa: một câu INSERT ... SELECT sai điều kiện JOIN vẫn chứa
# đủ mọi chuỗi chúng tìm, và vẫn gán sai vai trò cho tất cả mọi người.
#
# Backfill là chỗ không được sai: sai là khoá cứng ngoài hệ thống, im lặng.

def test_backfill_chay_that_gan_dung_vai_tro(csdl_kiem_thu):
    """Người `quan_tri` -> vai trò Quản trị; người khác -> Nhân viên."""
    import asyncio
    import json

    import asyncpg

    from agent.migrations.runner import apply_all

    async def chay():
        conn = await asyncpg.connect(csdl_kiem_thu)
        await conn.set_type_codec("jsonb", encoder=json.dumps,
                                  decoder=json.loads, schema="pg_catalog")
        try:
            await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
            await conn.execute(
                "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten, "
                "vai_tro) VALUES "
                "('kt_sep', 'x', 'Sếp', 'quan_tri'), "
                "('kt_nv', 'x', 'Nhân viên', 'nhan_vien') "
                "ON CONFLICT (ten_dang_nhap) DO NOTHING"
            )
            await apply_all(conn)
            ds = await conn.fetch(
                "SELECT nd.ten_dang_nhap, vt.ten AS vai_tro "
                "FROM nguoi_dung nd "
                "JOIN nguoi_dung_vai_tro ndvt ON ndvt.nguoi_dung_id = nd.id "
                "JOIN vai_tro vt ON vt.id = ndvt.vai_tro_id "
                "WHERE nd.ten_dang_nhap IN ('kt_sep', 'kt_nv')"
            )
            # Chạy lại: migration đã áp dụng thì runner bỏ qua, và kể cả
            # chạy lại tay thì ON CONFLICT giữ nguyên số dòng.
            truoc = await conn.fetchval("SELECT count(*) FROM nguoi_dung_vai_tro")
            await apply_all(conn)
            sau = await conn.fetchval("SELECT count(*) FROM nguoi_dung_vai_tro")
            return {r["ten_dang_nhap"]: r["vai_tro"] for r in ds}, truoc, sau

        finally:
            await conn.close()

    gan, truoc, sau = asyncio.run(chay())
    assert gan == {"kt_sep": "Quản trị", "kt_nv": "Nhân viên"}
    assert truoc == sau, "chạy lại migration làm nhân đôi phép gán vai trò"


def test_nhan_vien_nhan_dung_17_quyen(csdl_kiem_thu):
    """
    Số cụ thể, không phải "có vài quyền".

    Khẳng định mơ hồ kiểu `> 0` vẫn xanh khi câu CROSS JOIN chỉ chèn được
    một dòng — và nhân viên mất 16 quyền mà test không nói gì.
    """
    import asyncio
    import json

    import asyncpg

    from agent.migrations.runner import apply_all

    async def chay():
        conn = await asyncpg.connect(csdl_kiem_thu)
        await conn.set_type_codec("jsonb", encoder=json.dumps,
                                  decoder=json.loads, schema="pg_catalog")
        try:
            await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
            await apply_all(conn)
            return await conn.fetchval(
                "SELECT count(*) FROM vai_tro_quyen vq "
                "JOIN vai_tro vt ON vt.id = vq.vai_tro_id "
                "WHERE vt.ten = 'Nhân viên'"
            )
        finally:
            await conn.close()

    assert asyncio.run(chay()) == 17
