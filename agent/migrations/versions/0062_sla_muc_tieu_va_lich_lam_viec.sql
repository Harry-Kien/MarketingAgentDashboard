-- SLA theo TỪNG MỤC TIÊU, MỘT lịch làm việc chung, và hạn PHẢN HỒI SAU
-- CHUYỂN GIAO (phiếu việc của chủ dự án, mục 15 — 22.11.2026).
--
-- 1. MỘT LỊCH LÀM VIỆC (`lich_lam_viec`)
-- Rà soát tìm ra BA nguồn "giờ làm việc" khác nhau: `.env` GIO_LAM_VIEC_*
-- (câu báo ngoài giờ, điều kiện "ngoài giờ" của quy tắc tự động), cùng ô ấy
-- truyền vào `sla_han()` (hạn SLA), và `sla_policies.business_hours` (giờ
-- riêng từng chính sách). Ba nơi đọc ba thứ là ba giờ mở cửa cho cùng một
-- shop — câu báo khách "8 giờ có người" trong khi hạn SLA chạy từ 9 giờ.
-- Bảng này là nguồn DUY NHẤT khi đã có dòng (sửa ở dashboard); chưa có dòng
-- thì mọi nơi lui về `.env` y như trước — xem agent/core/lich_lam_viec.py.
--
-- Một dòng duy nhất (id = 1): cửa hàng có một lịch. `tuan` là 7 phần tử,
-- Thứ Hai trước, mỗi phần tử [phút mở, phút đóng] trong ngày hoặc null =
-- nghỉ cả ngày. Phút chứ không giờ: "8 giờ 30" là giờ mở cửa có thật.
CREATE TABLE IF NOT EXISTS lich_lam_viec (
    id         SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    bat        BOOLEAN NOT NULL DEFAULT true,
    tuan       JSONB NOT NULL CHECK (jsonb_typeof(tuan) = 'array'
                                     AND jsonb_array_length(tuan) = 7),
    ngay_nghi  JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(ngay_nghi) = 'array'),
    sua_boi    TEXT,
    sua_luc    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. CHẾ ĐỘ TÍNH GIỜ VÀ NGƯỠNG CẢNH BÁO THEO TỪNG MỤC TIÊU (`sla_muc_tieu`)
-- Trước bản này một công tắc `SLA_THEO_GIO_LAM_VIEC` quyết cho mọi mục tiêu.
-- Chủ dự án cần chọn riêng: phản hồi đầu có thể 24/7 (AI trực đêm) trong
-- khi phản hồi sau chuyển giao chỉ tính giờ có người. Thiếu dòng = lui về
-- công tắc `.env` cũ và ngưỡng chung `SLA_NGUONG_CANH_BAO`.
CREATE TABLE IF NOT EXISTS sla_muc_tieu (
    muc_tieu        TEXT PRIMARY KEY CHECK (muc_tieu IN (
                        'phan_hoi_dau', 'phan_hoi_sau_chuyen_giao', 'giai_quyet')),
    che_do          TEXT NOT NULL CHECK (che_do IN ('gio_lam_viec', '24_7')),
    nguong_canh_bao INT CHECK (nguong_canh_bao IS NULL
                               OR nguong_canh_bao BETWEEN 10 AND 95),
    sua_boi         TEXT,
    sua_luc         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. HẠN PHẢN HỒI SAU CHUYỂN GIAO
-- Số phút đặt theo chính sách (kênh × mức ưu tiên) như hai mục tiêu cũ.
-- NULL = chính sách không đặt mục tiêu này: lượt chuyển giao vẫn được ghi
-- và đo thời gian, chỉ không có hạn để đạt hay trễ.
ALTER TABLE sla_policies
    ADD COLUMN IF NOT EXISTS handover_response_minutes INT
        CHECK (handover_response_minutes IS NULL OR handover_response_minutes > 0);

-- Mỗi LƯỢT chuyển giao một dòng. Không dùng `sla_events`: khoá duy nhất
-- của bảng ấy là (hội thoại, chu kỳ, loại) — AI chuyển giao lần thứ hai
-- trong cùng chu kỳ thì `ON CONFLICT DO NOTHING` nuốt im vi phạm của lần
-- hai. Đổi khoá ấy là sửa tám câu `ON CONFLICT` đang chạy (và mọi câu nhánh
-- khác đang viết), hỏng lúc chạy chứ không lúc dịch. Bảng riêng có khoá
-- (hội thoại, lần) và giữ trọn lịch sử từng lượt.
CREATE TABLE IF NOT EXISTS sla_chuyen_giao (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    chu_ky          INT NOT NULL DEFAULT 1,
    lan             INT NOT NULL CHECK (lan >= 1),
    bat_dau         TIMESTAMPTZ NOT NULL,
    due_at          TIMESTAMPTZ,
    canh_bao_luc    TIMESTAMPTZ,
    vi_pham_luc     TIMESTAMPTZ,
    phan_hoi_luc    TIMESTAMPTZ,
    phan_hoi_boi    UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    message_id      UUID REFERENCES messages(id) ON DELETE SET NULL,
    ket_thuc_luc    TIMESTAMPTZ,
    ket_thuc_ly_do  TEXT CHECK (ket_thuc_ly_do IS NULL
                                OR ket_thuc_ly_do IN ('phan_hoi', 'giai_quyet', 'tra_ai')),
    ket_qua         TEXT NOT NULL DEFAULT 'dang_cho'
                    CHECK (ket_qua IN ('dang_cho', 'dat', 'tre', 'khong_han', 'huy')),
    detail          JSONB NOT NULL DEFAULT '{}',
    tao_luc         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, lan)
);

