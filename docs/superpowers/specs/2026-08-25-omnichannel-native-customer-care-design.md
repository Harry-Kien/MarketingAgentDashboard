# Agent chăm sóc khách hàng đa kênh native — thiết kế

Ngày 2026-08-25. Trạng thái: chờ duyệt trước khi lập kế hoạch triển khai.

## 1. Bài toán

Hệ thống hiện đã có FastAPI, PostgreSQL, dashboard, Agent/RAG, một hợp đồng
`ChannelAdapter`, ZaloCRM, Chatwoot, Messenger và Zalo OA. Tuy nhiên, mỗi
kênh vẫn có cách giữ tài khoản và định danh riêng; Chatwoot và ZaloCRM chạy
như hai sản phẩm bên ngoài. Điều này chưa đáp ứng mục tiêu cuối cùng:

- một mã nguồn và một thương hiệu của dự án;
- nhiều tài khoản trên cùng một kênh;
- một hộp thư và một hồ sơ khách hàng xuyên kênh;
- Agent và nhân viên bàn giao hai chiều nhưng không nói chồng nhau;
- đăng nhập, giám sát và vận hành tất cả kết nối từ cùng dashboard;
- có bằng chứng kiểm thử đủ mạnh cho khóa luận và triển khai thực tế.

## 2. Quyết định kiến trúc

Chọn **native modular monolith**:

- FastAPI hiện tại là control plane, API, inbox, Customer 360 và AI
  orchestration.
- PostgreSQL là nguồn sự thật duy nhất cho tài khoản kênh, danh tính khách,
  hội thoại, tin nhắn, hàng đợi và audit.
- Mỗi nền tảng nằm sau một adapter cùng hợp đồng.
- Zalo cá nhân là một Node sidecar cô lập vì thư viện đăng nhập QR thuộc hệ
  Node; nó không có CSDL nghiệp vụ riêng.
- Zalo OA, Meta và webchat chạy bằng connector Python trong ứng dụng chính.
- Không nhập nguyên ứng dụng Chatwoot hoặc ZaloCRM vào runtime cuối cùng.
  Chỉ tái sử dụng phần mã đã được phép khi cần cho tương thích giao thức;
  giao diện, CSDL và workflow nghiệp vụ được xây native.

Lý do không vendor nguyên hai hệ thống: cách đó tạo ba backend, ba mô hình
người dùng, nhiều CSDL và hai hộp thư cạnh tranh nhau. Nó nhanh ở màn hình
đầu nhưng làm phần đóng góp cá nhân khó chứng minh, dữ liệu khó hợp nhất và
vận hành nặng hơn phạm vi một khóa luận.

## 3. Phạm vi V1

### Kênh

1. Zalo cá nhân — nhiều tài khoản, đăng nhập QR, gửi/nhận chữ và tệp.
2. Zalo Official Account — nhiều OA, token xoay vòng, webhook chính thức.
3. Facebook Messenger — nhiều Page qua Meta OAuth.
4. Instagram Direct — nhiều Instagram Business account qua Meta OAuth.
5. WhatsApp Business — nhiều WABA/số điện thoại qua Meta OAuth.
6. Webchat — nhiều website/widget.

Email, voice/call center, SMS, billing SaaS và multi-tenant thương mại nằm
ngoài V1. Mô hình dữ liệu vẫn có `provider` mở để thêm kênh mà không đổi lõi.

### Chức năng dùng chung

- kết nối, ngắt, làm mới và kiểm tra sức khỏe từng tài khoản;
- inbox hợp nhất, tìm kiếm, bộ lọc theo kênh/tài khoản/trạng thái/nhân viên;
- Customer 360 và liên kết nhiều danh tính với cùng một khách;
- phân công, hàng chờ, SLA, nhãn, ghi chú nội bộ;
- Agent tự động hoặc chế độ trợ lý chờ duyệt;
- chuyển Agent → người → Agent với trạng thái nhìn thấy và audit đầy đủ;
- tệp đính kèm, delivery status, retry và dead-letter;
- retention, xuất/xóa dữ liệu cá nhân và báo cáo hiệu quả.

## 4. Ranh giới thành phần

