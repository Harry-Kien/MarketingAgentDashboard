-- 0068: cờ "phải đổi mật khẩu ở lần đăng nhập tới" (UX-13-07).
--
-- Quản trị đặt lại mật khẩu cho nhân viên quên mật khẩu, hoặc đặt mật khẩu
-- ban đầu lúc tạo tài khoản. Cả hai lần, QUẢN TRỊ biết mật khẩu ấy. Không
-- có cờ này thì mật khẩu do người khác biết sống mãi — đúng điều màn Đổi
-- mật khẩu sinh ra để chấm dứt.
--
-- Cờ đặt ở bảng người dùng chứ không ở phiên: đặt lại mật khẩu đá mọi phiên,
-- nên cờ phải sống qua lần đăng nhập kế tiếp. Máy chủ chặn mọi /api (trừ
-- /api/toi và /api/toi/doi-mat-khau) khi cờ bật — xem
-- `chan_neu_chua_dang_nhap` ở agent/main.py. Đổi mật khẩu thành công thì
-- tắt cờ (`xac_thuc.doi_mat_khau`).
--
-- Mặc định false: không ai đang làm việc bị bắt đổi mật khẩu chỉ vì nâng
-- cấp phiên bản.
ALTER TABLE nguoi_dung
    ADD COLUMN IF NOT EXISTS phai_doi_mat_khau BOOLEAN NOT NULL DEFAULT false;
