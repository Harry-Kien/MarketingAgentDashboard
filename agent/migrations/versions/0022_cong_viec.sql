-- Công việc: giao việc cho nhân viên và theo dõi tới khi xong.
--
-- VÌ SAO KHÔNG DÙNG LẠI `conversation_assignments`
-- -------------------------------------------------
-- Bảng ấy trả lời "ai đang cầm hội thoại này" — một trạng thái, không có
-- hạn, không có tiêu đề, và chết cùng hội thoại. Việc thì khác: "gọi lại
-- chị Hoa trước 5 giờ chiều" không gắn với một hội thoại nào đang mở, và
-- nó vẫn còn đó sau khi hội thoại đóng.
--
-- Việc quan trọng nhất bảng này làm được mà bảng kia không: ĐÓNG VÒNG khi
-- agent chuyển người. Trước bản này, agent chuyển người xong thì để lại
-- một dòng nhật ký và một hội thoại đổi màu. Không ai được GIAO gì cả —
-- nên nếu người trực đang bận, việc ấy không nằm ở đâu, và nó chỉ được
-- nhớ tới nếu tình cờ có người mở đúng hội thoại.

CREATE TABLE IF NOT EXISTS cong_viec (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tieu_de     TEXT NOT NULL CHECK (length(tieu_de) BETWEEN 3 AND 200),
    mo_ta       TEXT NOT NULL DEFAULT '',

    -- NULL = chưa giao cho ai. Cùng lý lẽ với khách vô chủ: việc chưa giao
    -- là việc của chung, thấy được, chứ không phải việc vô hình.
    nguoi_nhan  UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    -- NULL cũng hợp lệ: việc do AGENT tạo thì không có người giao.
    nguoi_giao  UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,

    trang_thai  TEXT NOT NULL DEFAULT 'moi',
    uu_tien     TEXT NOT NULL DEFAULT 'thuong',
    han         TIMESTAMPTZ,

    -- `nguoi` hay `agent`. Phân biệt được thì mới trả lời được câu "agent
    -- đẩy sang người bao nhiêu việc tuần này", và đó là số đo quan trọng
    -- nhất về việc agent đang gánh được bao nhiêu.
    nguon       TEXT NOT NULL DEFAULT 'nguoi',

    -- Liên kết. ON DELETE SET NULL chứ không CASCADE: xoá một hội thoại
    -- không được làm biến mất việc "gọi lại khách này" — việc ấy vẫn phải
    -- làm, chỉ là mất đường dẫn tới hội thoại.
    contact_id      UUID REFERENCES contacts(id) ON DELETE SET NULL,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,

    tao_luc     TIMESTAMPTZ NOT NULL DEFAULT now(),
    sua_luc     TIMESTAMPTZ NOT NULL DEFAULT now(),
    xong_luc    TIMESTAMPTZ,

    CHECK (trang_thai IN ('moi', 'dang_lam', 'xong', 'huy')),
    CHECK (uu_tien IN ('thap', 'thuong', 'cao', 'gap')),
    CHECK (nguon IN ('nguoi', 'agent')),
    -- `xong_luc` phải khớp trạng thái. Không ràng buộc thì một việc
    -- `trang_thai='xong'` mà `xong_luc` rỗng sẽ lọt khỏi mọi báo cáo thời
    -- gian xử lý, và báo cáo ấy im lặng thiếu đi vài dòng.
    CHECK ((trang_thai = 'xong') = (xong_luc IS NOT NULL))
);

-- Màn Công việc lọc theo người nhận và trạng thái ở mọi lần mở.
CREATE INDEX IF NOT EXISTS idx_cong_viec_nguoi_nhan
    ON cong_viec (nguoi_nhan, trang_thai, han);

-- Chỉ số "việc quá hạn" chạy ở mọi lần tải trang Ca trực. Chỉ mục một
-- phần: chỉ những việc CHƯA xong mới có thể quá hạn.
CREATE INDEX IF NOT EXISTS idx_cong_viec_qua_han
    ON cong_viec (han)
    WHERE han IS NOT NULL AND trang_thai IN ('moi', 'dang_lam');

CREATE INDEX IF NOT EXISTS idx_cong_viec_contact
    ON cong_viec (contact_id) WHERE contact_id IS NOT NULL;

-- Một hội thoại chỉ sinh ĐÚNG MỘT việc tự động đang mở.
--
-- Không có ràng buộc này thì mỗi tin khách nhắn thêm vào một hội thoại đã
-- chuyển người lại đẻ một việc mới, và tới cuối ngày màn Công việc có bốn
-- mươi dòng cho cùng một chuyện. Danh sách ấy thì không ai đọc, và việc
-- thật nằm lẫn trong đó.
CREATE UNIQUE INDEX IF NOT EXISTS idx_cong_viec_agent_mot_viec
    ON cong_viec (conversation_id)
    WHERE nguon = 'agent' AND trang_thai IN ('moi', 'dang_lam');
