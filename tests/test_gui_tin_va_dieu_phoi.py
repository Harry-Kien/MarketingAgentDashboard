"""
Gửi tin, nhân viên và điều phối — mười lỗi rà soát 16.11.2026.

Phần lớn là hỏng IM LẶNG: việc tự sinh không đóng nên lần chuyển người sau
không báo ai; webhook báo động trả 4xx mà vẫn coi là đã gửi; tin nhân viên
chết không gửi lại được; điểm CSAT nhận nhầm số trả lời câu khác. Phần đụng
CSDL chạy trên `app_that` — app đầy đủ, Postgres thật.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from conftest import _quan_tri  # noqa: E402
from tests.test_nghiem_thu_saas import (  # noqa: E402
    Nguoi, _kenh_webchat, _khach_nhan, _nhan_vien_moi, _quan_tri_vao, _sql,
    _them_thanh_vien,
)


# ------------------------------------------------------------------ helpers

def _mot(app, sql: str, *args):
    from agent import db

    async def doc():
        return await db.fetchrow(sql, *args)
    return _sql(app, doc)


def _nhieu(app, sql: str, *args):
    from agent import db

    async def doc():
        return await db.fetch(sql, *args)
    return _sql(app, doc)


def _khach(app, tk: str, ten: str = "Chị Hoa"):
    """
    MỘT khách web giữ nguyên phiên qua nhiều tin — cùng một hội thoại.
    `_khach_nhan` mở phiên mới mỗi lần, tức mỗi tin là một khách khác.
    """
    from conftest import GOC_WEB

    app.cookies.clear()
    ve = app.post(f"/webchat/{tk}/session", json={},
                  headers={"Origin": GOC_WEB}).json()["token"]

    def gui(text: str) -> None:
        app.cookies.clear()
        r = app.post(f"/webchat/{tk}/messages",
                     json={"client_message_id": str(uuid4()), "text": text,
                           "visitor_name": ten},
                     headers={"Origin": GOC_WEB, "Authorization": f"Bearer {ve}"})
        assert r.status_code == 202, r.text
    return gui


def _hoi_thoai_cua(app, tk: str) -> str:
    return str(_mot(app, "SELECT id FROM conversations WHERE account_id = $1::uuid "
                         "ORDER BY created_at DESC LIMIT 1", tk)["id"])


def _phien_ban(app, cid: str) -> int:
    return int(_mot(app, "SELECT version FROM conversations WHERE id = $1::uuid", cid)["version"])


def _ghi_bao(monkeypatch) -> list[str]:
    """Bắt mọi lần báo nhân viên — đường `cong_viec._bao_viec_moi_cho_nhan_vien`."""
    from agent import canh_gac

    bao: list[str] = []
    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen",
                        lambda tieu_de, chi_tiet: bao.append(tieu_de))
    return bao


def _quan_tri_co_id(app, ten: str = "sep") -> tuple[str, Nguoi]:
    uid, token = _sql(app, _quan_tri, ten)
    return str(uid), Nguoi(app, token)


# ------------------------------------------------------------------ 1. việc tự sinh tự đóng

def test_giai_quyet_dong_viec_tu_sinh_nen_lan_chuyen_nguoi_sau_co_viec_moi_va_co_bao(
        app_that, monkeypatch):
    """
    Trước bản vá: việc "Khách cần người trả lời" mở mãi sau khi giải quyết.
    Chốt một-việc-mỗi-hội-thoại nuốt lần chuyển người SAU — không việc mới,
    không báo ai, khách chờ.
    """
    bao = _ghi_bao(monkeypatch)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)                       # agent TẮT → mọi tin chuyển người
    gui = _khach(app_that, tk)
    gui("cần tư vấn")
    cid = _hoi_thoai_cua(app_that, tk)
    assert len(bao) == 1

    r = qt.post(f"/api/inbox/conversations/{cid}/giai-quyet")
    assert r.status_code == 200, r.text
    viec = _nhieu(app_that, "SELECT trang_thai, xong_luc FROM cong_viec "
                            "WHERE conversation_id = $1::uuid", cid)
    assert [v["trang_thai"] for v in viec] == ["xong"] and viec[0]["xong_luc"]

    gui("cho em hỏi thêm")
    dem = _mot(app_that, "SELECT count(*) FILTER (WHERE trang_thai = 'moi') mo, "
                         "count(*) tat_ca FROM cong_viec WHERE conversation_id = $1::uuid", cid)
    assert dem["tat_ca"] == 2 and dem["mo"] == 1, "lần chuyển người sau phải có việc mới"
    assert len(bao) == 2, "lần chuyển người sau phải báo nhân viên"


def test_ket_thuc_tiep_quan_dong_viec_tu_sinh(app_that, monkeypatch):
    bao = _ghi_bao(monkeypatch)
    uid, qt = _quan_tri_co_id(app_that)
    tk = _kenh_webchat(qt)
    _them_thanh_vien(app_that, tk, uid, "manager")
    gui = _khach(app_that, tk)
    gui("cần tư vấn")
    cid = _hoi_thoai_cua(app_that, tk)

    r = qt.post(f"/api/inbox/conversations/{cid}/takeover",
                json={"expected_version": _phien_ban(app_that, cid), "reason": "nhận khách"})
    assert r.status_code == 200, r.text
    r = qt.post(f"/api/inbox/conversations/{cid}/release",
                json={"expected_version": r.json()["version"], "reason": "đã xử lý xong"})
    assert r.status_code == 200, r.text
    assert _mot(app_that, "SELECT trang_thai FROM cong_viec WHERE conversation_id = $1::uuid",
                cid)["trang_thai"] == "xong"

    # Khách nhắn tiếp, agent vẫn tắt → chuyển người lại: việc MỚI và báo MỚI.
    gui("alo shop")
    assert _mot(app_that, "SELECT count(*) n FROM cong_viec WHERE conversation_id = $1::uuid "
                          "AND trang_thai = 'moi'", cid)["n"] == 1
    assert len(bao) == 2


def test_viec_nguoi_giao_tay_khong_bi_dong_khi_giai_quyet(app_that):
    """
    Chỉ việc nguon='agent' đóng theo hội thoại — "gọi lại chị Hoa" vẫn phải làm.

    Từ khi ghép Resolve Guard (DEV-04, Release 1), việc người giao tay còn mở
    thì CHẶN giải quyết (409 kèm danh sách việc) thay vì để hội thoại đóng với
    việc treo. Bất biến cần canh vẫn thế: việc ấy KHÔNG bị đóng hộ.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Hoa", "cần tư vấn")
    cid = _hoi_thoai_cua(app_that, tk)
    r = qt.post("/api/cong-viec", json={"tieu_de": "Gọi lại chị Hoa", "conversation_id": cid})
    assert r.status_code == 201
    chan = qt.post(f"/api/inbox/conversations/{cid}/giai-quyet")
    assert chan.status_code == 409
    assert [t["id"] for t in chan.json()["detail"]["pending_tasks"]] == [r.json()["id"]]
    assert _mot(app_that, "SELECT trang_thai FROM cong_viec WHERE id = $1::uuid",
                r.json()["id"])["trang_thai"] == "moi"


