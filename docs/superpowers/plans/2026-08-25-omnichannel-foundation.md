# Omnichannel Account-Aware Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tạo nền tảng account-aware an toàn để hệ thống quản lý nhiều tài khoản trên cùng một kênh và luôn nhận/gửi tin bằng đúng tài khoản nguồn.

**Architecture:** Giữ FastAPI modular monolith hiện tại, thêm migration runner tiến về phía trước, domain `channel_accounts`, credential vault AES-GCM và registry resolve adapter theo `(channel, account_id)`. Adapter cũ tiếp tục chạy qua một account legacy được backfill, giúp chuyển đổi từng bước mà không làm gián đoạn hành vi đang có.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, asyncpg/PostgreSQL, `cryptography` AESGCM, pytest, Ruff.

**Spec:** `docs/superpowers/specs/2026-08-25-omnichannel-native-customer-care-design.md`

## Global Constraints

- Không in hoặc trả giá trị credential; API chỉ trả `has_credentials`, thời điểm cập nhật và health summary.
- `account_id` là UUID nội bộ, không dùng Page ID/OA ID/Zalo UID làm khóa chính.
- `external_account_id` chỉ unique trong một provider; `external conversation id` chỉ unique trong một account.
- Mọi SQL mutation quan trọng chạy trong transaction; migration có checksum và không được sửa nội dung sau khi đã áp dụng.
- Registry không được fallback im lặng sang tài khoản mặc định khi caller đã cung cấp `account_id` sai.
- Không stage/commit; cuối mỗi task dùng diff checkpoint theo quy định repo.

---

### Task 1: Migration runner có version và checksum

**Status (2026-08-25):** Completed — focused tests, full suite và Ruff đều xanh.

**Files:**
- Create: `agent/migrations/__init__.py`
- Create: `agent/migrations/runner.py`
- Create: `agent/migrations/versions/0001_account_aware_foundation.sql`
- Modify: `agent/db.py`
- Test: `tests/test_migrations.py`

- [x] **Step 1: Viết test thất bại cho discovery, thứ tự và checksum**

```python
def test_discover_migrations_sorted(tmp_path):
    (tmp_path / "0002_second.sql").write_text("SELECT 2", encoding="utf-8")
    (tmp_path / "0001_first.sql").write_text("SELECT 1", encoding="utf-8")

    migrations = discover_migrations(tmp_path)

    assert [m.version for m in migrations] == ["0001", "0002"]
    assert all(len(m.checksum) == 64 for m in migrations)


def test_duplicate_version_is_rejected(tmp_path):
    (tmp_path / "0001_a.sql").write_text("SELECT 1", encoding="utf-8")
    (tmp_path / "0001_b.sql").write_text("SELECT 2", encoding="utf-8")

    with pytest.raises(MigrationError, match="trùng phiên bản"):
        discover_migrations(tmp_path)
```

- [x] **Step 2: Chạy test để xác nhận đỏ đúng lý do**

Run: `python -m pytest tests/test_migrations.py -q`

Expected: FAIL vì `agent.migrations.runner` chưa tồn tại.

- [x] **Step 3: Cài đặt model/discovery thuần Python nhỏ nhất**

```python
@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    path: Path
    checksum: str


def discover_migrations(directory: Path = VERSIONS_DIR) -> list[Migration]:
    found: list[Migration] = []
    versions: set[str] = set()
    for path in sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql")):
        version, name = path.stem.split("_", 1)
        if version in versions:
            raise MigrationError(f"trùng phiên bản migration: {version}")
        versions.add(version)
        content = path.read_bytes()
        found.append(Migration(version, name, path, hashlib.sha256(content).hexdigest()))
    return found
```

- [x] **Step 4: Viết test thất bại cho apply transaction, idempotency và checksum drift**

Test bằng fake async connection ghi lại `execute`, `fetch` và transaction context; xác nhận:

