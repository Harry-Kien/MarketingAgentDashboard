-- Nhãn động: MỘT danh mục, HAI loại ĐỘC LẬP — nhãn khách và nhãn hội thoại.
--
-- VÌ SAO BỎ NHÃN CHỮ TỰ DO
-- ------------------------
-- Trước bản này nhãn là chữ gõ tay ở hai bảng rời: `contact_tags` (0004) và
-- `hoi_thoai_nhan` (0028). Ba kiểu hỏng, cả ba đều im lặng:
--   · "VIP", "vip ", "Vip" là ba nhãn — bộ lọc tách đôi danh sách khách
--     mà không ai thấy.
--   · Quy tắc tự động đặt điều kiện "có nhãn vip" bằng CHỮ. Gõ sai một
--     dấu là quy tắc "đang bật" không bao giờ khớp.
--   · Không đổi tên, không đổi màu, không ngừng dùng được: muốn bỏ một
--     nhãn là phải gỡ khỏi từng khách, và lịch sử thì mất theo.
--
-- HAI LOẠI, KHÔNG GỘP
-- -------------------
-- Nhãn KHÁCH mô tả con người, sống lâu ("khách sỉ", "da nhạy cảm"), gắn ở
-- Customer 360. Nhãn HỘI THOẠI mô tả một vụ việc ("chờ hàng về", "khiếu nại
-- ship"), gắn trên hội thoại, và KHÔNG thay trạng thái xử lý. Cột `loai` đi
-- vào khoá ngoại của bảng gắn (FOREIGN KEY (nhan_id, loai)): gắn nhầm nhãn
-- khách lên hội thoại bị CSDL từ chối, không chỉ bị API từ chối — mã gọi
-- thẳng CSDL (quy tắc tự động, script) cũng không lách được.
--
-- NGỪNG DÙNG, KHÔNG XOÁ
-- ---------------------
-- Nhãn đã từng gắn thì không xoá: `ON DELETE RESTRICT` ở bảng gắn. Ngừng
-- dùng (`dang_dung = false`) ẩn nó khỏi ô chọn nhưng chỗ đã gắn vẫn hiện
-- (xám), nhật ký và quy tắc cũ vẫn đọc ra tên. Chỉ nhãn CHƯA từng gắn mới
-- xoá được (gõ nhầm lúc tạo).
--
-- BẢNG CŨ: GIỮ NGUYÊN, THÔI GHI
-- -----------------------------
-- `contact_tags` và `hoi_thoai_nhan` KHÔNG bị xoá (dữ liệu thật, và hai
-- migration ấy đã chốt checksum). Từ bản này không mã nào GHI vào chúng —
-- tests/test_nhan_dong.py canh điều đó. Chúng là ảnh chụp lúc chuyển đổi,
-- không phải bản sao song song: một bản sao phải đồng bộ khi đổi tên nhãn
-- là một bản sao sẽ lệch mà không ai biết. Ngoại lệ duy nhất là xoá dữ liệu
-- cá nhân (PDPD): `contact_tags` vẫn bị XOÁ theo khách, vì chữ trong đó là
-- chữ viết về một người.
--
-- Tên bảng gắn là `hoi_thoai_gan_nhan`/`khach_gan_nhan`, không phải
-- `hoi_thoai_nhan`: tên ấy đã thuộc bảng chữ tự do của 0028.

CREATE TABLE IF NOT EXISTS nhan (
    id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    loai      TEXT        NOT NULL CHECK (loai IN ('khach', 'hoi_thoai')),
    -- Tên đã chuẩn hoá (bỏ khoảng trắng thừa) — API chuẩn hoá trước khi
    -- ghi, CHECK chặn đường ghi nào quên bước ấy.
    ten       TEXT        NOT NULL
              CHECK (char_length(ten) BETWEEN 1 AND 80
                     AND ten = btrim(ten) AND ten !~ '\s\s'),
    mau       TEXT        NOT NULL DEFAULT '#4b5563' CHECK (mau ~ '^#[0-9a-f]{6}$'),
    mo_ta     TEXT        NOT NULL DEFAULT '' CHECK (char_length(mo_ta) <= 300),
    dang_dung BOOLEAN     NOT NULL DEFAULT true,
    thu_tu    INT         NOT NULL DEFAULT 100 CHECK (thu_tu BETWEEN 0 AND 10000),
    tao_boi   UUID        REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    tao_luc   TIMESTAMPTZ NOT NULL DEFAULT now(),
    sua_luc   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Đích của khoá ngoại hai cột ở bảng gắn.
    CONSTRAINT uq_nhan_id_loai UNIQUE (id, loai)
);
-- Trùng tên tính CẢ nhãn đã ngừng: tạo lại "vip" khi "VIP" đang ngừng là
-- hai nhãn cùng tên trong lịch sử, và bộ lọc không biết chọn cái nào.
CREATE UNIQUE INDEX IF NOT EXISTS uq_nhan_loai_ten ON nhan (loai, lower(ten));

CREATE TABLE IF NOT EXISTS hoi_thoai_gan_nhan (
    conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    nhan_id         UUID        NOT NULL,
    loai            TEXT        NOT NULL DEFAULT 'hoi_thoai' CHECK (loai = 'hoi_thoai'),
    gan_boi         UUID        REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    gan_luc         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_hoi_thoai_gan_nhan PRIMARY KEY (conversation_id, nhan_id),
    CONSTRAINT fk_hoi_thoai_gan_nhan_nhan FOREIGN KEY (nhan_id, loai)
        REFERENCES nhan (id, loai) ON DELETE RESTRICT
);
-- Lọc hộp thư theo nhãn và đếm "nhãn này đang gắn ở bao nhiêu nơi".
CREATE INDEX IF NOT EXISTS idx_hoi_thoai_gan_nhan_nhan ON hoi_thoai_gan_nhan (nhan_id);

CREATE TABLE IF NOT EXISTS khach_gan_nhan (
    contact_id UUID        NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    nhan_id    UUID        NOT NULL,
    loai       TEXT        NOT NULL DEFAULT 'khach' CHECK (loai = 'khach'),
    gan_boi    UUID        REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    gan_luc    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_khach_gan_nhan PRIMARY KEY (contact_id, nhan_id),
    CONSTRAINT fk_khach_gan_nhan_nhan FOREIGN KEY (nhan_id, loai)
        REFERENCES nhan (id, loai) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_khach_gan_nhan_nhan ON khach_gan_nhan (nhan_id);

-- ---------------------------------------------------------------------
-- CHUYỂN DỮ LIỆU CŨ
-- ---------------------------------------------------------------------
-- Gộp không phân biệt hoa thường và khoảng trắng: "VIP" và " vip" là MỘT
-- nhãn. Tên hiển thị lấy từ biến thể được gắn SỚM NHẤT. Màu chia vòng theo
-- bảng tám màu của agent/core/nhan.py (BANG_MAU — test canh hai nơi khớp);
-- mọi màu đủ tương phản với chữ trắng (WCAG AA).
--
-- Chữ chỉ có khoảng trắng hoặc dài quá 80 ký tự thì KHÔNG chuyển (CHECK
-- của `nhan` không nhận) — dòng cũ vẫn nằm nguyên ở bảng cũ, và số dòng bỏ
-- qua được ghi vào sự kiện `nhan.chuyen_doi` bên dưới, không mất im lặng.

WITH nguon AS (
    SELECT 'khach' AS loai,
           regexp_replace(btrim(tag), '\s+', ' ', 'g') AS ten, created_at AS luc
    FROM contact_tags
    UNION ALL
    SELECT 'hoi_thoai', regexp_replace(btrim(nhan), '\s+', ' ', 'g'), tao_luc
    FROM hoi_thoai_nhan
    UNION ALL
    -- Nhãn chữ trong quy tắc tự động là nhãn HỘI THOẠI (quy tắc cũ chỉ đọc
    -- và ghi `hoi_thoai_nhan`). Tạo sẵn để bước đổi quy tắc bên dưới luôn
    -- tìm được id — không có quy tắc nào bị bỏ lại với chữ không ai hiểu.
    SELECT 'hoi_thoai', regexp_replace(btrim(gt), '\s+', ' ', 'g'), now()
    FROM (
        SELECT CASE WHEN jsonb_typeof(dieu_kien) = 'string'
                    THEN (dieu_kien #>> '{}')::jsonb ELSE dieu_kien END AS dk,
               CASE WHEN jsonb_typeof(hanh_dong) = 'string'
                    THEN (hanh_dong #>> '{}')::jsonb ELSE hanh_dong END AS hd
        FROM quy_tac_tu_dong
    ) qt,
    LATERAL (
        SELECT qt.dk ->> 'nhan_co' AS gt
        WHERE jsonb_typeof(qt.dk -> 'nhan_co') = 'string'
        UNION ALL
        SELECT qt.dk ->> 'nhan_khong'
        WHERE jsonb_typeof(qt.dk -> 'nhan_khong') = 'string'
        UNION ALL
        SELECT h ->> 'nhan'
        FROM jsonb_array_elements(CASE WHEN jsonb_typeof(qt.hd) = 'array'
                                       THEN qt.hd ELSE '[]'::jsonb END) h
        WHERE h ->> 'loai' = 'gan_nhan' AND jsonb_typeof(h -> 'nhan') = 'string'
    ) chu
),
dai_dien AS (
    SELECT DISTINCT ON (loai, lower(ten)) loai, ten
    FROM nguon
    WHERE char_length(ten) BETWEEN 1 AND 80
    ORDER BY loai, lower(ten), luc, ten
)
INSERT INTO nhan (loai, ten, mau, mo_ta)
SELECT loai, ten,
       (ARRAY['#1d4ed8', '#15803d', '#b45309', '#b91c1c',
              '#6d28d9', '#0e7490', '#be185d', '#4b5563'])
           [1 + ((row_number() OVER (ORDER BY loai, lower(ten)) - 1) % 8)::int],
       'Chuyển từ nhãn chữ tự do (migration 0056).'
FROM dai_dien
ON CONFLICT DO NOTHING;

INSERT INTO khach_gan_nhan (contact_id, nhan_id, gan_boi, gan_luc)
SELECT t.contact_id, n.id, t.created_by, t.created_at
FROM contact_tags t
JOIN nhan n ON n.loai = 'khach'
           AND lower(n.ten) = lower(regexp_replace(btrim(t.tag), '\s+', ' ', 'g'))
ON CONFLICT DO NOTHING;

INSERT INTO hoi_thoai_gan_nhan (conversation_id, nhan_id, gan_boi, gan_luc)
SELECT h.conversation_id, n.id, h.tao_boi, h.tao_luc
FROM hoi_thoai_nhan h
JOIN nhan n ON n.loai = 'hoi_thoai'
           AND lower(n.ten) = lower(regexp_replace(btrim(h.nhan), '\s+', ' ', 'g'))
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------
-- ĐỔI QUY TẮC TỰ ĐỘNG SANG ID
-- ---------------------------------------------------------------------
--   nhan_co: "vip"                      -> nhan_hoi_thoai_co: ["<id>"]
--   nhan_khong: "đã chào"               -> nhan_hoi_thoai_khong: ["<id>"]
--   {"loai":"gan_nhan","nhan":"vip"}    -> {"loai":"gan_nhan_hoi_thoai","nhan_id":"<id>"}
--
-- Khoá cũ nào KHÔNG đổi được (giá trị không phải chữ, hoặc chữ rỗng) thì
-- để nguyên: agent/omnichannel/tu_dong.py vẫn hiểu khoá cũ (so theo TÊN
-- nhãn hội thoại đang gắn; gắn nhãn chữ thì tra danh mục, không có thì
-- lần chạy ghi "hỏng" kèm lý do). Lưu lại quy tắc qua API thì khoá cũ bị
-- đổi sang id hoặc bị từ chối 422 — không có đường nào lưu thêm chữ tự do.
-- Mỗi quy tắc đổi được ghi một sự kiện `nhan.chuyen_quy_tac`.
DO $$
DECLARE
    qt      RECORD;
    dk      JSONB;
    hd      JSONB;
    hd_moi  JSONB;
    pt      JSONB;
    nid     UUID;
    cu      TEXT;
    moi     TEXT;
    da_doi  BOOLEAN;
BEGIN
    FOR qt IN SELECT id, ten, dieu_kien, hanh_dong FROM quy_tac_tu_dong ORDER BY tao_luc LOOP
        dk := CASE WHEN jsonb_typeof(qt.dieu_kien) = 'string'
                   THEN (qt.dieu_kien #>> '{}')::jsonb ELSE qt.dieu_kien END;
        hd := CASE WHEN jsonb_typeof(qt.hanh_dong) = 'string'
                   THEN (qt.hanh_dong #>> '{}')::jsonb ELSE qt.hanh_dong END;
        da_doi := false;

        IF jsonb_typeof(dk) = 'object' THEN
            FOR cu, moi IN SELECT * FROM (VALUES ('nhan_co', 'nhan_hoi_thoai_co'),
                                                 ('nhan_khong', 'nhan_hoi_thoai_khong')) v LOOP
                IF jsonb_typeof(dk -> cu) = 'string' THEN
                    SELECT id INTO nid FROM nhan
                    WHERE loai = 'hoi_thoai'
                      AND lower(ten) = lower(regexp_replace(btrim(dk ->> cu), '\s+', ' ', 'g'));
                    IF nid IS NOT NULL THEN
                        dk := (dk - cu) || jsonb_build_object(moi, jsonb_build_array(nid::text));
                        da_doi := true;
                    END IF;
                END IF;
            END LOOP;
        END IF;

        IF jsonb_typeof(hd) = 'array' THEN
            hd_moi := '[]'::jsonb;
            FOR pt IN SELECT * FROM jsonb_array_elements(hd) LOOP
                IF pt ->> 'loai' = 'gan_nhan' AND jsonb_typeof(pt -> 'nhan') = 'string' THEN
                    SELECT id INTO nid FROM nhan
                    WHERE loai = 'hoi_thoai'
                      AND lower(ten) = lower(regexp_replace(btrim(pt ->> 'nhan'), '\s+', ' ', 'g'));
                    IF nid IS NOT NULL THEN
                        pt := jsonb_build_object('loai', 'gan_nhan_hoi_thoai', 'nhan_id', nid::text);
                        da_doi := true;
                    END IF;
                END IF;
                hd_moi := hd_moi || jsonb_build_array(pt);
            END LOOP;
            hd := hd_moi;
        END IF;

        IF da_doi THEN
            UPDATE quy_tac_tu_dong SET dieu_kien = dk, hanh_dong = hd WHERE id = qt.id;
            INSERT INTO events (kind, actor, ref_id, detail)
            VALUES ('nhan.chuyen_quy_tac', 'migration_0056', qt.id,
                    jsonb_build_object('ten', qt.ten, 'dieu_kien', dk, 'hanh_dong', hd));
        END IF;
    END LOOP;
END $$;

-- Một dòng tổng kết: con số để người vận hành đối chiếu sau khi nâng cấp.
INSERT INTO events (kind, actor, detail)
SELECT 'nhan.chuyen_doi', 'migration_0056', jsonb_build_object(
    'nhan_khach', (SELECT count(*) FROM nhan WHERE loai = 'khach'),
    'nhan_hoi_thoai', (SELECT count(*) FROM nhan WHERE loai = 'hoi_thoai'),
    'gan_khach', (SELECT count(*) FROM khach_gan_nhan),
    'gan_hoi_thoai', (SELECT count(*) FROM hoi_thoai_gan_nhan),
    'contact_tags_bo_qua', (SELECT count(*) FROM contact_tags t WHERE NOT EXISTS (
        SELECT 1 FROM khach_gan_nhan k JOIN nhan n ON n.id = k.nhan_id
        WHERE k.contact_id = t.contact_id
          AND lower(n.ten) = lower(regexp_replace(btrim(t.tag), '\s+', ' ', 'g')))),
    'hoi_thoai_nhan_bo_qua', (SELECT count(*) FROM hoi_thoai_nhan h WHERE NOT EXISTS (
        SELECT 1 FROM hoi_thoai_gan_nhan g JOIN nhan n ON n.id = g.nhan_id
        WHERE g.conversation_id = h.conversation_id
          AND lower(n.ten) = lower(regexp_replace(btrim(h.nhan), '\s+', ' ', 'g'))))
);
