"""Ghi outbound message và outbox job cùng transaction."""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from agent import db


class ConversationNotFound(RuntimeError):
    pass


class OutboundMessageNotFound(RuntimeError):
    pass


class OutboundBlocked(RuntimeError):
    """Policy hội thoại chặn loại outbound này."""


# Mục đích của một tin đi ra. Quyết định nó có phải hỏi đồng ý hay không.
#
# Mặc định là `transactional` CÓ CHỦ Ý: tuyệt đại đa số tin trong hệ thống
# này là trả lời khách đang nhắn, xác nhận đơn, báo mã vận đơn — những thứ
# khách đã yêu cầu bằng chính hành động của họ. Bắt mọi lời gọi phải khai
# `purpose` thì chỗ nào quên sẽ vỡ, mà chỗ hay quên nhất lại là chỗ vô hại
# nhất.
#
# Đổi lại, người thêm đường gửi quảng cáo mới PHẢI tự khai `purpose`. Đó là
# đánh đổi có ý thức: rủi ro nằm ở chỗ ít người đụng tới và dễ soi lại,
# thay vì rải đều khắp nơi.
MUC_DICH_MAC_DINH = "transactional"

# Chỉ những mục đích trong đây mới cần đồng ý. Danh sách nằm ở MỘT chỗ để
# khi luật đổi thì sửa một dòng, không phải đi tìm khắp mã.
CAN_DONG_Y = frozenset({"marketing", "promotional", "newsletter"})


def handover_idempotency_key(conversation_id: UUID, version: int) -> str:
    """Một thông báo mỗi escalation transition, không phải một lần suốt đời."""
    return f"handover:{conversation_id}:v{max(1, int(version))}"


@dataclass(frozen=True, slots=True)
class QueuedOutbound:
    job_id: UUID
    message_id: UUID
    account_id: UUID
    payload: Mapping[str, Any]
    status: str = "queued"
    duplicate: bool = False


