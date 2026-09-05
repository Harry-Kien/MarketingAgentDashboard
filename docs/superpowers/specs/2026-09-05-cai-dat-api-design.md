# Cài đặt API trên dashboard — thiết kế

Ngày 2026-09-05. Trạng thái: chờ chủ dự án duyệt trước khi lập kế hoạch.

Đợt 1 của ba đợt đã thống nhất: (1) Cài đặt API, (2) Phòng thử agent,
(3) Bảng sức khoẻ từng kênh. Tài liệu này chỉ nói đợt 1.

## 1. Bài toán

Khoá của nhà cung cấp model, ERP và vận chuyển hiện chỉ đọc từ `.env` một
lần lúc khởi động. Người vận hành muốn đổi khoá phải mở file, sửa tay, rồi
khởi động lại; gõ sai một ký tự thì agent im lặng ngừng trả lời. Gemini còn
đòi cài `gcloud` và một dự án GCP trên máy, thứ một cửa hàng mỹ phẩm không
có. Dashboard chưa có chỗ nào để nhập khoá, kiểm khoá, hay biết khoá đang
dùng lấy từ đâu.

Mục tiêu: một mục **Cài đặt API** trong màn Cấu hình, nơi quản trị viên
dán khoá, bấm **Kiểm tra** để biết khoá sống hay chết *trước khi* lưu, và
lưu xong là có hiệu lực ngay, không khởi động lại. Khoá không bao giờ đi
ngược ra trình duyệt.

## 2. Quyết định kiến trúc

Chọn **lớp cấu hình động, khoá mã hoá trong CSDL**:

- Bảng mới `cau_hinh_bi_mat` lưu giá trị đã mã hoá AES-256-GCM bằng chính
  `CredentialVault` đang bảo vệ credential kênh. Không thêm cơ chế mã hoá
  thứ hai.
- Module `agent/cau_hinh_dong.py` là *một* chỗ duy nhất trả lời "giá trị
  của khoá X là gì": CSDL trước, `.env` sau. Mọi chỗ gọi model, ERP, GHN
  đọc qua nó.
- `.env` vẫn là đường lui: máy chưa vào dashboard vẫn chạy được như hôm nay.

Hai cách đã loại: ghi thẳng `.env` từ web rồi tự khởi động lại (rơi tin
đang xử lý, file bị khoá trên Windows), và giữ khoá trong `.env` chỉ thêm
nút kiểm (không đúng yêu cầu nhập khoá).

## 3. Danh mục khoá

Chỉ những khoá trong danh mục dưới được nhập; tên lạ bị từ chối 422, cùng
lý do `sinh_token` chỉ nhận một danh sách trắng.

| Nhóm | Khoá | Bí mật | Ghi chú |
|---|---|---|---|
| Model | `LLM_PROVIDER` | không | `gemini_api` · `gemini` (Vertex) · `anthropic` · `vertex` |
| Model | `GEMINI_API_KEY` | có | Google AI Studio, dùng khi provider `gemini_api` |
| Model | `ANTHROPIC_API_KEY` | có | dùng khi provider `anthropic` |
| Model | `MODEL_CHAT`, `MODEL_HARD`, `MODEL_CHEAP` | không | tên model, phải có trong bảng giá `PRICING` |
| ERP | `ERPNEXT_URL` | không | |
| ERP | `ERPNEXT_API_KEY`, `ERPNEXT_API_SECRET` | có | |
| Vận chuyển | `GHN_TOKEN` | có | |
| Vận chuyển | `GHN_SHOP_ID` | không | |

`ERP_LOAI` và `SHIPPING_PROVIDER` **cố ý** không nằm đây: bật ERP thật có
thứ tự bắt buộc năm bước trong `docs/van-hanh.md`, và `shipping_provider`
rời `mock` là tạo vận đơn không xoá được. Hai công tắc đó vẫn ở `.env`.

Giá trị không bí mật vẫn được mã hoá cùng bảng cho đơn giản, nhưng API trả
về nguyên văn; giá trị bí mật chỉ trả về "đã đặt" và bốn ký tự cuối.

## 4. Thành phần

### 4.1. Lưu trữ và mã hoá

Migration `0013_cau_hinh_bi_mat.sql`:

```
cau_hinh_bi_mat(
  khoa          TEXT PRIMARY KEY,
  key_version   INT NOT NULL,
  nonce         BYTEA NOT NULL,
  ciphertext    BYTEA NOT NULL,
  sua_boi       TEXT NOT NULL,
  sua_luc       TIMESTAMPTZ NOT NULL DEFAULT now(),
  kiem_luc      TIMESTAMPTZ,
  kiem_ket_qua  TEXT
)
```

`CredentialVault` thêm tham số phạm vi: AAD hiện là
`channel-account:<uuid>`; thêm `cau-hinh:<khoa>`. Nhờ AAD khác nhau, một
bản mã của tài khoản kênh không giải mã được thành khoá hệ thống và ngược
lại, dù cùng khoá chủ. Chữ ký `encrypt(payload, account_id=)` giữ nguyên
cho mã cũ; thêm `encrypt_pham_vi(payload, pham_vi)` và
`decrypt_pham_vi(sealed, pham_vi)`.

