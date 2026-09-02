"""Tạo adapter theo account; tuyệt đối không fallback khi ID sai."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID

from agent.omnichannel.accounts import AccountStatus, Channel, ChannelAccount

from .base import ChannelAdapter
from .chatwoot import ChatwootAdapter
from .messenger import FacebookAdapter, MessengerAdapter
from .meta_channels import InstagramAdapter, WhatsAppAdapter
from .zalo_oa import ZaloOAAdapter
from .zalo_personal import ZaloPersonalAdapter
from .webchat import WebchatAdapter
from .zalocrm import ZaloCRMAdapter


class AccountAdapterNotFound(RuntimeError):
    """Account không tồn tại, bị khóa hoặc chưa có connector an toàn."""


class AccountReader(Protocol):
    async def get(self, account_id: UUID) -> ChannelAccount | None: ...


class CredentialReader(Protocol):
    async def load(self, account_id: UUID) -> Mapping[str, Any] | None: ...


_LEGACY_ADAPTERS: dict[Channel, type[ChannelAdapter]] = {
    Channel.LEGACY_ZALOCRM: ZaloCRMAdapter,
    Channel.LEGACY_CHATWOOT: ChatwootAdapter,
    Channel.LEGACY_MESSENGER: MessengerAdapter,
}

_NATIVE_ADAPTERS: dict[Channel, type[ChannelAdapter]] = {
    Channel.FACEBOOK: FacebookAdapter,
    Channel.ZALO_OA: ZaloOAAdapter,
    Channel.INSTAGRAM: InstagramAdapter,
    Channel.WHATSAPP: WhatsAppAdapter,
    Channel.ZALO_PERSONAL: ZaloPersonalAdapter,
    Channel.WEBCHAT: WebchatAdapter,
}


class AccountAdapterFactory:
    """Ranh giới strangler: account cũ chạy được, account native fail closed."""

    def __init__(
        self,
        repository: AccountReader,
        credentials: CredentialReader | None = None,
    ):
        self._repository = repository
        self._credentials = credentials

    async def create(self, account_id: UUID) -> ChannelAdapter:
        account = await self._repository.get(account_id)
        if account is None:
            raise AccountAdapterNotFound("không tìm thấy tài khoản kênh")
        if account.status not in {AccountStatus.ACTIVE, AccountStatus.DEGRADED}:
            raise AccountAdapterNotFound("tài khoản kênh không hoạt động")
        if account.is_legacy:
            adapter_class = _LEGACY_ADAPTERS.get(account.channel)
            if adapter_class is None:
                raise AccountAdapterNotFound(
                    "connector legacy của tài khoản này không tồn tại"
                )
            return adapter_class(account_id=account.id)

        adapter_class = _NATIVE_ADAPTERS.get(account.channel)
        if adapter_class is None:
            raise AccountAdapterNotFound(
                "connector native của tài khoản này chưa được kích hoạt"
            )
        if self._credentials is None:
            raise AccountAdapterNotFound("chưa cấu hình credential loader")
        loaded = await self._credentials.load(account.id)
        if not loaded:
            raise AccountAdapterNotFound("tài khoản native không có credential")
        credentials = dict(loaded)
        credentials.setdefault("external_account_id", account.external_account_id)
        kwargs: dict[str, Any] = {
            "account_id": account.id,
            "credentials": credentials,
        }
        rotate = getattr(self._credentials, "store_rotated", None)
        if account.channel == Channel.ZALO_OA and rotate is not None:
            async def persist(payload: Mapping[str, Any]) -> None:
                await rotate(account.id, payload)

            kwargs["on_credentials_rotated"] = persist
        return adapter_class(**kwargs)