| Thành phần | Trách nhiệm | Không được làm |
|---|---|---|
| `AccountService` | vòng đời kết nối, capability, health, quyền truy cập | không gửi tin |
| `CredentialVault` | mã hóa token/session, rotation, key version | không trả secret ra API/UI |
| `ChannelGateway` | xác minh webhook, tìm đúng account, chuẩn hóa event | không gọi Agent trực tiếp |
| `InboxService` | lưu hội thoại/tin, chưa đọc, assignment, SLA | không biết payload nhà cung cấp |
| `IdentityService` | contact và contact point đa kênh | không tự hợp nhất khi thiếu căn cứ |
| `RoutingService` | gán đội/người/Agent theo policy | không gửi ra nền tảng |
| `AIOrchestrator` | RAG, tools, policy, confidence, chi phí | không cầm token kênh |
| `HandoverService` | state machine Agent–người | không chỉ đổi cờ nội bộ nếu kênh có handover API |
| `OutboundService` | outbox, thứ tự, retry, delivery | không tự tạo nội dung |
| `ChannelAdapter` | chuyển event và gửi qua đúng provider account | không truy cập bảng nghiệp vụ tùy ý |

Mọi phụ thuộc đi theo chiều:

    Provider -> Gateway -> Inbox/Identity -> Routing -> AI hoặc người
                  ^                                  |
                  |--------- Outbox/Adapter <---------|

Agent không gọi provider trực tiếp. Mọi tin gửi đều đi qua policy, outbox và
adapter để có audit, retry, idempotency và đúng tài khoản nguồn.

## 5. Cấu trúc mã nguồn dự kiến

```text
agent/
  omnichannel/
    accounts.py          vòng đời tài khoản kênh
    credentials.py       mã hóa và rotation
    events.py            ChannelEvent chuẩn
    gateway.py           webhook/poll -> event
    inbox.py             conversation/message
    identity.py          Customer 360
    routing.py           assignment/SLA
    handover.py          state machine Agent–người
    outbox.py            gửi bền vững và retry
    health.py            trạng thái kết nối
  channels/
    base.py              hợp đồng adapter theo account
    zalo_personal.py     client tới sidecar
    zalo_oa.py
    meta.py              Messenger/Instagram/WhatsApp
    webchat.py
  migrations/            migration có phiên bản
services/
  zalo-personal/
    src/                  QR/session/event bridge Node
    package.json
dashboard/
  app.js                  inbox + account connection UI
tests/
  contract/              mọi adapter phải qua cùng hợp đồng
  integration/           PostgreSQL/outbox/identity
  e2e/                   browser + provider sandbox
```

`services/zalo-personal` chỉ giữ kết nối tài khoản cá nhân. Nó không giữ hồ
sơ khách, assignment, AI state hoặc một inbox riêng.

## 6. Mô hình dữ liệu

Thay đổi này phải chuyển repo từ một `schema.sql` lớn sang migration có phiên
bản. `schema.sql` tiếp tục được sinh từ migration để bản clone sạch vẫn dựng
được nhanh; migration là nguồn sự thật khi nâng cấp máy đang có dữ liệu.

### `channel_accounts`

Một dòng là một tài khoản có thể nhận/gửi tin.

```text
id UUID PK
provider TEXT                 zalo_personal | zalo_oa | meta | webchat
channel_type TEXT             zalo | messenger | instagram | whatsapp | web
external_account_id TEXT
display_name TEXT
auth_method TEXT              qr | oauth | token | widget
status TEXT                   connecting | active | degraded | expired | disabled
capabilities JSONB            text, image, file, typing, handover, window
credential_id UUID
token_expires_at TIMESTAMPTZ
last_seen_at TIMESTAMPTZ
last_error_code TEXT
metadata JSONB
created_by UUID
created_at, updated_at
UNIQUE(provider, external_account_id)
```

Không dùng biến `.env` riêng cho từng tài khoản. `.env` chỉ giữ master key và
client/app credential dùng chung; token/session từng account nằm trong vault.

### `credential_secrets`

```text
id UUID PK
ciphertext BYTEA
nonce BYTEA
key_version INT
secret_type TEXT
rotated_at TIMESTAMPTZ
created_at, updated_at
```

Mã hóa AES-256-GCM; khóa chủ chỉ đến từ secret store hoặc biến môi trường,
không nằm trong CSDL, log, backup plaintext hay API response.

