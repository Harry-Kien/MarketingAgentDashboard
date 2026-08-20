# Phân phối nội dung và đo hiệu quả

Tài liệu này mô tả bốn năng lực mới: hộp thư đa nền tảng, chọn nick Zalo,
đăng bài tự động, và phân tích hiệu quả bài đăng.

---

## 1. Điều phải nói trước: cái gì bị chặn, và bị chặn bởi ai

Đăng bài lên Facebook / Instagram / TikTok **không bị chặn bởi mã nguồn**.
Nó bị chặn bởi quy trình duyệt của chính các nền tảng:

| Nền tảng | Quyền cần xin | Điều kiện | Thời gian |
|---|---|---|---|
| Facebook Page | `pages_manage_posts`, `pages_read_engagement` | Business Verification (giấy phép kinh doanh) + App Review | 1–4 tuần |
| Instagram | `instagram_content_publish` | như trên, và tài khoản phải là Business | 1–4 tuần |
| TikTok | Content Posting API | Audit ứng dụng | vài tuần |

Đặc biệt với TikTok: ứng dụng **chưa qua audit thì mọi bài bị ép về chế độ
riêng tư**. Đăng thành công về mặt kỹ thuật nhưng không ai nhìn thấy — tình
huống nguy hiểm hơn báo lỗi, vì rất dễ tưởng hệ thống đang chạy tốt.

Hệ thống nói thẳng điều này ra dashboard thay vì im lặng thất bại lúc đăng.

---

## 2. `PublishAdapter` — cách hệ thống không đứng im trong lúc chờ duyệt

Cùng khuôn mẫu với `ChannelAdapter`. Phần trên chỉ biết "đăng bài đi";
đăng bằng đường nào là chuyện của adapter.

```
                    ┌─ n8n ────────── chạy được NGAY (n8n giữ OAuth)
   bài đã duyệt ──> ├─ meta / tiktok ─ mã sẵn sàng, bật khi được duyệt
                    └─ manual ─────── hàng đợi, người tải video và đăng tay
```

`agent/publish/registry.py` chọn adapter đầu tiên **sẵn sàng** theo thứ tự
trên. Hệ quả: hệ thống không bao giờ chết vì thiếu quyền — xấu nhất thì bài
rơi vào hàng đợi thủ công. Khi n8n hoặc App Review có rồi thì tự lên bậc,
không sửa một dòng mã.

Mỗi adapter cài `san_sang() -> (được/không, lý do)`. Dashboard hiển thị
đúng lý do đó, ví dụ:

> `meta: Chưa có Page Access Token. Cần Business Verification + App Review
> quyền pages_manage_posts (1-4 tuần).`

### Vì sao đi qua n8n

n8n đã có sẵn node Facebook Graph, Instagram, TikTok, YouTube, X, và có
wizard OAuth. Đặt xác thực ở đó nghĩa là:

- hệ thống này **không giữ token dài hạn** của mạng xã hội;
- Facebook đổi phiên bản Graph API thì sửa trong n8n, không sửa ở đây.

n8n chạy bất đồng bộ, nên adapter đánh dấu `da_nhan_chua_dang` và chờ n8n
gọi ngược về `/api/posts/{id}/callback` báo kết quả thật.

---

## 3. Không bao giờ tự đăng khi chưa có người duyệt

Đây là ràng buộc cứng, nằm trong mã chứ không nằm trong prompt.

Một câu quảng cáo mỹ phẩm sai luật đăng lên fanpage thật thì không gỡ lại
được ấn tượng, và theo Nghị định 181/2013 **doanh nghiệp chịu trách nhiệm,
không phải công cụ**. Nên mọi bài dừng ở `cho_duyet`.

Vòng đời một bài:

```
   agent soạn ──> cho_duyet ──┬── (có lịch hẹn) ──> da_len_lich ──┐
                              │                                   │
                              └── (đăng ngay) ────────────────────┤
                                                                  v
                                                            dang_dang
                                                                  │
                                            callback báo về ──────┤
                                                                  v
                                                       da_dang  /  loi
```

