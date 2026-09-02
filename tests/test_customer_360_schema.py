"""Contract migration Customer 360: account-scoped, undo được, không merge tên."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = (
    ROOT / "agent" / "migrations" / "versions" / "0004_customer_360.sql"
)


def _sql() -> str:
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_customer_360_co_du_bang_identity_audit_va_retention():
    sql = _sql()
    for table in (
        "contacts",
        "contact_points",
        "contact_tags",
        "contact_notes",
        "contact_consents",
        "contact_merges",
        "data_retention_jobs",
    ):
        assert f"create table if not exists {table}" in sql


def test_contact_point_unique_theo_account_va_external_identity():
    sql = _sql()
    points = sql.split("create table if not exists contact_points", 1)[1]
    points = points.split("create table", 1)[0]
    assert "unique (channel_account_id, external_user_id)" in points
    assert "verified_fields" in points


def test_backfill_bao_thu_va_khong_tu_merge_theo_ten():
    sql = _sql()
    assert "insert into contacts" in sql
    assert "uuid_generate_v5" in sql
    assert "account_id::text" in sql
    assert "customer_ref" in sql
    assert "group by customer_name" not in sql
    assert "partition by customer_name" not in sql


def test_conversation_bat_buoc_contact_point_sau_backfill():
    sql = _sql()
    update_at = sql.index("update conversations as conversation")
    contact_not_null = sql.index("alter column contact_id set not null")
    point_not_null = sql.index("alter column contact_point_id set not null")
    assert update_at < contact_not_null
    assert update_at < point_not_null
    assert "add column if not exists contact_id uuid" in sql
    assert "add column if not exists contact_point_id uuid" in sql


def test_merge_luu_snapshot_va_du_trang_thai_hoan_tac():
    sql = _sql()
    merges = sql.split("create table if not exists contact_merges", 1)[1]
    merges = merges.split("create table", 1)[0]
    assert "snapshot" in merges
    assert "expected_source_version" in merges
    assert "expected_target_version" in merges
    assert "reverted_at" in merges
    assert "reason" in merges
