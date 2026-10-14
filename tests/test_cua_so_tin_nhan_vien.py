"""
Tin NHÂN VIÊN ngoài cửa sổ nhắn tin không được chết im lặng.

LỖ ĐO ĐƯỢC 14.10.2026
---------------------
Agent tự gửi và thông báo chuyển người đều hỏi `can_send_now()` trước khi
xếp hàng (`agent/main.py`). Tin nhân viên thì không: người trực trả lời một
khách nhắn từ hôm qua, tin vào outbox với `messaging_type: RESPONSE`, Meta
từ chối, outbox thử lại tám lần rồi `dead`. Trên màn hình tin hiện như đã
gửi; khách không bao giờ nhận được; không ai biết.

Giờ: trong cửa sổ → gửi như cũ. Ngoài 24 giờ, kênh Meta, đã được duyệt
Human Agent và còn trong 7 ngày → gắn thẻ HUMAN_AGENT. Còn lại → 409 với lời
giải thích, KHÔNG xếp hàng.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from agent.omnichannel import cua_so_gui as cs


class _AdapterGia:
    def __init__(self, name: str, trong: bool):
        self.name = name
        self.account_id = uuid.uuid4()
        self._trong = trong

    async def can_send_now(self, ref: str) -> bool:
        return self._trong


@pytest.fixture
def gia(monkeypatch):
    hop = {"adapter": None, "trong_7_ngay": True, "loi_adapter": False}

    async def fetchrow(sql, *a):
        return {"account_id": uuid.uuid4(), "channel": hop["adapter"].name,
                "external_id": "psid-1"}

    async def get_for_account(_id):
        if hop["loi_adapter"]:
            raise RuntimeError("chưa cấu hình kênh")
        return hop["adapter"]

    async def con_trong_cua_so(channel, ref, gio, *, account_id=None):
        assert gio == cs.GIO_HUMAN_AGENT
        return hop["trong_7_ngay"]

    monkeypatch.setattr(cs.db, "fetchrow", fetchrow)
    monkeypatch.setattr(cs, "get_for_account", get_for_account)
    monkeypatch.setattr(cs, "con_trong_cua_so", con_trong_cua_so)
    return hop


def _xet():
    return asyncio.run(cs.xet_tin_nhan_vien(uuid.uuid4()))


def test_trong_cua_so_gui_binh_thuong(gia):
    gia["adapter"] = _AdapterGia("messenger", trong=True)
    qd = _xet()
    assert qd.duoc and qd.the is None


def test_ngoai_24h_chua_duyet_human_agent_thi_409(gia, monkeypatch):
    monkeypatch.setattr(cs.settings, "meta_the_human_agent", False)
    gia["adapter"] = _AdapterGia("messenger", trong=False)
    qd = _xet()
    assert not qd.duoc and "Human Agent" in qd.ly_do


def test_ngoai_24h_da_duyet_trong_7_ngay_gan_the(gia, monkeypatch):
    monkeypatch.setattr(cs.settings, "meta_the_human_agent", True)
    for kenh in ("messenger", "facebook", "instagram"):
        gia["adapter"] = _AdapterGia(kenh, trong=False)
        qd = _xet()
        assert qd.duoc and qd.the == "HUMAN_AGENT", kenh


def test_qua_7_ngay_thi_khong_gui_duoc(gia, monkeypatch):
    monkeypatch.setattr(cs.settings, "meta_the_human_agent", True)
    gia["adapter"] = _AdapterGia("messenger", trong=False)
    gia["trong_7_ngay"] = False
    qd = _xet()
    assert not qd.duoc and "7 ngày" in qd.ly_do


def test_kenh_khac_ngoai_cua_so_thi_409(gia, monkeypatch):
    monkeypatch.setattr(cs.settings, "meta_the_human_agent", True)
    gia["adapter"] = _AdapterGia("zalo_oa", trong=False)
    qd = _xet()
    assert not qd.duoc and qd.ly_do


def test_khong_dung_duoc_adapter_thi_de_worker_bao_loi(gia):
    """
    Không dựng được adapter ở API thì worker cũng không dựng được, và job
    sẽ thất bại có ghi lỗi. Chặn ở đây là chặn luôn kênh đang cấu hình dở —
    người trực không gửi được gì mà không biết vì sao.
    """
    gia["adapter"] = _AdapterGia("messenger", trong=False)
    gia["loi_adapter"] = True
    assert _xet().duoc


# ---------------- thẻ đi tới tận Meta ----------------

def test_messenger_gan_the_vao_body(monkeypatch):
    from agent.channels.messenger import MessengerAdapter

    ad = MessengerAdapter.__new__(MessengerAdapter)
    gui = {}

    async def _gui(body):
        gui.update(body)
        from agent.channels.base import Delivery
        return Delivery(True)

    ad.cau_hinh_du = lambda: True
    ad._gui = _gui
    asyncio.run(ad.send_text("psid", "chào", the="HUMAN_AGENT"))
    assert gui["messaging_type"] == "MESSAGE_TAG" and gui["tag"] == "HUMAN_AGENT"
    gui.clear()
    asyncio.run(ad.send_text("psid", "chào"))
    assert gui["messaging_type"] == "RESPONSE" and "tag" not in gui


def test_worker_truyen_the_xuong_adapter():
    from agent.workers.outbox_worker import OutboxProcessor

    goi = {}

    class _Ad:
        async def send_text(self, ref, text, **kw):
            goi.update(ref=ref, text=text, **kw)

    class _Job:
        kind = "send_text"
        payload = {"conversation_ref": "r", "text": "t", "the": "HUMAN_AGENT"}

    asyncio.run(OutboxProcessor._deliver(_Ad(), _Job()))
    assert goi["the"] == "HUMAN_AGENT"

    class _JobCu:
        kind = "send_text"
        payload = {"conversation_ref": "r", "text": "t"}

    class _AdCu:
        """Adapter không biết thẻ — job cũ không có thẻ vẫn phải gửi được."""
        async def send_text(self, ref, text):
            goi.update(cu=True)

    asyncio.run(OutboxProcessor._deliver(_AdCu(), _JobCu()))
    assert goi["cu"]


def test_route_ngoai_cua_so_tra_409_khong_xep_hang():
    """Ba đường gửi tin của người đều đi qua cùng một phép xét."""
    import inspect

    from agent.api import routes

    for ham in (routes.staff_send, routes.staff_send_file, routes.approve_draft):
        assert "xet_tin_nhan_vien" in inspect.getsource(ham), ham.__name__
