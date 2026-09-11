-- Vai trò tự tạo thay hai vai trò cứng `quan_tri | nhan_vien`.
--
-- VÌ SAO ĐỔI
-- ----------
-- Đếm thật trên app.routes: 166 route dưới /api và /tich-hop. 73 canh quản
-- trị, 32 canh đăng nhập, 61 không kiểm gì (vẫn kín nhờ middleware ở
-- main.py). Nghĩa là 85 route chỉ cần "đã đăng nhập" — và trong đó có duyệt
-- đơn, huỷ đơn, nhập kho, kiểm kê, duyệt bài đăng công khai, sửa kho tri
-- thức, tra cứu dữ liệu cá nhân theo số điện thoại.
--
-- Không có lỗ hổng nào với người ngoài. Nhưng bên trong thì mọi nhân viên
-- ngang quyền nhau ở những việc lẽ ra không ngang, và không có cách nào
-- phân biệt ngoài việc viết thêm mã.
--
-- VÌ SAO VAI TRÒ LÀ DỮ LIỆU CÒN DANH MỤC QUYỀN LÀ MÃ
-- ---------------------------------------------------
-- `vai_tro_quyen.quyen` CỐ Ý không có khoá ngoại: danh mục quyền sống trong
-- `agent/core/quyen.py`, không trong CSDL.
--
-- Nếu danh mục là bảng, thì thêm quyền là INSERT — và người thêm endpoint
-- tháng sau sẽ INSERT một quyền mới rồi quên gắn nó vào endpoint, hoặc gắn
-- một chuỗi chưa từng tồn tại. Cả hai đều im lặng. Danh mục trong mã cho
-- phép `kiem_moi_route_co_quyen()` quét mọi route lúc khởi động và ném.
--
-- Đổi lại: lúc đọc phải lọc bỏ quyền không còn trong danh mục (quyền bị xoá
-- ở bản sau), và có test canh không còn dòng mồ côi.

CREATE TABLE IF NOT EXISTS vai_tro (
    id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ten      TEXT UNIQUE NOT NULL CHECK (length(ten) BETWEEN 1 AND 80),
    mo_ta    TEXT NOT NULL DEFAULT '',
    -- Vai trò dựng sẵn. API từ chối xoá chúng: xoá vai trò Quản trị khi nó
    -- là vai trò duy nhất có `nguoi_dung.sua` là tự khoá mình ra ngoài, và
    -- không còn đường nào vào lại ngoài sửa tay trong CSDL.
    he_thong BOOLEAN NOT NULL DEFAULT false,
    tao_luc  TIMESTAMPTZ NOT NULL DEFAULT now(),
    sua_luc  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vai_tro_quyen (
    vai_tro_id UUID NOT NULL REFERENCES vai_tro(id) ON DELETE CASCADE,
    quyen      TEXT NOT NULL,
    PRIMARY KEY (vai_tro_id, quyen)
);

CREATE TABLE IF NOT EXISTS nguoi_dung_vai_tro (
    nguoi_dung_id UUID NOT NULL REFERENCES nguoi_dung(id) ON DELETE CASCADE,
    vai_tro_id    UUID NOT NULL REFERENCES vai_tro(id)    ON DELETE CASCADE,
    gan_boi       UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    gan_luc       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (nguoi_dung_id, vai_tro_id)
);

-- `doc_phien` JOIN theo chiều này ở MỌI request. Thiếu chỉ mục thì mỗi lần
-- tải trang là một lần quét bảng.
CREATE INDEX IF NOT EXISTS idx_ndvt_vai_tro
    ON nguoi_dung_vai_tro (vai_tro_id);

-- --- Nạp sẵn hai vai trò -------------------------------------

INSERT INTO vai_tro (ten, mo_ta, he_thong) VALUES
    ('Quản trị',
     'Toàn quyền. Vai trò dựng sẵn, không xoá được.',
     true),
    ('Nhân viên',
     'Trả lời khách, xem đơn và tồn kho. Vai trò dựng sẵn, không xoá được.',
     true)
ON CONFLICT (ten) DO NOTHING;

-- Quyền của `Quản trị` KHÔNG gõ ở đây.
--
-- Nó là *toàn bộ danh mục*, và danh mục ở trong mã. Gõ lại trong SQL là tạo
-- bản sao thứ hai, và bản sao sẽ lệch ở phiên bản sau: thêm quyền mới vào
-- mã thì quản trị không có nó, im lặng. `doc_phien()` cấp `frozenset(QUYEN)`
-- cho ai mang vai trò hệ thống tên 'Quản trị'.

-- Tập quyền của `Nhân viên` chọn để BẰNG ĐÚNG những gì nhân viên làm được
-- TRƯỚC migration này — không hơn không kém.
--
-- Migration không được là chỗ lặng lẽ đổi quyền của người đang làm việc.
-- Người vận hành chạy nó để nâng cấp, không để thay đổi ai làm được gì.
-- Việc siết quyền là của các bước sau, có chủ ý và nhìn thấy được.
--
-- `khach.pii` có trong tập vì hôm nay nhân viên xem được PII khi là
-- owner/manager của tài khoản kênh; trục `account_memberships` vẫn siết
-- tiếp phía sau trong SQL, nên để quyền này ở đây không nới thêm gì.
INSERT INTO vai_tro_quyen (vai_tro_id, quyen)
SELECT vt.id, q.ma
FROM vai_tro vt
CROSS JOIN (VALUES
    ('hoi_thoai.doc'),
    ('hoi_thoai.tra_loi'),
    ('hoi_thoai.nhan'),
    ('khach.doc'),
    ('khach.sua'),
    ('khach.pii'),
    ('khach.gop'),
    ('don.doc'),
    ('kenh.doc'),
    ('bao_cao.doc'),
    ('noi_dung.doc'),
    ('outbox.doc'),
    ('dinh_tuyen.doc'),
    ('agent.doc'),
    ('ky_nang.doc'),
    ('cau_hinh.doc'),
    ('tich_hop.doc'),
    ('nguoi_dung.doc')
) AS q(ma)
WHERE vt.ten = 'Nhân viên'
ON CONFLICT DO NOTHING;

-- --- Backfill người đang có ----------------------------------
--
-- KHÔNG BỎ QUA BƯỚC NÀY. Thiếu nó thì sau migration không ai có quyền gì —
-- kể cả quản trị. Đăng nhập vẫn được, chỉ là mọi màn đều 403, nên người gặp
-- sẽ kết luận máy chủ hỏng và đi khởi động lại. Khởi động lại không chữa.
INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id)
SELECT nd.id, vt.id
FROM nguoi_dung nd
JOIN vai_tro vt
  ON vt.ten = CASE WHEN nd.vai_tro = 'quan_tri' THEN 'Quản trị'
                   ELSE 'Nhân viên' END
ON CONFLICT DO NOTHING;
