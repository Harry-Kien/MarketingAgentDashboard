from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.retention import get_retention_repository, router
from agent.api.routes import bat_buoc_quan_tri


class _Repository:
    def __init__(self):
        self.calls = []

    async def list_jobs(self):
        return []

    async def approve(self, job_id, *, actor_id):
        self.calls.append(("approve", job_id, actor_id))
        return {"id": job_id, "status": "approved", "dry_run": True}

    async def cancel(self, job_id, *, actor_id):
        self.calls.append(("cancel", job_id, actor_id))
        return {"id": job_id, "status": "cancelled"}

    async def execute_dry_run(self, job_id, *, actor_id):
        self.calls.append(("dry_run", job_id, actor_id))
        return {"id": job_id, "status": "completed", "result": {"messages": 4}}


def test_retention_can_admin_approve_va_dry_run_co_audit_actor():
    app = FastAPI()
    app.include_router(router)
    repository = _Repository()
    user = {"id": uuid4(), "vai_tro": "quan_tri"}
    app.dependency_overrides[bat_buoc_quan_tri] = lambda: user
    app.dependency_overrides[get_retention_repository] = lambda: repository
    client = TestClient(app)
    job_id = uuid4()

    approved = client.post(f"/api/data-retention/jobs/{job_id}/approve")
    executed = client.post(f"/api/data-retention/jobs/{job_id}/execute-dry-run")

    assert approved.json()["status"] == "approved"
    assert executed.json()["result"] == {"messages": 4}
    assert [call[0] for call in repository.calls] == ["approve", "dry_run"]
    assert all(call[2] == user["id"] for call in repository.calls)
