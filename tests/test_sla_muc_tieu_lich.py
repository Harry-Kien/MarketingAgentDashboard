"""
SLA theo từng mục tiêu, lịch làm việc chung, hạn phản hồi sau chuyển giao
(phiếu việc chủ dự án mục 15 — 22.11.2026, migration 0062).

Mỗi ràng buộc một kiểu hỏng im lặng:

  1. MỘT lịch làm việc: câu báo ngoài giờ, quy tắc "ngoài giờ" và hạn SLA
     đọc cùng một lịch (dashboard trước, `.env` sau) — trước đây ba nguồn.
  2. Hạn đặt trong SQL và thời gian đo trong Python KHỚP nhau theo lịch tuần
     có ngày nghỉ và ngày lễ — lệch là cảnh báo tới sau vi phạm.
  3. Chế độ (giờ làm việc / 24/7) và ngưỡng cảnh báo chọn THEO MỤC TIÊU.
  4. Xác nhận tự động (tin `system`) KHÔNG đạt hạn phản hồi đầu, KHÔNG chốt
     lượt chuyển giao — xanh giả kiểu "đạt ở giây thứ hai".
  5. Mỗi lượt chuyển giao một hạn, một cảnh báo, một vi phạm; chuông tới
     người phụ trách; vi phạm không xoá được kể cả khi đã đọc thông báo.
  6. Phân tích tách mục tiêu sau chuyển giao, và AI / nhân viên ở giải quyết.
"""
from __future__ import annotations

import inspect
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import nguoi_thu
from test_phan_tich_va_sla import (
    LUOC_DO, NV, QT, _chay, _codec, _hoi_thoai, _kenh, _nguoi, _schema, _tin,
)

ROOT = Path(__file__).resolve().parent.parent
VN = timezone(timedelta(hours=7))


@pytest.fixture(autouse=True)
def _quen_bo_nho():
    """Lịch / mục tiêu nằm trong bộ nhớ tiến trình — không để lọt sang test khác."""
    from agent.omnichannel import sla_muc_tieu

    sla_muc_tieu.dat_lai_bo_nho()
    yield
    sla_muc_tieu.dat_lai_bo_nho()


def _lich_mau():
    """T2–T6 8:00–21:00, T7 9:00–12:00, CN nghỉ, lễ thứ Năm 26.11.2026."""
    from agent.core.lich_lam_viec import Lich

    return Lich(bat=True, tuan=((480, 1260),) * 5 + ((540, 720), None),
                ngay_nghi=((date(2026, 11, 26), "Lễ thử"),), nguon="csdl")


def _vn(*a) -> datetime:
    return datetime(*a, tzinfo=VN)


# ====================================================================== 1. lịch chung

def test_ngay_mau_dung_thu():
    assert date(2026, 11, 21).weekday() == 5 and date(2026, 11, 22).weekday() == 6
    assert date(2026, 11, 26).weekday() == 3


def test_lich_env_giu_nguyen_hanh_vi_cu(monkeypatch):
    from agent.config import settings
    from agent.core import gio_lam_viec, lich_lam_viec

    monkeypatch.setattr(settings, "gio_lam_viec_bat", True)
    monkeypatch.setattr(settings, "gio_lam_viec_bat_dau", 8)
    monkeypatch.setattr(settings, "gio_lam_viec_ket_thuc", 21)
    lich = lich_lam_viec.hien_hanh()
    assert lich.nguon == "env" and lich.gio_rieng and lich.tuan == ((480, 1260),) * 7
    assert gio_lam_viec.dang_trong_gio(_vn(2026, 11, 22, 10))       # Chủ nhật vẫn mở: .env không biết thứ
    assert not gio_lam_viec.dang_trong_gio(_vn(2026, 11, 22, 21))
    monkeypatch.setattr(settings, "gio_lam_viec_bat_dau", 21)
    monkeypatch.setattr(settings, "gio_lam_viec_ket_thuc", 8)
    assert gio_lam_viec.dang_trong_gio(_vn(2026, 11, 22, 3)), "cấu hình vô lý → trực suốt"
    assert lich_lam_viec.tieu_thu(_vn(2026, 11, 22, 0), _vn(2026, 11, 22, 1), lich_lam_viec.hien_hanh()) \
        == timedelta(hours=1), "không ngày nào có khung → đo 24/7, cùng quy ước SQL"