### Customer 360

`contacts` là con người/doanh nghiệp logic; `contact_points` là danh tính của
họ ở một tài khoản/kênh.

```text
contacts(id, display_name, phone, email, consent, profile, first_seen, last_seen)
contact_points(id, contact_id, channel_account_id, external_user_id,
               handle, verified_fields, metadata, first_seen, last_seen)
UNIQUE(channel_account_id, external_user_id)
```

Không tự hợp nhất chỉ vì tên giống nhau. Hợp nhất khi có số điện thoại/email
đã xác minh hoặc nhân viên duyệt. Mọi merge có lịch sử và có thể hoàn tác.

### Hội thoại và tin nhắn

`conversations` được nâng cấp:

- bắt buộc `channel_account_id` và `contact_id`;
- unique `(channel_account_id, external_id)` thay vì `(channel, external_id)`;
- có `assigned_user_id`, `assigned_team`, `mode`, `state`, `priority`,
  `sla_due_at`, `version` để khóa cạnh tranh;
- giữ `channel`/`nen_tang` trong giai đoạn migration rồi sinh từ account.

`messages` được nâng cấp:

- `external_message_id`, `direction`, `sender_type`, `sender_ref`;
- `status`: pending | queued | sent | delivered | read | failed;
- `idempotency_key`, `reply_to_id`, `provider_timestamp`, `raw_metadata`;
- unique `(channel_account_id, external_message_id)` khi provider có id.

Tệp chuyển khỏi JSONB sang `attachments`:

```text
attachments(id, message_id, kind, object_key, source_url, mime_type,
            size_bytes, sha256, scan_status, metadata, created_at)
```

### Độ bền và audit

- `webhook_deliveries`: request id, account, chữ ký hợp lệ, trạng thái parse.
- `outbox_jobs`: aggregate key, payload, attempt, next_attempt, locked_at,
  dead_letter_at.
- `conversation_assignments`: lịch sử gán/người nhận việc.
- `contact_merges`: nguồn, đích, người duyệt, dữ liệu hoàn tác.
- `account_health_events`: token hết hạn, mất session, rate limit, webhook lỗi.
- `events` hiện có tiếp tục là audit cấp nghiệp vụ.

## 7. Luồng kết nối nhiều tài khoản

### Zalo cá nhân

1. Quản trị chọn “Thêm Zalo cá nhân”.
2. Backend tạo `connection_session` dùng một lần, hết hạn ngắn.
3. Node sidecar tạo QR; dashboard nhận trạng thái qua SSE/WebSocket đã xác thực.
4. Người dùng quét QR; sidecar trả profile và session đã mã hóa về backend.
5. Backend tạo `channel_account`, lưu secret trong vault và chạy health probe.
6. Mỗi account có hàng đợi tuần tự riêng; lỗi/mất session của account A không
   chặn account B.
7. Khi session chết, account chuyển `expired`, dừng gửi, cảnh báo và yêu cầu
   quét lại; không tự báo thành công.

Zalo cá nhân là connector rủi ro cao: có kill switch riêng, rate limit bảo thủ,
không dùng làm nguồn dữ liệu duy nhất và luôn hiển thị đường chuyển sang OA.

### Zalo OA

1. Quản trị bắt đầu OAuth với `state` một lần và callback cố định.
2. Backend đổi code lấy token, truy vấn OA profile và tạo account.
3. Refresh token xoay vòng được cập nhật transactionally trong vault.
4. Webhook tìm account bằng OA/app identity, không dùng một account cấu hình
   toàn cục.
5. Ngoài cửa sổ nhắn tự do, OutboundService chặn và yêu cầu template phù hợp.

### Meta

1. Quản trị đăng nhập Meta OAuth.
2. Backend liệt kê Page, Instagram Business account, WABA và số điện thoại mà
   người đó có quyền quản lý.
3. Người dùng chọn một hoặc nhiều tài sản; mỗi tài sản tạo một account riêng.
4. Backend subscribe webhook và kiểm tra quyền cần thiết.
5. Webhook được định tuyến theo Page/IG/WABA id; reply luôn dùng token/account
   của hội thoại gốc.

