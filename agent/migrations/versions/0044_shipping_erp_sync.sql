-- DEV-02: trạng thái đồng bộ vận đơn sang ERPNext.
--
-- Mã vận đơn đã được GHN cấp là sự thật độc lập với việc ERPNext đã nhận
-- hay chưa. Vì vậy không dùng một cờ boolean: cần phân biệt chờ, đang làm,
-- thử lại, hoàn tất và lỗi cần người đối soát.

ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_van_chuyen_trang_thai TEXT
    NOT NULL DEFAULT 'not_required';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_van_chuyen_so_lan_thu INT
    NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_van_chuyen_thu_lai_luc TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_van_chuyen_loi TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_van_chuyen_dong_bo_luc TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_van_chuyen_khoa_luc TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_van_chuyen_khoa_boi TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'orders_erp_van_chuyen_trang_thai_check'
    ) THEN
        ALTER TABLE orders ADD CONSTRAINT orders_erp_van_chuyen_trang_thai_check
        CHECK (erp_van_chuyen_trang_thai IN (
            'not_required', 'pending', 'processing', 'retry', 'synced', 'dead'
        ));
    END IF;
END $$;

-- Vận đơn cũ có đủ liên kết ERP phải được nhặt lên sau khi triển khai; vận
-- đơn chưa có Sales Order không được đoán và cập nhật nhầm chứng từ.
UPDATE orders
SET erp_van_chuyen_trang_thai = 'pending',
    erp_van_chuyen_thu_lai_luc = now()
WHERE ma_van_don IS NOT NULL
  AND erp_ma_don IS NOT NULL
  AND erp_van_chuyen_trang_thai = 'not_required';

CREATE INDEX IF NOT EXISTS idx_order_erp_van_chuyen_cho
    ON orders (erp_van_chuyen_thu_lai_luc, created_at)
    WHERE erp_van_chuyen_trang_thai IN ('pending', 'retry', 'processing');

