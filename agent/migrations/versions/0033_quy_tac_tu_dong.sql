-- Quy tắc tự động hoá: SỰ KIỆN → ĐIỀU KIỆN → HÀNH ĐỘNG, dạng DỮ LIỆU.
--
-- VÌ SAO LÀ DỮ LIỆU, KHÔNG PHẢI MÃ / KHÔNG PHẢI n8n
-- -------------------------------------------------
-- Cửa hàng cần "khách nhắn ngoài giờ thì gắn nhãn và chào", "hỏi đổi trả
-- thì chuyển người" mà không phải gọi lập trình viên. n8n làm được, nhưng
-- giấy phép Sustainable Use của n8n KHÔNG cho khách hàng tự dựng luồng trên
-- sản phẩm bán lại (docs/superpowers/plans/2026-10-14-lo-trinh-saas-va-khoa-luan.md).
-- Và cùng lý do với plugin: mã tuỳ ý chạy cùng phía với sáu lớp lưới. Quy
-- tắc ở đây chỉ chọn trong một danh sách điều kiện/hành động ĐÓNG, kiểm ở
-- máy chủ (agent/omnichannel/tu_dong.py).

CREATE TABLE IF NOT EXISTS quy_tac_tu_dong (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ten         TEXT        NOT NULL CHECK (char_length(btrim(ten)) BETWEEN 1 AND 80),
    su_kien     TEXT        NOT NULL CHECK (su_kien IN ('tin_khach')),
    dieu_kien   JSONB       NOT NULL DEFAULT '{}'::jsonb,
    hanh_dong   JSONB       NOT NULL,
    bat         BOOLEAN     NOT NULL DEFAULT true,
    -- Nhỏ chạy trước. Hai quy tắc cùng gửi tin thì thứ tự là thứ tự khách nhận.
    thu_tu      INT         NOT NULL DEFAULT 100,
    tao_boi     UUID        REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    tao_luc     TIMESTAMPTZ NOT NULL DEFAULT now(),
    sua_luc     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Mỗi lần một quy tắc KHỚP: đã làm gì, hay hỏng vì sao. Hai việc:
--   · người vận hành thấy quy tắc chạy thật (không có bảng này thì "đã bật"
--     mà không bao giờ khớp trông y hệt "đang chạy tốt");
--   · chặn gửi lặp: hành động gửi tin / tạo việc chỉ làm MỘT lần mỗi hội
--     thoại cho mỗi quy tắc, kể cả khi khách nhắn mười tin liền.
CREATE TABLE IF NOT EXISTS quy_tac_lan_chay (
    id              BIGSERIAL   PRIMARY KEY,
    quy_tac_id      UUID        NOT NULL REFERENCES quy_tac_tu_dong(id) ON DELETE CASCADE,
    conversation_id UUID        REFERENCES conversations(id) ON DELETE CASCADE,
    ket_qua         TEXT        NOT NULL CHECK (ket_qua IN ('da_lam', 'bo_qua', 'hong')),
    chi_tiet        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    luc             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_quy_tac_lan_chay_quy_tac_hoi_thoai
    ON quy_tac_lan_chay (quy_tac_id, conversation_id);
CREATE INDEX IF NOT EXISTS idx_quy_tac_lan_chay_luc
    ON quy_tac_lan_chay (luc DESC);
