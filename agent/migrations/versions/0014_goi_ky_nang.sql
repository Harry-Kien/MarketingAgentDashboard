-- agent/migrations/versions/0014_goi_ky_nang.sql
-- Gói kỹ năng: hướng dẫn + công cụ + tài liệu + từ khoá, có phiên bản.
--
-- VÌ SAO LƯU CẢ GÓI DƯỚI DẠNG JSONB thay vì tách cột: gói được KIỂM bằng
-- `goi.doc_goi()` mỗi lần đọc lên (cùng lý do với `ban_mo_ta` ở 0010) —
-- tách cột là mở một đường ghi thứ hai không qua bộ kiểm.
--
-- VÌ SAO CÓ BẢNG LỊCH SỬ: cài đè một gói là thay cách agent tư vấn một chủ
-- đề; người vận hành phải quay lại được bản trước trong một cú bấm, không
-- phải đi tìm file cũ.

CREATE TABLE IF NOT EXISTS goi_ky_nang (
    ten        TEXT PRIMARY KEY,
    phien_ban  TEXT NOT NULL,
    bat        BOOLEAN NOT NULL DEFAULT TRUE,
    noi_dung   JSONB NOT NULL,
    tao_boi    TEXT NOT NULL,
    tao_luc    TIMESTAMPTZ NOT NULL DEFAULT now(),
    sua_luc    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS goi_ky_nang_lich_su (
    id         BIGSERIAL PRIMARY KEY,
    ten        TEXT NOT NULL,
    phien_ban  TEXT NOT NULL,
    noi_dung   JSONB NOT NULL,
    thay_luc   TIMESTAMPTZ NOT NULL DEFAULT now(),
    thay_boi   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_goi_lich_su_ten ON goi_ky_nang_lich_su (ten, thay_luc DESC);

-- Plugin thuộc gói nào. NULL = plugin rời tạo từ form. Bật/tắt gói là
-- bật/tắt mọi dòng có cùng `goi`.
ALTER TABLE ky_nang_cai_dat ADD COLUMN IF NOT EXISTS goi TEXT;
CREATE INDEX IF NOT EXISTS idx_ky_nang_goi ON ky_nang_cai_dat (goi) WHERE goi IS NOT NULL;