`schedule_loop` trong `main.py` chỉ đụng tới trạng thái `da_len_lich`. Bài
chưa duyệt không bao giờ lọt vào đó, dù có đặt lịch hay không — **hẹn giờ
là tiện lợi, không phải đường vòng qua khâu duyệt**.

### Hai lớp chặn tuân thủ quảng cáo

1. **Lúc soạn** (`copywriter.py`): model viết xong, mã kiểm danh sách cụm
   cấm, sai thì gửi lại phản hồi **nêu đích danh cụm sai** và bắt viết lại,
   tối đa 3 lần. Nhắc trong prompt thôi thì không đủ — model vẫn trượt.
2. **Lúc duyệt** (`service.py::dang_bai`): kiểm lại lần nữa. Người sửa tay
   nội dung sau khi agent soạn vẫn bị chặn nếu đưa cụm cấm vào.

Cụm cấm lấy từ Thông tư 06/2011/TT-BYT và Nghị định 181/2013: *trị mụn,
đặc trị, chữa, trị nám, xoá nhăn, hết mụn, tái tạo da, trắng da cấp tốc,
thay thế thuốc, cam kết khỏi, hiệu quả 100%, số 1 Việt Nam, tốt nhất thị
trường.*

---

## 4. Vòng phản hồi: số liệu quay lại ảnh hưởng nội dung

Phần lớn hệ thống "đăng bài tự động" dừng ở chỗ đăng xong. Vòng lặp chỉ
khép kín khi số liệu quay lại ảnh hưởng bài sau.

```
   soạn bài ──> đăng ──> thu số liệu ──> tóm tắt bài chạy tốt
      ^                                          │
      └──────────── chèn vào prompt ─────────────┘
```

`analytics.goi_y_cho_agent()` biến số liệu thành vài dòng chữ nhét vào
prompt soạn bài. Nó **trả rỗng khi chưa đủ dữ liệu** (dưới 2 bài có lượt
xem) — thà không gợi ý còn hơn gợi ý dựa trên hai bài đăng, vì đó là nhiễu
chứ không phải xu hướng.

Nguồn số liệu, cùng một hình dạng nên phân tích không cần biết đến từ đâu:

1. Insights API của nền tảng — cần quyền, hiện chưa có
2. n8n gọi về `/api/posts/{id}/metrics` — chạy được ngay
3. Người nhập tay trên dashboard — luôn dùng được

Mỗi lần thu thập ghi **một dòng mới**, không cập nhật đè, để giữ lịch sử:
bài đạt 10k lượt xem sau 1 giờ hay sau 1 tuần là hai câu chuyện khác nhau.

Chỉ số chính là **tỷ lệ tương tác** chứ không phải lượt xem tuyệt đối, vì
nó so sánh được giữa các bài chênh nhau hàng chục lần lượt xem.

---

## 5. Chọn nick Zalo

Doanh nghiệp chạy nhiều nick Zalo (mỗi nhân viên một nick, hoặc tách theo
ngành hàng). Khách nhắn vào nick A mà trả lời đi ra từ nick B thì với khách
đó là **một người lạ nhắn tin**, không phải câu trả lời.

Thứ tự chọn nick khi gửi:

```
   nick ghim riêng cho hội thoại  ->  nick mặc định trên dashboard  ->  .env
```

### Vì sao phải đọc thẳng CSDL của ZaloCRM

Public API của ZaloCRM có contacts, conversations, messages, appointments —
nhưng **không có endpoint nào liệt kê nick Zalo**, và `/api/public/
conversations` cũng không nói hội thoại thuộc nick nào. Endpoint nội bộ thì
cần JWT người dùng, tức phải giữ mật khẩu đăng nhập ZaloCRM trong hệ thống
này — đắt hơn nhiều so với một câu `SELECT`.