def test_lich_tuan_ngay_nghi_ngay_le_va_cau_bao_ngoai_gio(monkeypatch):
    from agent.config import settings
    from agent.core import gio_lam_viec, lich_lam_viec

    lich = _lich_mau()
    monkeypatch.setattr(lich_lam_viec, "_lich_csdl", lich)
    assert gio_lam_viec.dang_trong_gio(_vn(2026, 11, 21, 11, 59))
    assert not gio_lam_viec.dang_trong_gio(_vn(2026, 11, 21, 12, 0)), "T7 đóng 12:00"
    assert not gio_lam_viec.dang_trong_gio(_vn(2026, 11, 22, 10)), "Chủ nhật nghỉ"
    assert not gio_lam_viec.dang_trong_gio(_vn(2026, 11, 26, 10)), "ngày lễ nghỉ cả ngày"
    assert gio_lam_viec.dang_trong_gio(_vn(2026, 11, 27, 8))
    # Tối thứ Bảy: lần có người kế tiếp là 8 giờ thứ Hai — không phải "sáng mai".
    assert lich.lan_mo_ke_tiep(_vn(2026, 11, 21, 13)) == _vn(2026, 11, 23, 8)
    assert lich.lan_mo_ke_tiep(_vn(2026, 11, 25, 22)) == _vn(2026, 11, 27, 8), "bỏ qua ngày lễ"
    monkeypatch.setattr(lich_lam_viec, "_lich_csdl", lich_lam_viec.Lich(
        bat=True, tuan=((570, 1260),) * 7, nguon="csdl"))
    tin = gio_lam_viec.tin_chuyen_nguoi(_vn(2026, 11, 23, 23))
    assert tin == settings.tin_chuyen_nguoi_ngoai_gio.format(gio_mo="9 giờ 30")


def test_moi_noi_doc_gio_lam_viec_deu_qua_lich_chung():
    """Quy tắc tự động "ngoài giờ", cảnh báo sức khoẻ, câu báo khách: cùng một hàm."""
    from agent import suc_khoe
    from agent.core import gio_lam_viec
    from agent.omnichannel import tu_dong

    assert "gio_lam_viec.dang_trong_gio()" in inspect.getsource(tu_dong.chay_tin_khach)
    assert "gio_lam_viec.dang_trong_gio()" in inspect.getsource(suc_khoe)
    for ham in (gio_lam_viec.dang_trong_gio, gio_lam_viec.tin_chuyen_nguoi):
        src = inspect.getsource(ham)
        assert "lich_lam_viec.hien_hanh()" in src
        assert "settings.gio_lam_viec_bat_dau" not in src.split("if mo is not None")[0], \
            "đọc thẳng .env là quay lại ba nguồn giờ"


@pytest.mark.parametrize("sai, loi", [
    ({"tuan": []}, "7 ngày"),
    ({"tuan": [{"mo": "09:00", "dong": "08:00"}] * 7}, "giờ mở phải trước"),
    ({"tuan": [{"mo": "24:00", "dong": "24:00"}] * 7}, "không hợp lệ"),
    ({"tuan": [{"mo": "8h", "dong": "21:00"}] * 7}, "GG:PP"),
    ({"tuan": [{"nghi": True}] * 7}, "Không ngày nào mở"),
    ({"tuan": [{"mo": "08:00", "dong": "21:00"}] * 7,
      "ngay_nghi": [{"ngay": "2026-12-25"}, {"ngay": "2026-12-25"}]}, "bị lặp"),
    ({"tuan": [{"mo": "08:00", "dong": "21:00"}] * 7, "ngay_nghi": [{"ngay": "25/12"}]}, "NNNN-TT-NN"),
])
def test_chuan_hoa_lich_chan_luc_luu(sai, loi):
    from agent.core import lich_lam_viec

    with pytest.raises(ValueError, match=loi):
        lich_lam_viec.chuan_hoa(sai)


def test_chuan_hoa_lich_hop_le():
    from agent.core import lich_lam_viec

    bat, tuan, nghi = lich_lam_viec.chuan_hoa({
        "bat": True,
        "tuan": [{"mo": "08:30", "dong": "24:00"}] * 6 + [{"nghi": True}],
        "ngay_nghi": [{"ngay": "2027-01-01", "ten": "  Tết   dương lịch "}, {"ngay": "2026-12-31"}]})
    assert bat and tuan[0] == [510, 1440] and tuan[6] is None
    assert nghi == [{"ngay": "2026-12-31", "ten": ""}, {"ngay": "2027-01-01", "ten": "Tết dương lịch"}]
    # Tắt giờ làm việc thì đóng cả tuần vẫn lưu được (lịch chỉ để dành).
    assert lich_lam_viec.chuan_hoa({"bat": False, "tuan": [{"nghi": True}] * 7})[0] is False


# ====================================================================== 2. SQL ↔ Python

