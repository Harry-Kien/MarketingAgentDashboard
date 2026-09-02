-- Đồng bộ đơn sang ERP.
--
-- VÌ SAO KHÔNG DÙNG `omnichannel/outbox.py`
-- -----------------------------------------
-- Thiết kế ban đầu ghi "dùng chính outbox có sẵn, thêm loại job erp.tao_don".
-- Đọc kỹ thì sai: outbox đó gắn chặt `account_id`, `conversation_id`,
-- `message_id`, và ánh xạ trạng thái job sang `messages.delivery_status`.
-- Nó là outbox GỬI TIN NHẮN, không phải hàng đợi việc tổng quát. Nhét việc
-- ERP vào đó là bẻ nó, và tạo một đơn "tồn tại" ở hai nơi.
--
-- Chính bảng `orders` là hàng đợi: đơn `trang_thai='cho_dong_bo'` là việc
-- chưa xong. Một nguồn sự thật cho đơn, không hai.
--
-- VÌ SAO TÁCH CỘT RIÊNG, KHÔNG NHỒI VÀO `ghi_chu`
-- -----------------------------------------------
-- `ghi_chu` là văn xuôi cho người đọc. Bộ đối soát cần truy vấn được: đơn
-- nào kẹt, kẹt bao lâu, thử mấy lần. Nhồi vào văn xuôi là buộc bộ đối soát
-- đi phân tích chuỗi, và nó sẽ bỏ sót trong im lặng.

-- Mã đơn bên ERP. NULL nghĩa là chưa đẩy, hoặc đẩy chưa xong.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_ma_don TEXT;

-- Lần đẩy thành công gần nhất.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_dong_bo_luc TIMESTAMPTZ;

-- Đã thử mấy lần. Dùng cho backoff và để cảnh báo đơn kẹt.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_so_lan_thu INT NOT NULL DEFAULT 0;

-- Lý do lần thử cuối hỏng. Người trực đọc cái này khi đi chữa.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS erp_loi TEXT;

-- Một mã đơn bên ERP thuộc về đúng một đơn bên này.
--
-- Đây là lưới CUỐI chống đơn trùng. Bốn lớp trước nó — khoá idempotency gửi
-- kèm, bước tra trước khi tạo, chốt chống trùng của `_tao_don_hang`, và cột
-- `erp_ma_don` đã có giá trị — đều là mã, và mã thì trượt được. Ràng buộc
-- CSDL thì không.
CREATE UNIQUE INDEX IF NOT EXISTS idx_order_erp_ma_don
    ON orders (erp_ma_don) WHERE erp_ma_don IS NOT NULL;

-- Vòng lặp nền chỉ quét đơn CHƯA đồng bộ xong. Quét cả bảng mỗi phút là
-- đốt CPU cho việc không có gì thay đổi.
CREATE INDEX IF NOT EXISTS idx_order_cho_dong_bo
    ON orders (created_at) WHERE trang_thai = 'cho_dong_bo';
