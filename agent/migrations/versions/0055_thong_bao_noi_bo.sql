-- Thông báo NỘI BỘ: chuông trên đầu dashboard, mỗi dòng một người nhận.
--
-- VÌ SAO CẦN
-- Trước bản này "AI chuyển người", "được giao hội thoại", "bản nháp chờ
-- duyệt", "SLA sắp trễ" chỉ hiện ra nếu người trực tình cờ mở đúng màn.
-- Mọi lần AI chuyển giao lại đẻ một công việc "Khách cần người trả lời" —
-- trùng nghiệp vụ với chính hội thoại đang chờ, và màn Công việc đầy việc
-- không phải việc. Thông báo thay chỗ ấy: NHẮC và DẪN ĐƯỜNG, không phải
-- một hạng mục phải đóng.
--
-- KHÔNG CHÉP TÊN HAY LỜI KHÁCH VÀO ĐÂY
-- Tên khách đọc lúc hiển thị qua `conversation_id`. Liên kết là khoá ngoại
-- ON DELETE CASCADE: xoá dữ liệu khách theo PDPD (xoá hội thoại) là thông
-- báo về họ đi theo — không có bản sao thứ hai nằm lại trong bảng này.
CREATE TABLE IF NOT EXISTS thong_bao (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nguoi_nhan_id    UUID NOT NULL REFERENCES nguoi_dung(id) ON DELETE CASCADE,
    loai             TEXT NOT NULL CHECK (loai IN (
                         'duoc_giao_hoi_thoai',
                         'ai_chuyen_giao',
                         'can_duyet',
                         'duoc_giao_viec',
                         'sla_sap_tre',
                         'sla_tre'
                     )),
    tieu_de          TEXT NOT NULL CHECK (char_length(tieu_de) BETWEEN 1 AND 200),
    noi_dung         TEXT NOT NULL DEFAULT '' CHECK (char_length(noi_dung) <= 500),
    conversation_id  UUID REFERENCES conversations(id) ON DELETE CASCADE,
    cong_viec_id     UUID REFERENCES cong_viec(id) ON DELETE CASCADE,
    order_id         UUID REFERENCES orders(id) ON DELETE CASCADE,
    khoa_chong_trung TEXT CHECK (khoa_chong_trung IS NULL
                                 OR char_length(khoa_chong_trung) <= 300),
    tao_luc          TIMESTAMPTZ NOT NULL DEFAULT now(),
    da_doc_luc       TIMESTAMPTZ
);

-- Số chưa đọc của MỘT người — truy vấn chạy mỗi vòng làm mới dashboard.
CREATE INDEX IF NOT EXISTS idx_thong_bao_chua_doc
    ON thong_bao (nguoi_nhan_id, tao_luc DESC) WHERE da_doc_luc IS NULL;

CREATE INDEX IF NOT EXISTS idx_thong_bao_nguoi_nhan
    ON thong_bao (nguoi_nhan_id, tao_luc DESC);

-- Chống dội: mỗi người chỉ MỘT thông báo CHƯA ĐỌC cho cùng một chuyện
-- (cùng hội thoại cần duyệt, cùng lần chuyển giao). Chế độ Gợi ý soạn nháp
-- mỗi tin khách — không chặn ở CSDL thì chuông thành mười dòng giống nhau,
-- và hai tiến trình cùng kiểm "đã có chưa" rồi cùng chèn. Đã đọc thì lần
-- sau là chuyện mới, được một dòng mới.
CREATE UNIQUE INDEX IF NOT EXISTS idx_thong_bao_chong_trung
    ON thong_bao (nguoi_nhan_id, khoa_chong_trung)
    WHERE da_doc_luc IS NULL AND khoa_chong_trung IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_thong_bao_conversation
    ON thong_bao (conversation_id) WHERE conversation_id IS NOT NULL;

-- Khoá ngoại ON DELETE CASCADE không có chỉ mục là mỗi lần xoá một
-- việc / đơn phải quét cả bảng này.
CREATE INDEX IF NOT EXISTS idx_thong_bao_cong_viec
    ON thong_bao (cong_viec_id) WHERE cong_viec_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_thong_bao_order
    ON thong_bao (order_id) WHERE order_id IS NOT NULL;
