-- HỘP THƯ BỀN: tin khách được ghi vào đây TRƯỚC khi webhook trả 200
-- (tiếp nối 0045 — điểm hở cuối cùng đã biết).
--
-- Trước bản này mọi webhook trả 200 rồi mới xử lý trong BackgroundTasks:
-- app chết đúng khoảnh khắc ấy (máy ngủ, người canh dựng lại, deploy) là
-- tin biến mất — hãng đã nhận 200 nên không gửi lại, CSDL không có dòng
-- nào, không ai biết.
--
-- Một dòng = một tin của kênh, chờ `xu_ly_tin_vao.handle_inbound`. Bảng tự
-- dọn (agent/omnichannel/hop_thu_ben.py): nội dung là lời khách — không giữ
-- lâu hơn cần thiết.
CREATE TABLE IF NOT EXISTS tin_vao (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dedupe_key  TEXT        NOT NULL,
    account_id  UUID,
    kenh        TEXT        NOT NULL,
    payload     JSONB       NOT NULL,
    trang_thai  TEXT        NOT NULL DEFAULT 'cho'
        CHECK (trang_thai IN ('cho', 'dang_xu_ly', 'xong', 'chet')),
    so_lan_thu  INT         NOT NULL DEFAULT 0,
    cho_den     TIMESTAMPTZ NOT NULL DEFAULT now(),
    khoa_luc    TIMESTAMPTZ,
    loi         TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Hãng phát lại webhook (chuyện thường) không sinh dòng thứ hai.
CREATE UNIQUE INDEX IF NOT EXISTS idx_tin_vao_dedupe
    ON tin_vao (dedupe_key) WHERE dedupe_key <> '';
CREATE INDEX IF NOT EXISTS idx_tin_vao_cho
    ON tin_vao (trang_thai, cho_den) WHERE trang_thai IN ('cho', 'dang_xu_ly');