def test_tinh_tay_qua_ngay_nghi_va_ngay_le():
    from agent.core import lich_lam_viec

    lich = _lich_mau()
    # T7 11:50 + 30' = 10' thứ Bảy, nghỉ Chủ nhật, 20' sáng thứ Hai.
    assert lich_lam_viec.han(_vn(2026, 11, 21, 11, 50), 30, lich) == _vn(2026, 11, 23, 8, 20)
    assert lich_lam_viec.tieu_thu(_vn(2026, 11, 21, 11, 50), _vn(2026, 11, 23, 8, 20), lich) \
        == timedelta(minutes=30)
    # T4 20:30 + 60': 30' thứ Tư, lễ thứ Năm, 30' sáng thứ Sáu.
    assert lich_lam_viec.han(_vn(2026, 11, 25, 20, 30), 60, lich) == _vn(2026, 11, 27, 8, 30)
    assert lich_lam_viec.han(_vn(2026, 11, 22, 3), 15, None) == _vn(2026, 11, 22, 3, 15)


def test_sla_han_lich_trong_sql_khop_python(csdl_kiem_thu):
    """Hạn đặt bằng SQL, cảnh báo và Phân tích đo bằng Python — hai phép tính phải là một."""
    _schema(csdl_kiem_thu)
    from agent.core import lich_lam_viec

    lich = _lich_mau()
    j = json.dumps(lich.json_sql())
    moc = [_vn(2026, 11, 20, 6), _vn(2026, 11, 20, 20, 59), _vn(2026, 11, 21, 11, 50),
           _vn(2026, 11, 22, 15), _vn(2026, 11, 25, 20, 30), _vn(2026, 11, 26, 9), _vn(2026, 11, 23, 8)]

    async def ham(conn, _pool):
        for t in moc:
            for phut in (0, 1, 15, 30, 240, 780, 1440, 10000):
                sql = await conn.fetchval("SELECT sla_han_lich($1, $2, $3::text::jsonb)", t, phut, j)
                py = lich_lam_viec.han(t, phut, lich)
                assert sql == py, (t, phut, sql, py)
                assert lich_lam_viec.tieu_thu(t, py, lich) == timedelta(minutes=phut), (t, phut)
        # NULL = 24/7; lịch hỏng / không ngày mở → 24/7 (hỏng theo hướng phục vụ khách).
        t = _vn(2026, 11, 22, 3)
        assert await conn.fetchval("SELECT sla_han_lich($1, 15, NULL)", t) == t + timedelta(minutes=15)
        dong_ca_tuan = json.dumps({"tuan": [None] * 7, "nghi": []})
        assert await conn.fetchval("SELECT sla_han_lich($1, 15, $2::text::jsonb)", t, dong_ca_tuan) \
            == t + timedelta(minutes=15)
        assert await conn.fetchval("SELECT sla_han_lich($1, 15, '{\"tuan\": \"x\"}'::jsonb)", t) \
            == t + timedelta(minutes=15)
        assert await conn.fetchval("SELECT sla_han_lich(now(), NULL, NULL)") is None
        # Giờ riêng của chính sách: CHỈ khi lịch lui về .env (gio_rieng).
        env = json.dumps({**lich.json_sql(), "gio_rieng": True})
        gio = '{"bat_dau": 9, "ket_thuc": 18}'
        ra = await conn.fetchval("SELECT sla_lich_chinh_sach($1::text::jsonb, $2::text::jsonb)", env, gio)
        assert ra["tuan"] == [[540, 1080]] * 7
        ra = await conn.fetchval("SELECT sla_lich_chinh_sach($1::text::jsonb, $2::text::jsonb)", j, gio)
        assert ra["tuan"] == lich.json_sql()["tuan"], "đã có lịch chung thì giờ riêng thôi tác dụng"
        ra = await conn.fetchval(
            "SELECT sla_lich_chinh_sach($1::text::jsonb, '{\"bat_dau\": \"tám\"}'::jsonb)", env)
        assert ra == json.loads(env), "ô giờ riêng hỏng không làm hỏng việc tạo hội thoại"

    _chay(csdl_kiem_thu, ham)


# ====================================================================== 3. mục tiêu: chế độ, ngưỡng

