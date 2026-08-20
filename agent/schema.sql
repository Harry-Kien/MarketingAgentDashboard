-- ============================================================
--  Lược đồ dữ liệu — Marketing Agent
--  Chạy tự động khi khởi động app (idempotent).
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- --- Hội thoại ----------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    channel         TEXT        NOT NULL,          -- zalocrm | chatwoot | ...
    -- Nền tảng GỐC nơi khách thật sự nhắn tới. Chatwoot là hộp thư gộp:
    -- Facebook Messenger, Instagram DM, WhatsApp, chat website, email đều
    -- đổ về cùng một kênh `chatwoot`. Không tách ra thì dashboard chỉ ghi
    -- "Chatwoot" và mất đúng thông tin người vận hành cần — khách này đến
    -- từ đâu. Agent trả lời y hệt nhau; chỉ hiển thị và thống kê khác.
    nen_tang        TEXT,
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
    -- Vòng đời: queued -> claimed -> looking -> scripting -> voicing
    --           -> rendering -> pending_review -> ready
    -- Nhánh chết: failed. Thợ nền (agent/video/worker.py) nhận việc bằng
    -- `claimed`, và mọi trạng thái giữa chừng đều được nhặt lại khi app
    -- khởi động lại — không có video nào kẹt vĩnh viễn.
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

-- --- Bài đăng mạng xã hội ------------------------------------
-- Agent soạn nội dung + gắn video, người duyệt, rồi PublishAdapter
-- đẩy đi. KHÔNG BAO GIỜ tự đăng khi chưa duyệt.
CREATE TABLE IF NOT EXISTS posts (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id    UUID REFERENCES videos(id) ON DELETE SET NULL,
    tieu_de     TEXT NOT NULL,
    noi_dung    TEXT NOT NULL,
    hashtags    JSONB NOT NULL DEFAULT '[]',
    kenh        JSONB NOT NULL DEFAULT '[]',   -- ["facebook","tiktok"]
    -- nhap | cho_duyet | da_len_lich | dang_dang | da_dang | loi | da_huy
    trang_thai  TEXT NOT NULL DEFAULT 'cho_duyet',
    lich_dang   TIMESTAMPTZ,
    ket_qua     JSONB NOT NULL DEFAULT '{}',   -- {facebook:{ok,url,error}}
    tao_boi     TEXT NOT NULL DEFAULT 'agent',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_post_created ON posts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_post_status  ON posts (trang_thai);
CREATE INDEX IF NOT EXISTS idx_post_lich    ON posts (lich_dang)
    WHERE trang_thai = 'da_len_lich';

-- --- Số liệu bài đăng ----------------------------------------
-- Vòng phản hồi: nội dung nào chạy tốt thì agent biết mà làm tiếp.
CREATE TABLE IF NOT EXISTS post_metrics (
    id          BIGSERIAL PRIMARY KEY,
    post_id     UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    kenh        TEXT NOT NULL,
    url         TEXT,
    luot_xem    BIGINT NOT NULL DEFAULT 0,
    luot_thich  BIGINT NOT NULL DEFAULT 0,
    binh_luan   BIGINT NOT NULL DEFAULT 0,
    chia_se     BIGINT NOT NULL DEFAULT 0,
    luot_click  BIGINT NOT NULL DEFAULT 0,
    thu_thap_luc TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_metric_post ON post_metrics (post_id, thu_thap_luc DESC);

-- --- Nick Zalo dùng để trả lời từng hội thoại -----------------
-- Doanh nghiệp chạy nhiều nick (mỗi nhân viên một nick, hoặc tách theo
-- ngành hàng). Trả lời phải đi ra đúng nick khách đã nhắn vào, không thì
-- khách thấy một người lạ trả lời.
-- NULL = dùng nick mặc định đang chọn trên dashboard.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS zalo_account_id TEXT;

-- --- Trí nhớ về khách hàng ------------------------------------
-- Ranh giới giữa chatbot và agent: một chatbot trả lời rồi quên, agent giữ
-- lại hiểu biết về từng người và dùng ở lần sau.
--
-- `ghi_nho` là danh sách mẩu, mỗi mẩu có nguồn gốc:
--   hanh_dong  suy ra từ lời gọi công cụ  -> kiểm chứng được, không bịa nổi
--   don_hang   suy ra từ đơn đã lên
--   agent_ghi  điều agent nghe khách nói  -> kém chắc hơn
--
-- ĐÂY LÀ DỮ LIỆU CÁ NHÂN theo Nghị định 13/2023/NĐ-CP. Nó phải biến mất
-- khi khách yêu cầu xoá — xem agent/core/du_lieu_ca_nhan.py.
CREATE TABLE IF NOT EXISTS ho_so_khach (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_ref  TEXT NOT NULL,
    channel       TEXT NOT NULL,
    ten           TEXT NOT NULL DEFAULT '',
    sdt           TEXT,
    ghi_nho       JSONB NOT NULL DEFAULT '[]',
    lan_dau       TIMESTAMPTZ NOT NULL DEFAULT now(),
    lan_cuoi      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (customer_ref, channel)
);
CREATE INDEX IF NOT EXISTS idx_ho_so_cuoi ON ho_so_khach (lan_cuoi DESC);
CREATE INDEX IF NOT EXISTS idx_ho_so_sdt ON ho_so_khach (sdt) WHERE sdt IS NOT NULL;

-- --- Kho hàng ------------------------------------------------
-- Tồn kho là dữ liệu GIAO DỊCH: đổi mỗi lần bán, cần khoá hàng khi hai
-- khách cùng chốt món cuối. Nên nó nằm ở đây chứ không nằm trong
-- data/catalog.json — file đó giữ dữ liệu THAM CHIẾU (tên, giá, thành
-- phần) vốn ít đổi và nên vào được git.
CREATE TABLE IF NOT EXISTS ton_kho (
    ma           TEXT PRIMARY KEY,
    so_luong     INT NOT NULL DEFAULT 0 CHECK (so_luong >= 0),
    cap_nhat_luc TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sổ biến động. Không có nó thì khi tồn kho lệch với thực tế, không ai
-- truy được lệch từ đâu — và tồn kho LUÔN lệch, đó là chuyện thường ngày
-- của mọi kho hàng.
CREATE TABLE IF NOT EXISTS kho_bien_dong (
    id        BIGSERIAL PRIMARY KEY,
    ma        TEXT NOT NULL,
    thay_doi  INT  NOT NULL,          -- âm là xuất, dương là nhập
    ly_do     TEXT NOT NULL,          -- ban | huy_don | nhap | kiem_ke
    ma_don    TEXT,
    ghi_chu   TEXT,
    luc       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_kho_bd_ma  ON kho_bien_dong (ma, luc DESC);
CREATE INDEX IF NOT EXISTS idx_kho_bd_don ON kho_bien_dong (ma_don) WHERE ma_don IS NOT NULL;
