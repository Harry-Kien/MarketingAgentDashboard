-- GAP-07C: một lần Reopen hợp lệ bắt đầu chu kỳ SLA mới.
--
-- Trigger cũ bảo toàn deadline trên mọi UPDATE, kể cả khi hội thoại chuyển
-- từ trạng thái kết thúc sang open. Ngoại lệ dưới đây cố ý hẹp: chỉ đúng
-- chuyển trạng thái resolved/closed -> open mới được cấp lại deadline.
-- Trong cùng chu kỳ open/pending, chốt chống kéo dài SLA vẫn giữ nguyên.

CREATE OR REPLACE FUNCTION prevent_sla_deadline_reset()
RETURNS trigger AS $$
DECLARE
    is_valid_reopen BOOLEAN :=
        OLD.state IN ('resolved', 'closed') AND NEW.state = 'open';
BEGIN
    IF NOT is_valid_reopen THEN
        IF OLD.first_response_due_at IS NOT NULL
           AND NEW.first_response_due_at IS DISTINCT FROM OLD.first_response_due_at THEN
            NEW.first_response_due_at := OLD.first_response_due_at;
        END IF;
        IF OLD.resolution_due_at IS NOT NULL
           AND NEW.resolution_due_at IS DISTINCT FROM OLD.resolution_due_at THEN
            NEW.resolution_due_at := OLD.resolution_due_at;
        END IF;
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;
