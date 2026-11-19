"""GAP-07B: không Resolve hội thoại khi còn công việc chưa hoàn tất."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import nguoi_thu


ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "agent" / "schema.sql"
USER_ID = UUID("00000000-0000-0000-0000-000000000004")
PERMISSIONS = ("hoi_thoai.nhan", "hoi_thoai.doc")


async def _prepare_schema(url: str) -> None:
    from agent.migrations.runner import apply_all

    connection = await asyncpg.connect(url)
    try:
        await connection.execute(SCHEMA.read_text(encoding="utf-8"))
        await apply_all(connection)
    finally:
        await connection.close()


def _app(url: str) -> FastAPI:
    from agent import db
    from agent.api.hoi_thoai_nhan import router
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.migrations.runner import apply_all

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[nguoi_da_dang_nhap] = lambda: nguoi_thu(
        *PERMISSIONS, id=str(USER_ID), ten="resolve-guard"
    )

    async def _codec(connection):
        await connection.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    @app.on_event("startup")
    async def _open():
        db._pool = await asyncpg.create_pool(
            url, min_size=1, max_size=4, init=_codec
        )
        async with db._pool.acquire() as connection:
            await connection.execute(SCHEMA.read_text(encoding="utf-8"))
            await apply_all(connection)

    @app.on_event("shutdown")
    async def _close():
        if db._pool is not None:
            await db._pool.close()
            db._pool = None

    return app


async def _create_conversation(url: str) -> UUID:
    connection = await asyncpg.connect(url)
    try:
        await connection.execute(
            """
            INSERT INTO nguoi_dung (
                id, ten_dang_nhap, mat_khau_bam, ho_ten
            ) VALUES ($1, 'resolve-guard', 'x', 'Resolve Guard')
            ON CONFLICT (id) DO NOTHING
            """,
            USER_ID,
        )
        account_id = await connection.fetchval(
            """
            INSERT INTO channel_accounts (
                channel, display_name, status, external_account_id
            ) VALUES ('webchat', 'Resolve Guard', 'active', 'resolve-guard')
            RETURNING id
            """
        )
        contact_id = await connection.fetchval(
            "INSERT INTO contacts (display_name) VALUES ('Khach Guard') RETURNING id"
        )
        point_id = await connection.fetchval(
            """
            INSERT INTO contact_points (
                contact_id, channel_account_id, external_user_id
            ) VALUES ($1, $2, 'resolve-guard-customer')
            RETURNING id
            """,
            contact_id,
            account_id,
        )
        conversation_id = await connection.fetchval(
            """
            INSERT INTO conversations (
                account_id, channel, external_id, customer_ref, customer_name,
                contact_id, contact_point_id, assigned_to, state, status, mode,
                outcome, first_response_due_at, resolution_due_at
            ) VALUES (
                $1, 'webchat', 'resolve-guard-conversation',
                'resolve-guard-customer', 'Khach Guard', $2, $3, $4,
                'open', 'escalated', 'human', NULL,
                now() + interval '15 minutes', now() + interval '60 minutes'
            )
            RETURNING id
            """,
            account_id,
            contact_id,
            point_id,
            USER_ID,
        )
        await connection.execute(
            "INSERT INTO account_memberships (account_id, user_id) VALUES ($1, $2)",
            account_id,
            USER_ID,
        )
        await connection.execute(
            """
            INSERT INTO conversation_assignments (
                conversation_id, assigned_user_id, source, reason
            ) VALUES ($1, $2, 'manual', 'resolve guard test')
            """,
            conversation_id,
            USER_ID,
        )
        return conversation_id
    finally:
        await connection.close()


async def _insert_task(
    url: str,
    conversation_id: UUID,
    *,
    state: str,
    title: str = "Xu ly yeu cau khach",
    source: str = "nguoi",
) -> UUID:
    connection = await asyncpg.connect(url)
    try:
        return await connection.fetchval(
            """
            INSERT INTO cong_viec (
                tieu_de, conversation_id, trang_thai, nguon, xong_luc
            ) VALUES (
                $1, $2, $3, $4,
                CASE WHEN $3 = 'xong' THEN now() ELSE NULL END
            )
            RETURNING id
            """,
            title,
            conversation_id,
            state,
            source,
        )
    finally:
        await connection.close()


async def _row(url: str, sql: str, *args):
    connection = await asyncpg.connect(url)
    try:
        return await connection.fetchrow(sql, *args)
    finally:
        await connection.close()


def _snapshot(url: str, conversation_id: UUID) -> dict:
    async def read() -> dict:
        row = await _row(
            url,
            """
            SELECT state, status, mode, outcome, resolved_at,
                   first_response_due_at, resolution_due_at,
                   (SELECT count(*) FROM conversation_assignments
                    WHERE conversation_id = conversations.id
                      AND ended_at IS NULL) AS open_assignments,
                   (SELECT count(*) FROM sla_events
                    WHERE conversation_id = conversations.id) AS sla_events,
                   (SELECT count(*) FROM cong_viec
                    WHERE conversation_id = conversations.id
                      AND trang_thai IN ('moi', 'dang_lam')) AS open_tasks
            FROM conversations WHERE id = $1
            """,
            conversation_id,
        )
        return dict(row)

    return asyncio.run(read())


def test_tc01_resolve_succeeds_without_pending_actions(csdl_kiem_thu: str):
    with TestClient(_app(csdl_kiem_thu)) as client:
        conversation_id = asyncio.run(_create_conversation(csdl_kiem_thu))
        response = client.post(
            f"/api/inbox/conversations/{conversation_id}/giai-quyet"
        )

    assert response.status_code == 200, response.text
    after = _snapshot(csdl_kiem_thu, conversation_id)
    assert after["state"] == "resolved"
    assert after["resolved_at"] is not None
    assert after["open_assignments"] == 0


@pytest.mark.parametrize("task_state", ["moi", "dang_lam"])
def test_tc02_tc03_open_task_blocks_resolve(
    csdl_kiem_thu: str, task_state: str
):
    with TestClient(_app(csdl_kiem_thu)) as client:
        conversation_id = asyncio.run(_create_conversation(csdl_kiem_thu))
        task_id = asyncio.run(
            _insert_task(csdl_kiem_thu, conversation_id, state=task_state)
        )
        response = client.post(
            f"/api/inbox/conversations/{conversation_id}/giai-quyet"
        )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "conversation_has_pending_tasks"
    assert detail["message"] == "Không thể Resolve: còn công việc chưa hoàn tất."
    assert detail["pending_tasks"] == [
        {
            "id": str(task_id),
            "title": "Xu ly yeu cau khach",
            "state": task_state,
        }
    ]


@pytest.mark.parametrize("task_state", ["xong", "huy"])
def test_tc04_tc05_closed_task_does_not_block_resolve(
    csdl_kiem_thu: str, task_state: str
):
    with TestClient(_app(csdl_kiem_thu)) as client:
        conversation_id = asyncio.run(_create_conversation(csdl_kiem_thu))
        asyncio.run(
            _insert_task(csdl_kiem_thu, conversation_id, state=task_state)
        )
        response = client.post(
            f"/api/inbox/conversations/{conversation_id}/giai-quyet"
        )

    assert response.status_code == 200, response.text
    assert _snapshot(csdl_kiem_thu, conversation_id)["state"] == "resolved"


def test_tc06_one_open_task_among_many_blocks_resolve(csdl_kiem_thu: str):
    with TestClient(_app(csdl_kiem_thu)) as client:
        conversation_id = asyncio.run(_create_conversation(csdl_kiem_thu))
        asyncio.run(
            _insert_task(
                csdl_kiem_thu, conversation_id, state="xong", title="Da xong"
            )
        )
        open_id = asyncio.run(
            _insert_task(
                csdl_kiem_thu,
                conversation_id,
                state="moi",
                title="Con phai xu ly",
                source="tu_dong",
            )
        )
        asyncio.run(
            _insert_task(
                csdl_kiem_thu, conversation_id, state="huy", title="Da huy"
            )
        )
        response = client.post(
            f"/api/inbox/conversations/{conversation_id}/giai-quyet"
        )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["pending_tasks"] == [
        {"id": str(open_id), "title": "Con phai xu ly", "state": "moi"}
    ]


def test_tc07_rejected_resolve_changes_nothing(csdl_kiem_thu: str):
    with TestClient(_app(csdl_kiem_thu)) as client:
        conversation_id = asyncio.run(_create_conversation(csdl_kiem_thu))
        task_id = asyncio.run(
            _insert_task(csdl_kiem_thu, conversation_id, state="dang_lam")
        )
        before = _snapshot(csdl_kiem_thu, conversation_id)
        response = client.post(
            f"/api/inbox/conversations/{conversation_id}/giai-quyet"
        )

    assert response.status_code == 409, response.text
    assert _snapshot(csdl_kiem_thu, conversation_id) == before
    task = asyncio.run(
        _row(
            csdl_kiem_thu,
            "SELECT trang_thai FROM cong_viec WHERE id = $1",
            task_id,
        )
    )
    assert task["trang_thai"] == "dang_lam"


def test_tc08_task_created_first_wins_race_and_resolve_is_rejected(
    csdl_kiem_thu: str,
):
    async def race() -> tuple[str, int]:
        from agent import db
        from agent.omnichannel import giai_quyet

        await _prepare_schema(csdl_kiem_thu)
        pool = await asyncpg.create_pool(csdl_kiem_thu, min_size=1, max_size=4)
        previous_pool = db._pool
        db._pool = pool
        try:
            conversation_id = await _create_conversation(csdl_kiem_thu)
            async with pool.acquire() as task_connection:
                transaction = task_connection.transaction()
                await transaction.start()
                await task_connection.fetchrow(
                    "SELECT id FROM conversations WHERE id = $1 FOR KEY SHARE",
                    conversation_id,
                )
                await task_connection.execute(
                    """
                    INSERT INTO cong_viec (tieu_de, conversation_id, trang_thai)
                    VALUES ('Viec tao dong thoi', $1, 'moi')
                    """,
                    conversation_id,
                )
                resolve = asyncio.create_task(
                    giai_quyet.giai_quyet(conversation_id, USER_ID)
                )
                await asyncio.sleep(0)
                await transaction.commit()
                with pytest.raises(giai_quyet.ConversationHasPendingTasksError):
                    await resolve
            row = await pool.fetchrow(
                """
                SELECT state,
                       (SELECT count(*) FROM cong_viec
                        WHERE conversation_id = conversations.id
                          AND trang_thai IN ('moi', 'dang_lam')) AS open_tasks
                FROM conversations WHERE id = $1
                """,
                conversation_id,
            )
            return row["state"], row["open_tasks"]
        finally:
            db._pool = previous_pool
            await pool.close()

    state, open_tasks = asyncio.run(race())
    assert (state, open_tasks) == ("open", 1)


def test_tc08_resolve_created_first_prevents_late_open_task(
    csdl_kiem_thu: str,
):
    async def race() -> tuple[str, int]:
        await _prepare_schema(csdl_kiem_thu)
        conversation_id = await _create_conversation(csdl_kiem_thu)
        first = await asyncpg.connect(csdl_kiem_thu)
        second = await asyncpg.connect(csdl_kiem_thu)
        transaction = first.transaction()
        await transaction.start()
        try:
            await first.fetchrow(
                "SELECT id FROM conversations WHERE id = $1 FOR UPDATE",
                conversation_id,
            )
            insert = asyncio.create_task(
                second.execute(
                    """
                    INSERT INTO cong_viec (tieu_de, conversation_id, trang_thai)
                    VALUES ('Viec den qua muon', $1, 'moi')
                    """,
                    conversation_id,
                )
            )
            await asyncio.sleep(0)
            await first.execute(
                "UPDATE conversations SET state = 'resolved' WHERE id = $1",
                conversation_id,
            )
            await transaction.commit()
            with pytest.raises(asyncpg.CheckViolationError):
                await insert
            row = await first.fetchrow(
                """
                SELECT state,
                       (SELECT count(*) FROM cong_viec
                        WHERE conversation_id = conversations.id
                          AND trang_thai IN ('moi', 'dang_lam')) AS open_tasks
                FROM conversations WHERE id = $1
                """,
                conversation_id,
            )
            return row["state"], row["open_tasks"]
        finally:
            if first.is_in_transaction():
                await transaction.rollback()
            await first.close()
            await second.close()

    state, open_tasks = asyncio.run(race())
    assert (state, open_tasks) == ("resolved", 0)


@pytest.mark.parametrize(
    ("producer", "expected_source"),
    [
        ("handover", "agent"),
        ("automation", "tu_dong"),
        ("shipping", "van_chuyen"),
    ],
)
def test_reopen_allows_real_pending_action_producers(
    csdl_kiem_thu: str,
    monkeypatch: pytest.MonkeyPatch,
    producer: str,
    expected_source: str,
):
    """0045 không chặn nhầm task Handover/Automation/Shipping sau Reopen."""
    from agent import canh_gac, db
    from agent.core import cong_viec
    from agent.omnichannel import giai_quyet, tu_dong

    async def no_notification(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        cong_viec, "_bao_viec_moi_cho_nhan_vien", no_notification
    )
    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen", lambda *_a, **_k: None)

    async def exercise() -> tuple[dict, str | None]:
        await _prepare_schema(csdl_kiem_thu)
        conversation_id = await _create_conversation(csdl_kiem_thu)
        connection = await asyncpg.connect(csdl_kiem_thu)
        try:
            await connection.execute(
                """
                UPDATE conversations
                SET state = 'resolved', status = 'closed', mode = 'human',
                    outcome = 'resolved', resolved_at = now()
                WHERE id = $1
                """,
                conversation_id,
            )
        finally:
            await connection.close()

        previous_pool = db._pool
        db._pool = await asyncpg.create_pool(
            csdl_kiem_thu, min_size=1, max_size=2
        )
        try:
            reopened = await giai_quyet.mo_lai_neu_da_giai_quyet(
                conversation_id
            )
            assert reopened is True

            if producer == "handover":
                task_id = await cong_viec.tao_tu_chuyen_nguoi(
                    conversation_id, ly_do="Khách cần nhân viên sau Reopen"
                )
            elif producer == "automation":
                task_id = await tu_dong._tao_viec(
                    db, conversation_id, "Kiểm tra quy tắc", "Rule Reopen"
                )
            else:
                task_id = await cong_viec.tao_tu_van_chuyen(
                    "SO-REOPEN",
                    tieu_de="Gọi khách hẹn giao lại",
                    mo_ta="Hãng báo giao thất bại sau khi hội thoại mở lại",
                    khoa=f"dev04-reopen:{conversation_id}",
                    conversation_id=conversation_id,
                )

            row = await db.fetchrow(
                """
                SELECT c.state, c.status, c.mode,
                       v.id AS task_id, v.nguon, v.trang_thai
                FROM conversations c
                JOIN cong_viec v ON v.conversation_id = c.id
                WHERE c.id = $1
                """,
                conversation_id,
            )
            return row, task_id
        finally:
            await db._pool.close()
            db._pool = previous_pool

    row, task_id = asyncio.run(exercise())
    assert task_id is not None
    assert row == {
        "state": "open",
        "status": "auto",
        "mode": "auto",
        "task_id": UUID(task_id),
        "nguon": expected_source,
        "trang_thai": "moi",
    }


def test_migrations_0039_and_0045_apply_in_order_and_coexist(
    csdl_kiem_thu: str,
):
    """
    Mô phỏng upgrade: CSDL đang ở 0044 (dải main đã áp trên production), rồi
    áp Resolve Guard DEV-04. Khi ghép nhánh Release 1, guard đổi số 0040 →
    0045 vì 0040–0044 đã là migration khác của main; trigger chu kỳ SLA là
    0039 của main.
    """
    from agent.migrations.runner import (
        apply_migrations,
        discover_migrations,
    )

    async def upgrade() -> tuple[list[str], set[str]]:
        migrations = discover_migrations()
        through_0039 = [m for m in migrations if m.version <= "0039"]
        through_0045 = [m for m in migrations if m.version <= "0045"]
        connection = await asyncpg.connect(csdl_kiem_thu)
        try:
            await connection.execute(SCHEMA.read_text(encoding="utf-8"))
            await apply_migrations(connection, through_0039)
            assert await connection.fetchval(
                "SELECT max(version) FROM schema_migrations"
            ) == "0039"

            await apply_migrations(connection, through_0045)
            versions = await connection.fetch(
                """
                SELECT version FROM schema_migrations
                WHERE version IN ('0039', '0045') ORDER BY version
                """
            )
            functions = await connection.fetch(
                """
                SELECT proname
                FROM pg_proc
                WHERE proname IN (
                    'prevent_sla_deadline_reset',
                    'guard_open_task_on_finished_conversation'
                )
                """
            )
            return (
                [row["version"] for row in versions],
                {row["proname"] for row in functions},
            )
        finally:
            await connection.close()

    versions, functions = asyncio.run(upgrade())
    assert versions == ["0039", "0045"]
    assert functions == {
        "prevent_sla_deadline_reset",
        "guard_open_task_on_finished_conversation",
    }