Messenger, Instagram và WhatsApp dùng chung `MetaAdapter` cho OAuth, webhook,
retry và error parsing nhưng giữ capability/cửa sổ gửi riêng.

### Webchat

Mỗi website là một `channel_account`. Widget dùng public site id và handshake
ngắn hạn; server cấp conversation token ký, giới hạn origin và rate limit.
Secret quản trị không bao giờ nằm trong JavaScript công khai.

## 8. Luồng tin nhắn

### Tin đến

1. Provider gửi webhook hoặc sidecar phát event.
2. Gateway xác minh HMAC/token/timestamp trước khi parse.
3. Xác định `channel_account_id`; không tìm được thì ghi dead-letter, không
   đoán account mặc định.
4. Tạo `ChannelEvent` chuẩn và idempotency key.
5. Trong một transaction: chống trùng, upsert contact point, conversation,
   message và tạo job routing.
6. Routing kiểm tra trạng thái handover, assignment, giờ làm việc và policy.
7. Agent hoặc nhân viên xử lý; mọi output đi vào outbox.

### Tin đi

1. Outbox khóa job bằng `FOR UPDATE SKIP LOCKED`.
2. Nạp conversation và account, kiểm capability/cửa sổ gửi/token.
3. Adapter gửi với idempotency/client message id nếu provider hỗ trợ.
4. Cập nhật delivery status và audit.
5. Lỗi tạm thời retry exponential backoff có jitter; lỗi quyền/token chuyển
   account `degraded/expired`; lỗi vĩnh viễn vào dead-letter và báo người trực.

Thứ tự được bảo toàn theo conversation/account. Hệ thống chấp nhận delivery
at-least-once nhưng hiệu ứng nghiệp vụ exactly-once bằng idempotency.

## 9. State machine Agent–người

```text
auto_active
  -> pending_approval       Agent soạn, chờ duyệt
  -> waiting_human          Agent yêu cầu người
  -> human_active           nhân viên nhận việc
  -> resolved               đóng việc
  -> auto_active            khách nhắn lại hoặc người trả Agent
```

Quy tắc bắt buộc:

- một conversation chỉ có một speaker owner tại một thời điểm;
- chuyển trạng thái dùng `version`/compare-and-swap để hai request không cùng
  giành quyền;
- tin tới khi `human_active` vẫn được lưu nhưng Agent không trả lời;
- kênh có handover API phải hoàn tất cả trạng thái provider và trạng thái nội
  bộ; một bên thất bại thì hiển thị degraded, không báo thành công giả;
- release chỉ về Agent sau khi policy và cửa sổ gửi còn hợp lệ.

## 10. Agent AI và an toàn

Giữ vòng lặp RAG/tools và năm lớp lưới hiện có. Bổ sung context:

- contact/customer profile;
- account, channel capability và cửa sổ gửi;
- assignment/handover state;
- consent và policy riêng của account/brand.

Agent không được:

- tự chọn account khác để né lỗi gửi;
- gọi provider trực tiếp;
- hợp nhất contact;
- công khai bí mật;
- gửi ngoài cửa sổ bằng cách đổi timestamp;
- trả lời khi speaker owner là người.

Các hành động gây hậu quả như tạo đơn, xóa dữ liệu, đăng bài hoặc gửi template
chủ động tiếp tục qua approval/policy code, không chỉ prompt.

## 11. Dashboard

### Trang Kết nối

- nhóm theo provider, hiển thị nhiều account;
- nút thêm bằng QR/OAuth/widget;
- trạng thái active/degraded/expired/disabled, lần thấy cuối và lỗi có thể xử lý;
- reconnect, disable, rotate và xóa kết nối có xác nhận;
- không hiển thị token/session.

### Inbox hợp nhất

- cột trái: tìm kiếm và bộ lọc kênh/account/nhân viên/trạng thái;
- cột giữa: danh sách conversation, badge kênh + tên account;
- cột phải: timeline tin nhắn, hồ sơ Customer 360, assignment, mode và composer;
- reply composer khóa account nguồn, không cho đổi account tùy tiện;
- lỗi gửi/đang retry/dead-letter nhìn thấy ngay trên từng message.

### Quản trị

