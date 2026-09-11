"""
`merge_preview` chạy trên Postgres THẬT.

VÌ SAO PHẢI CÓ FILE NÀY
------------------------
`tests/test_contacts_api.py` kiểm endpoint gộp bằng một kho GIẢ — một lớp
Python trả về dict dựng sẵn. Nó kiểm được phân quyền và hình dạng phản hồi,
nhưng truy vấn SQL thật thì KHÔNG BAO GIỜ được chạy.

Và truy vấn ấy sai. Nó dùng `$3` ở hai chỗ mang hai nghĩa khác nhau: một
lần làm `user_id` (uuid), một lần làm cờ `is_admin` (boolean). Postgres suy
kiểu từ phép so uuid rồi nổ ở `WHERE $3 OR ...`:

    argument of OR must be type boolean, not type uuid

Nghĩa là `GET /api/contacts/merge/preview` chưa bao giờ chạy được, và
`POST /api/contacts/merge` cũng không — nó gọi cùng hàm ấy trước khi gộp.
Suốt thời gian đó bộ test vẫn xanh.

Đây là lý do một endpoint KHÔNG MÀN HÌNH NÀO GỌI thì nguy hiểm: không ai
bấm, nên không ai phát hiện, và kho giả giữ cho nó xanh mãi.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LUOC_DO = ROOT / "agent" / "schema.sql"


def _chay(url: str, viec):
    async def _m():
        import asyncpg

        from agent import db
        from agent.migrations.runner import apply_all

        async def _codec(conn):
            await conn.set_type_codec(
                "jsonb", encoder=json.dumps, decoder=json.loads,
                schema="pg_catalog")

        db._pool = await asyncpg.create_pool(
            url, min_size=1, max_size=3, init=_codec)
        try:
            async with db._pool.acquire() as conn:
                await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
                await apply_all(conn)
            return await viec()
        finally:
            await db._pool.close()
            db._pool = None
    return asyncio.run(_m())


async def _hai_khach(*, nguoi_quan: UUID | None = None) -> tuple[UUID, UUID]:
    """
    Hai khách CÓ contact_point thật, mỗi người trên một kênh.

    Đúng hình dạng của dữ liệu thật, và không phải chi tiết vụn vặt của
    test: `merge_preview` đếm contact_point để biết ai nhìn thấy được gì.
    Khách không có point nào thì nó trả None cho mọi người — nên dựng khách
    trần là dựng một tình huống không bao giờ xảy ra, rồi kết luận sai về
    một truy vấn không bao giờ được kiểm.
    """
    from agent import db

    ra = []
    for ten, kenh in (("Chị Lan (Zalo)", "zalo_personal"),
                      ("Chị Lan (Facebook)", "facebook")):
        tk = await db.fetchrow(
            "INSERT INTO channel_accounts (channel, display_name, "
            "external_account_id, status) VALUES ($1, $1, $2, 'active') "
            "RETURNING id", kenh, str(uuid4()))
        k = await db.fetchrow(
            "INSERT INTO contacts (display_name, status) "
            "VALUES ($1, 'active') RETURNING id", ten)
        await db.execute(
            "INSERT INTO contact_points (contact_id, channel_account_id, "
            "external_user_id) VALUES ($1, $2, $3)",
            k["id"], tk["id"], str(uuid4()))
        if nguoi_quan is not None:
            await db.execute(
                "INSERT INTO account_memberships (account_id, user_id, role) "
                "VALUES ($1, $2, 'manager')", tk["id"], nguoi_quan)
        ra.append(k["id"])
    return ra[0], ra[1]


def test_xem_truoc_gop_chay_duoc_tren_postgres_that(csdl_kiem_thu):
    """
    Chính phép kiểm mà kho giả không làm được: truy vấn có chạy không.

    Không khẳng định gì về nội dung — chỉ cần nó KHÔNG NÉM. Truy vấn này
    từng ném `DatatypeMismatchError` ở mọi lượt gọi.
    """
    from agent.api.contacts import PostgresContactRepository

    async def viec():
        a, b = await _hai_khach()
        d = await PostgresContactRepository().merge_preview(
            source_id=a, target_id=b, user_id=uuid4(), is_admin=True)
        assert d is not None
        assert d["source"]["id"] == a
        assert d["target"]["id"] == b
    _chay(csdl_kiem_thu, viec)


def test_xem_truoc_tra_du_truong_man_hinh_can(csdl_kiem_thu):
    """
    Màn gộp hiện số hội thoại, số danh tính, và gửi `version` lên khi gộp.
    Thiếu `version` là gộp theo một bản xem trước đã cũ mà không ai biết.
    """
    from agent.api.contacts import PostgresContactRepository

    async def viec():
        a, b = await _hai_khach()
        d = await PostgresContactRepository().merge_preview(
            source_id=a, target_id=b, user_id=uuid4(), is_admin=True)
        for ben in ("source", "target"):
            for truong in ("id", "display_name", "version",
                           "point_count", "conversation_count"):
                assert truong in d[ben], f"thiếu {ben}.{truong}"
        assert "can_manage" in d
    _chay(csdl_kiem_thu, viec)


def test_nguoi_thuong_khong_quan_duoc_thi_can_manage_false(csdl_kiem_thu):
    """
    `is_admin=False` đi qua ĐÚNG nhánh mà lỗi kiểu từng nằm ở đó.

    Với quản trị, `$3` là TRUE nên `WHERE $3 OR ...` có thể được rút gọn;
    chỉ khi là người thường thì Postgres mới thật sự phải đánh giá cả hai
    vế. Kiểm mỗi nhánh quản trị là bỏ sót đúng chỗ hỏng.
    """
    from agent.api.contacts import PostgresContactRepository

    async def viec():
        from agent import db

        nd = await db.fetchrow(
            "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten) "
            "VALUES ('kt_gop', 'x', 'Kiểm thử') RETURNING id")
        a, b = await _hai_khach(nguoi_quan=nd["id"])

        # Người QUẢN cả hai kênh: thấy được và gộp được.
        d = await PostgresContactRepository().merge_preview(
            source_id=a, target_id=b, user_id=nd["id"], is_admin=False)
        assert d is not None, "người quản cả hai kênh mà không xem trước được"
        assert d["can_manage"] is True

        # Người LẠ, không là thành viên kênh nào: không thấy gì.
        assert await PostgresContactRepository().merge_preview(
            source_id=a, target_id=b, user_id=uuid4(), is_admin=False) is None
    _chay(csdl_kiem_thu, viec)


def test_khach_khong_ton_tai_tra_none_chu_khong_nem(csdl_kiem_thu):
    from agent.api.contacts import PostgresContactRepository

    async def viec():
        a, _ = await _hai_khach()
        d = await PostgresContactRepository().merge_preview(
            source_id=a, target_id=uuid4(), user_id=uuid4(), is_admin=True)
        assert d is None
    _chay(csdl_kiem_thu, viec)


def test_man_hinh_gop_co_that_va_goi_dung_duong():
    """
    Endpoint chạy được mà không màn hình nào gọi thì nó lại thành mồ côi,
    và mồ côi là cách nó hỏng lần đầu.
    """
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert 'id="pnGop"' in html and 'id="gopMo"' in html
    assert "/contacts/merge/preview" in js
    assert '"/contacts/merge"' in js
    # Gửi `version` lên là điều kiện để máy chủ bắt được xung đột.
    assert "expected_source_version" in js
    assert "expected_target_version" in js
