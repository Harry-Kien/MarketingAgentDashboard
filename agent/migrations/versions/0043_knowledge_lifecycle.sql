-- DEV-11 / GAP-04: vòng đời Draft/Published và phiên bản cho Knowledge Base.
--
-- Dữ liệu cũ được bảo toàn thành version 1 ở trạng thái DRAFT. Cố ý không
-- tự Publish: nội dung lịch sử chưa qua bước duyệt không được phép trở thành
-- căn cứ trả lời khách chỉ vì ứng dụng được nâng cấp.

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS account_id UUID
        REFERENCES channel_accounts(id) ON DELETE RESTRICT,
    ADD COLUMN IF NOT EXISTS lifecycle_status TEXT NOT NULL DEFAULT 'draft',
    ADD COLUMN IF NOT EXISTS current_draft_version_id UUID,
    ADD COLUMN IF NOT EXISTS current_published_version_id UUID,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_lifecycle_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_lifecycle_status_check
    CHECK (lifecycle_status IN ('draft', 'published', 'archived'));

CREATE TABLE IF NOT EXISTS document_versions (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id    UUID        NOT NULL
        REFERENCES documents(id) ON DELETE CASCADE,
    version        INT         NOT NULL CHECK (version > 0),
    status         TEXT        NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'published', 'superseded')),
    content        TEXT        NOT NULL,
    index_status   TEXT        NOT NULL DEFAULT 'pending'
        CHECK (index_status IN ('pending', 'indexing', 'ready', 'failed')),
    index_error    TEXT,
    chunk_count    INT         NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    revision       INT         NOT NULL DEFAULT 1 CHECK (revision > 0),
    created_by     UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    published_by   UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at   TIMESTAMPTZ,
    UNIQUE (document_id, version),
    UNIQUE (id, document_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_document_versions_one_draft
    ON document_versions (document_id) WHERE status = 'draft';
CREATE INDEX IF NOT EXISTS idx_document_versions_history
    ON document_versions (document_id, version DESC);

-- Mỗi tài liệu cũ trở thành một draft v1. Ghép nội dung theo ord chỉ để có
-- bản xem/rollback; các chunk gốc vẫn được giữ nguyên bên dưới.
INSERT INTO document_versions (
    document_id, version, status, content, index_status,
    index_error, chunk_count, created_at, updated_at
)
SELECT d.id,
       1,
       'draft',
       coalesce(string_agg(c.content, E'\n\n' ORDER BY c.ord), ''),
       CASE
           WHEN count(c.id) = d.chunk_count
            AND count(c.id) > 0
            AND count(c.embedding) = count(c.id)
           THEN 'ready'
           ELSE 'failed'
       END,
       CASE
           WHEN count(c.id) = d.chunk_count
            AND count(c.id) > 0
            AND count(c.embedding) = count(c.id)
           THEN NULL
           ELSE 'Dữ liệu legacy cần được kiểm tra/lập chỉ mục lại trước khi Publish'
       END,
       count(c.id)::int,
       d.created_at,
       now()
FROM documents d
LEFT JOIN chunks c ON c.document_id = d.id
WHERE NOT EXISTS (
    SELECT 1 FROM document_versions v WHERE v.document_id = d.id
)
GROUP BY d.id, d.chunk_count, d.created_at;

UPDATE documents d
SET lifecycle_status = 'draft',
    current_draft_version_id = v.id,
    current_published_version_id = NULL,
    updated_at = now()
FROM document_versions v
WHERE v.document_id = d.id AND v.version = 1
  AND d.current_draft_version_id IS NULL;

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS document_version_id UUID;

UPDATE chunks c
SET document_version_id = v.id
FROM document_versions v
WHERE v.document_id = c.document_id
  AND v.version = 1
  AND c.document_version_id IS NULL;

ALTER TABLE chunks ALTER COLUMN document_version_id SET NOT NULL;
ALTER TABLE chunks
    DROP CONSTRAINT IF EXISTS chunks_document_version_document_fkey;
ALTER TABLE chunks
    ADD CONSTRAINT chunks_document_version_document_fkey
    FOREIGN KEY (document_version_id, document_id)
    REFERENCES document_versions(id, document_id) ON DELETE CASCADE;

ALTER TABLE documents
    DROP CONSTRAINT IF EXISTS documents_current_draft_version_fkey;
ALTER TABLE documents
    ADD CONSTRAINT documents_current_draft_version_fkey
    FOREIGN KEY (current_draft_version_id)
    REFERENCES document_versions(id) ON DELETE SET NULL;

ALTER TABLE documents
    DROP CONSTRAINT IF EXISTS documents_current_published_version_fkey;
ALTER TABLE documents
    ADD CONSTRAINT documents_current_published_version_fkey
    FOREIGN KEY (current_published_version_id)
    REFERENCES document_versions(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_documents_account_status
    ON documents (account_id, lifecycle_status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chunks_document_version
    ON chunks (document_version_id, ord);
