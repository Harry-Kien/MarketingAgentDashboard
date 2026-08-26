"""Contract dữ liệu cho inbox native và transactional outbox."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MIGRATION = (
    ROOT
    / "agent"
    / "migrations"
    / "versions"
    / "0002_native_inbox_outbox.sql"
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_migration_tao_ledger_outbox_va_attachments():
    sql = _sql()
    for table in ("webhook_deliveries", "outbox_jobs", "attachments"):
        assert f"create table if not exists {table}" in sql


def test_webhook_dedupe_bat_buoc_account_scope():
    sql = _sql()
    ledger = sql.split("create table if not exists webhook_deliveries", 1)[1]
    ledger = ledger.split("create table", 1)[0]
    assert "unique (account_id, dedupe_key)" in ledger
    assert re.search(r"raw_sha256\s+text\s+not null", ledger)
    assert "signature_valid" in ledger


def test_outbox_idempotency_va_claim_index_account_aware():
    sql = _sql()
    outbox = sql.split("create table if not exists outbox_jobs", 1)[1]
    outbox = outbox.split("create table", 1)[0]
    assert "unique (account_id, idempotency_key)" in outbox
    assert "available_at" in outbox
    assert "locked_at" in outbox
    assert "attempts" in outbox
    assert "dead" in outbox
    assert "idx_outbox_claim" in sql


def test_message_co_delivery_state_va_provider_identity():
    sql = _sql()
    for column in (
        "direction",
        "delivery_status",
        "provider_message_id",
        "client_idempotency_key",
    ):
        assert f"add column if not exists {column}" in sql
    assert "alter column direction set not null" in sql
    assert "alter column delivery_status set not null" in sql


def test_attachment_backfill_giu_nguyen_thu_tu_cu():
    sql = _sql()
    assert "jsonb_array_elements" in sql
    assert "with ordinality" in sql
    assert "unique (message_id, ordinal)" in sql
