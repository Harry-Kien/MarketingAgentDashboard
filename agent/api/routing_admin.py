"""API quản trị team, rule và SLA cho auto-routing account-aware."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from agent import db

from .routes import can_quyen


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


def canh_bao_thanh_vien(
    rules: list[dict[str, Any]],
    members: list[dict[str, Any]],
    thanh_vien_kenh: set[tuple[Any, Any]],
    ten_kenh: dict[Any, str],
) -> list[dict[str, Any]]:
    """
    Thành viên đội nào KHÔNG BAO GIỜ được giao việc, và vì sao.

    `AutoRoutingTransaction.candidates()` chỉ chọn người vừa ở trong đội vừa
    là thành viên của tài khoản kênh có hội thoại (`account_memberships`).
    Thêm người vào đội mà quên bước kia thì luật vẫn "đang chạy", đội vẫn
    "có người", và hội thoại vẫn nằm chờ mãi — không lỗi nào để mà đi tìm.
    Đo được trên hệ thống thật: một đội, một thành viên, 0 kênh.

    Hàm thuần để test không cần CSDL. Trả về từng cặp (người, đội) một dòng,
    kèm câu người vận hành đọc được.
    """
    ra: list[dict[str, Any]] = []
    luat_theo_doi: dict[Any, list[dict[str, Any]]] = {}
    for r in rules:
        if r.get("active"):
            luat_theo_doi.setdefault(r["team_id"], []).append(r)

    for m in members:
        if m.get("khoa") or not m.get("is_available", True):
            continue
        kenh_cua_nguoi = {tk for (nd, tk) in thanh_vien_kenh if nd == m["user_id"]}
        ten = m.get("ho_ten") or m.get("ten_dang_nhap") or str(m["user_id"])
        if not kenh_cua_nguoi:
            ra.append({
                "user_id": str(m["user_id"]), "team_id": str(m["team_id"]),
                "ho_ten": ten,
                "ly_do": f"{ten} chưa là thành viên kênh nào — bộ định tuyến "
                         "sẽ không bao giờ giao hội thoại cho người này. "
                         "Vào Nhân sự → Kênh được vào.",
            })
            continue
        # Luật trỏ tới một kênh cụ thể mà người này không ở trong kênh ấy.
        thieu = sorted({
            ten_kenh.get(r["account_id"], "kênh đã xoá")
            for r in luat_theo_doi.get(m["team_id"], [])
            if r.get("account_id") is not None
            and r["account_id"] not in kenh_cua_nguoi
        })
        if thieu:
            ra.append({
                "user_id": str(m["user_id"]), "team_id": str(m["team_id"]),
                "ho_ten": ten,
                "ly_do": f"{ten} không ở trong kênh {', '.join(thieu)} — luật "
                         "chia hội thoại của kênh ấy cho đội này sẽ bỏ qua "
                         "người này.",
            })
    return ra


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
            members = await connection.fetch(
                """
                SELECT tm.team_id, tm.user_id, tm.role, tm.max_active,
                       tm.is_available, nd.ho_ten, nd.ten_dang_nhap, nd.khoa
                FROM team_members tm
                JOIN nguoi_dung nd ON nd.id = tm.user_id
                ORDER BY nd.ho_ten, nd.ten_dang_nhap
                """
            )
            thanh_vien_kenh = await connection.fetch(
                "SELECT user_id, account_id FROM account_memberships "
                "WHERE user_id = ANY($1::uuid[])",
                [m["user_id"] for m in members],
            )
            ten_kenh = {
                r["id"]: r["display_name"]
                for r in await connection.fetch(
                    "SELECT id, display_name FROM channel_accounts")
            }
        return {
            "teams": [dict(row) for row in teams],
            "rules": [dict(row) for row in rules],
            "sla_policies": [dict(row) for row in sla],
            "members": [dict(row) for row in members],
            "canh_bao": canh_bao_thanh_vien(
                [dict(r) for r in rules], [dict(m) for m in members],
                {(r["user_id"], r["account_id"]) for r in thanh_vien_kenh},
                ten_kenh,
            ),
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
    _: dict = Depends(can_quyen("dinh_tuyen.doc")),
    repository: PostgresRoutingAdminRepository = Depends(get_routing_admin_repository),
):
    return await repository.list_config()


@router.post("/teams", status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamIn,
    user: dict = Depends(can_quyen("dinh_tuyen.sua")),
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
    user: dict = Depends(can_quyen("dinh_tuyen.sua")),
    repository: PostgresRoutingAdminRepository = Depends(get_routing_admin_repository),
):
    return await repository.upsert_member(
        team_id=team_id, user_id=user_id, actor_id=_actor(user), **body.model_dump()
    )


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_routing_rule(
    body: RoutingRuleIn,
    user: dict = Depends(can_quyen("dinh_tuyen.sua")),
    repository: PostgresRoutingAdminRepository = Depends(get_routing_admin_repository),
):
    return await repository.create_rule(actor_id=_actor(user), **body.model_dump())


@router.put("/sla-policies")
async def upsert_sla_policy(
    body: SlaPolicyIn,
    user: dict = Depends(can_quyen("dinh_tuyen.sua")),
    repository: PostgresRoutingAdminRepository = Depends(get_routing_admin_repository),
):
    return await repository.upsert_sla(actor_id=_actor(user), **body.model_dump())
