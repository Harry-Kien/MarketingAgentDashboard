-- Vé một lần cho n8n gọi báo kết quả đăng bài.
--
-- VẤN ĐỀ ĐANG SỬA
-- ---------------
-- `agent/publish/n8n.py` gửi `callback_url` trỏ vào
-- `POST /api/posts/{id}/callback`, nhưng đường ấy nằm sau chốt đăng nhập
-- `/api/*` và sau `can_quyen("noi_dung.duyet")`. n8n không có cookie phiên
-- nên nhận 401 — mọi lần, từ trước tới nay.
--
-- Hậu quả đúng kiểu repo này hay gặp: KHÔNG NỔ. Bài vẫn chuyển sang
-- "đang đăng", n8n vẫn đăng thật lên nền tảng, chỉ có kết quả là không bao
-- giờ được ghi lại. Dashboard hiện "đang đăng" vĩnh viễn, `post_metrics`
-- rỗng, và vòng phản hồi "nội dung nào chạy tốt" chết câm.
--
-- VÌ SAO LÀ VÉ LƯU TRONG BẢNG, KHÔNG PHẢI HMAC
-- ---------------------------------------------
-- Ký bằng HMAC thì không cần cột nào, nhưng phải có một bí mật CHẮC CHẮN
-- tồn tại để làm khoá. Trong `.env` không có khoá nào như vậy:
-- `WEBHOOK_SECRET`, `N8N_AUTH_HEADER`, `CREDENTIAL_MASTER_KEYS` đều có thể
-- rỗng. Khoá rỗng thì HMAC thành một hằng số ai cũng tính được — tức là
-- một chốt trông như chốt mà không khoá gì.
--
-- Vé ngẫu nhiên lưu tại dòng bài đăng thì không cần cấu hình gì, và phạm
-- vi của nó hẹp nhất có thể: một vé mở đúng MỘT bài, dùng xong xoá.
ALTER TABLE posts ADD COLUMN IF NOT EXISTS callback_token TEXT;

-- Chỉ mục bộ phận: tra theo vé chỉ xảy ra với bài đang chờ n8n báo về,
-- còn lại NULL. Chỉ mục đầy đủ ở đây là trả tiền cho mọi dòng để phục vụ
-- một thiểu số.
CREATE INDEX IF NOT EXISTS idx_post_callback_token
    ON posts (callback_token) WHERE callback_token IS NOT NULL;