```python
await apply_migrations(conn, [migration])
await apply_migrations(conn, [migration])
assert fake.applied_sql.count("SELECT 1") == 1

fake.applied["0001"] = "checksum-khac"
with pytest.raises(MigrationError, match="checksum"):
    await apply_migrations(fake, [migration])
```

- [x] **Step 5: Cài đặt bảng `schema_migrations` và apply trong transaction**

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`apply_migrations()` phải khóa advisory trong transaction, đọc phiên bản đã áp dụng, chặn checksum drift, chạy SQL và ghi lịch sử cùng transaction.

- [x] **Step 6: Gọi migration runner sau baseline schema trong `init_db()`**

```python
from agent.migrations.runner import apply_all

async with _pool.acquire() as conn:
    await conn.execute(schema)
    await apply_all(conn)
```

- [x] **Step 7: Chạy test và checkpoint**

Run: `python -m pytest tests/test_migrations.py tests/test_dich_vu_khoi_dong_duoc.py -q`

Expected: PASS.

Run: `python -m ruff check agent/migrations agent/db.py tests/test_migrations.py`

Expected: PASS.

Run: `git diff --check; git status --short`

Expected: không có whitespace error; chỉ hiện file trong phạm vi task cùng các file untracked có sẵn.

---

### Task 2: Schema account-aware nền tảng

**Status (2026-08-25):** Implementation complete; PostgreSQL integration gate đang bị chặn vì Docker Desktop service không mở được trong quyền Windows hiện tại. Contract tests xanh, integration test giữ trạng thái SKIP rõ lý do.

**Files:**
- Modify: `agent/migrations/versions/0001_account_aware_foundation.sql`
- Create: `tests/test_account_schema.py`

- [ ] **Step 1: Viết contract test thất bại cho migration SQL**

```python
def test_foundation_migration_contains_required_tables():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    for table in (
        "channel_accounts",
        "credential_secrets",
        "account_memberships",
        "account_health_events",
    ):
        assert f"create table if not exists {table}" in sql


def test_conversation_identity_is_account_scoped():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "account_id uuid" in sql
    assert "unique (account_id, external_id)" in sql
```

- [ ] **Step 2: Chạy test để xác nhận đỏ**

Run: `python -m pytest tests/test_account_schema.py -q`

Expected: FAIL vì migration chưa chứa schema nghiệp vụ.

- [ ] **Step 3: Thêm schema và constraints đầy đủ**

Migration phải tạo:

```sql
CREATE TABLE IF NOT EXISTS channel_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    channel TEXT NOT NULL,
    display_name TEXT NOT NULL,
    external_account_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    capabilities JSONB NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}',
    is_legacy BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('pending','active','degraded','reauth_required','disabled')),
    UNIQUE NULLS NOT DISTINCT (channel, external_account_id)
);

CREATE TABLE IF NOT EXISTS credential_secrets (
    account_id UUID PRIMARY KEY REFERENCES channel_accounts(id) ON DELETE CASCADE,
    key_version INT NOT NULL,
    nonce BYTEA NOT NULL,
    ciphertext BYTEA NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Đồng thời tạo membership/health tables, thêm nullable `conversations.account_id`, backfill bằng legacy account theo `channel`, đổi unique cũ sang `(account_id, external_id)`, rồi đặt `account_id NOT NULL`. Migration phải xử lý database trống và database đã có dữ liệu.

- [ ] **Step 4: Thêm test integration PostgreSQL có điều kiện**

Nếu `TEST_DATABASE_URL` tồn tại, test tạo schema tạm, chạy baseline + migration hai lần và xác nhận:

```python
assert await conn.fetchval("SELECT count(*) FROM channel_accounts WHERE is_legacy") >= 1
assert await conn.fetchval("SELECT count(*) FROM conversations WHERE account_id IS NULL") == 0
```

Nếu biến môi trường không tồn tại, mark `pytest.skip` với lý do rõ ràng; không báo PASS giả cho integration DB.

- [ ] **Step 5: Chạy test và checkpoint**

Run: `python -m pytest tests/test_account_schema.py tests/test_migrations.py -q`

Expected: PASS, integration DB chỉ SKIP khi chưa có `TEST_DATABASE_URL`.

Run: `python -m ruff check tests/test_account_schema.py`

Expected: PASS.

---

### Task 3: Domain model và credential vault AES-GCM

**Status (2026-08-25):** Completed — round-trip, AAD isolation, tamper detection và key rotation tests đều xanh.

**Files:**
- Create: `agent/omnichannel/__init__.py`
- Create: `agent/omnichannel/accounts.py`
- Create: `agent/security/__init__.py`
- Create: `agent/security/credential_vault.py`
- Modify: `agent/config.py`
- Modify: `.env.example`
- Modify: `requirements.txt`
- Test: `tests/test_channel_accounts.py`
- Test: `tests/test_credential_vault.py`

- [ ] **Step 1: Viết test đỏ cho enum/model account**

```python
def test_channel_account_public_view_never_contains_secret():
    account = ChannelAccount(
        id=uuid4(), channel=Channel.ZALO_OA, display_name="OA Hà Nội",
        external_account_id="oa-1", status=AccountStatus.ACTIVE,
        capabilities={"send_text": True}, metadata={}, is_legacy=False,
    )
    public = account.to_public(has_credentials=True)
    assert public["has_credentials"] is True
    assert "credentials" not in public
    assert "token" not in json.dumps(public).lower()
