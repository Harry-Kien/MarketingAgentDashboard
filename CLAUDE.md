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

`agent/core/agent.py` có **năm lớp lưới**, mỗi lớp canh một cách trượt khác
nhau. Đừng gỡ lớp nào mà không đọc `docs/co-so-ly-thuyet.md` mục 6 — có
bằng chứng thực nghiệm giải thích vì sao cần cả năm.

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

Khi sửa hay thêm gì, luôn hỏi: **hỏng thì có ai biết không?** Nếu không —
thêm phép kiểm, thêm nhật ký, hoặc để nó nổ to.

Xanh giả nguy hiểm hơn đỏ giả: đỏ giả thì người ta đi kiểm, xanh giả thì
không ai kiểm.

---

## Lệnh cần biết

```bash
python -m scripts.san_sang        # sẵn sàng chạy với khách thật chưa
python -m pytest -q               # 440 test, dưới 4 giây, không gọi API
ruff check .                      # chỉ bắt lỗi, không bắt phong cách
```

```bash
docker compose up -d              # Postgres+pgvector (5433) + n8n (5678)
python -m uvicorn agent.main:app --reload --port 8000
```

Sinh lại tài liệu **sau khi đổi schema hoặc chạy eval** (có test canh việc
này):

```bash
python -m scripts.sinh_so_do --ghi
python -m scripts.sinh_thuc_nghiem --ghi
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
