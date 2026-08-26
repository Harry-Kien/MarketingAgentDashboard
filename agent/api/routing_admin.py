"""API quản trị team, rule và SLA cho auto-routing account-aware."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from agent import db

from .routes import bat_buoc_quan_tri


router = APIRouter(prefix="/api/routing", tags=["routing-admin"])


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class TeamMemberIn(BaseModel):
    role: Literal["manager", "agent"] = "agent"
    skills: list[str] = Field(default_factory=list, max_length=50)
    max_active: int = Field(default=20, ge=1, le=500)
    is_available: bool = True


class RoutingRuleIn(BaseModel):
    account_id: UUID | None = None
    team_id: UUID
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    required_skills: list[str] = Field(default_factory=list, max_length=50)
    weight: int = Field(default=100, ge=1, le=10000)
    active: bool = True


class SlaPolicyIn(BaseModel):
    account_id: UUID | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    first_response_minutes: int = Field(ge=1, le=43200)
    resolution_minutes: int = Field(ge=1, le=525600)
    business_hours: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class PostgresRoutingAdminRepository:
    def __init__(self, pool_provider=db.pool) -> None:
        self._pool_provider = pool_provider

    async def list_config(self) -> dict[str, list[dict[str, Any]]]:
        async with self._pool_provider().acquire() as connection:
            teams = await connection.fetch(
                "SELECT * FROM teams ORDER BY status, name"
            )
            rules = await connection.fetch(
                "SELECT * FROM routing_rules ORDER BY active DESC, weight DESC, created_at"
            )
            sla = await connection.fetch(
                "SELECT * FROM sla_policies ORDER BY active DESC, account_id, priority"
            )
        return {
            "teams": [dict(row) for row in teams],
            "rules": [dict(row) for row in rules],
            "sla_policies": [dict(row) for row in sla],
        }

    async def create_team(self, *, name: str, description: str, actor_id: UUID):
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    "INSERT INTO teams (name, description) VALUES ($1,$2) RETURNING *",
                    name,
                    description,
                )
                await connection.execute(
                    "INSERT INTO events (kind, actor, ref_id, detail) "
                    "VALUES ('routing.team_created',$1,$2,$3)",
                    str(actor_id),
                    row["id"],
                    {"name": name},
                )
        return dict(row)

    async def upsert_member(
        self,
        *,
        team_id: UUID,
        user_id: UUID,
        role: str,
        skills: list[str],
        max_active: int,
        is_available: bool,
        actor_id: UUID,
    ):
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO team_members (
                        team_id,user_id,role,skills,max_active,is_available
                    ) VALUES ($1,$2,$3,$4,$5,$6)
                    ON CONFLICT (team_id,user_id) DO UPDATE SET
                        role=excluded.role, skills=excluded.skills,
                        max_active=excluded.max_active,
                        is_available=excluded.is_available
                    RETURNING *
                    """,
                    team_id, user_id, role, skills, max_active, is_available,
                )
                await connection.execute(
                    "INSERT INTO events (kind, actor, ref_id, detail) "
                    "VALUES ('routing.member_upserted',$1,$2,$3)",
                    str(actor_id), team_id, {"user_id": str(user_id)},
                )
        return dict(row)

    async def create_rule(self, *, actor_id: UUID, **values):
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO routing_rules (
                        account_id,team_id,priority,required_skills,weight,active
                    ) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *
                    """,
                    values["account_id"], values["team_id"], values["priority"],
                    values["required_skills"], values["weight"], values["active"],
                )
                await connection.execute(
                    "INSERT INTO events (kind, actor, ref_id, detail) "
                    "VALUES ('routing.rule_created',$1,$2,$3)",
                    str(actor_id), row["id"], {"team_id": str(values["team_id"])},
                )
        return dict(row)

    async def upsert_sla(self, *, actor_id: UUID, **values):
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO sla_policies (
                        account_id,priority,first_response_minutes,
                        resolution_minutes,business_hours,active
                    ) VALUES ($1,$2,$3,$4,$5,$6)
                    ON CONFLICT (account_id,priority) DO UPDATE SET
                        first_response_minutes=excluded.first_response_minutes,
                        resolution_minutes=excluded.resolution_minutes,
                        business_hours=excluded.business_hours,
                        active=excluded.active, updated_at=now()
                    RETURNING *
                    """,
                    values["account_id"], values["priority"],
                    values["first_response_minutes"], values["resolution_minutes"],
                    values["business_hours"], values["active"],
                )
                await connection.execute(
                    "INSERT INTO events (kind, actor, ref_id, detail) "
                    "VALUES ('routing.sla_upserted',$1,$2,$3)",
                    str(actor_id), row["id"], {"priority": values["priority"]},
                )
        return dict(row)


def get_routing_admin_repository() -> PostgresRoutingAdminRepository:
    return PostgresRoutingAdminRepository()


def _actor(user: dict) -> UUID:
    return UUID(str(user["id"]))


@router.get("")
async def routing_config(
    _: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresRoutingAdminRepository = Depends(get_routing_admin_repository),
):
    return await repository.list_config()


@router.post("/teams", status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamIn,
    user: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresRoutingAdminRepository = Depends(get_routing_admin_repository),
):
    return await repository.create_team(
        name=body.name.strip(), description=body.description.strip(), actor_id=_actor(user)
    )


@router.put("/teams/{team_id}/members/{user_id}")
async def upsert_team_member(
    team_id: UUID,
    user_id: UUID,
    body: TeamMemberIn,
    user: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresRoutingAdminRepository = Depends(get_routing_admin_repository),
):
    return await repository.upsert_member(
        team_id=team_id, user_id=user_id, actor_id=_actor(user), **body.model_dump()
    )


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_routing_rule(
    body: RoutingRuleIn,
    user: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresRoutingAdminRepository = Depends(get_routing_admin_repository),
):
    return await repository.create_rule(actor_id=_actor(user), **body.model_dump())


@router.put("/sla-policies")
async def upsert_sla_policy(
    body: SlaPolicyIn,
    user: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresRoutingAdminRepository = Depends(get_routing_admin_repository),
):
    return await repository.upsert_sla(actor_id=_actor(user), **body.model_dump())
