"""
Những chỗ TIN VÀO rò rỉ im lặng — rà soát 16.11.2026, kiểm bằng dữ liệu thật.

1. Ảnh/tệp Zalo cá nhân: sidecar không đọc → parse trả None → webhook trả
   `skipped` không một dòng nhật ký (80 tin, 0 tệp trên CSDL thật).
3. Hộp thư bền chạy lại SAU bước ingest: handle_inbound thoát sớm vì "trùng",
   dòng đánh `xong`, khách không được trả lời, không việc, không báo.
5. Tin NHÓM Zalo vào thẳng hệ thống (nhóm khoá luận); `thread_type` chỉ nhớ
   trong RAM của adapter tạm nên adapter gửi luôn gửi 0.
6. Meta trả quyền hội thoại về app nhưng `mode` vẫn `human`; đường native
   không nghe sự kiện bàn giao — hội thoại kẹt người vĩnh viễn.
7. Chống trùng hộp thư bền TOÀN CỤC: hai nick cùng nhóm, cùng msgId — bản
   thứ hai bị nuốt.

Phần đầu không cần CSDL; phần sau chạy trên Postgres thật.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.channels.base import InboundMessage  # noqa: E402
from agent.channels.zalo_personal import ZaloPersonalAdapter, ly_do_bo_qua  # noqa: E402
from agent.omnichannel.accounts import AccountStatus, Channel, ChannelAccount  # noqa: E402


# ====================================================================
#  1 + 5. Webhook Zalo cá nhân: không bỏ câm, mặc định bỏ tin nhóm
# ====================================================================

def _tk_zalo() -> ChannelAccount:
    return ChannelAccount(
        id=uuid4(), channel=Channel.ZALO_PERSONAL, display_name="Zalo shop",
        external_account_id="own-1", status=AccountStatus.ACTIVE,
        capabilities={}, metadata={}, is_legacy=False)


@pytest.fixture
def webhook_zalo(monkeypatch):
    """Route callback THẬT, chỉ thay kho tài khoản/credential/chữ ký/CSDL."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agent.api import zalo_personal_webhook as w

    tk = _tk_zalo()
    su_kien: list[tuple[str, dict]] = []
    vao_hop_thu: list[InboundMessage] = []

    class _Repo:
        async def get(self, _id):
            return tk

    class _Loader:
        async def load(self, _id):
            return {"sidecar_secret": "s" * 40}

    async def ghi(kind, **kw):
        su_kien.append((kind, kw))

    async def nhan(m, tasks=None):
        vao_hop_thu.append(m)
        return uuid4()

    monkeypatch.setattr(w, "PostgresAccountRepository", _Repo)
    monkeypatch.setattr(w, "_vault_loader", lambda _repo: _Loader())
    monkeypatch.setattr(w, "bo_sung_bi_mat_may_chu", lambda _k, c: c)
    monkeypatch.setattr(w, "verify_sidecar_callback", lambda *a, **k: True)
    monkeypatch.setattr(w.db, "log_event", ghi)
    monkeypatch.setattr(w.hop_thu_ben, "nhan", nhan)
    w._DA_GHI_NHOM.clear()
    app = FastAPI()
    app.include_router(w.router)
    with TestClient(app) as khach:
        yield khach, tk, su_kien, vao_hop_thu


def _tin(**kw) -> dict:
    tin = {"msg_id": "m1", "thread_id": "khach-1", "thread_type": 0,
           "sender_id": "khach-1", "sender_name": "Chị Lan", "text": "",
           "timestamp": 1763280000000, "attachments": [], "msg_type": "webchat"}
    tin.update(kw)
    return {"event": "message", "message": tin}


def test_anh_khong_chu_tu_sidecar_moi_vao_hop_thu(webhook_zalo):
    """Đúng hình sidecar nay gửi cho chat.photo — phải thành tin có ảnh."""
    khach, tk, _su_kien, vao = webhook_zalo
    r = khach.post(f"/webhook/native/zalo-personal/{tk.id}", json=_tin(
        msg_type="chat.photo",
        attachments=[{"type": "image", "url": "https://photo.zdn.vn/goc.jpg",
                      "thumb": "https://photo.zdn.vn/t.jpg"}]))
    assert r.json() == {"ok": True, "queued": 1}
    assert vao[0].text == ""
    assert vao[0].attachments[0]["loai"] == "image"
    assert vao[0].attachments[0]["url"] == "https://photo.zdn.vn/goc.jpg"


