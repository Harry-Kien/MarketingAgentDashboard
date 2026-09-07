# Gói kỹ năng — thiết kế

Ngày 2026-09-07. Đợt 3 sau (1) Cài đặt API và (2) Phòng thử agent. Chủ dự án
giao quyền quyết định thiết kế; các lựa chọn dưới đây là của người viết và
được ghi lý do. Nối máy chủ MCP ngoài **không** nằm trong đợt này (mục 8).

## 1. Bài toán

Kỹ năng của agent hôm nay có hai lớp: 11 công cụ viết sẵn (bật/tắt được) và
plugin cắm thêm (bốn loại chỉ đọc, viết bằng bản mô tả). Thiếu ba thứ mà mọi
hệ thống kỹ năng trên thị trường (Claude Code, GPT tuỳ chỉnh) đều có:

- **Hướng dẫn**: "khi khách hỏi về X thì hỏi lại Y, tra Z, không hứa W".
  Muốn đổi cách tư vấn một chủ đề hôm nay phải sửa prompt trong mã.
- **Đóng gói**: hướng dẫn + công cụ + tài liệu đi cùng nhau, cài một lần,
  xuất ra được, có phiên bản. Hôm nay plugin là từng dòng rời, tài liệu nạp
  riêng, không ai biết cái nào thuộc cái nào.
- **Số đo**: kỹ năng nào được gọi bao nhiêu lần, hỏng bao nhiêu lần. Hôm nay
  không có bảng nào ghi lần gọi công cụ.

Mục tiêu: một **gói kỹ năng** là dữ liệu, cài từ dashboard, có hiệu lực ngay,
và không được mạnh hơn kỹ năng viết sẵn (nguyên tắc trong CLAUDE.md: plugin
là dữ liệu, không phải mã).

## 2. Quyết định kiến trúc

1. **Hướng dẫn kích hoạt theo TỪ KHOÁ, nạp vào khối biến động của prompt.**
   `SYSTEM` phải là cùng một chuỗi ở mọi request để điểm cache còn dùng được
   (`agent/core/agent.py:40-41`); nội dung gói thay đổi theo lượt nên phải
   vào khối `volatile` cùng ngữ cảnh RAG. Chọn từ khoá thay vì để mô hình tự
   "mở" hướng dẫn qua một công cụ, vì cách sau tốn thêm một vòng gọi mô hình
   mỗi lần dùng và không tất định; từ khoá so khớp sau `fold()` là rẻ, đo
   được, và test được. Tối đa 2 gói kích hoạt một lượt, mỗi hướng dẫn tối đa
   4.000 ký tự, để ngữ cảnh không phình.
2. **Hướng dẫn đi qua đúng ba chốt của ô mô tả plugin, cộng một chốt nữa.**
   Nó được ghép thẳng vào thứ mô hình đọc, nên là một mẩu prompt do người
   trong nhà viết. Quét injection (`phong_thu.quet`), giới hạn độ dài, chỉ
   quản trị viên — và **quét từ cấm quảng cáo** (`cham_mot_luot.tu_cam`):
   một dòng "luôn nói kem này chữa khỏi" trong hướng dẫn là vi phạm luật đi
   vòng qua mọi lưới.
3. **Công cụ của gói là plugin hiện có.** Gói không thêm loại công cụ mới;
   nó gom các bản mô tả plugin và ghi chúng vào `ky_nang_cai_dat` với cột
   mới `goi` (tên gói sở hữu). Bật/tắt gói là bật/tắt các plugin của nó. Toàn
   bộ chốt an toàn của plugin (chỉ đọc, canh bằng AST) giữ nguyên.
4. **Tài liệu của gói nạp vào kho tri thức dưới nhãn của gói**: tiêu đề
   `[<tên gói>] <tiêu đề>`, nguồn `goi:<tên gói>:<slug>`. Plugin
   `tra_tai_lieu` của gói lọc theo nhãn ấy bằng cơ chế sẵn có (khớp chuỗi
   con tiêu đề). Tắt gói thì gỡ tài liệu của gói khỏi kho; bật lại thì nạp
   lại từ bản ghi. Không thêm cột nhóm vào `documents`: một migration cho
   một tính năng chưa ai đòi.
5. **Số đo ghi ở `run_tool`, không ở `chay.py`.** Test hiện có cấm `chay.py`
   gọi `db.*` (bộ thi hành plugin phải thuần). Mỗi lời gọi công cụ ghi một
   sự kiện `cong_cu.goi` (tên, gói nếu có, thành công hay lỗi, ms). Dashboard
   đếm từ `events` cho 7 ngày.
