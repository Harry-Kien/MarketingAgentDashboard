# Phòng thử agent — thiết kế

Ngày 2026-09-06. Đợt 2 của ba đợt: (1) Cài đặt API — xong, (2) **Phòng thử
agent**, (3) Gói kỹ năng. Chủ dự án giao quyền quyết định thiết kế; các
lựa chọn dưới đây là của người viết và được ghi lý do.

## 1. Bài toán

Không có chỗ nào để hỏi agent một câu và thấy nó **đã làm gì**: gọi công
cụ nào với tham số gì, lớp lưới nào bắt, căn cứ ở đâu, tốn bao nhiêu. Muốn
biết thì phải nhắn từ Zalo thật (gây tác dụng phụ thật) hoặc chạy
`scripts/eval` (tốn 13 phút, một lượt, không xem được dấu vết). Cài kỹ năng
mới xong không có cách nào biết mô hình có chọn nó hay không.

Mục tiêu: màn **Phòng thử** trên dashboard, chỉ quản trị viên, nhắn nhiều
lượt như khách và thấy toàn bộ bên trong mỗi lượt, **không để lại tác dụng
phụ nào** ngoài chi phí model.

## 2. Quyết định kiến trúc

1. **Sandbox là cờ ngữ cảnh, kiểm ở tầng thi hành công cụ.** `ContextVar`
   `dang_thu` trong `agent/core/thu_nghiem.py`; `tools.run_tool()` hỏi nó
   trước khi chạy công cụ có tác dụng phụ. Chọn cách này thay vì thêm tham
   số `sandbox=` xuyên suốt `respond()` → `run_tool()` → từng hàm con, vì
   `run_tool` không nhận `channel` và bốn hàm con có chữ ký khác nhau; một
   cờ ngữ cảnh chặn đúng một chỗ, và test AST canh được rằng mọi công cụ
   trong `CO_TAC_DUNG_PHU` đều đi qua chỗ đó.
2. **Dấu vết nằm trong `Reply`**, thu ngay tại vòng gọi công cụ của
   `respond()`. Không ghi `events`, không bảng mới: dấu vết là dữ liệu của
   một lượt, sống cùng `Reply`.
3. **Phiên thử trong bộ nhớ tiến trình**, không ghi `messages`. Hội thoại
   giả vẫn phải có trong `conversations` (công cụ tra đơn cần khoá ngoại),
   nhưng gắn vào một tài khoản kênh riêng đã **tắt** và ở `mode='human'`,
   `state='closed'`, nên `auto_routing`, `sla`, `outbox` và canh gác không
   nhìn thấy nó.
4. **Chi phí thử có sổ riêng.** `respond()` trong sandbox ghi vào
   `thu_nghiem.ghi_nhan()` thay vì `ngan_sach.ghi_nhan()`. Trần ngày riêng
   `phong_thu_tran_ngay_usd` (mặc định 1 USD) trong cấu hình agent. Trần
   sản xuất vẫn được kiểm trước khi gọi model — hết ngân sách thật thì
   phòng thử cũng dừng, vì tiền là một túi.

Đã loại: tái dùng `/webchat` (đẻ hội thoại và khách thật, đi qua outbox);
ghi lượt thử vào `messages` (làm sai số liệu tổng quan và chi phí).

## 3. Thành phần

### 3.1. `agent/core/thu_nghiem.py` — chế độ thử

- `dang_thu: ContextVar[bool]` mặc định `False`; `bat_thu()` trả về
  context manager đặt `True`.
- `CO_TAC_DUNG_PHU = frozenset({"tao_don_hang", "tao_video", "xin_huy_don",
  "xin_doi_tra"})`.
- `mo_phong(ten, args, products) -> dict`: kết quả giả đúng **hình dạng**
  bản thật để mô hình trả lời như thường, luôn có `thu_nghiem: True` và
  `ghi_chu` bắt đầu bằng `"ĐANG THỬ:"`:
  - `tao_don_hang`: kiểm mã hàng có trong danh mục và số lượng > 0 (đọc
    catalog, không đọc kho), trả `{da_tao: True, ma_don: "THU-<6 hex>",
    tong_tien, ...}`; mã sai trả đúng lỗi như bản thật.
  - `tao_video`: `{dat_duoc: True, video_id: "thu-<6 hex>"}`.
  - `xin_huy_don`, `xin_doi_tra`: `{da_ghi_nhan: True, can_chuyen_nhan_vien:
    True}` — giữ nguyên hành vi chuyển người của bản thật.