# ------------------------------------------------------------------ 2. báo động không nuốt 4xx

def test_bao_dong_webhook_404_bi_ghi_la_loi_va_khong_lo_token(monkeypatch):
    import httpx

    from agent import canh_gac
    from agent.config import settings

    nhat_ky: list[dict] = []

    async def ghi(kind, **kw):
        nhat_ky.append({"kind": kind, **kw})
    monkeypatch.setattr(canh_gac.db, "log_event", ghi)

    class Gia:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json):
            return httpx.Response(404, request=httpx.Request("POST", url))
    monkeypatch.setattr(canh_gac.httpx, "AsyncClient", Gia)
    monkeypatch.setattr(settings, "canh_gac_webhook",
                        "https://api.telegram.org/botBIMAT123/sendMessage")

    asyncio.run(canh_gac.bao_dong("Outbox chết", tieu_de="Hỏng"))   # không được ném

    loi = [n for n in nhat_ky if n["kind"] == "canh_gac.loi_gui"]
    assert loi, "webhook trả 404 mà không ghi lỗi gửi = báo động mất im lặng"
    assert loi[-1]["ma_http"] == 404 and loi[-1]["loi"] == "HTTPStatusError"
    assert "BIMAT123" not in repr(nhat_ky), "URL chứa token bot không được vào nhật ký"