6. **Phiên bản là lịch sử chỉ ghi thêm.** Cài gói cùng tên với phiên bản
   khác là ghi bản cũ vào `goi_ky_nang_lich_su` rồi thay bản hiện hành; có
   nút khôi phục. Giữ tối đa 10 bản mỗi gói.

Đã loại: gói mang mã Python/JS (trái nguyên tắc số một); thêm cột nhóm cho
`documents`; mô hình tự mở hướng dẫn qua công cụ (thêm một vòng gọi).

## 3. Định dạng gói

Một gói là JSON (dán, hoặc tệp `.json`, hoặc `.zip` chứa `goi.json` +
`HUONG_DAN.md` + `tai-lieu/*.md` — zip chỉ là cách chia file, nạp xong thành
đúng JSON dưới):

```json
{
  "ten": "tu-van-da-nhay-cam",
  "phien_ban": "1.0.0",
  "mo_ta": "Tư vấn cho khách da nhạy cảm, ưu tiên hỏi tiền sử kích ứng.",
  "tu_khoa": ["da nhạy cảm", "kích ứng", "ửng đỏ"],
  "huong_dan": "Khi khách nói da nhạy cảm:\n1. Hỏi ...\n2. Tra `bang_thanh_phan_ne` ...",
  "cong_cu": [ { "ten": "bang_thanh_phan_ne", "loai": "tra_bang", "mo_ta": "...", "tham_so": [...], "cau_hinh": {...} } ],
  "tai_lieu": [ { "tieu_de": "Thành phần nên tránh", "noi_dung": "..." } ]
}
```

Ràng buộc (kiểm trước khi ghi, sai một là không ghi gì):

| Trường | Luật |
|---|---|
| `ten` | `^[a-z][a-z0-9-]{2,39}$`, không trùng công cụ viết sẵn |
| `phien_ban` | `^\d+\.\d+\.\d+$` |
| `mo_ta` | 20–300 ký tự, quét injection |
| `tu_khoa` | 1–10 cụm, mỗi cụm 3–40 ký tự; so khớp sau `fold()` |
| `huong_dan` | 50–4.000 ký tự; quét injection; **không từ cấm quảng cáo** |
| `cong_cu` | 0–5 bản mô tả plugin, mỗi bản qua `doc_ban_mo_ta` y như plugin rời; tên không trùng plugin của gói khác |
| `tai_lieu` | 0–20 tài liệu, `tieu_de` 3–120 ký tự, `noi_dung` 50–20.000 ký tự |
| Tổng | tối đa 20 gói; trần 12 plugin bật cùng lúc hiện có vẫn áp dụng (plugin của gói tính vào) |

## 4. Thành phần

### 4.1. Lưu trữ

Migration `0014_goi_ky_nang.sql`:

```
goi_ky_nang(
  ten        TEXT PRIMARY KEY,
  phien_ban  TEXT NOT NULL,
  bat        BOOLEAN NOT NULL DEFAULT TRUE,
  noi_dung   JSONB NOT NULL,      -- toàn bộ gói đã kiểm
  tao_boi    TEXT NOT NULL,
  tao_luc    TIMESTAMPTZ NOT NULL DEFAULT now(),
  sua_luc    TIMESTAMPTZ NOT NULL DEFAULT now()
)
goi_ky_nang_lich_su(
  id         BIGSERIAL PRIMARY KEY,
  ten        TEXT NOT NULL,
  phien_ban  TEXT NOT NULL,
  noi_dung   JSONB NOT NULL,
  thay_luc   TIMESTAMPTZ NOT NULL DEFAULT now(),
  thay_boi   TEXT NOT NULL
)
ALTER TABLE ky_nang_cai_dat ADD COLUMN IF NOT EXISTS goi TEXT;
```

### 4.2. `agent/ky_nang/goi.py` — bản mô tả gói và kho

- `doc_goi(tho: dict) -> Goi` (dataclass): mọi luật ở mục 3; dùng lại
  `doc_ban_mo_ta` cho từng công cụ; ném `LoiGoi(ValueError)` với thông điệp
  chỉ đúng trường sai.
- `tu_zip(bytes) -> dict`: đọc `goi.json`, ghép `HUONG_DAN.md` vào
  `huong_dan` nếu JSON chưa có, ghép `tai-lieu/*.md` vào `tai_lieu` (tiêu đề
  = dòng đầu `# ...` hoặc tên tệp). Từ chối zip > 2 MB hoặc > 40 tệp, và
  mọi đường dẫn có `..` hay tuyệt đối (zip slip).
