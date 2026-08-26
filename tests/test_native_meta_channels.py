"""Fixtures đã khử bí mật cho Instagram và WhatsApp native."""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import httpx

from agent.channels.meta_channels import InstagramAdapter, WhatsAppAdapter


def test_instagram_parser_giu_exact_account_va_khong_bo_tin_anh():
    account_id = uuid4()
    adapter = InstagramAdapter(
        account_id=account_id,
        credentials={
            "access_token": "ig-token",
            "app_secret": "app-secret",
            "instagram_id": "ig-business-1",
        },
    )
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "ig-business-1",
                "messaging": [
                    {
                        "sender": {"id": "customer-1"},
                        "recipient": {"id": "ig-business-1"},
                        "timestamp": 1787600000000,
                        "message": {
                            "mid": "ig-mid-1",
                            "attachments": [
                                {
                                    "type": "image",
                                    "payload": {"url": "https://cdn.example/a.jpg"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    messages = adapter.parse_nhieu(payload)

    assert len(messages) == 1
    assert messages[0].account_id == account_id
    assert messages[0].channel == "instagram"
    assert messages[0].dedupe_key == "instagram:ig-mid-1"
    assert messages[0].attachments[0]["url"] == "https://cdn.example/a.jpg"
    asyncio.run(adapter.aclose())


def test_whatsapp_parser_batch_text_media_va_delivery_status_khong_thanh_inbound():
    account_id = uuid4()
    adapter = WhatsAppAdapter(
        account_id=account_id,
        credentials={
            "access_token": "wa-token",
            "app_secret": "app-secret",
            "phone_number_id": "phone-1",
        },
    )
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "phone-1"},
                            "contacts": [
                                {"wa_id": "8490111222", "profile": {"name": "An"}}
                            ],
                            "messages": [
                                {
                                    "id": "wamid.text",
                                    "from": "8490111222",
                                    "timestamp": "1787600000",
                                    "type": "text",
                                    "text": {"body": "Xin chào"},
                                },
                                {
                                    "id": "wamid.image",
                                    "from": "8490111222",
                                    "timestamp": "1787600001",
                                    "type": "image",
                                    "image": {"id": "media-1", "mime_type": "image/jpeg"},
                                },
                            ],
                            "statuses": [{"id": "outbound-1", "status": "delivered"}],
                        },
                    }
                ],
            }
        ],
    }

    messages = adapter.parse_nhieu(payload)

    assert [message.dedupe_key for message in messages] == [
        "whatsapp:wamid.text",
        "whatsapp:wamid.image",
    ]
    assert messages[0].text == "Xin chào"
    assert messages[1].attachments[0]["provider_media_id"] == "media-1"
    assert all(message.account_id == account_id for message in messages)
    asyncio.run(adapter.aclose())


def test_whatsapp_send_text_dung_phone_id_token_va_tra_provider_message_id():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"messages": [{"id": "wamid.outbound-1"}]},
        )

    client = httpx.AsyncClient(
        base_url="https://graph.example/v1",
        transport=httpx.MockTransport(handler),
    )
    adapter = WhatsAppAdapter(
        account_id=uuid4(),
        credentials={
            "access_token": "wa-token-A",
            "app_secret": "app-secret",
            "phone_number_id": "phone-A",
        },
        client=client,
    )

    delivery = asyncio.run(adapter.send_text("8490111222", "Đã nhận ạ"))

    assert delivery.ok is True
    assert delivery.provider_message_id == "wamid.outbound-1"
    assert requests[0].url.path.endswith("/phone-A/messages")
    assert requests[0].headers["authorization"] == "Bearer wa-token-A"
    assert json.loads(requests[0].content)["to"] == "8490111222"
    asyncio.run(adapter.aclose())


def test_meta_verify_connection_doc_identity_ma_khong_gui_tin():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer token-A"
        return httpx.Response(200, json={"id": "ig-verified", "name": "Instagram CSKH"})

    client = httpx.AsyncClient(
        base_url="https://graph.example/v1",
        transport=httpx.MockTransport(handler),
    )
    adapter = InstagramAdapter(
        account_id=uuid4(),
        credentials={"access_token": "token-A", "external_account_id": "pending:x"},
        client=client,
    )

    check = asyncio.run(adapter.verify_connection())

    assert check.ok is True
    assert check.external_account_id == "ig-verified"
    asyncio.run(adapter.aclose())