# ------------------------------------------------------------------ 3. ghi trạng thái cuối có điều kiện

def _kenh_agent_bat(app, monkeypatch) -> tuple[Nguoi, str]:
    from agent import runtime

    monkeypatch.setitem(runtime.STATE, "mode", "auto")
    qt = _quan_tri_vao(app)
    return qt, _kenh_webchat(qt, agent_bat=True)


def test_nhan_vien_tiep_quan_truoc_luc_xep_hang_thi_khong_bi_ghi_de_assist(app_that, monkeypatch):
    """
    Cửa sổ giữa bước kiểm lỗi thời và lúc xếp hàng: `OutboundBlocked` trước
    đây bị `except Exception` nuốt, rơi xuống lưu nháp rồi ghi `mode='assist'`
    ĐÈ lên lựa chọn tiếp quản của nhân viên.
    """
    from agent import db
    from agent.core import agent as brain
    from agent.omnichannel import xu_ly_tin_vao

    async def tra_loi(**kw):
        return brain.Reply(text="Dạ kem này giá 250.000đ ạ", cost_usd=0.002)
    monkeypatch.setattr(brain, "respond", tra_loi)

    async def tiep_quan_dung_luc(cid, message_id):
        await db.execute("UPDATE conversations SET mode = 'human', status = 'escalated', "
                         "version = version + 1 WHERE id = $1", cid)
        return None
    monkeypatch.setattr(xu_ly_tin_vao, "ly_do_loi_thoi", tiep_quan_dung_luc)

    _, tk = _kenh_agent_bat(app_that, monkeypatch)
    _khach_nhan(app_that, tk, "Chị Mai", "Kem chống nắng giá bao nhiêu?")
    cid = _hoi_thoai_cua(app_that, tk)

    hk = _mot(app_that, "SELECT mode, status, cost_usd FROM conversations WHERE id = $1::uuid", cid)
    assert hk["mode"] == "human" and hk["status"] == "escalated"
    assert float(hk["cost_usd"]) >= 0.002, "chi phí đã tốn vẫn phải ghi"
    assert _mot(app_that, "SELECT count(*) n FROM messages WHERE conversation_id = $1::uuid "
                          "AND content LIKE '%250.000%'", cid)["n"] == 0
    su = _mot(app_that, "SELECT detail FROM events WHERE kind = 'agent.superseded' "
                        "AND ref_id = $1::uuid", cid)
    assert su and "xếp hàng" in str(su["detail"])


def test_giai_quyet_trong_luc_ai_soan_cau_chuyen_nguoi_khong_ra_trang_thai_lai(
        app_that, monkeypatch):
    """
    Nhân viên bấm Giải quyết trong lúc AI soạn một câu xin chuyển người.
    Trước bản vá: `state='resolved'` + `status='escalated'` — kẹt, tin sau
    không mở lại hội thoại.
    """
    from agent.core import agent as brain
    from agent.omnichannel import giai_quyet

    async def tra_loi(*, conversation_id, **kw):
        await giai_quyet.giai_quyet(conversation_id, None)
        return brain.Reply(text="...", escalate=True, escalate_reason="khách đang mang thai")
    monkeypatch.setattr(brain, "respond", tra_loi)

    _, tk = _kenh_agent_bat(app_that, monkeypatch)
    _khach_nhan(app_that, tk, "Chị Mai", "em đang có bầu dùng kem này được không")
    cid = _hoi_thoai_cua(app_that, tk)
    hk = _mot(app_that, "SELECT state, status, mode FROM conversations WHERE id = $1::uuid", cid)
    assert (hk["state"], hk["status"]) == ("resolved", "closed")
    assert hk["mode"] != "human"


def test_hoi_thoai_ket_resolved_escalated_van_mo_lai_khi_khach_nhan(app_that):
    """Dữ liệu kẹt từ trước bản vá: mở lại phải xét `state`, không chỉ `status`."""
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    gui = _khach(app_that, tk)
    gui("alo")
    cid = _hoi_thoai_cua(app_that, tk)
    _mot(app_that, "UPDATE conversations SET state = 'resolved', status = 'escalated', "
                   "mode = 'human' WHERE id = $1::uuid RETURNING 1", cid)

    gui("shop ơi")
    assert _mot(app_that, "SELECT state FROM conversations WHERE id = $1::uuid",
                cid)["state"] == "open"


