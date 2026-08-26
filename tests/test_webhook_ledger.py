"""Ledger webhook chống duplicate và không lưu bí mật thô."""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from uuid import UUID, uuid4

from agent.omnichannel.webhook_ledger import (
    PostgresWebhookLedgerRepository,
    WebhookClaim,
    WebhookClaimRequest,
    WebhookLedger,
    WebhookReceipt,
    WebhookStatus,
)


class _LedgerInMemory:
    def __init__(self):
        self.rows: dict[tuple[UUID, str], WebhookReceipt] = {}

    async def claim(self, request):
        key = (request.account_id, request.dedupe_key)
        current = self.rows.get(key)
        if current is None:
            status = WebhookStatus.PROCESSING if request.signature_valid else WebhookStatus.REJECTED
            receipt = WebhookReceipt(
                id=uuid4(),
                account_id=request.account_id,
                dedupe_key=request.dedupe_key,
                raw_sha256=request.raw_sha256,
                signature_valid=request.signature_valid,
                status=status,
                attempts=1 if request.signature_valid else 0,
                metadata=request.metadata,
                last_error=None,
            )
            self.rows[key] = receipt
            return WebhookClaim(receipt, should_process=request.signature_valid)
        if current.raw_sha256 != request.raw_sha256:
            return WebhookClaim(current, should_process=False, collision=True)
        if current.status == WebhookStatus.FAILED and request.signature_valid:
            retried = replace(
                current,
                status=WebhookStatus.PROCESSING,
                attempts=current.attempts + 1,
                last_error=None,
            )
            self.rows[key] = retried
            return WebhookClaim(retried, should_process=True)
        return WebhookClaim(current, should_process=False)

    async def mark_processed(self, receipt_id):
        self._replace_by_id(receipt_id, status=WebhookStatus.PROCESSED, last_error=None)

    async def mark_failed(self, receipt_id, error):
        self._replace_by_id(receipt_id, status=WebhookStatus.FAILED, last_error=error)

    def _replace_by_id(self, receipt_id, **changes):
        key, current = next(
            (item for item in self.rows.items() if item[1].id == receipt_id)
        )
        self.rows[key] = replace(current, **changes)


def test_webhook_dau_tien_duoc_claim_bang_hash_khong_luu_raw_body():
    repository = _LedgerInMemory()
    ledger = WebhookLedger(repository)
    account_id = uuid4()
    raw = b'{"message":{"text":"xin chao"}}'

    claim = asyncio.run(
        ledger.claim(
            account_id=account_id,
            dedupe_key="message:m1",
            raw_body=raw,
            signature_valid=True,
            metadata={"event": "message"},
        )
    )

    assert claim.should_process is True
    assert claim.receipt.raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert raw.decode() not in repr(repository.rows)
    assert claim.receipt.status == WebhookStatus.PROCESSING


def test_webhook_processed_gui_lai_khong_duoc_xu_ly_lan_hai():
    repository = _LedgerInMemory()
    ledger = WebhookLedger(repository)
    kwargs = {
        "account_id": uuid4(),
        "dedupe_key": "message:m1",
        "raw_body": b"same",
        "signature_valid": True,
        "metadata": {},
    }
    first = asyncio.run(ledger.claim(**kwargs))
    asyncio.run(ledger.mark_processed(first.receipt.id))

    duplicate = asyncio.run(ledger.claim(**kwargs))

    assert duplicate.should_process is False
    assert duplicate.receipt.attempts == 1


def test_webhook_signature_sai_duoc_ghi_nhan_nhung_khong_xu_ly():
    repository = _LedgerInMemory()

    claim = asyncio.run(
        WebhookLedger(repository).claim(
            account_id=uuid4(),
            dedupe_key="message:m1",
            raw_body=b"payload",
            signature_valid=False,
            metadata={},
        )
    )

    assert claim.should_process is False
    assert claim.receipt.status == WebhookStatus.REJECTED


def test_webhook_failed_duoc_retry_va_tang_attempt():
    repository = _LedgerInMemory()
    ledger = WebhookLedger(repository)
    kwargs = {
        "account_id": uuid4(),
        "dedupe_key": "message:m1",
        "raw_body": b"same",
        "signature_valid": True,
        "metadata": {},
    }
    first = asyncio.run(ledger.claim(**kwargs))
    asyncio.run(ledger.mark_failed(first.receipt.id, "temporary database error"))

    retried = asyncio.run(ledger.claim(**kwargs))

    assert retried.should_process is True
    assert retried.receipt.attempts == 2
    assert retried.receipt.last_error is None


def test_metadata_loai_bo_token_cookie_va_authorization():
    repository = _LedgerInMemory()

    claim = asyncio.run(
        WebhookLedger(repository).claim(
            account_id=uuid4(),
            dedupe_key="m1",
            raw_body=b"payload",
            signature_valid=True,
            metadata={
                "event": "message",
                "access_token": "secret",
                "Cookie": "session=secret",
                "authorization": "Bearer secret",
            },
        )
    )

    assert claim.receipt.metadata == {"event": "message"}


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Connection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        return self.rows.pop(0)

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return "UPDATE 1"


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


def test_postgres_claim_insert_khong_truyen_raw_body_vao_csdl():
    account_id = uuid4()
    receipt_id = uuid4()
    row = {
        "id": receipt_id,
        "account_id": account_id,
        "dedupe_key": "m1",
        "raw_sha256": "a" * 64,
        "signature_valid": True,
        "status": "processing",
        "attempts": 1,
        "metadata": {"event": "message"},
        "last_error": None,
    }
    connection = _Connection([row])
    repository = PostgresWebhookLedgerRepository(lambda: _Pool(connection))
    request = WebhookClaimRequest(
        account_id=account_id,
        dedupe_key="m1",
        raw_sha256="a" * 64,
        signature_valid=True,
        metadata={"event": "message"},
    )

    claim = asyncio.run(repository.claim(request))

    assert claim.should_process is True
    assert claim.receipt.id == receipt_id
    sql, args = connection.calls[0]
    assert "INSERT INTO webhook_deliveries" in sql
    assert b"raw webhook body" not in args
    assert "raw webhook body" not in repr(args)
