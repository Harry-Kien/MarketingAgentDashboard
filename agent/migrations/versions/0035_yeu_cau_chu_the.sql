-- Sổ yêu cầu của chủ thể dữ liệu (khách) — Luật Bảo vệ dữ liệu cá nhân
-- 91/2025/QH15 Điều 4, thời hạn theo Nghị định 356/2025/NĐ-CP Điều 5.
--
-- VÌ SAO PHẢI CÓ SỔ
-- -----------------
-- Khách nhắn "xoá dữ liệu của em đi" vào khung chat. Trước đây yêu cầu ấy
-- chỉ là một tin nhắn: không ai biết nó tồn tại ngoài người đọc tin, không
-- có hạn, không có gì báo khi quá hạn. Luật cho 2 ngày làm việc để phản hồi
-- và 20 ngày để xoá. Quá hạn là vi phạm — và đúng kiểu hỏng im lặng.
--
-- KHÔNG LƯU SỐ ĐIỆN THOẠI
-- ----------------------
-- Sổ phải SỐNG SÓT qua chính việc xoá mà nó theo dõi: nó là bằng chứng đã
-- đáp ứng yêu cầu. Lưu số thật thì xoá xong dữ liệu vẫn nằm trong sổ. Lưu
-- dấu băm (`du_lieu_ca_nhan._dau_van_tay`) — đủ để khớp, không đủ để đọc.
-- `noi_dung` là lời tóm tắt của nhân viên, không phải nguyên văn tin khách.

CREATE TABLE IF NOT EXISTS yeu_cau_chu_the (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    loai            TEXT        NOT NULL CHECK (loai IN (
                        'xem', 'sua', 'xoa', 'rut_dong_y', 'han_che', 'phan_doi', 'bao_ve')),
    dau_van_tay     TEXT        NOT NULL DEFAULT '' CHECK (char_length(dau_van_tay) <= 64),
    kenh_nhan       TEXT        NOT NULL DEFAULT 'chat' CHECK (kenh_nhan IN (
                        'chat', 'dien_thoai', 'email', 'truc_tiep', 'van_ban')),
    noi_dung        TEXT        NOT NULL DEFAULT '' CHECK (char_length(noi_dung) <= 500),
    -- Phải nhờ bên xử lý / bên thứ ba (ERP, hãng vận chuyển) thì hạn dài hơn.
    co_ben_thu_ba   BOOLEAN     NOT NULL DEFAULT false,
    nhan_luc        TIMESTAMPTZ NOT NULL DEFAULT now(),
    han_phan_hoi    TIMESTAMPTZ NOT NULL,
    han_xu_ly       TIMESTAMPTZ NOT NULL,
    -- Gia hạn tối đa MỘT lần, phải có lý do và phải báo khách (NĐ 356 Điều 5).
    gia_han_den     TIMESTAMPTZ,
    ly_do_gia_han   TEXT        NOT NULL DEFAULT '' CHECK (char_length(ly_do_gia_han) <= 300),
    phan_hoi_luc    TIMESTAMPTZ,
    xong_luc        TIMESTAMPTZ,
    trang_thai      TEXT        NOT NULL DEFAULT 'moi' CHECK (trang_thai IN (
                        'moi', 'da_phan_hoi', 'da_xong', 'tu_choi')),
    ket_qua         TEXT        NOT NULL DEFAULT '' CHECK (char_length(ket_qua) <= 500),
    tao_boi         UUID        REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    xu_ly_boi       UUID        REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    CHECK (gia_han_den IS NULL OR gia_han_den > han_xu_ly),
    CHECK (trang_thai NOT IN ('da_xong', 'tu_choi') OR xong_luc IS NOT NULL),
    -- Từ chối phải nói vì sao (Luật 91/2025 Điều 14 khoản 2, Điều 19).
    CHECK (trang_thai <> 'tu_choi' OR char_length(btrim(ket_qua)) > 0)
);
CREATE INDEX IF NOT EXISTS idx_yeu_cau_chu_the_mo
    ON yeu_cau_chu_the (trang_thai, han_xu_ly) WHERE trang_thai IN ('moi', 'da_phan_hoi');
CREATE INDEX IF NOT EXISTS idx_yeu_cau_chu_the_van_tay
    ON yeu_cau_chu_the (dau_van_tay) WHERE dau_van_tay <> '';
