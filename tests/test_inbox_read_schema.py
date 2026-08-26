"""Contract migration cho unread và phân công native inbox."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT / "agent" / "migrations" / "versions" / "0003_inbox_read_state.sql"
)


def test_migration_co_read_state_assignee_va_indexes():
    sql = SQL.read_text(encoding="utf-8").lower()

    assert "create table if not exists conversation_reads" in sql
    assert "primary key (conversation_id, user_id)" in sql
    assert "add column if not exists assigned_to uuid" in sql
    assert "idx_conversations_assigned_updated" in sql
    assert "idx_messages_customer_unread" in sql
    assert "create table if not exists worker_heartbeats" in sql
