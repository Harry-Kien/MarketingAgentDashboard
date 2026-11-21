"""Regression GAP-07C: Reopen phải bắt đầu một chu kỳ SLA mới.

Các test trong file này chạy trên PostgreSQL thật vì lỗi nằm trong trigger
PL/pgSQL. Mỗi test nhận một database ``kt_<random>`` riêng từ fixture chung,
áp schema và toàn bộ migration rồi được xoá sau khi chạy.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from agent import db
from agent.migrations.runner import apply_all
from agent.omnichannel import giai_quyet
from agent.omnichannel.sla import PostgresSlaRepository, SlaMonitor


SCHEMA = Path(__file__).resolve().parent.parent / "agent" / "schema.sql"


@pytest.fixture(autouse=True)
def _bat_chu_ky_sla(monkeypatch):
    """
    Cả tệp kiểm DEV-01 (mở lại = chu kỳ SLA mới), nên BẬT công tắc ấy.

    Main tắt DEV-01 mặc định (`SLA_CHU_KY_KHI_MO_LAI=false`, quyết định của
    chủ dự án 13.11.2026); khi tắt, mở lại giữ hạn lượt đầu — hành vi đó có
    test riêng. Giờ làm việc tắt (24/7) để hạn mới đo được bằng phút đồng hồ.
    """
    from agent.config import settings

    monkeypatch.setattr(settings, "sla_chu_ky_khi_mo_lai", True)
    monkeypatch.setattr(settings, "sla_theo_gio_lam_viec", False)


@dataclass(frozen=True, slots=True)
class ReopenCase:
    url: str
    conversation_id: UUID
    old_first_response_due_at: datetime
    old_resolution_due_at: datetime


async def _prepare_case(url: str, *, state: str = "resolved") -> ReopenCase:
    connection = await asyncpg.connect(url)
    try:
        await connection.execute(SCHEMA.read_text(encoding="utf-8"))
        await apply_all(connection)
        account_id = await connection.fetchval(
            """
            INSERT INTO channel_accounts (
                channel, display_name, external_account_id, status
            ) VALUES ('webchat', 'Web SLA test', 'gap-07c', 'active')
            RETURNING id
            """
        )
        contact_id = await connection.fetchval(
            "INSERT INTO contacts (display_name) VALUES ('Khach GAP-07C') RETURNING id"
        )
        contact_point_id = await connection.fetchval(
            """
            INSERT INTO contact_points (
                contact_id, channel_account_id, external_user_id
            ) VALUES ($1, $2, 'gap-07c-customer')
            RETURNING id
            """,
            contact_id,
            account_id,
        )
        await connection.execute(
            """
            INSERT INTO sla_policies (
                account_id, priority, first_response_minutes, resolution_minutes
            ) VALUES ($1, 'normal', 15, 60)
            """,
            account_id,
        )
        row = await connection.fetchrow(
            """
            INSERT INTO conversations (
                account_id, channel, external_id, customer_ref, customer_name,
                contact_id, contact_point_id, state, status, mode, priority,
                first_response_due_at, resolution_due_at, first_responded_at,
                resolved_at
            ) VALUES (
                $1, 'webchat', 'gap-07c-conversation', 'gap-07c-customer',
                'Khach GAP-07C', $2, $3, $4,
                CASE WHEN $4 IN ('resolved', 'closed') THEN 'closed' ELSE 'auto' END,
                'auto', 'normal', now() - interval '105 minutes',
                now() - interval '60 minutes', now() - interval '115 minutes',
                CASE WHEN $4 IN ('resolved', 'closed')
                     THEN now() - interval '2 hours' ELSE NULL END
            )
            RETURNING id, first_response_due_at, resolution_due_at
            """,
            account_id,
            contact_id,
            contact_point_id,
            state,
        )
        return ReopenCase(
            url=url,
            conversation_id=row["id"],
            old_first_response_due_at=row["first_response_due_at"],
            old_resolution_due_at=row["resolution_due_at"],
        )
    finally:
        await connection.close()


@pytest.fixture
def reopen_case(csdl_kiem_thu: str) -> ReopenCase:
    return asyncio.run(_prepare_case(csdl_kiem_thu))


async def _fetchrow(case: ReopenCase, sql: str, *args):
    connection = await asyncpg.connect(case.url)
    try:
        return await connection.fetchrow(sql, *args)
    finally:
        await connection.close()


async def _execute(case: ReopenCase, sql: str, *args) -> str:
    connection = await asyncpg.connect(case.url)
    try:
        return await connection.execute(sql, *args)
    finally:
        await connection.close()


async def _reopen(case: ReopenCase) -> bool:
    pool = await asyncpg.create_pool(case.url, min_size=1, max_size=2)
    previous_pool = db._pool
    db._pool = pool
    try:
        return await giai_quyet.mo_lai_neu_da_giai_quyet(case.conversation_id)
    finally:
        db._pool = previous_pool
        await pool.close()


async def _scan_sla(case: ReopenCase) -> dict[str, int]:
    pool = await asyncpg.create_pool(case.url, min_size=1, max_size=2)
    try:
        repository = PostgresSlaRepository(lambda: pool)
        return await SlaMonitor(repository).scan_once("gap-07c-test")
    finally:
        await pool.close()


def test_resolved_to_open_gets_new_first_response_deadline(reopen_case: ReopenCase):
    assert asyncio.run(_reopen(reopen_case)) is True
    row = asyncio.run(
        _fetchrow(
            reopen_case,
            """
            SELECT state, first_responded_at, first_response_due_at,
                   first_response_due_at - now() AS remaining
            FROM conversations WHERE id = $1
            """,
            reopen_case.conversation_id,
        )
    )

    assert row["state"] == "open"
    assert row["first_responded_at"] is None
    assert row["first_response_due_at"] > reopen_case.old_first_response_due_at
    assert 14 * 60 <= row["remaining"].total_seconds() <= 16 * 60


def test_resolved_to_open_gets_new_resolution_deadline(reopen_case: ReopenCase):
    assert asyncio.run(_reopen(reopen_case)) is True
    row = asyncio.run(
        _fetchrow(
            reopen_case,
            """
            SELECT resolution_due_at, resolution_due_at - now() AS remaining
            FROM conversations WHERE id = $1
            """,
            reopen_case.conversation_id,
        )
    )

    assert row["resolution_due_at"] > reopen_case.old_resolution_due_at
    assert 59 * 60 <= row["remaining"].total_seconds() <= 61 * 60


@pytest.mark.parametrize(
    ("old_state", "new_state"),
    [("open", "open"), ("open", "pending"), ("pending", "open"), ("pending", "pending")],
)
def test_open_pending_cycle_cannot_extend_deadlines(
    csdl_kiem_thu: str, old_state: str, new_state: str
):
    case = asyncio.run(_prepare_case(csdl_kiem_thu, state=old_state))

    asyncio.run(
        _execute(
            case,
            """
            UPDATE conversations
            SET state = $2,
                first_response_due_at = first_response_due_at + interval '1 day',
                resolution_due_at = resolution_due_at + interval '1 day'
            WHERE id = $1
            """,
            case.conversation_id,
            new_state,
        )
    )
    row = asyncio.run(
        _fetchrow(
            case,
            """
            SELECT first_response_due_at, resolution_due_at
            FROM conversations WHERE id = $1
            """,
            case.conversation_id,
        )
    )

    assert row["first_response_due_at"] == case.old_first_response_due_at
    assert row["resolution_due_at"] == case.old_resolution_due_at


def test_reopen_does_not_create_immediate_false_breach(reopen_case: ReopenCase):
    assert asyncio.run(_reopen(reopen_case)) is True

    assert asyncio.run(_scan_sla(reopen_case)) == {
        "first_response": 0,
        "resolution": 0,
        "warning": 0,
        # Thêm 20.11.2026: cảnh báo hạn giải quyết và nâng ưu tiên khi trễ —
        # hội thoại vừa mở lại cũng không được kích hoạt hai thứ ấy.
        "resolution_warning": 0,
        "nang_uu_tien": 0,
    }
    breach_count = asyncio.run(
        _fetchrow(
            reopen_case,
            """
            SELECT count(*) AS count
            FROM sla_events
            WHERE conversation_id = $1
              AND kind IN ('first_response_breached', 'resolution_breached')
            """,
            reopen_case.conversation_id,
        )
    )["count"]
    assert breach_count == 0


def test_reopen_preserves_previous_sla_events(reopen_case: ReopenCase):
    before = asyncio.run(
        _fetchrow(
            reopen_case,
            """
            INSERT INTO sla_events (
                conversation_id, kind, due_at, detail, created_at
            ) VALUES (
                $1, 'resolution_met', $2, '{"session": "previous"}',
                now() - interval '1 hour'
            )
            RETURNING id, conversation_id, kind, due_at, detail, created_at
            """,
            reopen_case.conversation_id,
            reopen_case.old_resolution_due_at,
        )
    )

    assert asyncio.run(_reopen(reopen_case)) is True
    after = asyncio.run(
        _fetchrow(
            reopen_case,
            """
            SELECT id, conversation_id, kind, due_at, detail, created_at
            FROM sla_events WHERE id = $1
            """,
            before["id"],
        )
    )

    assert dict(after) == dict(before)


@pytest.mark.parametrize("state", ["open", "pending", "closed"])
def test_reopen_service_rejects_non_resolved_state(csdl_kiem_thu: str, state: str):
    case = asyncio.run(_prepare_case(csdl_kiem_thu, state=state))

    assert asyncio.run(_reopen(case)) is False
    row = asyncio.run(
        _fetchrow(
            case,
            """
            SELECT state, first_response_due_at, resolution_due_at
            FROM conversations WHERE id = $1
            """,
            case.conversation_id,
        )
    )
    assert row["state"] == state
    assert row["first_response_due_at"] == case.old_first_response_due_at
    assert row["resolution_due_at"] == case.old_resolution_due_at


def test_closed_to_open_is_a_valid_trigger_level_reopen(csdl_kiem_thu: str):
    """
    Ở tầng trigger, "mở lại hợp lệ" = TĂNG `sla_chu_ky` (migration 0039 của
    main). Bản gốc nhánh Release 1 cho đổi hạn ở mọi chuyển closed→open; main
    giữ thiết kế chu kỳ để công tắc DEV-01 tắt được — không tăng chu kỳ thì
    hạn không đổi.
    """
    case = asyncio.run(_prepare_case(csdl_kiem_thu, state="closed"))

    asyncio.run(
        _execute(
            case,
            """
            UPDATE conversations
            SET state = 'open',
                sla_chu_ky = sla_chu_ky + 1,
                first_response_due_at = now() + interval '15 minutes',
                resolution_due_at = now() + interval '60 minutes'
            WHERE id = $1
            """,
            case.conversation_id,
        )
    )
    row = asyncio.run(
        _fetchrow(
            case,
            """
            SELECT state, first_response_due_at, resolution_due_at
            FROM conversations WHERE id = $1
            """,
            case.conversation_id,
        )
    )

    assert row["state"] == "open"
    assert row["first_response_due_at"] > case.old_first_response_due_at
    assert row["resolution_due_at"] > case.old_resolution_due_at


def test_open_cycle_can_receive_initial_deadlines_when_they_are_null(
    csdl_kiem_thu: str,
):
    case = asyncio.run(_prepare_case(csdl_kiem_thu, state="open"))
    asyncio.run(
        _execute(
            case,
            """
            UPDATE conversations
            SET first_response_due_at = NULL, resolution_due_at = NULL
            WHERE id = $1
            """,
            case.conversation_id,
        )
    )
    # OLD deadline khác NULL nên trigger bảo toàn; mô phỏng bản ghi chưa từng
    # được cấp SLA bằng INSERT riêng thay vì cố xoá chốt chống gian lận.
    connection_id = asyncio.run(
        _fetchrow(
            case,
            """
            INSERT INTO conversations (
                account_id, channel, external_id, customer_ref, customer_name,
                contact_id, contact_point_id, state, status, mode, priority,
                first_response_due_at, resolution_due_at
            )
            SELECT account_id, channel, 'gap-07c-null-deadline', customer_ref,
                   customer_name, contact_id, contact_point_id, 'open', status,
                   mode, priority, NULL, NULL
            FROM conversations WHERE id = $1
            RETURNING id
            """,
            case.conversation_id,
        )
    )["id"]

    asyncio.run(
        _execute(
            case,
            """
            UPDATE conversations
            SET first_response_due_at = now() + interval '15 minutes',
                resolution_due_at = now() + interval '60 minutes'
            WHERE id = $1
            """,
            connection_id,
        )
    )
    row = asyncio.run(
        _fetchrow(
            case,
            """
            SELECT first_response_due_at, resolution_due_at
            FROM conversations WHERE id = $1
            """,
            connection_id,
        )
    )

    assert row["first_response_due_at"] is not None
    assert row["resolution_due_at"] is not None
