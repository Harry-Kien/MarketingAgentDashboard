-- Cấu hình agent sống qua khởi động lại.
--
-- LỖI THẬT, ĐO ĐƯỢC (03.09.2026)
--
--   POST /api/runtime {"confidence_floor": 0.9, "mode": "auto"}
--   -> 0.9 / auto          đúng như vừa đặt
--   khởi động lại máy chủ
--   -> 0.55 / assist       về mặc định, KHÔNG một dòng cảnh báo nào
--
-- `agent/runtime.py` giữ `STATE` trong bộ nhớ tiến trình. Tầng API có gọi
-- `db.log_event("runtime.update")`, nên nhật ký kiểm toán ghi rằng người ta
-- ĐÃ ĐỔI — nhưng giá trị thì không ở đâu cả. Nhật ký nói một đằng, hệ thống
-- chạy một nẻo, và không có gì đối chiếu hai thứ.
--
-- HẬU QUẢ THẬT, cả ba đều im lặng:
--
--   mode=auto  -> restart -> assist
--     Agent thôi tự trả lời. Tin khách vẫn vào, agent vẫn soạn, chỉ là
--     không ai bấm gửi. Khách ngồi chờ tới khi có người mở dashboard.
--
--   confidence_floor cao -> restart -> 0.55
--     Người vận hành nâng ngưỡng vì thấy agent trả lời ẩu. Sau restart nó
--     ẩu lại y như cũ, và người đã nâng ngưỡng thì tin là mình đã sửa.
--
--   max_cost thấp -> restart -> 0.25
--     Trần chi phí về mặc định. Phát hiện bằng hoá đơn.
--
-- Đúng họ với `ky_nang_cai_dat` (migration 0010): thứ người vận hành chỉnh
-- lúc 2 giờ sáng phải còn nguyên lúc 4 giờ máy chủ khởi động lại.
--
-- VÌ SAO KHOÁ–GIÁ TRỊ CHỨ KHÔNG PHẢI MỘT CỘT MỖI THIẾT LẬP
--
-- `STATE` là một dict, và mỗi thiết lập thêm vào sau này sẽ là một khoá mới.
-- Một cột mỗi thiết lập nghĩa là mỗi lần thêm phải viết migration — và
-- người viết sẽ chọn cách rẻ hơn: nhét vào .env, tức là quay lại đúng chỗ
-- migration này đang sửa.
--
-- Giá trị lưu dạng JSONB để giữ KIỂU: `0.9` là số, `"auto"` là chuỗi,
-- `true` là bool. Lưu hết thành TEXT thì lúc đọc lên phải đoán kiểu, và
-- `bool("false")` trong Python là True.

CREATE TABLE IF NOT EXISTS cau_hinh_agent (
    khoa      TEXT PRIMARY KEY,
    gia_tri   JSONB NOT NULL,
    sua_boi   TEXT,
    sua_luc   TIMESTAMPTZ NOT NULL DEFAULT now()
);
