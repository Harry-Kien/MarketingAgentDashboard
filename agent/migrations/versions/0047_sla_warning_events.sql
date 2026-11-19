-- DEV-07: thêm loại sự kiện cảnh báo sớm SLA (first_response_warning).
--
-- Bản gốc (nhánh Release 1) còn đổi khoá duy nhất sang (conversation_id,
-- kind, due_at). Bỏ phần ấy khi ghép: khoá theo chu kỳ đã có từ 0039
-- (`idx_sla_events_chu_ky` trên conversation_id, chu_ky, kind), và mọi
-- câu INSERT sự kiện SLA đều `ON CONFLICT` theo khoá đó.

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
            'paused',
            'resumed'
        )
    );
