"""Không để tin đi vào/đi ra sai tài khoản kênh."""
from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timezone
from uuid import uuid4

from agent import main as app_main
from agent.api import routes
from agent.channels.base import InboundMessage, con_trong_cua_so
from agent.omnichannel.inbox_service import InboxIngestResult
from agent.omnichannel.outbound_service import QueuedOutbound


def _inbound(account_id, dedupe_key):
    return InboundMessage(
        account_id=account_id,
        channel="messenger",
        conversation_ref="same-external-id",
        customer_ref="customer-1",
        customer_name="Khách",
        text="Xin chào",
        dedupe_key=dedupe_key,
        received_at=datetime.now(timezone.utc),
        meta={"standby": True},
    )


def test_handle_inbound_dung_inbox_service_truoc_khi_xu_ly_ai(monkeypatch):
    message = _inbound(uuid4(), "m1")
    calls = []

    async def ingest(inbound):
        calls.append(inbound)
        return InboxIngestResult(
            conversation_id=uuid4(),
            conversation_status="auto",
            message_id=None,
            duplicate=True,
            should_reply=False,
        )

    monkeypatch.setattr(app_main, "_ingest_inbound", ingest, raising=False)

    asyncio.run(app_main.handle_inbound(message))

    assert calls == [message]


def test_staff_reply_enqueue_chu_khong_goi_provider_truc_tiep(monkeypatch):
    account_id = uuid4()
    conversation_id = uuid4()
    job_id = uuid4()
    message_id = uuid4()
    calls = []

    async def queue(cid, body):
        calls.append((cid, body.text, body.idempotency_key))
        return QueuedOutbound(
            job_id=job_id,
            message_id=message_id,
            account_id=account_id,
            payload={"conversation_ref": "customer-1", "text": body.text},
        )

    monkeypatch.setattr(routes, "_queue_staff_reply", queue, raising=False)

    result = asyncio.run(
        routes.staff_send(
            str(conversation_id),
            routes.SendBody(text="Đã nhận ạ", idempotency_key="request-1"),
        )
    )

    assert result["ok"] is True
    assert result["queued"] is True
    assert result["job_id"] == str(job_id)
    assert calls == [(conversation_id, "Đã nhận ạ", "request-1")]


def test_approve_draft_enqueue_existing_message(monkeypatch):
    message_id = uuid4()
    account_id = uuid4()
    job_id = uuid4()
    calls = []

    async def queue(mid):
        calls.append(mid)
        return QueuedOutbound(
            job_id=job_id,
            message_id=message_id,
            account_id=account_id,
            payload={"conversation_ref": "customer-1", "text": "Bản nháp"},
        )

    monkeypatch.setattr(routes, "_queue_approved_draft", queue, raising=False)

    result = asyncio.run(routes.approve_draft(str(message_id)))

    assert result == {
        "ok": True,
        "queued": True,
        "job_id": str(job_id),
        "message_id": str(message_id),
        "duplicate": False,
    }
    assert calls == [message_id]


def test_cua_so_gui_chi_doc_tin_cua_dung_account(monkeypatch):
    from agent import db

    account_id = uuid4()
    captured = []

    async def fetchrow(sql, *args):
        captured.append((sql, args))
        return {"lan_cuoi": datetime.now(timezone.utc)}

    monkeypatch.setattr(db, "fetchrow", fetchrow)

    allowed = asyncio.run(
        con_trong_cua_so(
            "messenger",
            "same-external-id",
            24,
            account_id=account_id,
        )
    )

    assert allowed is True
    assert "c.account_id = $1" in captured[0][0]
    assert captured[0][1] == (account_id, "same-external-id")


def test_ai_auto_reply_enqueue_tung_phan_khong_go_provider(monkeypatch):
    account_id = uuid4()
    conversation_id = uuid4()
    message = _inbound(account_id, "provider-message-1")
    queued_calls = []

    class Adapter:
        async def send_text(self, *_args):
            raise AssertionError("AI không được gọi provider trực tiếp")

    async def queue(cid, text, key, metadata=None):
        queued_calls.append((cid, text, key, metadata))
        return QueuedOutbound(
            job_id=uuid4(),
            message_id=uuid4(),
            account_id=account_id,
            payload={"conversation_ref": message.conversation_ref, "text": text},
        )

    monkeypatch.setattr(app_main, "_queue_ai_text", queue, raising=False)
    monkeypatch.setattr(
        app_main.tu_nhien,
        "lam_tu_nhien",
        lambda _text, lan_dau: ["Phần một", "Phần hai"],
    )
    monkeypatch.setattr(app_main, "_la_tin_dau", lambda _cid: _async_value(True))

    result = asyncio.run(
        app_main._gui_nhu_nguoi(Adapter(), message, conversation_id, "Trả lời")
    )

    assert len(result) == 2
    assert [call[1] for call in queued_calls] == ["Phần một", "Phần hai"]
    assert [call[2] for call in queued_calls] == [
        "ai:provider-message-1:part:0",
        "ai:provider-message-1:part:1",
    ]


async def _async_value(value):
    return value


def test_ai_file_va_handover_notice_deu_di_qua_outbox():
    source = inspect.getsource(app_main.handle_inbound)
    handover = inspect.getsource(app_main.bao_khach_dang_chuyen_nguoi)

    assert "_queue_ai_file" in source
    assert "adapter.send_file" not in source
    assert "_queue_handover_notice" in handover
    assert "adapter.send_text" not in handover


def test_handover_notice_chi_queue_sau_khi_kiem_tra_cua_so(monkeypatch):
    conversation_id = uuid4()
    queued = []

    class Adapter:
        async def can_send_now(self, ref):
            assert ref == "customer-1"
            return True

        async def send_text(self, *_args):
            raise AssertionError("handover không được gọi provider trực tiếp")

    async def queue(cid, text):
        queued.append((cid, text))
        return QueuedOutbound(
            job_id=uuid4(),
            message_id=uuid4(),
            account_id=uuid4(),
            payload={"conversation_ref": "customer-1", "text": text},
        )

    monkeypatch.setattr(app_main, "_queue_handover_notice", queue, raising=False)

    asyncio.run(
        app_main.bao_khach_dang_chuyen_nguoi(
            Adapter(), "customer-1", conversation_id
        )
    )

    assert len(queued) == 1
    assert queued[0][0] == conversation_id
