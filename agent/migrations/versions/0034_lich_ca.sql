-- Lịch ca trực: ca lặp hằng tuần theo người, và lịch nghỉ.
--
-- VẤN ĐỀ
-- ------
-- Bộ định tuyến chỉ biết `team_members.is_available` — một công tắc bật
-- tay. Hết ca mà quên tắt là hội thoại mới vẫn được giao cho người đã về
-- nhà: hội thoại "đã có người nhận", không ai khác nhặt, khách chờ tới sáng.
-- Không lỗi, không nhật ký — đúng kiểu hỏng im lặng.
--
-- QUY ƯỚC
-- -------
-- · Người CHƯA có ca nào thì coi như LUÔN trong ca. Cửa hàng chưa xếp lịch
--   giữ nguyên hành vi cũ; thêm bảng này không được làm ai mất việc được
--   giao chỉ vì nâng cấp.
-- · Có lịch nghỉ phủ lên thời điểm đó thì NGOÀI ca, bất kể ca trực.
-- · Giờ Việt Nam UTC+7 cố định (agent/core/gio_lam_viec.py giải thích vì
--   sao cộng tay thay vì dùng tên múi giờ).

CREATE TABLE IF NOT EXISTS ca_truc (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nguoi_dung_id  UUID        NOT NULL REFERENCES nguoi_dung(id) ON DELETE CASCADE,
    -- ISO: 1 = thứ Hai … 7 = Chủ nhật. Ca qua đêm thuộc về ngày BẮT ĐẦU.
    thu            SMALLINT    NOT NULL CHECK (thu BETWEEN 1 AND 7),
    -- Phút trong ngày. ket_thuc < bat_dau nghĩa là ca qua đêm (22:00 → 06:00);
    -- 1440 = hết ngày, để viết được ca 14:00 → 24:00.
    bat_dau        SMALLINT    NOT NULL CHECK (bat_dau BETWEEN 0 AND 1439),
    ket_thuc       SMALLINT    NOT NULL CHECK (ket_thuc BETWEEN 1 AND 1440),
    tao_luc        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (bat_dau <> ket_thuc)
);
CREATE INDEX IF NOT EXISTS idx_ca_truc_nguoi ON ca_truc (nguoi_dung_id, thu);

CREATE TABLE IF NOT EXISTS ca_nghi (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nguoi_dung_id  UUID        NOT NULL REFERENCES nguoi_dung(id) ON DELETE CASCADE,
    tu_luc         TIMESTAMPTZ NOT NULL,
    den_luc        TIMESTAMPTZ NOT NULL,
    ly_do          TEXT        NOT NULL DEFAULT '' CHECK (char_length(ly_do) <= 200),
    tao_boi        UUID        REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    tao_luc        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (den_luc > tu_luc)
);
CREATE INDEX IF NOT EXISTS idx_ca_nghi_nguoi ON ca_nghi (nguoi_dung_id, den_luc);

-- Một nguồn sự thật cho "người này có đang trong ca không", dùng được ngay
-- trong câu chọn ứng viên của bộ định tuyến. Viết hai lần (SQL và Python)
-- là sớm muộn lệch nhau: màn hình nói "đang trong ca", bộ định tuyến bỏ qua.
CREATE OR REPLACE FUNCTION dang_trong_ca(uid UUID, t TIMESTAMPTZ)
RETURNS BOOLEAN LANGUAGE sql STABLE AS $$
    WITH vn AS (
        SELECT (t AT TIME ZONE 'UTC') + interval '7 hours' AS g
    ), x AS (
        SELECT extract(isodow FROM g)::int AS thu,
               ((extract(isodow FROM g)::int + 5) % 7) + 1 AS hom_qua,
               (extract(hour FROM g) * 60 + extract(minute FROM g))::int AS phut
        FROM vn
    )
    SELECT CASE
        WHEN EXISTS (SELECT 1 FROM ca_nghi n
                     WHERE n.nguoi_dung_id = uid AND t >= n.tu_luc AND t < n.den_luc)
            THEN false
        WHEN NOT EXISTS (SELECT 1 FROM ca_truc c WHERE c.nguoi_dung_id = uid)
            THEN true
        ELSE EXISTS (
            SELECT 1 FROM ca_truc c, x
            WHERE c.nguoi_dung_id = uid AND (
                -- ca trong ngày
                (c.bat_dau < c.ket_thuc AND c.thu = x.thu
                    AND x.phut >= c.bat_dau AND x.phut < c.ket_thuc)
                -- ca qua đêm: phần tối hôm nay, hoặc phần sáng của ca hôm qua
                OR (c.bat_dau > c.ket_thuc AND (
                       (c.thu = x.thu AND x.phut >= c.bat_dau)
                    OR (c.thu = x.hom_qua AND x.phut < c.ket_thuc)))
            ))
    END
$$;
