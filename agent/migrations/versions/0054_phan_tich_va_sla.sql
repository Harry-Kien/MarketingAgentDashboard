-- Phân tích và nâng cấp SLA (rà soát 20.11.2026).
--
-- 1. CẢNH BÁO SỚM HẠN GIẢI QUYẾT
-- `first_response_warning` (0047) chỉ canh hạn PHẢN HỒI ĐẦU. Hạn GIẢI QUYẾT
-- thường dài cả ngày, và người trực chỉ biết nó khi đã trễ. Thêm loại sự kiện
-- `resolution_warning`, cùng cách 50% của cảnh báo cũ (agent/omnichannel/sla.py).
ALTER TABLE sla_events
    DROP CONSTRAINT IF EXISTS sla_events_kind_check;

ALTER TABLE sla_events
    ADD CONSTRAINT sla_events_kind_check CHECK (
        kind IN (
            'started',
            'first_response_met',
            'first_response_breached',
            'first_response_warning',
            'resolution_met',
            'resolution_breached',
            'resolution_warning',
            'paused',
            'resumed'
        )
    );

-- 2. ĐỔI ƯU TIÊN CHỈ ĐƯỢC RÚT NGẮN HẠN, KHÔNG ĐƯỢC KÉO DÀI
-- Trước bản này không ai đổi được ưu tiên của hội thoại, nên trigger chặn
-- MỌI thay đổi hạn trong một chu kỳ. Giờ có API đổi ưu tiên
-- (agent/api/uu_tien.py): nâng ưu tiên là khách cần được lo SỚM hơn, nên
-- hạn phải được phép rút lại.
--
-- Luật đặt ở CSDL, không chỉ ở API: hạ ưu tiên để "tặng thêm giờ" cho một
-- hội thoại sắp trễ là đúng kiểu né vi phạm mà trigger này sinh ra để chặn.
-- Trong cùng chu kỳ, một hạn chỉ được đổi khi:
--   * hạn MỚI sớm hơn hạn CŨ (rút ngắn), VÀ
--   * hạn CŨ còn ở tương lai, VÀ hạn MỚI không ở quá khứ.
-- Hai vế sau chặn một cách né khác: kéo một hạn ĐÃ QUA lùi xa hơn nữa thì
-- dấu "Quá hạn" ở hộp thư (so `sla_events.due_at` với hạn hiện hành) biến
-- mất, dù vi phạm vẫn nằm nguyên trong lịch sử.
-- Mọi trường hợp khác (kéo dài, xoá về NULL) vẫn lặng lẽ giữ hạn cũ — đúng
-- hành vi từ 0005.
CREATE OR REPLACE FUNCTION prevent_sla_deadline_reset()
RETURNS trigger AS $$
BEGIN
    -- Chu kỳ mới (mở lại hội thoại): hạn mới là đúng, cho qua.
    IF NEW.sla_chu_ky > OLD.sla_chu_ky THEN
        RETURN NEW;
    END IF;
    IF OLD.first_response_due_at IS NOT NULL
       AND NEW.first_response_due_at IS DISTINCT FROM OLD.first_response_due_at
       AND NOT (
           NEW.first_response_due_at IS NOT NULL
           AND NEW.first_response_due_at < OLD.first_response_due_at
           AND OLD.first_response_due_at > now()
           AND NEW.first_response_due_at >= now()
       ) THEN
        NEW.first_response_due_at := OLD.first_response_due_at;
    END IF;
    IF OLD.resolution_due_at IS NOT NULL
       AND NEW.resolution_due_at IS DISTINCT FROM OLD.resolution_due_at
       AND NOT (
           NEW.resolution_due_at IS NOT NULL
           AND NEW.resolution_due_at < OLD.resolution_due_at
           AND OLD.resolution_due_at > now()
           AND NEW.resolution_due_at >= now()
       ) THEN
        NEW.resolution_due_at := OLD.resolution_due_at;
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

-- 3. TIN AI GHI HỒ SƠ AGENT LÚC VIẾT
-- Hồ sơ agent gán theo TÀI KHOẢN KÊNH (0024) và đổi được bất cứ lúc nào.
-- Báo cáo "hồ sơ nào làm tốt hơn" mà tra hồ sơ ĐANG gán cho kênh là quy công
-- tháng trước cho hồ sơ vừa gán hôm qua. Chụp lại ngay lúc tin được ghi.
--
-- Chụp bằng trigger chứ không bằng mã gọi: tin AI được ghi ở hai đường
-- (bản nháp trong xu_ly_tin_vao.py, tin xếp hàng trong outbound_service.py),
-- và đường thứ ba thêm sau này sẽ quên truyền cột. Trigger dùng ĐÚNG luật
-- chọn hồ sơ của `agent_ho_so.cho_kenh()`: hồ sơ của kênh, chỉ khi đang bật.
--
-- `ho_so_da_ghi` tách "tin trước bản này, không biết hồ sơ" khỏi "tin chạy
-- hồ sơ Mặc định" (agent_ho_so_id NULL). Gộp hai thứ ấy là đổ toàn bộ lịch
-- sử cũ vào cột Mặc định — một con số trông thật mà sai.
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS agent_ho_so_id UUID REFERENCES agent_ho_so(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS ho_so_da_ghi BOOLEAN NOT NULL DEFAULT false;

CREATE OR REPLACE FUNCTION ghi_ho_so_agent_cho_tin()
RETURNS trigger AS $$
BEGIN
    IF NEW.role = 'agent' AND NOT NEW.ho_so_da_ghi THEN
        SELECT hs.id INTO NEW.agent_ho_so_id
        FROM conversations c
        JOIN channel_accounts tk ON tk.id = c.account_id
        JOIN agent_ho_so hs ON hs.id = tk.agent_ho_so_id AND hs.bat
        WHERE c.id = NEW.conversation_id;
        NEW.ho_so_da_ghi := true;
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ghi_ho_so_agent_cho_tin ON messages;
CREATE TRIGGER trg_ghi_ho_so_agent_cho_tin
BEFORE INSERT ON messages
FOR EACH ROW EXECUTE FUNCTION ghi_ho_so_agent_cho_tin();
