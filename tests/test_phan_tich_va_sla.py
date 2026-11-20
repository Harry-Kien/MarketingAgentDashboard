"""
Màn Phân tích và nâng cấp SLA (rà soát 20.11.2026) — Postgres thật.

Canh năm ràng buộc, mỗi cái một kiểu hỏng im lặng:

  1. Đổi ưu tiên KHÔNG kéo dài được hạn SLA trong cùng chu kỳ — ở API và ở
     trigger CSDL (migration 0054). Hạ ưu tiên để "thêm giờ" là né vi phạm.
  2. Cảnh báo sớm HẠN GIẢI QUYẾT ở 50% khoảng, như cảnh báo phản hồi đầu.
  3. Trễ SLA sinh MỘT việc gấp (chống trùng theo hội thoại+chu kỳ+loại) và
     báo nhân viên; việc ấy không chặn nút "Đã giải quyết" và tự đóng theo.
  4. Số AI "tự lo" đếm theo SỰ KIỆN: duyệt nháp là có người can thiệp —
     con số cũ đếm `status = 'auto'` nên tô hồng đúng chỗ này.
  5. Mọi số của màn Phân tích tôn trọng phạm vi kênh như `/api/overview`.

Dữ liệu dựng tay, kết quả đúng tính được bằng tay.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import nguoi_thu

ROOT = Path(__file__).resolve().parent.parent
LUOC_DO = ROOT / "agent" / "schema.sql"
QT = UUID("00000000-0000-0000-0000-000000000001")   # id của nguoi_thu()
NV = UUID("00000000-0000-0000-0000-0000000000a1")


async def _codec(conn):
    await conn.set_type_codec("jsonb", encoder=json.dumps,
                              decoder=json.loads, schema="pg_catalog")


def _app(url: str, nguoi: dict) -> FastAPI:
    from agent import db
    from agent.api.phan_tich import router as r_pt
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.api.tong_quan import router as r_tq
    from agent.api.uu_tien import router as r_ut
    from agent.migrations.runner import apply_all

    app = FastAPI()
    for r in (r_pt, r_ut, r_tq):
        app.include_router(r)
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


def _schema(url: str) -> None:
    with TestClient(_app(url, nguoi_thu())):
        pass


def _chay(url: str, ham):
    """Chạy `ham(conn)` với `db._pool` trỏ vào CSDL kiểm thử, trong CÙNG vòng lặp."""
    from agent import db

    async def chay():
        pool = await asyncpg.create_pool(url, min_size=1, max_size=3, init=_codec)
        cu = db._pool
        db._pool = pool
        try:
            async with pool.acquire() as conn:
                return await ham(conn, pool)
        finally:
            db._pool = cu
            await pool.close()
    return asyncio.run(chay())


async def _nguoi(conn, uid: UUID, ten: str) -> None:
    await conn.execute(
        "INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, ho_ten) "
        "VALUES ($1,$2,'x',$3) ON CONFLICT DO NOTHING", uid, ten, ten.upper())


async def _kenh(conn, ma: str, ho_so: UUID | None = None) -> UUID:
    return await conn.fetchval(
        "INSERT INTO channel_accounts (channel, display_name, status, external_account_id, "
        "agent_ho_so_id) VALUES ('webchat',$1,'active',$1,$2) RETURNING id", ma, ho_so)


async def _hoi_thoai(conn, tk: UUID, ma: str, *, han_dau: str = "NULL", han_xong: str = "NULL",
                     tao: str = "now()", first_seen: str = "now()", priority: str = "normal",
                     state: str = "open") -> UUID:
    kh = await conn.fetchval(
        f"INSERT INTO contacts (display_name, first_seen) VALUES ($1, {first_seen}) RETURNING id", ma)
    dm = await conn.fetchval(
        "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
        "VALUES ($1,$2,$3) RETURNING id", kh, tk, ma)
    return await conn.fetchval(
        f"INSERT INTO conversations (account_id, channel, external_id, customer_ref, customer_name, "
        f"contact_id, contact_point_id, first_response_due_at, resolution_due_at, created_at, "
        f"priority, state) VALUES ($1,'webchat',$2,$2,$2,$3,$4,{han_dau},{han_xong},{tao},$5,$6) "
        f"RETURNING id", tk, ma, kh, dm, priority, state)


async def _tin(conn, cid: UUID, vai: str, **cot) -> UUID:
    cot = {"content": "x", "direction": "inbound" if vai == "customer" else "outbound",
           "delivery_status": "received" if vai == "customer" else "sent", **cot}
    ten = ", ".join(cot)
    so = ", ".join(f"${i}" for i in range(3, len(cot) + 3))
    return await conn.fetchval(
        f"INSERT INTO messages (conversation_id, role, {ten}) VALUES ($1, $2, {so}) RETURNING id",
        cid, vai, *cot.values())


async def _su_kien(conn, kind: str, cid: UUID, **detail) -> None:
    await conn.execute("INSERT INTO events (kind, ref_id, detail) VALUES ($1,$2,$3)",
                       kind, cid, detail)


# ============================================================ 1. trigger hạn SLA

def test_trigger_chi_cho_rut_ngan_han_con_o_tuong_lai(csdl_kiem_thu):
    """Kéo dài, xoá, hay lùi một hạn ĐÃ QUA đều bị đè về hạn cũ; rút ngắn hạn còn ở tương lai thì được."""
    _schema(csdl_kiem_thu)

    async def ham(conn, _pool):
        tk = await _kenh(conn, "web-trig")
        cid = await _hoi_thoai(conn, tk, "k1", han_dau="now() + interval '1 hour'",
                               han_xong="now() - interval '1 hour'")
        cu = await conn.fetchrow("SELECT first_response_due_at AS d, resolution_due_at AS x "
                                 "FROM conversations WHERE id = $1", cid)

        async def han():
            return await conn.fetchrow("SELECT first_response_due_at AS d, resolution_due_at AS x "
                                       "FROM conversations WHERE id = $1", cid)

        await conn.execute("UPDATE conversations SET first_response_due_at = first_response_due_at "
                           "+ interval '1 day' WHERE id = $1", cid)
        assert (await han())["d"] == cu["d"], "kéo dài hạn trong cùng chu kỳ phải bị chặn"
        await conn.execute("UPDATE conversations SET first_response_due_at = NULL WHERE id = $1", cid)
        assert (await han())["d"] == cu["d"], "xoá hạn phải bị chặn"
        # Hạn giải quyết đã QUA: lùi xa hơn là giấu dấu "Quá hạn" ở hộp thư.
        await conn.execute("UPDATE conversations SET resolution_due_at = resolution_due_at "
                           "- interval '1 day' WHERE id = $1", cid)
        assert (await han())["x"] == cu["x"], "lùi một hạn đã qua phải bị chặn"
        # Rút ngắn về một mốc trong quá khứ cũng không được.
        await conn.execute("UPDATE conversations SET first_response_due_at = now() - interval '1 minute' "
                           "WHERE id = $1", cid)
        assert (await han())["d"] == cu["d"]
        # Rút ngắn hợp lệ.
        await conn.execute("UPDATE conversations SET first_response_due_at = now() + interval '5 minutes' "
                           "WHERE id = $1", cid)
        assert (await han())["d"] < cu["d"], "rút ngắn hạn còn ở tương lai phải được phép"
        # Chu kỳ mới: đặt hạn bất kỳ.
        await conn.execute("UPDATE conversations SET sla_chu_ky = sla_chu_ky + 1, "
                           "first_response_due_at = now() + interval '9 hours' WHERE id = $1", cid)
        assert (await han())["d"] > cu["d"]

    _chay(csdl_kiem_thu, ham)


# ============================================================ 1b. API đổi ưu tiên

def test_han_sau_khi_doi_la_ham_thuan_dung_luat():
    from agent.api.uu_tien import han_sau_khi_doi

    bay_gio = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    cu, gan = bay_gio + timedelta(hours=1), bay_gio + timedelta(minutes=5)
    assert han_sau_khi_doi(nang=True, han_cu=cu, han_chinh_sach=gan, da_dat=False, bay_gio=bay_gio) == gan
    # Chính sách mới DÀI hơn hạn cũ: giữ hạn cũ.
    assert han_sau_khi_doi(nang=True, han_cu=gan, han_chinh_sach=cu, da_dat=False, bay_gio=bay_gio) == gan
    # Hạ ưu tiên, mục tiêu đã đạt, chưa có hạn, hạn đã qua: không đụng.
    assert han_sau_khi_doi(nang=False, han_cu=cu, han_chinh_sach=gan, da_dat=False, bay_gio=bay_gio) == cu
    assert han_sau_khi_doi(nang=True, han_cu=cu, han_chinh_sach=gan, da_dat=True, bay_gio=bay_gio) == cu
    assert han_sau_khi_doi(nang=True, han_cu=None, han_chinh_sach=gan, da_dat=False, bay_gio=bay_gio) is None
    qua = bay_gio - timedelta(minutes=1)
    assert han_sau_khi_doi(nang=True, han_cu=qua, han_chinh_sach=gan, da_dat=False, bay_gio=bay_gio) == qua


def _dung_doi_uu_tien(url: str) -> dict:
    async def ham(conn, _pool):
        await _nguoi(conn, QT, "qt")
        tk = await _kenh(conn, "web-ut")
        await conn.execute(
            "INSERT INTO sla_policies (account_id, priority, first_response_minutes, resolution_minutes) "
            "VALUES (NULL,'urgent',5,30), (NULL,'low',600,6000)")
        nang = await _hoi_thoai(conn, tk, "nang", han_dau="now() + interval '1 hour'",
                                han_xong="now() + interval '1 day'")
        ha = await _hoi_thoai(conn, tk, "ha", han_dau="now() + interval '10 minutes'",
                              han_xong="now() + interval '2 hours'")
        xong = await _hoi_thoai(conn, tk, "xong", state="resolved")
        await conn.execute("INSERT INTO sla_events (conversation_id, chu_ky, kind, due_at) "
                           "SELECT id, 1, 'first_response_warning', first_response_due_at "
                           "FROM conversations WHERE id = $1", nang)
        return {"tk": tk, "nang": nang, "ha": ha, "xong": xong}
    return _chay(url, ham)


def test_nang_uu_tien_rut_han_tu_bay_gio_ha_uu_tien_giu_han(csdl_kiem_thu):
    """Nâng: hạn = min(cũ, bây giờ + chính sách mới); hạ: hạn giữ nguyên. Cả hai ghi nhật ký có lý do."""
    nguoi = nguoi_thu("hoi_thoai.nhan", "hoi_thoai.xem_tat_ca", ten="qt")
    with TestClient(_app(csdl_kiem_thu, nguoi)) as k:
        d = _dung_doi_uu_tien(csdl_kiem_thu)
        r = k.put(f"/api/conversations/{d['nang']}/uu-tien",
                  json={"uu_tien": "urgent", "ly_do": "khách khiếu nại"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["uu_tien"] == "urgent"
        dau_cu, dau_moi = (datetime.fromisoformat(b[x]) for x in ("han_dau_cu", "han_dau_moi"))
        xong_cu, xong_moi = (datetime.fromisoformat(b[x]) for x in ("han_xong_cu", "han_xong_moi"))
        assert dau_moi < dau_cu and xong_moi < xong_cu
        bay_gio = datetime.now(timezone.utc)
        # Tính TỪ BÂY GIỜ, không lùi về lúc khách nhắn: 5 phút và 30 phút.
        assert timedelta(minutes=3) < dau_moi - bay_gio < timedelta(minutes=6)
        assert timedelta(minutes=28) < xong_moi - bay_gio < timedelta(minutes=31)

        r = k.put(f"/api/conversations/{d['ha']}/uu-tien",
                  json={"uu_tien": "low", "ly_do": "khách hẹn mai liên hệ lại"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["han_dau_moi"] == b["han_dau_cu"] and b["han_xong_moi"] == b["han_xong_cu"], \
            "hạ ưu tiên không được kéo dài hạn của chu kỳ đang chạy"

        # Lý do bắt buộc; đổi sang chính mức đang có; hội thoại đã giải quyết.
        assert k.put(f"/api/conversations/{d['nang']}/uu-tien",
                     json={"uu_tien": "high", "ly_do": ""}).status_code == 422
        assert k.put(f"/api/conversations/{d['nang']}/uu-tien",
                     json={"uu_tien": "urgent", "ly_do": "lại lần nữa"}).status_code == 422
        assert k.put(f"/api/conversations/{d['xong']}/uu-tien",
                     json={"uu_tien": "high", "ly_do": "thử"}).status_code == 409

    async def kiem(conn, _pool):
        ev = await conn.fetch("SELECT actor, ref_id, detail FROM events "
                              "WHERE kind = 'conversation.priority_changed' ORDER BY id")
        assert [(e["ref_id"], e["detail"]["den"]) for e in ev] == [(d["nang"], "urgent"), (d["ha"], "low")]
        assert ev[0]["actor"] == "qt" and ev[0]["detail"]["ly_do"] == "khách khiếu nại"
        assert await conn.fetchval("SELECT count(*) FROM inbox_events "
                                   "WHERE topic = 'conversation.priority_changed'") == 2
        # Cảnh báo 50% dời theo hạn mới, nếu không dấu "Sắp hết SLA" biến mất.
        w = await conn.fetchrow("SELECT s.due_at = c.first_response_due_at AS khop, s.detail "
                                "FROM sla_events s JOIN conversations c ON c.id = s.conversation_id "
                                "WHERE s.conversation_id = $1 AND s.kind = 'first_response_warning'",
                                d["nang"])
        assert w["khop"] and "han_truoc_khi_doi_uu_tien" in w["detail"]
    _chay(csdl_kiem_thu, kiem)


def test_doi_uu_tien_ngoai_kenh_la_404_va_can_quyen(csdl_kiem_thu):
    khong_kenh = nguoi_thu("hoi_thoai.nhan", ten="nv")
    with TestClient(_app(csdl_kiem_thu, khong_kenh)) as k:
        d = _dung_doi_uu_tien(csdl_kiem_thu)
        r = k.put(f"/api/conversations/{d['nang']}/uu-tien", json={"uu_tien": "high", "ly_do": "thử"})
        assert r.status_code == 404
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("hoi_thoai.doc"))) as k:
        r = k.put(f"/api/conversations/{d['nang']}/uu-tien", json={"uu_tien": "high", "ly_do": "thử"})
        assert r.status_code == 403


# ============================================================ 2. cảnh báo hạn giải quyết

def test_canh_bao_han_giai_quyet_o_nua_khoang(csdl_kiem_thu, monkeypatch):
    _schema(csdl_kiem_thu)
    from agent import canh_gac
    from agent.omnichannel.sla import PostgresSlaRepository

    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen", lambda *a: None)

    async def ham(conn, pool):
        tk = await _kenh(conn, "web-cb")
        # Bắt đầu 60' trước, hạn 30' nữa: đã qua 2/3 khoảng → cảnh báo.
        qua_nua = await _hoi_thoai(conn, tk, "qua", tao="now() - interval '60 minutes'",
                                   han_xong="now() + interval '30 minutes'")
        # Bắt đầu 10' trước, hạn 2 giờ nữa: chưa tới nửa → im.
        chua = await _hoi_thoai(conn, tk, "chua", tao="now() - interval '10 minutes'",
                                han_xong="now() + interval '2 hours'")
        repo = PostgresSlaRepository(lambda: pool)
        kq = await repo.mark_breaches()
        assert kq["resolution_warning"] == 1
        kq2 = await repo.mark_breaches()
        assert kq2["resolution_warning"] == 0, "mỗi chu kỳ chỉ cảnh báo một lần"
        ev = await conn.fetch("SELECT conversation_id FROM sla_events WHERE kind = 'resolution_warning'")
        assert [e["conversation_id"] for e in ev] == [qua_nua]
        assert chua not in [e["conversation_id"] for e in ev]
        assert await conn.fetchval("SELECT count(*) FROM inbox_events "
                                   "WHERE topic = 'sla.resolution_warning'") == 1

    _chay(csdl_kiem_thu, ham)


# ============================================================ 3. leo thang khi trễ

def test_tre_sla_sinh_mot_viec_gap_va_bao_nhan_vien(csdl_kiem_thu, monkeypatch):
    _schema(csdl_kiem_thu)
    from agent import canh_gac, cau_hinh_dong
    from agent.omnichannel import giai_quyet
    from agent.omnichannel.sla import PostgresSlaRepository

    bao: list[tuple] = []
    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen", lambda *a: bao.append(a))
    monkeypatch.setattr(cau_hinh_dong, "lay", lambda k: "bao" if k == "SLA_KHI_TRE" else "")

    async def ham(conn, pool):
        tk = await _kenh(conn, "web-tre")
        tre = await _hoi_thoai(conn, tk, "Lan", han_dau="now() - interval '5 minutes'")
        # Trả lời MUỘN (outbox ghi trễ kèm lúc phản hồi): khách đã được trả lời → không việc.
        muon = await _hoi_thoai(conn, tk, "Mai", han_dau="now() - interval '5 minutes'")
        await conn.execute("UPDATE conversations SET first_responded_at = now() WHERE id = $1", muon)
        await conn.execute("INSERT INTO sla_events (conversation_id, chu_ky, kind, due_at, detail) "
                           "VALUES ($1, 1, 'first_response_breached', now(), $2)",
                           muon, {"phan_hoi_luc": datetime.now(timezone.utc).isoformat(), "vai": "staff"})

        repo = PostgresSlaRepository(lambda: pool)
        assert (await repo.mark_breaches())["leo_thang"] == 1
        assert (await repo.mark_breaches())["leo_thang"] == 0, "lượt quét sau không đẻ việc thứ hai"
        viec = await conn.fetch("SELECT * FROM cong_viec")
        assert len(viec) == 1
        v = viec[0]
        assert v["conversation_id"] == tre and v["uu_tien"] == "gap" and v["nguon"] == "tu_dong"
        assert v["khoa_chong_trung"] == f"sla:{tre}:1:first_response_breached"
        assert len(bao) == 1 and "Lan" not in " ".join(bao[0]), "tên khách không đi ra ngoài"
        # Mặc định "bao": không đổi ưu tiên.
        assert await conn.fetchval("SELECT priority FROM conversations WHERE id = $1", tre) == "normal"

        # Việc trễ SLA KHÔNG chặn Resolve, và Resolve đóng nó theo.
        async with conn.transaction():
            assert await giai_quyet.kiem_tra_dieu_kien_resolve(conn, tre) is True
            await conn.execute("UPDATE conversations SET state = 'resolved', resolved_at = now() "
                               "WHERE id = $1", tre)
            await giai_quyet._sau_khi_giai_quyet(conn, tre, 1, None)
        assert await conn.fetchval("SELECT trang_thai FROM cong_viec WHERE id = $1", v["id"]) == "xong"

    _chay(csdl_kiem_thu, ham)


def test_tre_sla_nang_uu_tien_khi_bat_nhung_khong_rut_han(csdl_kiem_thu, monkeypatch):
    _schema(csdl_kiem_thu)
    from agent import canh_gac, cau_hinh_dong
    from agent.omnichannel.sla import PostgresSlaRepository

    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen", lambda *a: None)
    monkeypatch.setattr(cau_hinh_dong, "lay",
                        lambda k: "bao_va_nang_uu_tien" if k == "SLA_KHI_TRE" else "")

    async def ham(conn, pool):
        tk = await _kenh(conn, "web-nang")
        cid = await _hoi_thoai(conn, tk, "Hoa", han_dau="now() - interval '5 minutes'",
                               han_xong="now() + interval '1 day'")
        han_cu = await conn.fetchval("SELECT resolution_due_at FROM conversations WHERE id = $1", cid)
        await PostgresSlaRepository(lambda: pool).mark_breaches()
        c = await conn.fetchrow("SELECT priority, resolution_due_at FROM conversations WHERE id = $1", cid)
        assert c["priority"] == "high"
        assert c["resolution_due_at"] == han_cu, "máy tự nâng ưu tiên không được rút hạn"
        e = await conn.fetchrow("SELECT actor, detail FROM events WHERE kind = 'conversation.priority_changed'")
        assert e["actor"] == "sla" and e["detail"]["tu"] == "normal" and e["detail"]["den"] == "high"

    _chay(csdl_kiem_thu, ham)


def test_mo_lai_ghi_su_kien(csdl_kiem_thu):
    _schema(csdl_kiem_thu)
    from agent.omnichannel.giai_quyet import mo_lai_neu_da_giai_quyet

    async def ham(conn, _pool):
        tk = await _kenh(conn, "web-mo")
        cid = await _hoi_thoai(conn, tk, "Ngoc", state="resolved")
        assert await mo_lai_neu_da_giai_quyet(cid)
        assert await conn.fetchval("SELECT count(*) FROM events WHERE kind = 'conversation.reopened' "
                                   "AND ref_id = $1", cid) == 1

    _chay(csdl_kiem_thu, ham)


def test_outbox_ghi_ai_tra_loi_va_luc_tra_loi(csdl_kiem_thu):
    """Sự kiện phản hồi đầu mang `vai`, `phan_hoi_luc`; worker ghi trễ trước thì chỉ bổ sung, không đổi loại."""
    _schema(csdl_kiem_thu)
    from agent.omnichannel.outbox import PostgresOutboxRepository

    async def ham(conn, _pool):
        await _nguoi(conn, NV, "nv")
        tk = await _kenh(conn, "web-ob")
        cid = await _hoi_thoai(conn, tk, "Thu", han_dau="now() - interval '1 minute'")
        await conn.execute("INSERT INTO sla_events (conversation_id, chu_ky, kind, due_at) "
                           "VALUES ($1, 1, 'first_response_breached', now())", cid)
        mid = await _tin(conn, cid, "staff", gui_boi=NV, delivery_status="sending")
        job = await conn.fetchval(
            "INSERT INTO outbox_jobs (account_id, conversation_id, message_id, kind, "
            "idempotency_key, status) VALUES ($1,$2,$3,'text','k1','processing') RETURNING id",
            tk, cid, mid)
        async with conn.transaction():
            await PostgresOutboxRepository._mark_sent_on_connection(conn, job, {})
        s = await conn.fetchrow("SELECT kind, detail FROM sla_events WHERE conversation_id = $1 "
                                "AND kind LIKE 'first_response_%'", cid)
        assert s["kind"] == "first_response_breached"
        assert s["detail"]["vai"] == "staff" and s["detail"]["gui_boi"] == str(NV)
        assert "phan_hoi_luc" in s["detail"]

    _chay(csdl_kiem_thu, ham)


# ============================================================ 4–5. Phân tích và overview

def _dung_phan_tich(url: str) -> dict:
    """
    Kênh A (hồ sơ P), kênh B (Mặc định). Hôm nay:
      a1  AI trả lời, được giải quyết, không ai can thiệp       → tự giải quyết
      a2  AI trả lời, nhân viên NV nhắn thêm                    → cần người
      a3  AI soạn nháp, người DUYỆT (status vẫn lật thành auto)  → cần người
      b1  AI trả lời rồi tự chuyển người                        → cần người, AI tự chuyển
    Khách: a1 thấy lần đầu 30 ngày trước (quay lại), còn lại mới.
    SLA: a1 AI phản hồi đầu sau 60s đúng hạn; a2 NV phản hồi đầu sau 600s, trễ.
    """
    async def ham(conn, _pool):
        await _nguoi(conn, QT, "qt")
        await _nguoi(conn, NV, "nv")
        p = await conn.fetchval("INSERT INTO agent_ho_so (ten) VALUES ('Bán hàng') RETURNING id")
        a = await _kenh(conn, "web-a", p)
        b = await _kenh(conn, "web-b")
        await conn.execute("INSERT INTO account_memberships (account_id, user_id) VALUES ($1,$2)", a, NV)
        t0 = datetime.now(timezone.utc) - timedelta(minutes=30)
        a1 = await _hoi_thoai(conn, a, "a1", first_seen="now() - interval '30 days'",
                              han_dau="now() + interval '1 hour'")
        a2 = await _hoi_thoai(conn, a, "a2", han_dau="now() - interval '1 minute'")
        a3 = await _hoi_thoai(conn, a, "a3")
        b1 = await _hoi_thoai(conn, b, "b1")
        for cid in (a1, a2, a3, b1):
            await _tin(conn, cid, "customer")
        await _tin(conn, a1, "agent", model="m", confidence=0.9, grounded=True, cost_usd=0.01)
        await _tin(conn, a2, "agent", model="m", confidence=0.5, grounded=False, cost_usd=0.02)
        await _tin(conn, a2, "staff", gui_boi=NV)
        await _tin(conn, a3, "agent", model="m", confidence=0.7, grounded=True,
                   duyet_boi=QT, duyet_luc=datetime.now(timezone.utc))
        await _tin(conn, b1, "agent", model="m", confidence=0.3, grounded=False)
        await conn.execute("UPDATE conversations SET status = 'auto' WHERE id = ANY($1::uuid[])",
                           [a1, a2, a3])
        await conn.execute("UPDATE conversations SET status = 'escalated', mode = 'human' "
                           "WHERE id = $1", b1)
        await _su_kien(conn, "conversation.resolved", a1)
        await _su_kien(conn, "conversation.escalated", b1)
        for cid, giay, vai, kind, nv in ((a1, 60, "agent", "first_response_met", None),
                                         (a2, 600, "staff", "first_response_breached", str(NV))):
            await conn.execute("UPDATE conversations SET created_at = $2 WHERE id = $1", cid, t0)
            await conn.execute("INSERT INTO sla_events (conversation_id, chu_ky, kind, due_at, "
                               "created_at) VALUES ($1, 1, 'started', now(), $2)", cid, t0)
            await conn.execute(
                "INSERT INTO sla_events (conversation_id, chu_ky, kind, due_at, detail) "
                "VALUES ($1, 1, $2, now(), $3)", cid, kind,
                {"phan_hoi_luc": (t0 + timedelta(seconds=giay)).isoformat(), "vai": vai,
                 "gui_boi": nv, "ho_so": str(p) if vai == "agent" else None})
        return {"p": str(p), "a": str(a), "b": str(b)}
    return _chay(url, ham)


def test_phan_tich_ai_theo_ho_so_dem_theo_su_kien(csdl_kiem_thu):
    nguoi = nguoi_thu("bao_cao.doc", "hoi_thoai.xem_tat_ca", "hoi_thoai.doc")
    with TestClient(_app(csdl_kiem_thu, nguoi)) as k:
        d = _dung_phan_tich(csdl_kiem_thu)
        r = k.get("/api/phan-tich")
        assert r.status_code == 200, r.text
        o = r.json()
        ai = {x["ho_so"]: x for x in o["ai"]}
        p = ai[d["p"]]
        assert p["ten"] == "Bán hàng", "hồ sơ phải được chụp lúc ghi tin (trigger 0054)"
        assert (p["hoi_thoai"], p["tu_giai_quyet"], p["can_nguoi"], p["dang_do"]) == (3, 1, 2, 0)
        assert p["ty_le_thanh_cong"] == round(1 / 3, 4)
        assert p["tin_cay_tb"] == 0.7 and p["ty_le_co_can_cu"] == round(2 / 3, 4)
        md = ai["mac_dinh"]
        assert (md["hoi_thoai"], md["can_nguoi"], md["ai_tu_chuyen"]) == (1, 1, 1)

        h = o["hoi_thoai"]
        assert (h["moi"], h["giai_quyet"], h["chuyen_nguoi"], h["dang_mo"]) == (4, 1, 1, 4)
        assert o["khach"] == {"tong": 4, "moi": 3, "quay_lai": 1}

        ph = o["sla"]["phan_hoi_dau"]
        assert ph["theo_vai"]["agent"]["so"] == 1 and ph["theo_vai"]["agent"]["tb_giay"] == 60.0
        assert ph["theo_vai"]["staff"]["tre_han"] == 1 and ph["theo_vai"]["staff"]["trung_vi_giay"] == 600.0
        assert [n["ten"] for n in ph["nhan_vien"]] == ["NV"]
        assert o["sla"]["qua_han_dau"] == 1          # a2: chưa phản hồi trên cột, đã quá hạn

        tin = {(t["kenh"], t["vai"]): t for t in o["tin_nhan"]}
        assert tin[("webchat", "customer")]["nhan"] == 4
        assert tin[("webchat", "agent")]["gui"] == 4

        # Lọc theo hồ sơ và theo tài khoản kênh.
        o = k.get(f"/api/phan-tich?ho_so={d['p']}").json()
        assert [x["ho_so"] for x in o["ai"]] == [d["p"]] and o["hoi_thoai"]["moi"] == 3
        o = k.get(f"/api/phan-tich?account_id={d['b']}").json()
        assert [x["ho_so"] for x in o["ai"]] == ["mac_dinh"]
        o = k.get(f"/api/phan-tich?nhan_vien={NV}").json()
        assert o["hoi_thoai"]["moi"] == 1 and [n["ten_dang_nhap"] for n in o["nhan_vien"]] == ["nv"]
        assert k.get("/api/phan-tich?ho_so=bay").status_code == 422

        # Ô "AI tự lo" của overview cùng định nghĩa: duyệt nháp KHÔNG phải tự lo.
        c = k.get("/api/overview").json()["conversations"]
        assert c["handled"] == 3, "ảnh chụp status=auto vẫn đếm a3 — đúng lỗi con số cũ"
        assert (c["ai"], c["ai_tu_lo"], c["containment"]) == (4, 1, 0.25)


def test_phan_tich_chi_thay_kenh_duoc_giao(csdl_kiem_thu):
    """Nhân viên chỉ thuộc kênh A: không thấy hội thoại, tin, khách hay hồ sơ của kênh B."""
    nv = nguoi_thu("bao_cao.doc", id=str(NV), ten="nv")
    with TestClient(_app(csdl_kiem_thu, nv)) as k:
        d = _dung_phan_tich(csdl_kiem_thu)
        o = k.get("/api/phan-tich").json()
        assert o["hoi_thoai"]["moi"] == 3
        assert "mac_dinh" not in {x["ho_so"] for x in o["ai"]}
        assert o["khach"]["tong"] == 3
        # Lọc thẳng vào kênh không được giao: rỗng, không lộ.
        o = k.get(f"/api/phan-tich?account_id={d['b']}").json()
        assert o["hoi_thoai"]["moi"] == 0 and o["ai"] == []
        bl = k.get("/api/phan-tich/bo-loc").json()
        assert [t["id"] for t in bl["tai_khoan"]] == [d["a"]]
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("hoi_thoai.doc"))) as k:
        assert k.get("/api/phan-tich").status_code == 403


# ============================================================ cấu hình, chính sách, giao diện

def test_chinh_sach_sla_kiem_gio_rieng():
    from pydantic import ValidationError

    from agent.api.routing_admin import SlaPolicyIn

    co_ban = {"first_response_minutes": 5, "resolution_minutes": 60}
    assert SlaPolicyIn(**co_ban).business_hours == {}
    assert SlaPolicyIn(**co_ban, business_hours={"bat_dau": "9", "ket_thuc": 18}).business_hours \
        == {"bat_dau": 9, "ket_thuc": 18}
    for sai in ({"bat_dau": 9}, {"bat_dau": 18, "ket_thuc": 9}, {"bat_dau": 9, "ket_thuc": 25},
                {"bat_dau": None, "ket_thuc": 9}, {"mo": 8, "dong": 21}):
        with pytest.raises(ValidationError):
            SlaPolicyIn(**co_ban, business_hours=sai)


def test_sla_khi_tre_mac_dinh_chi_bao():
    from agent import cau_hinh_dong
    from agent.config import settings

    assert settings.sla_khi_tre == "bao"
    assert cau_hinh_dong.DANH_MUC["SLA_KHI_TRE"].chon == ("bao", "bao_va_nang_uu_tien")
    with pytest.raises(cau_hinh_dong.KhoaKhongHopLe):
        cau_hinh_dong.kiem_gia_tri("SLA_KHI_TRE", "tat")


def test_dashboard_co_man_phan_tich_doi_uu_tien_va_nghe_moi_su_kien_sla():
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    sla_py = (ROOT / "agent" / "omnichannel" / "sla.py").read_text(encoding="utf-8")
    # Mọi topic SLA máy chủ phát phải có người nghe.
    import re
    for topic in set(re.findall(r'"(sla\.[a-z_]+)"', sla_py)):
        assert topic in js, f"dashboard không nghe {topic}"
    assert 'data-view="phantich"' in html and "loadPhanTich" in js and "/phan-tich" in js
    assert "data-doi-uu-tien" in js and "/uu-tien" in js
    assert 'name="bat_dau"' in html and 'name="ket_thuc"' in html
    assert "business_hours: {}," not in js, "form SLA còn gửi cứng giờ rỗng"
