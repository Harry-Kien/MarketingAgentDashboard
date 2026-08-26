-- Nền tảng đa tài khoản cho mọi kênh chăm sóc khách hàng.
-- Migration này chạy sau schema.sql và phải nâng cấp được CSDL đã có dữ liệu.

CREATE TABLE IF NOT EXISTS channel_accounts (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    channel             TEXT        NOT NULL,
    display_name        TEXT        NOT NULL,
    external_account_id TEXT,
    status              TEXT        NOT NULL DEFAULT 'pending',
    capabilities        JSONB       NOT NULL DEFAULT '{}',
    metadata            JSONB       NOT NULL DEFAULT '{}',
    is_legacy           BOOLEAN     NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN (
        'pending', 'active', 'degraded', 'reauth_required', 'disabled'
    )),
    UNIQUE NULLS NOT DISTINCT (channel, external_account_id)
);
CREATE INDEX IF NOT EXISTS idx_channel_accounts_channel_status
    ON channel_accounts (channel, status);

CREATE TABLE IF NOT EXISTS credential_secrets (
    account_id  UUID PRIMARY KEY
        REFERENCES channel_accounts(id) ON DELETE CASCADE,
    key_version INT         NOT NULL CHECK (key_version > 0),
    nonce       BYTEA       NOT NULL CHECK (octet_length(nonce) = 12),
    ciphertext  BYTEA       NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS account_memberships (
    account_id UUID        NOT NULL
        REFERENCES channel_accounts(id) ON DELETE CASCADE,
    user_id    UUID        NOT NULL
        REFERENCES nguoi_dung(id) ON DELETE CASCADE,
    role       TEXT        NOT NULL DEFAULT 'agent',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, user_id),
    CHECK (role IN ('owner', 'manager', 'agent', 'viewer'))
);
CREATE INDEX IF NOT EXISTS idx_account_memberships_user
    ON account_memberships (user_id, account_id);

CREATE TABLE IF NOT EXISTS account_health_events (
    id          BIGSERIAL PRIMARY KEY,
    account_id  UUID        NOT NULL
        REFERENCES channel_accounts(id) ON DELETE CASCADE,
    status      TEXT        NOT NULL,
    code        TEXT        NOT NULL,
    detail      JSONB       NOT NULL DEFAULT '{}',
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN (
        'pending', 'active', 'degraded', 'reauth_required', 'disabled'
    ))
);
CREATE INDEX IF NOT EXISTS idx_account_health_latest
    ON account_health_events (account_id, observed_at DESC);

-- Tạo một account tương thích cho từng kênh đã có dữ liệu. external_account_id
-- không để NULL để mỗi kênh chỉ có đúng một account legacy và migration an toàn
-- nếu được thử lại trong môi trường kiểm tra.
INSERT INTO channel_accounts (
    id,
    channel,
    display_name,
    external_account_id,
    status,
    capabilities,
    is_legacy
)
SELECT DISTINCT
    uuid_generate_v5(
        'd5a0f4ad-cb42-4a70-a035-c1249fc71f78'::uuid,
        'legacy:' || channel
    ),
    channel,
    'Tài khoản cũ — ' || channel,
    'legacy:' || channel,
    'active',
    '{"compatibility": true}'::jsonb,
    true
FROM conversations
ON CONFLICT (channel, external_account_id) DO NOTHING;

ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS account_id UUID;

UPDATE conversations AS conversation
SET account_id = account.id
FROM channel_accounts AS account
WHERE conversation.account_id IS NULL
  AND account.channel = conversation.channel
  AND account.external_account_id = 'legacy:' || conversation.channel;

-- Không được tiếp tục nếu có dữ liệu không thể gắn account; fail closed giúp
-- người vận hành sửa dữ liệu thay vì tạo hội thoại không thể định tuyến reply.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM conversations WHERE account_id IS NULL) THEN
        RAISE EXCEPTION 'không thể backfill account_id cho toàn bộ conversations';
    END IF;
END
$$;

ALTER TABLE conversations
    ALTER COLUMN account_id SET NOT NULL;

ALTER TABLE conversations
    DROP CONSTRAINT IF EXISTS conversations_channel_external_id_key;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'conversations_account_id_fkey'
          AND conrelid = 'conversations'::regclass
    ) THEN
        ALTER TABLE conversations
            ADD CONSTRAINT conversations_account_id_fkey
            FOREIGN KEY (account_id)
            REFERENCES channel_accounts(id)
            ON DELETE RESTRICT;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'conversations_account_external_id_key'
          AND conrelid = 'conversations'::regclass
    ) THEN
        ALTER TABLE conversations
            ADD CONSTRAINT conversations_account_external_id_key
            UNIQUE (account_id, external_id);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_conversations_account_updated
    ON conversations (account_id, updated_at DESC);

-- Bảo toàn quyền hiện hành: quản trị cũ thành owner, nhân viên cũ thành agent
-- trên các account legacy. Account mới sẽ được gán membership qua service/API.
INSERT INTO account_memberships (account_id, user_id, role)
SELECT
    account.id,
    user_row.id,
    CASE
        WHEN user_row.vai_tro = 'quan_tri' THEN 'owner'
        ELSE 'agent'
    END
FROM channel_accounts AS account
CROSS JOIN nguoi_dung AS user_row
WHERE account.is_legacy = true
ON CONFLICT (account_id, user_id) DO NOTHING;