- Sổ chi phí: `ghi_nhan(usd)`, `da_tieu_hom_nay()`, `con_tran() -> (con,
  da_tieu, tran)`; đổi ngày thì về 0; `tran()` đọc
  `runtime.STATE["phong_thu_tran_ngay_usd"]`.

### 3.2. `agent/core/tools.py::run_tool`

Ngay sau chốt "kỹ năng đang tắt" và trước nhánh plugin:

```python
if thu_nghiem.dang_thu.get() and name in thu_nghiem.CO_TAC_DUNG_PHU:
    return await thu_nghiem.mo_phong(name, args, await _catalog())
```

Test AST: mọi tên trong `CO_TAC_DUNG_PHU` phải xuất hiện như một nhánh
`name == ...` trong `run_tool` **sau** dòng kiểm `dang_thu` — thêm công cụ
ghi mới mà quên đưa vào tập là test đỏ.

### 3.3. `Reply` mở rộng (`agent/core/agent.py`)

Ba trường mới, mặc định rỗng để mọi chỗ dựng `Reply` hiện có không đổi:

- `cong_cu: list[dict]` — mỗi phần tử `{ten, tham_so, ket_qua, ms, vong,
  thu_nghiem}`; `ket_qua` là bản cắt: chuỗi dài hơn 400 ký tự bị cắt, danh
  sách dài hơn 20 phần tử bị cắt, để một `tim_kien_thuc` trả 8 đoạn không
  làm phình phản hồi.
- `vong: list[dict]` — `{cost_usd, tokens_in, tokens_out, latency_ms,
  so_cong_cu}` mỗi lần gọi model.
- `luoi_bat: str | None` — mã lớp lưới, một trong: `tran_hoi_thoai`,
  `tran_ngay`, `injection`, `tin_cay_thap`, `bat_buoc_chuyen`,
  `hua_khong_goi`, `chan_doan_y_te`, `cong_cu_chuyen_nguoi`,
  `cong_cu_yeu_cau`, `het_vong`. Chuỗi `escalate_reason` **giữ nguyên**
  (test hiện có so chuỗi); mã là tầng bổ sung để dashboard và bộ đo không
  phải parse tiếng Việt.

`respond()` trong sandbox: không gọi `pipeline.request_video()`, gọi
`thu_nghiem.ghi_nhan()` thay `ngan_sach.ghi_nhan()`, không truyền
`customer_ref` (phòng thử gọi với chuỗi rỗng nên hồ sơ khách không bị đụng
— đã có sẵn, ghi lại để không ai "sửa" nó).

### 3.4. `agent/core/cham_mot_luot.py` — chấm hình thức một câu

Chuyển `fold()` và `_pham()` từ `scripts/eval.py` vào đây (script import
lại từ agent; chiều ngược lại là cấm). Thêm `TU_CAM_QUANG_CAO` (danh sách
đang nằm trong `scripts/sinh_bo_cau_vang.py`, chuyển vào đây và script
import lại) và:

- `tu_cam(text) -> list[str]`
- `so_voi_bo_vang(text, escalate, case) -> {dat, thieu, cam, sai_chuyen}` —
  đúng thuật toán `scripts/eval.py::run_case` phần chấm.

### 3.5. Phiên thử — `agent/core/phong_thu_phien.py`

- `Phien`: `id`, `conversation_id`, `history` (định dạng `respond()` nhận),
  `luot: list[{khach, agent, reply_tom_tat}]`, `chi_phi`, `tao_luc`,
  `cap_nhat`.
- Kho trong bộ nhớ: tối đa 20 phiên, phiên quá 2 giờ không dùng bị dọn khi
  tạo phiên mới, mỗi phiên tối đa 30 lượt.
