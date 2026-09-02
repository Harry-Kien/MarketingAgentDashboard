# Kien Omnichannel Customer Care OS

Hệ thống agent chăm sóc khách hàng và marketing đa kênh do Harry-Kien phát
triển cho khóa luận: nhiều tài khoản trên mỗi kênh, một inbox hợp nhất,
Customer 360, SLA, định tuyến nhân viên, AI copilot, phê duyệt và nhật ký kiểm
toán trong cùng một mã nguồn.

## Năng lực chính

- Kết nối nhiều tài khoản Zalo cá nhân, Zalo Official Account, Facebook,
  Instagram, WhatsApp và web chat.
- Hội thoại luôn giữ `account_id`; câu trả lời được gửi lại đúng tài khoản đã
  nhận tin, không cho giao diện tự đổi danh tính gửi.
- Inbox/outbox bền vững, chống webhook trùng, retry/dead-letter, SSE realtime
  và chốt chặn AI khi nhân viên tiếp quản.
- Customer 360 hợp nhất danh tính thận trọng, che PII theo quyền, tag, note,
  consent, merge có preview/version và hoàn tác bằng snapshot.
- Auto-routing theo account membership, team, skill, capacity và round-robin;
  SLA phản hồi/giải quyết có worker breach idempotent.
- Credential của từng tài khoản được mã hóa AES-256-GCM; secret chỉ được nhập,
  không trả lại qua API hoặc DOM.
- AI trả lời có căn cứ, assist/auto/human mode, approval cho hành động có hậu
  quả, đồng thời hỗ trợ RAG, đơn hàng, nội dung và video marketing.

## Kiến trúc

```text
Zalo cá nhân / Zalo OA / Meta / Web chat
                 │ webhook hoặc sidecar HMAC
                 ▼
      Inbox ledger + Identity resolver
                 │
       Conversation + Customer 360
                 │
     Routing / SLA / AI policy / Approval
                 │
        Transactional outbox worker
                 ▼
          Đúng provider account
```

Các ranh giới quan trọng:

- `agent/channels/base.py`: hợp đồng connector.
- `agent/omnichannel/`: account, inbox/outbox, identity, routing, SLA.
- `agent/api/`: API account-scoped và RBAC.
- `dashboard/`: dashboard first-party, không nhúng ứng dụng ngoài.
- `connectors/zalo-personal-sidecar/`: tiến trình cô lập phiên Zalo cá nhân.
- `agent/migrations/versions/`: migration version/checksum/advisory-lock.

Tài liệu chi tiết: `docs/kien-truc.md` và
`docs/superpowers/specs/2026-08-25-omnichannel-native-customer-care-design.md`.

## Chạy local

Yêu cầu: Python 3.12, Node.js 22+, Docker Desktop và FFmpeg.

```powershell
Copy-Item .env.example .env
docker compose up -d db n8n
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn agent.main:app --reload --port 8000
```

Mở `http://localhost:8000`.

Tạo tài khoản quản trị nếu hệ thống chưa có người dùng:

```powershell
.\.venv\Scripts\python.exe -m scripts.tao_tai_khoan admin "mat-khau-manh" --quan-tri
```

## Kho credential

Sinh master key riêng cho từng môi trường:

```powershell
.\.venv\Scripts\python.exe -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Đặt vào `.env`:

```dotenv
CREDENTIAL_MASTER_KEYS=1:<base64-key>
CREDENTIAL_ACTIVE_KEY_VERSION=1
```

Không commit `.env`, không in key/token vào log và phải sao lưu master key ở
kho bí mật khác máy chủ. Mất key đồng nghĩa không thể giải mã credential đã
lưu.

## Kết nối kênh

Trong dashboard, mở **Kết nối → Thêm tài khoản**:

1. Chọn kênh, đặt tên và nhập provider ID nếu đã biết.
2. Nhập credential tương ứng. Zalo OA dùng App ID, Secret Key và refresh
   token; Meta dùng access token, app secret và verify token.
3. Zalo cá nhân bấm **Quét QR**; các kênh khác cấu hình callback URL được hiển
   thị theo từng account.
4. Bấm **Xác minh provider**. Account chỉ chuyển sang **Sẵn sàng** sau probe
   thành công và provider identity đã được bind.
5. Chạy test inbound, outbound và media bằng tài khoản sandbox trước khi mở
   traffic thật.

Zalo cá nhân sidecar:

```powershell
Set-Location connectors\zalo-personal-sidecar
npm ci
npm test
# Sidecar đọc bí mật từ BIẾN MÔI TRƯỜNG, không tự đọc .env. Thiếu bước này
# thì nó thoát ngay với "ZALO_SIDECAR_SECRET phải dài ít nhất 32 ký tự".
$env:ZALO_SIDECAR_SECRET = (Select-String '^ZALO_SIDECAR_SECRET=' ..\..\.env).Line.Split('=',2)[1]
$env:ZALO_CONTROL_PLANE_URL = (Select-String '^ZALO_CONTROL_PLANE_URL=' ..\..\.env).Line.Split('=',2)[1]
npm start
```

Kênh Zalo cá nhân phụ thuộc phiên web không chính thức, vì vậy nên dùng tài
khoản vận hành riêng, có giám sát và phương án chuyển sang OA. Zalo OA và Meta
vẫn cần ứng dụng/quyền được nhà cung cấp phê duyệt.

## Định tuyến và SLA

API quản trị nằm tại `/api/routing`:

- `POST /api/routing/teams`
- `PUT /api/routing/teams/{team_id}/members/{user_id}`
- `POST /api/routing/rules`
- `PUT /api/routing/sla-policies`

Worker chỉ chọn nhân viên vừa thuộc team vừa có membership trên account, đủ
skill và chưa vượt `max_active`. Takeover/release dùng optimistic `version`;
takeover hủy AI job chưa gửi trong cùng transaction/fence.

Yêu cầu export/xóa/retention được tạo ở Customer 360 và quản trị tại
`/api/data-retention/jobs`. Luồng này bắt buộc phê duyệt bốn mắt; endpoint thực
thi hiện chỉ hỗ trợ `execute-dry-run` để kiểm đếm phạm vi, không tự xóa dữ liệu.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check agent tests scripts
node --check dashboard\app.js
Set-Location connectors\zalo-personal-sidecar
npm test
npm audit --audit-level=high
```

Snapshot local gần nhất: 732 test pass, 3 test PostgreSQL integration bị skip do
Docker daemon không khả dụng trong phiên kiểm tra. Con số test xanh không thay
thế cho sandbox provider hoặc nghiệm thu production.

## Gate trước production

- PostgreSQL migration và race test phải chạy trên database thật.
- Từng account phải có health probe xanh và test inbound/outbound/media.
- Meta App Review/Zalo OA permission và callback HTTPS phải hoàn tất.
- Kiểm thử browser desktop/mobile, backup/restore, dead-letter replay và cảnh
  báo worker heartbeat.
- Bắt đầu ở `assist`; chỉ bật `auto` sau evaluation tiếng Việt và canary.

## Tài liệu vận hành

- `docs/dua-vao-doanh-nghiep.md`: checklist triển khai.
- `docs/kien-truc.md`: schema và luồng dữ liệu.
- `docs/superpowers/plans/2026-08-25-omnichannel-native-roadmap.md`: roadmap/gate.
- `THIRD_PARTY_NOTICES.md`: thông tin giấy phép thành phần bên thứ ba.

Không commit, merge hoặc deploy production chỉ dựa trên README; dùng bằng chứng
test, database, provider sandbox và quan sát runtime tương ứng.
