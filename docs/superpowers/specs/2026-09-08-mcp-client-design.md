# Máy chủ MCP làm nguồn công cụ — bản thiết kế

Ngày: 08.09.2026 · Đợt 3b trong lộ trình kỹ năng · Trạng thái: đã duyệt phương án A

## 1. Mục tiêu

Người vận hành nối được một **máy chủ MCP** (Model Context Protocol) bên
ngoài từ dashboard, và công cụ của máy chủ đó xuất hiện cho agent **đúng
như một plugin**: qua cùng cửa `run_tool`, cùng trần 12 plugin, cùng số đo
`cong_cu.goi`, cùng sandbox Phòng thử, cùng lưới an toàn. Không có đường
nào cho một công cụ ngoài đi vòng qua các chốt của `agent/core/agent.py`.

Không làm trong đợt này: stdio (tiến trình con), OAuth, resources/prompts
của MCP, sampling ngược từ máy chủ về mô hình, kho chia sẻ máy chủ.

## 2. Vì sao chọn phương án A

Ba phương án đã cân nhắc:

- **A — máy chủ MCP là một nguồn công cụ ngang hàng plugin** (chọn). Mỗi
  công cụ MCP được ghi thành một dòng `ky_nang_cai_dat` với `loai="mcp"`.
  Mọi thứ đã có — trần, chốt tắt, sandbox, số đo, dashboard — áp dụng
  nguyên xi.
- **B — mỗi máy chủ là một gói kỹ năng tự sinh.** Ít mã hơn, nhưng gói là
  dữ liệu tĩnh có phiên bản còn công cụ MCP đổi theo máy chủ; trộn hai thứ
  là phá khái niệm gói.
- **C — gọi thẳng máy chủ MCP trong vòng lặp công cụ của `respond()`.**
  Nhanh nhất, và đi vòng qua đúng những chốt mà CLAUDE.md nói không được đi
  vòng.

## 3. Ranh giới an toàn (ràng buộc trong MÃ, có test canh)

1. **Chỉ Streamable HTTP.** Không stdio: stdio là chạy một tiến trình tuỳ ý
   trên máy chủ, tức biến kỹ năng từ DỮ LIỆU thành MÃ.
2. **Rào host, chỉ sửa được từ `.env`.** Địa chỉ máy chủ phải qua
   `mcp_khach.kiem_dia_chi()`:
   - `http`/`https`; host công khai phải nằm trong `KY_NANG_HOST_CHO_PHEP`
     và phân giải DNS ra địa chỉ công khai (dùng lại luật của
     `agent/ky_nang/mang.py`);
   - host nội bộ (`127.0.0.1`, `localhost`, `::1`) chỉ được phép khi cặp
     `host:cổng` nằm đúng trong biến mới `MCP_MAY_CHU_NOI_BO` (danh sách
     cách nhau bằng dấu phẩy, ví dụ `127.0.0.1:8765`). Dải riêng khác
     (10/8, 192.168/16…) không bao giờ được phép.
   - Cả hai biến cố ý không sửa được từ dashboard, cùng lý do với
     `KY_NANG_HOST_CHO_PHEP`: chiếm một tài khoản quản trị không được đồng
     nghĩa với chiếm đường ra mạng.
3. **Bí mật không rời máy chủ.** Header xác thực (ví dụ `Authorization`) lưu
   mã hoá bằng `CredentialVault.encrypt_pham_vi(payload, pham_vi=f"mcp:{ten}")`
   trong cột nonce/ciphertext/key_version của bảng `mcp_may_chu` (cùng kiểu
   `cau_hinh_bi_mat`). API chỉ trả về `co_bi_mat: true/false`.
4. **Mặc định mọi công cụ MCP là ĐỌC.** Quản trị đánh dấu từng công cụ là
   GHI (`ghi=true`). Công cụ GHI:
   - trong sandbox Phòng thử: KHÔNG gọi máy chủ, trả về bản mô phỏng
     `{"thu_nghiem": true, "mo_phong": true, "cong_cu": <ten>, "tham_so": args,
     "ghi_chu": "Phòng thử: công cụ ghi của máy chủ MCP không được gọi thật."}`;
   - ngoài sandbox: chỉ chạy khi `ghi_cho_phep=true` (quản trị bật rõ từng
     công cụ); chưa bật thì trả về "chuyển người" như mọi công cụ đang tắt.
   - Không có công cụ MCP nào gửi tin cho khách, chốt đơn hay đăng bài:
     những việc đó vẫn chỉ đi qua công cụ viết sẵn.
