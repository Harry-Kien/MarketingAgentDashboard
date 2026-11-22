"""
Công tắc AI Agent TOÀN CỤC (Cấu hình AI Agent → Cấu hình cơ bản) chạy qua
đường xử lý tin vào THẬT — `handle_inbound` trên Postgres, ingest thật.

Phiếu việc 20.11.2026 đặt ba quy tắc, và cả ba phải đúng ở MÃ, không phải ở
câu chữ trên màn hình:

    1. AI TẮT  -> không câu trả lời, không bản nháp AI nào; tin khách vào
                  hàng chờ người, nhân viên làm việc bình thường.
    2. Nhân viên đã tiếp quản -> AI không trả lời, dù công tắc đang BẬT.
    3. BẬT lại AI không giành hội thoại nhân viên đang cầm.

`tests/test_agent_bat_theo_kenh.py` kiểm hàm quyết định `agent_duoc_tra_loi`
và đọc mã `xu_ly_tin_vao` bằng chuỗi. Ở đây kiểm KẾT QUẢ: bộ não có bị gọi
không, CSDL còn gì, ai bị báo — vì một nhánh có thể gọi đúng hàm mà vẫn để
lọt một đường khác tới `brain.respond`.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

LUOC_DO = ROOT / "agent" / "schema.sql"
REF = "w-cong-tac"


async def _dung(url: str):
    import asyncpg

    from agent.migrations.runner import apply_all

    async def _codec(conn):
        await conn.set_type_codec("jsonb", encoder=json.dumps,
                                  decoder=json.loads, schema="pg_catalog")

    pool = await asyncpg.create_pool(url, min_size=1, max_size=4, init=_codec)
    async with pool.acquire() as conn:
        await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
        await apply_all(conn)
        tk = await conn.fetchval(
            "INSERT INTO channel_accounts (channel, display_name, status) "
            "VALUES ('webchat', 'Web shop', 'active') RETURNING id")
        nv = await conn.fetchval(
            "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam) "
            "VALUES ('lan', 'x') RETURNING id")
        await conn.execute(
            "INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id) "
            "SELECT $1, id FROM vai_tro WHERE ten = 'Nhân viên'", nv)
        await conn.execute(
            "INSERT INTO account_memberships (account_id, user_id, role) "
            "VALUES ($1, $2, 'agent')", tk, nv)
    return pool, tk, nv


def _tin(tk, chu="Shop ơi còn hàng không ạ"):
    from agent.channels.base import InboundMessage

    return InboundMessage(
        account_id=tk, channel="webchat", conversation_ref=REF, customer_ref=REF,
        customer_name="Chị Hoa", text=chu, dedupe_key=f"t-{uuid4().hex}",
        received_at=datetime.now(timezone.utc))


@pytest.fixture
def chay(csdl_kiem_thu, monkeypatch):
    """
    Chạy một kịch bản với CSDL thật, bộ não bị thay bằng cái bẫy đếm số lần
    được gọi, và công tắc toàn cục đặt bằng đúng đường dashboard ghi
    (`runtime.STATE`, qua `runtime.luu` khi kịch bản cần).
    """
    from agent import db, runtime
    from agent.omnichannel import xu_ly_tin_vao

    goi_nao: list[str] = []

    async def bay(*_a, **_k):
        goi_nao.append("respond")
        raise AssertionError("bộ não AI bị gọi trong khi không được phép trả lời")

    monkeypatch.setattr(xu_ly_tin_vao.brain, "respond", bay)
    monkeypatch.setitem(runtime.STATE, "enabled", runtime.STATE["enabled"])

    def _chay(kich_ban):
        async def boc():
            pool, tk, nv = await _dung(csdl_kiem_thu)
            cu = db._pool
            db._pool = pool
            try:
                return await kich_ban(pool, tk, nv)
            finally:
                db._pool = cu
                await pool.close()

        return asyncio.run(boc()), goi_nao

    return _chay


async def _hoi_thoai_nhan_vien_dang_cam(pool, tk, nv):
    """Một hội thoại có sẵn tin khách, do nhân viên `nv` đã bấm tiếp quản."""
    from agent.omnichannel.inbox_service import InboxService, PostgresInboxRepository

    kq = await InboxService(PostgresInboxRepository()).ingest(_tin(tk, "Tin đầu"))
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE conversations SET mode = 'human', status = 'escalated', "
            "assigned_to = $2 WHERE id = $1", kq.conversation_id, nv)
    return kq.conversation_id


async def _anh_chup(pool, cid):
    async with pool.acquire() as c:
        hd = dict(await c.fetchrow(
            "SELECT mode, status, assigned_to FROM conversations WHERE id = $1", cid))
        ai = await c.fetchval(
            "SELECT count(*) FROM messages WHERE conversation_id = $1 AND role = 'agent'", cid)
        khach = await c.fetchval(
            "SELECT count(*) FROM messages WHERE conversation_id = $1 AND role = 'customer'", cid)
        tb = await c.fetchval(
            "SELECT count(*) FROM thong_bao WHERE conversation_id = $1", cid)
    return hd, ai, khach, tb


def test_ai_TAT_khong_tra_loi_khong_nhap_va_vao_hang_cho_nguoi(chay):
    from agent import runtime
    from agent.omnichannel import xu_ly_tin_vao

    async def kich_ban(pool, tk, nv):
        runtime.STATE["enabled"] = False
        await xu_ly_tin_vao.handle_inbound(_tin(tk))
        async with pool.acquire() as c:
            cid = await c.fetchval(
                "SELECT id FROM conversations WHERE external_id = $1", REF)
        return await _anh_chup(pool, cid)

    (hd, ai, khach, tb), goi = chay(kich_ban)
    assert goi == [], "AI tắt mà bộ não vẫn bị gọi"
    assert ai == 0, "AI tắt mà vẫn có tin/bản nháp vai agent"
    assert khach == 1, "tin khách phải được LƯU — tắt AI không phải là im"
    assert hd["mode"] == "human" and hd["status"] == "escalated", (
        "tin vào lúc AI tắt phải nằm ở hàng chờ người")
    assert tb == 1, "phải báo nhân viên kênh — không thì kênh chết im lặng"


def test_nhan_vien_da_tiep_quan_thi_AI_khong_tra_loi_du_dang_BAT(chay):
    from agent import runtime
    from agent.omnichannel import xu_ly_tin_vao

    async def kich_ban(pool, tk, nv):
        runtime.STATE["enabled"] = True
        cid = await _hoi_thoai_nhan_vien_dang_cam(pool, tk, nv)
        await xu_ly_tin_vao.handle_inbound(_tin(tk, "Em hỏi thêm chút"))
        return await _anh_chup(pool, cid), nv

    ((hd, ai, khach, tb), nv), goi = chay(kich_ban)
    assert goi == [], "nhân viên đang cầm hội thoại mà AI vẫn soạn trả lời"
    assert ai == 0
    assert khach == 2
    assert hd["mode"] == "human" and hd["assigned_to"] == nv, (
        "hội thoại phải vẫn là của nhân viên đang tiếp quản")
    assert tb == 0, "nhân viên đang làm việc — không có gì để báo 'AI chuyển giao'"


def test_bat_lai_AI_khong_gianh_hoi_thoai_nhan_vien_dang_cam(chay):
    """
    Tắt AI -> khách nhắn -> BẬT AI (đúng đường dashboard: runtime.luu, ghi
    bảng cau_hinh_agent) -> khách nhắn tiếp. Hội thoại vẫn của nhân viên,
    AI không nói câu nào, và lúc AI tắt cũng không bắn thông báo thừa cho
    hội thoại nhân viên đang cầm (thứ tự xét trong agent_bat).
    """
    from agent import runtime
    from agent.omnichannel import xu_ly_tin_vao

    async def kich_ban(pool, tk, nv):
        runtime.STATE["enabled"] = True
        cid = await _hoi_thoai_nhan_vien_dang_cam(pool, tk, nv)
        runtime.STATE["enabled"] = False
        await xu_ly_tin_vao.handle_inbound(_tin(tk, "Alo shop"))
        _, _, _, tb_luc_tat = await _anh_chup(pool, cid)

        await runtime.luu({"enabled": True}, boi="kiem_thu")
        async with pool.acquire() as c:
            luu = await c.fetchval(
                "SELECT gia_tri FROM cau_hinh_agent WHERE khoa = 'enabled'")
        await xu_ly_tin_vao.handle_inbound(_tin(tk, "Shop ơi"))
        return await _anh_chup(pool, cid), tb_luc_tat, luu, nv

    ((hd, ai, khach, tb), tb_luc_tat, luu, nv), goi = chay(kich_ban)
    assert luu is True, "công tắc phải BỀN qua khởi động lại (bảng cau_hinh_agent)"
    assert goi == [], "bật lại AI mà AI chen vào hội thoại nhân viên đang cầm"
    assert ai == 0 and khach == 3
    assert hd["mode"] == "human" and hd["assigned_to"] == nv
    assert tb_luc_tat == 0 and tb == 0, (
        "AI tắt + hội thoại nhân viên đang cầm: không được báo 'AI chuyển giao'")


def test_agent_bat_xet_nguoi_tiep_quan_TRUOC_cong_tac():
    """Neo thứ tự mà test trên dựa vào — đổi lại là thông báo thừa quay về."""
    from agent import runtime
    from agent.core import agent_bat

    cu = runtime.STATE["enabled"]
    runtime.STATE["enabled"] = False
    try:
        kq = asyncio.run(agent_bat.agent_duoc_tra_loi(
            None, {"status": "escalated", "mode": "human"}))
    finally:
        runtime.STATE["enabled"] = cu
    assert not kq.duoc and "người tiếp quản" in kq.ly_do
