from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from agent.omnichannel.auto_routing import AutoRoutingService, AutoRoutingWorker


class _Tx:
    def __init__(self, store):
        self.store = store

    async def lock_conversation(self, conversation_id):
        return dict(self.store.conversation)

    async def da_co_nguoi_vao(self, conversation_id):
        self.store.hoi_nguoi_vao += 1
        return self.store.nguoi_vao

    async def matching_rule(self, **_kwargs):
        return self.store.rule

    async def candidates(self, **_kwargs):
        return self.store.candidates

    async def routing_cursor(self, _rule_id):
        return self.store.cursor

    async def apply_auto_assignment(self, **kwargs):
        self.store.applied = kwargs
        return {**self.store.conversation, "assigned_to": kwargs["assignee_id"], "assigned_team_id": kwargs["team_id"], "version": 2}


class _Store:
    def __init__(self):
        self.conversation = {
            "id": uuid4(), "account_id": uuid4(), "priority": "normal",
            "mode": "assist", "state": "open", "status": "assist",
            "assigned_to": None, "assigned_team_id": None, "version": 1,
        }
        self.rule = {"id": uuid4(), "team_id": uuid4(), "required_skills": ["sales"]}
        self.candidates = []
        self.cursor = None
        self.applied = None
        self.nguoi_vao = False
        self.hoi_nguoi_vao = 0

    @asynccontextmanager
    async def transaction(self):
        yield _Tx(self)


def test_auto_route_chon_tai_nhe_nhat_va_round_robin_khi_bang_tai():
    store = _Store()
    a, b, overloaded = uuid4(), uuid4(), uuid4()
    ordered = sorted([a, b], key=str)
    store.cursor = ordered[0]
    store.candidates = [
        {"user_id": ordered[0], "active_count": 2, "max_active": 10},
        {"user_id": ordered[1], "active_count": 2, "max_active": 10},
        {"user_id": overloaded, "active_count": 9, "max_active": 10},
    ]

    result = asyncio.run(AutoRoutingService(store).route(store.conversation["id"]))

    assert result is not None
    assert result.assigned_to == ordered[1]
    assert store.applied["source"] == "auto"


def test_auto_route_fail_closed_khi_nguoi_dang_giu_hoac_khong_co_agent():
    store = _Store()
    store.conversation["mode"] = "human"
    store.conversation["assigned_to"] = uuid4()       # đồng nghiệp đang giữ
    store.candidates = [{"user_id": uuid4(), "active_count": 0, "max_active": 5}]
    assert asyncio.run(AutoRoutingService(store).route(store.conversation["id"])) is None

    store.conversation["assigned_to"] = None
    store.conversation["mode"] = "assist"
    store.candidates = []
    assert asyncio.run(AutoRoutingService(store).route(store.conversation["id"])) is None
    assert store.applied is None


def test_ai_chuyen_nguoi_chua_ai_giu_thi_duoc_giao():
    """
    Trước 20.11.2026 mọi `mode='human'` bị bỏ qua: khách AI đã chuyển người
    chỉ có một công việc không ai nhận. Nay giao theo đúng quy tắc định tuyến.
    """
    store = _Store()
    store.conversation.update(mode="human", status="escalated")
    nguoi = uuid4()
    store.candidates = [{"user_id": nguoi, "active_count": 0, "max_active": 5}]
    kq = asyncio.run(AutoRoutingService(store).route(store.conversation["id"]))
    assert kq is not None and kq.assigned_to == nguoi
    assert store.hoi_nguoi_vao == 1


def test_human_chua_giao_nhung_nhan_vien_da_vao_tra_loi_thi_khong_giao():
    store = _Store()
    store.conversation.update(mode="human", status="escalated")
    store.nguoi_vao = True
    store.candidates = [{"user_id": uuid4(), "active_count": 0, "max_active": 5}]
    assert asyncio.run(AutoRoutingService(store).route(store.conversation["id"])) is None
    assert store.applied is None


def test_hoi_thoai_ai_khong_hoi_nguoi_vao():
    """Hội thoại AI không tốn thêm truy vấn: chỉ `human` mới cần xét."""
    store = _Store()
    store.candidates = [{"user_id": uuid4(), "active_count": 0, "max_active": 5}]
    asyncio.run(AutoRoutingService(store).route(store.conversation["id"]))
    assert store.hoi_nguoi_vao == 0


def test_worker_route_hang_doi_va_ghi_heartbeat():
    class QueueRepository:
        def __init__(self):
            self.ids = [uuid4(), uuid4()]
            self.heartbeats = []

        async def pending_conversation_ids(self, limit=50):
            return self.ids

        async def heartbeat(self, worker_id):
            self.heartbeats.append(worker_id)

    class Service:
        def __init__(self):
            self.ids = []

        async def route(self, conversation_id):
            self.ids.append(conversation_id)
            return object() if len(self.ids) == 1 else None

    repository, service = QueueRepository(), Service()
    result = asyncio.run(AutoRoutingWorker(repository, service).scan_once("routing-1"))

    assert result == {"examined": 2, "assigned": 1}
    assert service.ids == repository.ids
    assert repository.heartbeats == ["routing-1"]
