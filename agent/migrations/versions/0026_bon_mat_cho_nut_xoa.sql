-- Bốn mắt THẬT cho nút xoá dữ liệu cá nhân.
--
-- VẤN ĐỀ ĐANG SỬA
-- ---------------
-- Màn Nhật ký có khối "Đếm trước khi xoá — có người thứ hai duyệt", và
-- `data_retention_jobs` có đủ `requested_by` / `approved_by` với chốt
-- "người tạo không tự duyệt được". Nhưng nút xoá THẬT
-- (`POST /api/pdpd/{sdt}/xoa`) không hề nhìn tới bảng ấy: nó chỉ đòi quyền
-- `khach.xoa` và bắt gõ lại số điện thoại.
--
-- Nghĩa là quy trình duyệt chỉ canh việc ĐẾM, còn việc không hoàn tác được
-- thì một người bấm là xong. Đó là một chốt trông như chốt mà không khoá
-- gì — kiểu tệ nhất, vì người vận hành đọc tiêu đề panel rồi tin rằng đã
-- có người thứ hai canh.
--
-- VÌ SAO KHOÁ PHIẾU THEO SỐ ĐIỆN THOẠI, KHÔNG THEO `contact_id`
-- -------------------------------------------------------------
-- Phiếu đang gắn `contact_id`, còn nút xoá chạy theo SỐ ĐIỆN THOẠI. Hai
-- khoá khác nhau, và đo trên CSDL đang chạy: 0/8 dòng `contacts` có
-- `phone`. Buộc phiếu theo contact là mọi phiếu đều không khớp được số nào
-- — nút xoá thành tường gạch, và tường gạch thì người ta gỡ chốt chứ không
-- sửa dữ liệu.
--
-- Khoá theo số cũng đóng luôn một đường trôi: tra ngược contact ->
-- `contacts.phone` NGAY LÚC XOÁ thì khách được gộp hồ sơ hay sửa số sau khi
-- duyệt là phiếu ấy bỗng cho phép xoá một số KHÁC với số người duyệt đã
-- nhìn thấy. Không lỗi, không nhật ký.
--
-- VÌ SAO LƯU DẤU VÂN TAY CHỨ KHÔNG LƯU SỐ
-- ---------------------------------------
-- Phiếu ở lại bảng này VĨNH VIỄN để làm bằng chứng đã có người thứ hai
-- duyệt. Lưu số thật vào đó là sau khi "đã xoá", chính số vừa hứa xoá vẫn
-- nằm nguyên trong CSDL — đúng cái lý do `du_lieu_ca_nhan` băm số trước khi
-- ghi nhật ký. Băm 9 chữ số cuối: "+84967627336" và "0967 627 336" ra cùng
-- một dấu, nên phiếu vẫn khớp dù khách viết kiểu nào.
ALTER TABLE data_retention_jobs ADD COLUMN IF NOT EXISTS sdt_van_tay TEXT;

-- Dạng che, CHỈ để người duyệt biết mình đang duyệt cho ai — duyệt mà không
-- biết duyệt cho số nào thì bốn mắt chỉ còn là hai cú bấm. Cột này bị xoá
-- đi ngay khi phiếu được dùng (xem `du_lieu_ca_nhan._gianh_phieu_duyet`),
-- để thứ ở lại lâu dài chỉ còn dấu vân tay.
ALTER TABLE data_retention_jobs ADD COLUMN IF NOT EXISTS sdt_che TEXT;

-- Phiếu duyệt dùng MỘT LẦN. Không có cột này thì một phiếu đã duyệt trở
-- thành giấy phép xoá vĩnh viễn cho số đó: xoá xong, tháng sau khách nhắn
-- lại, một người tự xoá tiếp mà không ai duyệt lần nữa.
ALTER TABLE data_retention_jobs ADD COLUMN IF NOT EXISTS xoa_thuc_hien_luc TIMESTAMPTZ;

-- Vá dấu vân tay cho phiếu cũ có contact mang số. `sha256()` là hàm dựng
-- sẵn của Postgres 11+, và `left(...,16)` khớp đúng
-- `hashlib.sha256(...).hexdigest()[:16]` bên Python. Không vá thì phiếu cũ
-- vô dụng mà không ai hiểu vì sao.
UPDATE data_retention_jobs j
   SET sdt_van_tay = left(encode(sha256(right(regexp_replace(c.phone, '\D', '', 'g'), 9)::bytea), 'hex'), 16)
  FROM contacts c
 WHERE c.id = j.contact_id
   AND j.sdt_van_tay IS NULL
   AND c.phone IS NOT NULL
   AND length(regexp_replace(c.phone, '\D', '', 'g')) >= 9;

-- Chỉ mục bộ phận: lúc xoá chỉ tra những phiếu CHƯA dùng. Phiếu đã dùng
-- nằm lại mãi để làm bằng chứng, nên chỉ mục đầy đủ là trả tiền cho toàn bộ
-- lịch sử để phục vụ vài dòng còn hiệu lực.
CREATE INDEX IF NOT EXISTS idx_retention_phieu_con_hieu_luc
    ON data_retention_jobs (sdt_van_tay)
 WHERE sdt_van_tay IS NOT NULL AND xoa_thuc_hien_luc IS NULL;
