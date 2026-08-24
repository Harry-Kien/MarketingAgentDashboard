# Đưa hệ thống vào doanh nghiệp

Tài liệu này trả lời đúng một câu: **còn thiếu gì trước khi một doanh
nghiệp thật dùng được.** Nó cố ý nói cả phần chưa xong, vì phần chưa xong
mới là thứ gây tai nạn.

---

## Đã đủ

| | Bằng chứng |
|---|---|
| Chất lượng tư vấn | 51–55/56 bộ câu hỏi vàng · 0/16 bỏ sót chuyển người · 0 từ cấm |
| Giọng văn | 0,05 dấu hiệu lộ bot mỗi câu · 95% câu sạch |
| Độ phủ tri thức | 29/31 khớp tốt · 0 câu không có căn cứ |
| Kiểm thử | 440 ca, dưới 2 giây, chạy tự động mỗi push |
| Bảo vệ truy cập | 17/17 endpoint chặn khi chưa đăng nhập |
| Dữ liệu cá nhân | Nghị định 13/2023 — quyền biết, quyền xoá, thời hạn lưu |
| Kho hàng | tồn kho sống, khoá hàng khi trừ, sổ biến động |
| Đa kênh | Zalo (kéo) + Chatwoot (đẩy), cùng một agent |
| Sao lưu | `scripts/sao_luu.py` |
| Giám sát | canh gác trong tiến trình + `scripts/canh_gac_ngoai.py`, báo qua webhook |
| Chống dò mật khẩu | khoá tạm sau 8 lần sai trong 15 phút |
| Hàng đợi trực | xếp chờ-lâu-nhất-trước, báo động khi có người chờ quá 30 phút |
| Giờ làm việc | ngoài giờ không hứa suông với khách, không báo động vô ích |

---

## Kiểm bằng máy, đừng kiểm bằng trí nhớ

```bash
python -m scripts.san_sang
```

Bảy việc dưới đây là văn xuôi, và văn xuôi thì người ta đọc một lần rồi tin
là mình đã làm. Đúng chuyện đó đã xảy ra ngay trong dự án này: bảng "Đã đủ"
ghi *sao lưu: `scripts/sao_luu.py`* trong khi **không có lịch nào gọi nó**,
và `CANH_GAC_WEBHOOK` để trống nhiều ngày — tức là toàn bộ hệ thống báo
động ghi vào hư không.

Lệnh trên kiểm từng việc và trả về ba mức: **CHẶN** (chạy thật là gây hại)
· **cảnh báo** (chạy được nhưng sẽ đau) · **đủ**. Nó không bao giờ báo xanh
vì "không kiểm được" — dịch vụ đang tắt thì nó nói rõ là chưa kiểm.

---

## Bắt buộc làm trước khi chạy thật

### 1. Đổi mọi bí mật mặc định

```bash
python -m scripts.sinh_token MCP_TOKEN
python -m scripts.sinh_token WEBHOOK_SECRET
```

Hai lệnh trên sinh bí mật và ghi **thẳng vào `.env`, không in ra màn hình
lần nào**. Cách quen thuộc `python -c "...print(token)"` để lại bí mật
trong lịch sử cuộn terminal, lịch sử lệnh ghi ra đĩa, và — đã xảy ra hai
lần trong chính dự án này — trong ảnh chụp màn hình rồi gửi đi.

Kiểm còn giá trị mặc định nào không:

```bash
python -m scripts.san_sang
```

Bắt buộc đổi: `WEBHOOK_SECRET`, mật khẩu Postgres, mật khẩu Chatwoot,
`SECRET_KEY_BASE`. Bí mật mặc định trong tài liệu công khai không phải bí
mật.

### 2. Bật HTTPS và cookie an toàn

```
COOKIE_BAO_MAT=true
```

Không bật thì cookie phiên đi qua mạng ở dạng thường — ai bắt được gói tin
là vào được dashboard. Đặt hệ thống sau Caddy hoặc Nginx có chứng chỉ.

**Chỉ bật sau khi đã có HTTPS thật.** Bật khi còn chạy `http://localhost`
thì trình duyệt không gửi cookie và không ai đăng nhập được.

### 3. Đóng cổng không cần mở ra ngoài

Hiện ZaloCRM nghe ở `0.0.0.0:3080` — cả mạng LAN vào được. Kiểm:

```bash
netstat -ano | findstr LISTENING | findstr "3080 3200 5433 5434 8000"
```

Chỉ cổng của lớp proxy được ra ngoài. Mọi thứ khác chỉ `127.0.0.1`.

### 4. Tạo tài khoản cho từng người, không dùng chung

```bash
python -m scripts.tao_tai_khoan admin "mật khẩu mạnh" --quan-tri
python -m scripts.tao_tai_khoan lan "mật khẩu khác"
```

