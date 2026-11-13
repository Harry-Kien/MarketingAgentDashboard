-- GAP-07B: giữ invariant giữa Resolve và thao tác tạo/mở lại Pending Action.
--
-- Resolve khoá dòng conversations FOR UPDATE trước khi kiểm tra cong_viec.
-- Trigger này lấy FOR KEY SHARE trên cùng dòng trước khi một task trở thành
-- moi/dang_lam. Hai thao tác vì vậy được tuần tự hóa ở CSDL:
--   * task commit trước -> Resolve nhìn thấy task và từ chối;
--   * Resolve commit trước -> task nhìn thấy Conversation đã kết thúc và từ chối.

CREATE OR REPLACE FUNCTION guard_open_task_on_finished_conversation()
RETURNS trigger AS $$
DECLARE
    conversation_state TEXT;
BEGIN
    IF NEW.conversation_id IS NULL
       OR NEW.trang_thai NOT IN ('moi', 'dang_lam') THEN
        RETURN NEW;
    END IF;

    SELECT state INTO conversation_state
    FROM conversations
    WHERE id = NEW.conversation_id
    FOR KEY SHARE;

    IF conversation_state IN ('resolved', 'closed') THEN
        RAISE EXCEPTION
            'không thể tạo hoặc mở lại công việc trên hội thoại đã kết thúc'
            USING ERRCODE = '23514',
                  CONSTRAINT = 'cong_viec_open_requires_active_conversation';
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_guard_open_task_insert ON cong_viec;
CREATE TRIGGER trg_guard_open_task_insert
BEFORE INSERT ON cong_viec
FOR EACH ROW EXECUTE FUNCTION guard_open_task_on_finished_conversation();

DROP TRIGGER IF EXISTS trg_guard_open_task_update ON cong_viec;
CREATE TRIGGER trg_guard_open_task_update
BEFORE UPDATE OF conversation_id, trang_thai ON cong_viec
FOR EACH ROW EXECUTE FUNCTION guard_open_task_on_finished_conversation();
