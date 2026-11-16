-- Bí mật TOTP ĐANG CHỜ xác nhận, tách khỏi bí mật đang dùng.
--
-- VÌ SAO
-- ------
-- Trước bản này `POST /api/toi/hai-buoc/bat-dau` ghi bí mật mới đè lên cột
-- đang dùng VÀ đặt `hai_buoc_bat = false` ngay — trước khi người dùng gõ
-- được mã nào. Phiên bị chiếm (cookie lộ) gọi đúng một request ấy là GỠ 2FA
-- của tài khoản, không cần mật khẩu, không cần mã.
--
-- Giờ bí mật mới nằm ở ba cột "chờ"; 2FA đang bật giữ nguyên cho tới khi
-- `xac_nhan` kiểm được một mã thật từ bí mật mới. Mã hoá AES-GCM như cột
-- chính (0032_hai_buoc.sql), AAD riêng `totp-cho:<id>` — chép bản mã chờ
-- sang cột chính bằng tay thì không giải được.

ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS totp_cho_phien_ban INT;
ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS totp_cho_nonce BYTEA;
ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS totp_cho_ma_hoa BYTEA;
