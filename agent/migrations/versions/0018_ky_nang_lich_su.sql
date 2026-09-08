-- Lịch sử bản mô tả của plugin RỜI, để lùi lại được sau một lần sửa hỏng.
--
-- VÌ SAO GIỜ MỚI CÓ, TRONG KHI GÓI ĐÃ CÓ TỪ 0014
--
-- Gói viết một lần rồi để đó; plugin rời là thứ người vận hành sửa hằng
-- tuần — và từ đợt "khoá khách hay hỏi mà bảng chưa có" thì dashboard còn
-- mời họ sửa thường xuyên hơn nữa, mỗi lần một cú bấm. Càng dễ sửa thì
-- càng cần đường lùi, nên bất đối xứng cũ ngược hẳn với thực tế dùng.
--
-- Bảng RIÊNG chứ không thêm cột vào `ky_nang_cai_dat`: một cột JSONB chứa
-- mảng mười bản làm mọi lượt đọc cài đặt kéo theo cả khối chữ ấy, mà
-- `cong_cu_dang_bat()` chạy ở MỌI lượt trả lời khách.
--
-- Không khoá ngoại tới `ky_nang_cai_dat`: xoá một plugin rồi tạo lại cùng
-- tên là chuyện thường, và mất lịch sử ở giữa là mất đúng thứ người ta cần
-- lúc muốn biết "hôm trước nó thế nào".

CREATE TABLE IF NOT EXISTS ky_nang_lich_su (
    id        BIGSERIAL PRIMARY KEY,
    ten       TEXT NOT NULL,
    noi_dung  JSONB NOT NULL,
    thay_luc  TIMESTAMPTZ NOT NULL DEFAULT now(),
    thay_boi  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ky_nang_lich_su_ten
    ON ky_nang_lich_su (ten, id DESC);
