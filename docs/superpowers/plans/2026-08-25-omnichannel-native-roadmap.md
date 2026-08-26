# Omnichannel Native Customer Care Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển repo MarketingAgentDashboard thành hệ thống chăm sóc khách hàng đa kênh native, hỗ trợ nhiều tài khoản trên mỗi kênh, một hộp thư chung, Customer 360 và AI-human handover có thể kiểm chứng.

**Architecture:** Modular monolith FastAPI + PostgreSQL là control plane và nguồn dữ liệu chuẩn. Mỗi kết nối kênh là một `channel_account`; mọi webhook, hội thoại, tin nhắn và lần gửi đều mang `account_id`. Zalo cá nhân dùng Node sidecar cách ly giao thức; Zalo OA, Meta và webchat dùng connector native. Việc thay thế ZaloCRM/Chatwoot đi theo strangler pattern và chỉ bỏ runtime cũ sau khi đạt parity cùng canary.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, PostgreSQL/pgvector, pytest, Ruff, HTML/CSS/JavaScript hiện có; Node.js sidecar cho Zalo cá nhân; Meta Graph API, Zalo OA API và WebSocket/webhook cho webchat.

**Spec:** `docs/superpowers/specs/2026-08-25-omnichannel-native-customer-care-design.md`

## Global Constraints

- Toàn bộ giao diện, tài liệu, tên nghiệp vụ và thông báo lỗi dùng tiếng Việt rõ nghĩa.
- Không ghi token, refresh token, app secret, cookie đăng nhập hoặc nội dung bí mật vào log, API response hay git.
- Không stage hoặc commit khi chưa có yêu cầu rõ ràng của chủ repo; mỗi mốc “checkpoint” thay cho commit bằng `git diff --check`, test tập trung và rà soát `git status --short`.
- Không xóa submodule ZaloCRM/Chatwoot trước khi connector native đạt parity, có dữ liệu chuyển đổi và canary thành công.
- Mọi invariant quan trọng phải có test: tenant/account isolation, reply đúng tài khoản nguồn, idempotency, outbox không mất tin, webhook signature, RBAC và handover.
- Không tuyên bố production-ready chỉ dựa vào unit test; phải tách bằng chứng local, integration, sandbox/provider và production.
- Migrations chỉ tiến về phía trước, có version, chạy trong transaction và an toàn khi chạy lại.
- TDD là bắt buộc cho từng task: test thất bại có lý do đúng trước khi thêm implementation.

---

## Slice Plans

### Slice 1 — Nền tảng account-aware và credential vault

**Detailed plan:** `docs/superpowers/plans/2026-08-25-omnichannel-foundation.md`

- [x] Thêm migration runner có version và bảng lịch sử migration.
- [x] Thêm `channel_accounts`, `credential_secrets`, `account_memberships` và audit/health nền tảng.
- [x] Thêm `account_id` vào hợp đồng inbound/outbound và registry account-aware, vẫn tương thích adapter cũ trong giai đoạn chuyển tiếp.
- [x] Thêm credential vault AES-GCM và chốt không lộ bí mật.
- [x] Thêm repository/service/API quản trị nhiều tài khoản cùng RBAC.
- [x] Backfill tài khoản legacy và khóa định tuyến hội thoại về đúng tài khoản nguồn.

**Gate:** API tạo/liệt kê/khóa tài khoản chạy được; bí mật chỉ trả trạng thái; cùng một `external_id` ở hai tài khoản không đụng nhau; reply luôn mang đúng `account_id`.

### Slice 2 — Inbox native, webhook ledger và transactional outbox

- [x] Viết kế hoạch chi tiết riêng trước khi sửa mã.
- [x] Chuẩn hóa `contacts`, `contact_points`, `conversations`, `messages`, `attachments` theo account-aware model.
- [x] Thêm `webhook_deliveries` với raw-body hash, chữ ký, idempotency key và trạng thái xử lý.
- [x] Thêm `outbox_jobs` với claim bằng `FOR UPDATE SKIP LOCKED`, retry có backoff, dead-letter và audit.
- [x] Xây `InboxService` cho ingest, list/filter, send, assign, close/reopen và unread counters.
- [x] Thêm realtime event stream cho dashboard và recovery khi reconnect.

**Gate:** cùng webhook gửi lại không nhân đôi; crash giữa ghi DB và gửi provider không mất job; message timeline giữ đúng thứ tự provider; một inbox lọc được theo kênh, tài khoản, trạng thái và người phụ trách.

### Slice 3 — Connector native đa tài khoản

