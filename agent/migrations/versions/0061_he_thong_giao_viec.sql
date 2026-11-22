-- Hệ thống giao việc (phiếu việc mục 14): kết quả, lịch sử hoạt động,
-- nhắc quá hạn, và ba loại chuông mới cho công việc.
--
-- Cột còn thiếu so với "trường chuẩn" của một việc: KẾT QUẢ. Người làm xong
-- "gọi lại chị Hoa" phải ghi lại được chị Hoa nói gì — trước bản này chỉ có
-- `ket_qua_xu_ly_don` dành riêng cho việc huỷ/sửa đơn, việc thường đóng lại
-- là mất luôn câu trả lời. Các trường khác đã có: người tạo = `nguoi_giao`
-- (NULL khi máy tạo, nguồn ở `nguon`), cập nhật lúc = `sua_luc`, đơn =
-- `order_id` (0046).
ALTER TABLE cong_viec
    ADD COLUMN IF NOT EXISTS ket_qua TEXT,
    -- Mốc đã báo "việc quá hạn". Không có mốc bền thì vòng canh hoặc báo
    -- lại mỗi lượt (chuông đọc xong lại reo), hoặc không báo lần nào sau
    -- khi người ta đã đọc. API xoá mốc này khi hạn đổi: hạn mới, lần báo mới.
    ADD COLUMN IF NOT EXISTS bao_qua_han_luc TIMESTAMPTZ;

ALTER TABLE cong_viec DROP CONSTRAINT IF EXISTS cong_viec_ket_qua_dai_check;
ALTER TABLE cong_viec ADD CONSTRAINT cong_viec_ket_qua_dai_check
    CHECK (ket_qua IS NULL OR char_length(ket_qua) <= 2000);

-- Việc ĐANG quá hạn lúc nâng cấp coi như đã báo. Không thì lượt canh đầu
-- tiên sau khi nâng cấp đổ một tràng chuông về những việc cũ đã nằm trên
-- ô "quá hạn" của Tổng quan từ lâu — chuông reo một tràng là chuông người
-- ta học cách bỏ qua. Chạy TRƯỚC khi có trigger lịch sử bên dưới.
UPDATE cong_viec SET bao_qua_han_luc = now()
WHERE han < now() AND trang_thai IN ('moi', 'dang_lam') AND bao_qua_han_luc IS NULL;