Dùng chung một tài khoản thì nhật ký ghi "ai xoá dữ liệu khách" thành vô
nghĩa. Vai `nhan_vien` cho người trực; `quan_tri` chỉ cho người thật sự cần
xoá dữ liệu và đổi cấu hình.

### 5. Đặt sao lưu tự động

`scripts/sao_luu.py` đã có nhưng **chưa ai gọi nó theo lịch**. Đặt Task
Scheduler (Windows) hoặc cron chạy hằng ngày, và **thử phục hồi một lần** —
bản sao lưu chưa từng phục hồi thử thì chưa phải bản sao lưu.

### 6. Thay ảnh sản phẩm

44 ảnh hiện tại do model sinh. `manifest.json` ghi rõ *"KHÔNG phải ảnh chụp
sản phẩm thật"*. Bán hàng bằng ảnh không phải sản phẩm mình bán là quảng
cáo sai sự thật.

### 7. Sửa nội dung cho đúng doanh nghiệp mình

`data/knowledge/chinh-sach-thuong-mai.md` và `van-chuyen-doi-tra.md` là
chính sách tôi **đặt ra cho thương hiệu hư cấu**. Phí ship, thời hạn đổi
trả, quy trình xuất hoá đơn của bạn gần như chắc chắn khác.

Sửa xong chạy `python -m scripts.ingest`.

---

## Còn hở, chưa làm

### Zalo cá nhân là vùng xám điều khoản

ZaloCRM điều khiển một nick Zalo cá nhân. Điều khoản của Zalo không cho
phép điều này. Rủi ro thật là **khoá nick**, và nick khoá thì mất luôn lịch
sử hội thoại với khách.

Đường đúng cho production: **Zalo OA**. Nhờ lớp `ChannelAdapter`, đổi sang
OA không đụng agent, RAG, video hay dashboard — chỉ thêm một lớp con.

### Đăng Facebook/Instagram/TikTok chờ nền tảng duyệt

Business Verification + App Review, 1–4 tuần, có thể bị từ chối. Trong lúc
chờ, bài đăng đi qua hàng đợi thủ công — không phải giải pháp tạm bợ mà là
con đường thật, và nó đã được làm cho nhanh.

### Chưa có chăm sóc chủ động

Agent chỉ trả lời khi được hỏi. Không theo khách im lặng, không hỏi thăm
sau khi giao hàng, không nhắc hết hạn dùng.

**Không được làm mảng này trước khi chuyển sang Zalo OA.** Trả lời khi
khách nhắn trước thì còn giống người dùng thật; chủ động gửi đi hàng trăm
tin từ một nick cá nhân thì đúng định nghĩa hành vi mà Zalo dò tìm. Và nick
khoá thì mất luôn toàn bộ lịch sử hội thoại — mất chính tài sản mà hồ sơ
khách đang gây dựng.

### Bộ đo nhiều lượt đã có, nhưng CHƯA CHẠY LẦN NÀO

`scripts/eval_nhieu_luot.py` + 12 kịch bản · 43 lượt đã sẵn sàng, và bộ
chấm của nó có 29 test canh. Nhưng chạy thật thì gọi model thật — tốn tiền
và mất 8-12 phút — nên **chưa có con số nào**. Cho tới khi chạy, khả năng
tư vấn nhiều lượt của agent vẫn là một ẩn số.

```bash
python -m scripts.eval_nhieu_luot --kho   # kiểm bộ khung, không tốn tiền
python -m scripts.eval_nhieu_luot         # chạy thật
```

### Một máy, không có phương án khi máy hỏng

Toàn bộ chạy trên một máy: Postgres, agent, Chatwoot, ZaloCRM. Ổ cứng hỏng
là dừng toàn bộ. Với tiệm nhỏ thì chấp nhận được nếu có sao lưu; với doanh
nghiệp lớn hơn thì cần tách CSDL ra dịch vụ có sao lưu sẵn.

---

## Kết luận thẳng

**Dùng được cho một doanh nghiệp nhỏ** — tiệm mỹ phẩm, 2–5 nhân viên trực,
vài chục tới vài trăm khách mỗi ngày — **sau khi làm xong 7 việc ở trên.**

Chưa dùng được cho quy mô lớn hơn, và chưa nên chạy trên Zalo cá nhân dài
hạn.

Điều quan trọng nhất không phải danh sách trên, mà là: hệ thống này **nói
thật về giới hạn của chính nó**. Agent chuyển người khi vượt thẩm quyền,
chặn nội dung sai luật quảng cáo, không cho bán quá tồn kho, và không đăng
gì lên trang công khai khi chưa có người duyệt.

Một hệ thống biết dừng đúng lúc đáng tin hơn một hệ thống làm được nhiều
việc hơn.
