-- Inbox native: ledger webhook, trạng thái delivery, attachment chuẩn hóa
-- và transactional outbox. Không gọi provider trong transaction CSDL.

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id      UUID        NOT NULL
        REFERENCES channel_accounts(id) ON DELETE RESTRICT,
    dedupe_key      TEXT        NOT NULL,
    raw_sha256      TEXT        NOT NULL CHECK (length(raw_sha256) = 64),
    signature_valid BOOLEAN     NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'received',
    attempts        INT         NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    metadata        JSONB       NOT NULL DEFAULT '{}',
    last_error      TEXT,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, dedupe_key),
    CHECK (status IN ('received', 'processing', 'processed', 'failed', 'rejected'))
);
CREATE INDEX IF NOT EXISTS idx_webhook_delivery_status
    ON webhook_deliveries (status, received_at);

ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS direction TEXT;
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS delivery_status TEXT;
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS provider_message_id TEXT;
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS client_idempotency_key TEXT;

UPDATE messages
SET direction = CASE WHEN role = 'customer' THEN 'inbound' ELSE 'outbound' END
WHERE direction IS NULL;

UPDATE messages
SET delivery_status = CASE
    WHEN role = 'customer' THEN 'received'
    WHEN delivered = true THEN 'sent'
    WHEN role = 'agent' THEN 'draft'
    ELSE 'failed'
END
WHERE delivery_status IS NULL;

ALTER TABLE messages
    ALTER COLUMN direction SET NOT NULL;
ALTER TABLE messages
    ALTER COLUMN delivery_status SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'messages_direction_check'
          AND conrelid = 'messages'::regclass
    ) THEN
        ALTER TABLE messages
            ADD CONSTRAINT messages_direction_check
            CHECK (direction IN ('inbound', 'outbound', 'system'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'messages_delivery_status_check'
          AND conrelid = 'messages'::regclass
    ) THEN
        ALTER TABLE messages
            ADD CONSTRAINT messages_delivery_status_check
            CHECK (delivery_status IN (
                'received', 'draft', 'queued', 'sending', 'sent',
                'delivered', 'read', 'failed', 'dead', 'cancelled'
            ));
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION fill_message_delivery_defaults()
RETURNS trigger AS $$
BEGIN
    IF NEW.direction IS NULL THEN
        NEW.direction := CASE
            WHEN NEW.role = 'customer' THEN 'inbound'
            WHEN NEW.role = 'system' THEN 'system'
            ELSE 'outbound'
        END;
    END IF;
    IF NEW.delivery_status IS NULL THEN
        NEW.delivery_status := CASE
            WHEN NEW.role = 'customer' THEN 'received'
            WHEN NEW.delivered = true THEN 'sent'
            WHEN NEW.role = 'agent' THEN 'draft'
            ELSE 'failed'
        END;
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_message_delivery_defaults ON messages;
CREATE TRIGGER trg_message_delivery_defaults
BEFORE INSERT ON messages
FOR EACH ROW EXECUTE FUNCTION fill_message_delivery_defaults();

CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_provider_identity
    ON messages (conversation_id, provider_message_id)
    WHERE provider_message_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_client_idempotency
    ON messages (conversation_id, client_idempotency_key)
    WHERE client_idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS attachments (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    message_id   UUID        NOT NULL
        REFERENCES messages(id) ON DELETE CASCADE,
    ordinal      INT         NOT NULL CHECK (ordinal > 0),
    kind         TEXT        NOT NULL DEFAULT 'file',
    url          TEXT,
    original_url TEXT,
    storage_key  TEXT,
    mime_type    TEXT,
    size_bytes   BIGINT CHECK (size_bytes IS NULL OR size_bytes >= 0),
    metadata     JSONB       NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (message_id, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_attachments_message
    ON attachments (message_id, ordinal);

INSERT INTO attachments (
    message_id, ordinal, kind, url, original_url, metadata
)
SELECT
    message.id,
    item.ordinality::int,
    coalesce(item.value->>'loai', item.value->>'type', 'file'),
    nullif(item.value->>'url', ''),
    nullif(coalesce(item.value->>'goc', item.value->>'original_url'), ''),
    item.value
FROM messages AS message
CROSS JOIN LATERAL jsonb_array_elements(message.attachments)
    WITH ORDINALITY AS item(value, ordinality)
ON CONFLICT (message_id, ordinal) DO NOTHING;

CREATE TABLE IF NOT EXISTS outbox_jobs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id      UUID        NOT NULL
        REFERENCES channel_accounts(id) ON DELETE RESTRICT,
    conversation_id UUID
        REFERENCES conversations(id) ON DELETE CASCADE,
    message_id      UUID
        REFERENCES messages(id) ON DELETE SET NULL,
    kind            TEXT        NOT NULL,
    payload         JSONB       NOT NULL DEFAULT '{}',
    idempotency_key TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'pending',
    attempts        INT         NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts    INT         NOT NULL DEFAULT 8 CHECK (max_attempts > 0),
    available_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    locked_at       TIMESTAMPTZ,
    locked_by       TEXT,
    last_error      TEXT,
    provider_result JSONB       NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, idempotency_key),
    CHECK (status IN ('pending', 'processing', 'retry', 'sent', 'dead', 'cancelled'))
);
CREATE INDEX IF NOT EXISTS idx_outbox_claim
    ON outbox_jobs (available_at, created_at)
    WHERE status IN ('pending', 'retry');
CREATE INDEX IF NOT EXISTS idx_outbox_dead
    ON outbox_jobs (updated_at DESC)
    WHERE status = 'dead';
CREATE INDEX IF NOT EXISTS idx_outbox_conversation
    ON outbox_jobs (conversation_id, created_at DESC);

CREATE TABLE IF NOT EXISTS inbox_events (
    sequence_id BIGSERIAL PRIMARY KEY,
    account_id  UUID        NOT NULL
        REFERENCES channel_accounts(id) ON DELETE CASCADE,
    topic       TEXT        NOT NULL,
    ref_id      UUID,
    payload     JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inbox_events_account_sequence
    ON inbox_events (account_id, sequence_id);
