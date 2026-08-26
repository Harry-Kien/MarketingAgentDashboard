"""API takeover/release chuyển actor, version và không tin assignee từ client."""
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.inbox import get_routing_service, router
from agent.api.routes import bat_buoc_dang_nhap
from agent.omnichannel.routing import ConversationRoutingState


class _Service:
    def __init__(self):
        self.takeovers = []
        self.releases = []

    async def takeover(self, **kwargs):
        self.takeovers.append(kwargs)
        return ConversationRoutingState(
            kwargs["conversation_id"], "human", "escalated",
            kwargs["assignee_id"], kwargs["team_id"], kwargs["expected_version"] + 1,
        )

    async def release(self, **kwargs):
        self.releases.append(kwargs)
        return ConversationRoutingState(
            kwargs["conversation_id"], "assist", "assist", None, None,
            kwargs["expected_version"] + 1,
        )


def _client():
    app = FastAPI()
    app.include_router(router)
    service = _Service()
    user = {"id": uuid4(), "vai_tro": "nhan_vien"}
    app.dependency_overrides[bat_buoc_dang_nhap] = lambda: user
    app.dependency_overrides[get_routing_service] = lambda: service
    return TestClient(app), service, user


def test_self_takeover_mac_dinh_assignee_la_actor_va_co_expected_version():
    client, service, user = _client()
    conversation_id = uuid4()

    response = client.post(
        f"/api/inbox/conversations/{conversation_id}/takeover",
        json={"expected_version": 4, "reason": "Tôi nhận xử lý"},
    )

    assert response.status_code == 200
    assert service.takeovers[0]["actor_id"] == user["id"]
    assert service.takeovers[0]["assignee_id"] == user["id"]
    assert service.takeovers[0]["expected_version"] == 4
    assert response.json()["mode"] == "human"


def test_release_khong_tu_chuyen_ve_auto():
    client, service, _user = _client()
    conversation_id = uuid4()

    response = client.post(
        f"/api/inbox/conversations/{conversation_id}/release",
        json={"expected_version": 5, "reason": "Kết thúc xử lý"},
    )

    assert response.status_code == 200
    assert service.releases[0]["expected_version"] == 5
    assert response.json()["mode"] == "assist"
