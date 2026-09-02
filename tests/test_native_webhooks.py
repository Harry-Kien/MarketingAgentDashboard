"""Webhook Meta fan-out đúng account khi một app nối nhiều tài khoản."""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from uuid import uuid4

from fastapi import HTTPException

from agent.api.native_webhooks import MetaWebhookDispatcher, extract_meta_targets
from agent.channels.base import InboundMessage
from agent.omnichannel.accounts import AccountStatus, Channel, ChannelAccount


def _account(channel, external_id):
    return ChannelAccount(
        id=uuid4(),
        channel=channel,
        display_name=external_id,
        external_account_id=external_id,
        status=AccountStatus.ACTIVE,
        capabilities={},
        metadata={},
        is_legacy=False,
    )


def test_extract_targets_cho_facebook_instagram_whatsapp():
    assert extract_meta_targets(
        {"object": "page", "entry": [{"id": "page-1"}, {"id": "page-2"}]}
    ) == (Channel.FACEBOOK, {"page-1", "page-2"})
    assert extract_meta_targets(
        {"object": "instagram", "entry": [{"id": "ig-1"}]}
    ) == (Channel.INSTAGRAM, {"ig-1"})
    assert extract_meta_targets(
        {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {"value": {"metadata": {"phone_number_id": "phone-1"}}}
                    ]
                }
            ],
        }
    ) == (Channel.WHATSAPP, {"phone-1"})


def test_dispatch_batch_hai_page_chi_parse_bang_adapter_tuong_ung():
    first = _account(Channel.FACEBOOK, "page-1")
    second = _account(Channel.FACEBOOK, "page-2")

    class Accounts:
        async def find_active_by_external_ids(self, channel, external_ids):
            assert channel == Channel.FACEBOOK
            assert external_ids == {"page-1", "page-2"}
            return [first, second]

    @dataclass
    class Adapter:
        account: ChannelAccount

        def verify_signature(self, raw, signature):
            return signature == "sha256=valid"

        def parse_nhieu(self, payload):
            return [
                InboundMessage(
                    account_id=self.account.id,
                    channel="facebook",
                    conversation_ref=f"customer-{self.account.external_account_id}",
                    customer_ref="customer",
                    customer_name="Khách",
                    text="Xin chào",
                    dedupe_key=f"m:{self.account.external_account_id}",
                    received_at=__import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ),
                )
            ]

    class Factory:
        async def create(self, account_id):
            account = first if account_id == first.id else second
            return Adapter(account)

    payload = {"object": "page", "entry": [{"id": "page-1"}, {"id": "page-2"}]}
    raw = json.dumps(payload).encode()
    messages = asyncio.run(
        MetaWebhookDispatcher(Accounts(), Factory()).dispatch(
            raw_body=raw,
            signature="sha256=valid",
            payload=payload,
        )
    )

    assert {message.account_id for message in messages} == {first.id, second.id}


def test_dispatch_signature_sai_fail_closed_truoc_ingest():
    account = _account(Channel.INSTAGRAM, "ig-1")

    class Accounts:
        async def find_active_by_external_ids(self, channel, external_ids):
            return [account]

    class Adapter:
        def verify_signature(self, raw, signature):
            return False

        def parse_nhieu(self, payload):
            raise AssertionError("không được parse payload chưa xác thực")

    class Factory:
        async def create(self, account_id):
            return Adapter()

    payload = {"object": "instagram", "entry": [{"id": "ig-1"}]}
    with __import__("pytest").raises(HTTPException) as exc:
        asyncio.run(
            MetaWebhookDispatcher(Accounts(), Factory()).dispatch(
                raw_body=b"{}",
                signature="bad",
                payload=payload,
            )
        )
    assert exc.value.status_code == 401


def test_callback_theo_account_xac_minh_get_va_chan_payload_nham_account():
    account = _account(Channel.FACEBOOK, "page-1")

    class Accounts:
        async def get(self, account_id):
            return account if account_id == account.id else None

    class Adapter:
        def verify_challenge(self, params):
            if params.get("hub.verify_token") == "verify-1":
                return params.get("hub.challenge")
            return None

        def verify_signature(self, raw, signature):
            return signature == "sha256=valid"

        def parse_nhieu(self, payload):
            return ["parsed"]

    class Factory:
        async def create(self, account_id):
            assert account_id == account.id
            return Adapter()

    dispatcher = MetaWebhookDispatcher(Accounts(), Factory())

    challenge = asyncio.run(
        dispatcher.verify_account_challenge(
            account.id,
            {"hub.mode": "subscribe", "hub.verify_token": "verify-1", "hub.challenge": "99"},
        )
    )
    assert challenge == "99"

    wrong_payload = {"object": "page", "entry": [{"id": "page-2"}]}
    with __import__("pytest").raises(HTTPException) as exc:
        asyncio.run(
            dispatcher.dispatch_account(
                account_id=account.id,
                raw_body=json.dumps(wrong_payload).encode(),
                signature="sha256=valid",
                payload=wrong_payload,
            )
        )
    assert exc.value.status_code == 422
