# Omnichannel Native Inbox and Outbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây lõi inbox native không rơi/nhân đôi tin, ghi nhận webhook có kiểm chứng và đưa mọi outbound qua transactional outbox có retry/dead-letter.

**Architecture:** FastAPI tiếp tục là control plane. Inbound đi qua `WebhookLedger -> InboxService` trong transaction; outbound tạo message + outbox job cùng transaction, worker claim bằng `FOR UPDATE SKIP LOCKED`, gửi qua adapter account-aware rồi cập nhật delivery state. JSON attachments cũ được giữ tương thích trong lúc thêm bảng attachments chuẩn hóa.

**Tech Stack:** Python 3.12, FastAPI, asyncpg/PostgreSQL, pytest, Ruff, SHA-256/HMAC verification hiện có.

**Spec:** `docs/superpowers/specs/2026-08-25-omnichannel-native-customer-care-design.md`

## Global Constraints

- Không gọi provider trong transaction PostgreSQL.
- Không đánh dấu webhook `processed` trước khi conversation/message đã được commit.
- Cùng `(account_id, dedupe_key)` chỉ tạo tối đa một inbound message.
- Cùng `(account_id, idempotency_key)` chỉ tạo tối đa một outbound job.
- Worker crash sau khi provider nhận nhưng trước khi DB cập nhật phải retry bằng cùng provider/client idempotency key nếu provider hỗ trợ; nếu không hỗ trợ phải audit rủi ro duplicate.
- Dead-letter không tự biến mất; cần API xem, retry có quyền và audit.
- Payload/log/error không chứa credential hoặc raw webhook vượt quá retention đã định.
- Không stage/commit nếu chưa có yêu cầu riêng; dùng test/diff checkpoint.

---

### Task 1: Migration 0002 cho webhook ledger, outbox và delivery state

**Files:**
- Create: `agent/migrations/versions/0002_native_inbox_outbox.sql`
- Test: `tests/test_inbox_outbox_schema.py`
- Modify: `scripts/sinh_so_do.py`
- Generated: `docs/kien-truc.md`

- [ ] Viết test đỏ cho các bảng `webhook_deliveries`, `outbox_jobs`, `attachments` và account-scoped unique constraints.
- [ ] Thêm cột message delivery/provider identity an toàn, backfill direction/state từ `role`/`delivered` hiện có.
- [ ] Thêm indexes claim queue, timeline và dead-letter.
- [ ] Chạy contract tests; chạy integration PostgreSQL nếu `TEST_DATABASE_URL` có.
- [ ] Sinh lại kiến trúc và chạy `tests/test_so_do.py`.

### Task 2: Webhook ledger service idempotent

**Files:**
- Create: `agent/omnichannel/webhook_ledger.py`
- Test: `tests/test_webhook_ledger.py`

- [ ] Viết test đỏ: nhận lần đầu, nhận lại cùng key, signature invalid, processing failed rồi retry.
- [ ] Cài model/repository interface không lưu raw secret; chỉ lưu hash, metadata đã lọc và trạng thái.
- [ ] Cài PostgreSQL repository với insert-on-conflict và state transitions có guard.
- [ ] Chạy focused tests và Ruff.

### Task 3: InboxService ingest account-aware trong một transaction

**Files:**
- Create: `agent/omnichannel/inbox_service.py`
- Modify: `agent/main.py`
- Test: `tests/test_inbox_service.py`
- Modify: `tests/test_account_routing.py`

- [ ] Viết test đỏ: duplicate không nhân message, hai account không nhập hội thoại, attachment được chuẩn hóa, standby chỉ lưu không reply.
- [ ] Cài repository transaction: claim ledger, upsert conversation, insert message/attachments, mark processed.
- [ ] Giữ `handle_inbound` orchestration AI bên ngoài transaction và dùng kết quả ingest đã commit.
- [ ] Chạy focused regression cho Messenger/Zalo OA/Chatwoot.

### Task 4: Transactional outbox repository và worker

**Files:**
- Create: `agent/omnichannel/outbox.py`
- Create: `agent/workers/outbox_worker.py`
- Create: `agent/workers/__init__.py`
- Modify: `agent/main.py`
- Test: `tests/test_outbox.py`

- [ ] Viết test đỏ cho enqueue idempotent, claim không trùng, success, retry backoff, max-attempt dead-letter và stale-lock recovery.
- [ ] Cài repository API và state machine thuần domain trước.
- [ ] Cài PostgreSQL claim bằng `FOR UPDATE SKIP LOCKED`.
- [ ] Cài worker resolve exact account adapter, không log payload credential, và ghi provider result.
- [ ] Gắn worker vào lifespan với shutdown có kiểm soát.

### Task 5: Chuyển mọi đường outbound UI/AI sang enqueue

**Files:**
- Modify: `agent/api/routes.py`
- Modify: `agent/main.py`
- Test: `tests/test_outbound_enqueue.py`
- Modify: `tests/test_account_routing.py`

- [ ] Viết test đỏ cho staff send, approve draft, AI auto reply, file send và handover notice cùng transaction với message.
- [ ] Thay direct provider call bằng enqueue; API trả `queued` + job ID, không báo delivered trước worker.
- [ ] Giữ compatibility synchronous path sau feature flag chỉ cho rollback, mặc định outbox.
- [ ] Chạy regression ban giao/ảnh/assist/auto.

### Task 6: Inbox query, filters, unread và realtime event stream

**Files:**
- Create: `agent/api/inbox.py`
- Modify: `agent/main.py`
- Test: `tests/test_inbox_api.py`

- [ ] Viết test đỏ cho filter account/channel/status/assignee, cursor pagination ổn định và unread count.
- [ ] Cài API list/detail/mark-read trên account membership scope.
- [ ] Cài SSE stream bằng sequence cursor; reconnect nhận phần còn thiếu, không duplicate.
- [ ] Không thay dashboard lớn trong slice này; chỉ cung cấp contract cho Slice 6.

### Task 7: Dead-letter operations và verification

**Files:**
- Create: `agent/api/outbox.py`
- Modify: `scripts/san_sang.py`
- Modify: `README.md`
- Modify: `docs/dua-vao-doanh-nghiep.md`
- Test: `tests/test_outbox_api.py`
- Modify: `tests/test_san_sang.py`

- [ ] Viết test đỏ cho admin-only list/retry/cancel dead-letter và audit.
- [ ] Readiness cảnh báo pending quá hạn, chặn khi worker không heartbeat nhưng queue tăng.
- [ ] Tài liệu hóa retry/dead-letter/runbook và trạng thái delivery.
- [ ] Chạy focused suite, full pytest, Ruff, compileall, diff/secret scan.
- [ ] Chạy PostgreSQL integration; nếu môi trường vẫn thiếu, ghi đúng `pending DB verification` và không đóng slice gate.

## Acceptance Gate

```text
Local unit/static: bắt buộc PASS
PostgreSQL integration: bắt buộc PASS để đóng Slice 2
Provider sandbox: chứng minh ít nhất một inbound + outbound retry khi có credential
Production: chưa thuộc Slice 2, phải ghi NOT VERIFIED
```

Không đánh dấu Slice 2 hoàn tất nếu chỉ có source-contract test. Outbox chỉ đáng tin khi đã chạy transaction/claim/recovery trên PostgreSQL thật.
