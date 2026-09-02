"""Mở credential theo account và ghi an toàn token xoay vòng của provider."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from agent.omnichannel.account_repository import PostgresAccountRepository
from agent.security.credential_vault import CredentialVault


SYSTEM_ACTOR_ID = UUID(int=0)


class VaultCredentialLoader:
    def __init__(
        self,
        repository: PostgresAccountRepository,
        vault: CredentialVault,
    ) -> None:
        self._repository = repository
        self._vault = vault

    async def load(self, account_id: UUID) -> dict[str, Any] | None:
        sealed = await self._repository.get_credentials(account_id)
        if sealed is None:
            return None
        return self._vault.decrypt(sealed, account_id=account_id)

    async def store_rotated(
        self,
        account_id: UUID,
        credentials: Mapping[str, Any],
    ) -> None:
        sealed = self._vault.encrypt(credentials, account_id=account_id)
        await self._repository.store_credentials(
            account_id,
            sealed,
            actor_id=SYSTEM_ACTOR_ID,
        )
