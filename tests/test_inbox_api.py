"""Native inbox: account scope, cursor, unread và SSE replay."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from agent.api.inbox import (
    InboxFilters,
    PostgresInboxQueryRepository,
    decode_cursor,
    encode_cursor,
    event_stream,
    resolve_event_cursor,
)


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


class _Connection:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        return self.rows

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", sql, args))
        return self.row

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))
        return "INSERT 0 1"


def test_cursor_opaque_roundtrip_giu_timestamp_va_uuid():
    timestamp = datetime(2026, 8, 25, 12, 30, tzinfo=timezone.utc)
    conversation_id = uuid4()

    cursor = encode_cursor(timestamp, conversation_id)

    assert "2026" not in cursor
    assert decode_cursor(cursor) == (timestamp, conversation_id)


def test_list_scope_membership_filter_va_cursor_on_dinh():
    connection = _Connection([])
    repository = PostgresInboxQueryRepository(lambda: _Pool(connection))
    user_id = uuid4()
    account_id = uuid4()
    assignee_id = uuid4()
    cursor_time = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)
    cursor_id = uuid4()

    asyncio.run(
        repository.list_conversations(
            user_id=user_id,
            is_admin=False,
            filters=InboxFilters(
                account_id=account_id,
                channel="zalo_oa",
                status="assist",
                assignee_id=assignee_id,
            ),
            cursor=(cursor_time, cursor_id),
            limit=25,
        )
    )

    _kind, sql, args = connection.calls[0]
    assert "account_memberships" in sql
    assert "conversation.account_id = $" in sql
    assert "account.channel = $" in sql
    assert "conversation.status = $" in sql
    assert "conversation.assigned_to = $" in sql
    assert "(conversation.updated_at, conversation.id) <" in sql
    assert "ORDER BY conversation.updated_at DESC, conversation.id DESC" in sql
    assert "unread_count" in sql
    assert user_id in args and account_id in args and assignee_id in args


def test_mark_read_vua_scope_account_vua_upsert_read_state():
    conversation_id = uuid4()
    user_id = uuid4()
    connection = _Connection(row={"account_id": uuid4()})
    repository = PostgresInboxQueryRepository(lambda: _Pool(connection))

    marked = asyncio.run(
        repository.mark_read(
            conversation_id=conversation_id,
            user_id=user_id,
            is_admin=False,
        )
    )

    assert marked is True
    sql = "\n".join(call[1] for call in connection.calls)
    assert "account_memberships" in sql
    assert "INSERT INTO conversation_reads" in sql
    assert "ON CONFLICT (conversation_id, user_id)" in sql


def test_event_stream_replay_tu_sequence_cu_va_khong_lap():
    account_id = uuid4()

    class Repository:
        def __init__(self):
            self.after = []

        async def events_after(self, *, user_id, is_admin, after, limit=100):
            self.after.append(after)
            if after == 10:
                return [
                    {
                        "sequence_id": 11,
                        "account_id": account_id,
                        "topic": "message.created",
                        "ref_id": uuid4(),
                        "payload": {"message_id": "m1"},
                        "created_at": datetime.now(timezone.utc),
                    }
                ]
            raise asyncio.CancelledError

    repository = Repository()

    async def collect():
        chunks = []
        try:
            async for chunk in event_stream(
                repository,
                user_id=uuid4(),
                is_admin=False,
                after=10,
                poll_seconds=0,
            ):
                chunks.append(chunk)
        except asyncio.CancelledError:
            pass
        return chunks

    chunks = asyncio.run(collect())

    assert repository.after == [10, 11]
    assert "id: 11" in chunks[0]
    assert "event: message.created" in chunks[0]
    assert chunks[0].count("id: 11") == 1


def test_sse_ho_tro_last_event_id_va_query_duoc_uu_tien():
    assert resolve_event_cursor(None, "41") == 41
    assert resolve_event_cursor(7, "41") == 7


def test_sse_last_event_id_rac_bi_tu_choi():
    with __import__("pytest").raises(ValueError, match="Last-Event-ID"):
        resolve_event_cursor(None, "khong-phai-so")
