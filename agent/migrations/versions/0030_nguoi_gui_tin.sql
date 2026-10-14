-- Tin của nhân viên ghi lại AI đã gửi.
--
-- VÌ SAO
-- ------
-- `messages.role = 'staff'` nói "một người đã gửi", không nói người nào.
-- Không có cột này thì không có báo cáo hiệu suất theo nhân viên — thứ mọi
-- phần mềm CSKH ở VN đều có (Pancake: số tin, thời gian phản hồi, đơn chốt
-- theo từng người) — và cũng không trả lời được câu hỏi tranh chấp thường
-- gặp nhất: "ai đã nhắn câu đó cho khách?".
--
-- NULL cho tin cũ và cho tin của agent/hệ thống: không đoán ngược người gửi
-- của dữ liệu đã có — một con số bịa trong báo cáo hiệu suất là một lần
-- đánh giá sai một người thật.

ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS gui_boi UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_messages_gui_boi
    ON messages (gui_boi, created_at) WHERE gui_boi IS NOT NULL;
