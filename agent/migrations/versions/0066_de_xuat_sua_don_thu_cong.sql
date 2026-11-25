-- Đợt 5B: additive states; preserve legacy actions and all historical results.
-- No historical loi is reclassified: it may describe an actual technical error.
ALTER TABLE ai_de_xuat DROP CONSTRAINT ai_de_xuat_trang_thai_check;
ALTER TABLE ai_de_xuat ADD CONSTRAINT ai_de_xuat_trang_thai_check CHECK (
    trang_thai IN ('cho_duyet', 'da_duyet', 'dang_thuc_thi', 'da_thuc_hien',
                  'cho_xu_ly_thu_cong', 'loi', 'tu_choi', 'het_han')
);

-- Requests waiting for manual work are still open. Neither a retry nor a
-- concurrent model turn should recreate the same unfulfilled request.
DROP INDEX idx_ai_de_xuat_mot_dang_mo;
CREATE UNIQUE INDEX idx_ai_de_xuat_mot_dang_mo ON ai_de_xuat(khoa_trung)
    WHERE trang_thai IN ('cho_duyet', 'da_duyet', 'dang_thuc_thi', 'cho_xu_ly_thu_cong');
