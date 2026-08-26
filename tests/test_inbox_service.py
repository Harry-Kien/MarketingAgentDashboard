"""Ingest inbox phải nguyên tử, idempotent và account-aware."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

from agent.channels.base import InboundMessage
from agent.omnichannel.inbox_service import InboxService


class _Transaction:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def claim_webhook(self, message):
        key = (message.account_id, message.dedupe_key)
        if key in self.store.receipts:
            return None
        receipt_id = uuid4()
        self.store.receipts[key] = receipt_id
        return receipt_id

    async def find_conversation(self, account_id, external_id):
        return self.store.conversations.get((account_id, external_id))

    async def resolve_contact_point(self, message):
        key = (message.account_id, message.customer_ref)
        return self.store.contact_points.setdefault(
            key,
            {"id": uuid4(), "contact_id": uuid4()},
        )

    async def upsert_conversation(self, message, identity):
        key = (message.account_id, message.conversation_ref)
        return self.store.conversations.setdefault(
            key,
            {
                "id": uuid4(),
                "status": "auto",
                "account_id": message.account_id,
                "contact_id": identity["contact_id"],
                "contact_point_id": identity["id"],
            },
        )

    async def insert_message(self, conversation_id, message):
        message_id = uuid4()
        self.store.messages.append(
            {
                "id": message_id,
                "conversation_id": conversation_id,
                "account_id": message.account_id,
                "content": message.text,
            }
        )
        return message_id

    async def insert_attachment(self, message_id, ordinal, attachment):
        self.store.attachments.append(
            {"message_id": message_id, "ordinal": ordinal, **attachment}
        )

    async def finish_ingest(self, receipt_id, conversation_id, message_id, account_id):
        self.store.events.append((account_id, conversation_id, message_id))


class _Store:
    def __init__(self):
        self.receipts = {}
        self.conversations = {}
        self.contact_points = {}
        self.messages = []
        self.attachments = []
        self.events = []

    def transaction(self):
        return _Transaction(self)


def _message(account_id=None, dedupe="m1", attachments=None, standby=False):
    return InboundMessage(
        account_id=account_id or uuid4(),
        channel="messenger",
        conversation_ref="same-external-id",
        customer_ref="customer-1",
        customer_name="Khách",
        text="Xin chào",
        dedupe_key=dedupe,
        received_at=datetime.now(timezone.utc),
        attachments=attachments or [],
        meta={"standby": standby},
    )


def test_duplicate_khong_nhan_doi_message_event_hoac_attachment():
    store = _Store()
    service = InboxService(store)
    message = _message(
        attachments=[{"loai": "image", "url": "https://cdn/a.jpg"}]
    )

    first = asyncio.run(service.ingest(message))
    duplicate = asyncio.run(service.ingest(message))

    assert first.duplicate is False
    assert duplicate.duplicate is True
    assert len(store.messages) == 1
    assert len(store.attachments) == 1
    assert len(store.events) == 1


def test_cung_external_id_o_hai_account_khong_bi_nhap_lam_mot():
    store = _Store()
    service = InboxService(store)
    account_a = uuid4()
    account_b = uuid4()

    first = asyncio.run(service.ingest(_message(account_a, "m1")))
    second = asyncio.run(service.ingest(_message(account_b, "m2")))

    assert first.conversation_id != second.conversation_id
    assert len(store.conversations) == 2
    assert len(store.contact_points) == 2
    contact_ids = {row["contact_id"] for row in store.conversations.values()}
    assert len(contact_ids) == 2


def test_hai_conversation_cung_customer_trong_mot_account_dung_chung_contact():
    store = _Store()
    service = InboxService(store)
    account_id = uuid4()
    first = _message(account_id, "m1")
    second = _message(account_id, "m2")
    second = InboundMessage(
        account_id=second.account_id,
        channel=second.channel,
        conversation_ref="conversation-moi",
        customer_ref=second.customer_ref,
        customer_name=second.customer_name,
        text=second.text,
        dedupe_key=second.dedupe_key,
        received_at=second.received_at,
        attachments=second.attachments,
        meta=second.meta,
    )

    asyncio.run(service.ingest(first))
    asyncio.run(service.ingest(second))

    assert len(store.contact_points) == 1
    assert len({row["contact_id"] for row in store.conversations.values()}) == 1


def test_postgres_upsert_khoi_tao_sla_nhung_on_conflict_khong_reset_deadline():
    from agent.omnichannel.inbox_service import PostgresInboxTransaction

    class Connection:
        def __init__(self):
            self.sql = ""

        async def fetchrow(self, sql, *args):
            self.sql = sql
            return {"id": uuid4(), "status": "auto", "mode": "auto"}

    connection = Connection()
    transaction = PostgresInboxTransaction(connection)
    message = _message()
    asyncio.run(
        transaction.upsert_conversation(
            message, {"id": uuid4(), "contact_id": uuid4()}
        )
    )

    sql = connection.sql.lower()
    assert "sla_policies" in sql
    conflict_update = sql.split("on conflict", 1)[1]
    assert "first_response_due_at =" not in conflict_update
    assert "resolution_due_at =" not in conflict_update


def test_attachment_duoc_chuan_hoa_va_giu_ordinal():
    store = _Store()
    message = _message(
        attachments=[
            {"loai": "image", "url": "https://cdn/a.jpg", "goc": "https://origin/a"},
            {"type": "file", "url": "https://cdn/b.pdf", "mime_type": "application/pdf"},
        ]
    )

    asyncio.run(InboxService(store).ingest(message))

    assert [item["ordinal"] for item in store.attachments] == [1, 2]
    assert store.attachments[0]["kind"] == "image"
    assert store.attachments[0]["original_url"] == "https://origin/a"
    assert store.attachments[1]["mime_type"] == "application/pdf"


def test_standby_duoc_luu_nhung_khong_cho_ai_reply():
    result = asyncio.run(InboxService(_Store()).ingest(_message(standby=True)))

    assert result.should_reply is False