def test_che_do_va_nguong_theo_muc_tieu(monkeypatch):
    from agent.config import settings
    from agent.core import lich_lam_viec
    from agent.omnichannel import sla, sla_muc_tieu
    from agent.omnichannel.sla_muc_tieu import DongMucTieu

    monkeypatch.setattr(settings, "sla_theo_gio_lam_viec", False)
    assert [sla_muc_tieu.che_do(m) for m in sla_muc_tieu.MUC_TIEU] == ["24_7"] * 3, "lui về .env"
    assert sla.ty_le_canh_bao("phan_hoi_sau_chuyen_giao") == 0.8
    monkeypatch.setattr(lich_lam_viec, "_lich_csdl", _lich_mau())
    monkeypatch.setitem(sla_muc_tieu._dong, "phan_hoi_sau_chuyen_giao", DongMucTieu("gio_lam_viec", 50))
    monkeypatch.setitem(sla_muc_tieu._dong, "giai_quyet", DongMucTieu("24_7", None))
    assert sla_muc_tieu.lich_cho("phan_hoi_dau") is None
    assert sla_muc_tieu.lich_cho("phan_hoi_sau_chuyen_giao") == _lich_mau()
    assert sla.ty_le_canh_bao("phan_hoi_sau_chuyen_giao") == 0.5
    assert sla.ty_le_canh_bao("giai_quyet") == 0.8, "ngưỡng riêng trống → ngưỡng chung"
    # Cùng hai mốc, mỗi mục tiêu đo theo đồng hồ của nó.
    a, b = _vn(2026, 11, 21, 11), _vn(2026, 11, 23, 9)
    assert sla.thoi_gian_sla_da_tieu_thu(a, b, "phan_hoi_sau_chuyen_giao") == timedelta(hours=2)
    assert sla.thoi_gian_sla_da_tieu_thu(a, b, "giai_quyet") == b - a
    dau, xong = sla_muc_tieu.tham_so_han()
    assert dau is None and xong is None
    # Lịch tắt = 24/7 cho cả mục tiêu chọn giờ làm việc.
    monkeypatch.setattr(lich_lam_viec, "_lich_csdl", lich_lam_viec.Lich(bat=False, tuan=((480, 1260),) * 7))
    assert sla_muc_tieu.lich_cho("phan_hoi_sau_chuyen_giao") is None


@pytest.mark.parametrize("sai", [
    [], [{"ma": "la", "che_do": "24_7"}], [{"ma": "giai_quyet", "che_do": "dem"}],
    [{"ma": "giai_quyet", "che_do": "24_7", "nguong_canh_bao": 99}],
    [{"ma": "giai_quyet", "che_do": "24_7", "nguong_canh_bao": "abc"}],
])
def test_chuan_hoa_muc_tieu_chan_luc_luu(sai):
    from agent.omnichannel import sla_muc_tieu

    with pytest.raises(ValueError):
        sla_muc_tieu.chuan_hoa(sai)


# ====================================================================== 4. xác nhận tự động

def test_moi_nguon_xac_nhan_tu_dong_xep_hang_vai_system():
    """
    Luật "xác nhận tự động không phải phản hồi" đi theo VAI của tin. Một
    nguồn đổi sang `agent` là thông báo AI / câu báo chuyển người lặng lẽ
    "đạt" hạn phản hồi đầu ở giây thứ hai.
    """
    from agent.omnichannel import giai_quyet, thong_bao_ai, tu_dong, xu_ly_tin_vao
    from agent.shipping import service

    for ham in (thong_bao_ai.gui_neu_chua, xu_ly_tin_vao._queue_handover_notice,
                tu_dong._gui_mau, giai_quyet._hoi_csat, giai_quyet.ghi_diem_neu_la_csat,
                service._bao_khach):
        src = inspect.getsource(ham)
        assert 'role="system"' in src and 'role="agent"' not in src, ham.__qualname__


def test_outbox_dung_luat_phan_hoi_that():
    from agent.omnichannel import outbox, phan_hoi_that

    assert phan_hoi_that.VAI_PHAN_HOI_THAT == {"agent", "staff"}
    assert phan_hoi_that.VAI_PHAN_HOI_SAU_CHUYEN_GIAO == {"staff"}
    assert not phan_hoi_that.la_phan_hoi_that("system")
    assert not phan_hoi_that.chot_chuyen_giao("agent")
    src = inspect.getsource(outbox.PostgresOutboxRepository._mark_sent_on_connection)
    assert "phan_hoi_that.la_phan_hoi_that(" in src and "phan_hoi_that.chot_chuyen_giao(" in src


async def _gui_xong(conn, tk, cid, vai, **cot) -> UUID:
    """Tin chiều ra đi qua đúng đường outbox `mark_sent` thật."""
    from agent.omnichannel.outbox import PostgresOutboxRepository

    mid = await _tin(conn, cid, vai, delivery_status="sending", **cot)
    job = await conn.fetchval(
        "INSERT INTO outbox_jobs (account_id, conversation_id, message_id, kind, "
        "idempotency_key, status) VALUES ($1,$2,$3,'text',$4,'processing') RETURNING id",
        tk, cid, mid, f"k-{mid}")
    async with conn.transaction():
        await PostgresOutboxRepository._mark_sent_on_connection(conn, job, {})
    return mid