Nên `agent/channels/zalocrm_accounts.py` mở kết nối **chỉ đọc** tới Postgres
của ZaloCRM. Không `INSERT`, không `UPDATE`, không sửa một dòng mã nào của
ZaloCRM — nghĩa vụ copyleft AGPL-3.0 vẫn nằm gọn trong container của nó.
Việc **gửi** tin vẫn đi qua Public API như cũ.

---

## 6. Chatwoot — adapter thứ hai chứng minh lớp `ChannelAdapter`

ZaloCRM chỉ nói chuyện được với Zalo. Chatwoot gom Facebook Messenger,
Instagram DM, WhatsApp, khung chat website và email về **cùng một hộp thư,
cùng một hình dạng dữ liệu**. Thêm một adapter ở đây là thêm bốn nền tảng
cho agent, không phải viết lại agent bốn lần.

Điểm đáng nói về mặt kiến trúc: hai kênh chạy **hai cơ chế ngược nhau**.

| | ZaloCRM | Chatwoot |
|---|---|---|
| Cơ chế | KÉO (polling mỗi 4s) | ĐẨY (webhook, tức thì) |
| Chốt SSRF | có, **không tắt được** nếu không sửa mã | có, nhưng **tắt được bằng biến môi trường** |
| Gửi file | Public API chưa hỗ trợ → gửi đường dẫn dạng văn bản | multipart thật |

**Đính chính:** ban đầu tôi ghi ở đây là "Chatwoot không có chốt SSRF".
Điều đó **sai**. Chatwoot cũng chặn, và chặn ngay lần thử đầu tiên:

```
Invalid webhook URL http://host.docker.internal:8000/webhook/chatwoot
  : Hostname 'host.docker.internal' has no public ip addresses
```

Khác biệt thật nằm ở chỗ khác: Chatwoot để sẵn **đường thoát chính thức**
(`lib/safe_fetch.rb` đọc biến `SAFE_FETCH_ALLOW_PRIVATE_NETWORK`), còn
ZaloCRM thì không — muốn qua phải sửa mã nguồn của nó, mà đó là điều ta
cố ý tránh để giữ nghĩa vụ AGPL trong container của nó.

Nên kết luận kiến trúc vẫn đứng, chỉ là vì lý do khác với điều tôi tưởng:
**cùng một trở ngại, hai cách xử lý khác nhau, và lớp `ChannelAdapter`
hấp thụ cả hai** mà agent không biết gì.

Agent, RAG, video, dashboard **không biết và không cần biết** khác biệt đó.
Đó chính là điều lớp `ChannelAdapter` được dựng ra để làm.

`agent/channels/registry.py` định tuyến: `channels.get(conv["channel"])
.send_text(...)`, thay cho chuỗi `if channel == ... elif ...` rải ở năm chỗ.

### Một chi tiết bắt buộc phải xử lý

Chatwoot bắn **mọi** sự kiện về cùng một URL, kể cả tin nhắn ta vừa gửi đi.
Không lọc `message_type != "incoming"` thì agent tự trả lời chính mình
thành vòng lặp vô tận.

### Bật webhook về máy nội bộ

Thêm vào `.env.chatwoot`:

```
SAFE_FETCH_ALLOW_PRIVATE_NETWORK=true
```

Đây là đường thoát của chính Chatwoot, dành cho môi trường chạy nội bộ.
**Không được bật trên máy thật có thể ra Internet** — nó tắt lớp chống
SSRF, tức là ai điều khiển được URL webhook sẽ gọi được vào mạng nội bộ.

### Và một chi tiết về xác thực

Giao diện webhook của Chatwoot **không cho thêm header tuỳ ý**. Bắt buộc
header `x-webhook-secret` là khoá cửa luôn kênh này. Nên webhook nhận secret
ở header **hoặc** ở tham số URL (`?token=...`), so sánh bằng
`secrets.compare_digest` để không rò rỉ secret qua thời gian phản hồi.

Cấu hình trong Chatwoot: *Settings › Integrations › Webhooks*, trỏ về
`http://host.docker.internal:8000/webhook/chatwoot?token=<WEBHOOK_SECRET>`,
chọn sự kiện `message_created`.

