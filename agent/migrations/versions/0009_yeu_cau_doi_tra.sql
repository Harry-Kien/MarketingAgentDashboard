-- Khách xin ĐỔI hoặc TRẢ hàng sau khi đã nhận — ghi nhận lên chính đơn.
--
-- VẤN ĐỀ ĐANG SỬA
-- ---------------
-- Đã có `xin_huy_don` cho giai đoạn TRƯỚC giao. Sau giao thì không có gì:
-- `data/knowledge/` mô tả chính sách đổi trả rất kỹ, nên agent NÓI về nó
-- rất tốt — nhưng không có chỗ nào GHI NHẬN yêu cầu.
--
-- Hệ quả: mọi ca đổi trả rơi vào `conversations.outcome = 'escalated'` với
-- một dòng lý do văn xuôi tự do. Không đếm được, không truy được, không có
-- hàng đợi riêng, và không có gì hiện lên màn hình Đơn hàng — đúng cùng
-- một lỗ mà cột `yeu_cau_huy_luc` đã bịt cho chiều trước giao.
--
-- VÌ SAO LÀ CỜ, KHÔNG PHẢI TRẠNG THÁI MỚI
-- ---------------------------------------
-- Cùng lý do với `yeu_cau_huy_luc`: `trang_thai` là vòng đời của ĐƠN, còn
-- đây là yêu cầu của KHÁCH. Trộn hai thứ vào một cột là sớm muộn có người
-- sửa nhầm thành "đã đổi trả xong".
--
-- VÌ SAO TÁCH `loai` RA KHỎI `ly_do`
-- ----------------------------------
-- Đổi size và trả lại lấy tiền là hai việc khác nhau với người xử lý: một
-- bên cần kiểm tồn kho, một bên cần duyệt hoàn tiền. Chôn khác biệt đó
-- trong một câu văn xuôi là bắt người đọc từng dòng để phân loại.
--
-- CHECK ràng đúng hai giá trị: để một cột tự do thì sáu tháng nữa nó chứa
-- 'doi', 'Đổi', 'DOI', 'đổi hàng' — và mọi truy vấn thống kê đều sai mà
-- không ai biết.

ALTER TABLE orders ADD COLUMN IF NOT EXISTS yeu_cau_doi_tra_luc   TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS yeu_cau_doi_tra_loai  TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS yeu_cau_doi_tra_ly_do TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'orders_yeu_cau_doi_tra_loai_check'
          AND conrelid = 'orders'::regclass
    ) THEN
        ALTER TABLE orders
            ADD CONSTRAINT orders_yeu_cau_doi_tra_loai_check
            CHECK (yeu_cau_doi_tra_loai IS NULL
                   OR yeu_cau_doi_tra_loai IN ('doi', 'tra'));
    END IF;
END
$$;

-- Chỉ đánh chỉ mục phần đang chờ người xử lý: đây là hàng đợi việc, luôn
-- ngắn, và là truy vấn màn hình Đơn hàng chạy mỗi lần mở. Cùng khuôn với
-- `idx_order_xin_huy`.
CREATE INDEX IF NOT EXISTS idx_order_xin_doi_tra
    ON orders (yeu_cau_doi_tra_luc DESC)
    WHERE yeu_cau_doi_tra_luc IS NOT NULL AND trang_thai <> 'da_huy';
