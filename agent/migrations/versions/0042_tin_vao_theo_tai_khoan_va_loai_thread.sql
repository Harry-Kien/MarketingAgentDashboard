-- Hai lỗ ở đường TIN VÀO (rà soát 16.11.2026).
--
-- 1) Chỉ mục chống trùng của hộp thư bền (0040) là TOÀN CỤC theo
--    `dedupe_key`, trong khi `webhook_deliveries` chống trùng theo
--    (account_id, dedupe_key). Hai nick Zalo cùng ở một nhóm nhận CÙNG một
--    msgId → khoá `zalo_personal:<msgId>` trùng nhau → bản của nick thứ hai
--    bị `ON CONFLICT DO NOTHING` nuốt: không dòng, không lỗi, không nhật ký.
--    Chống trùng phải theo đúng phạm vi mà hãng phát lại: từng tài khoản.
--
--    NULLS NOT DISTINCT: `account_id` cho phép NULL; không có cờ này thì
--    hai dòng NULL không bao giờ "trùng" và việc chống phát lại tắt câm.
DROP INDEX IF EXISTS idx_tin_vao_dedupe;
CREATE UNIQUE INDEX IF NOT EXISTS idx_tin_vao_tk_dedupe
    ON tin_vao (account_id, dedupe_key) NULLS NOT DISTINCT
    WHERE dedupe_key <> '';

-- 2) Loại thread phía kênh (Zalo: 0 nhắn riêng, 1 nhóm), lưu BỀN.
--
--    Trước đây chỉ nhớ trong RAM của adapter TẠM dựng ở webhook; adapter
--    GỬI là instance khác (cache của registry) nên luôn gửi 0 — trả lời vào
--    nhóm bị Zalo từ chối "Tham số không hợp lệ". NULL = chưa biết / kênh
--    không có khái niệm này; đọc NULL thì coi là 0.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS thread_type SMALLINT;

-- Điền cho hội thoại Zalo cá nhân còn tin trong hộp thư bền (giữ 3 ngày):
-- đó là nguồn duy nhất còn biết loại thread của các hội thoại đã có.
UPDATE conversations c
SET thread_type = (t.payload -> 'meta' ->> 'thread_type')::smallint
FROM tin_vao t
WHERE c.thread_type IS NULL
  AND t.kenh = 'zalo_personal'
  AND jsonb_typeof(t.payload) = 'object'
  AND (t.payload -> 'meta' ->> 'thread_type') ~ '^[0-9]+$'
  AND t.account_id = c.account_id
  AND t.payload ->> 'conversation_ref' = c.external_id;
