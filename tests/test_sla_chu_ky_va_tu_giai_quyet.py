"""
DEV-01, DEV-03, DEV-05, DEV-06 — rà soát 12.11.2026. Postgres thật.

  DEV-01  Mở lại hội thoại vẫn dùng hạn SLA cũ (trigger đè hạn mới), và chu
          kỳ thứ hai không ghi được sự kiện SLA (UNIQUE theo hội thoại).
  DEV-03  Câu trả lời AI cho một tin đã LỖI THỜI (khách nhắn thêm, nhân viên
          tiếp quản, hội thoại đã giải quyết) vẫn được gửi.
  DEV-05  Không có worker tự giải quyết hội thoại nhàn rỗi.
  DEV-06  Hạn SLA tính liên tục 24/7, không theo giờ làm việc 08:00–21:00.
"""
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

VN = timezone(timedelta(hours=7))


def _schema(url: str) -> None:
    """Dựng schema + mọi migration lên CSDL kiểm thử (qua startup của app thử)."""
    with TestClient(_app(url, nguoi_thu(*Q))):
        pass


def _q(url: str, sql: str, *a, mot=True):
    async def chay():
        conn = await asyncpg.connect(url)
        try:
            return await (conn.fetchrow if mot else conn.fetch)(sql, *a)
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


# ====================================================================== DEV-06

def _han(url: str, bat_dau: datetime, phut: int, mo=8, dong=21) -> datetime:
    return _x(url, "SELECT sla_han($1, $2, $3, $4)", bat_dau, phut, mo, dong).astimezone(VN)


@pytest.mark.parametrize("bat_dau,phut,mong_doi", [
    # Trong giờ, còn đủ thời gian: cộng thẳng.
    ((2026, 11, 12, 10, 0), 15, (2026, 11, 12, 10, 15)),
    # Sát giờ đóng cửa: 5 phút hôm nay + 10 phút sáng mai.
    ((2026, 11, 12, 20, 55), 15, (2026, 11, 13, 8, 10)),
    # Đúng 21:00 là đã ngoài giờ.
    ((2026, 11, 12, 21, 0), 15, (2026, 11, 13, 8, 15)),
    # Ngoài giờ ban đêm: đồng hồ bắt đầu lúc mở cửa.
    ((2026, 11, 12, 23, 30), 15, (2026, 11, 13, 8, 15)),
    ((2026, 11, 12, 6, 0), 15, (2026, 11, 12, 8, 15)),
    # Hạn dài vắt qua nhiều ngày: 60' hôm nay, 13 tiếng ngày mai, 10 tiếng ngày kia.
    ((2026, 11, 12, 20, 0), 1440, (2026, 11, 14, 18, 0)),
    # Hết đúng lúc đóng cửa thì hạn là 21:00 hôm ấy, không đẩy sang mai.
    ((2026, 11, 12, 20, 45), 15, (2026, 11, 12, 21, 0)),
])
def test_han_sla_chi_tinh_trong_gio_lam_viec(csdl_kiem_thu, bat_dau, phut, mong_doi):
    _schema(csdl_kiem_thu)
    t = datetime(*bat_dau, tzinfo=VN)
    assert _han(csdl_kiem_thu, t, phut) == datetime(*mong_doi, tzinfo=VN)


def test_han_sla_24_7_khi_tat_gio_hoac_cau_hinh_vo_ly(csdl_kiem_thu):
    _schema(csdl_kiem_thu)
    t = datetime(2026, 11, 12, 23, 30, tzinfo=VN)
    assert _han(csdl_kiem_thu, t, 15, 0, 24) == t + timedelta(minutes=15)
    assert _han(csdl_kiem_thu, t, 15, 21, 8) == t + timedelta(minutes=15)    # vô lý → phục vụ khách
    assert _x(csdl_kiem_thu, "SELECT sla_han(now(), NULL, 8, 21)") is None
    # business_hours gõ sai không được làm hỏng việc tạo hội thoại.
    assert _x(csdl_kiem_thu, "SELECT sla_gio('{\"bat_dau\": \"tám giờ\"}'::jsonb, 'bat_dau', 8)") == 8
    assert _x(csdl_kiem_thu, "SELECT sla_gio('{\"bat_dau\": 9}'::jsonb, 'bat_dau', 8)") == 9


def test_moi_cho_dat_han_deu_dung_gio_lam_viec():
    from agent.omnichannel import giai_quyet, inbox_service, sla_gio

    assert "bieu_thuc_han(" in inspect.getsource(inbox_service.PostgresInboxTransaction.upsert_conversation)
    assert "bieu_thuc_han(" in inspect.getsource(giai_quyet.mo_lai_neu_da_giai_quyet)
    # Cùng cấu hình giờ với câu "ngoài giờ, mấy giờ có người".
    src = inspect.getsource(sla_gio.gio_sla)
    assert "gio_lam_viec_bat_dau" in src and "gio_lam_viec_ket_thuc" in src


# ====================================================================== DEV-01