### 4.2. `agent/cau_hinh_dong.py`

- `DANH_MUC`: bảng ở mục 3, kèm nhãn tiếng Việt, nhóm, cờ bí mật, và với
  `LLM_PROVIDER` danh sách giá trị hợp lệ.
- `async nap()`: gọi một lần trong `lifespan`, giải mã toàn bộ bảng vào bộ
  nhớ tiến trình. Vault chưa cấu hình thì ghi nhật ký cảnh báo và chạy
  bằng `.env`, không chặn khởi động.
- `lay(khoa) -> str`: đồng bộ, đọc bộ nhớ; rỗng thì
  `getattr(settings, khoa.lower(), "")`. Đồng bộ có chủ ý: chỗ gọi nằm sâu
  trong `llm.py`, `erpnext.py`, `ghn.py`, nơi không có `await` tiện tay.
- `nguon(khoa) -> "csdl" | "env" | "trong"`.
- `async dat(khoa, gia_tri, sua_boi)`: kiểm khoá thuộc danh mục và giá
  trị hợp lệ, mã hoá, upsert, cập nhật bộ nhớ, ghi `events`
  kind `cau_hinh_api.doi` với `khoa` và `sua_boi` (không ghi giá trị), rồi
  gọi `llm.xoa_cache_client()` để client Anthropic dựng lại với khoá mới.
- `async xoa(khoa, sua_boi)`: xoá dòng, bộ nhớ lui về `.env`, ghi nhật ký.
- `async ghi_ket_qua_kiem(khoa, ok, chi_tiet)`.

### 4.3. Đường gọi model

`agent/core/llm.py`:

- `provider()` đọc `cau_hinh_dong.lay("LLM_PROVIDER")`. Giá trị mới
  `gemini_api`.