5. **Kết quả từ máy chủ là nguồn không tin cậy.** Văn bản trả về bị cắt ở
   `KET_QUA_TOI_DA = 8000` ký tự, rồi qua `phong_thu.quet()`. Có dấu hiệu
   ra lệnh thì không đưa cho mô hình: trả `{"loi", "can_chuyen_nhan_vien":
   true, "dau_hieu": [...]}` và ghi sự kiện `bao_mat.mcp_injection` (kèm tên
   máy chủ, công cụ, trích 200 ký tự). Mô tả công cụ lấy từ máy chủ đi qua
   đúng bộ kiểm `doc_ban_mo_ta` (độ dài 20–600, quét injection); công cụ nào
   không qua được thì bị bỏ và ghi lý do vào kết quả đồng bộ, không làm
   hỏng cả máy chủ.
6. **Giới hạn cứng.** `MCP_MAY_CHU_TOI_DA = 5` máy chủ; mỗi lần đồng bộ
   nhận tối đa `CONG_CU_MOI_MAY_CHU_TOI_DA = 20` công cụ (dư thì bỏ, báo);
   công cụ MCP đang bật tính vào trần `PLUGIN_TOI_DA = 12`; kết nối
   `HAN_KET_NOI_GIAY = 5`, mỗi lời gọi `HAN_GOI_GIAY = 10`; thân yêu cầu
   gửi đi tối đa 16 KB. Không thử lại: lỗi là chuyển người, không phải im.
7. **Tách tệp theo trách nhiệm** để test AST soi được:
   - `agent/ky_nang/mcp_khach.py` — THUẦN MẠNG: không `db`, không `llm`,
     không đọc `.env` ngoài hai biến rào. Test AST cấm `.execute/.fetch/
     .fetchrow/.log_event/.complete/.ingest`, giống `chay.py`.
   - `agent/ky_nang/kho_mcp.py` — CSDL, bí mật, đồng bộ công cụ, nhật ký.
   - `agent/ky_nang/chay.py` — thêm nhánh `loai == "mcp"` gọi
     `kho_mcp.goi_cong_cu(bm, args)`; giữ nguyên ràng buộc không `db`/`llm`.

## 4. Dữ liệu

### 4.1 Bảng mới — migration `0016_mcp_may_chu.sql`