def test_mo_lai_mo_chu_ky_sla_moi_va_giu_lich_su_cu(csdl_kiem_thu):
    from agent.omnichannel import giai_quyet

    _schema(csdl_kiem_thu)
    _x(csdl_kiem_thu, "INSERT INTO sla_policies (account_id, priority, first_response_minutes, "
                      "resolution_minutes, business_hours) VALUES (NULL,'normal',15,240,"
                      "'{\"bat_dau\":0,\"ket_thuc\":24}') RETURNING 1")
    tk = _kenh(csdl_kiem_thu)
    cid = _hoi_thoai(csdl_kiem_thu, tk, "kh1", cach_gio=0.01)
    cu = _q(csdl_kiem_thu, "SELECT first_response_due_at, resolution_due_at FROM conversations WHERE id=$1", cid)

    assert _goi(csdl_kiem_thu, giai_quyet.giai_quyet, cid, None)["da_truoc"] is False
    assert _goi(csdl_kiem_thu, giai_quyet.mo_lai_neu_da_giai_quyet, cid) is True

    c = _q(csdl_kiem_thu, "SELECT sla_chu_ky, first_response_due_at, resolution_due_at, "
                          "first_responded_at, state FROM conversations WHERE id=$1", cid)
    assert c["sla_chu_ky"] == 2 and c["state"] == "open" and c["first_responded_at"] is None
    # Hạn MỚI, ở tương lai — không phải hạn cũ đã qua (trigger từng đè về).
    nay = datetime.now(timezone.utc)
    assert c["first_response_due_at"] > nay > cu["first_response_due_at"]
    assert c["resolution_due_at"] > nay > cu["resolution_due_at"]
    assert abs((c["first_response_due_at"] - nay) - timedelta(minutes=15)) < timedelta(minutes=2)

    su_kien = _q(csdl_kiem_thu, "SELECT chu_ky, kind FROM sla_events WHERE conversation_id=$1 "
                                "ORDER BY chu_ky, kind", cid, mot=False)
    # Chu kỳ 1 vẫn còn nguyên; chu kỳ 2 có sự kiện bắt đầu riêng.
    assert (2, "started") in [(r["chu_ky"], r["kind"]) for r in su_kien]
    assert all(r["chu_ky"] in (1, 2) for r in su_kien)


def test_trong_mot_chu_ky_han_van_khong_doi_duoc(csdl_kiem_thu):
    """Đổi ưu tiên, gán lại… không được làm hạn trôi đi — chỉ chu kỳ mới mới được."""
    _schema(csdl_kiem_thu)
    tk = _kenh(csdl_kiem_thu)
    cid = _hoi_thoai(csdl_kiem_thu, tk, "kh2")
    cu = _x(csdl_kiem_thu, "SELECT resolution_due_at FROM conversations WHERE id=$1", cid)
    _x(csdl_kiem_thu, "UPDATE conversations SET resolution_due_at = now() + interval '9 days' "
                      "WHERE id=$1 RETURNING 1", cid)
    assert _x(csdl_kiem_thu, "SELECT resolution_due_at FROM conversations WHERE id=$1", cid) == cu
    _x(csdl_kiem_thu, "UPDATE conversations SET sla_chu_ky = sla_chu_ky + 1, "
                      "resolution_due_at = now() + interval '9 days' WHERE id=$1 RETURNING 1", cid)
    assert _x(csdl_kiem_thu, "SELECT resolution_due_at FROM conversations WHERE id=$1", cid) != cu


def test_cung_mot_loai_su_kien_ghi_duoc_o_moi_chu_ky(csdl_kiem_thu):
    from agent.omnichannel.sla import PostgresSlaRepository

    _schema(csdl_kiem_thu)
    tk = _kenh(csdl_kiem_thu)
    cid = _hoi_thoai(csdl_kiem_thu, tk, "kh3")
    _goi(csdl_kiem_thu, PostgresSlaRepository().mark_breaches)
    # Sang chu kỳ 2 với hạn đã qua: worker phải ghi được lần trễ THỨ HAI.
    _x(csdl_kiem_thu, "UPDATE conversations SET sla_chu_ky = 2, "
                      "first_response_due_at = now() - interval '1 minute', "
                      "resolution_due_at = now() - interval '1 minute' WHERE id=$1 RETURNING 1", cid)
    _goi(csdl_kiem_thu, PostgresSlaRepository().mark_breaches)
    rows = _q(csdl_kiem_thu, "SELECT chu_ky, kind FROM sla_events WHERE conversation_id=$1 "
                             "AND kind LIKE '%breached' ORDER BY chu_ky, kind", cid, mot=False)
    assert [(r["chu_ky"], r["kind"]) for r in rows] == [
        (1, "first_response_breached"), (1, "resolution_breached"),
        (2, "first_response_breached"), (2, "resolution_breached"),
    ]


def test_chinh_sach_rieng_cua_kenh_thang_chinh_sach_chung(csdl_kiem_thu):
    """`ORDER BY (account_id = $1) DESC` xếp chính sách CHUNG (NULL) lên đầu."""
    from agent.omnichannel import giai_quyet

    _schema(csdl_kiem_thu)
    tk = _kenh(csdl_kiem_thu)
    h = "'{\"bat_dau\":0,\"ket_thuc\":24}'"
    _x(csdl_kiem_thu, f"INSERT INTO sla_policies (account_id, priority, first_response_minutes, "
                      f"resolution_minutes, business_hours) VALUES (NULL,'normal',600,6000,{h}), "
                      f"($1,'normal',5,50,{h}) RETURNING 1", tk)
    cid = _hoi_thoai(csdl_kiem_thu, tk, "kh4", state="resolved", status="closed")
    assert _goi(csdl_kiem_thu, giai_quyet.mo_lai_neu_da_giai_quyet, cid) is True
    han = _x(csdl_kiem_thu, "SELECT first_response_due_at FROM conversations WHERE id=$1", cid)
    assert han - datetime.now(timezone.utc) < timedelta(minutes=10)      # 5 phút, không phải 600


# ====================================================================== DEV-05

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


# ====================================================================== DEV-03

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
