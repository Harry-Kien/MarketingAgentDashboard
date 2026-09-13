"""
Tiện ích dùng chung: soi tài liệu, và CSDL kiểm thử.

VÌ SAO NẰM Ở ĐÂY CHỨ KHÔNG CHÉP VÀO TỪNG FILE
---------------------------------------------
`test_claude_md.py` và `test_dua_vao_doanh_nghiep.py` cùng cần một phép
kiểm: "đường dẫn tài liệu này nhắc tới còn sống không". Chép hai bản là tạo
đúng thứ vừa gây ra lỗi trong `agent/main.py` — hai bản sao của một việc,
rồi bản ít người đọc hơn mục đi. Ở đây nó lộ ra ngay khi viết: bản đầu tiên
quên xét thư mục cha, và bản thứ hai thừa hưởng nguyên lỗi ấy.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def nguoi_thu(*quyen: str, ten: str = "kt", **them) -> dict:
    """
    Dựng một người đăng nhập giả cho test API.

    Dùng với `app.dependency_overrides[routes.nguoi_da_dang_nhap]`. Đó là
    ĐIỂM GHI ĐÈ DUY NHẤT: `can_quyen()` trả closure mới mỗi lần gọi nên
    không ghi đè thẳng vào nó được.

    Gọi không đối số = người đã đăng nhập nhưng KHÔNG có quyền nào. Mặc
    định ấy có chủ ý: test muốn kiểm một endpoint thì phải nói ra endpoint
    ấy cần quyền gì, và câu nói ấy chính là tài liệu.

    `toan_quyen()` ở dưới dành cho test không quan tâm tới phân quyền.
    """
    nguoi = {
        "id": "00000000-0000-0000-0000-000000000001",
        "ten_dang_nhap": ten,
        "ho_ten": ten,
        "vai_tro": "nhan_vien",
        "khoa": False,
        "quyen": frozenset(quyen),
    }
    nguoi.update(them)
    return nguoi


def toan_quyen(ten: str = "qt", **them) -> dict:
    """Người có mọi quyền — tương đương vai trò `Quản trị`."""
    from agent.core.quyen import QUYEN

    return nguoi_thu(*QUYEN, ten=ten, vai_tro="quan_tri", **them)


@pytest.fixture
def csdl_kiem_thu():
    """
    Một CSDL RỖNG RIÊNG cho từng test, xoá sau khi xong.

    VÌ SAO KHÔNG DÙNG CHUNG MỘT CSDL
    --------------------------------
    Test migration phải chạy trên lược đồ trắng. Dùng chung thì test chạy
    trước để lại bảng và dữ liệu, và test sau xanh nhờ thứ nó không tự dựng —
    rồi đỏ khi có người chạy nó một mình. Đó là kiểu đỏ khiến người ta nghi
    ngờ bộ test thay vì nghi ngờ mã.

    Bỏ qua khi thiếu `TEST_DATABASE_URL`, nhưng CI LUÔN có nó — xem
    `tests/test_ci_co_postgres.py` và service postgres trong workflow. Nếu
    biến ấy biến mất khỏi CI thì test ở kia đỏ trước, nên việc bỏ qua ở đây
    không thể lặng lẽ thành vĩnh viễn.
    """
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("chưa cấp TEST_DATABASE_URL cho integration PostgreSQL")

    import asyncpg

    goc = url.rpartition("/")[0]
    ten = f"kt_{uuid.uuid4().hex[:12]}"

    async def tao():
        conn = await asyncpg.connect(f"{goc}/postgres")
        try:
            await conn.execute(f'CREATE DATABASE "{ten}"')
        finally:
            await conn.close()

    async def xoa():
        conn = await asyncpg.connect(f"{goc}/postgres")
        try:
            await conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()", ten)
            await conn.execute(f'DROP DATABASE IF EXISTS "{ten}"')
        finally:
            await conn.close()

    asyncio.run(tao())
    try:
        yield f"{goc}/{ten}"
    finally:
        asyncio.run(xoa())


def duong_dan_con_song(duong: str) -> bool:
    """
    Đường dẫn còn sống: có thật, HOẶC có bản `.example` đi thay.

    Phải chấp nhận vế thứ hai vì repo cố ý không mang theo dữ liệu thật
    (`data/catalog.json`, `data/knowledge/`) — đòi chúng tồn tại là đòi
    đúng thứ đã quyết định không đưa lên, và test sẽ xanh trên máy đã cấu
    hình rồi đỏ trên mọi bản clone sạch.

    `.example` có thể nằm ở BẤT KỲ tầng nào của đường dẫn, không riêng tầng
    cuối. Cả hai dạng dưới đây đều hợp lệ và phải nhận cả hai:

        data/catalog.json                      -> data/catalog.example.json
        data/knowledge/chinh-sach.md           -> data/knowledge.example/chinh-sach.md

    Bỏ sót dạng thứ hai chính là cách bản đầu tiên của hàm này lọt lưới.
    """
    p = Path(duong.rstrip("/"))
    if (ROOT / p).exists():
        return True
    # Thử đổi từng tầng sang bản `.example`, từ tầng cuối ngược lên gốc.
    phan = list(p.parts)
    for i in range(len(phan) - 1, -1, -1):
        goc = Path(phan[i])
        thu = phan.copy()
        thu[i] = f"{goc.stem}.example{goc.suffix}"
        if (ROOT / Path(*thu)).exists():
            return True
    return False


# =====================================================================
#  App ĐẦY ĐỦ trên Postgres thật — cho test đầu-cuối và nghiệm thu
# =====================================================================
#
# Khác `csdl_kiem_thu` (chỉ cấp một CSDL trắng): fixture này dựng
# `agent.main.app` với lifespan thật — cùng thứ uvicorn dựng — để middleware,
# chốt đăng nhập, vault và mọi router đều có mặt. Hai lỗi từng lọt qua test
# router trần (callback Zalo OA chết ở middleware) và test kho giả
# (`merge_preview` nổ ở SQL) là lý do fixture này tồn tại.

import base64  # noqa: E402
import secrets  # noqa: E402
from uuid import UUID  # noqa: E402

GOC_WEB = "https://shop.test"


@pytest.fixture
def app_that(csdl_kiem_thu, monkeypatch):
    """
    `agent.main.app` trỏ vào CSDL kiểm thử, KHÔNG dựng vòng nền.

    Vòng nền (canh gác Meta, sao lưu, outbox worker…) gọi ra mạng và chạm
    những thứ ngoài phạm vi test này. `nen_chay_vong_nen` là chính cái khoá
    mà production dùng để chia vai tiến trình — dùng lại nó, không vá sâu.
    """
    from fastapi.testclient import TestClient

    from agent import db, runtime
    from agent.config import settings
    import agent.main as main

    khoa = base64.b64encode(secrets.token_bytes(32)).decode()
    monkeypatch.setattr(settings, "database_url", csdl_kiem_thu)
    monkeypatch.setattr(settings, "credential_master_keys", f"1:{khoa}")
    monkeypatch.setattr(settings, "credential_active_key_version", 1)
    monkeypatch.setattr(main, "nen_chay_vong_nen", lambda *a, **k: False)

    # Test khác có thể để lại pool trỏ CSDL khác. Lifespan chỉ tạo pool khi
    # `_pool is None`, nên phải xoá trước — nếu không test này chạy trên
    # CSDL của test trước và xanh nhờ dữ liệu không phải của mình.
    db._pool = None
    # Công tắc TOÀN CỤC bật, để thứ chặn agent là công tắc THEO KÊNH.
    runtime.STATE["enabled"] = True

    with TestClient(main.app) as khach:
        yield khach
    db._pool = None


async def _quan_tri(ten: str) -> tuple[UUID, str]:
    """Người thật + vai trò Quản trị + phiên. Trả (id, token)."""
    from agent import db

    nd = await db.fetchrow(
        "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten, vai_tro) "
        "VALUES ($1, 'x', $1, 'quan_tri') RETURNING id", ten)
    await db.execute(
        "INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id) "
        "SELECT $1, id FROM vai_tro WHERE ten = 'Quản trị'", nd["id"])
    token = secrets.token_urlsafe(32)
    await db.execute(
        "INSERT INTO phien (token, nguoi_dung_id, het_han) "
        "VALUES ($1, $2, now() + interval '1 hour')", token, nd["id"])
    return nd["id"], token


