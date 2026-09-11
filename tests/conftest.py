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
