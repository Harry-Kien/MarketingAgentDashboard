-- Vòng đời giao hàng cho đơn hàng.
--
-- VẤN ĐỀ
-- ------
-- `orders.trang_thai` chỉ có cho_duyet / da_chot / da_huy. Sau khi chốt,
-- hệ thống không biết gì thêm — nên câu hỏi phổ biến NHẤT sau bán, "đơn em
-- tới đâu rồi?", agent không trả lời được.
--
-- VÌ SAO TÁCH CỘT RIÊNG, KHÔNG NHỒI VÀO `trang_thai`
-- ---------------------------------------------------
-- `trang_thai` nói về VÒNG DUYỆT: đơn đã được chốt chưa, có bị huỷ không.
-- Giao hàng là một trục khác: một đơn `da_chot` có thể đang giao, đã giao,
-- hoặc hoàn về. Nhồi hai trục vào một cột là mỗi lần thêm trạng thái lại
-- phải sửa mọi truy vấn đang lọc theo cột đó.
--
-- Cột mới cho phép NULL: đơn chưa bàn giao vận chuyển thì chưa có trạng
-- thái giao, và NULL nói đúng điều đó — khác hẳn với "đang giao".

ALTER TABLE orders ADD COLUMN IF NOT EXISTS ma_van_don TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS trang_thai_giao TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS hang_van_chuyen TEXT;
-- Mã trạng thái GỐC của hãng. Giữ lại vì bảng ánh xạ sẽ lỗi thời: hãng đổi
-- mã thì mã lạ rơi vào `khong_ro`, và người vận hành cần thấy hãng đang nói
-- gì để bổ sung vào bảng — thay vì đoán.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS ma_trang_thai_hang TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS giao_cap_nhat_luc TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'orders_trang_thai_giao_check'
    ) THEN
        ALTER TABLE orders
            ADD CONSTRAINT orders_trang_thai_giao_check
            CHECK (trang_thai_giao IS NULL OR trang_thai_giao IN (
                'dang_giao', 'da_giao', 'giao_that_bai', 'hoan_ve', 'khong_ro'
            ));
    END IF;
END
$$;

-- Một mã vận đơn thuộc về đúng một đơn. Tạo trùng là dấu hiệu lỗi logic,
-- và bắt bằng ràng buộc rẻ hơn bắt bằng mắt.
CREATE UNIQUE INDEX IF NOT EXISTS idx_order_ma_van_don
    ON orders (ma_van_don) WHERE ma_van_don IS NOT NULL;

-- Vòng lặp nền chỉ hỏi hãng về đơn ĐANG trên đường. Hỏi lại đơn đã giao
-- xong là đốt hạn mức gọi API vô ích.
CREATE INDEX IF NOT EXISTS idx_order_dang_giao
    ON orders (trang_thai_giao) WHERE trang_thai_giao = 'dang_giao';
