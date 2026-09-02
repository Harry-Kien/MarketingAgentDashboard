-- Bật/tắt kỹ năng, và kỹ năng cắm thêm (plugin).
--
-- VÌ SAO NẰM TRONG CSDL CHỨ KHÔNG PHẢI TRONG `agent/runtime.py`.
--
-- `runtime.STATE` là biến trong bộ nhớ tiến trình: khởi động lại là về mặc
-- định. Với công tắc ngắt hay ngưỡng tin cậy thì chấp nhận được — người
-- trực nhìn thấy trạng thái ngay trên thanh đầu trang và chỉnh lại trong
-- vài giây.
--
-- Với kỹ năng thì KHÔNG. Người vận hành tắt `tao_don_hang` lúc 2 giờ sáng
-- vì phát hiện bảng giá sai; máy chủ khởi động lại lúc 4 giờ; tới sáng
-- agent đã chốt đơn suốt hai tiếng theo bảng giá sai — và không có gì báo,
-- vì trạng thái "đã bật lại" trông y hệt trạng thái "chưa từng tắt".
--
-- Một dòng trong bảng thì sống qua mọi lần khởi động lại.

CREATE TABLE IF NOT EXISTS ky_nang_cai_dat (
    -- Tên công cụ, khớp với `name` trong lược đồ gửi model.
    ten        TEXT PRIMARY KEY,
    bat        BOOLEAN NOT NULL DEFAULT TRUE,

    -- NULL = kỹ năng viết sẵn trong mã (dòng này chỉ ghi bật/tắt).
    -- Khác NULL = plugin, và đây là toàn bộ định nghĩa của nó.
    --
    -- Lưu cả bản mô tả thay vì tách thành cột: bản mô tả được KIỂM bằng
    -- `doc_ban_mo_ta()` mỗi lần đọc lên, nên cột riêng chỉ tạo ra con đường
    -- thứ hai để ghi vào — con đường không đi qua bộ kiểm.
    ban_mo_ta  JSONB,

    tao_boi    TEXT,
    tao_luc    TIMESTAMPTZ NOT NULL DEFAULT now(),
    sua_luc    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Danh sách kỹ năng đang bật được đọc ở MỌI lượt trả lời khách. Chỉ mục
-- riêng phần đang bật giữ lượt đọc đó rẻ ngay cả khi bảng đầy plugin đã tắt.
CREATE INDEX IF NOT EXISTS idx_ky_nang_bat ON ky_nang_cai_dat (ten) WHERE bat;
