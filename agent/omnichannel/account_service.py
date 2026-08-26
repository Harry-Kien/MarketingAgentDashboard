"""Luật nghiệp vụ quản trị tài khoản kênh và credential của chúng."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import UUID, uuid4

from agent.security.credential_vault import CredentialVault, SealedCredential

from .accounts import (
    AccountStatus,
    Channel,
    ChannelAccount,
    kiem_metadata_khong_bi_mat,
)


class AccountServiceError(RuntimeError):
    """Lỗi nghiệp vụ public của account service."""


class AccountAlreadyExists(AccountServiceError):
    pass


class AccountNotFound(AccountServiceError):
    pass


class AccountPermissionDenied(AccountServiceError):
    pass


class AccountDisabled(AccountServiceError):
    pass


@dataclass(frozen=True, slots=True)
class AccountActor:
    user_id: UUID
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "quan_tri"


@dataclass(frozen=True, slots=True)
class CreateAccountCommand:
    channel: Channel
    display_name: str
    external_account_id: str | None
    capabilities: Mapping[str, Any]
    metadata: Mapping[str, Any]
    credentials: Mapping[str, Any] | None = None


class AccountRepository(Protocol):
    async def find_by_external(
        self,
        channel: Channel,
        external_account_id: str | None,
    ) -> ChannelAccount | None: ...

    async def create(
        self,
        account: ChannelAccount,
        sealed: SealedCredential | None,
        *,
        actor_id: UUID,
    ) -> ChannelAccount: ...

    async def get(self, account_id: UUID) -> ChannelAccount | None: ...

    async def has_credentials(self, account_id: UUID) -> bool: ...

    async def store_credentials(
        self,
        account_id: UUID,
        sealed: SealedCredential,
        *,
        actor_id: UUID,
    ) -> None: ...

    async def update_status(
        self,
        account_id: UUID,
        status: AccountStatus,
        *,
        actor_id: UUID,
    ) -> ChannelAccount: ...


class ChannelAccountService:
    def __init__(self, repository: AccountRepository, vault: CredentialVault):
        self._repository = repository
        self._vault = vault

    @staticmethod
    def _require_admin(actor: AccountActor) -> None:
        if not actor.is_admin:
            raise AccountPermissionDenied("chỉ quản trị viên được thay đổi tài khoản kênh")

    async def create_account(
        self,
        command: CreateAccountCommand,
        *,
        actor: AccountActor,
    ) -> ChannelAccount:
        self._require_admin(actor)
        display_name = command.display_name.strip()
        if not display_name:
            raise ValueError("tên hiển thị tài khoản không được để trống")
        account_id = uuid4()
        external_id = (command.external_account_id or "").strip()
        if external_id:
            existing = await self._repository.find_by_external(
                command.channel,
                external_id,
            )
            if existing is not None:
                raise AccountAlreadyExists("tài khoản kênh này đã tồn tại")
        else:
            # Provider ID thường chỉ có sau OAuth/QR. Placeholder theo UUID
            # cho phép tạo nhiều connection session mà vẫn giữ unique index.
            external_id = f"pending:{account_id}"
        account = ChannelAccount(
            id=account_id,
            channel=command.channel,
            display_name=display_name,
            external_account_id=external_id,
            status=AccountStatus.PENDING,
            capabilities=dict(command.capabilities),
            metadata=dict(kiem_metadata_khong_bi_mat(command.metadata)),
            is_legacy=False,
        )
        sealed = None
        if command.credentials:
            sealed = self._vault.encrypt(command.credentials, account_id=account.id)
        return await self._repository.create(
            account,
            sealed,
            actor_id=actor.user_id,
        )

    async def rotate_credentials(
        self,
        account_id: UUID,
        credentials: Mapping[str, Any],
        *,
        actor: AccountActor,
    ) -> None:
        self._require_admin(actor)
        if await self._repository.get(account_id) is None:
            raise AccountNotFound("không tìm thấy tài khoản kênh")
        sealed = self._vault.encrypt(credentials, account_id=account_id)
        await self._repository.store_credentials(
            account_id,
            sealed,
            actor_id=actor.user_id,
        )

    async def enable_account(
        self,
        account_id: UUID,
        *,
        actor: AccountActor,
    ) -> ChannelAccount:
        self._require_admin(actor)
        if await self._repository.get(account_id) is None:
            raise AccountNotFound("không tìm thấy tài khoản kênh")
        if not await self._repository.has_credentials(account_id):
            raise AccountDisabled("tài khoản chưa có credential để kích hoạt")
        return await self._repository.update_status(
            account_id,
            AccountStatus.ACTIVE,
            actor_id=actor.user_id,
        )

    async def disable_account(
        self,
        account_id: UUID,
        *,
        actor: AccountActor,
    ) -> ChannelAccount:
        self._require_admin(actor)
        if await self._repository.get(account_id) is None:
            raise AccountNotFound("không tìm thấy tài khoản kênh")
        return await self._repository.update_status(
            account_id,
            AccountStatus.DISABLED,
            actor_id=actor.user_id,
        )

    async def require_sendable(self, account_id: UUID) -> ChannelAccount:
        account = await self._repository.get(account_id)
        if account is None:
            raise AccountNotFound("không tìm thấy tài khoản kênh")
        if account.status not in {AccountStatus.ACTIVE, AccountStatus.DEGRADED}:
            raise AccountDisabled("tài khoản hiện không được phép gửi")
        if not await self._repository.has_credentials(account_id):
            raise AccountDisabled("tài khoản không có credential để gửi")
        return account
