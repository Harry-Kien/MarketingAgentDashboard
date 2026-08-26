# Native Dashboard and Hardening Plan

**Goal:** Một dashboard sở hữu hoàn toàn trong repo này cho unified inbox,
multi-account connections, Customer 360, SLA và vận hành; không hiển thị thương
hiệu/giao diện của hệ thống tham khảo.

## Task 1 — Native unified inbox

- Chuyển màn Hội thoại sang `/api/inbox`: account/channel/status/assignee filter,
  unread, stable cursor và SSE `Last-Event-ID`.
- Detail hiển thị account nguồn, delivery state, attachment, SLA, mode, assignee.
- Composer gửi staff qua outbox; takeover/release dùng expected version.

## Task 2 — Connections center

- Thay iframe/tên repo tham khảo bằng card tài khoản native: Zalo cá nhân, Zalo
  OA, Facebook, Instagram, WhatsApp và Webchat.
- Mỗi card có nhiều account, health/status, add/disable/reauth; secret chỉ nhập,
  không bao giờ render lại.
- Zalo cá nhân có QR lifecycle; official channels có hướng dẫn callback URL và
  trạng thái `pending provider verification` tới khi test thật.

## Task 3 — Customer 360 and team/SLA views

- Thêm danh sách/detail Customer 360 với contact points, timeline, tag/note,
  consent, merge preview/undo và PII mask.
- Hàng đợi ưu tiên SLA breach/due, team/assignee và mode rõ ràng.
- Admin view cho outbox dead-letter, account health và retention approvals.

## Task 4 — Rebrand and accessibility

- Xóa tên/sản phẩm demo và tên repo tham khảo khỏi UI chính; dùng nhận diện
  `Kien Omnichannel` có thể đổi bằng cấu hình sau.
- Keyboard/focus, reduced motion, responsive 360px, empty/error/loading state,
  không dùng màu là tín hiệu duy nhất.

## Task 5 — Verification and release evidence

- JS syntax, source tests, full Python suite, dependency/secret/license scan.
- Browser desktop/mobile smoke: login, inbox, takeover, staff send, contacts,
  connections và error state.
- PostgreSQL migration test, provider sandbox, restart/backup/restore và canary là
  gate riêng; thiếu gate nào phải ghi rõ, không gắn nhãn production-ready.
