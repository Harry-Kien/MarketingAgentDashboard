"""
Tin NHÓM Zalo: vào hộp thư cho NHÂN VIÊN, danh tính là nhóm, AI không nói.

Lỗi gốc (kiểm trên production 20.11.2026):
1. Hội thoại nhóm lấy người GỬI làm danh tính: tên hội thoại là người nói
   sau cùng, contact là contact riêng của người đó.
2. Trí nhớ agent khoá theo `customer_ref` = người gửi → hồ sơ riêng của một
   thành viên bị đọc vào câu trả lời trong nhóm, chuyện nhóm ghi vào hồ sơ họ.
3. `messages` không có người gửi → cả nhóm hiện thành một "Khách".
4. `contacts.display_name` bị tên mặc định đè; hai danh sách tên mặc định lệch.
5. `thread_type` NULL ở hội thoại cũ → nhân viên trả lời vào nhóm bị Zalo
   huỷ "Tham số không hợp lệ".
6. Mặc định bỏ hẳn tin nhóm — bỏ luôn khách hỏi hàng trong nhóm.

Quyết định của chủ dự án: tin nhóm VÀO hộp thư, đánh dấu nhóm, tên nhóm +
tên người gửi từng tin; AI KHÔNG BAO GIỜ trả lời trong nhóm.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.channels.base import InboundMessage, la_ref_nhom, ref_nhom  # noqa: E402
from agent.channels.ten_khach import (TEN_MAC_DINH, la_ten_mac_dinh,  # noqa: E402
                                      ten_nhom_du_phong)
from agent.channels.zalo_personal import ZaloPersonalAdapter  # noqa: E402


def _adapter() -> ZaloPersonalAdapter:
    return ZaloPersonalAdapter(account_id=uuid4(), credentials={"sidecar_secret": "s"})


def _cb(**kw) -> dict:
    tin = {"msg_id": "m1", "thread_id": "nhom-123456789", "thread_type": 1,
           "is_group": True, "group_name": "Hội mê skincare",
           "sender_id": "ban-1", "sender_name": "Chị Lan", "text": "shop ơi còn serum không",
           "timestamp": 1763280000000, "attachments": [], "msg_type": "webchat"}
    tin.update(kw)
    return {"event": "message", "message": tin}


# ====================================================================
#  Adapter: danh tính của hội thoại nhóm là NHÓM
# ====================================================================

def test_tin_nhom_danh_tinh_la_nhom_nguoi_gui_tach_rieng():
    m = _adapter().parse(_cb())
    assert m is not None
    assert m.la_nhom is True
    assert m.conversation_ref == "nhom-123456789"
    assert m.customer_ref == "group:nhom-123456789" == ref_nhom("nhom-123456789")
    assert m.customer_name == "Hội mê skincare"
    assert (m.sender_ref, m.sender_name) == ("ban-1", "Chị Lan")
    assert m.meta["thread_type"] == 1


def test_hai_thanh_vien_cung_mot_danh_tinh_nhom():
    ad = _adapter()
    a = ad.parse(_cb(msg_id="a", sender_id="ban-1", sender_name="Chị Lan"))
    b = ad.parse(_cb(msg_id="b", sender_id="ban-2", sender_name="Anh Tú"))
    assert a and b
    assert (a.customer_ref, a.customer_name) == (b.customer_ref, b.customer_name)
    assert a.sender_name != b.sender_name


def test_thieu_ten_nhom_thi_ten_du_phong_khong_lay_ten_nguoi_gui():
    m = _adapter().parse(_cb(group_name=""))
    assert m is not None
    assert m.customer_name == ten_nhom_du_phong("nhom-123456789") == "Nhóm Zalo …456789"
    assert "Chị Lan" not in m.customer_name
    assert la_ten_mac_dinh(m.customer_name), "tên dự phòng không được đè tên nhóm thật"


def test_sidecar_cu_chi_co_thread_type_van_nhan_ra_nhom():
    """Sidecar là tiến trình riêng, có thể chạy bản cũ chưa có `is_group`."""
    cb = _cb()
    del cb["message"]["is_group"], cb["message"]["group_name"]
    m = _adapter().parse(cb)
    assert m is not None and m.la_nhom is True
    assert la_ref_nhom(m.customer_ref)


def test_tin_rieng_giu_nguyen_hanh_vi_cu():
    m = _adapter().parse(_cb(thread_id="khach-1", thread_type=0, is_group=False,
                             group_name="", sender_id="khach-1", sender_name="Chị Lan"))
    assert m is not None
    assert m.la_nhom is False
    assert (m.customer_ref, m.customer_name) == ("khach-1", "Chị Lan")
    assert m.sender_ref == "khach-1"
    assert m.meta["thread_type"] == 0


def test_tin_rieng_khong_ten_van_la_Khach_Zalo():
    m = _adapter().parse(_cb(thread_id="khach-1", thread_type=0, is_group=False,
                             sender_id="khach-1", sender_name=""))
    assert m is not None and m.customer_name == "Khách Zalo"


# ====================================================================
#  Tên mặc định: MỘT danh sách cho cả hệ thống
# ====================================================================

def test_moi_ten_mac_dinh_cua_adapter_deu_nam_trong_TEN_MAC_DINH():
    """
    `identity.py` từng giữ danh sách riêng viết tay trong SQL, thiếu "Khách
    Facebook". Thêm adapter có tên mặc định mới mà quên thêm vào đây là tên
    thật của khách bị đè — test này đọc chính mã adapter để bắt.
    """
    nguon = list((ROOT / "agent" / "channels").glob("*.py")) + [ROOT / "agent/api/webchat.py"]
    thay: set[str] = set()
    for p in nguon:
        thay |= set(re.findall(r'"(Khách(?: [A-Za-zÀ-ỹ]+)?)"', p.read_text(encoding="utf-8")))
    assert thay, "không tìm thấy tên mặc định nào — biểu thức dò đã hỏng"
    assert thay <= TEN_MAC_DINH, thay - TEN_MAC_DINH


def test_identity_khong_con_danh_sach_rieng():
    src = (ROOT / "agent/omnichannel/identity.py").read_text(encoding="utf-8")
    assert "'Khách Zalo'" not in src and "la_ten_mac_dinh" in src


# ====================================================================
#  Webhook: mặc định NHẬN tin nhóm; so người gửi để lọc tin của chính mình
# ====================================================================

@pytest.fixture
def webhook(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agent.api import zalo_personal_webhook as w
    from agent.omnichannel.accounts import AccountStatus, Channel, ChannelAccount

    tk = ChannelAccount(id=uuid4(), channel=Channel.ZALO_PERSONAL, display_name="Zalo",
                        external_account_id="own-1", status=AccountStatus.ACTIVE,
                        capabilities={}, metadata={}, is_legacy=False)
    su_kien: list[str] = []
    vao: list[InboundMessage] = []

    class _Repo:
        async def get(self, _id):
            return tk

    class _Loader:
        async def load(self, _id):
            return {"sidecar_secret": "s" * 40}

    async def ghi(kind, **kw):
        su_kien.append(kind)

    async def nhan(m, tasks=None):
        vao.append(m)
        return uuid4()

    monkeypatch.setattr(w, "PostgresAccountRepository", _Repo)
    monkeypatch.setattr(w, "_vault_loader", lambda _r: _Loader())
    monkeypatch.setattr(w, "bo_sung_bi_mat_may_chu", lambda _k, c: c)
    monkeypatch.setattr(w, "verify_sidecar_callback", lambda *a, **k: True)
    monkeypatch.setattr(w.db, "log_event", ghi)
    monkeypatch.setattr(w.hop_thu_ben, "nhan", nhan)
    w._DA_GHI_NHOM.clear()
    app = FastAPI()
    app.include_router(w.router)
    with TestClient(app) as k:
        yield k, tk, su_kien, vao


def test_mac_dinh_tin_nhom_VAO_hop_thu(webhook):
    from agent.config import settings

    assert settings.zalo_nhan_tin_nhom is True, "mặc định phải NHẬN tin nhóm"
    k, tk, su_kien, vao = webhook
    r = k.post(f"/webhook/native/zalo-personal/{tk.id}", json=_cb())
    assert r.json() == {"ok": True, "queued": 1}
    assert vao[0].la_nhom and vao[0].customer_name == "Hội mê skincare"
    assert su_kien == []


def test_tin_nhan_vien_gui_vao_nhom_vong_ve_bi_loc(webhook):
    """`customer_ref` của nhóm là `group:…` — so nó với own_id thì lọt."""
    k, tk, _su_kien, vao = webhook
    r = k.post(f"/webhook/native/zalo-personal/{tk.id}", json=_cb(sender_id="own-1"))
    assert r.json()["skipped"] == "tin_tu_chinh_minh"
    assert vao == []


def test_tat_cong_tac_thi_tin_nhom_bi_bo_co_ghi(webhook, monkeypatch):
    from agent.config import settings

    monkeypatch.setattr(settings, "zalo_nhan_tin_nhom", False)
    k, tk, su_kien, vao = webhook
    r = k.post(f"/webhook/native/zalo-personal/{tk.id}", json=_cb())
    assert r.json() == {"ok": True, "skipped": "tin_nhom"}
    assert vao == [] and su_kien == ["zalo_personal.bo_tin_nhom"]


# ====================================================================
#  Hộp thư bền giữ cờ nhóm và người gửi
# ====================================================================

def test_hop_thu_ben_giu_co_nhom_va_nguoi_gui():
    from agent.omnichannel.hop_thu_ben import ra_json, tu_json

    m = _adapter().parse(_cb())
    assert m is not None
    lai = tu_json(json.loads(json.dumps(ra_json(m))))
    assert (lai.la_nhom, lai.sender_ref, lai.sender_name) == (True, "ban-1", "Chị Lan")
    cu = ra_json(m)
    for khoa in ("la_nhom", "sender_ref", "sender_name"):
        cu.pop(khoa)
    cu_lai = tu_json(cu)                 # dòng ghi trước bản này
    assert (cu_lai.la_nhom, cu_lai.sender_ref) == (False, "")


# ====================================================================
#  Lưới thứ hai: outbox, CSAT, trí nhớ
# ====================================================================

def test_outbox_chan_may_noi_vao_nhom_cho_nhan_vien():
    from agent.omnichannel.outbound_service import OutboundBlocked, OutboundService

    nhom = {"mode": "auto", "status": "auto", "state": "open", "thread_type": 1}
    for vai in ("agent", "system"):
        with pytest.raises(OutboundBlocked):
            OutboundService._ensure_role_allowed(nhom, vai)
    OutboundService._ensure_role_allowed(nhom, "staff")
    OutboundService._ensure_role_allowed({**nhom, "thread_type": 0}, "agent")
    OutboundService._ensure_role_allowed({**nhom, "thread_type": None}, "system")


def test_csat_khong_hoi_trong_nhom(monkeypatch):
    from agent.omnichannel import giai_quyet

    monkeypatch.setattr(giai_quyet.cau_hinh_dong, "lay", lambda _k: "bat")
    kq = asyncio.run(giai_quyet._hoi_csat(uuid4(), "nhom-1", None, la_nhom=True))
    assert kq == "nhóm — không hỏi"


def test_tri_nho_khach_khong_doc_khong_ghi_cho_nhom(monkeypatch):
    from agent.core import ho_so_khach

    async def no(*_a, **_k):
        raise AssertionError("không được chạm CSDL cho hồ sơ nhóm")
    monkeypatch.setattr(ho_so_khach.db, "fetchrow", no)
    monkeypatch.setattr(ho_so_khach.db, "fetchrow_chac", no)
    monkeypatch.setattr(ho_so_khach.db, "execute", no)
    ref = ref_nhom("nhom-1")
    assert asyncio.run(ho_so_khach.lay(ref, "zalo_personal")) is None
    assert asyncio.run(ho_so_khach.lam_ngu_canh(ref, "zalo_personal")) == ""
    asyncio.run(ho_so_khach.ghi(ref, "zalo_personal", "Loại da: da dầu"))
    asyncio.run(ho_so_khach.tu_tin_nhan(ref, "zalo_personal", "em da dầu, đang mang thai"))
    asyncio.run(ho_so_khach.tu_tool(ref, "zalo_personal", "goi_y_san_pham", {"loai_da": "da dầu"}))


def test_handle_inbound_chan_nhom_TRUOC_moi_nhanh_khac():
    """Đặt sau tu_dong/CSAT là máy kịp nói vào nhóm trước khi bị chặn."""
    import inspect

    from agent.omnichannel import xu_ly_tin_vao

    src = inspect.getsource(xu_ly_tin_vao.handle_inbound)
    chan = src.index("await _giao_nguoi_tin_nhom(")
    # So với MÃ, không so với chú thích ĐỌC ở đầu hàm (nó nhắc "standby" sớm hơn).
    for sau in ('(msg.meta or {}).get("standby")', "tu_dong.chay_tin_khach(",
                "ghi_diem_neu_la_csat(", "thong_bao_ai.gui_neu_chua(", "await brain.respond("):
        assert chan < src.index(sau), sau


# ====================================================================
#  Dashboard
# ====================================================================

def test_dashboard_gan_nhan_nhom_va_ten_nguoi_gui():
    src = (ROOT / "dashboard/src/03-hoi-thoai.js").read_text(encoding="utf-8")
    assert "Number(c && c.thread_type) === 1" in src
    # Nhãn ở CẢ danh sách lẫn đầu khung chi tiết.
    assert "${nhomBadge(c)}${srcBadge(c.channel" in src
    assert '<span class="convo__name">${esc(c.customer_name || "Khách")}</span>\n      ${nhomBadge(c)}' in src
    assert "m.sender_name" in src and "msg__nguoi" in src
    # Không mời "Để agent tự trả lời" trong nhóm.
    assert "!taken && !nhom" in src
    goi = (ROOT / "dashboard/app.js").read_text(encoding="utf-8")
    assert "function nhomBadge(c)" in goi, "chưa đóng gói lại dashboard"
    assert ".msg__nguoi" in (ROOT / "dashboard/app.css").read_text(encoding="utf-8")


def test_api_danh_sach_tra_thread_type():
    import inspect

    from agent.api.inbox import PostgresInboxQueryRepository

    assert "conversation.thread_type" in inspect.getsource(
        PostgresInboxQueryRepository.list_conversations)


# ====================================================================
#  Postgres thật
# ====================================================================

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


def _tin(account_id: UUID, msg_id: str, *, nhom=True, sender="ban-1", ten="Chị Lan",
         ten_nhom="Hội mê skincare", text="shop ơi") -> InboundMessage:
    ad = ZaloPersonalAdapter(account_id=account_id, credentials={"sidecar_secret": "s"})
    if nhom:
        cb = _cb(msg_id=msg_id, sender_id=sender, sender_name=ten, group_name=ten_nhom, text=text)
    else:
        cb = _cb(msg_id=msg_id, thread_id=sender, thread_type=0, is_group=False,
                 group_name="", sender_id=sender, sender_name=ten, text=text)
    m = ad.parse(cb)
    assert m is not None
    return m


async def _tai_khoan():
    from agent import db
    return (await db.fetchrow(
        "INSERT INTO channel_accounts (channel, display_name, status) "
        "VALUES ('zalo_personal', 'Zalo', 'active') RETURNING id"))["id"]


async def _hoi_thoai_tho(acc, kenh: str, ext: str, ref: str | None, *,
                         ten: str = "", loai: int | None = None) -> None:
    """Dòng `conversations` kiểu dữ liệu cũ — `contact_id` là NOT NULL."""
    from agent import db
    kh = await db.fetchrow("INSERT INTO contacts (display_name) VALUES ($1) RETURNING id",
                           ten or "Khách")
    # `contact_point_id` cũng NOT NULL — dòng cũ luôn có điểm liên hệ.
    diem = await db.fetchrow(
        "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
        "VALUES ($1, $2, $3) RETURNING id", kh["id"], acc, ref or ext)
    await db.execute(
        "INSERT INTO conversations (account_id, channel, external_id, customer_ref, "
        "customer_name, thread_type, contact_id, contact_point_id) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
        acc, kenh, ext, ref, ten, loai, kh["id"], diem["id"])


def test_ingest_nhom_hai_nguoi_gui_khong_doi_danh_tinh(csdl):
    from agent import db
    from agent.omnichannel.inbox_service import InboxService, PostgresInboxRepository

    async def chay():
        acc = await _tai_khoan()
        svc = InboxService(PostgresInboxRepository())
        # Chị Lan có cuộc nhắn riêng với shop TRƯỚC — đúng hình dữ liệu thật.
        await svc.ingest(_tin(acc, "r1", nhom=False, sender="ban-1", ten="Chị Lan"))
        kq1 = await svc.ingest(_tin(acc, "g1", sender="ban-1", ten="Chị Lan"))
        kq2 = await svc.ingest(_tin(acc, "g2", sender="ban-2", ten="Anh Tú"))
        # Sidecar hụt tên nhóm một lần: không được đổi tên hội thoại thành dãy số.
        await svc.ingest(_tin(acc, "g3", sender="ban-2", ten="Anh Tú", ten_nhom=""))
        nhom = await db.fetchrow(
            "SELECT customer_name, customer_ref, contact_id, thread_type "
            "FROM conversations WHERE external_id = 'nhom-123456789'")
        rieng = await db.fetchrow(
            "SELECT contact_id FROM conversations WHERE external_id = 'ban-1'")
        tin = await db.fetch(
            "SELECT m.sender_ref, m.sender_name FROM messages m JOIN conversations c "
            "ON c.id = m.conversation_id WHERE c.external_id = 'nhom-123456789' "
            "ORDER BY m.created_at, m.provider_message_id")
        ten_hs = await db.fetchrow("SELECT display_name FROM contacts WHERE id = $1",
                                   nhom["contact_id"])
        ten_rieng = await db.fetchrow("SELECT display_name FROM contacts WHERE id = $1",
                                      rieng["contact_id"])
        return kq1, kq2, dict(nhom), dict(rieng), [(t["sender_ref"], t["sender_name"]) for t in tin], ten_hs, ten_rieng

    kq1, kq2, nhom, rieng, tin, ten_hs, ten_rieng = _chay(csdl, chay)
    assert kq1.conversation_id == kq2.conversation_id
    assert kq1.la_nhom and kq2.la_nhom and not kq1.should_reply
    assert nhom["customer_name"] == "Hội mê skincare"
    assert nhom["customer_ref"] == "group:nhom-123456789"
    assert nhom["thread_type"] == 1
    # Nhóm KHÔNG dính vào contact riêng của Chị Lan.
    assert nhom["contact_id"] != rieng["contact_id"]
    assert ten_hs["display_name"] == "Hội mê skincare"
    assert ten_rieng["display_name"] == "Chị Lan"
    assert tin == [("ban-1", "Chị Lan"), ("ban-2", "Anh Tú"), ("ban-2", "Anh Tú")]


def test_ten_mac_dinh_khong_de_ten_that(csdl):
    """Khách đã có tên thật; tin sau thiếu tên (sidecar/Graph hụt) → giữ tên."""
    from agent import db
    from agent.omnichannel.inbox_service import InboxService, PostgresInboxRepository

    async def chay():
        acc = await _tai_khoan()
        svc = InboxService(PostgresInboxRepository())
        await svc.ingest(_tin(acc, "r1", nhom=False, sender="kh-9", ten="Chị Hoa"))
        await svc.ingest(_tin(acc, "r2", nhom=False, sender="kh-9", ten=""))
        c = await db.fetchrow("SELECT customer_name, contact_id FROM conversations "
                              "WHERE external_id = 'kh-9'")
        k = await db.fetchrow("SELECT display_name FROM contacts WHERE id = $1", c["contact_id"])
        d = await db.fetchrow("SELECT handle FROM contact_points WHERE contact_id = $1",
                              c["contact_id"])
        return c["customer_name"], k["display_name"], d["handle"]

    assert _chay(csdl, chay) == ("Chị Hoa", "Chị Hoa", "Chị Hoa")


def test_hoi_thoai_nhom_cu_chuyen_sang_danh_tinh_nhom_o_tin_ke_tiep(csdl):
    """Dữ liệu cũ: hội thoại nhóm mang tên + contact của một thành viên."""
    from agent import db
    from agent.omnichannel.inbox_service import InboxService, PostgresInboxRepository

    async def chay():
        acc = await _tai_khoan()
        svc = InboxService(PostgresInboxRepository())
        await svc.ingest(_tin(acc, "r1", nhom=False, sender="ban-1", ten="Chị Lan"))
        rieng = await db.fetchrow("SELECT contact_id, contact_point_id FROM conversations "
                                  "WHERE external_id = 'ban-1'")
        await db.execute(
            "INSERT INTO conversations (account_id, channel, external_id, customer_name, "
            "customer_ref, contact_id, contact_point_id) VALUES ($1, 'zalo_personal', "
            "'nhom-123456789', 'Chị Lan', 'ban-1', $2, $3)",
            acc, rieng["contact_id"], rieng["contact_point_id"])
        await svc.ingest(_tin(acc, "g1", sender="ban-2", ten="Anh Tú", ten_nhom=""))
        return dict(await db.fetchrow(
            "SELECT customer_name, customer_ref, contact_id, thread_type FROM conversations "
            "WHERE external_id = 'nhom-123456789'")), rieng["contact_id"]

    nhom, contact_rieng = _chay(csdl, chay)
    # Tên dự phòng đúng hơn tên một thành viên — kể cả khi chưa có tên thật.
    assert nhom["customer_name"] == "Nhóm Zalo …456789"
    assert nhom["customer_ref"] == "group:nhom-123456789"
    assert nhom["contact_id"] != contact_rieng
    assert nhom["thread_type"] == 1


def test_handle_inbound_nhom_AI_khong_chay_khong_nhap_giao_nguoi(csdl, monkeypatch):
    from agent import db
    from agent.omnichannel import tu_dong, xu_ly_tin_vao

    async def cam(*_a, **_k):
        raise AssertionError("AI/kênh/quy tắc tự động không được chạy với tin nhóm")
    monkeypatch.setattr(xu_ly_tin_vao.brain, "respond", cam)
    monkeypatch.setattr(xu_ly_tin_vao.channels, "get_for_account", cam)
    monkeypatch.setattr(xu_ly_tin_vao.thong_bao_ai, "gui_neu_chua", cam)
    monkeypatch.setattr(tu_dong, "chay_tin_khach", cam)

    async def chay():
        acc = await _tai_khoan()
        await xu_ly_tin_vao.handle_inbound(_tin(acc, "g1", sender="ban-1", ten="Chị Lan"))
        await xu_ly_tin_vao.handle_inbound(_tin(acc, "g2", sender="ban-2", ten="Anh Tú"))
        c = await db.fetchrow("SELECT id, status, mode FROM conversations "
                              "WHERE external_id = 'nhom-123456789'")
        dem = await db.fetchrow(
            "SELECT (SELECT count(*) FROM messages WHERE conversation_id = $1 "
            "         AND role <> 'customer') AS may_noi, "
            "       (SELECT count(*) FROM outbox_jobs WHERE conversation_id = $1) AS job, "
            "       (SELECT count(*) FROM cong_viec WHERE conversation_id = $1) AS viec",
            c["id"])
        return dict(c), dict(dem)

    c, dem = _chay(csdl, chay)
    assert (c["status"], c["mode"]) == ("escalated", "human")
    assert dem == {"may_noi": 0, "job": 0, "viec": 1}, "không nháp, không job; MỘT việc cho người"


def test_nhom_da_giai_quyet_co_tin_moi_thi_mo_lai_cho_NGUOI(csdl, monkeypatch):
    from agent import db
    from agent.omnichannel import xu_ly_tin_vao

    async def cam(*_a, **_k):
        raise AssertionError("AI không được chạy với tin nhóm")
    monkeypatch.setattr(xu_ly_tin_vao.brain, "respond", cam)

    async def chay():
        acc = await _tai_khoan()
        await xu_ly_tin_vao.handle_inbound(_tin(acc, "g1"))
        await db.execute(
            "UPDATE conversations SET state = 'resolved', status = 'closed', mode = 'auto', "
            "resolved_at = now()")
        await db.execute("UPDATE cong_viec SET trang_thai = 'xong', xong_luc = now()")
        await xu_ly_tin_vao.handle_inbound(_tin(acc, "g2", sender="ban-3", ten="Bé Na"))
        return dict(await db.fetchrow("SELECT state, status, mode FROM conversations"))

    assert _chay(csdl, chay) == {"state": "open", "status": "escalated", "mode": "human"}


def test_outbox_that_chan_he_thong_noi_vao_nhom_cho_nhan_vien_gui(csdl):
    from agent import db
    from agent.omnichannel.inbox_service import InboxService, PostgresInboxRepository
    from agent.omnichannel.outbound_service import (OutboundBlocked, OutboundService,
                                                    PostgresOutboundRepository)

    async def chay():
        acc = await _tai_khoan()
        kq = await InboxService(PostgresInboxRepository()).ingest(_tin(acc, "g1"))
        svc = OutboundService(PostgresOutboundRepository())
        bi_chan = []
        for vai in ("agent", "system"):
            try:
                await svc.queue_text(conversation_id=kq.conversation_id, role=vai,
                                     text="Dạ em là trợ lý AI", idempotency_key=f"k-{vai}")
            except OutboundBlocked:
                bi_chan.append(vai)
        await svc.queue_text(conversation_id=kq.conversation_id, role="staff",
                             text="Dạ còn ạ", idempotency_key="k-staff")
        job = await db.fetchrow("SELECT count(*) AS n FROM outbox_jobs")
        return bi_chan, job["n"]

    assert _chay(csdl, chay) == (["agent", "system"], 1)


def test_tra_loi_nhom_thread_type_rong_van_gui_dung_loai(csdl):
    """Hội thoại cũ thread_type NULL: suy từ customer_ref, không mặc định 0."""
    from agent import db

    gui: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        gui.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "message_id": "out-1"})

    async def chay():
        acc = await _tai_khoan()
        for ext, ref in (("nhom-cu", "ban-1"), ("nhom-moi", "group:nhom-moi"),
                         ("khach-1", "khach-1")):
            await _hoi_thoai_tho(acc, "zalo_personal", ext, ref)
        # Trước khi gửi: đúng tình trạng production — thread_type còn NULL.
        assert (await db.fetchrow(
            "SELECT count(*) AS n FROM conversations WHERE thread_type IS NULL"))["n"] == 3
        ad = ZaloPersonalAdapter(
            account_id=acc, credentials={"sidecar_secret": "s"},
            client=httpx.AsyncClient(base_url="http://127.0.0.1:3210",
                                     transport=httpx.MockTransport(handler)))
        try:
            for ext in ("nhom-cu", "nhom-moi", "khach-1"):
                await ad.send_text(ext, "Dạ")
        finally:
            await ad.aclose()

    _chay(csdl, chay)
    assert [g["thread_type"] for g in gui] == [1, 1, 0]


def test_migration_0051_danh_dau_nhom_cu_bao_thu(csdl):
    """Chạy lại ĐÚNG tệp migration trên dữ liệu kiểu production."""
    from agent import db

    sql = (ROOT / "agent/migrations/versions/0051_tin_nhom_nguoi_gui.sql").read_text(
        encoding="utf-8")

    async def chay():
        acc = await _tai_khoan()
        dong = {
            "nhom": ("zalo_personal", "383f3b0e-nhom", "ban-1", None),
            "rieng": ("zalo_personal", "khach-1", "khach-1", None),
            "khong_ref": ("zalo_personal", "x-1", None, None),
            "da_co": ("zalo_personal", "nhom-2", "ban-2", 0),
            "kenh_khac": ("facebook", "psid-1", "khac-psid", None),
        }
        for ten, (kenh, ext, ref, loai) in dong.items():
            await _hoi_thoai_tho(acc, kenh, ext, ref, ten=ten, loai=loai)
        await db.execute(sql)
        rows = await db.fetch("SELECT customer_name, thread_type, customer_ref "
                              "FROM conversations")
        cot = await db.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'messages' AND column_name IN ('sender_ref', 'sender_name')")
        return {r["customer_name"]: (r["thread_type"], r["customer_ref"]) for r in rows}, \
            {r["column_name"] for r in cot}

    kq, cot = _chay(csdl, chay)
    assert cot == {"sender_ref", "sender_name"}
    assert kq["nhom"] == (1, "ban-1"), "đánh dấu nhóm nhưng KHÔNG sửa customer_ref"
    assert kq["rieng"][0] == 0
    assert kq["khong_ref"][0] is None, "không đoán được thì để NULL"
    assert kq["da_co"][0] == 0, "không đè giá trị đã có"
    assert kq["kenh_khac"][0] is None, "chỉ đụng zalo_personal"


def test_api_chi_tiet_tra_ten_nguoi_gui_tung_tin(csdl):
    from agent.api.inbox import PostgresInboxQueryRepository
    from agent.omnichannel.inbox_service import InboxService, PostgresInboxRepository

    async def chay():
        acc = await _tai_khoan()
        kq = await InboxService(PostgresInboxRepository()).ingest(_tin(acc, "g1", ten="Chị Lan"))
        repo = PostgresInboxQueryRepository()
        ct = await repo.get_conversation(conversation_id=kq.conversation_id,
                                         user_id=uuid4(), is_admin=True)
        from agent.api.inbox import InboxFilters
        ds = await repo.list_conversations(user_id=uuid4(), is_admin=True,
                                           filters=InboxFilters(None, None, None, None, None, None),
                                           cursor=None, limit=10)
        return ct, ds

    ct, ds = _chay(csdl, chay)
    assert ct["thread_type"] == 1
    assert [m["sender_name"] for m in ct["messages"]] == ["Chị Lan"]
    assert ds[0]["thread_type"] == 1


def test_received_at_khong_doi():
    """Chặn hồi quy vô tình ở phần parse không liên quan."""
    m = _adapter().parse(_cb())
    assert m is not None and m.received_at == datetime.fromtimestamp(1763280000, timezone.utc)
