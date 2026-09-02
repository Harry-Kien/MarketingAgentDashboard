"""Webchat first-party: widget token, account isolation và inbound contract."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from agent.api.webchat import issue_widget_token, verify_widget_token
from agent.channels.webchat import WebchatAdapter


def test_widget_token_ky_account_origin_visitor_va_het_han():
    account_id = uuid4()
    visitor_id = uuid4()
    secret = "widget-secret-" + "a" * 32
    token = issue_widget_token(
        secret=secret,
        account_id=account_id,
        visitor_id=visitor_id,
        origin="https://shop.example",
        now=1_787_600_000,
        ttl_seconds=3600,
    )

    claims = verify_widget_token(
        token,
        secret=secret,
        account_id=account_id,
        origin="https://shop.example",
        now=1_787_600_100,
    )

    assert claims["visitor_id"] == str(visitor_id)
    with pytest.raises(ValueError):
        verify_widget_token(
            token + "x",
            secret=secret,
            account_id=account_id,
            origin="https://shop.example",
            now=1_787_600_100,
        )
    with pytest.raises(ValueError, match="origin"):
        verify_widget_token(
            token,
            secret=secret,
            account_id=account_id,
            origin="https://evil.example",
            now=1_787_600_100,
        )
    with pytest.raises(ValueError, match="hết hạn"):
        verify_widget_token(
            token,
            secret=secret,
            account_id=account_id,
            origin="https://shop.example",
            now=1_787_604_000,
        )


def test_webchat_adapter_parse_giu_exact_account_client_message_id():
    account_id = uuid4()
    adapter = WebchatAdapter(
        account_id=account_id,
        credentials={"widget_secret": "x"},
    )

    message = adapter.parse(
        {
            "visitor_id": "visitor-1",
            "client_message_id": "client-1",
            "visitor_name": "An",
            "text": "Cho mình hỏi giá",
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    assert message is not None
    assert message.account_id == account_id
    assert message.channel == "webchat"
    assert message.conversation_ref == "visitor-1"
    assert message.dedupe_key == "webchat:client-1"


def test_webchat_adapter_tu_choi_payload_khong_co_idempotency():
    adapter = WebchatAdapter(
        account_id=uuid4(),
        credentials={"widget_secret": "x"},
    )
    assert adapter.parse({"visitor_id": "v1", "text": "xin chào"}) is None
def test_webchat_chi_verify_khi_widget_secret_du_manh():
    weak = WebchatAdapter(account_id=uuid4(), credentials={"widget_secret": "short"})
    strong = WebchatAdapter(account_id=uuid4(), credentials={"widget_secret": "x" * 32})

    assert asyncio.run(weak.verify_connection()).ok is False
    assert asyncio.run(strong.verify_connection()).ok is True
