-- Khảo sát hài lòng (CSAT) sau khi hội thoại được GIẢI QUYẾT.
--
-- Mỗi lần giải quyết một dòng: khách quay lại, được giải quyết lần nữa thì
-- là một lượt phục vụ mới và một điểm mới — gộp vào một dòng là điểm lần
-- sau đè mất lần trước.
--
-- `nguoi_xu_ly` là người phụ trách LÚC giải quyết, ghi cứng tại thời điểm
-- ấy: giao lại hội thoại cho người khác sau đó không được chuyển điểm cũ
-- sang họ.

CREATE TABLE IF NOT EXISTS csat (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    nguoi_xu_ly     UUID        REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    gui_luc         TIMESTAMPTZ NOT NULL DEFAULT now(),
    diem            SMALLINT    CHECK (diem BETWEEN 1 AND 5),
    tra_loi_luc     TIMESTAMPTZ,
    CHECK ((diem IS NULL) = (tra_loi_luc IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_csat_hoi_thoai ON csat (conversation_id, gui_luc DESC);
CREATE INDEX IF NOT EXISTS idx_csat_nguoi ON csat (nguoi_xu_ly, tra_loi_luc)
    WHERE diem IS NOT NULL;