def test_tep_giu_ten_va_co(webhook_zalo):
    khach, tk, _su_kien, vao = webhook_zalo
    khach.post(f"/webhook/native/zalo-personal/{tk.id}", json=_tin(
        msg_type="share.file",
        attachments=[{"type": "file", "url": "https://f.zdn.vn/a.pdf",
                      "name": "Bao_gia.pdf", "size": 1832}]))
    tep = vao[0].attachments[0]
    assert tep["loai"] == "file" and tep["ten"] == "Bao_gia.pdf" and tep["size"] == 1832


def test_tin_khong_doc_duoc_thi_GHI_SU_KIEN_khong_bo_cam(webhook_zalo):
    """Lỗi số 1 lịch sử repo: tin bị bỏ mà không một dòng nhật ký."""
    khach, tk, su_kien, vao = webhook_zalo
    r = khach.post(f"/webhook/native/zalo-personal/{tk.id}",
                   json=_tin(msg_type="chat.sticker"))
    assert r.json()["skipped"] is True
    assert vao == []
    assert len(su_kien) == 1
    kind, kw = su_kien[0]
    assert kind == "zalo_personal.tin_bo_qua"
    assert kw["msg_type"] == "chat.sticker"
    assert kw["ly_do"] == "khong_co_chu_va_khong_co_tep"
    assert kw["ref_id"] == tk.id


def test_ly_do_bo_khong_chua_loi_khach():
    kq = ly_do_bo_qua(_tin(msg_id="", text="số em 0912345678"))
    assert kq["ly_do"] == "thieu_thread_id_hoac_msg_id"
    assert "0912345678" not in json.dumps(kq, ensure_ascii=False)


def test_tat_nhan_tin_nhom_thi_BI_BO_co_ghi_su_kien(webhook_zalo, monkeypatch):
    """
    Từ 20.11.2026 mặc định NHẬN tin nhóm (AI bị chặn ở chỗ khác — xem
    tests/test_tin_nhom_zalo.py). Người vận hành tắt thì vẫn bỏ có ghi.
    """
    from agent.config import settings

    monkeypatch.setattr(settings, "zalo_nhan_tin_nhom", False)
    khach, tk, su_kien, vao = webhook_zalo
    for i in range(3):          # nhóm sôi nổi: ba tin liền
        r = khach.post(f"/webhook/native/zalo-personal/{tk.id}", json=_tin(
            msg_id=f"g{i}", thread_id="nhom-1", thread_type=1,
            sender_id=f"ban-{i}", text="mai nộp khoá luận chưa"))
        assert r.json() == {"ok": True, "skipped": "tin_nhom"}
    assert vao == []
    # Ghi sự kiện, nhưng THƯA: một dòng cho cả loạt, không một dòng mỗi tin.
    assert [k for k, _ in su_kien] == ["zalo_personal.bo_tin_nhom"]


def test_bat_cong_tac_thi_tin_nhom_vao(webhook_zalo, monkeypatch):
    from agent.config import settings

    monkeypatch.setattr(settings, "zalo_nhan_tin_nhom", True)
    khach, tk, _su_kien, vao = webhook_zalo
    r = khach.post(f"/webhook/native/zalo-personal/{tk.id}", json=_tin(
        thread_id="nhom-1", thread_type=1, sender_id="ban-1", text="shop ơi"))
    assert r.json() == {"ok": True, "queued": 1}
    assert vao[0].meta["thread_type"] == 1


def test_ghi_bo_tin_nhom_moi_gio_mot_lan(monkeypatch):
    from agent.api import zalo_personal_webhook as w

    ghi: list = []

    async def log_event(kind, **kw):
        ghi.append(kind)
    monkeypatch.setattr(w.db, "log_event", log_event)
    w._DA_GHI_NHOM.clear()
    acc = uuid4()
    chay = asyncio.run
    assert chay(w._ghi_bo_tin_nhom(acc, "n1", bay_gio=100.0)) is True
    assert chay(w._ghi_bo_tin_nhom(acc, "n1", bay_gio=200.0)) is False
    assert chay(w._ghi_bo_tin_nhom(acc, "n2", bay_gio=200.0)) is True   # nhóm khác
    assert chay(w._ghi_bo_tin_nhom(acc, "n1", bay_gio=100.0 + 3601)) is True
    assert len(ghi) == 3


def test_env_example_khai_cong_tac_nhom():
    src = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "\nZALO_NHAN_TIN_NHOM=true" in src


# ====================================================================
#  6. Đường native nghe sự kiện bàn giao
# ====================================================================

