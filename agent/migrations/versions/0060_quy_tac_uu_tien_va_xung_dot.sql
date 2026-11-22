-- Quy tắc tự động: hai cờ cho chính sách xung đột (agent/omnichannel/tu_dong.py).
--
-- VÌ SAO LÀ CỘT, KHÔNG NHÉT VÀO `hanh_dong`
-- `hanh_dong` là danh sách việc LÀM; hai cờ này nói quy tắc ĐỨNG Ở ĐÂU so
-- với các quy tắc khác và với AI. Để trong JSON thì mỗi chỗ đọc phải tự
-- đoán giá trị thiếu, và một lần lưu thiếu khoá là cờ lặng lẽ về mặc định.
--
-- `dung_xet_sau`   quy tắc này KHỚP thì không xét quy tắc nào xếp sau nó.
-- `cho_ai_tra_loi` quy tắc này đã gửi mẫu cho khách mà AI VẪN trả lời chính
--                  tin ấy. Mặc định KHÔNG: khách nhận "sáng mai em trả lời"
--                  rồi ngay sau đó một câu AI tư vấn là hai lời mâu thuẫn.
--
-- Thứ tự ưu tiên đã có từ 0033 (`thu_tu`); hai quy tắc cùng số thì xếp theo
-- `tao_luc` rồi `id` — đủ để cùng một bộ quy tắc luôn chạy cùng một thứ tự.
-- Hai câu ALTER riêng, không gộp: scripts/sinh_so_do.py đọc MỘT cột mỗi câu
-- `ADD COLUMN`, gộp lại là sơ đồ CSDL lặng lẽ thiếu một cột.
ALTER TABLE quy_tac_tu_dong ADD COLUMN IF NOT EXISTS dung_xet_sau BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE quy_tac_tu_dong ADD COLUMN IF NOT EXISTS cho_ai_tra_loi BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_quy_tac_tu_dong_thu_tu
    ON quy_tac_tu_dong (thu_tu, tao_luc, id) WHERE bat;
