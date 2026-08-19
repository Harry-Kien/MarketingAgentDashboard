-- ============================================================
--  Lược đồ dữ liệu — Marketing Agent
--  Chạy tự động khi khởi động app (idempotent).
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- --- Hội thoại ----------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    channel         TEXT        NOT NULL,          -- zalocrm | zalo_oa | ...
    external_id     TEXT        NOT NULL,          -- id hội thoại phía kênh
    customer_name   TEXT,
    customer_ref    TEXT,
    -- auto: agent tự xử lý xong | assist: chờ người duyệt
    -- escalated: đã chuyển người | closed
    status          TEXT        NOT NULL DEFAULT 'auto',
    outcome         TEXT,                          -- resolved | escalated | abandoned
    cost_usd        NUMERIC(10,6) NOT NULL DEFAULT 0,
    msg_count       INT         NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel, external_id)
);
CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_status  ON conversations (status);

-- --- Tin nhắn -----------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT        NOT NULL,          -- customer | agent | staff | system
    content         TEXT        NOT NULL,
    -- Chế độ assist: agent soạn nhưng chưa gửi cho tới khi người duyệt.
    delivered       BOOLEAN     NOT NULL DEFAULT TRUE,
    grounded        BOOLEAN,                       -- có nguồn RAG hay không
    confidence      REAL,
    sources         JSONB       NOT NULL DEFAULT '[]',
    model           TEXT,
    tokens_in       INT         NOT NULL DEFAULT 0,
    tokens_out      INT         NOT NULL DEFAULT 0,
    cache_read      INT         NOT NULL DEFAULT 0,
    cost_usd        NUMERIC(10,6) NOT NULL DEFAULT 0,
    latency_ms      INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_msg_time ON messages (created_at DESC);

-- --- Cơ sở tri thức (RAG) -----------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title       TEXT NOT NULL,
    source      TEXT NOT NULL,
    chunk_count INT  NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ord         INT  NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(768),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chunk_doc ON chunks (document_id);
-- ivfflat cần dữ liệu trước khi build; tạo sau khi nạp corpus:
--   CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists=100);

-- --- Video --------------------------------------------------
CREATE TABLE IF NOT EXISTS videos (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    brief           TEXT NOT NULL,
    kind            TEXT NOT NULL DEFAULT 'explainer',   -- explainer | product
    -- queued | scripting | voicing | rendering | ready | failed | pending_review
    status          TEXT NOT NULL DEFAULT 'queued',
    renderer        TEXT,                                -- hyperframes | veo | hybrid
    duration_s      REAL,
    scenes          JSONB NOT NULL DEFAULT '[]',
    file_path       TEXT,
    error           TEXT,
    cost_usd        NUMERIC(10,6) NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_video_created ON videos (created_at DESC);

-- --- Ảnh sản phẩm của video --------------------------------
-- `analysis` là kết quả bước NHÌN ẢNH (agent/video/vision.py): mô tả, màu
-- chủ đạo, độ sáng, và vùng trống để đặt chữ. Đây là tầng dữ liệu kiểm
-- chứng được nằm giữa ảnh và khâu dựng — mở ra xem được khi video xấu.
CREATE TABLE IF NOT EXISTS video_assets (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id   UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    ord        INT  NOT NULL,
    file_path  TEXT NOT NULL,
    width      INT,
    height     INT,
    analysis   JSONB NOT NULL DEFAULT '{}',
    usable     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (video_id, ord)
);
CREATE INDEX IF NOT EXISTS idx_asset_video ON video_assets (video_id, ord);

-- --- Nhật ký kiểm toán --------------------------------------
CREATE TABLE IF NOT EXISTS events (
    id         BIGSERIAL PRIMARY KEY,
    kind       TEXT NOT NULL,
    actor      TEXT NOT NULL DEFAULT 'system',
    ref_id     UUID,
    detail     JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_event_time ON events (created_at DESC);

-- --- Chống xử lý trùng webhook ------------------------------
CREATE TABLE IF NOT EXISTS processed_webhooks (
    message_key TEXT PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --- Đơn hàng ------------------------------------------------
-- Tool đầu tiên có hậu quả KHÔNG ĐẢO NGƯỢC. Mọi chốt chặn nằm ở
-- agent/core/tools.py; bảng này chỉ lưu kết quả và trạng thái duyệt.
CREATE TABLE IF NOT EXISTS orders (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ma_don          TEXT UNIQUE NOT NULL,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    channel         TEXT NOT NULL DEFAULT 'zalocrm',
    khach_ten       TEXT NOT NULL,
    khach_sdt       TEXT NOT NULL,
    khach_dia_chi   TEXT NOT NULL,
    items           JSONB NOT NULL DEFAULT '[]',
    tong_tien       BIGINT NOT NULL DEFAULT 0,
    -- cho_duyet : vượt ngưỡng giá trị, cần người xác nhận
    -- da_chot   : agent tự chốt trong hạn mức
    -- da_huy    : người huỷ
    trang_thai      TEXT NOT NULL DEFAULT 'cho_duyet',
    tao_boi         TEXT NOT NULL DEFAULT 'agent',
    ghi_chu         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_order_created ON orders (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_status  ON orders (trang_thai);

-- Chống tạo trùng: khách nhắn "ok" hai lần không được ra hai đơn.
CREATE UNIQUE INDEX IF NOT EXISTS idx_order_dedupe
    ON orders (conversation_id, md5(items::text))
    WHERE trang_thai <> 'da_huy';