def test_dispatcher_native_doc_su_kien_ban_giao():
    from agent.api.native_webhooks import MetaWebhookDispatcher
    from agent.channels.messenger import FacebookAdapter

    tk = ChannelAccount(
        id=uuid4(), channel=Channel.FACEBOOK, display_name="Trang",
        external_account_id="page-1", status=AccountStatus.ACTIVE,
        capabilities={}, metadata={}, is_legacy=False)
    ad = FacebookAdapter(account_id=tk.id, credentials={
        "access_token": "t", "app_secret": "bi-mat", "app_id": "app-cua-ta",
        "external_account_id": "page-1"})

    class Accounts:
        async def find_active_by_external_ids(self, channel, ids):
            return [tk]

    class Factory:
        async def create(self, _id):
            return ad

    payload = {"object": "page", "entry": [{"id": "page-1", "messaging": [{
        "sender": {"id": "khach-9"}, "recipient": {"id": "page-1"},
        "pass_thread_control": {"new_owner_app_id": "app-cua-ta",
                                "metadata": "xong"}}]}]}
    raw = json.dumps(payload).encode()
    ky = "sha256=" + hmac.new(b"bi-mat", raw, hashlib.sha256).hexdigest()
    d = MetaWebhookDispatcher(Accounts(), Factory())
    tin = asyncio.run(d.dispatch(raw_body=raw, signature=ky, payload=payload))
    assert tin == []
    assert d.ban_giao == [(tk.id, {"khach": "khach-9", "loai": "pass_thread_control",
                                   "ve_tay_ta": True})]
    asyncio.run(ad.aclose())


def test_hai_route_native_deu_ap_ban_giao_truoc_khi_xep_tin():
    import inspect

    from agent.api import native_webhooks as nw

    for ham in (nw.native_meta_webhook, nw.native_meta_account_webhook):
        src = inspect.getsource(ham)
        assert src.index("_ap_ban_giao(") < src.index("hop_thu_ben.nhan("), ham.__name__


# ====================================================================
#  Postgres thật
# ====================================================================

def _sql(url: str, sql: str, *a):
    import asyncpg

    async def chay():
        conn = await asyncpg.connect(url)
        try:
            return await conn.fetchrow(sql, *a)
        finally:
            await conn.close()
    return asyncio.run(chay())


def _chay(url: str, ham, *a):
    from tests.test_giai_quyet_csat import _goi
    return _goi(url, ham, *a)


@pytest.fixture
def csdl(csdl_kiem_thu):
    from fastapi.testclient import TestClient

    from tests.conftest import nguoi_thu
    from tests.test_giai_quyet_csat import Q, _app
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*Q))):
        pass
    return csdl_kiem_thu


def _inbound(account_id: UUID, khoa: str, *, ref="t1", thread_type=0) -> InboundMessage:
    return InboundMessage(
        account_id=account_id, channel="zalo_personal", conversation_ref=ref,
        customer_ref="c1", customer_name="Lan", text="còn hàng không ạ",
        dedupe_key=khoa, received_at=datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc),
        attachments=[], meta={"thread_type": thread_type, "nen_tang_goc": "zalo_personal"})


def test_hai_nick_cung_nhom_cung_msgid_la_HAI_tin(csdl):
    """Chống trùng theo TÀI KHOẢN — cùng phạm vi với webhook_deliveries."""
    from agent.omnichannel import hop_thu_ben

    a, b = uuid4(), uuid4()
    assert _chay(csdl, hop_thu_ben.nhan, _inbound(a, "zalo_personal:g1")) is not None
    assert _chay(csdl, hop_thu_ben.nhan, _inbound(b, "zalo_personal:g1")) is not None
    # Hãng phát lại cho CÙNG nick thì vẫn chặn.
    assert _chay(csdl, hop_thu_ben.nhan, _inbound(a, "zalo_personal:g1")) is None
    r = _sql(csdl, "SELECT count(*) AS n FROM tin_vao WHERE dedupe_key = 'zalo_personal:g1'")
    assert r["n"] == 2