-- ---------------------------------------------------------------------
-- LỊCH SỬ HOẠT ĐỘNG CỦA MỘT VIỆC
-- ---------------------------------------------------------------------
-- Ai tạo, giao cho ai, chuyển từ ai sang ai, đổi trạng thái lúc nào, ghi
-- kết quả gì. Trước bản này chỉ có `events` ghi "cong_viec.sua trang_thai=x"
-- — không có người nhận cũ/mới, và không đọc được từ màn chi tiết việc.
--
-- VÌ SAO GHI BẰNG TRIGGER, KHÔNG GHI Ở API
-- Việc đổi người nhận/trạng thái từ ÍT NHẤT sáu đường: API Công việc, chuyển
-- việc khi khoá nhân viên, định tuyến tự động, đóng theo hội thoại, xác nhận
-- kết quả đơn, phân công tự động. Ghi ở từng đường là đường mới nào quên ghi
-- thì lịch sử thiếu một đoạn — hỏng im lặng: màn chi tiết vẫn hiện lịch sử,
-- chỉ là lịch sử sai. Trigger thì không đường nào vòng qua được.
--
-- Người thao tác và ghi chú đến qua biến phiên GIAO DỊCH (`set_config(...,
-- true)` — `agent/core/cong_viec.py::dat_ngu_canh`), tự xoá khi giao dịch
-- kết thúc nên không rò sang yêu cầu khác trên cùng kết nối của pool. Đường
-- nào không đặt thì người thao tác là NULL = "hệ thống" — đúng sự thật hơn
-- là đoán.
CREATE TABLE IF NOT EXISTS cong_viec_lich_su (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cong_viec_id   UUID NOT NULL REFERENCES cong_viec(id) ON DELETE CASCADE,
    loai           TEXT NOT NULL CHECK (loai IN (
                       'tao', 'giao', 'nhan', 'chuyen', 'bo_giao',
                       'tu_dong_giao', 'trang_thai', 'tien_do', 'ket_qua', 'sua'
                   )),
    -- Người thao tác. NULL = hệ thống (AI, quy tắc, vòng nền).
    nguoi_id       UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    tu_nguoi       UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    den_nguoi      UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    tu_trang_thai  TEXT,
    den_trang_thai TEXT,
    ghi_chu        TEXT NOT NULL DEFAULT '' CHECK (char_length(ghi_chu) <= 2000),
    tao_luc        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_cong_viec_lich_su_viec
    ON cong_viec_lich_su (cong_viec_id, tao_luc);

-- Phân công tự động chọn người LÂU NHẤT chưa được giao việc — câu hỏi ấy
-- chạy mỗi lần tự phân công, nên có chỉ mục riêng.
CREATE INDEX IF NOT EXISTS idx_cong_viec_lich_su_den_nguoi
    ON cong_viec_lich_su (den_nguoi, tao_luc DESC)
    WHERE den_nguoi IS NOT NULL;

-- Việc có từ trước bản này: một dòng "tạo" để màn chi tiết không trống,
-- và nói thẳng là phần trước đó KHÔNG có — không bịa lịch sử.
INSERT INTO cong_viec_lich_su (cong_viec_id, loai, nguoi_id, ghi_chu, tao_luc)
SELECT v.id, 'tao', v.nguoi_giao,
       'Việc có từ trước khi bật lịch sử hoạt động — các thay đổi trước đó không được ghi lại.',
       v.tao_luc
FROM cong_viec v
WHERE NOT EXISTS (SELECT 1 FROM cong_viec_lich_su l WHERE l.cong_viec_id = v.id);

CREATE OR REPLACE FUNCTION ghi_lich_su_cong_viec()
RETURNS trigger AS $$
DECLARE
    v_nguoi   UUID := NULLIF(current_setting('cong_viec.nguoi_id', true), '')::uuid;
    v_ghi_chu TEXT := left(coalesce(current_setting('cong_viec.ghi_chu', true), ''), 2000);
    v_tu_dong BOOLEAN := coalesce(current_setting('cong_viec.tu_dong_giao', true), '') = '1';
    v_loai    TEXT;
    v_doi     TEXT[] := '{}';
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO cong_viec_lich_su (cong_viec_id, loai, nguoi_id, den_nguoi,
                                       den_trang_thai, ghi_chu)
        VALUES (NEW.id, 'tao', coalesce(v_nguoi, NEW.nguoi_giao), NEW.nguoi_nhan,
                NEW.trang_thai, v_ghi_chu);
        RETURN NEW;
    END IF;

    IF NEW.nguoi_nhan IS DISTINCT FROM OLD.nguoi_nhan THEN
        v_loai := CASE
            WHEN NEW.nguoi_nhan IS NULL THEN 'bo_giao'
            WHEN v_tu_dong THEN 'tu_dong_giao'
            WHEN OLD.nguoi_nhan IS NULL AND NEW.nguoi_nhan = v_nguoi THEN 'nhan'
            WHEN OLD.nguoi_nhan IS NULL THEN 'giao'
            ELSE 'chuyen'
        END;
        INSERT INTO cong_viec_lich_su (cong_viec_id, loai, nguoi_id, tu_nguoi,
                                       den_nguoi, ghi_chu)
        VALUES (NEW.id, v_loai, v_nguoi, OLD.nguoi_nhan, NEW.nguoi_nhan, v_ghi_chu);
    END IF;

    IF NEW.trang_thai IS DISTINCT FROM OLD.trang_thai THEN
        INSERT INTO cong_viec_lich_su (cong_viec_id, loai, nguoi_id, tu_trang_thai,
                                       den_trang_thai, ghi_chu)
        VALUES (NEW.id, 'trang_thai',
                -- Xác nhận kết quả đơn không qua API Công việc nhưng tự ghi
                -- người xử lý vào `xu_ly_boi` — dùng nó thay vì "hệ thống".
                coalesce(v_nguoi, CASE WHEN NEW.xu_ly_luc IS DISTINCT FROM OLD.xu_ly_luc
                                       THEN NEW.xu_ly_boi END),
                OLD.trang_thai, NEW.trang_thai, v_ghi_chu);
    END IF;

    IF NEW.ket_qua IS DISTINCT FROM OLD.ket_qua AND NEW.ket_qua IS NOT NULL THEN
        INSERT INTO cong_viec_lich_su (cong_viec_id, loai, nguoi_id, ghi_chu)
        VALUES (NEW.id, 'ket_qua', v_nguoi, left(NEW.ket_qua, 2000));
    END IF;

    IF NEW.ket_qua_xu_ly_don IS DISTINCT FROM OLD.ket_qua_xu_ly_don
       AND NEW.ket_qua_xu_ly_don IS NOT NULL THEN
        INSERT INTO cong_viec_lich_su (cong_viec_id, loai, nguoi_id, ghi_chu)
        VALUES (NEW.id, 'ket_qua', coalesce(v_nguoi, NEW.xu_ly_boi),
                left(NEW.ket_qua_xu_ly_don
                     || coalesce(': ' || NULLIF(NEW.ly_do_ket_qua, ''), ''), 2000));
    END IF;

    IF NEW.tieu_de IS DISTINCT FROM OLD.tieu_de THEN v_doi := v_doi || 'tieu_de'::text; END IF;
    IF NEW.mo_ta IS DISTINCT FROM OLD.mo_ta THEN v_doi := v_doi || 'mo_ta'::text; END IF;
    IF NEW.uu_tien IS DISTINCT FROM OLD.uu_tien THEN v_doi := v_doi || 'uu_tien'::text; END IF;
    IF NEW.han IS DISTINCT FROM OLD.han THEN v_doi := v_doi || 'han'::text; END IF;
    IF cardinality(v_doi) > 0 THEN
        -- Ghi MÃ trường, không ghi nhãn: nhãn đổi được, mã thì bền. Màn
        -- hình dịch mã sang tiếng Việt (`cong_viec.NHAN_TRUONG`).
        INSERT INTO cong_viec_lich_su (cong_viec_id, loai, nguoi_id, ghi_chu)
        VALUES (NEW.id, 'sua', v_nguoi, array_to_string(v_doi, ','));
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cong_viec_lich_su ON cong_viec;
CREATE TRIGGER trg_cong_viec_lich_su
AFTER INSERT OR UPDATE ON cong_viec
FOR EACH ROW EXECUTE FUNCTION ghi_lich_su_cong_viec();

-- ---------------------------------------------------------------------
-- BA LOẠI CHUÔNG MỚI CHO CÔNG VIỆC
-- ---------------------------------------------------------------------
-- `viec_chua_giao`: việc ra đời mà không ai nhận (AI đề xuất, quy tắc, vận
--     chuyển, hoặc phân công tự động không tìm được người) — báo người điều
--     phối, không thì "Chưa phân công" là một danh sách không ai mở.
-- `viec_huy`: việc của mình bị người khác huỷ.
-- `viec_qua_han`: việc chưa xong đã qua hạn.
-- Tập này phải khớp `thong_bao_noi_bo.LOAI` — có test canh.
ALTER TABLE thong_bao DROP CONSTRAINT IF EXISTS thong_bao_loai_check;
ALTER TABLE thong_bao ADD CONSTRAINT thong_bao_loai_check CHECK (loai IN (
    'duoc_giao_hoi_thoai',
    'ai_chuyen_giao',
    'can_duyet',
    'duoc_giao_viec',
    'sla_sap_tre',
    'sla_tre',
    'viec_chua_giao',
    'viec_huy',
    'viec_qua_han'
));
