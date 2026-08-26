-- Read state theo từng nhân viên và phân công hội thoại cho native inbox.

ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS assigned_to UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'conversations_assigned_to_fkey'
          AND conrelid = 'conversations'::regclass
    ) THEN
        ALTER TABLE conversations
            ADD CONSTRAINT conversations_assigned_to_fkey
            FOREIGN KEY (assigned_to)
            REFERENCES nguoi_dung(id)
            ON DELETE SET NULL;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_conversations_assigned_updated
    ON conversations (assigned_to, updated_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS conversation_reads (
    conversation_id UUID        NOT NULL
        REFERENCES conversations(id) ON DELETE CASCADE,
    user_id         UUID        NOT NULL
        REFERENCES nguoi_dung(id) ON DELETE CASCADE,
    last_read_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (conversation_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_conversation_reads_user
    ON conversation_reads (user_id, last_read_at DESC);

CREATE INDEX IF NOT EXISTS idx_messages_customer_unread
    ON messages (conversation_id, created_at DESC)
    WHERE role = 'customer';

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_name  TEXT PRIMARY KEY,
    worker_id    TEXT        NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    detail       JSONB       NOT NULL DEFAULT '{}'
);
