"""Xác minh provider trước khi account được phép gửi/nhận production traffic."""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any
from uuid import UUID

from agent.channels.base import ChannelAdapter, ConnectionCheck

from .account_service import AccountNotFound
from .accounts import AccountStatus, Channel, ChannelAccount


class NativeVerificationAdapterFactory:
    def __init__(self, credential_loader: Any) -> None:
        self._credential_loader = credential_loader

    async def __call__(self, account: ChannelAccount) -> ChannelAdapter:
        credentials = await self._credential_loader.load(account.id)
        if not credentials:
            raise RuntimeError("tài khoản chưa có credential")
        values = dict(credentials)
        values.setdefault("external_account_id", account.external_account_id)
        if account.channel == Channel.FACEBOOK:
            from agent.channels.messenger import FacebookAdapter
            return FacebookAdapter(account_id=account.id, credentials=values)
        if account.channel == Channel.INSTAGRAM:
            from agent.channels.meta_channels import InstagramAdapter
            return InstagramAdapter(account_id=account.id, credentials=values)
        if account.channel == Channel.WHATSAPP:
            from agent.channels.meta_channels import WhatsAppAdapter
            return WhatsAppAdapter(account_id=account.id, credentials=values)
        if account.channel == Channel.ZALO_PERSONAL:
            from agent.channels.zalo_personal import ZaloPersonalAdapter
            return ZaloPersonalAdapter(account_id=account.id, credentials=values)
        if account.channel == Channel.WEBCHAT:
            from agent.channels.webchat import WebchatAdapter
            return WebchatAdapter(account_id=account.id, credentials=values)
        if account.channel == Channel.ZALO_OA:
            from agent.channels.zalo_oa import ZaloOAAdapter

            async def persist(rotated) -> None:
                await self._credential_loader.store_rotated(account.id, rotated)

            return ZaloOAAdapter(
                account_id=account.id,
                credentials=values,
                on_credentials_rotated=persist,
            )
        raise RuntimeError("connector này không hỗ trợ xác minh native")


class NativeConnectionVerifier:
    def __init__(
        self,
        repository: Any,
        adapter_factory: Callable[[ChannelAccount], ChannelAdapter | Any],
    ) -> None:
        self._repository = repository
        self._adapter_factory = adapter_factory

    async def verify(self, account_id: UUID, *, actor_id: UUID) -> ConnectionCheck:
        account = await self._repository.get(account_id)
        if account is None:
            raise AccountNotFound("không tìm thấy tài khoản kênh")
        adapter = None
        try:
            adapter = self._adapter_factory(account)
            if inspect.isawaitable(adapter):
                adapter = await adapter
            result = await adapter.verify_connection()
        except Exception as exc:  # provider/network failure becomes explicit health
            result = ConnectionCheck(
                False,
                "provider.unreachable",
                detail={"error_type": type(exc).__name__},
            )
        finally:
            close = getattr(adapter, "aclose", None) if adapter is not None else None
            if close is not None:
                await close()

        status = AccountStatus.ACTIVE if result.ok else (
            AccountStatus.REAUTH_REQUIRED
            if result.code in {"provider.unauthorized", "provider.token_expired"}
            else AccountStatus.DEGRADED
        )
        if result.ok and result.external_account_id:
            await self._repository.bind_external_identity(
                account_id,
                result.external_account_id,
                actor_id=actor_id,
            )
        await self._repository.record_health(
            account_id,
            status=status,
            code=result.code,
            detail=result.detail,
        )
        if account.status != status:
            await self._repository.update_status(
                account_id,
                status,
                actor_id=actor_id,
            )
        return result
