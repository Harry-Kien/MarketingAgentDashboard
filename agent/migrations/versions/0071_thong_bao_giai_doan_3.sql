-- Giai đoạn 3: hoàn thiện trạng thái, đối tượng liên kết, chu kỳ và phòng trùng
-- cho bảng `thong_bao`. Không sửa dữ liệu lịch sử đã có.

ALTER TABLE thong_bao
    ADD COLUMN IF NOT EXISTS de_xuat_id UUID REFERENCES ai_de_xuat(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS account_id UUID REFERENCES channel_accounts(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS outbox_job_id UUID REFERENCES outbox_jobs(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS chu_ky_nghiep_vu INTEGER,
    ADD COLUMN IF NOT EXISTS nguon_chi_tiet TEXT,
    ADD COLUMN IF NOT EXISTS da_xu_ly_luc TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_thong_bao_de_xuat
    ON thong_bao (de_xuat_id) WHERE de_xuat_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_thong_bao_account
    ON thong_bao (account_id) WHERE account_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_thong_bao_contact
    ON thong_bao (contact_id) WHERE contact_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_thong_bao_outbox_job
    ON thong_bao (outbox_job_id) WHERE outbox_job_id IS NOT NULL;

ALTER TABLE thong_bao DROP CONSTRAINT IF EXISTS thong_bao_loai_check;
ALTER TABLE thong_bao ADD CONSTRAINT thong_bao_loai_check CHECK (loai IN (
    'duoc_giao_hoi_thoai',
    'ai_chuyen_giao',
    'can_duyet',
    'duoc_giao_viec',
    'sla_sap_tre',
    'sla_tre',
    'viec_chua_giao',
    'viec_huy',
    'viec_qua_han',
    'kenh_can_xac_thuc',
    'tin_nhan_that_bai',
    'duoc_giao_khach'
));