---

## 7. Bảng endpoint

| Endpoint | Việc |
|---|---|
| `GET /api/channels` | Kênh nào đang nối, đi bằng cơ chế gì |
| `GET /api/zalo/accounts` | Nick Zalo đang kết nối |
| `POST /api/zalo/account` | Đặt nick mặc định |
| `POST /api/conversations/{id}/account` | Ghim nick cho riêng hội thoại |
| `GET /api/publish/channels` | Kênh đăng bài đi đường nào, vì sao bị chặn |
| `POST /api/posts/draft` | Agent soạn bài (chưa lưu) |
| `GET POST /api/posts` | Hàng đợi bài đăng |
| `POST /api/posts/{id}/approve` | Duyệt → đăng hoặc xếp lịch |
| `POST /api/posts/{id}/cancel` | Huỷ bài |
| `POST /api/posts/{id}/callback` | n8n báo kết quả thật |
| `GET POST /api/posts/{id}/metrics` | Số liệu bài đăng |
| `GET /api/analytics` | Tổng quan hiệu quả + bài chạy tốt nhất |

---

## 8. Cấu hình

Xem `.env.example`, mục *Phân phối bài lên mạng xã hội* và *Chatwoot*.
Không cấu hình gì thì hệ thống vẫn chạy: bài vào hàng đợi thủ công, kênh
Chatwoot tắt, Zalo hoạt động như cũ.

---

## 9. Dựng nhánh n8n trong 5 phút

`docs/n8n-dang-bai.json` là khung workflow nhập thẳng vào n8n được.

