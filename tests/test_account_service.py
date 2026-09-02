"""Hành vi nghiệp vụ khi quản trị nhiều tài khoản kênh."""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from agent.omnichannel.account_service import (
    AccountActor,
    AccountAlreadyExists,
    AccountDisabled,
    AccountPermissionDenied,
    ChannelAccountService,
    CreateAccountCommand,
)
from agent.omnichannel.accounts import AccountStatus, Channel, ChannelAccount
from agent.security.credential_vault import CredentialVault, SealedCredential


class _AccountsInMemory:
    """Repository bộ nhớ giữ hiệu ứng thật của service, không gọi mạng/CSDL."""

    def __init__(self):
        self.accounts: dict[UUID, ChannelAccount] = {}
        self.secrets: dict[UUID, SealedCredential] = {}
        self.audits: list[dict] = []

    async def find_by_external(self, channel: Channel, external_account_id: str | None):
        return next(
            (
                account
                for account in self.accounts.values()
                if account.channel == channel
                and account.external_account_id == external_account_id
            ),
            None,
        )

    async def create(
        self,
        account: ChannelAccount,
        sealed: SealedCredential | None,
        *,
        actor_id: UUID,
    ):
        self.accounts[account.id] = account
        if sealed:
            self.secrets[account.id] = sealed
        self.audits.append(
            {"kind": "channel_account.created", "account_id": account.id, "actor": actor_id}
        )
        return account

    async def get(self, account_id: UUID):
        return self.accounts.get(account_id)

    async def has_credentials(self, account_id: UUID):
        return account_id in self.secrets

    async def store_credentials(
        self,
        account_id: UUID,
        sealed: SealedCredential,
        *,
        actor_id: UUID,
    ):
        self.secrets[account_id] = sealed
        self.audits.append(
            {"kind": "channel_account.credentials_rotated", "account_id": account_id}
        )

    async def update_status(
        self,
        account_id: UUID,
        status: AccountStatus,
        *,
        actor_id: UUID,
    ):
        old = self.accounts[account_id]
        updated = ChannelAccount(
            id=old.id,
            channel=old.channel,
            display_name=old.display_name,
            external_account_id=old.external_account_id,
            status=status,
            capabilities=old.capabilities,
            metadata=old.metadata,
            is_legacy=old.is_legacy,
            created_at=old.created_at,
            updated_at=old.updated_at,
        )
        self.accounts[account_id] = updated
        self.audits.append(
            {"kind": "channel_account.status_changed", "account_id": account_id}
        )
        return updated


def _service(repository: _AccountsInMemory) -> ChannelAccountService:
    vault = CredentialVault({1: bytes.fromhex("01" * 32)}, active_version=1)
    return ChannelAccountService(repository, vault)


def _admin() -> AccountActor:
    return AccountActor(user_id=uuid4(), role="quan_tri")


def _command() -> CreateAccountCommand:
    return CreateAccountCommand(
        channel=Channel.ZALO_OA,
        display_name="OA Hà Nội",
        external_account_id="oa-1",
        capabilities={"send_text": True},
        metadata={},
        credentials={"access_token": "secret"},
    )


def test_create_account_ma_hoa_bi_mat_va_audit_khong_lo_token():
    repository = _AccountsInMemory()

    created = asyncio.run(_service(repository).create_account(_command(), actor=_admin()))

    assert created.channel == Channel.ZALO_OA
    assert asyncio.run(repository.has_credentials(created.id)) is True
    assert b"secret" not in repository.secrets[created.id].ciphertext
    assert "secret" not in repr(repository.audits)


def test_trung_external_account_bi_tu_choi():
    repository = _AccountsInMemory()
    service = _service(repository)
    admin = _admin()
    asyncio.run(service.create_account(_command(), actor=admin))

    with pytest.raises(AccountAlreadyExists):
        asyncio.run(service.create_account(_command(), actor=admin))

    assert len(repository.accounts) == 1


def test_co_the_tao_nhieu_account_chua_biet_provider_id():
    repository = _AccountsInMemory()
    service = _service(repository)
    admin = _admin()
    command = CreateAccountCommand(
        channel=Channel.ZALO_PERSONAL,
        display_name="Zalo chờ đăng nhập",
        external_account_id=None,
        capabilities={},
        metadata={},
        credentials={"sidecar_secret": "s" * 32},
    )

    first = asyncio.run(service.create_account(command, actor=admin))
    second = asyncio.run(service.create_account(command, actor=admin))

    assert first.external_account_id.startswith("pending:")
    assert second.external_account_id.startswith("pending:")
    assert first.external_account_id != second.external_account_id


def test_nhan_vien_khong_duoc_xoay_credential():
    repository = _AccountsInMemory()
    service = _service(repository)
    account = asyncio.run(service.create_account(_command(), actor=_admin()))
    staff = AccountActor(user_id=uuid4(), role="nhan_vien")

    with pytest.raises(AccountPermissionDenied):
        asyncio.run(
            service.rotate_credentials(
                account.id,
                {"access_token": "new-secret"},
                actor=staff,
            )
        )


def test_disable_account_chan_moi_duong_gui():
    repository = _AccountsInMemory()
    service = _service(repository)
    admin = _admin()
    account = asyncio.run(service.create_account(_command(), actor=admin))
    asyncio.run(service.enable_account(account.id, actor=admin))
    assert asyncio.run(service.require_sendable(account.id)).id == account.id

    asyncio.run(service.disable_account(account.id, actor=admin))

    with pytest.raises(AccountDisabled):
        asyncio.run(service.require_sendable(account.id))
