# Hướng dẫn cho Claude Code

File này được đọc tự động ở đầu mỗi phiên, trên **mọi máy**. Nhờ nó bạn
không phải nhớ gõ prompt mở đầu — chỉ cần nói việc cần làm.

---

## Dự án này là gì

Nhân sự số cho một cửa hàng mỹ phẩm: nhận tin Zalo (và Facebook /
Instagram / WhatsApp / web qua Chatwoot), tra tài liệu công ty để trả lời
**có căn cứ**, gọi công cụ khi cần số liệu thật, tự lên đơn, **chuyển cho
người khi vượt thẩm quyền** — rồi dựng video và soạn bài đăng, luôn sau khi
có người duyệt.

Toàn bộ mã, chú thích và tài liệu viết bằng **tiếng Việt**. Giữ nguyên như
vậy.

---

## Nguyên tắc quan trọng nhất

> **Ràng buộc nằm trong MÃ, không nằm trong prompt.**

Prompt là *yêu cầu*; mô hình sinh xác suất nên vẫn trượt. Với những việc
không được phép sai — luật quảng cáo mỹ phẩm, ranh giới tư vấn y tế, đăng
nội dung công khai — mỗi ràng buộc phải được hiện thực **hai lần**: một lần
trong prompt, một lần trong mã để chặn khi mô hình trượt.

`agent/core/agent.py` có **sáu lớp lưới**, mỗi lớp canh một cách trượt khác
nhau. Đừng gỡ lớp nào mà không đọc `docs/co-so-ly-thuyet.md` mục 6 — có
bằng chứng thực nghiệm giải thích vì sao cần cả sáu.

Cùng lý do đó, **kỹ năng cắm thêm (plugin) là DỮ LIỆU, không phải mã**. Mã
tuỳ ý chạy trong tiến trình agent thì nằm *cùng phía* với sáu lớp lưới —
đọc được biến môi trường, gọi được CSDL, sửa được chính hàm canh nó. Bốn
loại plugin đều chỉ đọc; xem `docs/ky-nang.md` và `agent/ky_nang/`.

---

## Lỗi hay gặp nhất trong repo này: hỏng IM LẶNG

Bốn lỗi nghiêm trọng nhất từng tìm ra đều **không nổ, không ghi nhật ký,
không ai biết**:

| Lỗi | Hậu quả |
|---|---|
| Bộ đọc webhook bỏ tin chỉ có ảnh | khách gửi ảnh vùng da → **tin biến mất hoàn toàn** |
| `_tu_khoa_loai_da()` đọc file không đi theo repo | trí nhớ loại da **chết câm** trên mọi máy mới |
| `zip()` cắt ngầm về danh sách ngắn hơn | đoạn tri thức lặng lẽ không vào kho |
| Bộ đo chỉ tìm dấu hỏi | **xanh giả** — thưởng cho cả câu prompt đã cấm |
| `httpx` ghi URL đầy đủ ở mức INFO | **token Meta vào log** mỗi lần canh gác chạy |
| Git đổi LF→CRLF khi checkout | checksum migration lệch, **ứng dụng không khởi động được** |
| Outbox bỏ cuộc sau 8 lần thử mà không báo ai | **tin nhân viên chết**, khách chờ mãi không có trả lời |

Khi sửa hay thêm gì, luôn hỏi: **hỏng thì có ai biết không?** Nếu không —
thêm phép kiểm, thêm nhật ký, hoặc để nó nổ to.

Xanh giả nguy hiểm hơn đỏ giả: đỏ giả thì người ta đi kiểm, xanh giả thì
không ai kiểm.

---

## Lệnh cần biết

```bash
python -m scripts.san_sang        # sẵn sàng chạy với khách thật chưa
python -m pytest -q               # ~1575 test, khoảng 1 phút, không gọi API
ruff check .                      # chỉ bắt lỗi, không bắt phong cách
```

Sau khi khởi động máy, dựng cả hệ thống bằng **một lệnh**:

