"""Customer 360 không merge đoán, merge có version và unmerge đúng snapshot."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from agent.omnichannel.identity import (
    ContactConflict,
    IdentityService,
    InvalidMerge,
)


class _Transaction:
    def __init__(self, store):
        self.store = store

    async def resolve_contact_point(
        self, *, account_id, external_user_id, display_name, metadata
    ):
        key = (account_id, external_user_id)
        if key not in self.store.points:
            contact_id = uuid4()
            point_id = uuid4()
            self.store.contacts[contact_id] = {
                "id": contact_id,
                "display_name": display_name or "Khách",
                "status": "active",
                "version": 1,
            }
            self.store.points[key] = {
                "id": point_id,
                "contact_id": contact_id,
                "account_id": account_id,
            }
        return self.store.points[key]

    async def lock_contacts(self, contact_ids):
        return {
            contact_id: dict(self.store.contacts[contact_id])
            for contact_id in contact_ids
            if contact_id in self.store.contacts
        }

    async def snapshot_contact_refs(self, source_id):
        return {
            "contact_point_ids": [
                point["id"]
                for point in self.store.points.values()
                if point["contact_id"] == source_id
            ],
            "conversation_ids": [
                key
                for key, contact_id in self.store.conversations.items()
                if contact_id == source_id
            ],
        }

    async def apply_merge(self, *, merge_id, source_id, target_id, actor_id,
                          reason, source_version, target_version, snapshot):
        self.store.merges[merge_id] = {
            "id": merge_id,
            "source_contact_id": source_id,
            "target_contact_id": target_id,
            "actor_id": actor_id,
            "reason": reason,
            "snapshot": snapshot,
            "status": "active",
        }
        for point in self.store.points.values():
            if point["id"] in snapshot["contact_point_ids"]:
                point["contact_id"] = target_id
        for conversation_id in snapshot["conversation_ids"]:
            self.store.conversations[conversation_id] = target_id
        self.store.contacts[source_id].update(
            status="merged", merged_into=target_id, version=source_version + 1
        )
        self.store.contacts[target_id]["version"] = target_version + 1

    async def lock_merge(self, merge_id):
        merge = self.store.merges.get(merge_id)
        return dict(merge) if merge else None

    async def apply_unmerge(self, *, merge, actor_id, reason):
        source_id = merge["source_contact_id"]
        target_id = merge["target_contact_id"]
        snapshot = merge["snapshot"]
        for point in self.store.points.values():
            if point["id"] in snapshot["contact_point_ids"]:
                point["contact_id"] = source_id
        for conversation_id in snapshot["conversation_ids"]:
            self.store.conversations[conversation_id] = source_id
        self.store.contacts[source_id].update(
            status="active", merged_into=None,
            version=self.store.contacts[source_id]["version"] + 1,
        )
        self.store.contacts[target_id]["version"] += 1
        self.store.merges[merge["id"]].update(
            status="reverted", reverted_by=actor_id, revert_reason=reason
        )


class _Store:
    def __init__(self):
        self.contacts = {}
        self.points = {}
        self.conversations = {}
        self.merges = {}

    @asynccontextmanager
    async def transaction(self):
        yield _Transaction(self)


def test_resolve_khong_merge_hai_nguoi_chi_vi_cung_ten():
    store = _Store()
    service = IdentityService(store)
    account_id = uuid4()

    first = asyncio.run(
        service.resolve_contact_point(
            account_id=account_id,
            external_user_id="u-1",
            display_name="Nguyễn An",
        )
    )
    second = asyncio.run(
        service.resolve_contact_point(
            account_id=account_id,
            external_user_id="u-2",
            display_name="Nguyễn An",
        )
    )

    assert first.contact_id != second.contact_id
    assert len(store.contacts) == 2


def test_merge_chuyen_dung_refs_va_luu_snapshot_de_unmerge():
    store = _Store()
    service = IdentityService(store)
    source, target, actor = uuid4(), uuid4(), uuid4()
    store.contacts[source] = {"id": source, "status": "active", "version": 2}
    store.contacts[target] = {"id": target, "status": "active", "version": 4}
    source_point = uuid4()
    target_point = uuid4()
    store.points[(uuid4(), "s")] = {
        "id": source_point, "contact_id": source, "account_id": uuid4()
    }
    store.points[(uuid4(), "t")] = {
        "id": target_point, "contact_id": target, "account_id": uuid4()
    }
    source_conversation = uuid4()
    target_conversation = uuid4()
    store.conversations[source_conversation] = source
    store.conversations[target_conversation] = target

    merged = asyncio.run(
        service.merge_contacts(
            source_id=source,
            target_id=target,
            actor_id=actor,
            reason="Khách xác nhận cùng số điện thoại",
            expected_source_version=2,
            expected_target_version=4,
        )
    )

    assert store.points[next(k for k, v in store.points.items() if v["id"] == source_point)]["contact_id"] == target
    assert store.conversations[source_conversation] == target
    assert store.merges[merged.merge_id]["snapshot"] == {
        "contact_point_ids": [source_point],
        "conversation_ids": [source_conversation],
    }

    asyncio.run(
        service.unmerge_contact(
            merge_id=merged.merge_id,
            actor_id=actor,
            reason="Duyệt nhầm hồ sơ",
        )
    )

    assert store.points[next(k for k, v in store.points.items() if v["id"] == source_point)]["contact_id"] == source
    assert store.points[next(k for k, v in store.points.items() if v["id"] == target_point)]["contact_id"] == target
    assert store.conversations[source_conversation] == source
    assert store.conversations[target_conversation] == target


def test_merge_chan_version_cu_va_hai_id_giong_nhau():
    store = _Store()
    service = IdentityService(store)
    source, target = uuid4(), uuid4()
    store.contacts[source] = {"id": source, "status": "active", "version": 2}
    store.contacts[target] = {"id": target, "status": "active", "version": 4}

    with pytest.raises(ContactConflict):
        asyncio.run(
            service.merge_contacts(
                source_id=source,
                target_id=target,
                actor_id=uuid4(),
                reason="đủ căn cứ",
                expected_source_version=1,
                expected_target_version=4,
            )
        )

    with pytest.raises(InvalidMerge):
        asyncio.run(
            service.merge_contacts(
                source_id=source,
                target_id=source,
                actor_id=uuid4(),
                reason="sai",
                expected_source_version=2,
                expected_target_version=2,
            )
        )
