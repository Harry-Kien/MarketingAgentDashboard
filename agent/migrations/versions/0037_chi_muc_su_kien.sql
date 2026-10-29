-- Tra sự kiện theo (loại, đối tượng): "khách này đã đòi gặp người chưa"
-- (agent/omnichannel/thong_bao_ai.py) chạy MỖI tin khách đi tới agent.
-- Không có chỉ mục là quét cả bảng events — bảng lớn nhất hệ thống — mỗi tin.
CREATE INDEX IF NOT EXISTS idx_event_kind_ref ON events (kind, ref_id, created_at DESC);