- account permissions và nhóm nhân viên;
- policy Agent theo account;
- audit, health, SLA và thống kê containment/handoff/delivery;
- merge Customer 360 có preview và undo.

Responsive ưu tiên desktop 1366px cho vận hành, nhưng các thao tác đọc/trả lời
cơ bản phải dùng được ở 360px.

## 12. Xác thực, quyền và bảo mật

Vai trò V1:

- `quan_tri`: kết nối account, policy, người dùng, xóa dữ liệu;
- `giam_sat`: xem mọi account được cấp, phân công, audit và báo cáo;
- `nhan_vien`: xử lý conversation của account/đội được cấp;
- `chi_xem`: xem báo cáo đã giảm dữ liệu nhạy cảm.

Thêm `channel_account_members` để một người chỉ thấy account được cấp. Mọi API
conversation kiểm quyền server-side; lọc UI không phải authorization.

Chốt bảo mật:

- OAuth state một lần, PKCE khi provider hỗ trợ;
- HMAC + timestamp + replay cache cho webhook;
- credential AES-GCM và key rotation;
- cookie HttpOnly/SameSite/Secure ở production, CSRF cho mutation;
- rate limit login, webhook và widget;
- tệp kiểm magic bytes, kích thước, hash và malware scan trước khi phục vụ;
- URL tải tệp ngắn hạn hoặc route có xác thực;
- log redact token/cookie/authorization/header và PII không cần thiết;
- backup được mã hóa và có bài test restore.

## 13. Quan sát và xử lý lỗi

Không có lỗi quan trọng nào chỉ được nuốt:

- dashboard health theo từng account;
- metric: inbound lag, outbound latency, retry, dead-letter, token expiry,
  handoff duration, containment, delivery success;
- event có `account_id`, `conversation_id`, `provider_request_id` và error code;
- alert chỉ nổ khi trạng thái đổi để tránh mệt mỏi cảnh báo;
- circuit breaker theo account, không theo toàn provider;
- dead-letter có nút retry sau khi sửa nguyên nhân.

## 14. Triển khai

V1 chạy trên một máy nhưng giữ ranh giới có thể tách sau:

```text
reverse proxy HTTPS
  -> FastAPI + dashboard + Python workers
  -> Zalo personal Node sidecar
  -> PostgreSQL/pgvector
  -> object storage (local private hoặc S3-compatible)
```

PostgreSQL outbox thay Redis cho job cốt lõi để giảm một thành phần bắt buộc.
n8n vẫn là nhánh marketing/publishing, không nằm trên đường nhận tin CSKH.
Langfuse vẫn tùy chọn; số liệu vận hành cốt lõi nằm trong CSDL dự án.

## 15. Migration và cắt chuyển

Không xóa submodule ngay. Chuyển theo strangler pattern:

1. Thêm migration runner, account registry và account-aware adapter contract.
2. Backfill account mặc định cho conversation hiện có.
3. Chuyển Messenger/Zalo OA hiện có sang account registry.
4. Xây Zalo personal sidecar và chạy shadow read song song với ZaloCRM.
5. Xây Meta multi-account và webchat native.
6. Hoàn thiện inbox/Customer 360/assignment native.
7. Chạy parity suite và canary từng account.
8. Ngắt đường proxy/Chatwoot/ZaloCRM, giữ rollback một chu kỳ.
9. Chỉ khi acceptance pass mới xóa submodule và compose cũ.

Rollback ở mỗi lát là đổi routing của account về adapter cũ; migration chỉ thêm
bảng/cột trước, chưa drop dữ liệu cho tới sau thời gian ổn định.

## 16. Kiểm thử và tiêu chí nghiệm thu

### Tự động

- unit test parser, HMAC, token rotation, window và error mapping;
- adapter contract test áp cho mọi provider/account;
- PostgreSQL integration test thật cho migration, unique, lock, outbox và RBAC;
- property test chống trùng/reorder payload;
- browser E2E cho kết nối account, inbox, assignment, handover và lỗi gửi;
- clean-clone test không có dữ liệu/secret;
- secret scan, dependency audit và static check;
- migration upgrade/rollback trên bản sao dữ liệu.

### Kịch bản bắt buộc

