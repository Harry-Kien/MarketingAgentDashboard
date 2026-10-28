-- Việc do QUY TẮC TỰ ĐỘNG sinh ra mang nguồn riêng `tu_dong`.
--
-- Gộp vào `agent` thì hai thứ hỏng: số "agent đẩy sang người bao nhiêu việc"
-- bị đếm lẫn việc của quy tắc, và việc của quy tắc đụng chốt "mỗi hội thoại
-- một việc agent đang mở" (idx_cong_viec_agent_mot_viec) — quy tắc ghi "đã
-- tạo việc" trong khi không có việc nào (rà soát 28.10.2026).
ALTER TABLE cong_viec DROP CONSTRAINT IF EXISTS cong_viec_nguon_check;
ALTER TABLE cong_viec ADD CONSTRAINT cong_viec_nguon_check
    CHECK (nguon IN ('nguoi', 'agent', 'tu_dong'));