- `_complete_gemini` tách phần URL và header ra `_gemini_dich(model)`:
  Vertex như cũ; `gemini_api` thì
  `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
  với header `x-goog-api-key`. Body, thử lại, đọc kết quả dùng chung. Thiếu
  khoá thì `RuntimeError` nói rõ tên khoá và chỗ nhập.
- `_anthropic_client()` bỏ `lru_cache` trần, cache theo `(provider, khoá)`
  và có `xoa_cache_client()`.
- `kiem_khoa(*, provider, khoa, model, project="") -> (ok, chi_tiet, ms)`:
  gọi một câu 8 token bằng đúng tham số truyền vào, **không** đụng cấu
  hình toàn cục. `suc_khoe._kiem_model` chuyển sang gọi hàm này với giá trị
  hiện hành để không có hai bản kiểm lệch nhau.

`agent/core/rag.py`: khi provider là `gemini_api`, embedding đi qua
`models/gemini-embedding-001:embedContent` của cùng API, với
`outputDimensionality: 768` để khớp cột `vector(768)`. Vector của hai
model không so được với nhau, nên đổi provider embedding là phải nạp lại
kho tri thức: `cau_hinh_dong` ghi `EMBED_MODEL_DANG_DUNG` vào
`cau_hinh_agent` lúc nạp kho, và `suc_khoe` báo đỏ khi giá trị đó khác
model hiện hành. Đây là lưới cho một kiểu hỏng im lặng mới: kho nạp bằng
model A, hỏi bằng model B, kết quả tìm kiếm sai mà không lỗi.

### 4.4. ERP và vận chuyển

- `agent/erp/erpnext.py`: URL, key, secret mặc định lấy từ `cau_hinh_dong`
  thay vì `settings`. Tham số tường minh vẫn thắng, để test và
  `kiem_ket_noi` truyền giá trị chưa lưu.
- `agent/shipping/ghn.py`: tương tự cho token và shop id.
- `agent/erp/kiem_ket_noi.py` nhận thêm `ghi_de: dict | None` để kiểm bằng
  giá trị người vừa nhập.
- GHN có hàm kiểm mới `kiem_ket_noi(token, shop_id)` gọi endpoint thông
  tin shop (chỉ đọc).

### 4.5. API — `agent/api/cai_dat_api.py`, prefix `/api/cai-dat-api`

| Đường | Quyền | Việc |
|---|---|---|
| `GET ""` | đăng nhập | danh sách theo nhóm: khoá, nhãn, bí mật?, đã đặt?, nguồn, đuôi 4 ký tự (bí mật) hoặc giá trị (không bí mật), kiểm lần cuối |
| `PUT /{khoa}` | quản trị | body `{gia_tri}`; 422 khoá lạ hoặc giá trị sai |
| `DELETE /{khoa}` | quản trị | lui về `.env` |
| `POST /kiem-tra` | quản trị | body `{nhom, gia_tri: {khoa: ...}}`; gộp giá trị gửi lên đè lên hiện hành, chạy kiểm, **không lưu**; trả `{ok, chi_tiet, ms}` |

`GET` không có trường nào chứa giá trị bí mật; test khoá điều đó bằng cách
đặt một khoá rồi tìm chuỗi ấy trong toàn bộ phản hồi.

### 4.6. Dashboard

Panel **Cài đặt API** ở đầu màn Cấu hình, ba thẻ: Model, ERP, Vận chuyển.
Mỗi dòng: nhãn, ô nhập (`type="password"` cho bí mật, không bao giờ có
`value` sẵn), trạng thái bên phải ("đã đặt ···abcd · từ CSDL", "đang dùng
.env", "chưa đặt"), kết quả kiểm gần nhất. Mỗi thẻ hai nút: **Kiểm tra**
(dùng giá trị đang gõ, chưa lưu) và **Lưu**. Provider là ô chọn; chọn
`gemini_api` thì ô Gemini API key nổi lên, chọn `anthropic` thì ô
Anthropic. Chỉ quản trị thấy nút Lưu, nhân viên xem được trạng thái.

Không tự kiểm khi mở trang, cùng lý do màn Sức khoẻ không tự chạy: mỗi lần
kiểm là một lượt gọi tốn tiền.

### 4.7. `san_sang`

Mục **Khoá API**: provider hiện hành, khoá lấy từ đâu (CSDL hay `.env`),
CHẶN khi provider cần khoá mà không có ở đâu cả, CẢNH BÁO khi kho tri thức
nạp bằng model embedding khác model hiện hành.

## 5. Luồng dữ liệu

1. Quản trị dán khoá, bấm Kiểm tra → `POST /kiem-tra` → `llm.kiem_khoa`
   với giá trị vừa gõ → kết quả hiện ngay, chưa ghi gì.
2. Bấm Lưu → `PUT /{khoa}` → `cau_hinh_dong.dat` → mã hoá, upsert, cập
   nhật bộ nhớ, xoá cache client, ghi nhật ký → lượt gọi model kế tiếp dùng
   khoá mới.
3. Khởi động lại app → `nap()` nạp lại từ CSDL, không cần `.env` có khoá.

## 6. Xử lý lỗi

- Vault chưa cấu hình: `GET` vẫn trả danh sách với nguồn `env`; `PUT` trả
  503 nói rõ cần `CREDENTIAL_MASTER_KEYS`.
- Khoá chủ đổi và không giải mã được: `nap()` ghi nhật ký
  `cau_hinh_api.giai_ma_hong` kèm tên khoá, bỏ qua khoá đó, lui về `.env`.
  Không nuốt: `san_sang` đọc sự kiện này và báo đỏ.
- Kiểm quá 45 giây: trả `ok=false`, chi tiết "quá hạn", giống `suc_khoe`.
- Mã 429 hoặc "exhaust": chi tiết "HẾT HẠN MỨC", vì đó là lý do phổ biến
  nhất khoá "đúng mà không chạy".

## 7. Kiểm thử

Mỗi ràng buộc một test, không gọi API thật:

- Ưu tiên CSDL trước `.env`, và lui về `.env` khi xoá.
- AAD phạm vi: bản mã tài khoản kênh không giải mã được bằng phạm vi cấu
  hình và ngược lại.
- `GET` không chứa giá trị bí mật (đặt khoá rồi tìm chuỗi trong phản hồi).
- `PUT`/`DELETE`/`kiem-tra` từ chối người không phải quản trị (401/403).
- `kiem-tra` không ghi gì vào bảng.
- Khoá ngoài danh mục và provider ngoài danh sách bị 422.
- `_gemini_dich` cho `gemini_api` ra đúng URL và header, không có
  `Authorization`.
- `dat()` làm `_anthropic_client()` dựng lại.
- `suc_khoe._kiem_model` và `kiem_khoa` là một đường, kiểm bằng
  `inspect.getsource`.
- Dashboard: panel tồn tại, ô bí mật là `type="password"` và không có
  `value=`, có nút Kiểm tra và Lưu, `test_app_js_khong_hong_cu_phap` vẫn
  xanh.
- `san_sang` có mục Khoá API và nằm trong `chay()`.

## 8. Tài liệu và việc đi kèm

- `docs/van-hanh.md`: mục "Nhập khoá API trên dashboard" và thứ tự đổi
  provider (kiểm → lưu → nạp lại kho tri thức nếu đổi embedding).
- `.env.example`: chú thích khoá có thể nhập trên dashboard, `.env` chỉ
  là đường lui.
- Đổi schema nên phải chạy `python -m scripts.sinh_so_do --ghi`.

## 9. Ngoài phạm vi đợt này

Phòng thử agent (đợt 2), bảng sức khoẻ từng kênh (đợt 3), chuyển
`ERP_LOAI` và `SHIPPING_PROVIDER` lên dashboard, khoá Telegram cho canh
gác, xoay khoá chủ vault.