-- Mỗi hội thoại tối đa MỘT lượt đang chờ: hai tiến trình canh SLA cùng mở
-- lượt cho một lần chuyển giao thì lần chèn thứ hai đụng chỉ mục này.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sla_chuyen_giao_dang_cho
    ON sla_chuyen_giao (conversation_id) WHERE ket_thuc_luc IS NULL;
CREATE INDEX IF NOT EXISTS idx_sla_chuyen_giao_bat_dau ON sla_chuyen_giao (bat_dau);

-- Lịch sử không sửa ngược được. Vi phạm và cảnh báo đã ghi thì giữ nguyên
-- — kể cả khi người trực đã đọc (hoặc lờ) thông báo, kể cả một câu UPDATE
-- gõ tay; hạn chỉ được rút ngắn (cùng luật `prevent_sla_deadline_reset`,
-- 0054); lượt đã chốt kết cục thì không mở lại, không đổi kết cục.
CREATE OR REPLACE FUNCTION giu_lich_su_sla_chuyen_giao()
RETURNS trigger AS $$
BEGIN
    NEW.bat_dau := OLD.bat_dau;
    NEW.vi_pham_luc := coalesce(OLD.vi_pham_luc, NEW.vi_pham_luc);
    NEW.canh_bao_luc := coalesce(OLD.canh_bao_luc, NEW.canh_bao_luc);
    IF OLD.due_at IS NOT NULL
       AND (NEW.due_at IS NULL OR NEW.due_at > OLD.due_at) THEN
        NEW.due_at := OLD.due_at;
    END IF;
    IF OLD.ket_thuc_luc IS NOT NULL THEN
        NEW.ket_thuc_luc := OLD.ket_thuc_luc;
        NEW.ket_thuc_ly_do := OLD.ket_thuc_ly_do;
        NEW.ket_qua := OLD.ket_qua;
        NEW.phan_hoi_luc := OLD.phan_hoi_luc;
    END IF;
    IF NEW.vi_pham_luc IS NOT NULL AND NEW.ket_qua IN ('dat', 'huy') THEN
        NEW.ket_qua := 'tre';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_giu_lich_su_sla_chuyen_giao ON sla_chuyen_giao;
CREATE TRIGGER trg_giu_lich_su_sla_chuyen_giao
BEFORE UPDATE ON sla_chuyen_giao
FOR EACH ROW EXECUTE FUNCTION giu_lich_su_sla_chuyen_giao();

-- 4. HẠN THEO LỊCH TUẦN
-- `sla_han()` (0039) chỉ biết MỘT khung giờ cho mọi ngày. Lịch chung có
-- ngày nghỉ trong tuần, giờ khác nhau theo thứ, và ngày lễ — nên cần một
-- phép tính mới. `sla_han()` giữ nguyên (đã chốt checksum, và test cũ canh
-- nó); mọi chỗ đặt hạn chuyển sang hàm dưới đây qua `sla_gio.bieu_thuc_han`.
--
-- `lich` do mã Python dựng (`Lich.json_sql`): {"tuan": [[mo, dong]|null ×7],
-- "nghi": ["YYYY-MM-DD", ...], "gio_rieng": bool}. NULL = đồng hồ chạy 24/7.
-- Lịch không có ngày mở nào (hoặc hỏng) cũng tính 24/7: hỏng theo hướng
-- phục vụ khách, cùng quy ước với `dang_trong_gio()`.
CREATE OR REPLACE FUNCTION sla_khung_hop_le(w JSONB)
RETURNS BOOLEAN LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    RETURN coalesce(
        jsonb_typeof(w) = 'array' AND jsonb_array_length(w) = 2
        AND (w ->> 0)::int >= 0 AND (w ->> 0)::int < (w ->> 1)::int
        AND (w ->> 1)::int <= 1440,
        false);
