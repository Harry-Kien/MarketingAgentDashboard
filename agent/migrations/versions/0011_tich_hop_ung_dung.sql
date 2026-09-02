-- Ứng dụng nhúng do người vận hành tự đăng ký.
--
-- Trước đây danh sách nằm trong `_MAC_DINH` của agent/api/tich_hop.py: bốn
-- tên gán cứng. Thêm Grafana, Metabase, Uptime Kuma hay bất cứ công cụ nội
-- bộ nào cũng phải sửa Python rồi triển khai lại — tức là phải có lập trình
-- viên cho một việc thuần vận hành.
--
-- VÌ SAO NẰM TRONG CSDL CHỨ KHÔNG PHẢI .env
--
-- Cùng lý do với `ky_nang_cai_dat`: sửa .env là phải khởi động lại, và
-- người trực ca đêm không làm được việc đó. Thêm một bảng thì đăng ký xong
-- là dùng được ngay.
--
-- DANH SÁCH TRẮNG VẪN CÒN, CHỈ LÀ NÓ GHI ĐƯỢC
--
-- Cái chặn SSRF không phải việc danh sách nằm trong mã — mà là việc tên app
-- lấy từ URL phải được TRA trong một danh sách, thay vì ghép thẳng vào địa
-- chỉ đích. Chuyển danh sách xuống CSDL không mất tính chất đó.
--
-- Bù lại, thêm một rào mới ở tầng ghi: địa chỉ đích BẮT BUỘC trỏ vào
-- loopback hoặc dải mạng riêng — xem `_kiem_dia_chi` trong tich_hop.py.

CREATE TABLE IF NOT EXISTS tich_hop_ung_dung (
    -- Tên đi thẳng vào đường dẫn /tich-hop/<ten>/ nên bị ràng buộc dạng
    -- chặt ở tầng ứng dụng: chữ thường, số, gạch ngang.
    ten        TEXT PRIMARY KEY,

    -- Nhãn hiện trên dashboard. Tách khỏi `ten` để đổi cách gọi mà không
    -- phá đường dẫn người ta đã bookmark.
    nhan       TEXT NOT NULL,

    -- Địa chỉ gốc, ví dụ http://127.0.0.1:3000
    dia_chi    TEXT NOT NULL,

    bat        BOOLEAN NOT NULL DEFAULT TRUE,
    tao_boi    TEXT,
    tao_luc    TIMESTAMPTZ NOT NULL DEFAULT now(),
    sua_luc    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Danh sách app đang bật được đọc ở MỌI request đi qua proxy. Chỉ mục
-- riêng phần đang bật giữ lượt đọc đó rẻ.
CREATE INDEX IF NOT EXISTS idx_tich_hop_bat ON tich_hop_ung_dung (ten) WHERE bat;
