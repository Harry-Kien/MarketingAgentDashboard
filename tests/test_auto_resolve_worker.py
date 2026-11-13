"""Kiểm thử DEV-05: Tự động giải quyết hội thoại nhàn rỗi kết hợp Resolve Guard DEV-04."""
from __future__ import annotations

import asyncio
import inspect
import os
import sys
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


def _q(url: str, sql: str, *a):
    async def chay():
        conn = await asyncpg.connect(url)
        try:
            return await conn.fetchrow(sql, *a)
        finally:
            await conn.close()
    return asyncio.run(chay())


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


def _tu_giai_quyet(url: str, gio: float = 4.0) -> list:
    from agent.omnichannel import giai_quyet
    return _goi(url, giai_quyet.tu_giai_quyet_mot_luot, gio)


def test_tu_giai_quyet_hoi_thoai_nhan_roi_va_ghi_ly_do(csdl_kiem_thu):
    _schema(csdl_kiem_thu)
    tk = _kenh(csdl_kiem_thu)
    cid = _hoi_thoai(csdl_kiem_thu, tk, "kh5", cach_gio=5,
                     han_xong="now() + interval '1 day'")
    assert _tu_giai_quyet(csdl_kiem_thu) == [cid]
    c = _q(csdl_kiem_thu, "SELECT state, status, outcome, resolved_at FROM conversations WHERE id=$1", cid)
    assert (c["state"], c["status"], c["outcome"]) == ("resolved", "closed", "resolved") and c["resolved_at"]
    su = _q(csdl_kiem_thu, "SELECT detail FROM events WHERE kind='conversation.resolved' AND ref_id=$1", cid)
    assert su and "nhàn rỗi" in str(su["detail"]) and "tu_dong" in str(su["detail"])
    assert _x(csdl_kiem_thu, "SELECT count(*) FROM sla_events WHERE conversation_id=$1 "
                             "AND kind='resolution_met'", cid) == 1
    assert _tu_giai_quyet(csdl_kiem_thu) == []                        # lần hai: không gì để làm


@pytest.mark.parametrize("ten,chuan_bi", [
    ("khách đang chờ trả lời", dict(vai_cuoi="customer")),
    ("nhân viên đang cầm", dict(mode="human", status="escalated")),
    ("mới có tin 1 giờ trước", dict(cach_gio=1)),
])
def test_khong_tu_giai_quyet_khi_con_nguoi_cho(csdl_kiem_thu, ten, chuan_bi):
    _schema(csdl_kiem_thu)
    tk = _kenh(csdl_kiem_thu)
    _hoi_thoai(csdl_kiem_thu, tk, "kh6", **{"cach_gio": 5, **chuan_bi})
    assert _tu_giai_quyet(csdl_kiem_thu) == [], ten


@pytest.mark.parametrize("ten,sql", [
    ("việc đang mở", "INSERT INTO cong_viec (tieu_de, conversation_id) VALUES ('Gọi lại khách', $1) RETURNING 1"),
    ("bản nháp chờ duyệt", "INSERT INTO messages (conversation_id, role, content, delivery_status, created_at) "
                           "VALUES ($1,'agent','nháp','draft', now() - interval '6 hours') RETURNING 1"),
    ("đơn chờ duyệt", "INSERT INTO orders (ma_don, conversation_id, khach_ten, khach_sdt, khach_dia_chi, "
                      "items, tong_tien, trang_thai) VALUES ('DH-TGQ', $1, 'Lan', '0912345678', 'x', "
                      "'[]', 2000000, 'cho_duyet') RETURNING 1"),
])
def test_khong_tu_giai_quyet_khi_con_viec_do(csdl_kiem_thu, ten, sql):
    _schema(csdl_kiem_thu)
    tk = _kenh(csdl_kiem_thu)
    cid = _hoi_thoai(csdl_kiem_thu, tk, "kh7", cach_gio=5)
    _x(csdl_kiem_thu, sql, cid)
    assert _tu_giai_quyet(csdl_kiem_thu) == [], ten


def test_tat_tu_giai_quyet_bang_0(csdl_kiem_thu):
    _schema(csdl_kiem_thu)
    tk = _kenh(csdl_kiem_thu)
    _hoi_thoai(csdl_kiem_thu, tk, "kh8", cach_gio=50)
    assert _tu_giai_quyet(csdl_kiem_thu, 0) == []


def test_worker_tu_giai_quyet_duoc_bat_va_co_heartbeat():
    import agent.main as m
    from agent.config import settings
    from agent.omnichannel import giai_quyet

    assert settings.tu_giai_quyet_sau_gio == 4.0
    assert "tu_giai_quyet_loop(" in inspect.getsource(m.lifespan)
    assert "heartbeat_tu_giai_quyet(" in inspect.getsource(giai_quyet.tu_giai_quyet_loop)
    # Chọn và đóng trong MỘT câu có khoá dòng — không đóng nhầm khách vừa nhắn.
    src = inspect.getsource(giai_quyet.tu_giai_quyet_mot_luot)
    assert "FOR UPDATE OF c SKIP LOCKED" in src
    assert "TU_GIAI_QUYET_SAU_GIO=" in (ROOT / ".env.example").read_text(encoding="utf-8")

