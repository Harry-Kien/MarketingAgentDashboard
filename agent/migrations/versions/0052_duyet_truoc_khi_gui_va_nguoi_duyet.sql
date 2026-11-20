-- Cờ "Duyệt trước khi gửi" RIÊNG của hội thoại, và người duyệt bản nháp AI.
--
-- VÌ SAO KHÔNG DÙNG LẠI `conversations.mode = 'assist'`
-- `mode = 'assist'` mang HAI nghĩa: máy tự đặt sau mỗi lượt AI soạn nháp ở
-- chế độ chung Gợi ý, và nhân viên chủ động chọn "Duyệt trước khi gửi" cho
-- một hội thoại. Luật gửi chỉ xét chế độ chung (rà soát 20.11.2026), nên
-- lựa chọn của nhân viên bị bỏ qua khi chế độ chung là Tự động — AI vẫn gửi
-- thẳng. Mà nếu cho luật gửi tôn trọng mọi `mode = 'assist'` thì bật chế độ
-- chung Tự động xong, mọi hội thoại từng có nháp không bao giờ tự gửi nữa.
-- Một cột riêng chỉ nhân viên đặt mới tách được hai nghĩa.
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS duyet_truoc_khi_gui BOOLEAN NOT NULL DEFAULT false;

-- Duyệt bản nháp KHÔNG sửa trước đây không để lại dấu vết người duyệt:
-- `sua_boi` chỉ ghi khi có sửa, `gui_boi` chỉ ghi tin nhân viên tự gõ.
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS duyet_boi UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS duyet_luc TIMESTAMPTZ;
