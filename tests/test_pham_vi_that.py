"""
Lớp phạm vi chạy THẬT trên Postgres.

`tests/test_pham_vi.py` khẳng định trên chuỗi SQL sinh ra — nó bắt lỗi soạn
mệnh đề. File này chạy mệnh đề ấy trên dữ liệu thật, và bắt loại lỗi mà chỉ
Postgres mới nói được: bí danh sai, tham số lệch số, `NULL` so sánh không
như người viết tưởng.

Ràng buộc ở đây là ràng buộc trung tâm của cả khối A. Sai theo hướng lỏng
thì nhân viên thấy khách không phải của mình — và không có gì hỏng để ai
nhận ra.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

LUOC_DO = ROOT / "agent" / "schema.sql"


async def _dung(url: str):
    """Lược đồ + migration + một bộ dữ liệu nhỏ. Trả (pool, id các thứ)."""
    import asyncpg

    from agent.migrations.runner import apply_all

    async def _codec(conn):
        await conn.set_type_codec("jsonb", encoder=json.dumps,
                                  decoder=json.loads, schema="pg_catalog")

    pool = await asyncpg.create_pool(url, min_size=1, max_size=3, init=_codec)
    async with pool.acquire() as conn:
        await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
        await apply_all(conn)

        thao = await conn.fetchval(
            "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten) "
            "VALUES ('thao', 'x', 'Thảo') RETURNING id")
        minh = await conn.fetchval(
            "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten) "
            "VALUES ('minh', 'x', 'Minh') RETURNING id")

        # Một tài khoản kênh, và cả hai người đều là thành viên — để trục
        # `account_memberships` KHÔNG che mất thứ đang muốn đo.
        tk = await conn.fetchval(
            "INSERT INTO channel_accounts (channel, display_name, status) "
            "VALUES ('webchat', 'Web', 'active') RETURNING id")
        for nd in (thao, minh):
            await conn.execute(
                "INSERT INTO account_memberships (account_id, user_id, role) "
                "VALUES ($1, $2, 'agent')", tk, nd)

        khach = {}
        for ten, chu in [("Của Thảo", thao), ("Của Minh", minh),
                         ("Vô chủ", None)]:
            kid = await conn.fetchval(
                "INSERT INTO contacts (display_name, owner_user_id) "
                "VALUES ($1, $2) RETURNING id", ten, chu)
            await conn.execute(
                "INSERT INTO contact_points "
                "(contact_id, channel_account_id, external_user_id) "
                "VALUES ($1, $2, $3)", kid, tk, f"ext-{ten}")
            khach[ten] = kid

    return pool, {"thao": thao, "minh": minh, "tk": tk, "khach": khach}


def _chay(url, kich_ban):
    async def boc():
        from agent import db

        pool, ids = await _dung(url)
        cu = db._pool
        db._pool = pool
        try:
            return await kich_ban(pool, ids)
        finally:
            db._pool = cu
            await pool.close()

    return asyncio.run(boc())


@pytest.mark.parametrize("muc,cho_doi", [
    # Mặc định: thấy hết, hệt như trước khối A2.
    ("tat", {"Của Thảo", "Của Minh", "Vô chủ"}),
    # Hai mức giữa vẫn THẤY đủ — chúng chỉ đổi cờ, không lọc danh sách.
    ("an_noi_dung", {"Của Thảo", "Của Minh", "Vô chủ"}),
    ("chi_doc", {"Của Thảo", "Của Minh", "Vô chủ"}),
    # Chỉ `an` mới giấu, và vẫn giữ khách vô chủ vì đó là của chung.
    ("an", {"Của Thảo", "Vô chủ"}),
])
def test_bon_muc_loc_dung_tap_khach(csdl_kiem_thu, muc, cho_doi):
    from agent.api.contacts import PostgresContactRepository

    async def kich_ban(pool, ids):
        kho = PostgresContactRepository(lambda: pool)
        return await kho.list_visible(
            user_id=ids["thao"], is_admin=False, query="",
            account_id=None, limit=50,
            nguoi={"id": ids["thao"], "quyen": frozenset({"khach.doc"})},
            muc=muc,
        )

    ds = _chay(csdl_kiem_thu, kich_ban)
    assert {d["display_name"] for d in ds} == cho_doi


def test_nguoi_co_xem_tat_ca_khong_bi_giau_o_muc_an(csdl_kiem_thu):
    from agent.api.contacts import PostgresContactRepository

    async def kich_ban(pool, ids):
        kho = PostgresContactRepository(lambda: pool)
        return await kho.list_visible(
            user_id=ids["thao"], is_admin=True, query="",
            account_id=None, limit=50,
            nguoi={"id": ids["thao"],
                   "quyen": frozenset({"khach.doc", "khach.xem_tat_ca"})},
            muc="an",
        )

    ds = _chay(csdl_kiem_thu, kich_ban)
    assert len(ds) == 3


def test_tra_ve_kem_chu_so_huu(csdl_kiem_thu):
    """
    Màn Khách hàng hiện cột "Phụ trách". Không trả tên chủ thì dashboard
    phải gọi thêm một request cho MỖI dòng — hoặc tệ hơn, hiện UUID.
    """
    from agent.api.contacts import PostgresContactRepository

    async def kich_ban(pool, ids):
        kho = PostgresContactRepository(lambda: pool)
        return await kho.list_visible(
            user_id=ids["thao"], is_admin=True, query="",
            account_id=None, limit=50,
            nguoi={"id": ids["thao"], "quyen": frozenset({"khach.doc"})},
            muc="tat",
        )

    ds = {d["display_name"]: d for d in _chay(csdl_kiem_thu, kich_ban)}
    assert ds["Của Thảo"]["owner_ho_ten"] == "Thảo"
    assert ds["Vô chủ"]["owner_user_id"] is None
    assert ds["Vô chủ"]["owner_ho_ten"] is None


def test_xoa_nhan_vien_thi_khach_thanh_vo_chu(csdl_kiem_thu):
    """
    `ON DELETE SET NULL` chạy thật.

    Đây là loại ràng buộc chỉ CSDL mới nói được đúng sai, và hậu quả nếu sai
    là không xoá nổi tài khoản người đã nghỉ — rồi người ta đi khoá tài
    khoản thay vì xoá, và khách vẫn "có chủ" là một người không đi làm nữa.
    """
    async def kich_ban(pool, ids):
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM nguoi_dung WHERE id = $1", ids["thao"])
            return await conn.fetchval(
                "SELECT owner_user_id FROM contacts WHERE display_name = 'Của Thảo'")

    assert _chay(csdl_kiem_thu, kich_ban) is None


def test_doc_muc_mac_dinh_va_sau_khi_dat(csdl_kiem_thu):
    from agent.core import pham_vi

    async def kich_ban(pool, ids):
        truoc = await pham_vi.doc_muc()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO cau_hinh_agent (khoa, gia_tri) VALUES ($1, $2)",
                pham_vi.KHOA_CAU_HINH, "an")
        sau = await pham_vi.doc_muc()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE cau_hinh_agent SET gia_tri = $2 WHERE khoa = $1",
                pham_vi.KHOA_CAU_HINH, "rac_khong_hop_le")
        hong = await pham_vi.doc_muc()
        return truoc, sau, hong

    truoc, sau, hong = _chay(csdl_kiem_thu, kich_ban)
    assert truoc == "tat", "chưa đặt gì thì phải là mặc định"
    assert sau == "an"
    assert hong == "tat", (
        "giá trị hỏng phải lui về mặc định, không được ném — hàm này chạy ở "
        "mọi lần mở màn Khách hàng"
    )
