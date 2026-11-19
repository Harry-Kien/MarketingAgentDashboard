"""
Canh các chỗ SỬA KHI GHÉP nhánh Release 1 (selective-sync) vào main.

Mỗi test ứng với một chỗ hai nửa mã đúng riêng lẻ nhưng ghép lại thì hỏng
IM LẶNG — không lỗi, không nhật ký:

1. Việc xử lý ĐƠN (khách xin huỷ/đổi trả) mang nguon='agent', trùng nguồn với
   việc "khách cần người trả lời" mà main tự đóng khi giải quyết. Không phân
   biệt thì yêu cầu huỷ đơn biến mất khi nhân viên trả hội thoại cho agent.
2. Trigger 0045 cấm việc mở trên hội thoại đã kết thúc. Việc "giao hàng thất
   bại" của main gắn hội thoại của đơn — khách chat xong hôm qua thì việc bị
   từ chối, rơi vào nhánh except, không ai gọi khách hẹn giao lại.
3. Mã Release 1 `json.dumps` trước khi truyền vào `$n::jsonb`, trong khi codec
   đã dumps hộ: cột lưu một CHUỖI JSON, mọi `->>` trả NULL.
4. Cảnh báo SLA sớm (DEV-07) phải theo cùng công tắc 24/7 với hạn SLA.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "agent" / "schema.sql"


async def _codec(conn):
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def _chuan_bi(url: str) -> asyncpg.Pool:
    from agent import db
    from agent.migrations.runner import apply_all

    pool = await asyncpg.create_pool(url, min_size=1, max_size=4, init=_codec)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA.read_text(encoding="utf-8"))
        await apply_all(conn)
    db._pool = pool
    return pool


async def _hoi_thoai(pool, *, state: str = "open") -> UUID:
    async with pool.acquire() as conn:
        acc = await conn.fetchval(
            "INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
            "VALUES ('webchat', 'Ghep', 'active', gen_random_uuid()::text) RETURNING id")
        contact = await conn.fetchval(
            "INSERT INTO contacts (display_name) VALUES ('Khach Ghep') RETURNING id")
        point = await conn.fetchval(
            "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
            "VALUES ($1, $2, gen_random_uuid()::text) RETURNING id", contact, acc)
        return await conn.fetchval(
            """
            INSERT INTO conversations (account_id, channel, external_id, customer_ref,
                customer_name, contact_id, contact_point_id, state, status, mode)
            VALUES ($1, 'webchat', gen_random_uuid()::text, 'k', 'Khach Ghep', $2, $3,
                    $4, CASE WHEN $4 = 'resolved' THEN 'closed' ELSE 'escalated' END,
                    'human')
            RETURNING id
            """, acc, contact, point, state)


async def _don(pool, cid: UUID, ma: str) -> UUID:
    return await pool.fetchval(
        """
        INSERT INTO orders (ma_don, khach_ten, khach_sdt, khach_dia_chi, items,
                            tong_tien, trang_thai, conversation_id, channel)
        VALUES ($1, 'Khach Ghep', '0901234567', '1 Le Loi, Q1', '[]'::jsonb,
                100000, 'da_chot', $2, 'webchat')
        RETURNING id
        """, ma, cid)


def _chay(url, ham):
    async def run():
        from agent import db

        pool = await _chuan_bi(url)
        try:
            return await ham(pool)
        finally:
            await pool.close()
            db._pool = None

    return asyncio.run(run())


# ------------------------------------------------------------------ 1.
def test_tra_ve_agent_khong_dong_viec_xu_ly_don(csdl_kiem_thu):
    """
    `idx_cong_viec_agent_mot_viec` cho mỗi hội thoại MỘT việc nguon='agent'
    đang mở — việc nhắc và việc xử lý đơn không cùng tồn tại, nên kiểm trên
    hai hội thoại riêng.
    """
    from agent.omnichannel.giai_quyet import dong_viec_tu_sinh

    async def ham(pool):
        c_nhac = await _hoi_thoai(pool)
        nhac = await pool.fetchval(
            "INSERT INTO cong_viec (tieu_de, nguon, conversation_id) "
            "VALUES ('Khách cần người trả lời', 'agent', $1) RETURNING id", c_nhac)
        c_don = await _hoi_thoai(pool)
        oid = await _don(pool, c_don, "GHEP-01")
        huy = await pool.fetchval(
            "INSERT INTO cong_viec (tieu_de, nguon, conversation_id, order_id, loai_xu_ly_don) "
            "VALUES ('Xử lý yêu cầu hủy đơn GHEP-01', 'agent', $1, $2, 'huy') RETURNING id",
            c_don, oid)
        async with pool.acquire() as conn:
            await dong_viec_tu_sinh(conn, c_nhac)
            await dong_viec_tu_sinh(conn, c_don)
        return (await pool.fetchval("SELECT trang_thai FROM cong_viec WHERE id = $1", nhac),
                await pool.fetchval("SELECT trang_thai FROM cong_viec WHERE id = $1", huy))

    nhac, huy = _chay(csdl_kiem_thu, ham)
    assert nhac == "xong", "việc nhắc trả lời khách vẫn phải tự đóng"
    assert huy == "moi", "yêu cầu huỷ đơn của khách bị đóng hộ — biến mất khỏi danh sách việc"


def test_giai_quyet_bi_chan_boi_viec_xu_ly_don_nhung_khong_boi_viec_nhac(csdl_kiem_thu):
    from agent.omnichannel import giai_quyet

    async def ham(pool):
        c_nhac = await _hoi_thoai(pool)
        await pool.execute(
            "INSERT INTO cong_viec (tieu_de, nguon, conversation_id) "
            "VALUES ('Khách cần người trả lời', 'agent', $1)", c_nhac)
        c_don = await _hoi_thoai(pool)
        oid = await _don(pool, c_don, "GHEP-02")
        await pool.execute(
            "INSERT INTO cong_viec (tieu_de, nguon, conversation_id, order_id, loai_xu_ly_don) "
            "VALUES ('Xử lý yêu cầu hủy đơn GHEP-02', 'agent', $1, $2, 'huy')", c_don, oid)
        async with pool.acquire() as conn:
            async with conn.transaction():
                duoc_nhac = await giai_quyet.kiem_tra_dieu_kien_resolve(conn, c_nhac)
            bi_chan = False
            try:
                async with conn.transaction():
                    await giai_quyet.kiem_tra_dieu_kien_resolve(conn, c_don)
            except giai_quyet.ConversationHasPendingTasksError:
                bi_chan = True
        return duoc_nhac, bi_chan

    duoc_nhac, bi_chan = _chay(csdl_kiem_thu, ham)
    assert duoc_nhac is True, "việc nhắc tự sinh không được chặn Resolve — Resolve tự đóng nó"
    assert bi_chan is True, "còn yêu cầu huỷ đơn mà vẫn Resolve được"


# ------------------------------------------------------------------ 2.
def test_viec_van_chuyen_tren_hoi_thoai_da_dong_van_duoc_tao(csdl_kiem_thu, monkeypatch):
    from agent import canh_gac
    from agent.core import cong_viec

    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen", lambda *a, **k: None)

    async def ham(pool):
        cid = await _hoi_thoai(pool, state="resolved")
        vid = await cong_viec.tao_tu_van_chuyen(
            "GHEP-03", tieu_de="Gọi khách hẹn giao lại đơn GHEP-03",
            mo_ta="Giao thất bại", khoa="van_chuyen:that_bai:GHEP-03",
            conversation_id=cid)
        dong = await pool.fetchrow(
            "SELECT conversation_id, contact_id, trang_thai FROM cong_viec WHERE id = $1",
            UUID(vid)) if vid else None
        return vid, dong

    vid, dong = _chay(csdl_kiem_thu, ham)
    assert vid is not None, "việc giao thất bại bị trigger 0045 từ chối — không ai gọi khách"
    assert dong["conversation_id"] is None and dong["contact_id"] is not None
    assert dong["trang_thai"] == "moi"


# ------------------------------------------------------------------ 3.
def test_jsonb_van_don_luu_object_khong_phai_chuoi(csdl_kiem_thu):
    from agent.shipping import doi_soat

    async def ham(pool):
        cid = await _hoi_thoai(pool)
        oid = await _don(pool, cid, "GHEP-04")
        await pool.execute(
            "INSERT INTO shipping_waybill_requests (order_id, ma_don, client_order_code) "
            "VALUES ($1, 'GHEP-04', 'GHEP-04')", oid)
        await doi_soat.chot_luu_van_don_thanh_cong(
            order_id=oid, ma_don="GHEP-04", ma_van_don="GHN-GHEP-04",
            provider_code="ghn", du_lieu_phan_hoi={"order_code": "GHN-GHEP-04",
                                                    "luc": datetime.now(timezone.utc)})
        return await pool.fetchrow(
            "SELECT jsonb_typeof(du_lieu_phan_hoi) AS kieu, "
            "du_lieu_phan_hoi->>'order_code' AS ma FROM shipping_waybill_requests "
            "WHERE order_id = $1", oid)

    r = _chay(csdl_kiem_thu, ham)
    assert r["kieu"] == "object", "JSONB bị mã hoá hai lần — lưu thành chuỗi"
    assert r["ma"] == "GHN-GHEP-04"


def test_khong_ghi_van_don_len_don_da_huy(csdl_kiem_thu):
    from agent.shipping import doi_soat

    async def ham(pool):
        cid = await _hoi_thoai(pool)
        oid = await _don(pool, cid, "GHEP-05")
        await pool.execute("UPDATE orders SET trang_thai = 'da_huy' WHERE id = $1", oid)
        try:
            await doi_soat.chot_luu_van_don_thanh_cong(
                order_id=oid, ma_don="GHEP-05", ma_van_don="GHN-GHEP-05",
                provider_code="ghn")
        except doi_soat.DonKhongConChot:
            return await pool.fetchval("SELECT ma_van_don FROM orders WHERE id = $1", oid), True
        return None, False

    ma, da_chan = _chay(csdl_kiem_thu, ham)
    assert da_chan, "đơn huỷ giữa lúc chờ hãng vẫn được ghi mã vận đơn"
    assert ma is None


# ------------------------------------------------------------------ 4.
@pytest.mark.parametrize("theo_gio, mong", [(False, timedelta(hours=20)),
                                            (True, timedelta(hours=1))])
def test_canh_bao_sla_theo_cung_cong_tac_24_7(monkeypatch, theo_gio, mong):
    from agent.config import settings
    from agent.omnichannel.sla import thoi_gian_sla_da_tieu_thu

    monkeypatch.setattr(settings, "sla_theo_gio_lam_viec", theo_gio)
    monkeypatch.setattr(settings, "gio_lam_viec_bat", True)
    monkeypatch.setattr(settings, "gio_lam_viec_bat_dau", 8)
    monkeypatch.setattr(settings, "gio_lam_viec_ket_thuc", 21)
    vn = timezone(timedelta(hours=7))
    # 20:00 → 16:00 hôm sau: 20 giờ đồng hồ, 1 + 8 = 9 giờ làm việc.
    bat_dau = datetime(2026, 11, 18, 20, 0, tzinfo=vn)
    ket_thuc = datetime(2026, 11, 19, 16, 0, tzinfo=vn)
    da_tieu = thoi_gian_sla_da_tieu_thu(bat_dau, ket_thuc)
    if theo_gio:
        assert da_tieu == timedelta(hours=9)
    else:
        assert da_tieu == mong, "SLA tính 24/7 mà cảnh báo vẫn đếm theo giờ làm việc"
