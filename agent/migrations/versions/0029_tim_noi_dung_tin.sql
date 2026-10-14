-- Tìm hội thoại theo NỘI DUNG tin nhắn, gõ không dấu vẫn ra.
--
-- VÌ SAO TRIGRAM CHỨ KHÔNG FULL-TEXT SEARCH
-- ----------------------------------------
-- Postgres không có từ điển tiếng Việt: `to_tsvector('simple', …)` tách
-- theo khoảng trắng, nên "kem chống nắng" chỉ khớp khi gõ đủ cả từ. Người
-- trực lại gõ MẢNH: "chong nan", "0912", "đơn AS2510". Trigram trên bản đã
-- bỏ dấu (`public.bo_dau`, xem schema.sql) cho `LIKE '%mảnh%'` dùng được chỉ
-- mục, gõ thiếu dấu hay thiếu chữ đều ra.
--
-- pg_trgm là extension "trusted" từ Postgres 13: chủ CSDL không phải
-- superuser vẫn tạo được — quan trọng khi lên Postgres dịch vụ (SaaS).

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_messages_noi_dung_trgm
    ON messages USING gin (pg_catalog.lower(public.bo_dau(content)) public.gin_trgm_ops);
