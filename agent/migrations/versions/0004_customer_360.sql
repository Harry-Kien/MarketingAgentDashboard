-- Customer 360 account-scoped. Backfill bảo thủ: mỗi danh tính nguồn là một
-- contact riêng; tuyệt đối không hợp nhất chỉ vì tên hiển thị giống nhau.

CREATE TABLE IF NOT EXISTS contacts (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    display_name TEXT        NOT NULL DEFAULT 'Khách',
    phone        TEXT,
    email        TEXT,
    profile      JSONB       NOT NULL DEFAULT '{}',
    status       TEXT        NOT NULL DEFAULT 'active',
    merged_into  UUID REFERENCES contacts(id) ON DELETE RESTRICT,
    version      INT         NOT NULL DEFAULT 1 CHECK (version > 0),
    first_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('active', 'merged', 'deletion_pending', 'deleted')),
    CHECK (
        (status = 'merged' AND merged_into IS NOT NULL)
        OR (status <> 'merged' AND merged_into IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_contacts_last_seen
    ON contacts (last_seen DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_contacts_phone
    ON contacts (phone) WHERE phone IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contacts_email
    ON contacts (lower(email)) WHERE email IS NOT NULL;

CREATE TABLE IF NOT EXISTS contact_points (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contact_id         UUID        NOT NULL
        REFERENCES contacts(id) ON DELETE RESTRICT,
    channel_account_id UUID        NOT NULL
        REFERENCES channel_accounts(id) ON DELETE RESTRICT,
    external_user_id   TEXT        NOT NULL,
    handle             TEXT,
    verified_fields    JSONB       NOT NULL DEFAULT '{}',
    metadata           JSONB       NOT NULL DEFAULT '{}',
    first_seen         TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel_account_id, external_user_id)
);
CREATE INDEX IF NOT EXISTS idx_contact_points_contact
    ON contact_points (contact_id, last_seen DESC);

CREATE TABLE IF NOT EXISTS contact_tags (
    contact_id UUID        NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    tag        TEXT        NOT NULL CHECK (length(tag) BETWEEN 1 AND 80),
    created_by UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (contact_id, tag)
);

CREATE TABLE IF NOT EXISTS contact_notes (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contact_id UUID        NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    body       TEXT        NOT NULL CHECK (length(body) BETWEEN 1 AND 5000),
    visibility TEXT        NOT NULL DEFAULT 'team',
    created_by UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (visibility IN ('team', 'manager'))
);
CREATE INDEX IF NOT EXISTS idx_contact_notes_timeline
    ON contact_notes (contact_id, created_at DESC);

CREATE TABLE IF NOT EXISTS contact_consents (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contact_id  UUID        NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    account_id  UUID REFERENCES channel_accounts(id) ON DELETE CASCADE,
    purpose     TEXT        NOT NULL,
    status      TEXT        NOT NULL,
    source      TEXT        NOT NULL,
    evidence    JSONB       NOT NULL DEFAULT '{}',
    captured_by UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('granted', 'denied', 'withdrawn')),
    UNIQUE NULLS NOT DISTINCT (contact_id, account_id, purpose)
);
CREATE INDEX IF NOT EXISTS idx_contact_consents_contact
    ON contact_consents (contact_id, purpose);

CREATE TABLE IF NOT EXISTS contact_merges (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_contact_id       UUID        NOT NULL
        REFERENCES contacts(id) ON DELETE RESTRICT,
    target_contact_id       UUID        NOT NULL
        REFERENCES contacts(id) ON DELETE RESTRICT,
    actor_id                UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    reason                  TEXT        NOT NULL CHECK (length(reason) > 0),
    expected_source_version INT         NOT NULL,
    expected_target_version INT         NOT NULL,
    snapshot                JSONB       NOT NULL,
    status                  TEXT        NOT NULL DEFAULT 'active',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    reverted_by             UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    reverted_at             TIMESTAMPTZ,
    revert_reason           TEXT,
    CHECK (source_contact_id <> target_contact_id),
    CHECK (status IN ('active', 'reverted'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contact_merge_one_active_source
    ON contact_merges (source_contact_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS data_retention_jobs (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contact_id  UUID REFERENCES contacts(id) ON DELETE SET NULL,
    kind        TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'pending_approval',
    requested_by UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    approved_by UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    reason      TEXT        NOT NULL,
    dry_run     BOOLEAN     NOT NULL DEFAULT true,
    result      JSONB       NOT NULL DEFAULT '{}',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CHECK (kind IN ('export', 'delete', 'retention')),
    CHECK (status IN (
        'pending_approval', 'approved', 'running', 'completed', 'failed', 'cancelled'
    ))
);
CREATE INDEX IF NOT EXISTS idx_retention_jobs_status
    ON data_retention_jobs (status, requested_at);

ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS contact_id UUID;
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS contact_point_id UUID;

-- Một UUID ổn định theo account + external identity giúp migration chạy lại
-- an toàn. customer_ref rỗng dùng conversation external_id, không dùng tên.
INSERT INTO contacts (
    id, display_name, first_seen, last_seen, profile
)
SELECT
    uuid_generate_v5(
        '26cb54f1-7d25-459d-bdb4-b2deca60c7ab'::uuid,
        conversation.account_id::text || ':' ||
        coalesce(nullif(conversation.customer_ref, ''),
                 'conversation:' || conversation.external_id)
    ),
    coalesce(max(nullif(conversation.customer_name, '')), 'Khách'),
    min(conversation.created_at),
    max(conversation.updated_at),
    jsonb_build_object('backfilled', true)
FROM conversations AS conversation
GROUP BY
    conversation.account_id,
    coalesce(nullif(conversation.customer_ref, ''),
             'conversation:' || conversation.external_id)
ON CONFLICT (id) DO NOTHING;

INSERT INTO contact_points (
    id, contact_id, channel_account_id, external_user_id, handle,
    first_seen, last_seen, metadata
)
SELECT
    uuid_generate_v5(
        'e962d92d-ed71-4496-bb0d-5d7472d738b7'::uuid,
        conversation.account_id::text || ':' ||
        coalesce(nullif(conversation.customer_ref, ''),
                 'conversation:' || conversation.external_id)
    ),
    uuid_generate_v5(
        '26cb54f1-7d25-459d-bdb4-b2deca60c7ab'::uuid,
        conversation.account_id::text || ':' ||
        coalesce(nullif(conversation.customer_ref, ''),
                 'conversation:' || conversation.external_id)
    ),
    conversation.account_id,
    coalesce(nullif(conversation.customer_ref, ''),
             'conversation:' || conversation.external_id),
    max(nullif(conversation.customer_name, '')),
    min(conversation.created_at),
    max(conversation.updated_at),
    jsonb_build_object('backfilled', true)
FROM conversations AS conversation
GROUP BY
    conversation.account_id,
    coalesce(nullif(conversation.customer_ref, ''),
             'conversation:' || conversation.external_id)
ON CONFLICT (channel_account_id, external_user_id) DO NOTHING;

UPDATE conversations AS conversation
SET contact_id = point.contact_id,
    contact_point_id = point.id
FROM contact_points AS point
WHERE conversation.contact_id IS NULL
  AND point.channel_account_id = conversation.account_id
  AND point.external_user_id = coalesce(
      nullif(conversation.customer_ref, ''),
      'conversation:' || conversation.external_id
  );

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM conversations
        WHERE contact_id IS NULL OR contact_point_id IS NULL
    ) THEN
        RAISE EXCEPTION 'không thể backfill Customer 360 cho toàn bộ conversations';
    END IF;
END
$$;

ALTER TABLE conversations ALTER COLUMN contact_id SET NOT NULL;
ALTER TABLE conversations ALTER COLUMN contact_point_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'conversations_contact_id_fkey'
          AND conrelid = 'conversations'::regclass
    ) THEN
        ALTER TABLE conversations ADD CONSTRAINT conversations_contact_id_fkey
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE RESTRICT;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'conversations_contact_point_id_fkey'
          AND conrelid = 'conversations'::regclass
    ) THEN
        ALTER TABLE conversations
            ADD CONSTRAINT conversations_contact_point_id_fkey
            FOREIGN KEY (contact_point_id)
            REFERENCES contact_points(id) ON DELETE RESTRICT;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_conversations_contact_updated
    ON conversations (contact_id, updated_at DESC);
