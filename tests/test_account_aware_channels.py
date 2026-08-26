"""Hợp đồng định tuyến kênh theo đúng tài khoản nguồn."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from agent.channels.base import InboundMessage, legacy_account_id
from agent.channels.factory import AccountAdapterFactory, AccountAdapterNotFound
from agent.channels.messenger import MessengerAdapter
from agent.channels.meta_channels import InstagramAdapter, WhatsAppAdapter
from agent.channels.webchat import WebchatAdapter
from agent.channels.zalo_personal import ZaloPersonalAdapter
from agent.omnichannel.accounts import AccountStatus, Channel, ChannelAccount


class _AccountRepository:
    def __init__(self, account=None):
        self.account = account

    async def get(self, account_id):
        if self.account and self.account.id == account_id:
            return self.account
        return None


class _Credentials:
    def __init__(self, values=None):
        self.values = values or {}

    async def load(self, account_id):
        return self.values.get(account_id)


def test_inbound_message_bat_buoc_co_account_id():
    """Thiếu account nguồn phải hỏng ồn ào thay vì reply qua nick mặc định."""
    with pytest.raises(TypeError):
        InboundMessage(
            channel="facebook",
            conversation_ref="c1",
            customer_ref="u1",
            customer_name="An",
            text="Chào",
            dedupe_key="m1",
            received_at=datetime.now(timezone.utc),
        )


def test_legacy_account_id_on_dinh_giua_cac_lan_khoi_dong():
    assert legacy_account_id("messenger") == legacy_account_id("messenger")
    assert legacy_account_id("messenger") != legacy_account_id("zalo_oa")


def test_adapter_gan_account_id_vao_moi_tin_inbound():
    account_id = uuid4()
    adapter = MessengerAdapter(account_id=account_id)
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-1",
                "messaging": [
                    {
                        "sender": {"id": "customer-1"},
                        "recipient": {"id": "page-1"},
                        "timestamp": 1735689600000,
                        "message": {"mid": "m1", "text": "Xin chào"},
                    }
                ],
            }
        ],
    }

    message = adapter.parse_nhieu(payload)[0]

    assert message.account_id == account_id
    asyncio.run(adapter.aclose())


def test_factory_resolve_legacy_adapter_dung_account():
    account = ChannelAccount(
        id=uuid4(),
        channel=Channel.LEGACY_MESSENGER,
        display_name="Messenger cũ",
        external_account_id="legacy:messenger",
        status=AccountStatus.ACTIVE,
        capabilities={},
        metadata={},
        is_legacy=True,
    )

    adapter = asyncio.run(AccountAdapterFactory(_AccountRepository(account)).create(account.id))

    assert adapter.name == "messenger"
    assert adapter.account_id == account.id
    asyncio.run(adapter.aclose())


def test_factory_khong_fallback_khi_account_id_sai():
    with pytest.raises(AccountAdapterNotFound):
        asyncio.run(AccountAdapterFactory(_AccountRepository()).create(uuid4()))


def test_factory_chan_account_bi_disable():
    account = ChannelAccount(
        id=uuid4(),
        channel=Channel.LEGACY_MESSENGER,
        display_name="Messenger cũ",
        external_account_id="legacy:messenger",
        status=AccountStatus.DISABLED,
        capabilities={},
        metadata={},
        is_legacy=True,
    )

    with pytest.raises(AccountAdapterNotFound, match="không hoạt động"):
        asyncio.run(AccountAdapterFactory(_AccountRepository(account)).create(account.id))


def test_factory_native_facebook_hai_account_khong_dung_lan_token():
    first = ChannelAccount(
        id=uuid4(),
        channel=Channel.FACEBOOK,
        display_name="Page A",
        external_account_id="page-a",
        status=AccountStatus.ACTIVE,
        capabilities={},
        metadata={},
        is_legacy=False,
    )
    second = ChannelAccount(
        id=uuid4(),
        channel=Channel.FACEBOOK,
        display_name="Page B",
        external_account_id="page-b",
        status=AccountStatus.ACTIVE,
        capabilities={},
        metadata={},
        is_legacy=False,
    )
    credentials = _Credentials(
        {
            first.id: {"access_token": "token-a", "app_secret": "secret-a"},
            second.id: {"access_token": "token-b", "app_secret": "secret-b"},
        }
    )

    adapter_a = asyncio.run(
        AccountAdapterFactory(_AccountRepository(first), credentials).create(first.id)
    )
    adapter_b = asyncio.run(
        AccountAdapterFactory(_AccountRepository(second), credentials).create(second.id)
    )

    assert adapter_a.account_id == first.id
    assert adapter_b.account_id == second.id
    assert adapter_a._page_token == "token-a"
    assert adapter_b._page_token == "token-b"
    assert adapter_a._page_token != adapter_b._page_token
    asyncio.run(adapter_a.aclose())
    asyncio.run(adapter_b.aclose())


def test_factory_native_thieu_credential_thi_fail_closed():
    account = ChannelAccount(
        id=uuid4(),
        channel=Channel.ZALO_OA,
        display_name="OA A",
        external_account_id="oa-a",
        status=AccountStatus.ACTIVE,
        capabilities={},
        metadata={},
        is_legacy=False,
    )

    with pytest.raises(AccountAdapterNotFound, match="credential"):
        asyncio.run(
            AccountAdapterFactory(_AccountRepository(account), _Credentials()).create(
                account.id
            )
        )


@pytest.mark.parametrize(
    ("channel", "adapter_type"),
    [
        (Channel.INSTAGRAM, InstagramAdapter),
        (Channel.WHATSAPP, WhatsAppAdapter),
        (Channel.ZALO_PERSONAL, ZaloPersonalAdapter),
        (Channel.WEBCHAT, WebchatAdapter),
    ],
)
def test_factory_kich_hoat_du_cac_connector_native(channel, adapter_type):
    account = ChannelAccount(
        id=uuid4(),
        channel=channel,
        display_name=f"Native {channel.value}",
        external_account_id=f"external-{channel.value}",
        status=AccountStatus.ACTIVE,
        capabilities={},
        metadata={},
        is_legacy=False,
    )
    credentials = _Credentials(
        {
            account.id: {
                "access_token": "token",
                "app_secret": "s" * 32,
                "sidecar_secret": "s" * 32,
                "widget_secret": "s" * 32,
            }
        }
    )

    adapter = asyncio.run(
        AccountAdapterFactory(_AccountRepository(account), credentials).create(
            account.id
        )
    )

    assert isinstance(adapter, adapter_type)
    assert adapter.account_id == account.id
    asyncio.run(adapter.aclose())