```

- [ ] **Step 2: Cài đặt enum/model immutable đủ cho repository và API**

`Channel` gồm `zalo_personal`, `zalo_oa`, `facebook`, `instagram`, `whatsapp`, `webchat`; status theo constraint schema. Validation từ chuỗi lạ phải thất bại rõ ràng.

- [ ] **Step 3: Viết test đỏ cho vault**

```python
def test_encrypt_decrypt_round_trip():
    vault = CredentialVault({1: bytes.fromhex("00" * 32)}, active_version=1)
    sealed = vault.encrypt({"access_token": "secret", "refresh_token": "rotate"})
    assert vault.decrypt(sealed) == {
        "access_token": "secret", "refresh_token": "rotate"
    }
    assert b"secret" not in sealed.ciphertext


def test_ciphertext_is_bound_to_account_id():
    sealed = vault.encrypt({"token": "secret"}, account_id=account_a)
    with pytest.raises(InvalidCredentialCiphertext):
        vault.decrypt(sealed, account_id=account_b)
```

- [ ] **Step 4: Thêm dependency và cấu hình master key có version**

Thêm `cryptography` với phiên bản chính xác đã cài/kiểm thử. `.env.example` chỉ hướng dẫn `CREDENTIAL_MASTER_KEYS=1:<base64-32-bytes>` và `CREDENTIAL_ACTIVE_KEY_VERSION=1`, không chứa key dùng thật. `agent/config.py` không log giá trị.

- [ ] **Step 5: Cài đặt AESGCM với nonce 96-bit và AAD theo account**

```python
nonce = os.urandom(12)
aad = f"channel-account:{account_id}".encode("utf-8")
ciphertext = AESGCM(key).encrypt(nonce, canonical_json, aad)
```

Decrypt phải phân biệt key version không tồn tại, ciphertext sai và JSON sai; mọi lỗi public dùng thông báo an toàn không kèm dữ liệu đầu vào.

- [ ] **Step 6: Chạy test và checkpoint**

Run: `python -m pytest tests/test_channel_accounts.py tests/test_credential_vault.py -q`

Expected: PASS.

Run: `python -m ruff check agent/omnichannel agent/security agent/config.py tests/test_channel_accounts.py tests/test_credential_vault.py`

Expected: PASS.

---

### Task 4: Repository/service quản trị nhiều tài khoản

**Status (2026-08-25):** Completed — atomic create/secret/audit, RBAC và disable-send gate đã kiểm.

**Files:**
- Create: `agent/omnichannel/account_repository.py`
- Create: `agent/omnichannel/account_service.py`
- Test: `tests/test_account_service.py`

- [ ] **Step 1: Viết test đỏ cho create/list/disable và che bí mật**

Fake repository/vault phải chứng minh:

```python
created = await service.create_account(command, actor=admin)
assert created.channel == Channel.ZALO_OA
assert await repo.has_credentials(created.id) is True
assert "access_token" not in repr(created)

