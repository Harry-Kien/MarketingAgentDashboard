-- Khoá API của nhà cung cấp model, ERP, vận chuyển — nhập từ dashboard.
--
-- VÌ SAO KHÔNG ĐỂ TRONG .env
-- Khoá trong .env đọc một lần lúc khởi động. Đổi khoá là mở file, sửa tay,
-- khởi động lại; gõ sai một ký tự thì agent im lặng ngừng trả lời. Người
-- vận hành cửa hàng không nên phải mở file cấu hình để đổi một API key.
--
-- VÌ SAO KHÔNG DÙNG cau_hinh_agent
-- Bảng đó lưu JSONB ở dạng THƯỜNG. Khoá API là bí mật: phải mã hoá bằng
-- đúng vault đang bảo vệ credential kênh (AES-256-GCM, AAD theo phạm vi),
-- nên cần cột nonce/ciphertext/key_version riêng.
--
-- .env vẫn là đường lui: bảng rỗng thì hệ thống chạy như trước.

CREATE TABLE IF NOT EXISTS cau_hinh_bi_mat (
    khoa          TEXT PRIMARY KEY,
    key_version   INTEGER NOT NULL,
    nonce         BYTEA NOT NULL,
    ciphertext    BYTEA NOT NULL,
    sua_boi       TEXT NOT NULL,
    sua_luc       TIMESTAMPTZ NOT NULL DEFAULT now(),
    kiem_luc      TIMESTAMPTZ,
    kiem_ket_qua  TEXT
);
