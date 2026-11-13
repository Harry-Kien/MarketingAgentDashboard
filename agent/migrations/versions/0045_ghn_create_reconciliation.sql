-- DEV-08: Theo dõi tạo vận đơn GHN và đối soát sau timeout/mất kết nối.
--
-- Không gộp chung trạng thái chưa rõ kết quả thành "thất bại": mỗi yêu cầu
-- tạo vận đơn đi qua vòng đời tường minh để chặn tạo trùng khi kết quả phía
-- GHN chưa được xác minh, giữ nguyên client_order_code ổn định qua các lần
-- đối soát, và chuyển hàng đợi xử lý thủ công khi tự đối soát chưa kết luận.

CREATE TABLE IF NOT EXISTS shipping_waybill_requests (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id            UUID NOT NULL UNIQUE REFERENCES orders(id) ON DELETE CASCADE,
    ma_don              TEXT NOT NULL,
    provider            TEXT NOT NULL DEFAULT 'ghn',
    client_order_code   TEXT NOT NULL,
    trang_thai          TEXT NOT NULL DEFAULT 'not_sent',
    ma_van_don          TEXT,
    phi_van_chuyen      BIGINT,
    so_lan_gui          INT NOT NULL DEFAULT 0,
    so_lan_doi_soat     INT NOT NULL DEFAULT 0,
    doi_soat_tiep_luc   TIMESTAMPTZ,
    khoa_luc            TIMESTAMPTZ,
    khoa_boi            TEXT,
    gui_luc             TIMESTAMPTZ,
    xac_nhan_luc        TIMESTAMPTZ,
    xac_nhan_boi        TEXT,
    ly_do_chan          TEXT,
    loi_cuoi            TEXT,
    du_lieu_phan_hoi    JSONB NOT NULL DEFAULT '{}'::jsonb,
    bang_chung_thu_cong JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT shipping_waybill_requests_trang_thai_check CHECK (
        trang_thai IN (
            'not_sent',
            'sending',
            'confirmed',
            'rejected',
            'unknown_timeout',
            'reconciling',
            'reconciled',
            'manual_required'
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_shipping_waybill_req_client_code
    ON shipping_waybill_requests (provider, client_order_code);

CREATE INDEX IF NOT EXISTS idx_shipping_waybill_req_reconcile
    ON shipping_waybill_requests (doi_soat_tiep_luc, updated_at)
    WHERE trang_thai IN ('unknown_timeout', 'reconciling', 'sending');

CREATE INDEX IF NOT EXISTS idx_shipping_waybill_req_status
    ON shipping_waybill_requests (trang_thai, updated_at);

INSERT INTO shipping_waybill_requests (
    order_id,
    ma_don,
    provider,
    client_order_code,
    trang_thai,
    ma_van_don,
    so_lan_gui,
    gui_luc,
    xac_nhan_luc,
    xac_nhan_boi
)
SELECT
    o.id,
    o.ma_don,
    COALESCE(NULLIF(TRIM(o.don_vi_van_chuyen), ''), 'ghn'),
    o.ma_don,
    'confirmed',
    NULLIF(TRIM(o.ma_van_don), ''),
    1,
    COALESCE(o.cap_nhat_van_chuyen_luc, o.updated_at, o.created_at),
    COALESCE(o.cap_nhat_van_chuyen_luc, o.updated_at, o.created_at),
    'legacy_backfill'
FROM orders o
WHERE NULLIF(TRIM(o.ma_van_don), '') IS NOT NULL
ON CONFLICT (order_id) DO NOTHING;