await service.disable_account(created.id, actor=admin)
with pytest.raises(AccountDisabled):
    await service.require_sendable(created.id)
```

- [ ] **Step 2: Viết test đỏ cho uniqueness và permission**

```python
with pytest.raises(AccountAlreadyExists):
    await service.create_account(same_external_account, actor=admin)

with pytest.raises(AccountPermissionDenied):
    await service.rotate_credentials(account_id, payload, actor=staff_without_membership)
```

- [ ] **Step 3: Cài đặt repository bằng SQL parameterized**

Repository cung cấp `create`, `get`, `list_for_user`, `update_status`, `store_credentials`, `has_credentials`, `record_health`. Không truyền raw credential qua `channel_accounts.metadata`.

- [ ] **Step 4: Cài đặt service transaction boundary và audit**

Service validate capability/channel, mã hóa trước khi lưu, rollback account nếu lưu secret thất bại, ghi event chỉ với `account_id`, channel, actor và loại thao tác.

- [ ] **Step 5: Chạy test và checkpoint**

Run: `python -m pytest tests/test_account_service.py -q`

Expected: PASS.

Run: `python -m ruff check agent/omnichannel tests/test_account_service.py`

Expected: PASS.

---

### Task 5: API quản trị account với RBAC và response an toàn

**Status (2026-08-25):** Completed — auth, admin mutation, staff filtering, health và no-secret-echo tests xanh.

**Files:**
- Create: `agent/api/channel_accounts.py`
- Modify: `agent/main.py`
- Modify: `agent/api/routes.py`
- Test: `tests/test_channel_accounts_api.py`

- [ ] **Step 1: Viết API test đỏ cho auth và response schema**

```python
def test_list_accounts_requires_login(client):
    assert client.get("/api/channel-accounts").status_code == 401


