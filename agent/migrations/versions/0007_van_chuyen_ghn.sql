-- Vận chuyển qua API hãng (GHN / GHTK / Mock) — gộp về MỘT bộ cột.
--
-- VẤN ĐỀ ĐANG SỬA
-- ---------------
-- Migration 0006 dựng vòng đời giao hàng "đọc sổ cửa hàng": `trang_thai_giao`,
-- `hang_van_chuyen`, `ma_trang_thai_hang`, `giao_cap_nhat_luc`, với CHECK
-- ràng giá trị tiếng Việt (dang_giao / da_giao / giao_that_bai / hoan_ve).
--
-- Phần kết nối GHN đưa vào sau lại dùng bộ tên khác cho ĐÚNG NHỮNG THỨ ĐÓ,
-- kèm bộ giá trị tiếng Anh khớp `InternalShippingStatus`.
--
-- Hai bộ cột cho một khái niệm là hai nguồn sự thật. Sớm muộn một nửa mã ghi
-- vào bộ này, một nửa đọc từ bộ kia, và không ai biết bên nào đúng — đúng
-- kiểu hỏng im lặng mà dự án này sợ nhất.
--
-- VÌ SAO GIỮ BỘ TÊN MỚI, KHÔNG GIỮ BỘ CŨ
-- ---------------------------------------
-- Bộ mới đi kèm cả phân hệ đã chạy được: tạo vận đơn, webhook hãng báo về,
-- lịch sử lộ trình, phí vận chuyển. Bộ cũ chỉ có bốn cột và một CHECK ràng
-- giá trị tiếng Việt — CHECK đó sẽ TỪ CHỐI mọi giá trị mà mã mới ghi vào.
--
-- VÌ SAO XOÁ ĐƯỢC AN TOÀN
-- ------------------------
-- Đã đếm trước khi viết migration này: bảng `orders` có 0 dòng, và cả bốn
-- cột cũ đều 0 dòng có dữ liệu. Không mất gì. Nếu về sau chạy trên CSDL đã
-- có dữ liệu, câu UPDATE bên dưới chuyển giá trị sang trước khi xoá.

-- Bộ cột dùng chung cho mọi hãng.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS ma_van_don TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS don_vi_van_chuyen TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS trang_thai_giao_hang TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS phi_van_chuyen BIGINT NOT NULL DEFAULT 0;
-- Giữ nguyên văn từng mốc hãng báo. Cần nó khi khách khiếu nại "shop nói
-- giao rồi mà tôi chưa nhận": không có sổ thì không ai dựng lại được chuyện.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS lich_su_giao_hang JSONB NOT NULL DEFAULT '[]';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS ngay_du_kien_giao TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cap_nhat_van_chuyen_luc TIMESTAMPTZ;

-- Chuyển dữ liệu cũ sang (nếu có), ánh xạ luôn giá trị tiếng Việt -> tiếng Anh.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'orders' AND column_name = 'trang_thai_giao'
    ) THEN
        UPDATE orders SET
            trang_thai_giao_hang = COALESCE(trang_thai_giao_hang, CASE trang_thai_giao
                WHEN 'dang_giao'      THEN 'delivering'
                WHEN 'da_giao'        THEN 'delivered'
                WHEN 'giao_that_bai'  THEN 'delivery_failed'
                WHEN 'hoan_ve'        THEN 'returned'
                ELSE NULL END),
            don_vi_van_chuyen = COALESCE(don_vi_van_chuyen, hang_van_chuyen),
            cap_nhat_van_chuyen_luc = COALESCE(cap_nhat_van_chuyen_luc, giao_cap_nhat_luc)
        WHERE trang_thai_giao IS NOT NULL
           OR hang_van_chuyen IS NOT NULL
           OR giao_cap_nhat_luc IS NOT NULL;
    END IF;
END $$;

-- Xoá bộ cũ cùng CHECK của nó. CHECK phải đi trước: nó ràng cột sắp xoá.
ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_trang_thai_giao_check;
DROP INDEX IF EXISTS idx_order_dang_giao;
ALTER TABLE orders DROP COLUMN IF EXISTS trang_thai_giao;
ALTER TABLE orders DROP COLUMN IF EXISTS hang_van_chuyen;
ALTER TABLE orders DROP COLUMN IF EXISTS ma_trang_thai_hang;
ALTER TABLE orders DROP COLUMN IF EXISTS giao_cap_nhat_luc;

-- Webhook của hãng tra đơn theo mã vận đơn. Không có chỉ mục thì mỗi lần
-- hãng báo trạng thái là một lần quét toàn bảng.
CREATE INDEX IF NOT EXISTS idx_order_waybill ON orders (ma_van_don)
    WHERE ma_van_don IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_order_ship_status ON orders (trang_thai_giao_hang)
    WHERE trang_thai_giao_hang IS NOT NULL;

-- Một mã vận đơn chỉ thuộc về MỘT đơn. Thiếu ràng buộc này thì một lần gọi
-- tạo vận đơn hai lần sẽ sinh hai đơn cùng mã, và webhook cập nhật nhầm đơn.
CREATE UNIQUE INDEX IF NOT EXISTS idx_order_waybill_unique ON orders (ma_van_don)
    WHERE ma_van_don IS NOT NULL;