- `async cai(tho, *, boi) -> Goi`: kiểm, ghi lịch sử nếu đã có bản khác
  phiên bản, upsert `goi_ky_nang`, ghi/ghi đè plugin của gói vào
  `ky_nang_cai_dat` với `goi=ten` (xoá plugin cũ của gói không còn trong
  bản mới), nạp tài liệu (`rag.ingest` với nhãn, sau khi gỡ tài liệu cũ
  của gói), `log_event("ky_nang.goi_cai", ...)`, `kho_ky_nang.xoa_dem()`.
- `async bat_tat(ten, bat, *, boi)`: đổi `bat` của gói và của mọi plugin
  `goi=ten`; tắt thì `rag.xoa_nguon("goi:<ten>:")`, bật thì nạp lại.
- `async xoa(ten, *, boi)`: gỡ plugin, gỡ tài liệu, xoá dòng, giữ lịch sử.
- `async khoi_phuc(ten, id_lich_su, *, boi)`: cài lại bản trong lịch sử
  (đi qua `cai`, nên bản hiện hành lại vào lịch sử).
- `async liet_ke() -> list[dict]`: gói + số công cụ + số tài liệu + số lần
  gọi 7 ngày (đếm `events` kind `cong_cu.goi` có `goi=ten`).
- `async huong_dan_cho_luot(cau_hoi: str) -> list[tuple[str, str]]`: các
  gói **đang bật** có từ khoá khớp `fold(cau_hoi)`, tối đa 2, theo thứ tự
  số từ khoá khớp giảm dần rồi tên; trả `(ten, huong_dan)`. Đọc từ bộ đệm
  30 giây như `kho_ky_nang._doc` (cùng `xoa_dem()`).
- `rag.xoa_nguon(prefix: str) -> int` mới trong `agent/core/rag.py`: xoá
  `documents` (và `chunks` theo khoá ngoại) có `source LIKE prefix || '%'`.

### 4.3. `respond()` — nạp hướng dẫn

Sau khi dựng `context` từ RAG và hồ sơ khách (`agent/core/agent.py` ~430-445),
trước `llm.cached_system(SYSTEM, context)`:

```python
goi_kich_hoat = await goi.huong_dan_cho_luot(question)
if goi_kich_hoat:
    context += "\n\n" + "\n\n".join(
        f"## Hướng dẫn kỹ năng «{ten}»\n{hd}" for ten, hd in goi_kich_hoat
    )
```

Hướng dẫn nằm trong khối biến động, sau ngữ cảnh RAG. `Reply` thêm trường
`goi_ky_nang: list[str]` (tên gói đã kích hoạt) để phòng thử hiện được.
Sandbox không ảnh hưởng: hướng dẫn là đọc.

### 4.4. `run_tool` — số đo

Bọc toàn bộ thân `run_tool` hiện có vào `_run_tool_that`; `run_tool` mới đo
thời gian, gọi, rồi `db.log_event("cong_cu.goi", ten=name, goi=<goi của
plugin nếu có>, ok=<không có khoá "loi">, ms=..., thu_nghiem=dang_thu)`
trong `try/except` nuốt lỗi CSDL với chú thích VÌ SAO (số đo hỏng không
được làm hỏng câu trả lời). Trong sandbox vẫn ghi nhưng đánh dấu
`thu_nghiem=True` để dashboard trừ ra.

### 4.5. API — `agent/api/goi_ky_nang.py`, prefix `/api/goi-ky-nang`, tất cả quản trị

| Đường | Việc |
|---|---|
| `GET ""` | danh sách gói (mục 4.2 `liet_ke`) + số lần gọi 7 ngày từng công cụ viết sẵn và plugin rời (`cong_cu: [{ten, so_lan, so_loi}]`) |
| `POST /kiem` | body JSON gói → `{hop_le, loi?, tom_tat{so_cong_cu, so_tai_lieu, tu_khoa}}`, không ghi |
| `POST ""` | body JSON gói → cài |
| `POST /tep` | multipart `tep` (.json hoặc .zip) → cài |
| `POST /{ten}/bat-tat` | body `{bat}` |
| `DELETE /{ten}` | xoá |
| `GET /{ten}/xuat` | JSON gói hiện hành (đúng định dạng mục 3, tải về được) |
| `GET /{ten}/lich-su` | danh sách `{id, phien_ban, thay_luc, thay_boi}` |
| `POST /{ten}/khoi-phuc/{id}` | cài lại bản trong lịch sử |

Lỗi: 422 kèm thông điệp của `LoiGoi`; 409 khi quá 20 gói hoặc quá trần
plugin; 413 zip quá lớn; 404 gói/lịch sử không có.

