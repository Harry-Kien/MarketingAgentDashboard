-- Xác thực hai bước (TOTP) cho người dùng dashboard.
--
-- VÌ SAO
-- ------
-- Khi host công khai, trang đăng nhập nằm trên Internet. Một mật khẩu bị lộ
-- (dùng lại ở trang khác, nhân viên nghỉ việc ghi vào sổ) là mở được toàn bộ
-- hội thoại và số điện thoại khách — dữ liệu cá nhân theo Luật BVDLCN.
--
-- Bí mật TOTP KHÔNG lưu nguyên văn: mã hoá AES-GCM bằng kho khoá sẵn có
-- (agent/security/credential_vault.py), AAD gắn với id người dùng — chép
-- bản mã sang người khác thì không giải được. Mã dự phòng lưu dạng băm
-- scrypt như mật khẩu.

ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS hai_buoc_bat BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS totp_phien_ban INT;
ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS totp_nonce BYTEA;
ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS totp_ma_hoa BYTEA;
ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS ma_du_phong TEXT[] NOT NULL DEFAULT '{}';
-- Chặn dùng lại cùng một mã trong cửa sổ 30 giây (replay).
ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS totp_buoc_cuoi BIGINT;