def test_xac_nhan_tu_dong_khong_dat_phan_hoi_dau(csdl_kiem_thu):
    _schema(csdl_kiem_thu)

    async def ham(conn, _pool):
        tk = await _kenh(conn, "web-ack")
        cid = await _hoi_thoai(conn, tk, "ack", han_dau="now() + interval '10 minutes'")
        await _gui_xong(conn, tk, cid, "system", content="Dạ bạn đang trò chuyện với trợ lý AI…")
        c = await conn.fetchrow("SELECT first_responded_at FROM conversations WHERE id = $1", cid)
        assert c["first_responded_at"] is None, "thông báo tự động không phải phản hồi"
        assert await conn.fetchval("SELECT count(*) FROM sla_events WHERE conversation_id = $1 "
                                   "AND kind LIKE 'first_response_%'", cid) == 0
        await _gui_xong(conn, tk, cid, "agent", content="Dạ sản phẩm này còn hàng ạ")
        s = await conn.fetchrow("SELECT kind, detail FROM sla_events WHERE conversation_id = $1 "
                                "AND kind LIKE 'first_response_%'", cid)
        assert s["kind"] == "first_response_met" and s["detail"]["vai"] == "agent"

    _chay(csdl_kiem_thu, ham)


# ====================================================================== 5. chuyển giao

async def _dung_chuyen_giao(conn, ma: str, *, truoc: str = "25 minutes", phut: int | None = 30):
    await _nguoi(conn, NV, "nv")
    tk = await _kenh(conn, f"web-{ma}")
    await conn.execute(
        "INSERT INTO sla_policies (account_id, priority, first_response_minutes, "
        "resolution_minutes, handover_response_minutes) VALUES (NULL, 'normal', 30, 1440, $1) "
        "ON CONFLICT DO NOTHING", phut)
    cid = await _hoi_thoai(conn, tk, ma)
    await conn.execute("UPDATE conversations SET mode = 'human', status = 'escalated', "
                       "assigned_to = $2 WHERE id = $1", cid, NV)
    await conn.execute("INSERT INTO events (kind, ref_id, created_at) "
                       f"VALUES ('conversation.escalated', $1, now() - interval '{truoc}')", cid)
    return tk, cid


async def _lui_moc_migration(conn) -> None:
    """Chuyển giao trong test xảy ra 'trước' lúc 0062 chạy — lùi mốc như một CSDL đã chạy lâu."""
    await conn.execute("UPDATE schema_migrations SET applied_at = now() - interval '2 days' "
                       "WHERE version = '0062'")


def test_chuyen_giao_mo_luot_canh_bao_vi_pham_chuong_va_chot(csdl_kiem_thu):
    _schema(csdl_kiem_thu)
    from agent.omnichannel.sla import PostgresSlaRepository

    async def ham(conn, pool):
        await _lui_moc_migration(conn)
        tk, cid = await _dung_chuyen_giao(conn, "cg")
        repo = PostgresSlaRepository(lambda: pool)
        kq = await repo.mark_breaches()
        assert kq["chuyen_giao_mo"] == 1 and kq["chuyen_giao_canh_bao"] == 1, kq
        kq = await repo.mark_breaches()
        assert kq["chuyen_giao_mo"] == 0 and kq["chuyen_giao_canh_bao"] == 0, "mỗi lượt một lần"
        g = await conn.fetchrow("SELECT * FROM sla_chuyen_giao WHERE conversation_id = $1", cid)
        assert g["lan"] == 1 and g["ket_qua"] == "dang_cho"
        assert g["due_at"] - g["bat_dau"] == timedelta(minutes=30), "24/7 mặc định: lúc chuyển + 30'"
        assert g["detail"]["threshold_ratio"] == 0.8
        p = await conn.fetchval("SELECT payload FROM inbox_events "
                                "WHERE topic = 'sla.handover_response_warning'")
        assert p["conversation_id"] == str(cid) and p["lan"] == 1 and p["nguoi_phu_trach"] == str(NV)
        tb = await conn.fetch("SELECT loai, tieu_de FROM thong_bao WHERE nguoi_nhan_id = $1", NV)
        assert [(t["loai"], "chuyển giao" in t["tieu_de"]) for t in tb] == [("sla_sap_tre", True)]

        # Quá hạn: rút hạn về quá khứ (trigger cho rút ngắn) rồi quét.
        await conn.execute("UPDATE sla_chuyen_giao SET due_at = now() - interval '1 minute' "
                           "WHERE conversation_id = $1", cid)
        assert (await repo.mark_breaches())["chuyen_giao_tre"] == 1
        assert (await repo.mark_breaches())["chuyen_giao_tre"] == 0, "một vi phạm ghi một lần"
        assert await conn.fetchval("SELECT count(*) FROM thong_bao WHERE nguoi_nhan_id = $1 "
                                   "AND loai = 'sla_tre'", NV) == 1
        assert await conn.fetchval("SELECT count(*) FROM inbox_events "
                                   "WHERE topic = 'sla.handover_response_breached'") == 1

        # Đọc (hay lờ) thông báo KHÔNG xoá vi phạm; sửa tay cũng không.
        await conn.execute("UPDATE thong_bao SET da_doc_luc = now()")
        await conn.execute("UPDATE sla_chuyen_giao SET vi_pham_luc = NULL, ket_qua = 'dat', "
                           "due_at = now() + interval '1 day' WHERE conversation_id = $1", cid)
        g = await conn.fetchrow("SELECT * FROM sla_chuyen_giao WHERE conversation_id = $1", cid)
        assert g["vi_pham_luc"] is not None and g["ket_qua"] == "tre" and g["due_at"] < g["tao_luc"] + \
            timedelta(hours=1)

        # Câu báo chuyển người (system) và tin AI không chốt lượt; tin nhân viên chốt.
        await _gui_xong(conn, tk, cid, "system", content="Dạ em nhờ bạn chuyên môn hỗ trợ ạ")
        await _gui_xong(conn, tk, cid, "agent", content="x")
        assert await conn.fetchval("SELECT ket_thuc_luc FROM sla_chuyen_giao "
                                   "WHERE conversation_id = $1", cid) is None
        await _gui_xong(conn, tk, cid, "staff", content="Chào chị, em là Hoa", gui_boi=NV)
        g = await conn.fetchrow("SELECT * FROM sla_chuyen_giao WHERE conversation_id = $1", cid)
        assert (g["ket_qua"], g["ket_thuc_ly_do"], g["phan_hoi_boi"]) == ("tre", "phan_hoi", NV)

        # Chuyển giao LẦN HAI: lượt mới, hạn mới — không bị lượt một nuốt.
        await conn.execute("UPDATE conversations SET mode = 'auto', status = 'auto' WHERE id = $1", cid)
        await conn.execute("UPDATE conversations SET mode = 'human', status = 'escalated' WHERE id = $1", cid)
        await conn.execute("INSERT INTO events (kind, ref_id) VALUES ('conversation.escalated', $1)", cid)
        assert (await repo.mark_breaches())["chuyen_giao_mo"] == 1
        # Trả về AI trước hạn, chưa ai nhắn: lượt hai chốt "huy", không phải vi phạm.
        await conn.execute("UPDATE conversations SET mode = 'assist', status = 'assist' WHERE id = $1", cid)
        await repo.mark_breaches()
        ds = await conn.fetch("SELECT lan, ket_qua, ket_thuc_ly_do FROM sla_chuyen_giao "
                              "WHERE conversation_id = $1 ORDER BY lan", cid)
        assert [(r["lan"], r["ket_qua"], r["ket_thuc_ly_do"]) for r in ds] == [
            (1, "tre", "phan_hoi"), (2, "huy", "tra_ai")]

    _chay(csdl_kiem_thu, ham)