### 4.6. Dashboard — màn Kỹ năng

Thêm panel **Gói kỹ năng** phía trên panel plugin: bảng gói (tên, phiên
bản, bật/tắt, số công cụ, số tài liệu, số lần gọi 7 ngày; nút Xuất, Lịch
sử, Xoá). Form cài: ô dán JSON hoặc chọn tệp `.json`/`.zip`, nút **Kiểm**
(gọi `/kiem`, hiện tóm tắt hoặc lỗi), nút **Cài**. Lịch sử mở ra danh sách
phiên bản với nút Khôi phục. Bảng kỹ năng viết sẵn và plugin rời hiện có
thêm cột **gọi 7 ngày** (số lần, số lỗi). Phòng thử hiện "Gói kích hoạt:
…" ở "Bên trong lượt vừa rồi".

Mọi chuỗi máy chủ qua `esc()`; tải tệp bằng `FormData` như hộp thư
(`app.js` ~600-625).

### 4.7. Tài liệu

`docs/ky-nang.md` là file sinh từ `so_dang_ky.py`: thêm vào bộ sinh một mục
"Gói kỹ năng" (định dạng, luật, cách cài, cách tắt). `docs/van-hanh.md`:
mục "Cài một gói kỹ năng" và cảnh báo hướng dẫn là prompt do người trong
nhà viết. Một gói mẫu `data/goi-ky-nang/tu-van-da-nhay-cam.example.json`
đi theo repo để thử ngay.

## 5. Luồng

**Cài**: dán JSON → `POST /kiem` → xem tóm tắt → `POST ""` → `doc_goi`
kiểm hết → lịch sử → upsert → plugin → tài liệu → nhật ký → xoá đệm → có
hiệu lực ở lượt tiếp theo.

**Một lượt trả lời**: `respond()` gọi `huong_dan_cho_luot(question)` → ghép
vào `context` → mô hình thấy hướng dẫn và các công cụ của gói (đã có trong
lược đồ vì là plugin đang bật) → gọi công cụ → `run_tool` ghi `cong_cu.goi`
→ `Reply.goi_ky_nang` mang tên gói.

## 6. Xử lý lỗi

- Bản gói sai → 422, không ghi gì (kiểm toàn bộ trước khi chạm CSDL).
- Nạp tài liệu hỏng giữa chừng (embedding lỗi) → gói vẫn được ghi nhưng
  `bat=False`, trả 502 kèm lý do; người dùng bật lại sau khi sửa (bật = nạp
  lại). Ghi `ky_nang.goi_tai_lieu_hong`.
- `huong_dan_cho_luot` lỗi CSDL → trả rỗng và ghi cảnh báo qua `logging`;
  agent trả lời không có hướng dẫn thay vì chết.
- Ghi số đo hỏng → nuốt, có chú thích VÌ SAO.

## 7. Kiểm thử (không API, không CSDL trừ khi giả)

- `doc_goi`: từng luật ở mục 3 có một ca đỏ; hướng dẫn có từ cấm bị từ chối
  với thông điệp nêu cụm; injection trong hướng dẫn bị từ chối; tên trùng
  công cụ viết sẵn.
- `tu_zip`: ghép đúng; zip slip bị từ chối; quá lớn bị từ chối.
- `huong_dan_cho_luot`: khớp không dấu, tối đa 2, gói tắt không kích hoạt.
- `respond()`: hướng dẫn xuất hiện trong khối biến động (bắt qua `llm.complete`
  giả) và KHÔNG trong `SYSTEM`; `Reply.goi_ky_nang` đúng tên.
- `run_tool`: ghi `cong_cu.goi` với `ok` đúng; lỗi `log_event` không làm hỏng
  kết quả; `chay.py` vẫn không gọi `db.*` (test AST hiện có).
- Kho: cài → plugin có `goi`; tắt → plugin tắt, `xoa_nguon` được gọi; xoá →
  lịch sử còn; khôi phục → bản hiện hành vào lịch sử (CSDL giả ghi SQL).
- API: 403 nhân viên; 422/409/413/404; `xuat` trả đúng định dạng nạp lại
  được (round-trip).
- Dashboard: regex panel, form, `esc`, FormData; JS parse được.
- Migration: `sinh_so_do` sinh lại, test schema hiện có.

## 8. Ngoài phạm vi

Nối máy chủ MCP ngoài (đợt 3b: client MCP, allowlist trong `.env` như
`ky_nang_host_cho_phep`, máy chủ giả để test); chợ gói; ký số gói; kích hoạt
hướng dẫn do mô hình tự chọn.
