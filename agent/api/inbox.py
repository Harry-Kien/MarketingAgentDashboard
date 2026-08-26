"""API native inbox có account scope, unread và SSE replay được."""
from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent import db
from agent.config import settings
from agent.omnichannel.routing import (
    AssignmentDenied,
    ConversationConflict,
    ConversationNotFound,
    ConversationRoutingService,
    PostgresRoutingRepository,
    RoutingError,
)

from .routes import bat_buoc_dang_nhap


router = APIRouter(prefix="/api/inbox", tags=["native-inbox"])


@dataclass(frozen=True, slots=True)
class InboxFilters:
    account_id: UUID | None = None
    channel: str | None = None
    status: str | None = None
    assignee_id: UUID | None = None


def encode_cursor(updated_at: datetime, conversation_id: UUID) -> str:
    raw = json.dumps(
        [updated_at.isoformat(), str(conversation_id)],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        timestamp, conversation_id = json.loads(
            base64.urlsafe_b64decode(padded).decode()
        )
        return datetime.fromisoformat(timestamp), UUID(conversation_id)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("cursor inbox không hợp lệ") from exc


class PostgresInboxQueryRepository:
    def __init__(self, pool_provider: Callable[[], Any] = db.pool):
        self._pool_provider = pool_provider

    async def list_conversations(
        self,
        *,
        user_id: UUID,
        is_admin: bool,
        filters: InboxFilters,
        cursor: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        args: list[Any] = [user_id, is_admin]

        def bind(value: Any) -> str:
            args.append(value)
            return f"${len(args)}"

        clauses = [
            "($2 OR EXISTS ("
            "SELECT 1 FROM account_memberships membership "
            "WHERE membership.account_id = conversation.account_id "
            "AND membership.user_id = $1))"
        ]
        if filters.account_id is not None:
            clauses.append(f"conversation.account_id = {bind(filters.account_id)}")
        if filters.channel:
            clauses.append(f"account.channel = {bind(filters.channel)}")
        if filters.status:
            clauses.append(f"conversation.status = {bind(filters.status)}")
        if filters.assignee_id is not None:
            clauses.append(
                f"conversation.assigned_to = {bind(filters.assignee_id)}"
            )
        if cursor is not None:
            ts_param = bind(cursor[0])
            id_param = bind(cursor[1])
            clauses.append(
                "(conversation.updated_at, conversation.id) "
                f"< ({ts_param}, {id_param})"
            )
        limit_param = bind(max(1, min(limit, 100)))
        sql = f"""
            SELECT conversation.id, conversation.account_id,
                   account.channel, account.display_name AS account_name,
                   conversation.nen_tang, conversation.customer_name,
                   conversation.customer_ref, conversation.status,
                   conversation.outcome, conversation.mode, conversation.state,
                   conversation.priority, conversation.assigned_to,
                   conversation.assigned_team_id, conversation.version,
                   conversation.first_response_due_at,
                   conversation.resolution_due_at,
                   conversation.msg_count, conversation.updated_at,
                   latest.content AS last_message,
                   latest.delivery_status AS last_delivery_status,
                   (
                       SELECT count(*)
                       FROM messages unread_message
                       WHERE unread_message.conversation_id = conversation.id
                         AND unread_message.role = 'customer'
                         AND unread_message.created_at > coalesce(
                             read_state.last_read_at, 'epoch'::timestamptz
                         )
                   ) AS unread_count
            FROM conversations conversation
            JOIN channel_accounts account ON account.id = conversation.account_id
            LEFT JOIN conversation_reads read_state
              ON read_state.conversation_id = conversation.id
             AND read_state.user_id = $1
            LEFT JOIN LATERAL (
                SELECT content, delivery_status
                FROM messages
                WHERE conversation_id = conversation.id
                ORDER BY created_at DESC, id DESC
                LIMIT 1
            ) latest ON true
            WHERE {" AND ".join(clauses)}
            ORDER BY conversation.updated_at DESC, conversation.id DESC
            LIMIT {limit_param}
        """
        async with self._pool_provider().acquire() as connection:
            rows = await connection.fetch(sql, *args)
        return [dict(row) for row in rows]

    async def get_conversation(
        self,
        *,
        conversation_id: UUID,
        user_id: UUID,
        is_admin: bool,
    ) -> dict[str, Any] | None:
        sql = """
            SELECT conversation.*, account.display_name AS account_name,
                   account.channel AS account_channel
            FROM conversations conversation
            JOIN channel_accounts account ON account.id = conversation.account_id
            WHERE conversation.id = $1
              AND ($3 OR EXISTS (
                  SELECT 1 FROM account_memberships membership
                  WHERE membership.account_id = conversation.account_id
                    AND membership.user_id = $2
              ))
        """
        async with self._pool_provider().acquire() as connection:
            conversation = await connection.fetchrow(
                sql, conversation_id, user_id, is_admin
            )
            if conversation is None:
                return None
            messages = await connection.fetch(
                """
                SELECT message.*,
                       coalesce(jsonb_agg(
                           jsonb_build_object(
                               'id', attachment.id,
                               'kind', attachment.kind,
                               'url', attachment.url,
                               'original_url', attachment.original_url,
                               'storage_key', attachment.storage_key,
                               'mime_type', attachment.mime_type,
                               'metadata', attachment.metadata
                           ) ORDER BY attachment.ordinal
                       ) FILTER (WHERE attachment.id IS NOT NULL), '[]') attachments
                FROM messages message
                LEFT JOIN attachments attachment ON attachment.message_id = message.id
                WHERE message.conversation_id = $1
                GROUP BY message.id
                ORDER BY message.created_at, message.id
                """,
                conversation_id,
            )
        result = dict(conversation)
        result["messages"] = [dict(message) for message in messages]
        return result

    async def mark_read(
        self,
        *,
        conversation_id: UUID,
        user_id: UUID,
        is_admin: bool,
    ) -> bool:
        async with self._pool_provider().acquire() as connection:
            allowed = await connection.fetchrow(
                """
                SELECT conversation.account_id
                FROM conversations conversation
                WHERE conversation.id = $1
                  AND ($3 OR EXISTS (
                      SELECT 1 FROM account_memberships membership
                      WHERE membership.account_id = conversation.account_id
                        AND membership.user_id = $2
                  ))
                """,
                conversation_id,
                user_id,
                is_admin,
            )
            if allowed is None:
                return False
            await connection.execute(
                """
                INSERT INTO conversation_reads (
                    conversation_id, user_id, last_read_at
                ) VALUES ($1,$2,now())
                ON CONFLICT (conversation_id, user_id)
                DO UPDATE SET last_read_at = excluded.last_read_at
                """,
                conversation_id,
                user_id,
            )
        return True

    async def events_after(
        self,
        *,
        user_id: UUID,
        is_admin: bool,
        after: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        async with self._pool_provider().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT event.*
                FROM inbox_events event
                WHERE event.sequence_id > $1
                  AND ($4 OR EXISTS (
                      SELECT 1 FROM account_memberships membership
                      WHERE membership.account_id = event.account_id
                        AND membership.user_id = $2
                  ))
                ORDER BY event.sequence_id
                LIMIT $3
                """,
                max(0, after),
                user_id,
                max(1, min(limit, 500)),
                is_admin,
            )
        return [dict(row) for row in rows]


def _json_default(value: Any) -> str:
    if isinstance(value, (UUID, datetime)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    raise TypeError(f"không thể JSON hoá {type(value).__name__}")


async def event_stream(
    repository: PostgresInboxQueryRepository,
    *,
    user_id: UUID,
    is_admin: bool,
    after: int,
    poll_seconds: float = settings.sse_poll_seconds,
) -> AsyncIterator[str]:
    cursor = max(0, after)
    while True:
        events = await repository.events_after(
            user_id=user_id,
            is_admin=is_admin,
            after=cursor,
        )
        if events:
            for event in events:
                sequence = int(event["sequence_id"])
                cursor = max(cursor, sequence)
                data = json.dumps(event, default=_json_default, ensure_ascii=False)
                yield f"id: {sequence}\nevent: {event['topic']}\ndata: {data}\n\n"
        else:
            yield ": keep-alive\n\n"
        await asyncio.sleep(poll_seconds)


def get_inbox_repository() -> PostgresInboxQueryRepository:
    return PostgresInboxQueryRepository()


def get_routing_service() -> ConversationRoutingService:
    return ConversationRoutingService(PostgresRoutingRepository())


def _user_scope(user: dict) -> tuple[UUID, bool]:
    return UUID(str(user["id"])), user["vai_tro"] == "quan_tri"


def resolve_event_cursor(after: int | None, last_event_id: str | None) -> int:
    """Query tường minh thắng header; header phục hồi kết nối SSE chuẩn."""
    if after is not None:
        return max(0, after)
    if not last_event_id:
        return 0
    try:
        return max(0, int(last_event_id))
    except ValueError as exc:
        raise ValueError("Last-Event-ID không hợp lệ") from exc


class TakeoverIn(BaseModel):
    assignee_id: UUID | None = None
    team_id: UUID | None = None
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class ReleaseIn(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


def _routing_response(state) -> dict[str, Any]:
    return {
        "conversation_id": str(state.conversation_id),
        "mode": state.mode,
        "status": state.status,
        "assigned_to": str(state.assigned_to) if state.assigned_to else None,
        "assigned_team_id": (
            str(state.assigned_team_id) if state.assigned_team_id else None
        ),
        "version": state.version,
    }


def _raise_routing(exc: RoutingError) -> None:
    if isinstance(exc, ConversationNotFound):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, AssignmentDenied):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, ConversationConflict):
        raise HTTPException(409, str(exc)) from exc
    raise exc


@router.get("/conversations")
async def list_inbox_conversations(
    account_id: UUID | None = None,
    channel: str | None = None,
    status: str | None = None,
    assignee_id: UUID | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(bat_buoc_dang_nhap),
    repository: PostgresInboxQueryRepository = Depends(get_inbox_repository),
) -> dict[str, Any]:
    decoded = None
    if cursor:
        try:
            decoded = decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    user_id, is_admin = _user_scope(user)
    rows = await repository.list_conversations(
        user_id=user_id,
        is_admin=is_admin,
        filters=InboxFilters(account_id, channel, status, assignee_id),
        cursor=decoded,
        limit=limit + 1,
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    next_cursor = None
    if has_more and visible:
        tail = visible[-1]
        next_cursor = encode_cursor(tail["updated_at"], tail["id"])
    return {"items": visible, "next_cursor": next_cursor}


@router.get("/conversations/{conversation_id}")
async def inbox_conversation_detail(
    conversation_id: UUID,
    user: dict = Depends(bat_buoc_dang_nhap),
    repository: PostgresInboxQueryRepository = Depends(get_inbox_repository),
) -> dict[str, Any]:
    user_id, is_admin = _user_scope(user)
    conversation = await repository.get_conversation(
        conversation_id=conversation_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    if conversation is None:
        raise HTTPException(404, "Không tìm thấy hội thoại")
    return conversation


@router.post("/conversations/{conversation_id}/read")
async def mark_inbox_read(
    conversation_id: UUID,
    user: dict = Depends(bat_buoc_dang_nhap),
    repository: PostgresInboxQueryRepository = Depends(get_inbox_repository),
) -> dict[str, bool]:
    user_id, is_admin = _user_scope(user)
    if not await repository.mark_read(
        conversation_id=conversation_id,
        user_id=user_id,
        is_admin=is_admin,
    ):
        raise HTTPException(404, "Không tìm thấy hội thoại")
    return {"ok": True}


@router.post("/conversations/{conversation_id}/takeover")
async def takeover_conversation(
    conversation_id: UUID,
    body: TakeoverIn,
    user: dict = Depends(bat_buoc_dang_nhap),
    service: ConversationRoutingService = Depends(get_routing_service),
) -> dict[str, Any]:
    actor_id, is_admin = _user_scope(user)
    try:
        state = await service.takeover(
            conversation_id=conversation_id,
            actor_id=actor_id,
            assignee_id=body.assignee_id or actor_id,
            team_id=body.team_id,
            expected_version=body.expected_version,
            reason=body.reason,
            actor_is_admin=is_admin,
        )
    except RoutingError as exc:
        _raise_routing(exc)
    return _routing_response(state)


@router.post("/conversations/{conversation_id}/release")
async def release_conversation(
    conversation_id: UUID,
    body: ReleaseIn,
    user: dict = Depends(bat_buoc_dang_nhap),
    service: ConversationRoutingService = Depends(get_routing_service),
) -> dict[str, Any]:
    actor_id, is_admin = _user_scope(user)
    try:
        state = await service.release(
            conversation_id=conversation_id,
            actor_id=actor_id,
            expected_version=body.expected_version,
            reason=body.reason,
            actor_is_admin=is_admin,
        )
    except RoutingError as exc:
        _raise_routing(exc)
    return _routing_response(state)


@router.get("/events")
async def inbox_events(
    after: int | None = Query(None, ge=0),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    user: dict = Depends(bat_buoc_dang_nhap),
    repository: PostgresInboxQueryRepository = Depends(get_inbox_repository),
) -> StreamingResponse:
    user_id, is_admin = _user_scope(user)
    try:
        cursor = resolve_event_cursor(after, last_event_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return StreamingResponse(
        event_stream(
            repository,
            user_id=user_id,
            is_admin=is_admin,
            after=cursor,
            poll_seconds=settings.sse_poll_seconds,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
