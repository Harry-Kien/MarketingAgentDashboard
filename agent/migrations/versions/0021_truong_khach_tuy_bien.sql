-- Trường thông tin khách do người vận hành tự thêm trên dashboard.
--
-- VÌ SAO ĐỊNH NGHĨA LÀ BẢNG CÒN GIÁ TRỊ LÀ JSONB
-- -----------------------------------------------
-- Hai lựa chọn hiển nhiên hơn, và vì sao không chọn:
--
--   Mỗi trường một CỘT trên `contacts`. Nghĩa là mỗi lần người vận hành
--   thêm một trường là một lần `ALTER TABLE` chạy từ tầng ứng dụng — tức
--   trao quyền sửa lược đồ cho bất kỳ ai vào được màn Cấu hình. Và lược đồ
--   khi ấy khác nhau giữa các máy, nên migration checksum hết ý nghĩa.
--
--   Cả định nghĩa LẪN giá trị trong JSONB. Rẻ hơn, nhưng khi ấy không có
--   gì buộc hai thứ khớp nhau: một trường bị xoá khỏi định nghĩa vẫn còn
--   giá trị nằm lại trong hồ sơ khách, vô hình trên màn hình và không ai
--   gỡ được. Với DỮ LIỆU CÁ NHÂN thì đó không phải bất tiện, đó là dữ liệu
--   giữ quá hạn mà không ai biết mình đang giữ (Nghị định 13/2023/NĐ-CP).
--
-- Nên: định nghĩa vào bảng — đếm được, sửa được, xoá được, và xoá thì kéo
-- theo giá trị. Giá trị vào `contacts.profile` vốn đã tồn tại.

CREATE TABLE IF NOT EXISTS truong_khach (
    -- `ma` là KHOÁ trong `contacts.profile`. Đổi nó là mọi giá trị đã lưu
    -- thành mồ côi, nên API cấm đổi — chỉ `nhan` sửa được.
    ma            TEXT PRIMARY KEY
                  CHECK (ma ~ '^[a-z][a-z0-9_]{0,39}$'),
    nhan          TEXT NOT NULL CHECK (length(nhan) BETWEEN 1 AND 80),
    kieu          TEXT NOT NULL,
    goi_y         TEXT NOT NULL DEFAULT '',
    bat_buoc      BOOLEAN NOT NULL DEFAULT false,
    -- Chỉ dùng cho kiểu `chon` và `nhieu_chon`. Danh sách chuỗi.
    lua_chon      JSONB NOT NULL DEFAULT '[]',
    -- Trường có hiện ở DANH SÁCH khách hay chỉ trong hồ sơ chi tiết.
    -- Mặc định false: danh sách nhồi thêm cột là danh sách không ai đọc.
    hien_danh_sach BOOLEAN NOT NULL DEFAULT false,
    thu_tu        INT NOT NULL DEFAULT 100,
    tao_luc       TIMESTAMPTZ NOT NULL DEFAULT now(),
    sua_luc       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (kieu IN ('chu', 'so', 'ngay', 'chon', 'nhieu_chon', 'dung_sai')),
    -- Kiểu `chon`/`nhieu_chon` mà không có lựa chọn nào là một ô người dùng
    -- không chọn được gì — và nó trông hệt như một ô đang tải.
    CHECK (kieu NOT IN ('chon', 'nhieu_chon')
           OR jsonb_array_length(lua_chon) > 0)
);

CREATE INDEX IF NOT EXISTS idx_truong_khach_thu_tu
    ON truong_khach (thu_tu, ma);

-- Chỉ mục để lọc/tìm theo giá trị trường tuỳ biến sau này. GIN trên JSONB
-- trả lời được `profile @> '{"loai_da": "dầu"}'` mà không quét bảng.
CREATE INDEX IF NOT EXISTS idx_contacts_profile
    ON contacts USING gin (profile);