def test_chuyen_giao_truoc_migration_khong_mo_luot(csdl_kiem_thu):
    """Mở lượt cho cả hàng chờ cũ là một trận chuông 'đã trễ' cho chuyện tuần trước."""
    _schema(csdl_kiem_thu)
    from agent.omnichannel.sla import PostgresSlaRepository

    async def ham(conn, pool):
        _tk, cid = await _dung_chuyen_giao(conn, "cu", truoc="3 hours")
        assert (await PostgresSlaRepository(lambda: pool).mark_breaches())["chuyen_giao_mo"] == 0
        assert await conn.fetchval("SELECT count(*) FROM sla_chuyen_giao") == 0

    _chay(csdl_kiem_thu, ham)


def test_nhan_vien_nhan_truoc_khi_vong_quet_mo_luot_thi_dat(csdl_kiem_thu):
    _schema(csdl_kiem_thu)
    from agent.omnichannel.sla import PostgresSlaRepository

    async def ham(conn, pool):
        await _lui_moc_migration(conn)
        _tk, cid = await _dung_chuyen_giao(conn, "nhanh", truoc="5 minutes", phut=None)
        await _tin(conn, cid, "staff", gui_boi=NV)          # đã gửi, không qua outbox
        await PostgresSlaRepository(lambda: pool).mark_breaches()
        g = await conn.fetchrow("SELECT * FROM sla_chuyen_giao WHERE conversation_id = $1", cid)
        assert g["ket_qua"] == "khong_han" and g["phan_hoi_boi"] == NV, "chính sách không đặt phút"

    _chay(csdl_kiem_thu, ham)


def test_luu_chinh_sach_khong_gui_o_nao_thi_giu_o_ay(csdl_kiem_thu):
    """Form cũ không có ô chuyển giao, form mới không có ô giờ riêng — Lưu không được xoá chúng."""
    _schema(csdl_kiem_thu)
    from agent.api.routing_admin import PostgresRoutingAdminRepository

    async def ham(conn, pool):
        repo = PostgresRoutingAdminRepository(lambda: pool)
        chung = {"account_id": None, "priority": "normal", "first_response_minutes": 10,
                 "resolution_minutes": 100, "active": True}
        await repo.upsert_sla(actor_id=QT, **chung, business_hours={"bat_dau": 9, "ket_thuc": 18},
                              handover_response_minutes=20)
        await repo.upsert_sla(actor_id=QT, **chung, business_hours={},
                              handover_response_minutes=None,
                              da_gui=frozenset({"first_response_minutes", "resolution_minutes"}))
        r = await conn.fetchrow("SELECT * FROM sla_policies")
        assert r["handover_response_minutes"] == 20 and r["business_hours"] == {"bat_dau": 9, "ket_thuc": 18}
        await repo.upsert_sla(actor_id=QT, **chung, business_hours={}, handover_response_minutes=None,
                              da_gui=frozenset({"handover_response_minutes"}))
        r = await conn.fetchrow("SELECT * FROM sla_policies")
        assert r["handover_response_minutes"] is None, "gửi null tường minh = bỏ mục tiêu"
        assert r["business_hours"] == {"bat_dau": 9, "ket_thuc": 18}

    _chay(csdl_kiem_thu, ham)