```bash
python -m scripts.khoi_dong                  # có cổng công khai
python -m scripts.khoi_dong --khong-tunnel   # chạy nội bộ, không tunnel
```

**Không tunnel vẫn chạy được, và đó là mặc định xuất xưởng**
(`PUBLIC_BASE_URL=http://host.docker.internal:8000` trong `.env.example`).
Zalo cá nhân KHÔNG đi qua tunnel — sidecar gọi thẳng
`127.0.0.1:8000/webhook/native/zalo-personal`; đo được 34/39 tin khách vào
bằng đúng đường ấy. Mất là mất **chiều nhận** của Zalo OA và Facebook, vì
máy chủ của họ cần một địa chỉ công khai để gọi vào. Chiều **gửi** vẫn chạy.

Cờ `--khong-tunnel` trả `.env` về địa chỉ nội bộ, và đó mới là điểm chính:
để nguyên tên miền `trycloudflare` đã chết thì mục "Cổng công khai" đỏ vĩnh
viễn — đỏ thật về kỹ thuật, vô nghĩa về vận hành, và một bảng luôn đỏ là
bảng người ta thôi đọc.

Nó in một dòng cho mỗi tầng và **trả mã thoát khác 0 nếu còn tầng nào
hỏng**. Tên miền tunnel đổi mỗi lần chạy, nên lệnh nhắc dán lại URL webhook
— bỏ bước đó là kênh chết im lặng.

Vì sao cần: hệ thống là **năm tiến trình rời nhau**. Đo được 03.09.2026 —
máy tắt lúc 19:52, bật lại lúc 22:41, **không cổng nào trong
8000/5433/3210/5678 còn nghe**. Ba tiếng đó khách nhắn vào rơi vào hư
không: không lỗi, không nhật ký, và dashboard cũng không chạy để mà hiện
đỏ. `restart: unless-stopped` trong `docker-compose.yml` lo nửa Docker; ba
tiến trình ngoài Docker cần lệnh trên.

Bật riêng từng tầng khi cần gỡ lỗi:

```bash
docker compose up -d              # Postgres+pgvector (5433) + n8n (5678)
python -m uvicorn agent.main:app --reload --port 8000
python -m scripts.chay_tunnel                # tunnel công khai + ghi .env
```

Zalo cá nhân cần **sidecar Node chạy riêng** (`connectors/zalo-personal-
sidecar`). Nó KHÔNG nằm trong `docker-compose`, nên không tự lên sau khi
khởi động máy — và tắt nó là một kiểu hỏng im lặng: dashboard hiện "Gián
đoạn", tin nhân viên vào outbox rồi **chết sau tám lần thử**, khách chờ mãi
không có trả lời.

```bash
python -m scripts.chay_sidecar_zalo          # chạy nền
python -m scripts.chay_sidecar_zalo --hien   # xem log ngay trên terminal
```

Bật xong vào dashboard → **Kết nối** → **Xác minh provider**. Phiên cũ tự
khôi phục nếu còn hạn; hết hạn mới phải quét QR lại.

Sinh lại tài liệu **sau khi đổi schema, thêm kỹ năng, hoặc chạy eval** (có
test canh việc này):

```bash
python -m scripts.sinh_so_do --ghi
python -m scripts.sinh_thuc_nghiem --ghi
python -m scripts.sinh_ky_nang --ghi
```

Đo chất lượng — **gọi API thật, tốn tiền**, hỏi chủ dự án trước khi chạy:

```bash
python -m scripts.sinh_bo_cau_vang     # dựng bộ 56 câu, KHÔNG tốn tiền
python -m scripts.eval                 # 56 câu vàng, một lượt
python -m scripts.eval tuan_thu        # chỉ nhóm tuân thủ — rẻ hơn nhiều
python -m scripts.eval_nhieu_luot      # 12 kịch bản nhiều lượt
python -m scripts.eval_nhieu_luot --kho  # kiểm bộ khung, KHÔNG tốn tiền
```

