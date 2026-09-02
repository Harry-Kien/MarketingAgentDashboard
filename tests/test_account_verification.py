from __future__ import annotations

import asyncio
from dataclasses import replace
from uuid import uuid4

from agent.channels.base import ConnectionCheck
from agent.omnichannel.account_verification import NativeConnectionVerifier
from agent.omnichannel.accounts import AccountStatus, Channel, ChannelAccount


class _Repository:
    def __init__(self, account):
        self.account = account
        self.health = []
        self.identities = []
        self.statuses = []

    async def get(self, account_id):
        return self.account if account_id == self.account.id else None

    async def record_health(self, account_id, **kwargs):
        self.health.append((account_id, kwargs))

    async def bind_external_identity(self, account_id, external_id, *, actor_id):
        self.identities.append((account_id, external_id, actor_id))

    async def update_status(self, account_id, status, *, actor_id):
        self.statuses.append((account_id, status, actor_id))
        self.account = replace(self.account, status=status)
        return self.account


class _Adapter:
    def __init__(self, result):
        self.result = result
        self.closed = False

    async def verify_connection(self):
        return self.result

    async def aclose(self):
        self.closed = True


def _account():
    return ChannelAccount(
        id=uuid4(), channel=Channel.FACEBOOK, display_name="Page Hà Nội",
        external_account_id="pending:test", status=AccountStatus.PENDING,
        capabilities={}, metadata={}, is_legacy=False,
    )


def test_verify_thanh_cong_moi_bind_identity_va_active():
    account = _account()
    repository = _Repository(account)
    adapter = _Adapter(ConnectionCheck(True, "provider.ok", "page-123", {"name": "Page"}))
    actor = uuid4()
    verifier = NativeConnectionVerifier(repository, lambda _account: adapter)

    result = asyncio.run(verifier.verify(account.id, actor_id=actor))

    assert result.ok is True
    assert repository.identities == [(account.id, "page-123", actor)]
    assert repository.statuses[-1][1] == AccountStatus.ACTIVE
    assert repository.health[-1][1]["status"] == AccountStatus.ACTIVE
    assert adapter.closed is True


def test_verify_that_bai_degraded_va_khong_bind_identity():
    account = _account()
    repository = _Repository(account)
    adapter = _Adapter(ConnectionCheck(False, "provider.unauthorized", None, {}))
    verifier = NativeConnectionVerifier(repository, lambda _account: adapter)

    result = asyncio.run(verifier.verify(account.id, actor_id=uuid4()))

    assert result.ok is False
    assert repository.identities == []
    assert repository.statuses[-1][1] == AccountStatus.REAUTH_REQUIRED
    assert repository.health[-1][1]["code"] == "provider.unauthorized"
    assert adapter.closed is True
