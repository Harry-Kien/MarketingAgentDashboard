"""Mọi outbound phải được ghi message + outbox trước khi gọi provider."""
from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import pytest

from agent.omnichannel.outbound_service import (
    OutboundBlocked,
    OutboundService,
    PostgresOutboundRepository,
    handover_idempotency_key,
)


class _Transaction:
    def __init__(self, store):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get_conversation(self, conversation_id):
        return self.store.conversations.get(conversation_id)

    async def get_message(self, message_id, conversation_id):
        message = self.store.existing_messages.get(message_id)
        if message and message["conversation_id"] == conversation_id:
            return message
        return None

    async def find_existing(self, account_id, idempotency_key):
        return self.store.jobs.get((account_id, idempotency_key))

    async def lock_idempotency(self, account_id, idempotency_key):
        self.store.locks.append((account_id, idempotency_key))

    async def insert_message(
        self, conversation_id, role, text, idempotency_key, metadata=None
    ):
        message_id = uuid4()
        self.store.messages.append(
            {
                "id": message_id,
                "conversation_id": conversation_id,
                "role": role,
                "text": text,
                "status": "queued",
                "idempotency_key": idempotency_key,
                "metadata": dict(metadata or {}),
            }
        )
        return message_id

    async def insert_job(
        self,
        account_id,
        conversation_id,
        message_id,
        kind,
        payload,
        idempotency_key,
    ):
        job_id = uuid4()
        row = {
            "job_id": job_id,
            "message_id": message_id,
            "account_id": account_id,
            "payload": payload,
            "duplicate": False,
        }
        self.store.jobs[(account_id, idempotency_key)] = row
        return row

    async def insert_attachment(
        self, message_id, kind, path, caption, position=0
    ):
        self.store.attachments.append(
            (message_id, kind, path, caption, position)
        )

    async def finish_enqueue(self, account_id, conversation_id, message_id, job_id):
        self.store.events.append((account_id, conversation_id, message_id, job_id))

    async def mark_message_queued(self, message_id, idempotency_key):
        self.store.queued_existing.append((message_id, idempotency_key))

    async def finish_existing_enqueue(
        self, account_id, conversation_id, message_id, job_id
    ):
        self.store.events.append((account_id, conversation_id, message_id, job_id))

    async def get_consent(self, contact_id, purpose, account_id):
        return self.store.consents.get((contact_id, purpose, account_id))


class _Store:
    def __init__(self):
        self.conversations = {}
        self.messages = []
        self.jobs = {}
        self.events = []
        self.queued_existing = []
        self.existing_messages = {}
        self.locks = []
        self.attachments = []
        # (contact_id, purpose, account_id) -> "granted" | "revoked"
        self.consents = {}

    def transaction(self):
        return _Transaction(self)


def test_queue_text_lay_account_va_external_ref_tu_conversation():
    store = _Store()
    conversation_id = uuid4()
    account_id = uuid4()
    store.conversations[conversation_id] = {
        "id": conversation_id,
        "account_id": account_id,
        "external_id": "customer-1",
        "status": "auto",
    }

    queued = asyncio.run(
        OutboundService(store).queue_text(
            conversation_id=conversation_id,
            role="staff",
            text="Đã nhận ạ",
            idempotency_key="staff-request-1",
        )
    )

    assert queued.account_id == account_id
    assert queued.status == "queued"
    assert queued.payload == {"conversation_ref": "customer-1", "text": "Đã nhận ạ"}
    assert store.messages[0]["status"] == "queued"
    assert len(store.events) == 1


def test_queue_ai_text_luu_metadata_cung_message_va_job():
    store = _Store()
    conversation_id = uuid4()
    account_id = uuid4()
    store.conversations[conversation_id] = {
        "id": conversation_id,
        "account_id": account_id,
        "external_id": "customer-1",
        "status": "auto",
    }
    metadata = {
        "grounded": True,
        "confidence": 0.91,
        "sources": [{"title": "FAQ"}],
        "model": "gpt-test",
        "tokens_in": 12,
        "tokens_out": 7,
        "cache_read": 2,
        "cost_usd": 0.001,
        "latency_ms": 120,
    }

    asyncio.run(
        OutboundService(store).queue_text(
            conversation_id=conversation_id,
            role="agent",
            text="Đã kiểm tra ạ",
            idempotency_key="ai:m1:part:0",
            metadata=metadata,
        )
    )

    assert store.messages[0]["metadata"] == metadata


