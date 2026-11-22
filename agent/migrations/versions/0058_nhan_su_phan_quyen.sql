-- Nhân sự & Phân quyền (phiếu việc mục 12 và 13).
--
-- Bốn việc, cùng một đợt vì chúng cùng trả lời một câu: "đổi ai làm được gì
-- mà không làm mất dấu vết, không làm ai mất việc đang làm".

-- ---------------------------------------------------------------------
-- 1. VAI TRÒ NGỪNG DÙNG thay cho XOÁ
-- ---------------------------------------------------------------------
-- Xoá một vai trò đã từng được gán là xoá luôn câu trả lời cho "tháng trước
-- vì sao người này duyệt được đơn": `nguoi_dung_vai_tro` ON DELETE CASCADE
-- cuốn theo mọi dòng gán, và nhật ký chỉ còn trỏ vào một id không tồn tại.
--
-- Vai trò ngừng dùng KHÔNG cấp quyền nào (mọi chỗ tính quyền lọc
-- `vt.dang_dung` — có test quét mã canh), không gán mới được (trigger dưới),
-- nhưng vẫn nằm đó để lịch sử đọc được.
ALTER TABLE vai_tro
    ADD COLUMN IF NOT EXISTS dang_dung BOOLEAN NOT NULL DEFAULT true,
    -- Lần ĐẦU vai trò được gán cho ai đó. Khác NULL = có lịch sử nghiệp vụ,
    -- không xoá hẳn được nữa, chỉ ngừng dùng. Đặt bằng trigger chứ không
    -- bằng API: gán vai trò còn đi qua `scripts.tao_tai_khoan`, qua lệnh SQL
    -- cứu hộ trong CLAUDE.md, qua `cua_hang nhap` — đường nào quên đặt thì
    -- vai trò ấy xoá được mà không ai biết nó từng có người mang.
    ADD COLUMN IF NOT EXISTS tung_gan_luc TIMESTAMPTZ;

-- Vai trò dựng sẵn không ngừng dùng được. `Quản trị` mà ngừng là không còn
-- ai có `nguoi_dung.sua` (API có chặn, nhưng sửa tay trong CSDL thì không
-- qua API) — chốt ở CSDL là chốt cuối cùng còn đứng khi mọi chốt khác bị
-- vòng qua.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'vai_tro_he_thong_luon_dung'
          AND conrelid = 'vai_tro'::regclass
    ) THEN
        ALTER TABLE vai_tro ADD CONSTRAINT vai_tro_he_thong_luon_dung
            CHECK (dang_dung OR NOT he_thong);
    END IF;
END
$$;

-- Vai trò đang có người mang, hoặc nhật ký từng ghi một lần gán nó, là đã
-- có lịch sử. Soi nhật ký bằng `detail::text` chứ không bằng toán tử JSONB:
-- dữ liệu cũ có dòng bị mã hoá hai lần (chuỗi JSON nằm trong JSONB), và
-- `detail -> 'vai_tro'` trên một chuỗi trả NULL — tức là bỏ sót im lặng.
-- `LIKE 'nguoi_dung%vai_tro'` thay cho so bằng: test quét migration coi mọi
-- chuỗi dạng `x.y` trong ngoặc đơn là tên quyền.
UPDATE vai_tro vt
   SET tung_gan_luc = now()
 WHERE vt.tung_gan_luc IS NULL
   AND (EXISTS (SELECT 1 FROM nguoi_dung_vai_tro x WHERE x.vai_tro_id = vt.id)
        OR EXISTS (SELECT 1 FROM events e
                    WHERE e.kind LIKE 'nguoi_dung%vai_tro'
                      AND e.detail::text LIKE '%' || vt.id::text || '%'));

CREATE OR REPLACE FUNCTION nguoi_dung_vai_tro_truoc_khi_gan()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    con_dung BOOLEAN;
BEGIN
    SELECT dang_dung INTO con_dung FROM vai_tro WHERE id = NEW.vai_tro_id;
    -- Không có dòng: để khoá ngoại báo lỗi của nó, đừng nói một câu sai.
    IF con_dung IS NOT NULL AND NOT con_dung THEN
        RAISE EXCEPTION 'vai_tro_ngung_dung: vai trò % đã ngừng dùng, không gán mới được',
            NEW.vai_tro_id USING ERRCODE = 'check_violation';
    END IF;
    UPDATE vai_tro SET tung_gan_luc = coalesce(tung_gan_luc, now())
     WHERE id = NEW.vai_tro_id AND tung_gan_luc IS NULL;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_nguoi_dung_vai_tro_gan ON nguoi_dung_vai_tro;
CREATE TRIGGER trg_nguoi_dung_vai_tro_gan
BEFORE INSERT ON nguoi_dung_vai_tro
FOR EACH ROW EXECUTE FUNCTION nguoi_dung_vai_tro_truoc_khi_gan();

-- ---------------------------------------------------------------------
-- 2. EMAIL NHÂN VIÊN (mục 13.3: "họ tên, email hoặc tên đăng nhập")
-- ---------------------------------------------------------------------
-- Không bắt buộc: cửa hàng nhỏ có nhân viên không dùng email. Duy nhất khi
-- có — hai tài khoản cùng một email là hai người không phân biệt được trên
-- màn Nhân viên, và chuông báo/ khôi phục mật khẩu sau này gửi nhầm người.
ALTER TABLE nguoi_dung ADD COLUMN IF NOT EXISTS email TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_nguoi_dung_email
    ON nguoi_dung (lower(email)) WHERE email IS NOT NULL;

-- ---------------------------------------------------------------------
-- 3. QUYỀN MỚI TÁCH RA — GIỮ NGUYÊN AI LÀM ĐƯỢC GÌ
-- ---------------------------------------------------------------------
-- Ba việc trước đây đi kèm một quyền khác nay có quyền riêng. Migration
-- không được là chỗ lặng lẽ THU quyền: người vận hành chạy nó để nâng cấp,
-- không để thay đổi ai làm được gì. Nên cấp quyền mới cho đúng những vai
-- trò đang làm được việc ấy hôm nay. Siết lại là việc của quản trị, có chủ
-- ý, trên màn Vai trò & Quyền — và để lại lịch sử ở đó.
INSERT INTO vai_tro_quyen (vai_tro_id, quyen)
SELECT vai_tro_id, moi.quyen
  FROM vai_tro_quyen cu
  JOIN (VALUES
        ('hoi_thoai.tra_loi', 'ai.duyet'),
        ('hoi_thoai.tra_loi', 'hoi_thoai.ghi_chu'),
        ('don.doc', 'kho.doc'),
        ('don.sua', 'kho.sua')
  ) AS moi(tu, quyen) ON moi.tu = cu.quyen
ON CONFLICT DO NOTHING;