- `hoi_thoai_thu(phien_id)`: tạo idempotent tài khoản kênh `channel=
  'webchat'`, `external_account_id='phong-thu'`, `display_name='Phòng thử
  agent'`, `status='disabled'`; contact "Khách thử" + contact_point theo
  `phien_id`; hội thoại `channel='phong_thu'`, `nen_tang='phong_thu'`,
  `mode='human'`, `state='closed'`, `external_id=f"phong-thu:{phien_id}"`.
  Tài khoản `disabled` nên factory, xác minh, canh gác đều bỏ qua.
- Danh sách hội thoại (`GET /api/conversations`) và tổng quan
  (`GET /api/overview`) thêm `channel <> 'phong_thu'`.

### 3.6. API — `agent/api/phong_thu_agent.py`, prefix `/api/phong-thu`, tất cả quản trị

| Đường | Việc |
|---|---|
| `POST /phien` | tạo phiên, trả `{id}` |
| `GET /phien/{id}` | lịch sử lượt + chi phí phiên |
| `DELETE /phien/{id}` | xoá phiên khỏi bộ nhớ |
| `POST /phien/{id}/hoi` | body `{cau_hoi, ky_vong?}`; chạy `respond()` trong `bat_thu()`; trả lượt (mục 4) |
| `GET /goi-y` | câu gợi ý từ `data/eval/golden.jsonl` (lui về `.example`), nhóm theo `nhom`, mỗi câu kèm `ky_vong` |
| `GET /ngan-sach` | `{da_tieu, tran}` của sổ thử |

`ky_vong` là đúng một dòng bộ vàng (`chuyen_nguoi`, `phai_co`,
`phai_co_mot_trong`, `khong_duoc_co`); có thì lượt trả thêm `so_voi_bo_vang`.

Lỗi: hết trần thử → 429 kèm `{da_tieu, tran}`; hết trần sản xuất → 429 với
lý do của `respond()` (nó trả `Reply` escalate `tran_ngay`, API dịch thành
429 để dashboard không tưởng là câu trả lời); phiên không có → 404; câu hỏi
rỗng hoặc quá 2000 ký tự → 422; phiên đủ 30 lượt → 409.

### 3.7. Dashboard — view `phongthu`

Rail thêm mục **Phòng thử** sau *Kỹ năng*. Bố cục hai cột:

- Trái: khung chat (bong bóng khách/agent, meta chi phí và độ trễ mỗi lượt),
  ô nhập, nút *Gửi*, nút *Phiên mới*, *Xoá phiên*; bên dưới là các chip
  **Gợi ý** theo bốn nhóm bộ vàng — bấm chip là điền câu và mang `ky_vong`.
- Phải, "Bên trong lượt vừa rồi": huy hiệu lớp lưới (`luoi_bat` → nhãn
  tiếng Việt, kèm `escalate_reason`), chuyển người có/không, độ tin cậy,
  căn cứ, **công cụ đã gọi** (mỗi cái một dòng, bấm mở `<pre class="pre">`
  JSON tham số và kết quả, nhãn "ĐANG THỬ" nếu mô phỏng), chi phí/thời
  gian/model/token theo vòng, và **chấm nhanh**: từ cấm, lỗi hình thức
  (`cham_nhieu_luot.cham` trên cả phiên), đạt/không so với bộ vàng nếu có.
- Không tự tải lại theo vòng 6 giây của `refresh()`: view chỉ vẽ lại khi
  người dùng bấm.
- Mọi chuỗi từ máy chủ qua `esc()`; JSON chỉ vào `<pre>` sau `esc()`.

### 3.8. Cấu hình

`phong_thu_tran_ngay_usd` (mặc định 1.0) vào `runtime.KHOA_BEN_VUNG` và
`_MO_TA_CAU_HINH` để chỉnh trên màn Cấu hình, cùng cơ chế lưu bền hiện có.

## 4. Luồng một lượt thử

