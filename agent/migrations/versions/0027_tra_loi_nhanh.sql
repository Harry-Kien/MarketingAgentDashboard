-- Mẫu trả lời nhanh: nhân viên gõ "/" + mã tắt để chèn câu soạn sẵn.
--
-- VÌ SAO CÓ
-- ---------
-- Mọi phần mềm CSKH đa kênh ở VN (Pancake, Haravan, Sapo) đều có; người trực
-- trả lời cùng một câu về phí ship, giờ mở cửa, cách đổi trả hàng chục lần
-- mỗi ngày. Không có mẫu thì mỗi người gõ một kiểu — và chính chỗ gõ vội ấy
-- là chỗ lọt cụm cấm quảng cáo.
--
-- VÌ SAO MẪU BỊ SOI TỪ CẤM NGAY LÚC LƯU
-- ------------------------------------
-- Bản nháp AI do quản lý sửa thì CẢNH BÁO rồi cho bấm qua (người bấm chịu
-- trách nhiệm cho một câu cụ thể). Mẫu thì khác: một mẫu dính cụm cấm là
-- vi phạm nhân lên theo số lần dùng, bởi những người không tự gõ nó. Nên ở
-- đây CHẶN — xem agent/api/tra_loi_nhanh.py.

CREATE TABLE IF NOT EXISTS tra_loi_nhanh (
    id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Chữ thường, số, gạch: gõ được nhanh và không lẫn dấu tiếng Việt.
    ma_tat    TEXT        NOT NULL UNIQUE
              CHECK (ma_tat ~ '^[a-z0-9_-]{1,32}$'),
    noi_dung  TEXT        NOT NULL
              CHECK (char_length(btrim(noi_dung)) BETWEEN 1 AND 2000),
    tao_boi   UUID        REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    tao_luc   TIMESTAMPTZ NOT NULL DEFAULT now(),
    sua_luc   TIMESTAMPTZ NOT NULL DEFAULT now()
);
