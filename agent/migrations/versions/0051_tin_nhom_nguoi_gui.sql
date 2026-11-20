-- Tin NHÓM Zalo: người gửi từng tin, và đánh dấu hội thoại nhóm cũ.
--
-- 1) Người gửi của TỪNG tin.
--
--    Hội thoại nhóm mang danh tính của NHÓM (customer_ref `group:<id>`),
--    nên `conversations.customer_name` không còn nói được ai gõ câu nào.
--    Trước bản này `messages` không có cột người gửi: trong nhóm mọi thành
--    viên hiện thành một "Khách", và cách duy nhất để biết ai nói là... ghi
--    đè tên hội thoại bằng người nói sau cùng — đúng lỗi đang sửa.
--
--    Cho phép NULL: tin cũ không có, tin của agent/nhân viên không cần.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender_ref TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS sender_name TEXT;

-- 2) Đánh dấu loại thread cho hội thoại Zalo cá nhân còn RỖNG.
--
--    Backfill của 0042 dựa vào `tin_vao`, mà hộp thư bền chỉ giữ 3 ngày —
--    hội thoại cũ hơn vẫn NULL, adapter gửi đọc NULL thành 0 (nhắn riêng),
--    và câu trả lời của nhân viên vào nhóm bị Zalo huỷ với "Tham số không
--    hợp lệ" (đã xảy ra thật trên production).
--
--    Dấu hiệu dùng ở đây là thứ duy nhất CÒN trên mọi dòng: ở tin nhắn
--    riêng, thread của Zalo CHÍNH LÀ người kia, nên `external_id` (thread)
--    trùng `customer_ref` (người gửi). Hội thoại nhóm thì `external_id` là
--    id nhóm, còn `customer_ref` là id người gửi (dữ liệu cũ) hoặc
--    `group:<id>` (dữ liệu mới) — hai thứ khác nhau.
--
--    BẢO THỦ: chỉ đụng kênh zalo_personal, chỉ dòng `thread_type IS NULL`,
--    chỉ khi có `customer_ref`. Không đoán được thì để NULL. KHÔNG sửa tên,
--    contact hay customer_ref của các hội thoại nhóm cũ — contact của một
--    thành viên đã bị nhóm làm bẩn thì để người xem lại; tin nhóm kế tiếp
--    tự gắn hội thoại sang contact riêng của nhóm (inbox_service).
UPDATE conversations
SET thread_type = CASE WHEN external_id <> customer_ref THEN 1 ELSE 0 END
WHERE channel = 'zalo_personal'
  AND thread_type IS NULL
  AND customer_ref IS NOT NULL
  AND customer_ref <> '';
