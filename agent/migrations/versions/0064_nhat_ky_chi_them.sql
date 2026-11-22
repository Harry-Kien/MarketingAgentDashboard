-- Nhật ký kiểm toán CHỈ THÊM, và tra được theo hội thoại / lượt AI.
--
-- Phiếu việc mục 18 (trách nhiệm của AI), các điểm 3, 4, 10–12.
--
-- 1. CHỈ THÊM (điểm 12)
-- `events` là bằng chứng: "ai đã làm gì, lúc nào". Bằng chứng sửa được thì
-- không còn là bằng chứng — một lệnh UPDATE lỡ tay (hay cố ý) xoá dấu vết
-- mà không để lại gì. Đính chính, giải trình, đánh dấu sự cố đều là DÒNG
-- MỚI trỏ về dòng gốc (`agent/core/nhat_ky_kiem_toan.py`).
--
-- Chặn ở CSDL chứ không chỉ ở mã: chốt trong mã chỉ canh được mã đi qua
-- nó; SQL tay, script dọn dẹp, một migration sau này thì không.
--
-- LỐI RA DUY NHẤT: `SET LOCAL cskh.cho_xoa_nhat_ky = 'on'`, chỉ cho DELETE
-- (không cho UPDATE). Hôm nay chưa đường nào xoá `events` — hạn lưu trữ và
-- yêu cầu xoá của khách (`du_lieu_ca_nhan.py`) xoá hội thoại, tin nhắn, hồ
-- sơ, sự kiện HỘP THƯ, không đụng bảng này. Lối ra để sẵn cho ngày luật bắt
-- dọn nhật ký quá hạn: đường ấy phải tự nói ra mình đang xoá nhật ký, trong
-- đúng giao dịch của nó (`SET LOCAL` hết hiệu lực khi giao dịch kết thúc).
-- UPDATE không có lối ra: sửa một dòng nhật ký không bao giờ là việc đúng —
-- ẩn danh thì xoá rồi ghi dòng mới.
--
-- Đây là chốt chống NHẦM và chống mã sai, không phải chống quản trị CSDL:
-- ai có quyền chủ bảng vẫn DROP TRIGGER được. Chống được người đó cần ghi
-- ra ngoài máy (WORM), nằm ngoài phạm vi (điểm 14).
CREATE OR REPLACE FUNCTION events_chi_them() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND coalesce(current_setting('cskh.cho_xoa_nhat_ky', true), '') = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'nhật ký kiểm toán (events) chỉ được thêm, không được % — '
                    'đính chính bằng một sự kiện mới', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END $$;

DROP TRIGGER IF EXISTS events_chi_them_dong ON events;
CREATE TRIGGER events_chi_them_dong
    BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW EXECUTE FUNCTION events_chi_them();

-- TRUNCATE không kích hoạt trigger theo dòng — không chặn riêng thì một
-- lệnh dọn bảng đi lọt qua đúng cái chốt vừa dựng.
DROP TRIGGER IF EXISTS events_chi_them_truncate ON events;
CREATE TRIGGER events_chi_them_truncate
    BEFORE TRUNCATE ON events
    FOR EACH STATEMENT EXECUTE FUNCTION events_chi_them();

-- 2. TRA THEO HỘI THOẠI VÀ LƯỢT AI (điểm 3, 4, 9)
-- Mọi sự kiện trong một lượt AI mang `detail.luot_id`; sự kiện có `ref_id`
-- không phải hội thoại (đơn, tin nhắn) mang thêm `detail.hoi_thoai_id`
-- (`agent/core/luot_ai.py`). Không chỉ mục thì mỗi lần mở "Nhật ký" của một
-- hội thoại là quét cả bảng lớn nhất hệ thống.
CREATE INDEX IF NOT EXISTS idx_event_ref_time
    ON events (ref_id, id DESC) WHERE ref_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_event_luot
    ON events ((detail ->> 'luot_id')) WHERE detail ? 'luot_id';
CREATE INDEX IF NOT EXISTS idx_event_hoi_thoai
    ON events ((detail ->> 'hoi_thoai_id'), id DESC) WHERE detail ? 'hoi_thoai_id';
-- Vài nơi ghi cũ để hội thoại ở `detail.conversation_id` thay vì `ref_id`.
CREATE INDEX IF NOT EXISTS idx_event_conversation_id
    ON events ((detail ->> 'conversation_id')) WHERE detail ? 'conversation_id';
-- Sự cố, giải trình trỏ về dòng gốc qua `detail.su_kien_goc`.
CREATE INDEX IF NOT EXISTS idx_event_su_kien_goc
    ON events ((detail ->> 'su_kien_goc')) WHERE detail ? 'su_kien_goc';

-- 3. QUYỀN MỚI `nhat_ky.su_co` (điểm 10–11)
-- Cấp cho mọi vai trò đang đọc được nhật ký: người đọc được nhật ký là
-- người đang làm việc soát lỗi; bắt quản trị đi cấp thêm thì ngày đầu không
-- ai đánh dấu được sự cố nào. Siết lại sau trên màn vai trò được.
INSERT INTO vai_tro_quyen (vai_tro_id, quyen)
SELECT vai_tro_id, 'nhat_ky.su_co' FROM vai_tro_quyen WHERE quyen = 'nhat_ky.doc'
ON CONFLICT DO NOTHING;