def test_thread_type_ben_adapter_GUI_khac_adapter_DOC_van_dung(csdl):
    """
    Xanh giả cũ: test dùng CÙNG một instance để đọc rồi gửi. Thật ra adapter
    đọc là bản tạm trong webhook, adapter gửi là bản trong cache registry.
    Ở đây: ingest qua CSDL, rồi một adapter MỚI TINH gửi vào nhóm.
    """
    from agent import db
    from agent.omnichannel.inbox_service import InboxService, PostgresInboxRepository

    gui: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        gui.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "message_id": "out-1"})

    async def chay():
        acc = await db.fetchrow(
            "INSERT INTO channel_accounts (channel, display_name, status) "
            "VALUES ('zalo_personal', 'Zalo', 'active') RETURNING id")
        await InboxService(PostgresInboxRepository()).ingest(
            _inbound(acc["id"], "zalo_personal:n1", ref="nhom-7", thread_type=1))
        await InboxService(PostgresInboxRepository()).ingest(
            _inbound(acc["id"], "zalo_personal:r1", ref="khach-7", thread_type=0))
        moi = ZaloPersonalAdapter(
            account_id=acc["id"], credentials={"sidecar_secret": "s"},
            client=httpx.AsyncClient(base_url="http://127.0.0.1:3210",
                                     transport=httpx.MockTransport(handler)))
        try:
            await moi.send_text("nhom-7", "Dạ em trả lời nhóm")
            await moi.send_file("nhom-7", "/tmp/a.jpg", "ảnh")
            await moi.send_text("khach-7", "Dạ em trả lời riêng")
            await moi.send_text("chua-tung-thay", "chào")
        finally:
            await moi.aclose()
        return (await db.fetchrow(
            "SELECT thread_type FROM conversations WHERE external_id = 'nhom-7'"))["thread_type"]

    assert _chay(csdl, chay) == 1
    assert [g["thread_type"] for g in gui] == [1, 1, 0, 0]


def test_nhan_lai_quyen_thi_ca_mode_ve_auto(csdl):
    """Hành vi, không soi chuỗi: test cũ chỉ tìm "'auto'" trong mã nên xanh giả."""
    from agent import db
    from agent.omnichannel.ban_giao_meta import ap_dung_ban_giao

    async def chay():
        acc = await db.fetchrow(
            "INSERT INTO channel_accounts (channel, display_name, status) "
            "VALUES ('facebook', 'Trang', 'active') RETURNING id")
        kh = await db.fetchrow("INSERT INTO contacts (display_name) VALUES ('Hoa') RETURNING id")
        d = await db.fetchrow(
            "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
            "VALUES ($1, $2, 'psid-1') RETURNING id", kh["id"], acc["id"])
        c = await db.fetchrow(
            "INSERT INTO conversations (account_id, channel, external_id, contact_id, "
            "contact_point_id, status, mode, version) VALUES ($1, 'facebook', 'psid-1', "
            "$2, $3, 'escalated', 'human', 3) RETURNING id", acc["id"], kh["id"], d["id"])
        kq_nhan = await ap_dung_ban_giao(
            {"khach": "psid-1", "loai": "pass_thread_control", "ve_tay_ta": True},
            acc["id"], boi="meta_native")
        sau_nhan = await db.fetchrow(
            "SELECT status, mode, version FROM conversations WHERE id = $1", c["id"])
        kq_trao = await ap_dung_ban_giao(
            {"khach": "psid-1", "loai": "take_thread_control", "ve_tay_ta": False},
            acc["id"], boi="meta_native")
        sau_trao = await db.fetchrow(
            "SELECT status, mode FROM conversations WHERE id = $1", c["id"])
        khong_co = await ap_dung_ban_giao(
            {"khach": "la", "loai": "pass_thread_control", "ve_tay_ta": True},
            acc["id"], boi="meta_native")
        return kq_nhan, dict(sau_nhan), kq_trao, dict(sau_trao), khong_co

    kq_nhan, sau_nhan, kq_trao, sau_trao, khong_co = _chay(csdl, chay)
    assert kq_nhan == "nhan_lai"
    assert sau_nhan == {"status": "auto", "mode": "auto", "version": 4}
    assert kq_trao == "trao_di" and sau_trao == {"status": "escalated", "mode": "human"}
    assert khong_co is None


# ---------------------------------------------- 3. chạy lại sau ingest (app thật)

def _dem_tin_vao(app_that):
    from agent import db
    from tests.test_nghiem_thu_saas import _sql as goi

    async def doc():
        t = await db.fetchrow("SELECT id, trang_thai, so_lan_thu FROM tin_vao")
        c = await db.fetchrow("SELECT id, status, mode FROM conversations")
        return dict(t) if t else None, dict(c) if c else None
    return goi(app_that, doc)


def _gay_hong_sau_ingest(monkeypatch):
    """
    handle_inbound THẬT; chỉ `channels.get_for_account` ném — đúng chỗ đã
    quan sát được, nằm SAU bước lưu tin và TRƯỚC khi AI soạn.
    """
    from agent.channels import registry

    async def hong(_account_id):
        raise RuntimeError("không dựng được adapter")
    monkeypatch.setattr(registry, "get_for_account", hong)