1. Hai account cùng provider nhận tin đồng thời nhưng không lẫn token/hội thoại.
2. Reply đi đúng account nguồn trong 100% fixture và sandbox cases.
3. Webhook gửi lại không tạo tin/đơn/handoff trùng.
4. Restart app/worker không mất QR session đã lưu hoặc outbox đang chờ.
5. Token xoay vòng và token hết hạn cho trạng thái đúng, không chết câm.
6. Tin chỉ có ảnh/file vẫn tạo conversation và hiển thị được.
7. Khi người nhận việc, Agent không gửi thêm; khi release, Agent chỉ nói sau
   khi trạng thái cả hai phía hợp lệ.
8. Account A rate-limit hoặc mất kết nối không chặn account B.
9. Nhân viên không được đọc/gửi qua account chưa được cấp.
10. Yêu cầu xóa dữ liệu loại bỏ contact, contact point, tin và tệp theo policy.

### Mục tiêu kỹ thuật V1

- không mất tin trong test restart/retry;
- idempotency không sinh bản ghi nghiệp vụ trùng;
- p95 từ webhook đã nhận tới khi lưu DB dưới 1 giây trong tải kiểm thử local;
- p95 tạo outbound job dưới 500 ms; thời gian provider nằm ngoài SLO nội bộ;
- mọi lỗi gửi có trạng thái và nguyên nhân nhìn thấy;
- không secret nào xuất hiện trong API, log, test artifact hay Git;
- desktop và mobile browser smoke đều pass;
- sandbox E2E pass cho từng API chính thức; Zalo cá nhân cần bài test account
  riêng và được ghi rõ là connector rủi ro.

Không được tuyên bố production-ready chỉ vì test fixture xanh. Cần bằng chứng
provider thật/sandbox, restart, canary, backup-restore và quan sát ít nhất một
chu kỳ vận hành.

## 17. Lát triển khai

### Lát 1 — nền dữ liệu và account-aware contract

Migration runner, `channel_accounts`, vault, contact/contact point, outbox,
adapter contract mới và backfill không đổi hành vi người dùng.

### Lát 2 — Zalo cá nhân native

Node sidecar, QR flow, multi-session, message/file bridge, health và dashboard
kết nối; shadow/parity trước khi cắt ZaloCRM.

### Lát 3 — Zalo OA và Meta multi-account

OAuth/token rotation, asset picker, webhook account routing, window/capability
và contract/E2E sandbox.

### Lát 4 — webchat và unified inbox

Widget, Customer 360, assignment, SLA, composer đúng account và attachment.

### Lát 5 — AI/handover/operations

Policy theo account, state machine, RBAC, audit/metrics, dead-letter, backup và
browser E2E.

### Lát 6 — cutover

Canary, migration dữ liệu, rollback rehearsal, gỡ proxy/submodule/compose cũ và
cập nhật toàn bộ tài liệu khóa luận.

Mỗi lát có TDD, review và verification riêng; không gộp tất cả vào một commit
khổng lồ hoặc báo “hoàn thiện” trước lát 6.

## 18. Rủi ro đã chấp nhận

- Zalo cá nhân phụ thuộc giao thức không chính thức và có thể mất phiên hoặc
  thay đổi bất ngờ; cô lập sidecar và OA-first giảm phạm vi thiệt hại.
- Meta/Zalo OA cần app review/quyền thật; fixture không thay được nghiệm thu.
- Hợp nhất Customer 360 sai nguy hiểm hơn để tách, nên auto-merge bảo thủ.
- Nhiều account làm rò token chéo trở thành lỗi P0; mọi cache/client phải key
  theo `channel_account_id` và có cross-account tests.
- Một máy vẫn là single point of failure; V1 phải có backup/restore, còn HA là
  giai đoạn sau khóa luận.

## 19. Kết luận thiết kế

Thiết kế này biến repo hiện tại thành sản phẩm CSKH đa kênh độc lập mà không
vứt bỏ phần Agent/RAG/dashboard đã có. Nền tảng mới sở hữu account registry,
inbox, Customer 360, routing và audit; provider chỉ còn là adapter thay thế
được. Thành công được đo bằng đúng-account routing, không mất/trùng tin,
handover an toàn, bảo mật credential và E2E thật — không đo bằng số lượng file
đã sao chép từ hai repo tham khảo.
