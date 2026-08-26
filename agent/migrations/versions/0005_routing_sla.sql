-- Routing, assignment và SLA account-aware. Deadline là mốc nghiệp vụ bất biến:
-- tin mới cập nhật activity nhưng không được "tặng thêm giờ" cho hàng chờ.

CREATE TABLE IF NOT EXISTS teams (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT        NOT NULL UNIQUE,
    description TEXT        NOT NULL DEFAULT '',
    status      TEXT        NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('active', 'disabled'))
);

CREATE TABLE IF NOT EXISTS team_members (
    team_id     UUID        NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id     UUID        NOT NULL REFERENCES nguoi_dung(id) ON DELETE CASCADE,
    role        TEXT        NOT NULL DEFAULT 'agent',
    skills      JSONB       NOT NULL DEFAULT '[]',
    max_active  INT         NOT NULL DEFAULT 20 CHECK (max_active > 0),
    is_available BOOLEAN    NOT NULL DEFAULT true,
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, user_id),
    CHECK (role IN ('manager', 'agent'))
);
CREATE INDEX IF NOT EXISTS idx_team_members_available
    ON team_members (team_id, is_available, user_id);

CREATE TABLE IF NOT EXISTS sla_policies (
    id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id             UUID REFERENCES channel_accounts(id) ON DELETE CASCADE,
    priority               TEXT        NOT NULL DEFAULT 'normal',
    first_response_minutes INT         NOT NULL CHECK (first_response_minutes > 0),
    resolution_minutes     INT         NOT NULL CHECK (resolution_minutes > 0),
    business_hours         JSONB       NOT NULL DEFAULT '{}',
    active                 BOOLEAN     NOT NULL DEFAULT true,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    UNIQUE NULLS NOT DISTINCT (account_id, priority)
);

CREATE TABLE IF NOT EXISTS routing_rules (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id      UUID REFERENCES channel_accounts(id) ON DELETE CASCADE,
    team_id         UUID        NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    priority        TEXT,
    required_skills JSONB       NOT NULL DEFAULT '[]',
    weight          INT         NOT NULL DEFAULT 100 CHECK (weight > 0),
    active          BOOLEAN     NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (priority IS NULL OR priority IN ('low', 'normal', 'high', 'urgent'))
);
CREATE INDEX IF NOT EXISTS idx_routing_rules_match
    ON routing_rules (account_id, active, priority);

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS mode TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS state TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS priority TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS assigned_team_id UUID;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS first_response_due_at TIMESTAMPTZ;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS resolution_due_at TIMESTAMPTZ;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS first_responded_at TIMESTAMPTZ;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS version INT;

UPDATE conversations
SET mode = CASE
        WHEN status = 'escalated' THEN 'human'
        WHEN status = 'assist' THEN 'assist'
        ELSE 'auto'
    END,
    state = CASE WHEN status = 'closed' THEN 'closed' ELSE 'open' END,
    priority = 'normal',
    version = 1
WHERE mode IS NULL OR state IS NULL OR priority IS NULL OR version IS NULL;

ALTER TABLE conversations ALTER COLUMN mode SET DEFAULT 'auto';
ALTER TABLE conversations ALTER COLUMN mode SET NOT NULL;
ALTER TABLE conversations ALTER COLUMN state SET DEFAULT 'open';
ALTER TABLE conversations ALTER COLUMN state SET NOT NULL;
ALTER TABLE conversations ALTER COLUMN priority SET DEFAULT 'normal';
ALTER TABLE conversations ALTER COLUMN priority SET NOT NULL;
ALTER TABLE conversations ALTER COLUMN version SET DEFAULT 1;
ALTER TABLE conversations ALTER COLUMN version SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'conversations_mode_check'
          AND conrelid = 'conversations'::regclass
    ) THEN
        ALTER TABLE conversations ADD CONSTRAINT conversations_mode_check
            CHECK (mode IN ('auto', 'assist', 'human'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'conversations_state_check'
          AND conrelid = 'conversations'::regclass
    ) THEN
        ALTER TABLE conversations ADD CONSTRAINT conversations_state_check
            CHECK (state IN ('open', 'pending', 'resolved', 'closed'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'conversations_priority_check'
          AND conrelid = 'conversations'::regclass
    ) THEN
        ALTER TABLE conversations ADD CONSTRAINT conversations_priority_check
            CHECK (priority IN ('low', 'normal', 'high', 'urgent'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'conversations_assigned_team_id_fkey'
          AND conrelid = 'conversations'::regclass
    ) THEN
        ALTER TABLE conversations
            ADD CONSTRAINT conversations_assigned_team_id_fkey
            FOREIGN KEY (assigned_team_id) REFERENCES teams(id) ON DELETE SET NULL;
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS conversation_assignments (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id  UUID        NOT NULL
        REFERENCES conversations(id) ON DELETE CASCADE,
    assigned_user_id UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    assigned_team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
    actor_id          UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    source            TEXT        NOT NULL,
    reason            TEXT        NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at          TIMESTAMPTZ,
    CHECK (source IN ('manual', 'auto', 'takeover', 'release')),
    CHECK (ended_at IS NULL OR ended_at >= started_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_assignment_one_active
    ON conversation_assignments (conversation_id) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_assignment_user_active
    ON conversation_assignments (assigned_user_id, started_at)
    WHERE ended_at IS NULL;

CREATE TABLE IF NOT EXISTS sla_events (
    id              BIGSERIAL PRIMARY KEY,
    conversation_id UUID        NOT NULL
        REFERENCES conversations(id) ON DELETE CASCADE,
    kind            TEXT        NOT NULL,
    due_at          TIMESTAMPTZ,
    detail          JSONB       NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (kind IN (
        'started', 'first_response_met', 'first_response_breached',
        'resolution_met', 'resolution_breached', 'paused', 'resumed'
    )),
    UNIQUE (conversation_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_sla_events_due
    ON sla_events (kind, due_at) WHERE due_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS routing_cursors (
    rule_id       UUID PRIMARY KEY REFERENCES routing_rules(id) ON DELETE CASCADE,
    last_user_id  UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION prevent_sla_deadline_reset()
RETURNS trigger AS $$
BEGIN
    IF OLD.first_response_due_at IS NOT NULL
       AND NEW.first_response_due_at IS DISTINCT FROM OLD.first_response_due_at THEN
        NEW.first_response_due_at := OLD.first_response_due_at;
    END IF;
    IF OLD.resolution_due_at IS NOT NULL
       AND NEW.resolution_due_at IS DISTINCT FROM OLD.resolution_due_at THEN
        NEW.resolution_due_at := OLD.resolution_due_at;
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_sla_deadline_reset ON conversations;
CREATE TRIGGER trg_prevent_sla_deadline_reset
BEFORE UPDATE ON conversations
FOR EACH ROW EXECUTE FUNCTION prevent_sla_deadline_reset();

CREATE INDEX IF NOT EXISTS idx_conversations_routing_queue
    ON conversations (state, mode, priority, resolution_due_at, updated_at)
    WHERE state IN ('open', 'pending');
CREATE INDEX IF NOT EXISTS idx_conversations_assigned_workload
    ON conversations (assigned_to, state, updated_at)
    WHERE assigned_to IS NOT NULL AND state IN ('open', 'pending');
