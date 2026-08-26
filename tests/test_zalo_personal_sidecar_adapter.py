"""Zalo cá nhân native gọi sidecar bằng HMAC và giữ account isolation."""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import httpx

from agent.api.zalo_personal_webhook import (
    provider_identity_from_health,
    verify_sidecar_callback,
)
from agent.channels.zalo_personal import ZaloPersonalAdapter


def test_parse_inbound_sidecar_gan_dung_account_va_media():
    account_id = uuid4()
    adapter = ZaloPersonalAdapter(
        account_id=account_id,
        credentials={"sidecar_url": "http://127.0.0.1:3210", "sidecar_secret": "x"},
    )
    message = adapter.parse(
        {
            "event": "message",
            "message": {
                "msg_id": "zalo-msg-1",
                "thread_id": "customer-1",
                "sender_id": "customer-1",
                "sender_name": "An",
                "text": "",
                "timestamp": 1787600000000,
                "attachments": [
                    {"type": "image", "url": "https://cdn.example/a.jpg"}
                ],
            },
        }
    )

    assert message is not None
    assert message.account_id == account_id
    assert message.channel == "zalo_personal"
    assert message.dedupe_key == "zalo_personal:zalo-msg-1"
    assert message.attachments[0]["url"] == "https://cdn.example/a.jpg"
    asyncio.run(adapter.aclose())


def test_send_text_ky_hmac_account_path_va_tra_provider_id():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["x-sidecar-signature"].startswith("sha256=")
        assert request.headers["x-sidecar-timestamp"]
        assert request.headers["x-sidecar-nonce"]
        return httpx.Response(200, json={"ok": True, "message_id": "zalo-out-1"})

    account_id = uuid4()
    client = httpx.AsyncClient(
        base_url="http://127.0.0.1:3210",
        transport=httpx.MockTransport(handler),
    )
    adapter = ZaloPersonalAdapter(
        account_id=account_id,
        credentials={
            "sidecar_url": "http://127.0.0.1:3210",
            "sidecar_secret": "sidecar-secret-A",
        },
        client=client,
    )

    delivery = asyncio.run(adapter.send_text("customer-1", "Xin chào"))

    assert delivery.ok is True
    assert delivery.provider_message_id == "zalo-out-1"
    assert requests[0].url.path == f"/v1/accounts/{account_id}/send-text"
    assert json.loads(requests[0].content)["thread_id"] == "customer-1"
    asyncio.run(adapter.aclose())


def test_callback_hmac_chong_replay_va_body_bi_sua():
    import hashlib
    import hmac

    secret = "sidecar-secret-" + "a" * 24
    account_id = uuid4()
    path = f"/webhook/native/zalo-personal/{account_id}"
    body = b'{"event":"health","data":{"status":"connected"}}'
    timestamp = "1787600000"
    nonce = "nonce-1"
    canonical = b".".join(
        [timestamp.encode(), nonce.encode(), b"POST", path.encode(), body]
    )
    signature = "sha256=" + hmac.new(
        secret.encode(), canonical, hashlib.sha256
    ).hexdigest()
    headers = {
        "x-sidecar-timestamp": timestamp,
        "x-sidecar-nonce": nonce,
        "x-sidecar-signature": signature,
    }
    seen = {}

    assert verify_sidecar_callback(
        secret, path, body, headers, seen, now=1787600000
    )
    assert not verify_sidecar_callback(
        secret, path, body, headers, seen, now=1787600000
    )
    assert not verify_sidecar_callback(
        secret, path, body + b"x", {**headers, "x-sidecar-nonce": "nonce-2"}, {},
        now=1787600000,
    )


def test_health_chi_bind_provider_identity_khi_da_connected():
    assert provider_identity_from_health({"status": "connected", "own_id": " 12345 "}) == "12345"
    assert provider_identity_from_health({"status": "disconnected", "own_id": "12345"}) is None
    assert provider_identity_from_health({"status": "connected", "own_id": ""}) is None


def test_sidecar_verify_connection_can_connected_va_own_id():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "status": "connected", "own_id": "zalo-42"})

    client = httpx.AsyncClient(
        base_url="http://127.0.0.1:3210",
        transport=httpx.MockTransport(handler),
    )
    adapter = ZaloPersonalAdapter(
        account_id=uuid4(),
        credentials={"sidecar_url": "http://127.0.0.1:3210", "sidecar_secret": "x"},
        client=client,
    )

    check = asyncio.run(adapter.verify_connection())

    assert check.ok is True
    assert check.external_account_id == "zalo-42"
    asyncio.run(adapter.aclose())