def test_standby_khong_ghi_escalated_len_hoi_thoai_da_giai_quyet():
    import inspect

    from agent.omnichannel import xu_ly_tin_vao

    src = inspect.getsource(xu_ly_tin_vao.handle_inbound)
    nhanh = src[src.index('get("standby")'):src.index('get("loai") == "binh_luan"')]
    assert "state NOT IN ('resolved', 'closed')" in nhanh
    cuoi = src[src.index("SET cost_usd = cost_usd + $2,"):]
    assert "mode <> 'human' AND state NOT IN ('resolved', 'closed')" in cuoi


# ------------------------------------------------------------------ 4. đổi chế độ theo kênh

def test_doi_che_do_ngoai_kenh_bi_404_ca_route_lan_service(app_that):
    from agent.omnichannel.routing import (
        ConversationNotFound, ConversationRoutingService, PostgresRoutingRepository,
    )

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _khach_nhan(app_that, tk, "Chị Hoa", "alo")
    cid = _hoi_thoai_cua(app_that, tk)
    _mot(app_that, "UPDATE conversations SET mode = 'assist', status = 'assist' "
                   "WHERE id = $1::uuid RETURNING 1", cid)

    than = {"che_do": "auto", "expected_version": _phien_ban(app_that, cid),
            "reason": "trả cho agent"}
    r = lan.post(f"/api/inbox/conversations/{cid}/che-do", json=than)
    assert r.status_code == 404, r.text
    assert _mot(app_that, "SELECT mode FROM conversations WHERE id = $1::uuid",
                cid)["mode"] == "assist"

    async def qua_service():
        await ConversationRoutingService(PostgresRoutingRepository()).dat_che_do(
            conversation_id=UUID(cid), actor_id=UUID(lan_id), che_do="auto",
            expected_version=than["expected_version"], reason="trả cho agent",
            actor_is_admin=False)
    with pytest.raises(ConversationNotFound):
        _sql(app_that, qua_service)

    _them_thanh_vien(app_that, tk, lan_id)
    r = lan.post(f"/api/inbox/conversations/{cid}/che-do", json=than)
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "auto"


# ------------------------------------------------------------------ 5. công việc theo kênh

def test_cong_viec_kenh_khac_khong_thay_khong_sua_duoc(app_that):
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _khach_nhan(app_that, tk, "Chị Hoa", "em đang mang thai")
    vid = qt.get("/api/cong-viec").json()["cong_viec"][0]["id"]

    assert lan.get("/api/cong-viec").json()["cong_viec"] == [], (
        "nhân viên kênh khác không được thấy tên khách và lý do chuyển người")
    assert lan.put(f"/api/cong-viec/{vid}", json={"nguoi_nhan": lan_id}).status_code == 404

    _them_thanh_vien(app_that, tk, lan_id)
    assert [v["id"] for v in lan.get("/api/cong-viec").json()["cong_viec"]] == [vid]
    assert lan.put(f"/api/cong-viec/{vid}", json={"nguoi_nhan": lan_id}).status_code == 200


def test_pham_vi_cong_viec_xet_thanh_vien_kenh_va_xoa_cung_loc():
    import inspect

    from agent.api import cong_viec as api
    from agent.core import cong_viec as cv

    nv = {"id": "11111111-1111-1111-1111-111111111111", "quyen": frozenset({"cong_viec.doc"})}
    sql, _ = cv.dieu_kien_pham_vi(nguoi=nv, so_tham_so=0)
    assert "account_memberships" in sql
    sql, _ = cv.dieu_kien_pham_vi(nguoi={**nv, "quyen": frozenset(
        {"cong_viec.doc", "hoi_thoai.xem_tat_ca"})}, so_tham_so=0)
    assert "account_memberships" not in sql, "người thấy mọi kênh không bị lọc kênh"
    assert "dieu_kien_pham_vi" in inspect.getsource(api.xoa)
    assert "dieu_kien_pham_vi" in inspect.getsource(api.sua)


# ------------------------------------------------------------------ 6. gửi lại tin nhân viên chết