def test_queue_ai_bi_chan_khi_human_da_takeover_nhung_staff_van_gui_duoc():
    store = _Store()
    conversation_id = uuid4()
    store.conversations[conversation_id] = {
        "id": conversation_id,
        "account_id": uuid4(),
        "external_id": "customer-1",
        "status": "escalated",
        "mode": "human",
    }

    with pytest.raises(OutboundBlocked):
        asyncio.run(
            OutboundService(store).queue_text(
                conversation_id=conversation_id,
                role="agent",
                text="AI không được gửi",
                idempotency_key="ai:late",
            )
        )

    queued = asyncio.run(
        OutboundService(store).queue_text(
            conversation_id=conversation_id,
            role="staff",
            text="Nhân viên vẫn gửi được",
            idempotency_key="staff:1",
        )
    )
    assert queued.status == "queued"


def test_queue_lai_cung_idempotency_key_khong_tao_message_thu_hai():
    store = _Store()
    conversation_id = uuid4()
    account_id = uuid4()
    store.conversations[conversation_id] = {
        "id": conversation_id,
        "account_id": account_id,
        "external_id": "customer-1",
        "status": "auto",
    }
    service = OutboundService(store)
    kwargs = {
        "conversation_id": conversation_id,
        "role": "staff",
        "text": "Đã nhận ạ",
        "idempotency_key": "same-request",
    }

    first = asyncio.run(service.queue_text(**kwargs))
    duplicate = asyncio.run(service.queue_text(**kwargs))

    assert duplicate.job_id == first.job_id
    assert duplicate.duplicate is True
    assert len(store.messages) == 1
    assert len(store.jobs) == 1


def test_queue_text_tu_choi_idempotency_key_rong():
    store = _Store()

    try:
        asyncio.run(
            OutboundService(store).queue_text(
                conversation_id=uuid4(),
                role="staff",
                text="x",
                idempotency_key=" ",
            )
        )
    except ValueError as exc:
        assert "idempotency" in str(exc)
    else:
        raise AssertionError("idempotency key rỗng đã được chấp nhận")


def test_queue_existing_draft_khong_tao_message_thu_hai():
    store = _Store()
    conversation_id = uuid4()
    account_id = uuid4()
    message_id = uuid4()
    store.conversations[conversation_id] = {
        "id": conversation_id,
        "account_id": account_id,
        "external_id": "customer-1",
        "status": "assist",
    }
    store.existing_messages[message_id] = {
        "id": message_id,
        "conversation_id": conversation_id,
        "content": "Bản nháp đã duyệt",
    }

    queued = asyncio.run(
        OutboundService(store).queue_existing_text(
            conversation_id=conversation_id,
            message_id=message_id,
            text="Bản nháp đã duyệt",
            idempotency_key=f"approve:{message_id}",
        )
    )

    assert queued.message_id == message_id
    assert store.messages == []
    assert store.queued_existing == [(message_id, f"approve:{message_id}")]


def test_queue_file_tao_message_attachment_va_outbox_cung_luc():
    store = _Store()
    conversation_id = uuid4()
    account_id = uuid4()
    store.conversations[conversation_id] = {
        "id": conversation_id,
        "account_id": account_id,
        "external_id": "customer-1",
        "status": "auto",
    }

    queued = asyncio.run(
        OutboundService(store).queue_file(
            conversation_id=conversation_id,
            role="agent",
            path="data/products/p1.jpg",
            caption="Sản phẩm P1",
            idempotency_key="ai:reply-1:file:0",
        )
    )

    assert queued.payload == {
        "conversation_ref": "customer-1",
        "path": "data/products/p1.jpg",
        "caption": "Sản phẩm P1",
    }
    assert store.messages[0]["text"] == "Sản phẩm P1"
    assert store.attachments == [
        (queued.message_id, "image", "data/products/p1.jpg", "Sản phẩm P1", 0)
    ]
    job = store.jobs[(account_id, "ai:reply-1:file:0")]
    assert job["payload"]["path"] == "data/products/p1.jpg"