**Chạy `sinh_bo_cau_vang` TRƯỚC.** `data/eval/golden.jsonl` bị `.gitignore`
chặn — đúng, vì khi thay danh mục mẫu bằng hàng thật thì nó chứa giá thật.
Nhưng vì thế nó không đi theo repo, và `scripts.eval` chết ngay dòng đầu.

Sửa xong `_BUOC_CHUYEN` hay prompt thì **chạy lại nhóm tuân thủ** rồi sinh
lại `docs/thuc-nghiem.md` — có test canh việc tài liệu đã cũ.

Bảng hàng của cửa hàng không có sáu trường tư vấn (`so_cong_bo`,
`khong_chua`, `hsd_thang`, `cach_dung`, `thoi_diem`, `do_pH`). Thiếu chúng
agent KHÔNG nói sai — nó chuyển người, ở đúng những câu lẽ ra tự trả lời
được, mỗi ngày. Hai script này để người điền nốt:

```bash
python -m scripts.sinh_mau_bo_sung           # sinh Excel để người điền
python -m scripts.nap_bo_sung_tu_van         # xem trước, KHÔNG ghi
python -m scripts.nap_bo_sung_tu_van --ghi   # gộp vào catalog.json
```

Tách khỏi `nap_catalog_tu_excel` có chủ ý: bảng giá được xuất lại mỗi lần
đổi giá, phần tư vấn thì viết một lần. Chung một tệp là mỗi lần xuất lại
bảng giá mất sạch phần tư vấn.

---

## Quy ước bắt buộc

**Mỗi ràng buộc phải có test canh.** Không có test thì nó sẽ bị gỡ trong
một lần dọn dẹp nào đó.

**Chú thích giải thích VÌ SAO, không giải thích LÀM GÌ.** Mã đã nói nó làm
gì. Phần đáng ghi lại là lý do — nhất là lý do KHÔNG làm theo cách hiển
nhiên hơn.

**Đừng gõ số vào tài liệu.** `docs/kien-truc.md` và `docs/thuc-nghiem.md`
được **sinh ra** từ mã và dữ liệu. Sửa tay là lần sau bị ghi đè, và có test
bắt việc file đã cũ.

**Bí mật không bao giờ in ra màn hình:**

```bash
python -m scripts.sinh_token MCP_TOKEN
```

Không dùng `python -c "...print(token)"` — nó để lại bí mật trong lịch sử
terminal và trong ảnh chụp màn hình.

**Không chép mã ZaloCRM vào repo.** Nó là AGPL-3.0; chép vào là toàn bộ hệ
thống phải công bố mã nguồn. Submodule trỏ vào fork của chủ dự án, giao
tiếp chỉ qua HTTP API. Xem `docs/co-so-ly-thuyet.md` mục 10.

---

## Thứ KHÔNG đi theo repo

Chạy `python -m scripts.san_sang` để biết còn thiếu gì. Bốn thứ này cố ý
không lên GitHub:

| | Lấy lại thế nào |
|---|---|
| `.env` | `cp .env.example .env` rồi điền `GCP_PROJECT_ID` |
| `data/catalog.json`, `data/knowledge/` | có bản `.example`, dùng ngay được |
| Dữ liệu Postgres | `scripts/sao_luu.py` |
| `video-studio/` | `npx hyperframes init video-studio` |

**Khi viết mã đọc các file này, LUÔN có đường lui sang bản `.example`.**
Đã có hai lỗi vì quên điều đó — xem bảng "hỏng im lặng" ở trên.

---

## Trước khi báo là xong

1. `python -m pytest -q` — phải xanh hết
2. `ruff check .` — phải sạch
3. Đổi schema hoặc chạy eval thì **sinh lại tài liệu**
4. Sửa thứ đọc dữ liệu không-đi-theo-repo thì **thử trên bản clone sạch**
   (CI có job `clone-sach` làm việc này, nhưng biết sớm thì tốt hơn)

Đừng nói "đã xong" khi chưa chạy lệnh và nhìn kết quả.