class OutboundTransaction(Protocol):
    async def get_conversation(self, conversation_id: UUID): ...

    async def get_message(self, message_id: UUID, conversation_id: UUID): ...

    async def find_existing(self, account_id: UUID, idempotency_key: str): ...

    async def lock_idempotency(
        self, account_id: UUID, idempotency_key: str
    ) -> None: ...

    async def insert_message(
        self,
        conversation_id: UUID,
        role: str,
        text: str,
        idempotency_key: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> UUID: ...

    async def insert_job(
        self,
        account_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        kind: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ): ...

    async def insert_attachment(
        self,
        message_id: UUID,
        kind: str,
        path: str,
        caption: str,
        position: int = 0,
    ) -> None: ...

    async def finish_enqueue(
        self,
        account_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        job_id: UUID,
    ) -> None: ...

    async def mark_message_queued(
        self, message_id: UUID, idempotency_key: str
    ) -> None: ...

    async def finish_existing_enqueue(
        self,
        account_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        job_id: UUID,
    ) -> None: ...


class OutboundRepository(Protocol):
    def transaction(self): ...


def _queued_from_existing(row: Mapping[str, Any]) -> QueuedOutbound:
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return QueuedOutbound(
        job_id=row["job_id"],
        message_id=row["message_id"],
        account_id=row["account_id"],
        payload=dict(payload),
        duplicate=True,
    )


class OutboundService:
    def __init__(self, repository: OutboundRepository):
        self._repository = repository

    @staticmethod
    def _ensure_role_allowed(conversation: Mapping[str, Any], role: str) -> None:
        if role == "agent" and (
            conversation.get("mode") == "human"
            or conversation.get("status") == "escalated"
        ):
            raise OutboundBlocked("AI đã dừng vì người thật đang tiếp quản")

    @staticmethod
    async def _ensure_consent_allowed(
        tx: Any,
        conversation: Mapping[str, Any],
        purpose: str,
    ) -> None:
        """
        Mục đích cần đồng ý thì phải CÓ đồng ý, không phải chỉ không bị từ chối.

        VÌ SAO CHỐT NẰM Ở ĐÂY, KHÔNG NẰM Ở GIAO DIỆN
        ---------------------------------------------
        `queue_text` là cửa duy nhất mọi tin đi ra đều qua: dashboard, agent,
        worker, API quản trị. Đặt chốt ở giao diện là chỉ khoá một trong bốn
        cửa, và ba cửa còn lại không có gì báo khi chúng gửi sai.

        VÌ SAO MẶC ĐỊNH LÀ CHẶN, KHÔNG PHẢI CHO QUA
        --------------------------------------------
        Thiếu bản ghi đồng ý nghĩa là ta KHÔNG BIẾT khách có đồng ý không,
        chứ không phải khách đã đồng ý. Với tin quảng cáo, không biết thì
        không được gửi — luật đòi opt-in, và im lặng không phải là đồng ý.

        Tin giao dịch (mã vận đơn, xác nhận đơn) KHÔNG đi qua chốt này: khách
        đặt hàng là đã yêu cầu chúng. Chặn nhầm nhóm đó thì để khách không
        biết đơn của mình đi tới đâu, và đó cũng là một kiểu hại khách.
        """
        if purpose not in CAN_DONG_Y:
            return
        contact_id = conversation.get("contact_id")
        if contact_id is None:
            # Không truy được người nhận thì không kiểm được đồng ý. Fail
            # closed: thà không gửi còn hơn gửi cho người chưa cho phép.
            raise OutboundBlocked(
                f"Chưa gắn contact cho hội thoại nên không kiểm được đồng ý "
                f"'{purpose}'"
            )
        trang_thai = await tx.get_consent(
            contact_id, purpose, conversation["account_id"]
        )
        if trang_thai != "granted":
            raise OutboundBlocked(
                f"Khách chưa đồng ý nhận nội dung '{purpose}'"
                if trang_thai is None
                else f"Khách đã từ chối nhận nội dung '{purpose}'"
            )

    async def queue_text(
        self,
        *,
        conversation_id: UUID,
        role: str,
        text: str,
        idempotency_key: str,
        metadata: Mapping[str, Any] | None = None,
        purpose: str = MUC_DICH_MAC_DINH,
    ) -> QueuedOutbound:
        key = idempotency_key.strip()
        if not key:
            raise ValueError("outbound idempotency key không được để trống")
        if role not in {"agent", "staff", "system"}:
            raise ValueError("outbound role không hợp lệ")
        if not text.strip():
            raise ValueError("nội dung outbound không được để trống")

        async with self._repository.transaction() as tx:
            conversation = await tx.get_conversation(conversation_id)
            if conversation is None:
                raise ConversationNotFound("không tìm thấy hội thoại")
            self._ensure_role_allowed(conversation, role)
            await self._ensure_consent_allowed(tx, conversation, purpose)
            account_id = conversation["account_id"]
            await tx.lock_idempotency(account_id, key)
            existing = await tx.find_existing(account_id, key)
            if existing is not None:
                return _queued_from_existing(existing)

            payload = {
                "conversation_ref": conversation["external_id"],
                "text": text,
            }
            message_id = await tx.insert_message(
                conversation_id,
                role,
                text,
                key,
                metadata,
            )
            job = await tx.insert_job(
                account_id,
                conversation_id,
                message_id,
                "send_text",
                payload,
                key,
            )
            await tx.finish_enqueue(
                account_id,
                conversation_id,
                message_id,
                job["job_id"],
            )
            return QueuedOutbound(
                job_id=job["job_id"],
                message_id=message_id,
                account_id=account_id,
                payload=payload,
            )

    async def queue_existing_text(
        self,
        *,
        conversation_id: UUID,
        message_id: UUID,
        text: str,
        idempotency_key: str,
    ) -> QueuedOutbound:
        key = idempotency_key.strip()
        if not key:
            raise ValueError("outbound idempotency key không được để trống")
        async with self._repository.transaction() as tx:
            conversation = await tx.get_conversation(conversation_id)
            if conversation is None:
                raise ConversationNotFound("không tìm thấy hội thoại")
            account_id = conversation["account_id"]
            await tx.lock_idempotency(account_id, key)
            existing = await tx.find_existing(account_id, key)
            if existing is not None:
                return _queued_from_existing(existing)
            message = await tx.get_message(message_id, conversation_id)
            if message is None:
                raise OutboundMessageNotFound("không tìm thấy bản nháp")

            payload = {
                "conversation_ref": conversation["external_id"],
                "text": text,
            }
            await tx.mark_message_queued(message_id, key)
            job = await tx.insert_job(
                account_id,
                conversation_id,
                message_id,
                "send_text",
                payload,
                key,
            )
            await tx.finish_existing_enqueue(
                account_id,
                conversation_id,
                message_id,
                job["job_id"],
            )
            return QueuedOutbound(
                job_id=job["job_id"],
                message_id=message_id,
                account_id=account_id,
                payload=payload,
            )

    async def queue_file(
        self,
        *,
        conversation_id: UUID,
        role: str,
        path: str,
        caption: str,
        idempotency_key: str,
        kind: str = "image",
        purpose: str = MUC_DICH_MAC_DINH,
    ) -> QueuedOutbound:
        key = idempotency_key.strip()
        if not key:
            raise ValueError("outbound idempotency key không được để trống")
        if role not in {"agent", "staff", "system"}:
            raise ValueError("outbound role không hợp lệ")
        if not path.strip():
            raise ValueError("đường dẫn tệp outbound không được để trống")

        async with self._repository.transaction() as tx:
            conversation = await tx.get_conversation(conversation_id)
            if conversation is None:
                raise ConversationNotFound("không tìm thấy hội thoại")
            self._ensure_role_allowed(conversation, role)
            await self._ensure_consent_allowed(tx, conversation, purpose)
            account_id = conversation["account_id"]
            await tx.lock_idempotency(account_id, key)
            existing = await tx.find_existing(account_id, key)
            if existing is not None:
                return _queued_from_existing(existing)

            visible_text = caption.strip() or "[Tệp đính kèm]"
            payload = {
                "conversation_ref": conversation["external_id"],
                "path": path,
                "caption": caption,
            }
            message_id = await tx.insert_message(
                conversation_id,
                role,
                visible_text,
                key,
                None,
            )
            await tx.insert_attachment(
                message_id,
                kind,
                path,
                caption,
                0,
            )
            job = await tx.insert_job(
                account_id,
                conversation_id,
                message_id,
                "send_file",
                payload,
                key,
            )
            await tx.finish_enqueue(
                account_id,
                conversation_id,
                message_id,
                job["job_id"],
            )
            return QueuedOutbound(
                job_id=job["job_id"],
                message_id=message_id,
                account_id=account_id,
                payload=payload,
            )


class PostgresOutboundTransaction:
    def __init__(self, connection):
        self._connection = connection

    async def get_conversation(self, conversation_id: UUID):
        return await self._connection.fetchrow(
            """
            SELECT id, account_id, external_id, status, mode, contact_id
            FROM conversations WHERE id = $1
            FOR SHARE
            """,
            conversation_id,
        )

    async def get_consent(
        self,
        contact_id: UUID,
        purpose: str,
        account_id: UUID,
    ) -> str | None:
        """
        Trạng thái đồng ý, ưu tiên bản ghi RIÊNG cho tài khoản.

        `contact_consents.account_id` cho phép NULL, nghĩa là "đồng ý ở mọi
        kênh". Khách có thể đồng ý toàn cục nhưng rút riêng ở một kênh —
        `ORDER BY account_id NULLS LAST` đảm bảo bản ghi riêng thắng bản ghi
        toàn cục, chứ không phải bản nào ra trước thì thắng.
        """
        row = await self._connection.fetchrow(
            """
            SELECT status
            FROM contact_consents
            WHERE contact_id = $1
              AND purpose = $2
              AND (account_id = $3 OR account_id IS NULL)
            ORDER BY account_id NULLS LAST
            LIMIT 1
            """,
            contact_id,
            purpose,
            account_id,
        )
        return None if row is None else str(row["status"])

    async def get_message(self, message_id: UUID, conversation_id: UUID):
        return await self._connection.fetchrow(
            """
            SELECT id, conversation_id, content, delivery_status
            FROM messages
            WHERE id = $1 AND conversation_id = $2
            FOR UPDATE
            """,
            message_id,
            conversation_id,
        )

    async def find_existing(self, account_id: UUID, idempotency_key: str):
        return await self._connection.fetchrow(
            """
            SELECT job.id AS job_id, job.message_id, job.account_id, job.payload
            FROM outbox_jobs AS job
            WHERE job.account_id = $1 AND job.idempotency_key = $2
            """,
            account_id,
            idempotency_key,
        )

    async def lock_idempotency(
        self,
        account_id: UUID,
        idempotency_key: str,
    ) -> None:
        # Khoá theo (account,key) nằm trong transaction: hai request đồng thời
        # sẽ tuần tự hoá trước bước kiểm tra, không đua nhau tạo hai message.
        #
        # `str(account_id)` KHÔNG thừa: SQL ép `$1::text`, nên asyncpg suy ra
        # tham số phải là chuỗi và từ chối đối tượng UUID ngay lúc bind —
        # trước cả khi câu lệnh chạm tới Postgres. Mọi fake trong test đều
        # chỉ ghi tham số vào một list nên không chạm bộ mã hoá của driver;
        # lỗi này lọt qua 767 test và chỉ nổ khi người thật bấm "Duyệt và
        # gửi" cho một hội thoại khách thật.
        await self._connection.execute(
            """
            SELECT pg_advisory_xact_lock(
                hashtextextended($1::text || ':' || $2, 0)
            )
            """,
            str(account_id),
            idempotency_key,
        )

    async def insert_message(
        self,
        conversation_id: UUID,
        role: str,
        text: str,
        idempotency_key: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> UUID:
        meta = dict(metadata or {})
        row = await self._connection.fetchrow(
            """
            INSERT INTO messages (
                conversation_id, role, content, delivered, direction,
                delivery_status, client_idempotency_key, grounded, confidence,
                sources, model, tokens_in, tokens_out, cache_read, cost_usd,
                latency_ms
            ) VALUES (
                $1,$2,$3,false,'outbound','queued',$4,$5,$6,$7,$8,$9,$10,$11,$12,$13
            )
            RETURNING id
            """,
            conversation_id,
            role,
            text,
            idempotency_key,
            bool(meta.get("grounded", False)),
            float(meta.get("confidence", 0.0)),
            list(meta.get("sources") or []),
            str(meta.get("model", "")),
            int(meta.get("tokens_in", 0)),
            int(meta.get("tokens_out", 0)),
            int(meta.get("cache_read", 0)),
            float(meta.get("cost_usd", 0.0)),
            int(meta.get("latency_ms", 0)),
        )
        return row["id"]

    async def insert_job(
        self,
        account_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        kind: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ):
        row = await self._connection.fetchrow(
            """
            INSERT INTO outbox_jobs (
                account_id, conversation_id, message_id, kind,
                payload, idempotency_key
            ) VALUES ($1,$2,$3,$4,$5,$6)
            RETURNING id
            """,
            account_id,
            conversation_id,
            message_id,
            kind,
            dict(payload),
            idempotency_key,
        )
        return {"job_id": row["id"]}

    async def insert_attachment(
        self,
        message_id: UUID,
        kind: str,
        path: str,
        caption: str,
        position: int = 0,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO attachments (
                message_id, ordinal, kind, storage_key, metadata
            ) VALUES ($1,$2,$3,$4,$5)
            ON CONFLICT (message_id, ordinal) DO NOTHING
            """,
            message_id,
            position + 1,
            kind,
            path,
            {"caption": caption},
        )

    async def finish_enqueue(
        self,
        account_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        job_id: UUID,
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
            INSERT INTO inbox_events (account_id, topic, ref_id, payload)
            VALUES ($1,'outbox.queued',$2,$3)
            """,
            account_id,
            conversation_id,
            {"message_id": str(message_id), "job_id": str(job_id)},
        )

    async def mark_message_queued(
        self,
        message_id: UUID,
        idempotency_key: str,
    ) -> None:
        await self._connection.execute(
            """
            UPDATE messages
            SET role = 'staff', delivered = false, delivery_status = 'queued',
                client_idempotency_key = $2
            WHERE id = $1
            """,
            message_id,
            idempotency_key,
        )

    async def finish_existing_enqueue(
        self,
        account_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        job_id: UUID,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO inbox_events (account_id, topic, ref_id, payload)
            VALUES ($1,'outbox.queued',$2,$3)
            """,
            account_id,
            conversation_id,
            {"message_id": str(message_id), "job_id": str(job_id)},
        )


class PostgresOutboundRepository:
    def __init__(self, pool_provider: Callable[[], Any] = db.pool):
        self._pool_provider = pool_provider

    @asynccontextmanager
    async def transaction(self):
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                yield PostgresOutboundTransaction(connection)
