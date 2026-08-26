# Routing, SLA, AI Copilot and Human Handover Plan

**Goal:** Phân công hội thoại đa tài khoản có SLA ổn định và khóa cứng việc AI
gửi sau khi người thật tiếp quản.

## Task 1 — Operational conversation state

- Migration 0005 thêm `mode` (`auto|assist|human`), `state`, `priority`, team,
  SLA timestamps, `version` và lịch sử assignment.
- Backfill từ `status`: escalated thành human, assist thành assist, còn lại auto.
- Message mới không reset `assigned_at`, `first_response_due_at` hoặc
  `resolution_due_at`.

## Task 2 — Last-mile outbound authorization

- Trước từng provider call, outbox worker kiểm lại trạng thái conversation.
- Job AI (`message.role=agent`) bị cancel nguyên tử nếu mode human/escalated;
  job `staff` và thông báo hệ thống vẫn được phép.
- Takeover transaction đổi mode, gán người, hủy mọi AI job pending/retry và ghi
  inbox event/audit. Check ở worker xử lý cả race job đã claim.

## Task 3 — Assignment and routing

- Teams, memberships, skills, queue policy, workload cap và round-robin ổn định.
- Manual assign/takeover/release có expected version; mọi đổi gán có actor/reason.
- Auto routing chỉ chọn user có membership trên account và team/skill phù hợp.

## Task 4 — SLA

- Policy theo account/priority: first response và resolution minutes.
- SLA bắt đầu một lần khi conversation được tạo/route; message mới không kéo dài.
- Staff response dừng first-response timer; resolve dừng resolution timer.
- Worker đánh dấu due/breached và tạo event/cảnh báo idempotent.

## Task 5 — AI policy and evaluation

- AI chỉ auto-send khi conversation mode auto tại cả lúc sinh và lúc provider send.
- Assist tạo draft; human không sinh reply. Action hậu quả tiếp tục cần approval.
- Bộ evaluation tiếng Việt khóa grounding, prompt injection, routing, handover,
  tone và multi-turn memory; không coi model fixture là provider proof.

## Gate

- Unit + race fixtures: takeover trước enqueue, sau enqueue, sau claim.
- PostgreSQL integration: concurrent takeover/worker, assignment conflict, SLA không
  reset và audit transaction.
- Provider sandbox xác nhận staff vẫn gửi được sau takeover còn AI bị chặn.