class _DbTransaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        self.connection.in_transaction = True

    async def __aexit__(self, exc_type, exc, traceback):
        self.connection.in_transaction = False
        return False


class _Connection:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []
        self.in_transaction = False

    def transaction(self):
        return _DbTransaction(self)

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args, self.in_transaction))
        return self.rows.pop(0)

    async def execute(self, sql, *args):
        self.calls.append((sql, args, self.in_transaction))
        return "OK"


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


def test_postgres_queue_message_job_event_trong_cung_transaction():
    conversation_id = uuid4()
    account_id = uuid4()
    message_id = uuid4()
    job_id = uuid4()
    connection = _Connection(
        [
            {
                "id": conversation_id,
                "account_id": account_id,
                "external_id": "customer-1",
                "status": "auto",
            },
            None,
            {"id": message_id},
            {"id": job_id},
        ]
    )
    service = OutboundService(PostgresOutboundRepository(lambda: _Pool(connection)))

    queued = asyncio.run(
        service.queue_text(
            conversation_id=conversation_id,
            role="staff",
            text="Đã nhận ạ",
            idempotency_key="request-1",
        )
    )

    assert queued.job_id == job_id
    assert all(call[2] for call in connection.calls)
    sql = "\n".join(call[0] for call in connection.calls)
    assert "INSERT INTO messages" in sql
    assert "INSERT INTO outbox_jobs" in sql
    assert "INSERT INTO inbox_events" in sql
    assert "pg_advisory_xact_lock" in sql
    # Tham số đầu phải là CHUỖI, không phải đối tượng UUID: câu lệnh khoá ép
    # `$1::text`, và asyncpg từ chối UUID cho tham số kiểu text ngay lúc bind.
    #
    # Khẳng định cũ ở đây chờ `account_id` dạng UUID — tức nó neo đúng cái lỗi
    # làm hành vi mong đợi, và giữ cho lỗi ấy sống qua mọi lần chạy CI. Đừng
    # đổi ngược lại; xem test_postgres_lock_idempotency_chay_that_tren_postgresql.
    assert connection.calls[1][1] == (str(account_id), "request-1")


def test_handover_key_dedupe_trong_cung_transition_nhung_cho_phep_escalate_lai():
    conversation_id = uuid4()
    assert handover_idempotency_key(conversation_id, 4) == handover_idempotency_key(conversation_id, 4)
    assert handover_idempotency_key(conversation_id, 4) != handover_idempotency_key(conversation_id, 7)


# ---------------------------------------------------------------
#  Chốt consent — P0 trong báo cáo audit
# ---------------------------------------------------------------
# Trước lớp này, `consents` chỉ được GHI ở API Customer 360 và không có chỗ
# nào ĐỌC lúc gửi. Khách bấm "không nhận tin quảng cáo" xong vẫn nhận tin.
# Đó không phải bug kỹ thuật mà là vi phạm quyền dữ liệu, nên chốt phải nằm
# trong mã đường gửi chứ không nằm ở giao diện: giao diện chỉ là một trong
# nhiều đường vào `queue_text`.


def _hoi_thoai_co_contact(store, *, contact_id):
    conversation_id = uuid4()
    account_id = uuid4()
    store.conversations[conversation_id] = {
        "id": conversation_id,
        "account_id": account_id,
        "external_id": "customer-1",
        "status": "auto",
        "contact_id": contact_id,
    }
    return conversation_id, account_id