def test_admin_can_create_without_secret_echo(admin_client):
    response = admin_client.post("/api/channel-accounts", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["has_credentials"] is True
    assert "credentials" not in body
    assert "access_token" not in response.text
```

- [ ] **Step 2: Viết test đỏ cho staff membership filtering**

Nhân viên chỉ thấy account được gán; quản trị thấy tất cả. Tạo/rotate credential/disable chỉ cho quản trị.

- [ ] **Step 3: Cài đặt router và Pydantic models**

Endpoints tối thiểu:

```text
GET    /api/channel-accounts
POST   /api/channel-accounts
GET    /api/channel-accounts/{account_id}
PUT    /api/channel-accounts/{account_id}/credentials
POST   /api/channel-accounts/{account_id}/disable
POST   /api/channel-accounts/{account_id}/enable
GET    /api/channel-accounts/{account_id}/health
```

Không dùng model chứa credential làm response model. Validation error không echo giá trị secret.

- [ ] **Step 4: Đăng ký router sau auth bootstrap và giữ compatibility route cũ**

Route `/api/zalo/accounts` cũ vẫn tồn tại trong slice này; thêm deprecation header hoặc adapter response sau khi API mới ổn định, không xóa đột ngột.

- [ ] **Step 5: Chạy test và checkpoint**

Run: `python -m pytest tests/test_channel_accounts_api.py tests/test_xac_thuc.py -q`

Expected: PASS.

Run: `python -m ruff check agent/api/channel_accounts.py agent/main.py agent/api/routes.py tests/test_channel_accounts_api.py`

Expected: PASS.

---

### Task 6: Account-aware channel contract và registry

**Status (2026-08-25):** Completed cho compatibility layer — account ID bắt buộc, UUID legacy ổn định và strict factory fail-closed. Connector native đa tài khoản vẫn thuộc Slice 3.

**Files:**
- Modify: `agent/channels/base.py`
- Modify: `agent/channels/registry.py`
- Create: `agent/channels/factory.py`
- Test: `tests/test_account_aware_channels.py`
- Modify: `tests/test_messenger.py`
- Modify: `tests/test_zalo_oa.py`

- [ ] **Step 1: Viết test đỏ cho inbound bắt buộc có account**

```python
def test_inbound_message_requires_account_id():
    with pytest.raises(TypeError):
        InboundMessage(
            channel="facebook", conversation_ref="c1", customer_ref="u1",
            customer_name="An", text="Chào", dedupe_key="m1",
            received_at=datetime.now(timezone.utc),
        )
```

- [ ] **Step 2: Viết test đỏ cho registry strict account routing**

```python
adapter = await registry.get_for_account(account_a.id)
await adapter.send_text("conversation-1", "Xin chào")
assert factory.last_credentials_account_id == account_a.id

with pytest.raises(AccountAdapterNotFound):
    await registry.get_for_account(uuid4())
```

- [ ] **Step 3: Mở rộng `InboundMessage` và outbound context**

Thêm `account_id: UUID`; attachments sửa annotation thành `list[dict]` để khớp hành vi hiện tại. Thêm `OutboundContext(account_id, conversation_ref, idempotency_key)` và phương thức account-aware mới. Compatibility wrapper chỉ dùng khi conversation legacy đã được backfill thành account cụ thể.

- [ ] **Step 4: Thêm adapter factory theo account, không singleton theo channel**

Cache key là `account_id`; cache entry chứa account `updated_at` hoặc credential version để invalidate khi rotate. Tài khoản disabled/reauth-required không tạo adapter sendable. Không fallback sang `zalocrm` khi ID sai.

- [ ] **Step 5: Cập nhật fixture adapter hiện có**

Tests Messenger/Zalo OA truyền UUID account fixture và tiếp tục chứng minh batch parsing, signature, window rule. Provider token trong settings chỉ còn compatibility path cho legacy account ở slice này.

- [ ] **Step 6: Chạy test và checkpoint**

Run: `python -m pytest tests/test_account_aware_channels.py tests/test_messenger.py tests/test_zalo_oa.py -q`

Expected: PASS.

Run: `python -m ruff check agent/channels tests/test_account_aware_channels.py tests/test_messenger.py tests/test_zalo_oa.py`

Expected: PASS.

---

### Task 7: Khóa định tuyến conversation về đúng account nguồn

**Status (2026-08-25):** Completed — ingest, reply và send-window đều account-scoped; focused regression xanh.

**Files:**
- Modify: `agent/main.py`
- Modify: `agent/api/routes.py`
- Modify: `agent/channels/base.py`
- Test: `tests/test_account_routing.py`

- [ ] **Step 1: Viết test đỏ cho hai account có cùng external conversation ID**

```python
first = await ingest(inbound(account_id=account_a, conversation_ref="same"))
second = await ingest(inbound(account_id=account_b, conversation_ref="same"))

assert first.conversation_id != second.conversation_id
assert first.account_id == account_a
assert second.account_id == account_b
```

- [ ] **Step 2: Viết test đỏ cho reply exact-account**

```python
await reply(conversation_from_account_b.id, "Đã nhận ạ")

factory.assert_sent_once(
    account_id=account_b,
    conversation_ref="same",
    text="Đã nhận ạ",
)
```

Ca âm: conversation thiếu/invalid account, account disabled hoặc channel mismatch phải fail closed và ghi audit; tuyệt đối không gọi default adapter.

- [ ] **Step 3: Sửa ingest query account-scoped**

```sql
INSERT INTO conversations (account_id, channel, external_id, customer_name, customer_ref)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (account_id, external_id)
DO UPDATE SET customer_name = EXCLUDED.customer_name, updated_at = now()
RETURNING *;
```

- [ ] **Step 4: Sửa mọi đường outbound resolve từ `conversation.account_id`**

Áp dụng cho trả lời agent, staff reply, approve draft, send file, typing indicator và handover notification. Request từ dashboard không được tự truyền account tùy ý để ghi đè nguồn conversation.

- [ ] **Step 5: Chạy tập test hồi quy trọng điểm**

Run: `python -m pytest tests/test_account_routing.py tests/test_ban_giao.py tests/test_ban_giao_messenger.py tests/test_anh_khach_gui.py -q`

Expected: PASS.

Run: `python -m ruff check agent/main.py agent/api/routes.py agent/channels/base.py tests/test_account_routing.py`

Expected: PASS.

---

### Task 8: Foundation verification và cập nhật tài liệu vận hành

**Status (2026-08-25):** Local gate completed (`614 passed, 3 skipped`, Ruff/compileall/diff check xanh); PostgreSQL integration và provider/production vẫn chưa được xác minh.

**Files:**
- Modify: `README.md`
- Modify: `docs/kien-truc.md`
- Modify: `docs/dua-vao-doanh-nghiep.md`
- Modify: `scripts/san_sang.py`
- Test: `tests/test_san_sang.py`
- Test: `tests/test_tai_lieu.py`

- [ ] **Step 1: Viết readiness test đỏ cho master key và account health**

Readiness phải trả `CHẶN` khi có credential rows mà master key version tương ứng không tải được; trả `CẢNH BÁO` khi account active nhưng health stale; không bao giờ in key/token/ciphertext.

- [ ] **Step 2: Cập nhật readiness implementation và tài liệu**

README mô tả cách sinh key cục bộ, tạo account qua API/UI và trạng thái bằng chứng. Kiến trúc ghi rõ account routing invariant. Tài liệu doanh nghiệp có key rotation, revoke account, backup/restore secret rows và cách xử lý `reauth_required`.

- [ ] **Step 3: Chạy focused suite**

Run: `python -m pytest tests/test_migrations.py tests/test_account_schema.py tests/test_channel_accounts.py tests/test_credential_vault.py tests/test_account_service.py tests/test_channel_accounts_api.py tests/test_account_aware_channels.py tests/test_account_routing.py tests/test_san_sang.py tests/test_tai_lieu.py -q`

Expected: PASS; DB integration chỉ SKIP có lý do khi chưa cấp `TEST_DATABASE_URL`.

- [ ] **Step 4: Chạy full static/test verification**

Run: `python -m pytest -q`

Expected: PASS.

Run: `python -m ruff check .`

Expected: PASS.

Run: `python -m compileall -q agent scripts`

Expected: exit code 0.

- [ ] **Step 5: Kiểm bí mật và diff**

Run: `git diff --check`

Expected: PASS.

Run: `rg -n --hidden -g '!\.git/**' -g '!\.env' '(access_token|refresh_token|app_secret|credential_master_keys)\s*[=:]\s*[^<{\[]'`

Expected: không phát hiện giá trị bí mật thật trong file được theo dõi; mọi hit mẫu được rà soát thủ công.

Run: `git status --short`

Expected: không có file ngoài phạm vi bị sửa; `.serena/` vẫn nguyên trạng.

- [ ] **Step 6: Ghi báo cáo gate trung thực**

Báo cáo riêng:

```text
Local unit/static: PASS/FAIL
PostgreSQL integration: PASS/SKIPPED/FAIL
Provider sandbox: NOT IN SCOPE FOR SLICE 1
Production: NOT VERIFIED
```

Slice 1 chỉ hoàn tất khi local suite xanh và DB integration xanh trên một PostgreSQL thật. Nếu chưa có DB integration, trạng thái là “implementation complete, pending DB verification”, không gọi production-ready.