```sql
CREATE TABLE IF NOT EXISTS mcp_may_chu (
    ten          TEXT PRIMARY KEY,          -- ^[a-z][a-z0-9_]{1,19}$
    nhan         TEXT NOT NULL,             -- tên hiển thị, 3–60 ký tự
    dia_chi      TEXT NOT NULL,             -- URL đầy đủ tới endpoint MCP
    bat          BOOLEAN NOT NULL DEFAULT TRUE,
    key_version  INTEGER,                   -- NULL = không có bí mật
    nonce        BYTEA,
    ciphertext   BYTEA,
    suc_khoe     JSONB NOT NULL DEFAULT '{}',  -- {ok, luc, so_cong_cu, so_bo, loi}
    tao_boi      TEXT NOT NULL,
    tao_luc      TIMESTAMPTZ NOT NULL DEFAULT now(),
    sua_luc      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Không cần bảng riêng cho công cụ: công cụ nằm trong `ky_nang_cai_dat`.

### 4.2 Công cụ MCP trong `ky_nang_cai_dat`

- `ten` = `mcp_<ten_may_chu>_<ten_goc đã chuẩn hoá>`: chữ thường, ký tự
  ngoài `[a-z0-9_]` thành `_`, cắt để tổng ≤ 40 ký tự; nếu cắt gây trùng thì
  nối `_<4 hex đầu của sha1(ten_goc)>`. Phải khớp `_TEN_RE` của
  `ban_mo_ta.py` và không trùng công cụ viết sẵn (bộ kiểm hiện có lo).
- `goi` = `mcp:<ten_may_chu>`. Cột `goi` được dùng lại có chủ ý: mọi chốt
  "công cụ có chủ" của đợt gói (không xoá lẻ, không ghi đè bằng form, bật
  tắt theo chủ, nhãn trong số đo) áp dụng luôn cho công cụ MCP. Tên gói không
  bao giờ chứa `:` (`^[a-z][a-z0-9-]{2,39}$`) nên hai loại chủ không lẫn.
- `ban_mo_ta` (JSONB, dict — không `json.dumps`):

```json
{
  "ten": "mcp_kho_tra_ton",
  "loai": "mcp",
  "mo_ta": "<description từ máy chủ, đã kiểm 20–600 ký tự và quét injection>",
  "tham_so": [],
  "cau_hinh": {
    "may_chu": "kho",
    "cong_cu_goc": "tra_ton",
    "luoc_do": { "type": "object", "properties": {...}, "required": [...] },
    "ghi": false,
    "ghi_cho_phep": false
  }
}
```

- `doc_ban_mo_ta` cho `loai="mcp"`: bắt buộc `cau_hinh.may_chu` (khớp tên
  máy chủ), `cau_hinh.cong_cu_goc` (1–100 ký tự), `cau_hinh.luoc_do` là
  object có `type: "object"`, tối đa 20 thuộc tính, mỗi thuộc tính có
  `type` hợp lệ (`string/integer/number/boolean/array/object`); `ghi` và
  `ghi_cho_phep` là bool (mặc định false). `tham_so` được phép rỗng cho
  loại này (các loại khác giữ luật cũ).
- `thanh_cong_cu` cho `loai="mcp"`: `input_schema` lấy nguyên `luoc_do`
  (đã kiểm), không dựng lại từ `tham_so`. Đây là lý do có loại riêng: mô
  hình cần đúng kiểu tham số (số, mảng) mà `ThamSo` chỉ biết chuỗi.
- `LOAI_PLUGIN` thêm `"mcp"`; test AST hiện có sẽ đòi `chay.py` có nhánh
  tương ứng.

### 4.3 Sự kiện

- `mcp.dong_bo` — mỗi lần đồng bộ: `{ten, ok, so_cong_cu, so_bo, loi}`.
- `mcp.may_chu` — tạo/sửa/xoá/bật tắt: `{ten, viec, boi}`.
- `bao_mat.mcp_injection` — kết quả có dấu hiệu ra lệnh.
- Số lần gọi và lỗi dùng sự kiện `cong_cu.goi` sẵn có; nhãn `goi` tự ra
  `mcp:<ten>` qua bản đồ `goi_cua` của `kho_ky_nang`.

## 5. Thành phần

### 5.1 `agent/ky_nang/mcp_khach.py` (thuần mạng)

```
MCP_MAY_CHU_TOI_DA = 5; CONG_CU_MOI_MAY_CHU_TOI_DA = 20
HAN_KET_NOI_GIAY = 5.0; HAN_GOI_GIAY = 10.0; KET_QUA_TOI_DA = 8000; THAN_GUI_TOI_DA = 16 * 1024
class LoiMCP(RuntimeError)
@dataclass CongCuGoc: ten, mo_ta, luoc_do: dict, goi_y_ghi: bool   # goi_y_ghi từ annotations.readOnlyHint == False / destructiveHint
def kiem_dia_chi(url) -> str            # trả host đã chuẩn hoá hoặc ném LoiMCP; luật ở §3.2
def chuan_hoa_ten(ten_may_chu, ten_goc) -> str
async def liet_ke_cong_cu(url, headers, *, http_client=None) -> list[CongCuGoc]
async def goi(url, headers, ten_goc, args, *, http_client=None) -> dict
    # → {"ket_qua": str, "du_lieu": dict|None, "ghi_chu": "..."}
    # hoặc {"loi": str, "can_chuyen_nhan_vien": True, "ghi_chu": "..."}
    # hoặc {"loi", "can_chuyen_nhan_vien": True, "dau_hieu": [...]}  (injection)
