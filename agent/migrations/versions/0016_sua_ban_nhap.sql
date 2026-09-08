-- Quản lý sửa bản nháp AI trước khi gửi.
--
-- VÌ SAO GIỮ BẢN GỐC THAY VÌ GHI ĐÈ `content`
--
-- `confidence`, `grounded`, `model`, `cost_usd` trên cùng dòng ấy là số đo
-- của bản AI viết. Ghi đè `content` mà không cất bản gốc thì những con số
-- đó gắn vào câu do NGƯỜI viết, và bộ đo chất lượng agent chấm điểm cho văn
-- của người — điểm càng đẹp khi agent càng viết dở. Xanh giả.
--
-- Giữ bản gốc còn trả lời được một câu hỏi vận hành thật: agent hay bị sửa
-- ở chỗ nào? Đó là đầu vào để đi sửa prompt, và nó chỉ có nếu bản gốc còn.
--
-- Ba cột đều NULL được: mọi dòng cũ giữ nguyên, `noi_dung_goc IS NULL`
-- nghĩa là "chưa ai sửa" — không cần backfill.

ALTER TABLE messages ADD COLUMN IF NOT EXISTS noi_dung_goc TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS sua_boi TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS sua_luc TIMESTAMPTZ;
