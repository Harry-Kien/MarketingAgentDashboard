-- agent/migrations/versions/0015_chi_muc_su_kien_theo_loai.sql
-- Chỉ mục cho câu đếm 7 ngày của bảng Kỹ năng / Gói kỹ năng.
--
-- VÌ SAO CẦN: `events` là bảng lớn nhất và lớn nhanh nhất — MỖI lời gọi công
-- cụ thêm một dòng `cong_cu.goi`, cộng mọi sự kiện vận hành khác. Câu đếm
-- lọc theo `kind = 'cong_cu.goi'` rồi `created_at > now() - interval '7 days'`,
-- và dashboard chạy nó lại mỗi 6 giây. Không có chỉ mục thì đó là một lần
-- quét toàn bảng mỗi 6 giây, và cái giá ấy tăng đều theo lượng khách — kiểu
-- hỏng không nổ, chỉ chậm dần cho tới lúc không ai hiểu vì sao dashboard ì.
--
-- VÌ SAO (kind, created_at DESC) chứ không hai chỉ mục rời: bộ lọc luôn cố
-- định `kind` trước rồi cắt theo thời gian, nên một chỉ mục ghép đọc đúng
-- một dải liên tục; hai chỉ mục rời buộc Postgres hợp nhất bitmap.

CREATE INDEX IF NOT EXISTS idx_event_kind_time ON events (kind, created_at DESC);