def _job_chet(app, tk: str, cid: str, vai: str) -> str:
    from agent import db

    async def gieo():
        m = await db.fetchrow(
            "INSERT INTO messages (conversation_id, role, content, delivered, direction, "
            "delivery_status) VALUES ($1::uuid, $2, 'Dạ shop gửi chị ạ', false, 'outbound', "
            "'dead') RETURNING id", cid, vai)
        j = await db.fetchrow(
            "INSERT INTO outbox_jobs (account_id, conversation_id, message_id, kind, "
            " idempotency_key, status, attempts, max_attempts, payload) "
            "VALUES ($1::uuid, $2::uuid, $3, 'send_text', $4, 'dead', 8, 8, $5) RETURNING id",
            tk, cid, m["id"], str(uuid4()), {"conversation_ref": "x", "text": "y"})
        return str(j["id"])
    return _sql(app, gieo)


def test_gui_lai_tin_nhan_vien_chet_khi_dang_tiep_quan(app_that):
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Hoa", "alo")      # agent tắt → mode human
    cid = _hoi_thoai_cua(app_that, tk)
    assert _mot(app_that, "SELECT mode FROM conversations WHERE id = $1::uuid",
                cid)["mode"] == "human"

    jid_nv = _job_chet(app_that, tk, cid, "staff")
    r = qt.post(f"/api/outbox/jobs/{jid_nv}/retry")
    assert r.status_code == 200, r.text

    jid_ai = _job_chet(app_that, tk, cid, "agent")
    assert qt.post(f"/api/outbox/jobs/{jid_ai}/retry").status_code == 409


def test_danh_sach_tin_chet_loc_theo_kenh(app_that):
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")        # Nhân viên có outbox.doc
    _khach_nhan(app_that, tk, "Chị Hoa", "alo")
    cid = _hoi_thoai_cua(app_that, tk)
    _job_chet(app_that, tk, cid, "staff")

    assert len(qt.get("/api/outbox/jobs?status=dead").json()["items"]) == 1
    assert lan.get("/api/outbox/jobs?status=dead").json()["items"] == []
    _them_thanh_vien(app_that, tk, lan_id)
    assert len(lan.get("/api/outbox/jobs?status=dead").json()["items"]) == 1


# ------------------------------------------------------------------ 7. giữ thứ tự trong hội thoại

def test_claim_khong_vuot_job_cu_hon_dang_cho_retry(app_that):
    from agent import db
    from agent.omnichannel.outbox import PostgresOutboxRepository

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Hoa", "alo")
    cid = _hoi_thoai_cua(app_that, tk)

    async def gieo():
        await db.execute("UPDATE outbox_jobs SET status = 'cancelled'")
        p1 = await db.fetchrow(
            "INSERT INTO outbox_jobs (account_id, conversation_id, kind, idempotency_key, "
            " status, attempts, available_at, created_at) "
            "VALUES ($1::uuid, $2::uuid, 'send_text', 'phan-1', 'retry', 1, "
            " now() + interval '5 minutes', now() - interval '10 seconds') RETURNING id", tk, cid)
        p2 = await db.fetchrow(
            "INSERT INTO outbox_jobs (account_id, conversation_id, kind, idempotency_key, "
            " status, created_at) VALUES ($1::uuid, $2::uuid, 'send_text', 'phan-2', "
            " 'pending', now() - interval '5 seconds') RETURNING id", tk, cid)
        return p1["id"], p2["id"]
    p1, p2 = _sql(app_that, gieo)

    async def lay():
        return [j.id for j in await PostgresOutboxRepository().claim(worker_id="kt", limit=20)]
    assert p2 not in _sql(app_that, lay), "phần 2 không được đi trước phần 1 đang chờ retry"

    async def phan_1_chet():
        await db.execute("UPDATE outbox_jobs SET status = 'dead' WHERE id = $1", p1)
    _sql(app_that, phan_1_chet)
    assert _sql(app_that, lay) == [p2], "job cũ đã chết thì không chặn job sau nữa"


# ------------------------------------------------------------------ 8. kêu tin chết SAU guard