def test_chay_lai_sau_ingest_ma_chua_ai_tra_loi_thi_CHUYEN_NGUOI(app_that, monkeypatch):
    from agent import db
    from agent.omnichannel import hop_thu_ben
    from tests.test_nghiem_thu_saas import _kenh_webchat, _khach_nhan, _quan_tri_vao
    from tests.test_nghiem_thu_saas import _sql as goi

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt, agent_bat=True)
    _gay_hong_sau_ingest(monkeypatch)
    _khach_nhan(app_that, tk, "Chị Hoa", "Shop còn kem chống nắng không?")

    t, c = _dem_tin_vao(app_that)
    assert t["trang_thai"] == "cho" and t["so_lan_thu"] == 1
    assert c["status"] == "auto"            # tin đã lưu, chưa ai lo

    # App bị dừng giữa chừng lần sau (CancelledError không bị bắt): dòng kẹt
    # `dang_xu_ly`. Vòng nền nhặt lại sau BO_DO_SAU_GIAY.
    async def ket():
        await db.execute("UPDATE tin_vao SET trang_thai = 'dang_xu_ly', "
                         "khoa_luc = now() - interval '20 minutes'")
    goi(app_that, ket)
    assert goi(app_that, hop_thu_ben.quet_mot_luot) == {"xong": 1}

    t, c = _dem_tin_vao(app_that)
    assert t["trang_thai"] == "xong"
    assert c["status"] == "escalated" and c["mode"] == "human"

    async def bang_chung():
        su = await db.fetchrow("SELECT count(*) AS n FROM events "
                               "WHERE kind = 'tin_vao.chay_lai_chuyen_nguoi'")
        viec = await db.fetchrow("SELECT count(*) AS n FROM cong_viec "
                                 "WHERE conversation_id = $1", c["id"])
        return su["n"], viec["n"]
    assert goi(app_that, bang_chung) == (1, 1)


def test_chay_lai_khi_DA_co_phan_hoi_thi_khong_chuyen_nguoi(app_that, monkeypatch):
    """Đã có nháp/tin agent sau tin khách: không chuyển người thừa."""
    from agent import db
    from agent.omnichannel import hop_thu_ben
    from tests.test_nghiem_thu_saas import _kenh_webchat, _khach_nhan, _quan_tri_vao
    from tests.test_nghiem_thu_saas import _sql as goi

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt, agent_bat=True)
    _gay_hong_sau_ingest(monkeypatch)
    _khach_nhan(app_that, tk, "Chị Hoa", "Shop còn kem chống nắng không?")
    _t, c = _dem_tin_vao(app_that)

    async def da_tra_loi():
        await db.execute(
            "INSERT INTO messages (conversation_id, role, content, delivered, direction, "
            "delivery_status, created_at) VALUES ($1, 'agent', 'Dạ còn ạ', false, "
            "'outbound', 'draft', now() + interval '1 second')", c["id"])
        await db.execute("UPDATE tin_vao SET cho_den = now()")
    goi(app_that, da_tra_loi)
    assert goi(app_that, hop_thu_ben.quet_mot_luot) == {"xong": 1}
    _t, c = _dem_tin_vao(app_that)
    assert c["status"] == "auto" and c["mode"] != "human"


def test_lan_dau_hong_TRUOC_ingest_thi_lan_sau_xu_ly_tron_khong_chuyen_thua(csdl, monkeypatch):
    """Tin chưa từng được lưu: lần chạy lại là lần đầu thật, không kiểm gì thêm."""
    from agent.omnichannel import hop_thu_ben, xu_ly_tin_vao

    goi_kiem: list = []

    async def ok(_msg):
        return None

    async def kiem(*a):
        goi_kiem.append(a)
        return False
    monkeypatch.setattr(xu_ly_tin_vao, "handle_inbound", ok)
    monkeypatch.setattr(hop_thu_ben, "_dam_bao_co_nguoi_lo", kiem)
    id_ = _chay(csdl, hop_thu_ben.nhan, _inbound(uuid4(), "zalo_personal:x"))
    _sql(csdl, "UPDATE tin_vao SET so_lan_thu = 2 WHERE id = $1 RETURNING 1", id_)
    assert _chay(csdl, hop_thu_ben.xu_ly_mot, id_) == "xong"
    assert goi_kiem == []
