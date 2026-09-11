-- Bật/tắt agent theo TỪNG tài khoản kênh.
--
-- VÌ SAO CẦN, KHI ĐÃ CÓ CÔNG TẮC TOÀN CỤC
-- ----------------------------------------
-- `runtime.enabled` là một công tắc cho cả hệ thống: bật thì agent trả lời
-- mọi kênh, tắt thì không trả lời kênh nào. Không có nấc giữa.
--
-- Nhưng cách người ta thật sự dùng lại là nấc giữa: mở Zalo cho agent trả
-- lời vì tin ở đó đơn giản và nhiều, còn Facebook thì để người trực vì
-- khách ở đó hỏi khó hơn. Không có cột này thì lựa chọn duy nhất là tắt
-- sạch — và tắt sạch nghĩa là agent không dùng được, tức yêu cầu "agent là
-- một lựa chọn" chỉ đúng theo nghĩa có/không.
--
-- MẶC ĐỊNH `true`, CÓ CHỦ Ý
-- --------------------------
-- Cột này thêm vào một hệ thống đang chạy. Mặc định `false` là sáng hôm sau
-- agent im lặng trên mọi kênh, và không ai hiểu vì sao — migration không
-- được là chỗ đổi hành vi của thứ đang chạy.
--
-- TẮT AGENT KHÔNG ĐƯỢC LÀM TIN BIẾN MẤT
-- --------------------------------------
-- Ràng buộc quan trọng nhất của cả khối này, và nó nằm ở MÃ chứ không ở
-- đây: khi agent tắt cho một kênh, tin khách vẫn phải vào, hội thoại vẫn
-- phải chuyển sang người, và phải sinh một công việc.
--
-- Bỏ vế ấy thì "agent tuỳ chọn" biến thành "kênh chết im lặng": tin vào,
-- không ai trả lời, và dashboard vẫn xanh vì không có gì hỏng cả.

ALTER TABLE channel_accounts
    ADD COLUMN IF NOT EXISTS agent_bat BOOLEAN NOT NULL DEFAULT true;

-- Ai tắt, lúc nào, và vì sao. Không ghi thì câu hỏi "vì sao kênh này agent
-- không trả lời" chỉ có một cách trả lời: đoán.
ALTER TABLE channel_accounts
    ADD COLUMN IF NOT EXISTS agent_tat_boi TEXT;
ALTER TABLE channel_accounts
    ADD COLUMN IF NOT EXISTS agent_tat_luc TIMESTAMPTZ;
ALTER TABLE channel_accounts
    ADD COLUMN IF NOT EXISTS agent_tat_ly_do TEXT;
