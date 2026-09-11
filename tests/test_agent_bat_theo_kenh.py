"""
Agent bật/tắt theo từng kênh.

RÀNG BUỘC QUAN TRỌNG NHẤT: TẮT KHÔNG PHẢI LÀ IM.

Tắt agent cho một kênh mà tin khách rơi vào hư không thì "agent là tuỳ chọn"
biến thành "kênh chết im lặng": tin vào, không ai trả lời, và dashboard vẫn
xanh vì không có gì hỏng cả. Đúng loại lỗi `CLAUDE.md` liệt kê.

Nên: tắt agent -> hội thoại chuyển sang người VÀ sinh một công việc.
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


async def _dung(url: str):
    import asyncpg

    from agent.migrations.runner import apply_all

    async def _codec(conn):
        await conn.set_type_codec("jsonb", encoder=json.dumps,
                                  decoder=json.loads, schema="pg_catalog")

    pool = await asyncpg.create_pool(url, min_size=1, max_size=3, init=_codec)
    async with pool.acquire() as conn:
        await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
        await apply_all(conn)
        tk = await conn.fetchval(
            "INSERT INTO channel_accounts (channel, display_name, status) "
            "VALUES ('webchat', 'Web shop', 'active') RETURNING id")
        kh = await conn.fetchval(
            "INSERT INTO contacts (display_name) VALUES ('Chị Hoa') RETURNING id")
        diem = await conn.fetchval(
            "INSERT INTO contact_points (contact_id, channel_account_id, "
            "external_user_id) VALUES ($1,$2,'w1') RETURNING id", kh, tk)
        cid = await conn.fetchval(
            "INSERT INTO conversations (account_id, channel, external_id, "
            "customer_ref, customer_name, contact_id, contact_point_id) "
            "VALUES ($1,'webchat','w1','w1','Chị Hoa',$2,$3) RETURNING id",
            tk, kh, diem)
    return pool, tk, cid


def _chay(url, kich_ban):
    async def boc():
        from agent import db

        pool, tk, cid = await _dung(url)
        cu = db._pool
        db._pool = pool
        try:
            return await kich_ban(pool, tk, cid)
        finally:
            db._pool = cu
            await pool.close()

    return asyncio.run(boc())


def test_mac_dinh_agent_BAT_cho_kenh_moi(csdl_kiem_thu):
    """
    Cột này thêm vào một hệ thống đang chạy. Mặc định `false` là sáng hôm
    sau agent im lặng trên mọi kênh và không ai hiểu vì sao — migration
    không được là chỗ đổi hành vi của thứ đang chạy.
    """
    async def kich_ban(pool, tk, cid):
        async with pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT agent_bat FROM channel_accounts WHERE id = $1", tk)

    assert _chay(csdl_kiem_thu, kich_ban) is True


def test_cho_phep_khi_moi_thu_binh_thuong(csdl_kiem_thu):
    from agent.core import agent_bat

    async def kich_ban(pool, tk, cid):
        async with pool.acquire() as conn:
            conv = dict(await conn.fetchrow(
                "SELECT status, mode FROM conversations WHERE id = $1", cid))
        return await agent_bat.agent_duoc_tra_loi(tk, conv)

    kq = _chay(csdl_kiem_thu, kich_ban)
    assert kq.duoc is True


def test_tat_theo_kenh_thi_chan_va_NOI_RO_LY_DO(csdl_kiem_thu):
    """
    Một hàm trả True/False là đủ để chặn, nhưng không đủ để ai đó trả lời
    câu "vì sao kênh này agent không nói gì" — và câu ấy luôn được hỏi,
    thường là lúc khách đã chờ hai tiếng.
    """
    from agent.core import agent_bat

    async def kich_ban(pool, tk, cid):
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE channel_accounts SET agent_bat = false, "
                "agent_tat_ly_do = 'khách Facebook hỏi khó' WHERE id = $1", tk)
            conv = dict(await conn.fetchrow(
                "SELECT status, mode FROM conversations WHERE id = $1", cid))
        return await agent_bat.agent_duoc_tra_loi(tk, conv)

    kq = _chay(csdl_kiem_thu, kich_ban)
    assert kq.duoc is False
    assert "Web shop" in kq.ly_do
    assert "khách Facebook hỏi khó" in kq.ly_do


def test_cong_tac_toan_cuc_thang_va_khong_hoi_CSDL(csdl_kiem_thu, monkeypatch):
    """
    Kiểm toàn cục TRƯỚC: khi người vận hành bấm ngắt khẩn cấp, không được
    còn phụ thuộc vào việc CSDL có trả lời kịp hay không.
    """
    from agent import runtime
    from agent.core import agent_bat

    monkeypatch.setattr(runtime, "enabled", lambda: False)

    async def kich_ban(pool, tk, cid):
        return await agent_bat.agent_duoc_tra_loi(tk, None)

    kq = _chay(csdl_kiem_thu, kich_ban)
    assert kq.duoc is False
    assert "toàn hệ thống" in kq.ly_do


def test_hoi_thoai_da_co_nguoi_thi_agent_dung_ngoai(csdl_kiem_thu):
    from agent.core import agent_bat

    async def kich_ban(pool, tk, cid):
        return await agent_bat.agent_duoc_tra_loi(
            tk, {"status": "escalated", "mode": "human"})

    kq = _chay(csdl_kiem_thu, kich_ban)
    assert kq.duoc is False
    assert "người tiếp quản" in kq.ly_do


def test_tai_khoan_khong_ton_tai_thi_CHAN(csdl_kiem_thu):
    """
    Cho qua là mở đường cho một hội thoại trỏ vào tài khoản đã xoá được
    agent trả lời nhân danh một kênh không còn tồn tại.
    """
    from agent.core import agent_bat

    async def kich_ban(pool, tk, cid):
        return await agent_bat.agent_duoc_tra_loi(
            "00000000-0000-0000-0000-0000000000ff", None)

    kq = _chay(csdl_kiem_thu, kich_ban)
    assert kq.duoc is False
    assert "Không tìm thấy" in kq.ly_do


def test_tat_agent_thi_SINH_VIEC_chu_khong_im_lang(csdl_kiem_thu):
    """
    Đây là ràng buộc trung tâm của khối D.

    Không có nó thì tắt agent = kênh chết im lặng: tin vào, không ai trả
    lời, dashboard vẫn xanh.
    """
    from agent.core import agent_bat, cong_viec

    async def kich_ban(pool, tk, cid):
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE channel_accounts SET agent_bat = false, "
                "agent_tat_ly_do = 'để người trực' WHERE id = $1", tk)
            conv = dict(await conn.fetchrow(
                "SELECT status, mode, customer_name FROM conversations "
                "WHERE id = $1", cid))

        kq = await agent_bat.agent_duoc_tra_loi(tk, conv)
        assert not kq.duoc
        # Mô phỏng đúng thứ `handle_inbound` làm khi bị chặn.
        await cong_viec.tao_tu_chuyen_nguoi(
            cid, ly_do=kq.ly_do, ten_khach=conv["customer_name"])

        async with pool.acquire() as conn:
            return dict(await conn.fetchrow(
                "SELECT tieu_de, mo_ta, nguon, nguoi_nhan FROM cong_viec"))

    v = _chay(csdl_kiem_thu, kich_ban)
    assert v["nguon"] == "agent"
    assert v["nguoi_nhan"] is None, "việc phải CHƯA GIAO để ai cũng thấy"
    assert "Chị Hoa" in v["tieu_de"]
    assert "để người trực" in v["mo_ta"], "lý do tắt phải đi vào mô tả việc"


def test_main_py_that_su_goi_va_sinh_viec():
    """
    Test trên mô phỏng thứ `handle_inbound` làm. Nếu `main.py` không gọi
    như vậy thì test vẫn xanh trong khi hệ thống thật vẫn im lặng.
    """
    noi_dung = (ROOT / "agent" / "main.py").read_text(encoding="utf-8")
    assert "agent_bat.agent_duoc_tra_loi(" in noi_dung
    vt = noi_dung.index("agent_bat.agent_duoc_tra_loi(")
    doan = noi_dung[vt:vt + 1400]
    assert "cong_viec.tao_tu_chuyen_nguoi(" in doan, (
        "agent bị chặn mà không sinh việc — tin khách rơi vào hư không")
    assert "conversation.escalated" in doan