- [x] Viết kế hoạch chi tiết riêng và đối chiếu tài liệu API chính thức mới nhất.
- [ ] Zalo Personal sidecar: QR session lifecycle, encrypted session storage, health/reconnect, send/receive media, device approval warning.
- [ ] Zalo OA: OAuth/token rotation theo từng OA, webhook signature, send window/template rules và health diagnostics.
- [ ] Meta: một app kết nối nhiều Page/Instagram/WhatsApp account, webhook fan-out theo account, token expiry và permission diagnostics.
- [ ] Webchat: widget key theo website, anonymous-to-known identity upgrade, websocket reconnect và attachment upload.
- [ ] Contract tests dùng recorded fixtures đã khử bí mật; sandbox smoke cho từng provider khi chủ repo đăng nhập/cấp credential.

**Gate:** mỗi loại kênh có ít nhất hai account giả lập độc lập; sandbox thật chứng minh inbound + outbound + attachment + reconnect; không có đường gửi nhầm account.

### Slice 4 — Customer 360 và định danh hợp nhất

- [x] Viết kế hoạch chi tiết riêng trước khi sửa mã.
- [x] Xây contact profile và contact points theo provider/account.
- [x] Matching chắc chắn bằng external identity; matching gợi ý bằng số điện thoại/email đã chuẩn hóa.
- [x] Human-approved merge, unmerge có audit và không làm mất lịch sử.
- [x] Timeline hợp nhất, tags, notes, consent/opt-out và retention workflow
  có phê duyệt bốn mắt; thực thi xóa thật vẫn bị khóa sau gate pháp lý/vận hành.

**Gate:** không auto-merge chỉ dựa trên tên; merge/unmerge giữ nguyên mọi conversation; quyền xem PII được kiểm theo role và account membership.

### Slice 5 — Routing, SLA, AI copilot và human handover

- [x] Viết kế hoạch chi tiết riêng trước khi sửa mã.
- [x] Assignment queues, skills, workload và SLA timers.
- [ ] State machine `auto -> assist -> escalated -> human -> resolved/closed` có guard rõ ràng.
- [x] AI suggestion có confidence, citations, action policy và approval gate cho hành động hậu quả.
- [ ] Handover package gồm lý do, tóm tắt, dữ kiện khách, việc đã làm và việc cần người xử lý.
- [ ] Evaluation suite tiếng Việt cho grounding, routing, tool safety, tone và multi-turn memory.

**Gate:** bot dừng gửi ngay khi human takeover; mọi action hậu quả cần policy/approval; SLA và assignment không bị reset bởi message mới; audit truy được ai/AI đã làm gì.

### Slice 6 — Dashboard vận hành, migration parity và release hardening

- [x] Viết kế hoạch chi tiết riêng và dùng frontend-design cho phần tái thiết kế UI.
- [ ] Connections center đa tài khoản, QR/OAuth flows, health và reconnect actions. (UI/QR/health xong; OAuth chính thức chờ app credential.)
- [x] Unified Inbox, source badges và exact-account reply khóa theo conversation.
- [ ] Customer 360, team/SLA views, audit/dead-letter/health admin views.
- [ ] Dual-write/read-compare hoặc import có kiểm đếm từ ZaloCRM/Chatwoot; parity report.
- [ ] Canary, backup/restore drill, load test, security scan, runbook và rollback drill.
- [ ] Chỉ sau release gate mới gỡ proxy iframe/runtime/submodule legacy và cập nhật NOTICE/source attribution.

**Gate:** browser smoke trên desktop/mobile; accessibility cơ bản; migration count/hash khớp; canary không rơi/nhân đôi tin; rollback diễn tập thành công; readiness report phân biệt rõ local/sandbox/production.

## Cross-Slice Acceptance Matrix

| Invariant | Unit | Integration DB | Browser | Provider sandbox | Production canary |
|---|---:|---:|---:|---:|---:|
| Reply đúng tài khoản nguồn | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc |
| Webhook idempotency | Bắt buộc | Bắt buộc | Không áp dụng | Bắt buộc | Quan sát |
| Outbox không mất tin | Bắt buộc | Bắt buộc | Không áp dụng | Bắt buộc | Quan sát |
| Bí mật không lộ | Bắt buộc | Bắt buộc | Bắt buộc | Rà soát | Rà soát |
| Handover dừng bot | Bắt buộc | Bắt buộc | Bắt buộc | Khuyến nghị | Bắt buộc |
| Nhiều account cùng kênh | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc | Bắt buộc |
| Customer merge an toàn | Bắt buộc | Bắt buộc | Bắt buộc | Không áp dụng | Kiểm mẫu |

## Completion Rule

Roadmap chỉ được đánh dấu hoàn tất khi cả sáu slice đạt gate riêng, full test + Ruff + build/smoke đều qua, provider sandbox có bằng chứng thật cho các tài khoản đã đăng nhập, và production canary/rollback có log kiểm chứng. Nếu chưa có credential hoặc môi trường production, kết quả phải ghi đúng là “foundation/integration complete, pending provider or production verification”, không gọi là hệ thống production-ready.