# ====================================================================== API + hạn thật theo lịch

def _app_sla(url: str, nguoi: dict) -> FastAPI:
    from agent import db
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.api.sla_cau_hinh import router
    from agent.migrations.runner import apply_all

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[nguoi_da_dang_nhap] = lambda: nguoi

    @app.on_event("startup")
    async def _mo():
        db._pool = await asyncpg.create_pool(url, min_size=1, max_size=3, init=_codec)
        async with db._pool.acquire() as conn:
            await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
            await apply_all(conn)

    @app.on_event("shutdown")
    async def _dong():
        if db._pool is not None:
            await db._pool.close()
            db._pool = None

    return app


_TUAN = [{"mo": "08:00", "dong": "21:00"}] * 5 + [{"mo": "09:00", "dong": "12:00"}, {"nghi": True}]


def test_api_lich_va_muc_tieu_co_hieu_luc_o_moi_noi(csdl_kiem_thu, monkeypatch):
    from agent.config import settings
    from agent.core import gio_lam_viec, lich_lam_viec
    from agent.omnichannel import sla_gio, sla_muc_tieu

    monkeypatch.setattr(settings, "sla_theo_gio_lam_viec", False)
    qt = nguoi_thu("dinh_tuyen.doc", "dinh_tuyen.sua", "cau_hinh.doc", ten="qt")
    with TestClient(_app_sla(csdl_kiem_thu, qt)) as k:
        d = k.get("/api/sla/cau-hinh").json()
        assert d["lich"]["nguon"] == "env" and len(d["muc_tieu"]) == 3
        r = k.put("/api/sla/lich-lam-viec", json={"bat": True, "tuan": _TUAN,
                                                   "ngay_nghi": [{"ngay": "2026-11-26", "ten": "Lễ"}]})
        assert r.status_code == 200, r.text
        assert r.json()["lich"]["nguon"] == "csdl"
        # Câu báo ngoài giờ / quy tắc "ngoài giờ" đọc lịch vừa lưu.
        assert not gio_lam_viec.dang_trong_gio(_vn(2026, 11, 22, 10))
        assert not gio_lam_viec.dang_trong_gio(_vn(2026, 11, 26, 10))
        assert gio_lam_viec.dang_trong_gio(_vn(2026, 11, 27, 10))
        assert k.put("/api/sla/lich-lam-viec", json={"tuan": [{"mo": "9:00", "dong": "8:00"}] * 7}
                     ).status_code == 422
        r = k.put("/api/sla/muc-tieu", json={"muc_tieu": [
            {"ma": "phan_hoi_dau", "che_do": "gio_lam_viec", "nguong_canh_bao": 60},
            {"ma": "giai_quyet", "che_do": "24_7"}]})
        assert r.status_code == 200, r.text
        mt = {m["ma"]: m for m in r.json()["muc_tieu"]}
        assert mt["phan_hoi_dau"]["nguong_hieu_luc"] == 60 and mt["giai_quyet"]["nguong_hieu_luc"] == 80
        assert mt["phan_hoi_sau_chuyen_giao"]["nguon_che_do"] == "env"
        dau, xong = sla_gio.tham_so_han()
        assert json.loads(dau)["nghi"] == ["2026-11-26"] and xong is None

        async def han_that(conn, _pool):
            # Biểu thức THẬT mà ba chỗ đặt hạn dùng, với giờ riêng của chính sách
            # đã bị lịch chung thay thế.
            await conn.execute(
                "INSERT INTO sla_policies (priority, first_response_minutes, resolution_minutes, "
                "business_hours) VALUES ('normal', 45, 600, '{\"bat_dau\": 13, \"ket_thuc\": 14}')")
            r = await conn.fetchrow(
                f"SELECT now() AS t, {sla_gio.bieu_thuc_han('first_response_minutes', 1)} AS dau, "
                f"{sla_gio.bieu_thuc_han('resolution_minutes', 2)} AS xong "
                "FROM sla_policies policy LIMIT 1", dau, xong)
            assert r["dau"] == lich_lam_viec.han(r["t"], 45, lich_lam_viec.hien_hanh())
            assert r["xong"] == r["t"] + timedelta(minutes=600), "giải quyết chọn 24/7"
        _chay(csdl_kiem_thu, han_that)

        assert k.delete("/api/sla/lich-lam-viec").json()["lich"]["nguon"] == "env"
        assert lich_lam_viec.hien_hanh().nguon == "env"
        assert sla_muc_tieu.che_do("phan_hoi_dau") == "gio_lam_viec", "bỏ lịch không xoá mục tiêu"

    chi_xem = nguoi_thu("dinh_tuyen.doc", ten="xem")
    with TestClient(_app_sla(csdl_kiem_thu, chi_xem)) as k:
        assert k.get("/api/sla/cau-hinh").status_code == 200
        assert k.put("/api/sla/lich-lam-viec", json={"tuan": _TUAN}).status_code == 403
        assert k.put("/api/sla/muc-tieu", json={"muc_tieu": [
            {"ma": "giai_quyet", "che_do": "24_7"}]}).status_code == 403
        assert k.delete("/api/sla/lich-lam-viec").status_code == 403


