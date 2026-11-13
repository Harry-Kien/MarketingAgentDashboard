-- DEV-07: Bo sung loai su kien canh bao som SLA (first_response_warning)
-- va doi rang buoc duy nhat theo tung chu ky SLA (conversation_id, kind, due_at)
-- de ho tro Reopen (DEV-01) van giu lich su canh bao / vi pham cua chu ky cu.

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

ALTER TABLE sla_events
    DROP CONSTRAINT IF EXISTS sla_events_conversation_id_kind_key;

ALTER TABLE sla_events
    ADD CONSTRAINT sla_events_conversation_kind_due_key
    UNIQUE NULLS NOT DISTINCT (conversation_id, kind, due_at);