def test_tin_chet_trong_guard_chi_keu_sau_khi_commit(app_that, monkeypatch):
    from agent import db
    from agent.omnichannel import outbox
    from agent.omnichannel.outbox import PostgresOutboxRepository

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)

    async def gieo():
        await db.execute("UPDATE outbox_jobs SET status = 'cancelled'")
        await db.execute(
            "INSERT INTO outbox_jobs (account_id, kind, idempotency_key, status, attempts, "
            " max_attempts) VALUES ($1::uuid, 'send_text', $2, 'pending', 2, 3)",
            tk, str(uuid4()))
    _sql(app_that, gieo)

    thu_tu: list[str] = []
    repo = PostgresOutboxRepository()

    async def keu(job, loi):
        # Lúc kêu: đã thoát guard, và trạng thái `dead` đã COMMIT (đọc được
        # từ một kết nối khác).
        assert repo._guarded_connection.get() is None
        r = await db.fetchrow("SELECT status FROM outbox_jobs WHERE id = $1", job.id)
        thu_tu.append(f"keu:{r['status']}")
    monkeypatch.setattr(outbox, "_keu_tin_chet", keu)

    async def chay(nem: bool):
        job = (await repo.claim(worker_id="kt", limit=1))[0]
        try:
            async with repo.delivery_guard(job) as duoc:
                assert duoc
                await repo.mark_failed(job, "ConnectError: sidecar")
                thu_tu.append("trong_guard")
                if nem:
                    raise RuntimeError("hỏng sau khi ghi")
        except RuntimeError:
            thu_tu.append("rollback")
        return job.id

    _sql(app_that, chay, False)
    assert thu_tu == ["trong_guard", "keu:dead"]

    # Giao dịch rollback → job chưa hề chết → KHÔNG kêu.
    thu_tu.clear()

    async def gieo_lai():
        await db.execute(
            "INSERT INTO outbox_jobs (account_id, kind, idempotency_key, status, attempts, "
            " max_attempts) VALUES ($1::uuid, 'send_text', $2, 'pending', 2, 3)",
            tk, str(uuid4()))
    _sql(app_that, gieo_lai)
    jid = _sql(app_that, chay, True)
    assert thu_tu == ["trong_guard", "rollback"]
    assert _mot(app_that, "SELECT status FROM outbox_jobs WHERE id = $1",
                jid)["status"] == "processing"


# ------------------------------------------------------------------ 9. CSAT không nhận nhầm

def test_so_tra_loi_cau_hoi_khac_khong_thanh_diem_csat(app_that, monkeypatch):
    """
    Hỏi CSAT → khách hỏi tiếp (mở lại) → AI hỏi "lấy mấy hộp" → tự giải quyết
    → khách nhắn "2". "2" là số hộp, KHÔNG phải điểm 2/5.
    """
    from agent import cau_hinh_dong

    goc = cau_hinh_dong.lay
    monkeypatch.setattr(cau_hinh_dong, "lay",
                        lambda k, *a, **kw: "bat" if k == "CSAT_BAT" else goc(k, *a, **kw))
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    gui = _khach(app_that, tk)
    gui("alo")
    cid = _hoi_thoai_cua(app_that, tk)

    r = qt.post(f"/api/inbox/conversations/{cid}/giai-quyet")
    assert r.status_code == 200 and r.json()["csat"] == "đã hỏi", r.text

    gui("cho em hỏi thêm kem chống nắng")
    _mot(app_that, "INSERT INTO messages (conversation_id, role, content, direction, "
                   "delivery_status) VALUES ($1::uuid, 'agent', 'Dạ chị lấy mấy hộp ạ?', "
                   "'outbound', 'sent') RETURNING 1", cid)
    _mot(app_that, "UPDATE conversations SET state = 'resolved', status = 'closed', "
                   "mode = 'auto' WHERE id = $1::uuid RETURNING 1", cid)

    gui("2")
    assert _mot(app_that, "SELECT count(*) n FROM csat WHERE conversation_id = $1::uuid "
                          "AND diem IS NOT NULL", cid)["n"] == 0
    assert _mot(app_that, "SELECT state FROM conversations WHERE id = $1::uuid",
                cid)["state"] == "open", "tin '2' là yêu cầu mới — phải mở lại"


