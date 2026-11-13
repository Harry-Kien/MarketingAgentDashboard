"""Kiểm thử DEV-03: Chống AI gửi phản hồi lỗi thời sau khi nhân viên Takeover / có tin mới / đã giải quyết."""
from __future__ import annotations

import asyncio
import inspect
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.conftest import nguoi_thu  # noqa: E402
from tests.test_giai_quyet_csat import Q, _app, _goi  # noqa: E402


def _schema(url: str) -> None:
    """Dựng schema + mọi migration lên CSDL kiểm thử (qua startup của app thử)."""
    with TestClient(_app(url, nguoi_thu(*Q))):
        pass


def _x(url: str, sql: str, *a):
    async def chay():
        conn = await asyncpg.connect(url)
        try:
            return await conn.fetchval(sql, *a)
        finally:
            await conn.close()
    return asyncio.run(chay())


def _kenh(url: str, ma: str = "web-sla") -> UUID:
    return _x(url, "INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
                   "VALUES ('webchat','Web','active',$1) RETURNING id", ma)


def _hoi_thoai(url: str, tk: UUID, ma: str, *, cach_gio: float = 5.0, vai_cuoi: str = "agent",
               state: str = "open", mode: str = "auto", status: str = "auto",
               han_dau: str = "now() - interval '3 hours'", han_xong: str = "now() - interval '1 hour'") -> UUID:
    kh = _x(url, "INSERT INTO contacts (display_name) VALUES ('Lan') RETURNING id")
    dm = _x(url, "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
                 "VALUES ($1,$2,$3) RETURNING id", kh, tk, ma)
    cid = _x(url, f"INSERT INTO conversations (account_id, channel, external_id, customer_ref, customer_name, "
                  f"contact_id, contact_point_id, state, mode, status, first_response_due_at, resolution_due_at) "
                  f"VALUES ($1,'webchat',$2,$2,'Lan',$6,$7,$3,$4,$5,{han_dau},{han_xong}) RETURNING id",
             tk, ma, state, mode, status, kh, dm)
    _x(url, "INSERT INTO messages (conversation_id, role, content, created_at) VALUES "
            "($1,'customer','hỏi', now() - make_interval(secs => $2 + 60)), "
            "($1,$3,'trả lời', now() - make_interval(secs => $2)) RETURNING 1",
       cid, cach_gio * 3600, vai_cuoi)
    return cid


def test_nhan_dien_phan_hoi_loi_thoi(csdl_kiem_thu):
    from agent.omnichannel.xu_ly_tin_vao import LY_DO_LOI_THOI, ly_do_loi_thoi

    _schema(csdl_kiem_thu)
    tk = _kenh(csdl_kiem_thu)
    cid = _hoi_thoai(csdl_kiem_thu, tk, "kh9", cach_gio=0.01, vai_cuoi="customer")
    tin = _x(csdl_kiem_thu, "SELECT id FROM messages WHERE conversation_id=$1 "
                            "ORDER BY created_at DESC LIMIT 1", cid)
    assert _goi(csdl_kiem_thu, ly_do_loi_thoi, cid, tin) is None

    _x(csdl_kiem_thu, "INSERT INTO messages (conversation_id, role, content) "
                      "VALUES ($1,'customer','à mà shop ơi') RETURNING 1", cid)
    assert _goi(csdl_kiem_thu, ly_do_loi_thoi, cid, tin) == "co_tin_moi_hon"

    _x(csdl_kiem_thu, "UPDATE conversations SET state='resolved' WHERE id=$1 RETURNING 1", cid)
    assert _goi(csdl_kiem_thu, ly_do_loi_thoi, cid, tin) == "da_giai_quyet"

    _x(csdl_kiem_thu, "UPDATE conversations SET mode='human' WHERE id=$1 RETURNING 1", cid)
    assert _goi(csdl_kiem_thu, ly_do_loi_thoi, cid, tin) == "nguoi_da_tiep_quan"
    assert set(LY_DO_LOI_THOI) == {"co_tin_moi_hon", "da_giai_quyet", "nguoi_da_tiep_quan"}


def test_khach_nhan_them_khi_ai_dang_soan_thi_bo_cau_tra_loi_cu(app_that, monkeypatch):
    """
    Đầu-cuối trên app thật: AI đang soạn cho tin 1 thì khách gửi tin 2.
    Câu trả lời cho tin 1 KHÔNG được xếp hàng gửi, không thành bản nháp, và
    trạng thái hội thoại không bị ghi đè.
    """
    from agent import db
    from agent.core import agent as brain
    from tests.test_nghiem_thu_saas import _kenh_webchat, _khach_nhan, _quan_tri_vao, _sql

    async def soan_cham(*, conversation_id, **kw):
        # Trong lúc "model đang chạy", khách nhắn thêm một tin.
        await db.execute("INSERT INTO messages (conversation_id, role, content) "
                         "VALUES ($1,'customer','à cho mình hỏi thêm')", conversation_id)
        return brain.Reply(text="Dạ kem này giá 250.000đ ạ", cost_usd=0.001)
    monkeypatch.setattr(brain, "respond", soan_cham)

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt, agent_bat=True)
    _khach_nhan(app_that, tk, "Chị Mai", "Kem chống nắng giá bao nhiêu?")

    async def doc():
        tra_loi = await db.fetchrow(
            "SELECT count(*) n FROM messages WHERE role='agent' AND content LIKE '%250.000%'")
        su = await db.fetchrow("SELECT detail FROM events WHERE kind='agent.superseded'")
        return tra_loi["n"], su
    so, su = _sql(app_that, doc)
    assert so == 0
    assert su and "co_tin_moi_hon" in str(su["detail"])


def test_xin_chuyen_nguoi_khong_bi_bo_du_loi_thoi():
    """Tín hiệu vượt thẩm quyền (mang thai, bệnh da…) không được mất vì khách nhắn thêm."""
    from agent.omnichannel import xu_ly_tin_vao

    src = inspect.getsource(xu_ly_tin_vao.handle_inbound)
    i = src.index("ly_do_loi_thoi(cid, ingested.message_id)")
    assert "if not reply.escalate:" in src[i - 200:i]
    # Kiểm TRƯỚC khi xếp hàng gửi và trước khi ghi trạng thái hội thoại.
    assert i < src.index("auto_send = ") < src.index("SET cost_usd = cost_usd + $2,")


def test_khong_xep_hang_tin_ai_vao_hoi_thoai_da_giai_quyet():
    from agent.omnichannel.outbound_service import OutboundBlocked, OutboundService

    with pytest.raises(OutboundBlocked):
        OutboundService._ensure_role_allowed({"mode": "auto", "status": "closed", "state": "resolved"}, "agent")
    with pytest.raises(OutboundBlocked):
        OutboundService._ensure_role_allowed({"mode": "human", "status": "auto", "state": "open"}, "agent")
    # Nhân viên và tin hệ thống vẫn gửi được (CSAT, cảm ơn…).
    OutboundService._ensure_role_allowed({"mode": "auto", "status": "closed", "state": "resolved"}, "staff")
    OutboundService._ensure_role_allowed({"mode": "auto", "status": "closed", "state": "resolved"}, "system")


def test_luc_gui_van_huy_tin_ai_khi_nguoi_da_tiep_quan():
    """Giai đoạn gửi thực tế: chốt có từ trước — ghim lại để không bị gỡ."""
    from agent.omnichannel.outbox import PostgresOutboxRepository

    src = inspect.getsource(PostgresOutboxRepository.delivery_guard)
    assert 'row["role"] == "agent"' in src and "human_takeover" in src

