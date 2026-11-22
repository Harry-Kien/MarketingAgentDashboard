"""Ingest inbox nguyên tử: ledger, hội thoại, tin, tệp và event."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from agent import db
from agent.channels.base import THREAD_NHOM, InboundMessage
from agent.channels.ten_khach import la_ten_mac_dinh
from agent.omnichannel.identity import PostgresIdentityTransaction
from agent.omnichannel import sla_muc_tieu
from agent.omnichannel.sla_gio import bieu_thuc_han, tham_so_han


@dataclass(frozen=True, slots=True)
class InboxIngestResult:
    conversation_id: UUID | None
    conversation_status: str | None
    message_id: UUID | None
    duplicate: bool
    should_reply: bool
    conversation_mode: str | None = None
    # `state` chứ không chỉ `status`: hội thoại có thể `resolved` mà
    # `status` lại không phải `closed` (dữ liệu cũ kẹt `escalated`). Đường
    # mở lại hội thoại phải xét `state` — xem `xu_ly_tin_vao.handle_inbound`.
    conversation_state: str | None = None
    # Hội thoại NHÓM — theo tin VÀ theo CSDL. Lấy cả hai: tin chạy lại từ
    # hộp thư bền ghi trước bản có `la_nhom` không mang cờ, nhưng hội thoại
    # đã được đánh dấu nhóm (migration 0051) thì vẫn nhận ra.
    la_nhom: bool = False


class InboxTransaction(Protocol):
    async def claim_webhook(self, message: InboundMessage) -> UUID | None: ...

    async def find_conversation(
        self, account_id: UUID, external_id: str
    ) -> Mapping[str, Any] | None: ...

    async def resolve_contact_point(
        self, message: InboundMessage
    ) -> Mapping[str, Any]: ...

    async def upsert_conversation(
        self, message: InboundMessage, identity: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...

    async def insert_message(
        self, conversation_id: UUID, message: InboundMessage
    ) -> UUID: ...

    async def insert_attachment(
        self,
        message_id: UUID,
        ordinal: int,
        attachment: Mapping[str, Any],
    ) -> None: ...

    async def finish_ingest(
        self,
        receipt_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        account_id: UUID,
    ) -> None: ...


class InboxRepository(Protocol):
    def transaction(self): ...


def normalize_attachment(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Một hình dạng attachment duy nhất cho mọi connector."""
    size = raw.get("size_bytes", raw.get("size"))
    try:
        size = int(size) if size is not None else None
    except (TypeError, ValueError):
        size = None
    return {
        "kind": str(raw.get("loai") or raw.get("type") or "file")[:40],
        "url": str(raw.get("url") or "") or None,
        "original_url": str(
            raw.get("goc") or raw.get("original_url") or ""
        )
        or None,
        "storage_key": str(raw.get("storage_key") or "") or None,
        "mime_type": str(raw.get("mime_type") or "") or None,
        "size_bytes": size if size is None or size >= 0 else None,
        "metadata": dict(raw),
    }


class InboxService:
    def __init__(self, repository: InboxRepository):
        self._repository = repository

    async def ingest(self, message: InboundMessage) -> InboxIngestResult:
        async with self._repository.transaction() as tx:
            receipt_id = await tx.claim_webhook(message)
            if receipt_id is None:
                existing = await tx.find_conversation(
                    message.account_id,
                    message.conversation_ref,
                )
                return InboxIngestResult(
                    conversation_id=existing["id"] if existing else None,
                    conversation_status=existing["status"] if existing else None,
                    message_id=None,
                    duplicate=True,
                    should_reply=False,
                    conversation_mode=existing.get("mode") if existing else None,
                    conversation_state=existing.get("state") if existing else None,
                )

            identity = await tx.resolve_contact_point(message)
            conversation = await tx.upsert_conversation(message, identity)
            message_id = await tx.insert_message(conversation["id"], message)
            for ordinal, raw in enumerate(message.attachments, start=1):
                await tx.insert_attachment(
                    message_id,
                    ordinal,
                    normalize_attachment(raw),
                )
            await tx.finish_ingest(
                receipt_id,
                conversation["id"],
                message_id,
                message.account_id,
            )
            la_nhom = (bool(message.la_nhom)
                       or conversation.get("thread_type") == THREAD_NHOM)
            return InboxIngestResult(
                conversation_id=conversation["id"],
                conversation_status=conversation["status"],
                message_id=message_id,
                duplicate=False,
                should_reply=(not bool((message.meta or {}).get("standby"))
                              and not la_nhom),
                conversation_mode=conversation.get("mode"),
                conversation_state=conversation.get("state"),
                la_nhom=la_nhom,
            )