1. Mở n8n (http://localhost:5678) › **Workflows** › **Import from File**,
   chọn `docs/n8n-dang-bai.json`.
2. Hai node giữa là **chỗ trống có chú thích** — thay bằng node Facebook
   Graph API / TikTok thật của n8n, rồi nối OAuth trong *Credentials*.
   Cố ý để trống: OAuth phải nối bằng tay trong giao diện n8n, không có
   cách nào xuất ra file được.
3. Bật workflow, copy Production URL của node Webhook.
4. Dán vào `.env`:

   ```
   N8N_WEBHOOK_URL=http://localhost:5678/webhook/marketing-agent-dang-bai
   ```

5. Khởi động lại hệ thống. Màn **Đăng bài** sẽ hiện `n8n` ở bậc sáng thay
   vì `manual`.

Khung này đã nối sẵn đường **callback**: sau khi đăng xong, n8n gọi ngược
về `/api/posts/{id}/callback` để bài chuyển từ `dang_dang` sang `da_dang`
và ghi lại URL bài thật.

---

## 10. Hai khiếm khuyết tìm ra khi kiểm thử đợt này

Ghi lại vì cả hai đều thuộc loại không lộ ra qua thử tay, chỉ lộ khi chạy
bộ 56 câu hỏi vàng.

### Lời gọi mạng đồng bộ nằm trong coroutine

`_vertex_token()` trong `agent/core/llm.py` gọi `_creds.refresh()` của
google-auth — một lời gọi mạng **đồng bộ**. Nó nằm thẳng trong coroutine, nên
trong lúc chờ, toàn bộ tiến trình đứng im: poller ngừng lấy tin Zalo, API
dashboard ngừng trả lời, hàng đợi bài đăng ngừng chạy.

Token ADC hết hạn mỗi giờ nên chuyện này xảy ra đều đặn. Một lần chạy eval
bị treo gần 6 tiếng mà chỉ tốn 12 giây CPU — dấu hiệu điển hình của kẹt chờ
mạng chứ không phải tính toán.

Sửa: `asyncio.to_thread` đẩy sang luồng khác, `asyncio.wait_for` đặt trần 30
giây. Hệ quả đo được trên cùng bộ 56 câu:

| | Trước | Sau |
|---|---|---|
| Độ trễ trung vị | 11.3s | **4.5s** |
| p90 | 44.8s | **12.1s** |

### Lưới an toàn bắt lời hứa chuyển người quá giòn

`_promises_handoff()` dùng danh sách chuỗi cố định. Agent nói *"Em sẽ chuyển
cuộc trò chuyện của mình cho bạn nhân viên có chuyên môn"* — không chuỗi nào
khớp, nên hệ thống tưởng agent tự xử lý được. Khách nhận lời hứa chuyển
người mà không ai nhận việc.

Sửa: thêm mẫu bắt **cấu trúc** `chuyển … cho <người có thẩm quyền>` trong
cùng một câu, thay vì đoán trước từng cách diễn đạt.

### Và một đề bài quá rộng

Luật *"khách xin ngoại lệ chính sách → chuyển người"* nuốt luôn câu hỏi
chính sách bình thường: *"Thanh toán bằng Momo được không ạ?"* bị chuyển
người trong khi câu trả lời nằm ngay ở đoạn RAG xếp hạng nhất. Đã tách rõ
trong `agent/prompts/system.md`: **hỏi chính sách nói gì** khác **đòi điều
chính sách không cho**.

### Bài học chung: luật quan trọng phải có lưới an toàn trong mã

Ba lỗi tìm ra đợt này đều cùng một hình dạng — prompt đã nói rõ, model vẫn
trượt, và không có gì trong hệ thống biết là vừa trượt:

| Prompt cấm | Model vẫn làm | Lưới an toàn đã thêm |
|---|---|---|
| "không hứa suông rồi dừng" | *"Để em kiểm tra giá nha."* rồi dừng | `_stalls()` — ép thêm một vòng gọi công cụ, đúng một lần |
| "nói sẽ chuyển thì phải gọi tool" | nói bằng cách diễn đạt lạ | `_HANDOFF_RE` — bắt cấu trúc, không bắt chuỗi |
| "không dùng cách nói điều trị" | — | `_bat_buoc_chuyen()` (đã có từ trước) |

Nguyên tắc rút ra: **prompt là hướng dẫn, không phải cơ chế bảo đảm.** Điều
gì sai thì gây hậu quả thật — khách bị bỏ rơi giữa chừng, quảng cáo sai
luật — thì phải kiểm bằng mã sau khi model trả lời.

Cùng nguyên tắc đó áp cho bài đăng: `copywriter.py` kiểm tuân thủ sau khi
model viết xong, và `service.py` kiểm lại lần nữa lúc duyệt.

### Một lỗi trong chính bộ chấm điểm

`khong_duoc_co: ["trị nám"]` khớp bên trong câu **từ chối đúng đắn** *"em
không thể tư vấn sản phẩm điều trị nám được"* — tức là phạt agent vì đã làm
đúng. "điều trị" là danh từ y khoa trung tính; "trị nám" mới là cách nói
quảng cáo bị cấm. `scripts/eval.py::_pham()` giờ bỏ qua những lần khớp nằm
ngay sau chữ "điều".

Đáng ghi lại vì đây là loại lỗi nguy hiểm nhất trong đo lường: nó làm chỉ
số xấu đi trong khi hệ thống đang chạy đúng, dẫn tới đi sửa nhầm chỗ.

---

## 11. Agent nói như người thật — và đo được

`agent/core/tu_nhien.py`. Cùng một bài học đã lặp lại bốn lần trong dự án
này: prompt là hướng dẫn, mã mới là bảo đảm.

`system.md` dặn rất kỹ — chào một lần, câu ngắn, không gạch đầu dòng,
không kết bằng "cần hỗ trợ gì thêm không ạ". Model vẫn trượt. Khác ở chỗ
những lỗi này **sửa được** chứ không phải chuyển người:

| Dấu hiệu lộ bot | Cách sửa |
|---|---|
| Chào lại ở tin thứ hai | cắt câu chào, giữ nguyên nội dung |
| Gạch đầu dòng, markdown | bỏ dấu, giữ chữ (Zalo hiện nguyên dấu sao) |
| "Anh chị cần hỗ trợ gì thêm không ạ" | bỏ câu cuối |
| Một khối 800 ký tự | tách thành 2-3 tin, cắt ở ranh giới câu |
| Ba tin nhảy ra cùng một giây | nghỉ giữa các tin theo thời gian gõ |

`cham_diem()` trả về danh sách dấu hiệu — nghĩa là **đo được**, không phải
cảm tính. `lam_tu_nhien()` sửa. `nhip_go()` tính thời gian nghỉ.

Tắt bằng `NHIP_NGUOI_THAT=false` trong `.env` nếu cần trả lời tức thì.

### Hai lỗi tìm ra khi chạy thật qua Chatwoot

**Tin 884 ký tự.** Vòng gộp đuôi trong `_tach_tin` gộp mà không kiểm độ
dài, nên nó tạo ra đúng thứ cả module sinh ra để tránh — gấp 5 lần ngưỡng.
Giờ chỉ gộp khi kết quả vẫn dưới ngưỡng; thà nhắn thừa một tin ngắn còn
hơn dội cho khách một bức tường chữ.

**"Đặc trị" lọt vào lời tư vấn.** Đây là cụm bị cấm theo Thông tư
06/2011/TT-BYT, nhưng nó là **tên nhóm hàng** trong `data/catalog.json`,
nên model đọc được và nhắc lại một cách hoàn toàn tự nhiên. Nguồn rò rỉ
nằm ở **dữ liệu**, không ở prompt — đã đổi thành "Tinh chất chuyên sâu".

Bài học: khi kiểm tuân thủ, phải soi cả dữ liệu tham chiếu chứ không chỉ
soi lời model nói. Một danh mục sản phẩm đặt tên sai luật thì mọi chốt
chặn phía sau đều vô ích.

---

## 12. Chiến dịch đa nền tảng — một ý tưởng, bốn bài viết riêng

Cách làm đa nền tảng phổ biến nhất là copy-paste một caption ra bốn chỗ.
Đó cũng là cách kém hiệu quả nhất, vì bốn nền tảng có bốn hành vi người
dùng khác hẳn nhau:

| Nền tảng | Điều quyết định |
|---|---|
| TikTok | 3 giây đầu. Không có móc câu là lướt qua |
| Facebook | người đọc chịu khó hơn, kể được một tình huống |
| Instagram | sống bằng hashtag và cảm giác, không phải mô tả tính năng |
| YouTube | tiêu đề dưới 60 ký tự vì bị cắt trong danh sách gợi ý |

`agent/publish/chien_dich.py` gọi `copywriter.soan()` **riêng cho từng
kênh** — cùng ý tưởng, cùng dữ liệu sản phẩm, bốn bản viết khác nhau. Bốn
kênh soạn song song vì chúng độc lập.

Chi phí đo được: **$0.0025 cho một chiến dịch 4 nền tảng** (~63đ).

Kết quả thật từ một lần chạy:

```
FACEBOOK   "Bí quyết cho làn da dầu mùa hè"        5 hashtag
INSTAGRAM  "Da dầu mùa hè? Đừng lo!"              11 hashtag
TIKTOK     "Da dầu mùa hè cứ đổ dầu, rửa mặt
            xong lại khô căng khó chịu?"           4 hashtag  <- mở bằng câu hỏi
YOUTUBE    "Kiềm dầu mùa hè: Da sạch thoáng,
            không khô căng"                       tiêu đề ngắn
```

### Giãn giờ đăng

Đăng cả bốn nền tảng cùng một phút là dấu hiệu tự động rõ nhất, và nó cũng
tự cạnh tranh với chính mình trên bảng tin. Mặc định giãn 30 phút.

**Một bẫy đã sửa:** ban đầu, giãn cách chỉ có tác dụng khi người dùng nhập
giờ bắt đầu. Không nhập thì mốc là `None` → lịch mọi bài đều `None` → cả
bốn bài đăng cùng lúc, trong khi ô "giãn cách 30 phút" vẫn hiện trên màn
hình. Sai mà không báo lỗi. Giờ mặc định lấy thời điểm hiện tại.

Kiểm chứng: duyệt một chiến dịch 3 kênh giãn 45 phút →
`['dang_dang', 'da_len_lich', 'da_len_lich']`.

### Vẫn không vòng qua khâu duyệt

Chiến dịch soạn nhanh hơn, không quyết định thay người. `tests/
test_chien_dich.py` soi thẳng mã nguồn: `tao()` không được phép gọi
`dang_bai()` hay `duyet()`.

---

## 13. Bộ đăng thủ công — đường DUY NHẤT chạy tới cả 4 nền tảng hôm nay

Chừng nào Facebook và TikTok chưa duyệt quyền, đây không phải giải pháp
tạm bợ mà là con đường thật. Nên làm cho nó nhanh và không sai sót còn giá
trị hơn ngồi chờ App Review.

`GET /api/posts/{id}/kit` trả về mọi thứ cần trong một lần bấm:

- **caption đã ghép sẵn hashtag** đúng định dạng nền tảng
- **link tải video** về máy
- **lưu ý riêng từng nền tảng** — để người đăng không phải nhớ và không bị
  từ chối vì sai định dạng:

  > Instagram: chỉ đăng được từ điện thoại. Reels nhận video dọc 9:16, tối đa 90 giây.
  > TikTok: video dọc 9:16. Caption tối đa 2.200 ký tự, hashtag tính trong giới hạn đó.
  > YouTube: Shorts cần video dọc dưới 60 giây và có #Shorts trong tiêu đề hoặc mô tả.

Đăng xong bấm **Đã đăng xong** và dán link bài thật. Có link mới đo được
hiệu quả — không có nó thì bài biến mất khỏi hệ thống ngay sau khi đăng và
vòng phản hồi số liệu đứt.

---

## 14. Mở khoá n8n — hai bước bạn phải tự làm

n8n đang chạy ở `http://localhost:5678` nhưng **chưa có tài khoản chủ**
(`showSetupOnFirstLoad: true`). Tôi không tạo tài khoản thay bạn.

**Bước 1 — tạo tài khoản chủ.** Mở http://localhost:5678, điền email và
mật khẩu của bạn. Mất 30 giây.

**Bước 2 — nhập workflow.** Trong n8n: *Workflows › Import from File*, chọn
`docs/n8n-dang-bai.json`. Hai node giữa là chỗ trống có chú thích — thay
bằng node Facebook Graph / TikTok thật và nối OAuth trong *Credentials*.
(Cố ý để trống: OAuth phải nối bằng tay trong giao diện n8n, không xuất ra
file được.)

**Bước 3 — bật và dán URL.** Bật workflow, copy Production URL của node
Webhook, dán vào `.env`:

```
N8N_WEBHOOK_URL=http://localhost:5678/webhook/marketing-agent-dang-bai
```

Khởi động lại hệ thống. Màn **Đăng bài** sẽ hiện `n8n` ở bậc sáng thay vì
`manual`, và bài đăng đi thẳng qua n8n thay vì vào hàng đợi tay.

---

## 15. Đo giọng văn — biến lời khẳng định thành con số

"Agent nói như người thật" là điều dễ nói và khó chứng minh. `tu_nhien
.cham_diem()` đã có từ trước nhưng chưa được dùng để đo, nên nó vẫn chỉ là
một lời khẳng định.

### Phải đo ở HAI mốc, không phải một

Bản đầu tôi chỉ đo văn bản model vừa sinh ra và được **0,45 dấu hiệu/câu,
62% sạch**. Con số đó sai lệch: phần lớn dấu hiệu là "tin quá dài" (21/56
lần), mà những tin đó đã được `lam_tu_nhien()` tách thành 2-3 tin ngắn
**trước khi gửi**. Khách không bao giờ nhận bức tường chữ đó.

Chỉ báo con số thô là tự bôi xấu mình. Chỉ báo con số sau xử lý là giấu đi
việc prompt còn yếu. Nên báo cả hai:

```
--- Giọng văn ---
Văn bản model sinh ra:
  dấu hiệu lộ bot   0.45 / câu   |  sạch 35/56 (62%)
  độ dài trung bình 180 ký tự   (ngưỡng tin nhắn: 180)
KHÁCH THẬT SỰ NHẬN (sau khi tách tin, bỏ markdown):
  dấu hiệu lộ bot   0.09 / câu   |  sạch 51/56 (91%)   <-- con số thật
  số tin mỗi lượt   1.5
Hay gặp nhất (trong văn bản thô):
  tin quá dài              21 lần
  gạch đầu dòng             4 lần
```

Hai con số nói hai chuyện: **0,45** đo prompt hiệu quả tới đâu, **0,09** là
chất lượng khách thật sự trải nghiệm. Cột "hay gặp nhất" chỉ đúng chỗ cần
sửa tiếp thay vì phải đọc lại 56 câu trả lời.

Dùng `lan_dau=True` khi chấm, vì mỗi ca eval là một hội thoại mới — chào ở
đó là đúng, không phải lỗi.

---

## 16. Quan sát chi phí — bỏ Langfuse, dùng dữ liệu của chính mình

Langfuse chạy trong container suốt nhiều giờ mà **không nhận một dòng nào**:
khoá để rỗng, và không có mã nào gửi trace lên. Tốn ~195MB RAM để làm nền,
trong khi tài liệu thì ghi là hệ thống có tracing.

Đã chuyển nó vào profile `trace` nên `docker compose up -d` không khởi động
nó nữa. Bật lại khi cần:

```bash
docker compose --profile trace up -d
```

Thay vào đó, `GET /api/cost` dựng báo cáo từ bảng `messages` — nơi đã lưu
sẵn model, token vào/ra, token đọc cache, chi phí và độ trễ **từ ngày đầu**.
Không cài thêm gì, không tạo tài khoản, không có container nằm không.

Số thật từ một lần chạy:

| | |
|---|---|
| Chi phí 7 ngày | 1.290đ / 23 tin |
| Token vào | 53.702 |
| **Đọc từ cache** | **86,8%** |
| claude-sonnet-5 | 9 tin, độ trễ 1,6s |
| gemini-2.5-flash | 14 tin, độ trễ 11,3s |

Con số 86,8% là thứ đáng nói nhất: Vertex **không tự cache**, phải tự đặt
`cache_control` lên khối ổn định và để ngữ cảnh RAG biến động nằm sau. Đặt
ngược lại thì mọi request đều ghi cache mới và không bao giờ đọc lại được.
Đây là bằng chứng đo được rằng việc đó có ăn thua.

---

## 17. Một lần suýt phá thứ đang chạy tốt

Tôi đã viết `don_viec_ket()` trong `main.py` để dọn video kẹt khi khởi động
lại, và thêm một endpoint `/videos/{id}/retry`.

Cả hai đều **thừa và có hại**. `agent/video/worker.py` đã có sẵn:

- hàng đợi bền vững trong Postgres, không phải trong bộ nhớ tiến trình
- `reclaim_stale()` nhặt lại việc dở khi app khởi động
- `FOR UPDATE SKIP LOCKED` để hai tiến trình không giẫm chân nhau
- và nó đã được nối vào `lifespan` từ trước

Mã tôi viết **xung đột trực tiếp**: nó đánh dấu video kẹt là `failed` TRƯỚC
khi `reclaim_stale()` kịp đưa chúng về hàng đợi. Endpoint thì trùng route —
FastAPI dùng cái đăng ký trước, nên phần tôi viết là mã chết.

Đã gỡ cả hai. Bài học: trước khi sửa một vấn đề đã biết, đọc lại xem có ai
sửa rồi chưa — nhất là trong dự án nhiều người cùng chạm vào.