def test_diem_csat_ngay_sau_cau_hoi_van_duoc_ghi(app_that, monkeypatch):
    from agent import cau_hinh_dong

    goc = cau_hinh_dong.lay
    monkeypatch.setattr(cau_hinh_dong, "lay",
                        lambda k, *a, **kw: "bat" if k == "CSAT_BAT" else goc(k, *a, **kw))
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    gui = _khach(app_that, tk)
    gui("alo")
    cid = _hoi_thoai_cua(app_that, tk)
    assert qt.post(f"/api/inbox/conversations/{cid}/giai-quyet").json()["csat"] == "đã hỏi"
    gui("5")
    assert _mot(app_that, "SELECT diem FROM csat WHERE conversation_id = $1::uuid",
                cid)["diem"] == 5


# ------------------------------------------------------------------ 10. duyệt chỉ bản nháp AI

def _tin(app, cid: str, vai: str, trang_thai: str | None) -> str:
    return str(_mot(app, "INSERT INTO messages (conversation_id, role, content, delivered, "
                         "delivery_status) VALUES ($1::uuid, $2, 'Dạ còn hàng ạ', false, $3) "
                         "RETURNING id", cid, vai, trang_thai)["id"])


def test_duyet_chi_nhan_ban_nhap_ai(app_that):
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Hoa", "alo")
    cid = _hoi_thoai_cua(app_that, tk)
    _mot(app_that, "UPDATE conversations SET mode = 'assist', status = 'assist' "
                   "WHERE id = $1::uuid RETURNING 1", cid)

    def so_job():
        return _mot(app_that, "SELECT count(*) n FROM outbox_jobs "
                              "WHERE conversation_id = $1::uuid", cid)["n"]

    # Tin KHÁCH (dòng `delivered=false` — dữ liệu cũ, hoặc kênh ghi như thế):
    # không được biến thành tin nhân viên rồi gửi ngược cho chính khách.
    khach = _tin(app_that, cid, "customer", "received")
    truoc = so_job()
    assert qt.post(f"/api/messages/{khach}/approve").status_code == 409
    assert _mot(app_that, "SELECT role FROM messages WHERE id = $1::uuid",
                khach)["role"] == "customer"

    # Tin AI ĐANG XẾP HÀNG: duyệt nữa là job thứ hai, khách nhận hai lần.
    dang_gui = _tin(app_that, cid, "agent", "queued")
    assert qt.post(f"/api/messages/{dang_gui}/approve").status_code == 409
    assert so_job() == truoc

    # Bản nháp AI thật: duyệt được, bấm hai lần vẫn một job.
    nhap = _tin(app_that, cid, "agent", "draft")
    r = qt.post(f"/api/messages/{nhap}/approve")
    assert r.status_code == 200 and r.json().get("queued"), r.text
    r2 = qt.post(f"/api/messages/{nhap}/approve")
    assert r2.status_code == 200 and r2.json().get("duplicate") is True, r2.text
    assert so_job() == truoc + 1


# ------------------------------------------------------------------ ghi chú phụ: tệp đính kèm

def test_tep_dinh_kem_kenh_khac_tra_404(app_that, tmp_path):
    from agent import db

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _, lan = _nhan_vien_moi(qt, "lan")
    _khach_nhan(app_that, tk, "Chị Hoa", "alo")
    cid = _hoi_thoai_cua(app_that, tk)

    async def gieo():
        m = await db.fetchrow("SELECT id FROM messages WHERE conversation_id = $1::uuid "
                              "LIMIT 1", cid)
        a = await db.fetchrow(
            "INSERT INTO attachments (message_id, ordinal, kind, storage_key) "
            "VALUES ($1, 99, 'image', $2) RETURNING id",
            m["id"], str(ROOT / "data" / f"khong-co-{uuid4().hex}.png"))
        return str(a["id"])
    aid = _sql(app_that, gieo)

    # Quản trị qua được chốt kênh (tệp không có trên đĩa → "Tệp không còn").
    r = qt.get(f"/api/attachments/{aid}/file")
    assert r.status_code == 404 and "không còn" in r.json()["detail"]
    # Nhân viên ngoài kênh dừng ngay ở chốt kênh.
    r = lan.get(f"/api/attachments/{aid}/file")
    assert r.status_code == 404 and r.json()["detail"] == "Không thấy hội thoại"