# ====================================================================== 6. Phân tích

def test_phan_tich_muc_tieu_chuyen_giao_va_giai_quyet_ai_nhan_vien(csdl_kiem_thu):
    _schema(csdl_kiem_thu)
    from agent.api.phan_tich import tinh
    from agent.omnichannel.sla import PostgresSlaRepository
    from agent.omnichannel.sla_muc_tieu import MUC_TIEU

    async def ham(conn, pool):
        await _lui_moc_migration(conn)
        tk, cid = await _dung_chuyen_giao(conn, "pt", truoc="40 minutes")
        repo = PostgresSlaRepository(lambda: pool)
        await repo.mark_breaches()                               # mở lượt, đã quá 30' → trễ
        await _gui_xong(conn, tk, cid, "staff", gui_boi=NV)
        _tk2, cid2 = await _dung_chuyen_giao(conn, "pt2", truoc="2 minutes")
        await repo.mark_breaches()
        await _gui_xong(conn, tk, cid2, "staff", gui_boi=NV)     # trong hạn → đạt
        # Hai lượt giải quyết: một AI tự lo, một có nhân viên.
        ai = await _hoi_thoai(conn, tk, "ai-lo", tao="now() - interval '10 minutes'")
        for c in (ai, cid):
            await conn.execute("INSERT INTO events (kind, ref_id) VALUES ('conversation.resolved', $1)", c)
        hom_nay = datetime.now(VN).date()
        d = await tinh(hom_nay, hom_nay, xem_het=True, nguoi_id=QT)
        cg = d["sla"]["chuyen_giao"]
        assert (cg["dung_han"], cg["tre_han"], cg["ty_le_dung_han"]) == (1, 1, 0.5)
        assert cg["thoi_gian"]["so"] == 2 and cg["nhan_vien"][0]["id"] == str(NV)
        assert d["sla"]["vi_pham_tat_ca"] == d["sla"]["vi_pham"] + 1
        assert set(d["che_do_muc_tieu"]) == set(MUC_TIEU)
        vai = d["sla"]["thoi_gian_giai_quyet"]["theo_vai"]
        assert vai["agent"]["so"] == 1 and vai["staff"]["so"] == 1

    _chay(csdl_kiem_thu, ham)


# ====================================================================== giao diện

def test_giao_dien_sla_gan_tab_va_khong_trung_o_cau_hinh():
    js = (ROOT / "dashboard" / "src" / "26-sla.js").read_text(encoding="utf-8")
    assert 'window.GAN_TAB["cc-sla"]' in js
    assert 'data-api-cac-nhom="sla"' in js, "ngưỡng chung và khi trễ hiện trong tab SLA"
    assert "/sla/lich-lam-viec" in js and "/sla/muc-tieu" in js and "handover_response_minutes" in js
    assert len(js.splitlines()) <= 1000
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    # Hai ô cùng nhóm trong một trang: nút Lưu gom cả giá trị của ô bị ẩn.
    assert 'data-api-cac-nhom="sla"' not in html
    vong = (ROOT / "dashboard" / "src" / "10-vong-lam-moi.js").read_text(encoding="utf-8")
    assert vong.count("sla.handover_response_breached") == 2
    # Không thêm SLA thường trực vào khung hội thoại (phiếu việc 15.7).
    assert "chuyen_giao" not in (ROOT / "dashboard" / "src" / "03-hoi-thoai.js").read_text(encoding="utf-8")


def test_chuong_co_hai_loai_chuyen_giao_dung_loai_co_san():
    from agent.core import thong_bao_noi_bo

    for k in ("handover_response_warning", "handover_response_breached"):
        loai, _ = thong_bao_noi_bo._SLA[k]
        assert loai in thong_bao_noi_bo.LOAI
