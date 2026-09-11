-- Chủ sở hữu khách: "khách này do ai phụ trách".
--
-- VÌ SAO MỘT CỘT CHỨ KHÔNG MỘT BẢNG
-- ----------------------------------
-- `conversation_assignments` dùng bảng riêng, và đúng cho nó: hội thoại đổi
-- người liên tục, lịch sử LÀ dữ liệu chính, và một hội thoại chỉ sống vài
-- ngày.
--
-- Sở hữu khách ngược lại: đọc ở MỌI truy vấn danh sách khách, đổi thì hiếm,
-- và sống suốt đời khách hàng. JOIN thêm một bảng ở mọi truy vấn là chi phí
-- thường trực để phục vụ đúng một cột.
--
-- Lịch sử vẫn có bảng riêng ở dưới — chỉ là nó không nằm trên đường nóng.
--
-- VÌ SAO `ON DELETE SET NULL` CHỨ KHÔNG `RESTRICT`
-- -------------------------------------------------
-- RESTRICT nghe an toàn hơn: không cho xoá người còn đang giữ khách. Nhưng
-- hệ quả thật là không xoá nổi tài khoản của người đã nghỉ việc, và người
-- vận hành sẽ chọn đường dễ hơn — KHOÁ tài khoản rồi để đấy.
--
-- Khi ấy khách vẫn hiện "có chủ", chủ là một người không còn đi làm, và
-- không ai nhận ra vì màn hình trông vẫn bình thường. Khách của họ không ai
-- trả lời, và cũng không ai thấy là không ai trả lời.
--
-- SET NULL thì khách thành vô chủ NGAY, và rơi thẳng vào chỉ số "khách chưa
-- có chủ" trên trang Ca trực. Mất dữ liệu ư — không: ai từng là chủ vẫn nằm
-- nguyên trong `contact_owner_history`.

ALTER TABLE contacts ADD COLUMN IF NOT EXISTS owner_user_id UUID
    REFERENCES nguoi_dung(id) ON DELETE SET NULL;

-- Lọc "khách của tôi" chạy ở mọi lần mở màn Khách hàng.
CREATE INDEX IF NOT EXISTS idx_contacts_owner
    ON contacts (owner_user_id) WHERE owner_user_id IS NOT NULL;

-- Chỉ số "khách chưa có chủ" chạy ở MỌI lần tải trang Ca trực, và nó cần cả
-- số lượng lẫn khách vô chủ lâu nhất. Chỉ mục một phần theo `first_seen` trả
-- lời được cả hai mà không quét bảng.
CREATE INDEX IF NOT EXISTS idx_contacts_vo_chu
    ON contacts (first_seen)
    WHERE owner_user_id IS NULL AND status = 'active';

-- Lịch sử giao khách.
--
-- `owner_user_id` NULL ở đây nghĩa là THU HỒI — một sự kiện thật, phải ghi
-- được. Không ghi thì khoảng trống giữa hai lần giao trở nên vô hình, và
-- câu hỏi "từ lúc nào khách này không còn ai phụ trách" không trả lời được.
CREATE TABLE IF NOT EXISTS contact_owner_history (
    id            BIGSERIAL PRIMARY KEY,
    contact_id    UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    owner_user_id UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    actor_id      UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    ly_do         TEXT NOT NULL CHECK (length(ly_do) BETWEEN 3 AND 500),
    luc           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_coh_contact
    ON contact_owner_history (contact_id, luc DESC);
