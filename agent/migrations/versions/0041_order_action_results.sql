-- DEV-09 / GAP-05: liên kết Pending Action với đơn và lưu kết quả đối soát.
--
-- Không nhồi dữ liệu này vào `mo_ta`: Dashboard và Resolve Guard cần truy
-- vấn được loại nghiệp vụ, kết quả cuối, người xác nhận và bằng chứng ERP.
-- Các cột đều nullable để migration tương thích với công việc lịch sử.

ALTER TABLE cong_viec
    ADD COLUMN IF NOT EXISTS order_id UUID
        REFERENCES orders(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS loai_xu_ly_don TEXT,
    ADD COLUMN IF NOT EXISTS ket_qua_xu_ly_don TEXT,
    ADD COLUMN IF NOT EXISTS ly_do_ket_qua TEXT,
    ADD COLUMN IF NOT EXISTS erp_tham_chieu TEXT,
    ADD COLUMN IF NOT EXISTS erp_trang_thai TEXT,
    -- ERPNext trả `modified` theo timezone của site và thường không kèm
    -- offset. Giữ nguyên chuỗi nguồn thay vì đoán timezone rồi làm sai bằng chứng.
    ADD COLUMN IF NOT EXISTS erp_sua_luc TEXT,
    ADD COLUMN IF NOT EXISTS xu_ly_boi UUID
        REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS xu_ly_luc TIMESTAMPTZ;

ALTER TABLE cong_viec
    ADD CONSTRAINT cong_viec_loai_xu_ly_don_check
        CHECK (loai_xu_ly_don IS NULL OR loai_xu_ly_don IN ('sua', 'huy')),
    ADD CONSTRAINT cong_viec_ket_qua_xu_ly_don_check
        CHECK (
            ket_qua_xu_ly_don IS NULL
            OR ket_qua_xu_ly_don IN ('thanh_cong', 'khong_the', 'cho_doi_soat')
        ),
    ADD CONSTRAINT cong_viec_xu_ly_don_can_order_check
        CHECK (loai_xu_ly_don IS NULL OR order_id IS NOT NULL),
    ADD CONSTRAINT cong_viec_ket_qua_cuoi_can_thoi_diem_check
        CHECK (
            ket_qua_xu_ly_don NOT IN ('thanh_cong', 'khong_the')
            OR (xu_ly_luc IS NOT NULL AND xong_luc IS NOT NULL)
        );

CREATE INDEX IF NOT EXISTS idx_cong_viec_order
    ON cong_viec (order_id, trang_thai)
    WHERE order_id IS NOT NULL;