1. Dashboard `POST /phien/{id}/hoi {cau_hoi, ky_vong?}`.
2. API kiểm phiên, độ dài, trần thử (`thu_nghiem.con_tran()`).
3. `with bat_thu(): reply = await brain.respond(conversation_id, history,
   question, customer_ref="", channel="phong_thu")`.
4. `run_tool` mô phỏng bốn công cụ ghi; các công cụ đọc chạy thật; dấu vết
   được ghi vào `reply.cong_cu`/`reply.vong`; lưới đặt `reply.luoi_bat`.
5. API nối `history` (user + assistant, đúng định dạng `respond()` nhận —
   không nối `tool_calls` để lượt sau không mang dấu vết cũ), ghi
   `thu_nghiem.ghi_nhan(reply.cost_usd)`, chấm nhanh, trả:
   `{tra_loi, escalate, escalate_reason, luoi_bat, grounded, confidence,
   sources, cong_cu, vong, cost_usd, latency_ms, model, tokens_in,
   tokens_out, cham: {tu_cam, hinh_thuc, so_voi_bo_vang?}, phien: {so_luot,
   chi_phi}}`.

## 5. Xử lý lỗi

- Mô hình lỗi (429, mạng): `respond()` ném → API trả 502 với
  `type(exc).__name__` và thông điệp cắt 200 ký tự, không lộ khoá; lượt
  không được nối vào `history`.
- Công cụ mô phỏng ném (mã hàng sai): trả dict lỗi giống bản thật để mô
  hình xin lại thông tin — đó chính là hành vi cần thử.
- Sandbox không bao giờ được im lặng rơi về thật: `mo_phong` là đường duy
  nhất cho bốn công cụ, và test AST canh.

## 6. Kiểm thử (không gọi API, không cần CSDL)

- `Reply` mới có ba trường mặc định rỗng; `respond()` với `llm.complete`
  giả trả `tool_calls` → `cong_cu` có đúng tên/tham số/kết quả cắt, `vong`
  đúng số vòng, `luoi_bat` đúng mã cho từng lưới (bảy ca).
- `run_tool` trong `bat_thu()`: bốn công cụ ghi không chạm CSDL (monkeypatch
  `db.execute`/`db.fetch` để ném), trả `thu_nghiem: True`; ngoài `bat_thu()`
  đường cũ không đổi. Test AST cho tập `CO_TAC_DUNG_PHU`.
- `respond()` trong sandbox không gọi `ngan_sach.ghi_nhan`, không gọi
  `pipeline.request_video`.
- Sổ chi phí thử: cộng dồn, đổi ngày về 0, trần từ `runtime.STATE`.
- `cham_mot_luot`: `fold`/`_pham`/`tu_cam`/`so_voi_bo_vang` với các ca của
  `scripts/eval.py` giữ nguyên hành vi; `scripts/eval.py` và
  `sinh_bo_cau_vang.py` import từ agent (test canh không còn bản chép).
- Phiên: giới hạn 20/2 giờ/30 lượt; hội thoại thử `mode='human'`,
  `state='closed'`, tài khoản `disabled` (test đọc SQL).
- API: 403 nhân viên; 404/422/409/429; phản hồi không chứa chuỗi khoá; lọc
  `phong_thu` trong hai truy vấn danh sách/tổng quan (test đọc SQL).
- Dashboard: regex `view="phongthu"`, hàm `hoiPhongThu`, `esc(` cho mọi
  chuỗi máy chủ, không có lời gọi trong `refresh()` ngoài lần đầu; JS parse
  được (test hiện có).

## 7. Tài liệu

`docs/van-hanh.md` mục "Thử agent trước khi cho khách gặp": cách dùng,
"ĐANG THỬ" nghĩa là gì, trần thử, và câu nhắc: phòng thử **không** thay bộ
56 câu vàng — nó trả lời "hôm nay nó làm gì", bộ vàng trả lời "nó có ổn
định không". `docs/kien-truc.md` sinh lại nếu schema đổi (không đổi).

## 8. Ngoài phạm vi

Lưu và chia sẻ phiên thử, chạy lại bộ vàng từ dashboard, so sánh hai
provider cạnh nhau, gửi ảnh trong phòng thử (chỉ chữ ở đợt này).