def test_marketing_bi_chan_khi_khach_chua_dong_y():
    """Chưa đồng ý là CHƯA ĐƯỢC GỬI — mặc định phải là opt-in, không phải opt-out."""
    store = _Store()
    contact_id = uuid4()
    conversation_id, _ = _hoi_thoai_co_contact(store, contact_id=contact_id)

    with pytest.raises(OutboundBlocked):
        asyncio.run(
            OutboundService(store).queue_text(
                conversation_id=conversation_id,
                role="staff",
                text="Bên em đang có khuyến mãi ạ",
                idempotency_key="mkt-1",
                purpose="marketing",
            )
        )

    assert store.messages == []
    assert store.jobs == {}


def test_gui_file_quang_cao_cung_phai_qua_chot_consent():
    """Ảnh khuyến mãi cũng là quảng cáo. Khoá một cửa mà bỏ cửa kia là chưa khoá."""
    store = _Store()
    contact_id = uuid4()
    conversation_id, _ = _hoi_thoai_co_contact(store, contact_id=contact_id)

    with pytest.raises(OutboundBlocked):
        asyncio.run(
            OutboundService(store).queue_file(
                conversation_id=conversation_id,
                role="staff",
                path="data/mau/khuyen-mai.jpg",
                caption="Giảm 30% hôm nay",
                idempotency_key="mkt-file-1",
                purpose="marketing",
            )
        )

    assert store.messages == []
    assert store.attachments == []


def test_postgres_doc_contact_id_va_hoi_consent_that_su():
    """
    Repository THẬT phải hỏi bảng consents, không chỉ lớp service với fake.

    Test này canh đúng khoảng cách hay bị bỏ quên: service có chốt, nhưng
    `get_conversation` không SELECT contact_id thì chốt luôn thấy None và
    chặn nhầm mọi tin quảng cáo hợp lệ — hỏng theo kiểu không ai báo.
    """
    conversation_id = uuid4()
    account_id = uuid4()
    contact_id = uuid4()
    connection = _Connection(
        [
            {
                "id": conversation_id,
                "account_id": account_id,
                "external_id": "customer-1",
                "status": "auto",
                "contact_id": contact_id,
            },
            {"status": "withdrawn"},
        ]
    )
    service = OutboundService(PostgresOutboundRepository(lambda: _Pool(connection)))

    with pytest.raises(OutboundBlocked):
        asyncio.run(
            service.queue_text(
                conversation_id=conversation_id,
                role="staff",
                text="Khuyến mãi tháng này ạ",
                idempotency_key="mkt-pg-1",
                purpose="marketing",
            )
        )

    sql_hoi_thoai = connection.calls[0][0]
    assert "contact_id" in sql_hoi_thoai, "get_conversation phải lấy cả contact_id"
    sql_consent = connection.calls[1][0]
    assert "consents" in sql_consent
    assert connection.calls[1][1] == (contact_id, "marketing", account_id)


def test_postgres_lock_idempotency_chay_that_tren_postgresql():
    """
    Chạy `lock_idempotency` với connection THẬT, không phải fake.

    LỖI ĐÃ XẢY RA THẬT
    ------------------
    SQL ép `$1::text`, nên asyncpg suy ra tham số phải là chuỗi. Mã truyền
    vào đối tượng `UUID` -> DataError ngay lúc bind, trước cả khi câu lệnh
    chạm tới Postgres.

    Mọi fake trong file này chỉ ghi `(account_id, key)` vào một list, nên
    chúng không bao giờ chạm tới bộ mã hoá tham số của asyncpg — chỗ duy
    nhất phát hiện được kiểu sai. Kết quả: bấm "Duyệt và gửi" trên dashboard
    trả 500 với một hội thoại khách THẬT, trong khi 767 test vẫn xanh.

    Bài học: chỗ nào fake thay cho driver thì chỗ đó phải có một test chạm
    driver thật, dù chỉ một.
    """
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("chưa cấp TEST_DATABASE_URL cho integration PostgreSQL")

    import asyncpg

    from agent.omnichannel.outbound_service import PostgresOutboundTransaction

    async def kiem():
        conn = await asyncpg.connect(database_url)
        try:
            async with conn.transaction():
                tx = PostgresOutboundTransaction(conn)
                await tx.lock_idempotency(uuid4(), "khoa-thu-nghiem-1")
        finally:
            await conn.close()

    asyncio.run(kiem())
