"""Takeover/release có version, account permission và hủy AI job."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from agent.omnichannel.routing import (
    AssignmentDenied,
    ConversationConflict,
    ConversationRoutingService,
)


class _Transaction:
    def __init__(self, store):
        self.store = store

    async def lock_conversation(self, conversation_id):
        row = self.store.conversations.get(conversation_id)
        return dict(row) if row else None

    async def can_assign(self, **kwargs):
        return self.store.can_assign

    async def apply_takeover(self, **kwargs):
        conversation = self.store.conversations[kwargs["conversation_id"]]
        conversation.update(
            mode="human",
            status="escalated",
            assigned_to=kwargs["assignee_id"],
            version=conversation["version"] + 1,
        )
        self.store.cancelled_ai_jobs += 2
        self.store.history.append(("takeover", kwargs))
        return dict(conversation)

    async def can_release(self, **kwargs):
        return self.store.can_release

    async def apply_release(self, **kwargs):
        conversation = self.store.conversations[kwargs["conversation_id"]]
        conversation.update(
            mode="assist",
            status="assist",
            assigned_to=None,
            version=conversation["version"] + 1,
        )
        self.store.history.append(("release", kwargs))
        return dict(conversation)


class _Store:
    def __init__(self):
        self.conversations = {}
        self.can_assign = True
        self.can_release = True
        self.cancelled_ai_jobs = 0
        self.history = []

    @asynccontextmanager
    async def transaction(self):
        yield _Transaction(self)


def _conversation(store, *, mode="auto", version=1):
    conversation_id = uuid4()
    store.conversations[conversation_id] = {
        "id": conversation_id,
        "account_id": uuid4(),
        "mode": mode,
        "status": "auto" if mode == "auto" else "escalated",
        "assigned_to": None,
        "assigned_team_id": None,
        "version": version,
        "first_response_due_at": "fixed-first",
        "resolution_due_at": "fixed-resolution",
    }
    return conversation_id


def test_takeover_chuyen_human_huy_ai_jobs_va_khong_reset_sla():
    store = _Store()
    conversation_id = _conversation(store)
    actor = uuid4()

    result = asyncio.run(
        ConversationRoutingService(store).takeover(
            conversation_id=conversation_id,
            actor_id=actor,
            assignee_id=actor,
            expected_version=1,
            reason="Nhân viên nhận xử lý",
        )
    )

    assert result.mode == "human"
    assert result.assigned_to == actor
    assert store.cancelled_ai_jobs == 2
    assert store.conversations[conversation_id]["first_response_due_at"] == "fixed-first"
    assert store.conversations[conversation_id]["resolution_due_at"] == "fixed-resolution"


def test_takeover_chan_version_cu_va_nguoi_khong_co_quyen_account():
    store = _Store()
    conversation_id = _conversation(store, version=3)
    service = ConversationRoutingService(store)

    with pytest.raises(ConversationConflict):
        asyncio.run(
            service.takeover(
                conversation_id=conversation_id,
                actor_id=uuid4(),
                assignee_id=uuid4(),
                expected_version=2,
                reason="stale",
            )
        )

    store.can_assign = False
    with pytest.raises(AssignmentDenied):
        asyncio.run(
            service.takeover(
                conversation_id=conversation_id,
                actor_id=uuid4(),
                assignee_id=uuid4(),
                expected_version=3,
                reason="không có quyền",
            )
        )


def test_release_ve_assist_chu_khong_tu_bat_ai_auto():
    store = _Store()
    conversation_id = _conversation(store, mode="human", version=5)
    actor = uuid4()
    store.conversations[conversation_id]["assigned_to"] = actor

    result = asyncio.run(
        ConversationRoutingService(store).release(
            conversation_id=conversation_id,
            actor_id=actor,
            expected_version=5,
            reason="Kết thúc ca trực",
        )
    )

    assert result.mode == "assist"
    assert result.assigned_to is None
    assert result.version == 6
