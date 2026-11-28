-- BUG-17-04: nhất quán trạng thái đơn hàng, vận đơn, tồn kho và đồng bộ ERPNext.
--
-- 1. `van_don_da_lay_hang`:
--    - NULL  : đơn cũ (không đủ dữ liệu xác định shipper đã lấy hàng hay chưa)
--              -> xử lý an toàn, KHÔNG tự động hoàn tồn kho khi huỷ vận đơn.
--    - FALSE : vận đơn mới tạo ở trạng thái chờ lấy hàng (`ready_to_pick`),
--              chưa từng ghi nhận bước lấy hàng / trung chuyển.
--    - TRUE  : hãng đã lấy hàng hoặc đã đi vào luồng giao/hoàn/giao xong;
--              một chiều, không bao giờ hạ ngược về FALSE.
--
-- 2. Mở rộng CHECK `orders_erp_van_chuyen_trang_thai_check` thêm
--    `'skipped_cancelled'` để dừng đồng bộ vận đơn gọn gàng khi Sales Order
--    trên ERPNext đã bị huỷ (`docstatus = 2`), tránh báo `dead` và sinh việc giả.

ALTER TABLE orders ADD COLUMN IF NOT EXISTS van_don_da_lay_hang BOOLEAN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'orders_erp_van_chuyen_trang_thai_check'
    ) THEN
        ALTER TABLE orders DROP CONSTRAINT orders_erp_van_chuyen_trang_thai_check;
    END IF;

    ALTER TABLE orders ADD CONSTRAINT orders_erp_van_chuyen_trang_thai_check
    CHECK (erp_van_chuyen_trang_thai IN (
        'not_required', 'pending', 'processing', 'retry', 'synced', 'dead',
        'skipped_cancelled'
    ));
END $$;
