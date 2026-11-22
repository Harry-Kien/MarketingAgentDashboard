-- BA MỨC ỦY QUYỀN THỰC THI CỦA AI (phiếu việc của chủ dự án, mục 17 — 22.11.2026).
--
-- 1. CHÍNH SÁCH THEO HÀNH ĐỘNG (`ai_uy_quyen`)
-- Mỗi hành động nghiệp vụ AI có thể làm (tạo đơn, huỷ đơn…) mang MỘT mức:
--   khong_su_dung  AI không được làm — chuyển nhân viên
--   co_phe_duyet   AI chuẩn bị đề xuất, chờ người có thẩm quyền duyệt
--   tu_dong        AI làm thẳng khi đủ điều kiện nghiệp vụ và lưới an toàn
-- Danh mục hành động và mức MẶC ĐỊNH nằm trong MÃ (agent/core/uy_quyen.py),
-- không nằm ở đây: bảng chỉ giữ những gì quản trị đã ĐỔI. Không có dòng =
-- dùng mặc định của mã. Nhờ vậy thêm một hành động mới vào mã thì nó có mức
-- mặc định ngay (hỏng-đóng: hành động lạ = không sử dụng), không cần chờ ai
-- chèn dòng — và quên chèn dòng không thể biến thành "tự động".
--
-- `nguong_vnd` chỉ có nghĩa với `tao_don`: ở mức tự động, đơn từ ngưỡng này
-- trở lên vẫn phải duyệt — đó là `NGUONG_TU_CHOT_VND` cũ, nay sửa được trên
-- dashboard. NULL = dùng giá trị trong `.env`.
CREATE TABLE IF NOT EXISTS ai_uy_quyen (
    hanh_dong   TEXT PRIMARY KEY,
    muc         TEXT NOT NULL CHECK (muc IN ('khong_su_dung', 'co_phe_duyet', 'tu_dong')),
    nguong_vnd  BIGINT CHECK (nguong_vnd IS NULL OR nguong_vnd >= 0),
    sua_boi     TEXT NOT NULL DEFAULT 'system',
    sua_luc     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. YÊU CẦU PHÊ DUYỆT (`ai_de_xuat`)
-- AI đã chuẩn bị một hành động CỤ THỂ nhưng chưa được tự làm. Khác chuyển
-- người: chuyển người là AI thiếu thông tin hay khả năng, người cầm hội
-- thoại; phê duyệt là AI đã có đủ dữ liệu đã kiểm, chỉ thiếu THẨM QUYỀN.
--
-- Vòng đời (CHECK bên dưới, test canh khớp với mã):
--   cho_duyet -> da_duyet -> da_thuc_hien | loi
--   cho_duyet -> tu_choi
--   cho_duyet -> het_han         (quá `het_han_luc`)
-- `da_duyet` là trạng thái GIỮ CHỖ: người duyệt đầu tiên chuyển nó trong một
-- giao dịch có khoá dòng, người thứ hai thấy không còn `cho_duyet` và bị từ
-- chối — một đề xuất không bao giờ thi hành hai lần.
CREATE TABLE IF NOT EXISTS ai_de_xuat (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    hanh_dong        TEXT NOT NULL,
    -- Chế độ AI lúc đề xuất và vì sao phải duyệt (Gợi ý / chính sách / vượt
    -- ngưỡng) — lưu nguyên văn để lịch sử không phụ thuộc cấu hình hiện tại.
    che_do_ai        TEXT NOT NULL CHECK (che_do_ai IN ('goi_y', 'tu_dong')),
    muc_uy_quyen     TEXT NOT NULL CHECK (muc_uy_quyen IN ('khong_su_dung', 'co_phe_duyet', 'tu_dong')),
    ly_do_can_duyet  TEXT NOT NULL,
    trang_thai       TEXT NOT NULL DEFAULT 'cho_duyet' CHECK (trang_thai IN (
                         'cho_duyet', 'da_duyet', 'da_thuc_hien', 'loi', 'tu_choi', 'het_han')),
    order_id         UUID REFERENCES orders(id) ON DELETE SET NULL,
    -- Tin AI cùng lượt — mở "Xem căn cứ" (messages.dau_vet_ai, 0053) từ thẻ.
    message_id       UUID REFERENCES messages(id) ON DELETE SET NULL,
    -- Đầu vào ĐÃ KIỂM để thi hành: dòng hàng với giá lấy từ danh mục, không
    -- phải lời model. Thi hành lại kiểm từ đầu, không tin chỗ này là đúng.
    tham_so          JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Cho người đọc: tiêu đề, trước/sau, lý do.
    de_xuat          JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Nguồn hệ thống đã kiểm, rủi ro, điều kiện còn thiếu.
    can_cu           JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Chống trùng: một đề xuất ĐANG MỞ cho cùng việc trên cùng đối tượng.
    khoa_trung       TEXT NOT NULL,
    tao_luc          TIMESTAMPTZ NOT NULL DEFAULT now(),
    het_han_luc      TIMESTAMPTZ NOT NULL,
    duyet_boi        UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    duyet_luc        TIMESTAMPTZ,
    tu_choi_boi      UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    tu_choi_luc      TIMESTAMPTZ,
    ly_do_tu_choi    TEXT,
    thuc_hien_luc    TIMESTAMPTZ,
    ket_qua          JSONB,
    loi              TEXT,
    cap_nhat_luc     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_de_xuat_mot_dang_mo
    ON ai_de_xuat (khoa_trung) WHERE trang_thai IN ('cho_duyet', 'da_duyet');
CREATE INDEX IF NOT EXISTS idx_ai_de_xuat_hoi_thoai
    ON ai_de_xuat (conversation_id, tao_luc);
CREATE INDEX IF NOT EXISTS idx_ai_de_xuat_cho
    ON ai_de_xuat (het_han_luc) WHERE trang_thai = 'cho_duyet';
CREATE INDEX IF NOT EXISTS idx_ai_de_xuat_don
    ON ai_de_xuat (order_id) WHERE order_id IS NOT NULL;
