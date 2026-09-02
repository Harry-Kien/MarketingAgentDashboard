"""Định tuyến tự động theo account, skill, capacity và round-robin ổn định."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from agent import db


@dataclass(frozen=True, slots=True)
class AutoRoutingState:
    conversation_id: UUID
    assigned_to: UUID
    assigned_team_id: UUID
    version: int


class AutoRoutingTransaction(Protocol):
    async def lock_conversation(self, conversation_id: UUID): ...
    async def matching_rule(self, **kwargs): ...
    async def candidates(self, **kwargs): ...
    async def routing_cursor(self, rule_id: UUID): ...
    async def apply_auto_assignment(self, **kwargs): ...


class AutoRoutingRepository(Protocol):
    def transaction(self): ...


def _choose_candidate(rows: list[Mapping[str, Any]], cursor: UUID | None):
    eligible = [row for row in rows if int(row["active_count"]) < int(row["max_active"])]
    if not eligible:
        return None
    minimum = min(
        eligible,
        key=lambda row: int(row["active_count"]) / int(row["max_active"]),
    )
    low = [
        row for row in eligible
        if int(row["active_count"]) * int(minimum["max_active"])
        == int(minimum["active_count"]) * int(row["max_active"])
    ]
    low.sort(key=lambda row: str(row["user_id"]))
    if cursor is None:
        return low[0]
    for row in low:
        if str(row["user_id"]) > str(cursor):
            return row
    return low[0]


class AutoRoutingService:
    def __init__(self, repository: AutoRoutingRepository) -> None:
        self._repository = repository

    async def route(self, conversation_id: UUID) -> AutoRoutingState | None:
        async with self._repository.transaction() as tx:
            conversation = await tx.lock_conversation(conversation_id)
            if (
                conversation is None
                or conversation.get("assigned_to") is not None
                or conversation.get("mode") == "human"
                or conversation.get("state") in {"resolved", "closed"}
            ):
                return None
            rule = await tx.matching_rule(
                account_id=conversation["account_id"],
                priority=conversation["priority"],
            )
            if rule is None:
                return None
            candidates = await tx.candidates(
                account_id=conversation["account_id"],
                team_id=rule["team_id"],
                required_skills=rule.get("required_skills") or [],
            )
            cursor = await tx.routing_cursor(rule["id"])
            selected = _choose_candidate(list(candidates), cursor)
            if selected is None:
                return None
            updated = await tx.apply_auto_assignment(
                conversation_id=conversation_id,
                account_id=conversation["account_id"],
                rule_id=rule["id"],
                team_id=rule["team_id"],
                assignee_id=selected["user_id"],
                source="auto",
            )
        return AutoRoutingState(
            conversation_id=UUID(str(updated["id"])),
            assigned_to=UUID(str(updated["assigned_to"])),
            assigned_team_id=UUID(str(updated["assigned_team_id"])),
            version=int(updated["version"]),
        )


class PostgresAutoRoutingTransaction:
    def __init__(self, connection) -> None:
        self._connection = connection

    async def lock_conversation(self, conversation_id: UUID):
        await self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"conversation-send:{conversation_id}",
        )
        return await self._connection.fetchrow(
            "SELECT * FROM conversations WHERE id = $1 FOR UPDATE",
            conversation_id,
        )

    async def matching_rule(self, *, account_id: UUID, priority: str):
        return await self._connection.fetchrow(
            """
            SELECT * FROM routing_rules
            WHERE active
              AND (account_id = $1 OR account_id IS NULL)
              AND (priority = $2 OR priority IS NULL)
            ORDER BY (account_id IS NOT NULL) DESC,
                     (priority IS NOT NULL) DESC,
                     weight DESC, created_at, id
            LIMIT 1
            FOR UPDATE
            """,
            account_id,
            priority,
        )

    async def candidates(
        self,
        *,
        account_id: UUID,
        team_id: UUID,
        required_skills: list[str],
    ):
        return await self._connection.fetch(
            """
            SELECT member.user_id, member.max_active,
                   count(conversation.id)::int AS active_count
            FROM team_members member
            JOIN account_memberships membership
              ON membership.user_id = member.user_id
             AND membership.account_id = $1
            LEFT JOIN conversations conversation
              ON conversation.assigned_to = member.user_id
             AND conversation.state IN ('open', 'pending')
            WHERE member.team_id = $2
              AND member.is_available
              AND member.skills @> $3::jsonb
            GROUP BY member.user_id, member.max_active
            HAVING count(conversation.id) < member.max_active
            ORDER BY member.user_id
            """,
            account_id,
            team_id,
            required_skills,
        )

    async def routing_cursor(self, rule_id: UUID):
        return await self._connection.fetchval(
            "SELECT last_user_id FROM routing_cursors WHERE rule_id = $1 FOR UPDATE",
            rule_id,
        )

    async def apply_auto_assignment(
        self,
        *,
        conversation_id: UUID,
        account_id: UUID,
        rule_id: UUID,
        team_id: UUID,
        assignee_id: UUID,
        source: str,
    ):
        await self._connection.execute(
            """
            INSERT INTO conversation_assignments (
                conversation_id, assigned_user_id, assigned_team_id,
                source, reason
            ) VALUES ($1,$2,$3,$4,'matched routing rule')
            """,
            conversation_id,
            assignee_id,
            team_id,
            source,
        )
        updated = await self._connection.fetchrow(
            """
            UPDATE conversations
            SET assigned_to = $2, assigned_team_id = $3,
                assigned_at = now(), version = version + 1, updated_at = now()
            WHERE id = $1 AND assigned_to IS NULL AND mode <> 'human'
            RETURNING *
            """,
            conversation_id,
            assignee_id,
            team_id,
        )
        if updated is None:
            raise RuntimeError("conversation changed during auto routing")
        await self._connection.execute(
            """
            INSERT INTO routing_cursors (rule_id, last_user_id, updated_at)
            VALUES ($1,$2,now())
            ON CONFLICT (rule_id) DO UPDATE
            SET last_user_id = EXCLUDED.last_user_id, updated_at = now()
            """,
            rule_id,
            assignee_id,
        )
        await self._connection.execute(
            "INSERT INTO inbox_events (account_id, topic, ref_id, payload) "
            "VALUES ($1,'conversation.assigned',$2,$3)",
            account_id,
            conversation_id,
            {"assignee_id": str(assignee_id), "team_id": str(team_id), "source": source},
        )
        await self._connection.execute(
            "INSERT INTO events (kind, actor, ref_id, detail) "
            "VALUES ('conversation.auto_assigned','system',$1,$2)",
            conversation_id,
            {"assignee_id": str(assignee_id), "team_id": str(team_id), "rule_id": str(rule_id)},
        )
        return updated


class PostgresAutoRoutingRepository:
    def __init__(self, pool_provider: Callable[[], Any] = db.pool) -> None:
        self._pool_provider = pool_provider

    @asynccontextmanager
    async def transaction(self):
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                yield PostgresAutoRoutingTransaction(connection)

    async def pending_conversation_ids(self, limit: int = 50) -> list[UUID]:
        async with self._pool_provider().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT id FROM conversations
                WHERE assigned_to IS NULL
                  AND mode <> 'human'
                  AND state IN ('open', 'pending')
                ORDER BY CASE priority
                           WHEN 'urgent' THEN 4 WHEN 'high' THEN 3
                           WHEN 'normal' THEN 2 ELSE 1 END DESC,
                         resolution_due_at NULLS LAST, updated_at
                LIMIT $1
                """,
                limit,
            )
        return [row["id"] for row in rows]

    async def heartbeat(self, worker_id: str) -> None:
        async with self._pool_provider().acquire() as connection:
            await connection.execute(
                """
                INSERT INTO worker_heartbeats (
                    worker_name, worker_id, last_seen_at, detail
                ) VALUES ('auto-routing',$1,now(),'{}')
                ON CONFLICT (worker_name) DO UPDATE
                SET worker_id = excluded.worker_id,
                    last_seen_at = excluded.last_seen_at
                """,
                worker_id,
            )


class AutoRoutingWorker:
    def __init__(self, repository: Any, service: AutoRoutingService) -> None:
        self._repository = repository
        self._service = service

    async def scan_once(self, worker_id: str) -> dict[str, int]:
        ids = await self._repository.pending_conversation_ids()
        assigned = 0
        for conversation_id in ids:
            if await self._service.route(conversation_id) is not None:
                assigned += 1
        await self._repository.heartbeat(worker_id)
        return {"examined": len(ids), "assigned": assigned}


async def auto_routing_loop(
    worker: AutoRoutingWorker,
    *,
    worker_id: str,
    interval_seconds: float = 3.0,
    log_error: Callable[[str], Awaitable[None]] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    while True:
        try:
            await worker.scan_once(worker_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # worker phải tự hồi phục
            if log_error is not None:
                await log_error(f"{type(exc).__name__}: {exc}"[:500])
        await sleep(interval_seconds)
