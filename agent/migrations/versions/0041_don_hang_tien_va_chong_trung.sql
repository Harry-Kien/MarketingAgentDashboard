-- Đơn hàng: bỏ chống trùng VĨNH VIỄN, thêm sổ "đã thu tiền", thêm nguồn việc
-- `don_hang` (rà soát 16.11.2026).

-- 1. `idx_order_dedupe` là UNIQUE (conversation_id, md5(items)) cho MỌI đơn
--    chưa huỷ, không giới hạn thời gian. Khách mua lại đúng món cũ (đơn cũ đã
--    giao) bị chặn vĩnh viễn, và công cụ lên đơn còn bảo agent nói "đơn đã
--    ghi nhận" — trong khi KHÔNG có đơn nào. Chống bấm "ok" hai lần nay nằm
--    trong mã (`tools._tao_don_hang`): advisory lock + chỉ coi là trùng khi
--    có đơn cùng hàng tạo trong vài phút gần nhất.
--    Dòng tạo chỉ mục cũng đã xoá khỏi schema.sql — để đó là mỗi lần khởi
--    động nó được dựng lại trước khi migration này kịp xoá.
DROP INDEX IF EXISTS idx_order_dedupe;

-- Tra "đơn gần nhất của hội thoại này" cho phép chống trùng mới.
CREATE INDEX IF NOT EXISTS idx_order_hoi_thoai_tao
    ON orders (conversation_id, created_at DESC)
    WHERE conversation_id IS NOT NULL;

-- 2. Khách chuyển khoản VietQR mà không có chỗ ghi là đã thu: vận đơn luôn
--    thu hộ COD bằng tổng tiền, khách bị thu lần hai lúc nhận hàng.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS so_tien_da_thu BIGINT NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS da_thu_luc     TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS da_thu_boi     UUID
    REFERENCES nguoi_dung(id) ON DELETE SET NULL;
ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_so_tien_da_thu_check;
ALTER TABLE orders ADD CONSTRAINT orders_so_tien_da_thu_check
    CHECK (so_tien_da_thu >= 0);

-- 3. Việc sinh từ chính ĐƠN HÀNG (ERP nhận đơn trong lúc người huỷ, ERP
--    giữ bản nháp chưa submit, hãng báo đã giao một đơn đã huỷ). Nguồn
--    riêng để không đếm lẫn với việc agent đẩy sang người.
ALTER TABLE cong_viec DROP CONSTRAINT IF EXISTS cong_viec_nguon_check;
ALTER TABLE cong_viec ADD CONSTRAINT cong_viec_nguon_check
    CHECK (nguon IN ('nguoi', 'agent', 'tu_dong', 'van_chuyen', 'don_hang'));
