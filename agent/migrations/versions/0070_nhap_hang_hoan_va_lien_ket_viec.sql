-- BUG-17-04 (hoàn thiện): chống nhập hàng hoàn trùng khi retry / double-submit.
--
-- Cột `khoa_chong_trung` (nullable) kèm chỉ mục duy nhất từng phần trên
-- `kho_bien_dong`:
--   - Dữ liệu cũ giữ NULL, không ảnh hưởng biến động cũ.
--   - Lần retry nhập hoàn một phần cùng `khoa_chong_trung` trả lại đúng kết quả
--     lần đầu mà không cộng tồn kho lần hai.

ALTER TABLE kho_bien_dong ADD COLUMN IF NOT EXISTS khoa_chong_trung TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_kho_bd_khoa_chong_trung
    ON kho_bien_dong (khoa_chong_trung)
    WHERE khoa_chong_trung IS NOT NULL;
