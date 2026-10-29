-- Việc do VẬN CHUYỂN sinh ra: hãng báo giao thất bại, hoặc gửi mã trạng
-- thái hệ thống không nhận ra. Trước bản này hai chuyện ấy chỉ để lại một
-- dòng nhật ký — kiện hàng có thể đang lạc mà không ai được giao đi gọi
-- khách (rà soát 29.10.2026).
--
-- Nguồn riêng `van_chuyen` để số "agent đẩy sang người" không đếm lẫn.
ALTER TABLE cong_viec DROP CONSTRAINT IF EXISTS cong_viec_nguon_check;
ALTER TABLE cong_viec ADD CONSTRAINT cong_viec_nguon_check
    CHECK (nguon IN ('nguoi', 'agent', 'tu_dong', 'van_chuyen'));

-- Khoá chống trùng: hãng phát lại webhook là chuyện thường, và lần phát
-- thứ hai không được đẻ việc thứ hai. Ràng buộc ở CSDL chứ không chỉ trong
-- mã: hai webhook về cùng lúc thì cả hai cùng thấy "chưa có việc".
ALTER TABLE cong_viec ADD COLUMN IF NOT EXISTS khoa_chong_trung TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_cong_viec_khoa_chong_trung
    ON cong_viec (khoa_chong_trung) WHERE khoa_chong_trung IS NOT NULL;
