from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.routes import bat_buoc_quan_tri
from agent.api.routing_admin import get_routing_admin_repository, router


class _Repository:
    def __init__(self):
        self.calls = []

    async def list_config(self):
        return {"teams": [], "rules": [], "sla_policies": []}

    async def create_team(self, **kwargs):
        self.calls.append(("team", kwargs))
        return {"id": uuid4(), **kwargs, "status": "active"}

    async def upsert_member(self, **kwargs):
        self.calls.append(("member", kwargs))
        return kwargs

    async def create_rule(self, **kwargs):
        self.calls.append(("rule", kwargs))
        return {"id": uuid4(), **kwargs}

    async def upsert_sla(self, **kwargs):
        self.calls.append(("sla", kwargs))
        return {"id": uuid4(), **kwargs}


def _client():
    app = FastAPI()
    app.include_router(router)
    repository = _Repository()
    user = {"id": uuid4(), "vai_tro": "quan_tri"}
    app.dependency_overrides[bat_buoc_quan_tri] = lambda: user
    app.dependency_overrides[get_routing_admin_repository] = lambda: repository
    return TestClient(app), repository


def test_admin_tao_team_member_rule_va_sla_account_aware():
    client, repository = _client()
    team = client.post("/api/routing/teams", json={"name": "Tư vấn", "description": "Sales"})
    team_id = team.json()["id"]
    user_id, account_id = str(uuid4()), str(uuid4())
    member = client.put(f"/api/routing/teams/{team_id}/members/{user_id}", json={"role": "agent", "skills": ["sales"], "max_active": 12, "is_available": True})
    rule = client.post("/api/routing/rules", json={"account_id": account_id, "team_id": team_id, "priority": "high", "required_skills": ["sales"], "weight": 100})
    sla = client.put("/api/routing/sla-policies", json={"account_id": account_id, "priority": "high", "first_response_minutes": 5, "resolution_minutes": 120, "business_hours": {}})

    assert [team.status_code, member.status_code, rule.status_code, sla.status_code] == [201, 200, 201, 200]
    assert [call[0] for call in repository.calls] == ["team", "member", "rule", "sla"]
    assert repository.calls[2][1]["actor_id"]