EXCEPTION WHEN others THEN
    RETURN false;
END
$$;

CREATE OR REPLACE FUNCTION sla_han_lich(bat_dau TIMESTAMPTZ, phut INTEGER, lich JSONB)
RETURNS TIMESTAMPTZ LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    con    INTERVAL;
    t      TIMESTAMP;            -- giờ Việt Nam, không múi (UTC+7 cố định)
    ngay   TIMESTAMP;
    w      JSONB;
    nghi   JSONB;
    mo     TIMESTAMP;
    dong   TIMESTAMP;
    du     INTERVAL;
    co_mo  BOOLEAN := false;
    i      INTEGER;
BEGIN
    IF bat_dau IS NULL OR phut IS NULL THEN
        RETURN NULL;
    END IF;
    con := make_interval(mins => GREATEST(phut, 0));
    IF lich IS NULL OR jsonb_typeof(lich -> 'tuan') IS DISTINCT FROM 'array'
       OR jsonb_array_length(lich -> 'tuan') <> 7 THEN
        RETURN bat_dau + con;
    END IF;
    FOR i IN 0..6 LOOP
        IF sla_khung_hop_le(lich -> 'tuan' -> i) THEN
            co_mo := true;
        END IF;
    END LOOP;
    IF NOT co_mo THEN
        RETURN bat_dau + con;
    END IF;
    nghi := CASE WHEN jsonb_typeof(lich -> 'nghi') = 'array'
                 THEN lich -> 'nghi' ELSE '[]'::jsonb END;
    t := (bat_dau AT TIME ZONE 'UTC') + INTERVAL '7 hours';
    -- Chặn trên số vòng: mỗi vòng tiến ít nhất một ngày. Mười năm ngày nghỉ
    -- liên tiếp là dữ liệu hỏng — lui về 24/7 thay vì treo câu tạo hội thoại.
    FOR i IN 1..3700 LOOP
        ngay := date_trunc('day', t);
        w := lich -> 'tuan' -> (extract(isodow FROM ngay)::int - 1);
        IF NOT sla_khung_hop_le(w) OR nghi ? to_char(ngay, 'YYYY-MM-DD') THEN
            t := ngay + INTERVAL '1 day';
            CONTINUE;
        END IF;
        mo   := ngay + make_interval(mins => (w ->> 0)::int);
        dong := ngay + make_interval(mins => (w ->> 1)::int);
        IF t < mo THEN
            t := mo;
        END IF;
        IF t >= dong THEN
            t := ngay + INTERVAL '1 day';
            CONTINUE;
        END IF;
        du := dong - t;
        IF con <= du THEN
            RETURN ((t + con) - INTERVAL '7 hours') AT TIME ZONE 'UTC';
        END IF;
        con := con - du;
        t := ngay + INTERVAL '1 day';
    END LOOP;
    RETURN bat_dau + make_interval(mins => GREATEST(phut, 0));
END
$$;

-- Giờ riêng của MỘT chính sách (`business_hours` {"bat_dau", "ket_thuc"},
-- giờ nguyên) — CHỈ khi lịch đang lui về `.env` (`gio_rieng`: true), tức
-- chưa ai lưu lịch chung trên dashboard. Đó là hành vi cũ (0039), giữ để
-- tương thích. Đã có lịch chung thì lịch chung là nguồn duy nhất và ô này
-- thôi có tác dụng — ba nguồn giờ là đúng thứ bản này sinh ra để dẹp.
-- Ô hỏng thì giữ nguyên lịch (cùng tinh thần `sla_gio()`).
CREATE OR REPLACE FUNCTION sla_lich_chinh_sach(lich JSONB, gio_rieng JSONB)
RETURNS JSONB LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    mo   INTEGER;
    dong INTEGER;
BEGIN
    IF lich IS NULL OR NOT coalesce((lich ->> 'gio_rieng')::boolean, false) THEN
        RETURN lich;
    END IF;
    mo := sla_gio(gio_rieng, 'bat_dau', NULL);
    dong := sla_gio(gio_rieng, 'ket_thuc', NULL);
    IF mo IS NULL OR dong IS NULL OR mo < 0 OR dong > 24 OR mo >= dong THEN
        RETURN lich;
    END IF;
    RETURN jsonb_set(lich, '{tuan}', (
        SELECT jsonb_agg(jsonb_build_array(mo * 60, dong * 60))
        FROM generate_series(1, 7)));
EXCEPTION WHEN others THEN
    RETURN lich;
END
$$;
