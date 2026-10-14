-- Nhãn và ghi chú nội bộ gắn theo HỘI THOẠI.
--
-- VÌ SAO KHÁC NHÃN/GHI CHÚ CỦA KHÁCH (0004)
-- -----------------------------------------
-- `contact_tags`/`contact_notes` mô tả CON NGƯỜI và sống lâu ("khách sỉ",
-- "da nhạy cảm"). Nhãn hội thoại mô tả MỘT VỤ VIỆC ("chờ hàng về", "khiếu
-- nại ship", "đã báo giá") và hết nghĩa khi vụ việc đóng. Gộp hai thứ vào
-- một là hồ sơ khách đầy nhãn của những chuyện đã xong từ tháng trước.
--
-- Ghi chú hội thoại là để người trực BÀN GIAO cho nhau giữa ca. Nó KHÔNG
-- BAO GIỜ đi ra kênh — không có đường nào từ bảng này tới outbox, và
-- tests/test_api_nhan_ghi_chu_hoi_thoai.py canh điều đó.

CREATE TABLE IF NOT EXISTS hoi_thoai_nhan (
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    nhan            TEXT        NOT NULL
                    CHECK (char_length(btrim(nhan)) BETWEEN 1 AND 40),
    tao_boi         UUID        REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    tao_luc         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (conversation_id, nhan)
);
-- Lọc danh sách theo nhãn: "mọi hội thoại đang chờ hàng về".
CREATE INDEX IF NOT EXISTS idx_hoi_thoai_nhan_nhan ON hoi_thoai_nhan (nhan);

CREATE TABLE IF NOT EXISTS hoi_thoai_ghi_chu (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    noi_dung        TEXT        NOT NULL
                    CHECK (char_length(btrim(noi_dung)) BETWEEN 1 AND 5000),
    tao_boi         UUID        REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    tao_luc         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_hoi_thoai_ghi_chu_hoi_thoai
    ON hoi_thoai_ghi_chu (conversation_id, tao_luc DESC);
