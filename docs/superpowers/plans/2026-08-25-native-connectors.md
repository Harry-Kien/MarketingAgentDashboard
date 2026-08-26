# Native Multi-account Connectors Implementation Plan

**Goal:** Kết nối nhiều Zalo cá nhân, Zalo OA, Facebook Page, Instagram,
WhatsApp Cloud và website chat vào cùng hợp đồng account-aware, không dùng
branding/runtime giao diện của repo tham khảo.

**Nguồn đối chiếu:** Zalo Developers/OpenAPI cho OA; Meta Graph API cho Page,
Instagram Messaging và WhatsApp Cloud; hành vi thực chiến đã được phép tham
khảo từ ZaloCRM/Chatwoot. Không chép giao diện hoặc tên thương hiệu. Thành phần
được tái sử dụng nguyên văn (nếu có) phải giữ LICENSE/NOTICE theo giấy phép.

## Task 1 — Connector contract và credential loading

- Mở rộng `ChannelAdapter` với provider message id, health và account lifecycle.
- Factory giải mã credential đúng `account_id`; account native thiếu credential
  phải fail closed.
- Contract fixtures chứng minh hai account cùng loại không dùng lẫn token.

## Task 2 — Meta connector dùng chung transport, tách parser

- Graph transport account-scoped, timeout/error redaction và appsecret proof.
- Facebook Page, Instagram, WhatsApp parser nhận batch webhook, media và status.
- Webhook fan-out dựa trên Page/IG/phone-number id rồi map tới `channel_accounts`.
- Gửi text/file qua outbox và trả provider message id khi API cung cấp.

## Task 3 — Zalo OA native

- Credential theo OA, token expiry/refresh metadata và health `reauth_required`.
- Parser webhook account-aware, text/media; kiểm chữ ký trước ingest.
- Cửa sổ gửi và API upload/send tách khỏi Zalo cá nhân.

## Task 4 — Zalo Personal sidecar cách ly

- Sidecar Node tối thiểu dùng `zca-js`, một session manager cho mỗi account.
- QR lifecycle có trạng thái rõ, giới hạn refresh, reconnect và device warning.
- Session blob chỉ truyền về vault/control plane; không ghi cookie ra log/git.
- HTTP nội bộ ký HMAC, bind localhost, inbound callback mang `account_id`.

## Task 5 — Webchat first-party

- Widget key theo website/account, visitor id ký, REST history/send và SSE reconnect.
- Anonymous-to-known upgrade không tự merge chỉ bằng tên.
- Attachment upload có size/MIME allowlist và storage key, không nhận đường dẫn tuỳ ý.

## Task 6 — Verification

- Recorded fixtures đã khử bí mật cho inbound/outbound từng connector.
- Unit + PostgreSQL integration + two-account isolation.
- Provider sandbox chỉ đánh dấu PASS sau khi chủ dự án đăng nhập/cấp credential và
  có bằng chứng inbound, outbound, media, reconnect thực.

## Gate

Source/unit không đủ để gọi production-ready. Thiếu QR/OAuth/provider sandbox thì
trạng thái phải là `connector implemented, pending provider verification`.
