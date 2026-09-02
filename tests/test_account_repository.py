"""Ranh giới PostgreSQL của tài khoản kênh."""
from __future__ import annotations

import asyncio
from uuid import uuid4

from agent.omnichannel.account_repository import PostgresAccountRepository
from agent.omnichannel.accounts import AccountStatus, Channel, ChannelAccount
from agent.security.credential_vault import SealedCredential


class _Transaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        self.connection.in_transaction = True

    async def __aexit__(self, exc_type, exc, traceback):
        self.connection.in_transaction = False
        return False


class _Connection:
    def __init__(self):
        self.in_transaction = False
        self.operations: list[tuple[str, tuple, bool]] = []

    def transaction(self):
        return _Transaction(self)

    async def execute(self, sql: str, *args):
        self.operations.append((sql, args, self.in_transaction))
        return "OK"


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


def test_create_account_secret_va_audit_cung_mot_transaction():
    """Crash giữa account và secret không được để lại kết nối nửa vời."""
    connection = _Connection()
    repository = PostgresAccountRepository(lambda: _Pool(connection))
    account = ChannelAccount(
        id=uuid4(),
        channel=Channel.ZALO_OA,
        display_name="OA Hà Nội",
        external_account_id="oa-1",
        status=AccountStatus.PENDING,
        capabilities={"send_text": True},
        metadata={},
        is_legacy=False,
    )
    sealed = SealedCredential(1, b"1" * 12, b"ciphertext")
    actor_id = uuid4()

    created = asyncio.run(repository.create(account, sealed, actor_id=actor_id))

    assert created == account
    assert len(connection.operations) == 4
    assert all(in_transaction for _, _, in_transaction in connection.operations)
    account_sql, account_args, _ = connection.operations[0]
    secret_sql, secret_args, _ = connection.operations[1]
    membership_sql, membership_args, _ = connection.operations[2]
    audit_sql, audit_args, _ = connection.operations[3]
    assert "INSERT INTO channel_accounts" in account_sql
    assert "INSERT INTO credential_secrets" in secret_sql
    assert "INSERT INTO account_memberships" in membership_sql
    assert actor_id in membership_args
    assert "INSERT INTO events" in audit_sql
    assert sealed.ciphertext in secret_args
    assert "ciphertext" not in repr(audit_args)
    assert sealed.ciphertext not in audit_args


def test_bind_provider_identity_va_audit_cung_transaction():
    class IdentityConnection(_Connection):
        async def fetchrow(self, sql: str, *args):
            self.operations.append((sql, args, self.in_transaction))
            return {"id": args[0]}

    connection = IdentityConnection()
    repository = PostgresAccountRepository(lambda: _Pool(connection))
    account_id, actor_id = uuid4(), uuid4()

    asyncio.run(
        repository.bind_external_identity(
            account_id,
            "zalo-user-123",
            actor_id=actor_id,
        )
    )

    assert len(connection.operations) == 2
    assert all(in_transaction for _, _, in_transaction in connection.operations)
    update_sql, update_args, _ = connection.operations[0]
    audit_sql, audit_args, _ = connection.operations[1]
    assert "external_account_id" in update_sql
    assert "LIKE 'pending:%'" in update_sql
    assert update_args == (account_id, "zalo-user-123")
    assert "channel_account.identity_bound" in audit_sql
    assert str(actor_id) in audit_args