def _thread_type(message: InboundMessage) -> int | None:
    """
    Loại thread kênh báo kèm tin (Zalo: 0 riêng, 1 nhóm), hoặc None.

    Lưu BỀN vào hội thoại vì adapter GỬI không phải adapter đã ĐỌC tin —
    xem migration 0042 và ZaloPersonalAdapter._loai.
    """
    if message.la_nhom:
        return THREAD_NHOM
    gia_tri = (message.meta or {}).get("thread_type")
    try:
        return int(gia_tri) if gia_tri is not None else None
    except (TypeError, ValueError):
        return None


def _message_hash(message: InboundMessage) -> str:
    canonical = json.dumps(
        {
            "account_id": str(message.account_id),
            "channel": message.channel,
            "conversation_ref": message.conversation_ref,
            "customer_ref": message.customer_ref,
            "text": message.text,
            "attachments": message.attachments,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class PostgresInboxTransaction:
    def __init__(self, connection):
        self._connection = connection

    async def claim_webhook(self, message: InboundMessage) -> UUID | None:
        raw_hash = _message_hash(message)
        metadata = {
            "channel": message.channel,
            "received_at": message.received_at.isoformat(),
        }
        row = await self._connection.fetchrow(
            """
            INSERT INTO webhook_deliveries (
                account_id, dedupe_key, raw_sha256, signature_valid,
                status, attempts, metadata
            ) VALUES ($1,$2,$3,true,'processing',1,$4)
            ON CONFLICT (account_id, dedupe_key) DO NOTHING
            RETURNING id
            """,
            message.account_id,
            message.dedupe_key,
            raw_hash,
            metadata,
        )
        if row:
            return row["id"]
        retried = await self._connection.fetchrow(
            """
            UPDATE webhook_deliveries
            SET status = 'processing', attempts = attempts + 1,
                last_error = NULL, updated_at = now()
            WHERE account_id = $1 AND dedupe_key = $2
              AND raw_sha256 = $3 AND status = 'failed'
            RETURNING id
            """,
            message.account_id,
            message.dedupe_key,
            raw_hash,
        )
        return retried["id"] if retried else None

    async def find_conversation(self, account_id: UUID, external_id: str):
        return await self._connection.fetchrow(
            """
            SELECT id, status, mode, state FROM conversations
            WHERE account_id = $1 AND external_id = $2
            """,
            account_id,
            external_id,
        )

    async def resolve_contact_point(self, message: InboundMessage):
        # Hội thoại nhóm gắn vào một contact CỦA NHÓM (khoá `group:<id>`),
        # không gắn contact của người vừa gõ — xem `ref_nhom` ở channels/base.
        #
        # VÌ SAO VẪN CÓ CONTACT thay vì để trống: `contact_id` của hội thoại
        # được đọc ở việc tự sinh, Customer 360, phân quyền nhìn thấy, gộp
        # khách… Để trống là đổi hợp đồng của cả chục câu truy vấn; một
        # contact riêng cho nhóm giữ nguyên mọi đường đọc, mà điều cần chặn
        # — dính vào hồ sơ riêng của một thành viên — vẫn bị chặn.
        metadata: dict[str, Any] = {"channel": message.channel}
        if message.la_nhom:
            metadata["loai"] = "nhom"
        return await PostgresIdentityTransaction(
            self._connection
        ).resolve_contact_point(
            account_id=message.account_id,
            external_user_id=message.customer_ref,
            display_name=message.customer_name,
            metadata=metadata,
        )

    async def upsert_conversation(
        self,
        message: InboundMessage,
        identity: Mapping[str, Any],
    ):
        # `customer_name` chỉ bị THAY khi tin mang tên thật, hoặc khi danh
        # tính của hội thoại đổi (hội thoại nhóm cũ từng mang id người gửi —
        # tên người gửi ấy là tên SAI, tên dự phòng còn đúng hơn). Tên giữ
        # chỗ ("Khách Zalo", "Nhóm Zalo …ab12") không đè tên đã biết của
        # cùng danh tính: sidecar hụt tên nhóm một lần thì hội thoại không
        # được đổi tên thành dãy số.
        return await self._connection.fetchrow(
            """
            INSERT INTO conversations (
                account_id, channel, external_id, customer_name,
                customer_ref, nen_tang, contact_id, contact_point_id,
                thread_type, first_response_due_at, resolution_due_at
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$11,
                (
                    SELECT {han_dau}
                    FROM sla_policies policy
                    WHERE policy.active = true AND policy.priority = 'normal'
                      AND (policy.account_id = $1 OR policy.account_id IS NULL)
                    ORDER BY (policy.account_id IS NOT NULL) DESC
                    LIMIT 1
                ),
                (
                    SELECT {han_xong}
                    FROM sla_policies policy
                    WHERE policy.active = true AND policy.priority = 'normal'
                      AND (policy.account_id = $1 OR policy.account_id IS NULL)
                    ORDER BY (policy.account_id IS NOT NULL) DESC
                    LIMIT 1
                )
            )
            ON CONFLICT (account_id, external_id) DO UPDATE
            SET customer_name = CASE
                    WHEN $12 AND conversations.customer_ref
                                 IS NOT DISTINCT FROM EXCLUDED.customer_ref
                    THEN conversations.customer_name
                    ELSE EXCLUDED.customer_name END,
                customer_ref = EXCLUDED.customer_ref,
                nen_tang = coalesce(EXCLUDED.nen_tang, conversations.nen_tang),
                contact_id = EXCLUDED.contact_id,
                contact_point_id = EXCLUDED.contact_point_id,
                thread_type = coalesce(EXCLUDED.thread_type, conversations.thread_type),
                updated_at = now()
            RETURNING id, status, mode, state, thread_type
            """.replace("{han_dau}", bieu_thuc_han("first_response_minutes", 9))
               .replace("{han_xong}", bieu_thuc_han("resolution_minutes", 10)),
            message.account_id,
            message.channel,
            message.conversation_ref,
            message.customer_name,
            message.customer_ref,
            (message.meta or {}).get("nen_tang_goc"),
            identity["contact_id"],
            identity["id"],
            *tham_so_han(),
            _thread_type(message),
            la_ten_mac_dinh(message.customer_name),
        )

    async def insert_message(
        self,
        conversation_id: UUID,
        message: InboundMessage,
    ) -> UUID:
        # Người gửi của TỪNG tin (migration 0051). Trong nhóm, hội thoại là
        # của nhóm nên `conversations.customer_name` không nói được ai gõ câu
        # nào — thiếu hai cột này thì mọi thành viên hiện thành một "Khách".
        row = await self._connection.fetchrow(
            """
            INSERT INTO messages (
                conversation_id, role, content, attachments, direction,
                delivery_status, provider_message_id, sender_ref, sender_name
            ) VALUES ($1,'customer',$2,$3,'inbound','received',$4,$5,$6)
            RETURNING id
            """,
            conversation_id,
            message.text,
            message.attachments,
            message.dedupe_key,
            (message.sender_ref or "").strip()[:200] or None,
            (message.sender_name or "").strip()[:200] or None,
        )
        return row["id"]

    async def insert_attachment(
        self,
        message_id: UUID,
        ordinal: int,
        attachment: Mapping[str, Any],
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO attachments (
                message_id, ordinal, kind, url, original_url,
                storage_key, mime_type, size_bytes, metadata
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (message_id, ordinal) DO NOTHING
            """,
            message_id,
            ordinal,
            attachment["kind"],
            attachment["url"],
            attachment["original_url"],
            attachment["storage_key"],
            attachment["mime_type"],
            attachment["size_bytes"],
            attachment["metadata"],
        )

    async def finish_ingest(
        self,
        receipt_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        account_id: UUID,
    ) -> None:
        await self._connection.execute(
            """
            UPDATE conversations
            SET msg_count = msg_count + 1, updated_at = now()
            WHERE id = $1
            """,
            conversation_id,
        )
        await self._connection.execute(
            """
            UPDATE webhook_deliveries
            SET status = 'processed', processed_at = now(), updated_at = now()
            WHERE id = $1 AND status = 'processing'
            """,
            receipt_id,
        )
        await self._connection.execute(
            """
            INSERT INTO inbox_events (account_id, topic, ref_id, payload)
            VALUES ($1,'message.created',$2,$3)
            """,
            account_id,
            conversation_id,
            {"message_id": str(message_id)},
        )
        await self._connection.execute(
            """
            INSERT INTO sla_events (conversation_id, chu_ky, kind, due_at, detail)
            SELECT id, sla_chu_ky, 'started', first_response_due_at,
                   jsonb_build_object(
                       'first_response_due_at', first_response_due_at,
                       'resolution_due_at', resolution_due_at
                   )
            FROM conversations
            WHERE id = $1 AND first_response_due_at IS NOT NULL
            ON CONFLICT (conversation_id, chu_ky, kind) DO NOTHING
            """,
            conversation_id,
        )


class PostgresInboxRepository:
    def __init__(self, pool_provider: Callable[[], Any] = db.pool):
        self._pool_provider = pool_provider

    @asynccontextmanager
    async def transaction(self):
        async with self._pool_provider().acquire() as connection:
            # Lịch/mục tiêu SLA đặt hạn cho hội thoại mới. Làm mới TRƯỚC khi
            # mở giao dịch: tiến trình chỉ giữ vai `api` không chạy vòng
            # canh SLA, nên đây là chỗ nó thấy lịch vừa sửa trên dashboard.
            await sla_muc_tieu.lam_moi_neu_cu(conn=connection)
            async with connection.transaction():
                yield PostgresInboxTransaction(connection)
