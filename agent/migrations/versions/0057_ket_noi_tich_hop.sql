-- Kết nối & Tích hợp: kết quả "Kiểm tra kết nối", lịch sử đổi cấu hình,
-- và sổ webhook đã nhận theo từng dịch vụ.
--
-- VÌ SAO KẾT QUẢ KIỂM CÓ `dau_van_tay`
-- Kết quả "Kết nối thành công" chỉ đúng cho ĐÚNG bộ giá trị đã kiểm. Đổi
-- token sau khi kiểm mà màn hình vẫn xanh là xanh giả — nguy hiểm hơn đỏ
-- giả. Dấu vân tay là băm (cắt ngắn) của bộ giá trị lúc kiểm; lệch với bộ
-- hiện hành thì trạng thái quay về "Chưa kiểm tra", kể cả khi người ta sửa
-- `.env` bằng tay chứ không qua dashboard.
CREATE TABLE IF NOT EXISTS ket_noi_kiem_tra (
    dich_vu      TEXT PRIMARY KEY CHECK (dich_vu ~ '^[a-z_]{2,40}$'),
    ok           BOOLEAN NOT NULL,
    chi_tiet     TEXT NOT NULL DEFAULT '' CHECK (char_length(chi_tiet) <= 300),
    ms           INT NOT NULL DEFAULT 0 CHECK (ms >= 0),
    dau_van_tay  TEXT NOT NULL CHECK (char_length(dau_van_tay) BETWEEN 8 AND 64),
    kiem_boi     TEXT,
    kiem_luc     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Lịch sử đổi cấu hình kết nối: AI, LÚC NÀO, TRƯỜNG NÀO.
--
-- KHÔNG CÓ CỘT GIÁ TRỊ — cố ý. Một cột "giá trị cũ/mới" chỉ cần một lần ai
-- đó quên che là thành bản sao rõ của khoá bí mật nằm ngoài vault. Không có
-- cột thì không có chỗ để quên.
--
-- `account_id` KHÔNG có khoá ngoại: xoá tài khoản kênh vẫn phải để lại dấu
-- "ai đã xoá", và dòng lịch sử nằm lại sau khi tài khoản đi là đúng ý đồ.
CREATE TABLE IF NOT EXISTS lich_su_ket_noi (
    id          BIGSERIAL PRIMARY KEY,
    dich_vu     TEXT NOT NULL CHECK (char_length(dich_vu) BETWEEN 1 AND 40),
    truong      TEXT NOT NULL CHECK (char_length(truong) BETWEEN 1 AND 300),
    hanh_dong   TEXT NOT NULL CHECK (hanh_dong IN (
                    'dat', 'xoa', 'doi_credential', 'bat', 'tat',
                    'doi_tuy_chon', 'tao', 'xoa_tai_khoan')),
    bi_mat      BOOLEAN NOT NULL DEFAULT false,
    account_id  UUID,
    doi_tuong   TEXT CHECK (doi_tuong IS NULL OR char_length(doi_tuong) <= 120),
    sua_boi     TEXT NOT NULL,
    sua_luc     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lich_su_ket_noi_luc
    ON lich_su_ket_noi (sua_luc DESC);
CREATE INDEX IF NOT EXISTS idx_lich_su_ket_noi_dich_vu
    ON lich_su_ket_noi (dich_vu, sua_luc DESC);

-- Sổ webhook đã nhận: MỌI lời gọi vào `/webhook/*`, kể cả lời bị từ chối.
--
-- VÌ SAO CẦN KHI ĐÃ CÓ `webhook_deliveries`
-- `webhook_deliveries` chỉ có dòng cho tin ĐÃ qua chữ ký và parse được —
-- nó là sổ chống trùng. Webhook bị 401 vì lệch bí mật (callback Zalo cá
-- nhân từng bị 401 tám ngày mà không ai biết), GHTK gửi form mà ta đọc
-- JSON, GHN gọi thiếu token: tất cả không để lại dòng nào ở đó. Sổ này ghi
-- mã HTTP, thời gian xử lý và lỗi của từng lần gọi, nên màn Kết nối & Tích
-- hợp trả lời được "hãng có gọi vào không, và lần cuối hỏng vì sao".
--
-- Chỉ ghi ĐƯỜNG DẪN, không bao giờ ghi query string: URL webhook vận chuyển
-- mang bí mật trong `?token=`. Không có khoá ngoại tới channel_accounts vì
-- UUID trong đường dẫn do bên ngoài gửi tới, có thể là rác — một dòng ghi
-- hỏng vì khoá ngoại là đúng lần gọi cần nhìn thấy nhất bị mất.
CREATE TABLE IF NOT EXISTS webhook_nhan (
    id            BIGSERIAL PRIMARY KEY,
    dich_vu       TEXT NOT NULL CHECK (char_length(dich_vu) BETWEEN 1 AND 40),
    account_id    UUID,
    phuong_thuc   TEXT NOT NULL CHECK (char_length(phuong_thuc) <= 10),
    duong         TEXT NOT NULL CHECK (char_length(duong) <= 300),
    ma_http       INT NOT NULL,
    thoi_gian_ms  INT NOT NULL CHECK (thoi_gian_ms >= 0),
    loi           TEXT CHECK (loi IS NULL OR char_length(loi) <= 300),
    nhan_luc      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_webhook_nhan_dich_vu
    ON webhook_nhan (dich_vu, nhan_luc DESC);
CREATE INDEX IF NOT EXISTS idx_webhook_nhan_tai_khoan
    ON webhook_nhan (account_id, nhan_luc DESC) WHERE account_id IS NOT NULL;
