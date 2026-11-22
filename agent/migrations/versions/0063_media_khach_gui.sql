-- Media khách gửi: tải về máy chủ, giữ theo thời hạn, chống trùng bằng sha256.
--
-- VÌ SAO CẦN
-- Rà soát 20.11.2026: ảnh, video, tệp khách gửi KHÔNG BAO GIỜ được lưu lại.
-- `attachments.url` chỉ giữ đường CDN của hãng — Facebook ký URL có hạn vài
-- ngày, Zalo xoá tệp sau một thời gian. Hết hạn là ảnh vùng da khách gửi,
-- ảnh hàng vỡ, ảnh chuyển khoản biến thành ô vỡ trên dashboard, không lỗi,
-- không nhật ký. Chủ dự án quyết: tải về, giữ 180 ngày, chống trùng.
--
-- CHỐNG TRÙNG: BẢNG THEO NỘI DUNG + DÒNG THAM CHIẾU, KHÔNG ĐẾM THAM CHIẾU
-- Mỗi nội dung (sha256) là MỘT dòng `media_tep` và MỘT tệp trên đĩa; mỗi
-- đính kèm trỏ vào nó qua `attachments.media_sha256`. Số người dùng tệp
-- được TÍNH từ chính các dòng `attachments`, không giữ trong một cột đếm.
-- Cột đếm phải được trừ ở MỌI đường xoá — mà hội thoại bị xoá theo
-- `ON DELETE CASCADE` (dọn theo thời hạn, xoá theo PDPD, gộp khách...), nơi
-- không có mã Python nào chạy để trừ. Lệch một lần là hoặc giữ tệp mãi mãi,
-- hoặc xoá tệp người khác vẫn đang dùng. Đếm từ sự thật thì không lệch được.
CREATE TABLE IF NOT EXISTS media_tep (
    sha256       TEXT PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    -- Khoá TƯƠNG ĐỐI `data/media/...` (xem agent/duong_dan_du_lieu.py):
    -- chuyển cửa hàng sang máy khác thì cùng dòng vẫn mở được.
    storage_key  TEXT NOT NULL CHECK (storage_key LIKE 'data/media/%'),
    mime_type    TEXT NOT NULL,
    size_bytes   BIGINT NOT NULL CHECK (size_bytes >= 0),
    tao_luc      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Lần dọn thấy tệp KHÔNG còn trên đĩa. Chỉ đánh dấu, không xoá dòng:
    -- máy mới dựng CSDL trước rồi mới chép `data/media` sang thì một lượt
    -- dọn chạy giữa hai bước không được biến cả kho thành "mồ côi".
    mat_tep_luc  TIMESTAMPTZ
);

-- Trạng thái tải của TỪNG đính kèm khách gửi. NULL = không phải media
-- khách gửi (tệp nhân viên gửi, dòng cũ trước bản này).
--   cho      chờ tải (lần đầu hoặc chờ thử lại theo `media_thu_lai_luc`)
--   dang_tai một worker đang tải; kẹt quá lâu thì được nhặt lại
--   da_tai   đã có bản trên máy chủ (`media_sha256`)
--   loi      hỏng sau đủ số lần thử
--   qua_lon  vượt trần dung lượng — cố ý không tải
--   het_han  hãng trả 403/404/410: link đã chết, thử nữa vô ích
--   bo_qua   không có nguồn tải, hoặc kiểu tệp ngoài danh sách cho phép
--   da_don   đã xoá theo thời hạn lưu trữ
--   mat_tep  CSDL nói có, đĩa không có
ALTER TABLE attachments
    ADD COLUMN IF NOT EXISTS media_trang_thai TEXT
        CHECK (media_trang_thai IS NULL OR media_trang_thai IN (
            'cho', 'dang_tai', 'da_tai', 'loi', 'qua_lon', 'het_han',
            'bo_qua', 'da_don', 'mat_tep')),
    ADD COLUMN IF NOT EXISTS media_sha256 TEXT
        REFERENCES media_tep(sha256) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS media_so_lan_thu INT NOT NULL DEFAULT 0
        CHECK (media_so_lan_thu >= 0),
    ADD COLUMN IF NOT EXISTS media_thu_lai_luc TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS media_loi TEXT
        CHECK (media_loi IS NULL OR char_length(media_loi) <= 300),
    ADD COLUMN IF NOT EXISTS media_tai_luc TIMESTAMPTZ;

-- Hàng chờ của worker tải: chỉ vài dòng đang chờ trong cả bảng.
CREATE INDEX IF NOT EXISTS idx_attachments_media_cho
    ON attachments (media_thu_lai_luc)
    WHERE media_trang_thai IN ('cho', 'dang_tai');

-- "Còn ai dùng tệp này không" — câu hỏi của mỗi lượt dọn.
CREATE INDEX IF NOT EXISTS idx_attachments_media_sha256
    ON attachments (media_sha256, created_at)
    WHERE media_sha256 IS NOT NULL;

-- Mỗi lượt dọn một dòng: người vận hành phải thấy lần dọn cuối là khi nào,
-- xoá bao nhiêu, giải phóng bao nhiêu — "dọn chạy chưa" không được là câu
-- hỏi phải đi đọc nhật ký mới trả lời được.
CREATE TABLE IF NOT EXISTS media_lan_don (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bat_dau           TIMESTAMPTZ NOT NULL DEFAULT now(),
    xong_luc          TIMESTAMPTZ,
    nguon             TEXT NOT NULL CHECK (nguon IN ('tu_dong', 'thu_cong', 'pdpd')),
    xem_truoc         BOOLEAN NOT NULL DEFAULT false,
    thoi_han_ngay     INT NOT NULL CHECK (thoi_han_ngay > 0),
    so_tep_xoa        INT NOT NULL DEFAULT 0,
    byte_giai_phong   BIGINT NOT NULL DEFAULT 0,
    so_mo_coi_xoa     INT NOT NULL DEFAULT 0,
    so_dong_mat_tep   INT NOT NULL DEFAULT 0,
    chi_tiet          JSONB NOT NULL DEFAULT '{}',
    boi               TEXT
);
CREATE INDEX IF NOT EXISTS idx_media_lan_don_moi
    ON media_lan_don (bat_dau DESC);
