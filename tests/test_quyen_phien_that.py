"""
`doc_phien()` nạp quyền — chạy trên Postgres thật.

VÌ SAO KHÔNG ĐỦ NẾU CHỈ SOI CHỮ TRONG CÂU SQL
----------------------------------------------
Câu truy vấn mới có `array_agg(DISTINCT ...) FILTER (...)`, `bool_or` và
`GROUP BY n.id`. Đó là loại mệnh đề mà chỉ Postgres mới nói được đúng sai:
thiếu một cột trong GROUP BY thì nó ném lúc LẬP KẾ HOẠCH, kể cả khi không
có dòng nào khớp — y như lỗi `FOR UPDATE` trên nhánh nullable từng làm chết
toàn bộ đường gửi (xem `tests/test_delivery_guard_postgres.py`).

Và lỗi ấy nổ ở `doc_phien`, tức là ở MỌI request: không ai đăng nhập được.
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

LUOC_DO = ROOT / "agent" / "schema.sql"


async def _dung_va_chay(url: str, kich_ban):
    """Trỏ `agent.db` vào CSDL kiểm thử, dựng lược đồ, chạy kịch bản."""
    import asyncpg

    from agent import db
    from agent.migrations.runner import apply_all

    async def _codec(conn):
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    pool = await asyncpg.create_pool(url, min_size=1, max_size=2, init=_codec)
    cu = db._pool
    db._pool = pool
    try:
        async with pool.acquire() as conn:
            await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
            await apply_all(conn)
        return await kich_ban(pool)
    finally:
        db._pool = cu
        await pool.close()


async def _tao_nguoi_va_phien(pool, ten: str, vai_tro: str) -> str:
    """Trả token phiên của người vừa tạo."""
    async with pool.acquire() as conn:
        nd = await conn.fetchval(
            "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten, vai_tro) "
            "VALUES ($1, 'x', $1, $2) RETURNING id",
            ten, vai_tro,
        )
        # Backfill của migration đã chạy TRƯỚC khi người này tồn tại, nên
        # phải gán vai trò tay — đúng như `them_nguoi_dung` sẽ làm.
        await conn.execute(
            "INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id) "
            "SELECT $1, id FROM vai_tro WHERE ten = $2",
            nd, "Quản trị" if vai_tro == "quan_tri" else "Nhân viên",
        )
        token = f"token-{ten}"
        await conn.execute(
            "INSERT INTO phien (token, nguoi_dung_id, het_han) "
            "VALUES ($1, $2, now() + interval '1 day')",
            token, nd,
        )
        return token


def test_quan_tri_nhan_toan_bo_danh_muc(csdl_kiem_thu):
    """
    Quản trị nhận `frozenset(QUYEN)` tính từ MÃ, không từ CSDL.

    Nếu nó đếm dòng trong `vai_tro_quyen` thì mỗi quyền thêm vào mã sau này
    sẽ vắng mặt với quản trị — im lặng, và người ta đi sửa từng vai trò tay.
    """
    from agent.core import xac_thuc
    from agent.core.quyen import QUYEN

    async def kich_ban(pool):
        token = await _tao_nguoi_va_phien(pool, "kt_sep", "quan_tri")
        return await xac_thuc.doc_phien(token)

    nguoi = asyncio.run(_dung_va_chay(csdl_kiem_thu, kich_ban))
    assert nguoi is not None
    assert nguoi["quyen"] == frozenset(QUYEN)


def test_nhan_vien_nhan_dung_tap_cua_vai_tro(csdl_kiem_thu):
    from agent.core import xac_thuc

    async def kich_ban(pool):
        token = await _tao_nguoi_va_phien(pool, "kt_nv", "nhan_vien")
        return await xac_thuc.doc_phien(token)

    nguoi = asyncio.run(_dung_va_chay(csdl_kiem_thu, kich_ban))
    assert nguoi is not None
    assert len(nguoi["quyen"]) == 19
    assert "hoi_thoai.tra_loi" in nguoi["quyen"]
    assert "khach.xoa" not in nguoi["quyen"]
    assert "don.sua" not in nguoi["quyen"]


def test_nguoi_khong_vai_tro_nao_van_doc_duoc_phien(csdl_kiem_thu):
    """
    Không vai trò -> tập quyền RỖNG, không phải None.

    Trả None nghĩa là "chưa đăng nhập", và middleware sẽ đá họ ra màn đăng
    nhập. Họ đăng nhập lại, lại bị đá ra — một vòng lặp mà không thông báo
    nào nói rằng vấn đề là chưa được cấp quyền.
    """
    from agent.core import xac_thuc

    async def kich_ban(pool):
        async with pool.acquire() as conn:
            nd = await conn.fetchval(
                "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten) "
                "VALUES ('kt_treo', 'x', 'Treo') RETURNING id")
            await conn.execute(
                "INSERT INTO phien (token, nguoi_dung_id, het_han) "
                "VALUES ('token-treo', $1, now() + interval '1 day')", nd)
        return await xac_thuc.doc_phien("token-treo")

    nguoi = asyncio.run(_dung_va_chay(csdl_kiem_thu, kich_ban))
    assert nguoi is not None, "người chưa có vai trò vẫn phải đăng nhập được"
    assert nguoi["quyen"] == frozenset()


def test_thu_quyen_co_hieu_luc_o_request_ke_tiep(csdl_kiem_thu):
    """
    Không cache quyền vào phiên.

    Nhân viên nghỉ việc lúc 9 giờ sáng mà token còn dùng được tới lúc hết
    hạn là đúng thứ bảng `phien` sinh ra để tránh.
    """
    from agent.core import xac_thuc

    async def kich_ban(pool):
        token = await _tao_nguoi_va_phien(pool, "kt_thu", "nhan_vien")
        truoc = await xac_thuc.doc_phien(token)
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM nguoi_dung_vai_tro ndvt USING nguoi_dung nd "
                "WHERE ndvt.nguoi_dung_id = nd.id AND nd.ten_dang_nhap = 'kt_thu'")
        sau = await xac_thuc.doc_phien(token)
        return truoc, sau

    truoc, sau = asyncio.run(_dung_va_chay(csdl_kiem_thu, kich_ban))
    assert len(truoc["quyen"]) == 19
    assert sau["quyen"] == frozenset(), "thu quyền rồi mà request sau vẫn có"


def test_quyen_mo_coi_trong_csdl_bi_loc_bo(csdl_kiem_thu):
    """
    Quyền bị xoá khỏi danh mục ở bản sau vẫn còn dòng trong `vai_tro_quyen`.

    Không lọc thì `duoc_phep()` nhận một chuỗi không còn ý nghĩa gì — và tệ
    hơn, nếu bản sau dùng lại đúng tên ấy cho một quyền KHÁC thì những người
    cũ bỗng có quyền mới mà không ai cấp.
    """
    from agent.core import xac_thuc

    async def kich_ban(pool):
        token = await _tao_nguoi_va_phien(pool, "kt_mo_coi", "nhan_vien")
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO vai_tro_quyen (vai_tro_id, quyen) "
                "SELECT id, 'quyen_cu.da_xoa' FROM vai_tro WHERE ten = 'Nhân viên'")
        return await xac_thuc.doc_phien(token)

    nguoi = asyncio.run(_dung_va_chay(csdl_kiem_thu, kich_ban))
    assert "quyen_cu.da_xoa" not in nguoi["quyen"]
    assert len(nguoi["quyen"]) == 19
