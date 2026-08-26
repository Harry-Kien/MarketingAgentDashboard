"""Contract dữ liệu assignment, routing, SLA và human mode."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "agent" / "migrations" / "versions" / "0005_routing_sla.sql"


def _sql():
    return SQL_PATH.read_text(encoding="utf-8").lower()


def test_schema_co_team_routing_assignment_sla():
    sql = _sql()
    for table in (
        "teams",
        "team_members",
        "routing_rules",
        "conversation_assignments",
        "sla_policies",
        "sla_events",
    ):
        assert f"create table if not exists {table}" in sql


def test_conversation_co_mode_state_priority_version_va_deadline():
    sql = _sql()
    for column in (
        "mode",
        "state",
        "priority",
        "assigned_team_id",
        "assigned_at",
        "first_response_due_at",
        "resolution_due_at",
        "first_responded_at",
        "resolved_at",
        "version",
    ):
        assert f"add column if not exists {column}" in sql


def test_backfill_escalated_thanh_human_va_khong_reset_sla_bang_trigger():
    sql = _sql()
    assert "when status = 'escalated' then 'human'" in sql
    assert "prevent_sla_deadline_reset" in sql
    assert "old.first_response_due_at" in sql
    assert "old.resolution_due_at" in sql


def test_assignment_history_khong_bi_ghi_de():
    sql = _sql()
    assignments = sql.split("create table if not exists conversation_assignments", 1)[1]
    assignments = assignments.split("create table", 1)[0]
    assert "started_at" in assignments
    assert "ended_at" in assignments
    assert "actor_id" in assignments
    assert "reason" in assignments