```

- `http_client` tuỳ chọn để test cắm `httpx.ASGITransport` — đã thử thành
  công với `mcp==2.0.0`: `MCPServer(...).streamable_http_app(json_response=True,
  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))`
  + `streamable_http_client(url, http_client=...)`. Ở SDK 2.0 tên thuộc tính
  là `input_schema`, `is_error`, `structured_content`.
- Mọi lời gọi mở phiên mới (`initialize` → `call_tool` → đóng). Không giữ
  phiên dài: đơn giản, và một máy chủ treo không giữ được tài nguyên của
  tiến trình agent quá `HAN_GOI_GIAY`.
- Kết quả: ghép các phần `type == "text"`; phần khác ghi `"[<type> bị bỏ]"`;
  `structured_content` (nếu có) thành `du_lieu` sau khi `json.dumps` ≤
  `KET_QUA_TOI_DA`; `is_error` → nhánh `loi`. Quét injection trên toàn bộ
  văn bản đã ghép.

### 5.2 `agent/ky_nang/kho_mcp.py` (CSDL)

```
class MayChuKhongTonTai(LookupError); class KhoDay(RuntimeError)
async def kiem_ket_noi(dia_chi, headers) -> dict          # không ghi gì: {ok, so_cong_cu, cong_cu: [{ten, mo_ta, ghi_goi_y, ly_do_bo?}], loi?}
async def them(ten, nhan, dia_chi, headers|None, *, boi) -> dict   # kiểm, mã hoá, ghi, rồi dong_bo()
async def dong_bo(ten, *, boi) -> dict                     # liệt kê công cụ → upsert ky_nang_cai_dat (goi='mcp:<ten>')
async def bat_tat(ten, bat, *, boi)                         # UPDATE máy chủ + mọi công cụ cùng goi
async def dat_cong_cu(ten, ten_cong_cu, *, bat=None, ghi=None, ghi_cho_phep=None, boi)
async def xoa(ten, *, boi) -> bool                          # xoá công cụ cùng goi rồi máy chủ
async def liet_ke() -> list[dict]                           # kèm công cụ, số đo 7 ngày (dem_goi_7_ngay của goi.py)
async def goi_cong_cu(bm, args) -> dict                     # đọc máy chủ + giải mã header → mcp_khach.goi; ghi bao_mat.mcp_injection nếu có dau_hieu
```

Luật đồng bộ:
- Công cụ mới: ĐỌC (`goi_y_ghi=False`) thì `bat=true` nếu còn chỗ dưới trần
  12 (đếm bằng `_kiem_tran_plugin` của `goi.py`, tách ra dùng chung), hết
  chỗ thì `bat=false` và báo trong kết quả; GHI (`goi_y_ghi=True`) thì
  `ghi=true, bat=false, ghi_cho_phep=false`.
- Công cụ đã có: cập nhật `mo_ta` và `luoc_do`, GIỮ `bat/ghi/ghi_cho_phep`
  do người đặt. Công cụ máy chủ không còn trả về: xoá dòng, ghi vào `so_bo`.
- Mô tả không qua `doc_ban_mo_ta`: bỏ công cụ đó, ghi `ly_do_bo`.
- Kết quả đồng bộ ghi vào `mcp_may_chu.suc_khoe` và sự kiện `mcp.dong_bo`;
  gọi `kho_ky_nang.xoa_dem()` sau mọi lần ghi.

### 5.3 Cửa thi hành

- `chay.py`: `if bm.loai == "mcp": return await kho_mcp.goi_cong_cu(bm, args)`.
- `tools._run_tool_that`, ngay trong nhánh plugin, TRƯỚC `chay_plugin`:
  - `bm.loai == "mcp" and bm.cau_hinh.get("ghi")`:
    - `thu_nghiem.dang_thu.get()` → trả bản mô phỏng (§3.4), không gọi;
    - `not bm.cau_hinh.get("ghi_cho_phep")` → trả "chuyển người" nêu tên
      công cụ và cách bật.
  - Test AST của `test_thu_nghiem.py` chỉ dẫn ra công cụ ghi theo tên tĩnh;
    công cụ MCP ghi là động, nên có test riêng: một `BanMoTa` mcp `ghi=true`
    trong `bat_thu()` không được chạm `kho_mcp.goi_cong_cu` (monkeypatch
    ném nếu bị gọi).
- `run_tool` (bọc số đo) không đổi: `_goi_cua` trả `mcp:<ten>`.

### 5.4 API `/api/mcp` (quản trị)

| Phương thức | Đường | Việc |
|---|---|---|
| GET | `/api/mcp` | máy chủ + công cụ + số đo, `may_chu_toi_da`, `plugin_toi_da` |
| POST | `/api/mcp/kiem` | `{dia_chi, headers?}` → kết nối, liệt kê, KHÔNG ghi |
| POST | `/api/mcp` | `{ten, nhan, dia_chi, headers?}` → 201; 409 khi đủ 5 hoặc trùng tên; 422 địa chỉ/tên sai; 502 không nối được |
| POST | `/api/mcp/{ten}/dong-bo` | đồng bộ lại công cụ |
| POST | `/api/mcp/{ten}/bat-tat` | `{bat}` |
| POST | `/api/mcp/{ten}/cong-cu/{ten_cong_cu}` | `{bat?, ghi?, ghi_cho_phep?}`; 409 khi bật vượt trần |
| DELETE | `/api/mcp/{ten}` | 204; xoá công cụ đi kèm |

Mọi lỗi dịch qua một `_loi()` như `goi_ky_nang.py`. `headers` chỉ nhận tối
đa 5 cặp, tên header `^[A-Za-z0-9-]{1,40}$`, giá trị ≤ 500 ký tự; không bao
giờ trả lại trong GET.

### 5.5 Dashboard (view Kỹ năng, panel "Máy chủ MCP")

- Danh sách máy chủ: nhãn, host (không hiện path/query), trạng thái đồng
  bộ cuối (ok/lỗi, lúc nào), `x/y công cụ đang bật`, nút Đồng bộ / Bật-Tắt /
  Xoá.
- Bảng công cụ dưới mỗi máy chủ: tên cho mô hình, mô tả (cắt 120), huy hiệu
  ĐỌC/GHI, công tắc Bật, và với công cụ GHI thêm công tắc "cho phép ghi
  ngoài phòng thử" (mặc định tắt, có dòng cảnh báo). Gọi 7 ngày / lỗi.
- Form thêm: tên (gợi ý từ nhãn), nhãn, địa chỉ, ô header dạng
  `Tên: giá trị` mỗi dòng (ẩn giá trị sau khi lưu). Nút **Kiểm** gọi
  `/kiem` và hiện danh sách công cụ sẽ có, kèm công cụ bị bỏ và lý do; nút
  **Thêm** tạo rồi đồng bộ.
- Mọi chuỗi máy chủ qua `esc()`. Panel lỗi thì tự nói "không tải được", không
  im như panel gói đã sửa.
- Panel plugin hiện có: công cụ có `goi` bắt đầu `mcp:` hiện huy hiệu
  "MCP · <máy chủ>" thay vì "gói", và không có nút Xoá (đã có chốt).

### 5.6 Cấu hình và tài liệu

- `.env.example` thêm `MCP_MAY_CHU_NOI_BO=` với chú thích VÌ SAO (mục §3.2).
- `agent/config.py`: `mcp_may_chu_noi_bo: str = ""`.
- `scripts/sinh_ky_nang.py`: mục "Máy chủ MCP" (giới hạn từ hằng, luật đọc/
  ghi, rào host) → `docs/ky-nang.md`.
- `docs/van-hanh.md`: "Nối một máy chủ MCP" (Kiểm → Thêm → bật công cụ →
  Phòng thử → với công cụ ghi: bật "cho phép ghi" chỉ sau khi thử).
- `scripts/kiem_goi.py`: không đổi. Thêm `scripts/kiem_mcp.py <ten>`: nối
  máy chủ, liệt kê, gọi thử một công cụ ĐỌC không tham số bắt buộc (nếu có),
  mã thoát khác 0 khi hỏng — không tốn tiền mô hình.
- `scripts/sinh_so_do.py`: `mcp_may_chu` vào nhóm "Vận hành".

## 6. Luồng

1. **Thêm máy chủ**: dashboard → `POST /api/mcp/kiem` (xem trước) →
   `POST /api/mcp` → `kho_mcp.them`: `kiem_dia_chi` → mã hoá header → INSERT
   → `dong_bo` → công cụ vào `ky_nang_cai_dat` → `kho_ky_nang.xoa_dem()`.
2. **Khách hỏi**: `respond()` → `cong_cu_dang_bat` đưa lược đồ MCP cho mô
   hình → mô hình gọi `mcp_kho_tra_ton` → `run_tool` → `_run_tool_that`:
   chốt tắt → chốt ghi/sandbox → `chay_plugin` → `kho_mcp.goi_cong_cu` →
   `mcp_khach.goi` (kết nối 5 s, gọi 10 s) → cắt 8.000, quét → kết quả về
   mô hình → số đo `cong_cu.goi` với `goi="mcp:kho"`.
3. **Máy chủ chết**: `mcp_khach.goi` ném/timeout → `{"loi", "can_chuyen_nhan_vien": true}`
   → agent chuyển người, `cong_cu.goi` ghi `ok=false` → cột lỗi 7 ngày đỏ.
4. **Tắt máy chủ**: `bat_tat(False)` tắt mọi công cụ cùng `goi` → chốt thứ
   hai của `run_tool` chặn ngay cả khi lược đồ còn trong lịch sử hội thoại.

## 7. Lỗi và hỏng im lặng

| Tình huống | Hành vi |
|---|---|
| Địa chỉ nội bộ không nằm trong `MCP_MAY_CHU_NOI_BO` | 422 lúc Kiểm/Thêm, nêu đúng biến cần sửa |
| Máy chủ trả > 20 công cụ | nhận 20 đầu theo tên, `so_bo` + lý do, hiện trên dashboard |
| Mô tả công cụ có câu ra lệnh | bỏ công cụ đó, lý do trong kết quả đồng bộ, sự kiện `mcp.dong_bo` |
| Kết quả có câu ra lệnh | không đưa mô hình, chuyển người, `bao_mat.mcp_injection` (bỏ qua trong sandbox như `bao_mat.injection`) |
| Đồng bộ hỏng (mạng) | máy chủ giữ nguyên công cụ cũ, `suc_khoe.ok=false` + lỗi, dashboard đỏ dòng đó |
| Vault chưa cấu hình mà có header | 503 như `cau_hinh_dong`; máy chủ không header vẫn thêm được |
| Trần 12 đầy | công cụ mới `bat=false`, dashboard nói rõ; bật tay → 409 |

## 8. Test

- `tests/test_mcp_khach.py`: `kiem_dia_chi` (từng luật: scheme, host ngoài
  danh sách, nội bộ không khai, nội bộ đã khai, dải riêng luôn chặn, DNS trỏ
  về loopback); `chuan_hoa_ten` (ký tự lạ, cắt 40, trùng → hex); máy chủ
  giả trong tiến trình qua `ASGITransport`: liệt kê, gọi đọc, `is_error`,
  cắt 8.000, `structured_content`, injection trong kết quả bị chặn, timeout
  (công cụ giả `sleep` > hạn với hạn rút ngắn qua tham số).
- `tests/test_kho_mcp.py`: CSDL giả theo mẫu `_CSDL` của test gói: thêm →
  upsert công cụ đúng `goi`, đọc bật/ghi tắt, trần 12, giữ cờ người đặt khi
  đồng bộ lại, xoá công cụ biến mất, bỏ mô tả xấu có lý do, tắt máy chủ tắt
  công cụ, xoá sạch, header mã hoá (vault giả) và không rò trong `liet_ke`,
  `goi_cong_cu` ghi `bao_mat.mcp_injection`.
- `tests/test_ky_nang_plugin.py`: `doc_ban_mo_ta` loại `mcp` (luoc_do sai,
  quá 20 thuộc tính, thiếu may_chu, tham_so rỗng được phép), `thanh_cong_cu`
  dùng nguyên `luoc_do`; AST: `mcp_khach.py` không `db/llm`.
- `tests/test_thu_nghiem.py` hoặc tệp mới: công cụ MCP ghi trong sandbox
  không gọi thật; ngoài sandbox chưa `ghi_cho_phep` thì chuyển người.
- `tests/test_api_mcp.py`: 403 nhân viên; kiểm không ghi; 409 trần máy chủ;
  422 địa chỉ; header không có trong GET; bật công cụ vượt trần 409.
- `tests/test_dashboard_mcp.py`: panel, `esc()`, nút, huy hiệu MCP ở plugin,
  lỗi panel tự báo.
- Test tài liệu sinh, sơ đồ, `.env.example` có biến mới.

## 9. Ngoài phạm vi, ghi lại

- OAuth 2.1 cho máy chủ MCP công cộng; stdio; resources/prompts; sampling.
- Giữ phiên MCP dài để tiết kiệm `initialize` (đo trước khi làm).
- Kho máy chủ MCP gợi ý sẵn (danh sách "nối một cú bấm").
