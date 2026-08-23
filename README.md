# Marketing Agent — MVP

Nhân sự số cho doanh nghiệp: nhận tin nhắn Zalo (và Facebook / Instagram /
WhatsApp / web qua Chatwoot), tra tài liệu công ty để trả lời **có căn cứ**,
gọi hệ thống nghiệp vụ khi cần số liệu thật, tự lên đơn, chuyển cho người khi
vượt khả năng — sản xuất video marketing có giọng đọc **khớp đúng thời lượng
nội dung**, rồi soạn bài và phân phối lên mạng xã hội **sau khi có người
duyệt**, đo hiệu quả và mang số liệu đó quay lại cho lần soạn sau.

Chạy trên **Vertex AI** (Claude + về sau là Veo), một GCP project, một hóa đơn.

---

## Bốn nguyên tắc kiến trúc

| Nguyên tắc | Nằm ở đâu |
|---|---|
| **ChannelAdapter là ranh giới** — đổi Zalo cá nhân sang Zalo OA chỉ là viết thêm một lớp con, không đụng agent/RAG/video | `agent/channels/base.py` |
| **Âm thanh trước, hình sau** — thời lượng cảnh đo bằng `ffprobe` từ file giọng đọc thật, không bao giờ để model đoán | `agent/video/timing.py` |
| **Không phát ngôn không căn cứ** — giá, tồn kho, tình trạng đơn chỉ đến từ tool; thiếu căn cứ thì chuyển người | `agent/core/tools.py`, `agent/prompts/system.md` |
| **Vertex không có auto-caching** — phải tự đặt `cache_control` lên khối ổn định, ngữ cảnh RAG biến động nằm sau | `agent/core/llm.py` → `cached_system()` |
| **PublishAdapter là ranh giới thứ hai** — đăng bài đi qua n8n, API chính thức, hay hàng đợi thủ công đều cùng một hợp đồng; thiếu quyền nền tảng thì tụt bậc chứ không chết | `agent/publish/base.py` |
| **Nội dung ra công chúng luôn phải có người duyệt** — ràng buộc nằm trong mã, không nằm trong prompt | `agent/publish/service.py` |

---

## Cài trên máy mới

Repo mang sẵn dữ liệu mẫu để chạy được ngay sau khi clone, **chưa cần** Zalo,
chưa cần danh mục thật, chưa cần tài liệu công ty:

- `data/catalog.example.json` — 22 sản phẩm mô phỏng. Mã tự dùng file này khi
  chưa có `data/catalog.json` (bản thật không lên repo).
- `data/products/` — 44 ảnh sản phẩm cho 22 mã, đủ để agent dựng video ngay.
- `data/knowledge.example/` — tài liệu mẫu cho RAG.
- `data/mau/` — ảnh tổng hợp cho bài test bộ dựng.

Việc phải làm khi chuyển sang dùng thật: đặt danh mục thật vào
`data/catalog.json`, tài liệu thật vào `data/knowledge/` rồi nạp, và thay ảnh
sinh trong `data/products/<mã>/` bằng **ảnh chụp sản phẩm thật** — ảnh trong
repo là do model sinh, không phải hàng thật của bạn.

Kiểm nhanh xem máy đã sẵn sàng chưa, không cần Postgres hay Zalo:

```bash
.venv/Scripts/python.exe -m scripts.test_render --images data/mau
```

Ra được `data/videos/_test/video.mp4` với sai lệch thời lượng dưới 0,6 giây
là bộ dựng chạy đúng.

---

## Chạy trong 15 phút

### 0. Clone kèm submodule

```bash
git clone --recurse-submodules https://github.com/Harry-Kien/MarketingAgentDashboard.git
cd MarketingAgentDashboard
.\scripts\cai_dat.ps1
```

Quên `--recurse-submodules` thì thư mục `ZaloCRM/` rỗng. Sửa bằng:

```bash
git submodule update --init --recursive
```

**Submodule trỏ vào `Harry-Kien/ZaloCRM`** — bản fork thuộc tài khoản chủ
dự án, không phải repo của người lạ. Thượng nguồn xoá repo hay đổi lịch sử
cũng không làm hỏng hệ thống này; nhận bản vá thì `git pull upstream`.

**Vì sao vẫn là submodule chứ không chép mã vào repo:** nó cấp phép
AGPL-3.0. Chép mã vào đây là gộp hai thứ làm một, và Điều 13 của giấy phép
buộc công bố **toàn bộ mã nguồn hệ thống** cho bất kỳ ai dùng nó qua mạng.
Submodule là một con trỏ tới repo của họ — mã của họ ở lại repo của họ,
dưới giấy phép của họ, còn bạn vẫn clone một lệnh là đủ.

### 1. Điều kiện

- Docker Desktop **đang chạy**
- Python 3.11+ · Node 22+ · FFmpeg (kèm `ffprobe`) trong PATH
- GCP project đã bật Vertex AI
- **Google Cloud SDK** — nếu `gcloud` báo *not recognized*:

```bash
winget install --id Google.CloudSDK -e
```

Sau khi cài **phải mở terminal mới** thì `gcloud` mới vào PATH. Rồi:

```bash
gcloud auth application-default login
```

### 2. Cấu hình

```bash
cp .env.example .env
```

Bắt buộc điền `GCP_PROJECT_ID`. Các mục khác có thể để mặc định lúc đầu.

### 3. Hạ tầng

```bash
docker compose up -d
```

Dựng Postgres+pgvector (cổng **5433**), Langfuse (cổng **3001**).

### 4. Cài thư viện Python

Dự án dùng venv riêng tại `.venv`, không đụng Python hệ thống.

```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

### 5. Chạy

```bash
.venv/Scripts/python.exe -m uvicorn agent.main:app --reload --port 8000
```

Mở **http://localhost:8000**

### 6. Xem dashboard có dữ liệu ngay (chưa cần Zalo/Vertex)

```bash
.venv/Scripts/python.exe -m scripts.demo_seed
```

Xoá sạch dữ liệu mẫu: thêm `--clear`.

---

## Nối Zalo (giai đoạn 1)

ZaloCRM chạy **compose riêng của nó**. Đây là chủ ý, không phải lười: giữ
nguyên bản, không fork, không sửa — nghĩa vụ copyleft AGPL nằm gọn trong
container đó, không lan sang mã nguồn này.

```bash
git clone https://github.com/locphamnguyen/ZaloCRM.git
```

```bash
cd ZaloCRM && cp .env.example .env && docker compose up -d
```

Rồi: mở web UI → quét QR bằng **tài khoản Zalo phụ** (không dùng tài khoản
chính) → Settings lấy `X-API-Key` → đặt webhook về:

```
http://host.docker.internal:8000/webhook
```

> Trên Windows/Docker Desktop **phải** dùng `host.docker.internal`, không dùng
> `localhost` — container không tự gọi được vào host.

Điền `ZALOCRM_API_KEY` vào `.env` rồi khởi động lại app.

---

## Giọng đọc

Không có giọng đọc thì video **câm** và thời lượng chỉ là ước lượng âm tiết —
mất đúng thứ khiến hệ thống này khác các bộ dựng video khác. Kiểm trước:

```bash
.venv/Scripts/python.exe -m scripts.test_tts
```

Hai đường, hệ thống tự chọn đường nào đang chạy (`TTS_PROVIDER=auto`):

| Đường | Cần gì | Chi phí |
|---|---|---|
| **Google Cloud TTS** | Bật một API trên chính project GCP đang dùng | ~0,005 USD mỗi video 30 giây |
| **viet-tts** | Clone repo, tải model, tự dựng | Miễn phí |

Đường nhanh nhất:

```bash
gcloud services enable texttospeech.googleapis.com
```

Đường miễn phí: dựng [viet-tts](https://github.com/dangvansam/viet-tts) theo
README của nó rồi trỏ `TTS_BASE_URL` vào cổng nó mở.

---

## Chatwoot — hộp thư nhiều nền tảng

Chatwoot gom Facebook Messenger, Instagram DM, WhatsApp, chat website và
email về **một hộp thư**. Agent trả lời y hệt nhau ở mọi nơi; chỉ dashboard
và thống kê là tách ra.

```bash
docker compose -f docker-compose.chatwoot.yml up -d
```

Rồi trong Chatwoot: **Settings › Integrations › Webhooks**, trỏ về

```
http://host.docker.internal:8000/webhook/chatwoot?token=<WEBHOOK_SECRET>
```

và chọn sự kiện `message_created`. Điền `CHATWOOT_*` vào `.env`.

Mỗi hội thoại lưu **nền tảng gốc** riêng, nên huy hiệu ghi "Facebook" hay
"Instagram" chứ không phải "Chatwoot", và mục *Số hiệu* tách từng nền tảng
thành một dòng.

### Vì sao KHÔNG gộp vào `docker-compose.yml`

Gộp trông gọn hơn nhưng **không giảm được container nào**: Chatwoot cần
Rails, Sidekiq, Postgres và Redis riêng dù nằm ở file nào.

Đổi lại nó thêm một rủi ro thật. Docker đặt tên volume theo *tên project*,
mà tên project lấy từ tên thư mục. Gộp file là đổi project, và volume
`chatwoot_chatwoot_pg` thành `marketing_chatwoot_pg` — một volume RỖNG. Hộp
thư, kết nối OAuth, toàn bộ lịch sử khách trông như biến mất.

Tên volume nay đã được **ghim tuyệt đối** trong `docker-compose.chatwoot.yml`
nên dữ liệu bám vào volume chứ không bám vào tên thư mục. Nhưng hai file vẫn
tách nhau, vì tách đúng ranh giới: Chatwoot là dịch vụ bên ngoài có vòng đời
riêng, `docker compose down` của dự án này không được phép kéo nó theo.

---

## Nạp tài liệu cho agent

Không có tài liệu thì agent không có căn cứ và sẽ chuyển hết cho người — đúng
thiết kế, nhưng vô dụng. Nạp bằng một trong hai cách:

- **Dashboard** → mục *Tri thức* → dán nội dung
- **Hàng loạt**: đặt file `.md`/`.txt` vào `data/knowledge/` rồi:

```bash
.venv/Scripts/python.exe -m scripts.ingest data/knowledge
```

Kiểm tra agent tìm được gì bằng ô *Thử truy vấn* — không tốn lượt gọi model.

---

## Video

Bộ dựng **đã chạy được ngay** qua backend `ffmpeg` — không cần cài thêm gì.
Kiểm chứng bất cứ lúc nào, không cần Postgres/Vertex/Zalo:

```bash
.venv/Scripts/python.exe -m scripts.test_render
```

Bật backend chính (HyperFrames) — lệnh này **hỏi tương tác**, phải chạy trong
terminal thật, không chạy được trong script nền:

```bash
npx hyperframes init video-studio
```

```bash
cd video-studio && npx skills add heygen-com/hyperframes --full-depth
```

Giọng đọc (khuyến nghị — thiếu nó thì thời lượng chỉ là ước lượng):

```bash
git clone https://github.com/dangvansam/viet-tts
```

Chạy theo README của repo, rồi trỏ `TTS_BASE_URL` trong `.env` tới cổng nó mở.

**Dây chuyền:** (ảnh → **nhìn ảnh**) → kịch bản → giọng đọc (viet-tts) →
**đo bằng ffprobe** → dựng hình → MP4 dọc 1080×1920.

Hai bước in đậm là hai chỗ hệ thống **đo thực tế** thay vì tin model đoán.

### Video từ ảnh sản phẩm

Kéo-thả ảnh vào mục *Video* trên dashboard (tối đa 8 ảnh). Agent tự xem từng
ảnh trước khi viết kịch bản, và kết quả xem được lưu lại để soi:

```bash
.venv/Scripts/python.exe -m scripts.test_vision data/mau
```

Mỗi ảnh cho ra mô tả, màu chủ đạo, độ sáng, và **vùng trống để đặt chữ** —
trường cuối lái toàn bộ bố cục, nên chữ tránh sản phẩm thay vì luôn nằm giữa
khung. Ảnh mờ, quá tối, hay đã có chữ quảng cáo in sẵn bị loại tự động.

Ảnh được xoá sạch EXIF khi nhận — ảnh điện thoại mang theo toạ độ GPS, mà
video thì đăng công khai.

Thử toàn tuyến, không cần Postgres hay Zalo:

```bash
.venv/Scripts/python.exe -m scripts.test_render --images data/mau --vision
```

Bỏ `--vision` thì phân tích ảnh được gán tại chỗ, không tốn lời gọi model.

### Ba bậc dựng hình

Bộ dựng tự tụt bậc: `veo` → `hyperframes` → `ffmpeg`. Bậc cuối chỉ cần ffmpeg
trong PATH nên dây chuyền không bao giờ đứng vì thiếu hạ tầng. Thẻ video ghi
rõ bậc nào đã dựng, bậc nào bị bỏ qua và vì sao, thời lượng là **đo thật**
hay **ước lượng**.

Bậc Veo **tắt theo mặc định** vì tính tiền theo giây video. Bật bằng cách đặt
`VEO_MODEL` trong `.env`.

### Hàng đợi — video chạy độc lập với người dùng

Video không dựng ngay lúc bấm nút. Nó vào hàng đợi trong Postgres, thợ nền
(`agent/video/worker.py`) nhận và chạy. Ba điều đổi được nhờ vậy:

- **App tắt giữa chừng không mất việc.** Khởi động lại thì việc dở dang được
  nhặt lại và chạy tiếp. Trước đây video kẹt vĩnh viễn ở trạng thái dở, không
  một dòng lỗi nào.
- **Không tranh CPU với khách.** Mặc định dựng một video tại một thời điểm
  (`VIDEO_WORKERS`), vì ffmpeg nặng mà nó chạy chung tiến trình với việc trả
  lời khách đang đợi.
- **Video lỗi chạy lại được** bằng nút *Chạy lại* trên thẻ video. Ảnh sản phẩm
  giữ nguyên, không phải tải lên lần nữa.

Việc nhận dùng `FOR UPDATE SKIP LOCKED` nên chạy nhiều app trên cùng một DB
cũng không ai giẫm chân ai.

Phụ đề được burn cứng vào hình, lấy mốc thời gian từ chính số đo ffprobe.
Khi chưa có TTS, đây là thứ duy nhất truyền được lời thoại.

Video xong ở trạng thái **chờ duyệt** — hệ thống không bao giờ tự đăng.

---

## Phân phối nội dung và đo hiệu quả

Hộp thư đa nền tảng, chọn nick Zalo, đăng bài lên mạng xã hội, phân tích
hiệu quả — kể cả phần **bị chặn bởi quy trình duyệt của nền tảng** và cách
hệ thống vẫn chạy trong lúc chờ: [docs/phan-phoi-noi-dung.md](docs/phan-phoi-noi-dung.md)

Tóm tắt ngắn:

- Đăng thẳng lên Facebook/Instagram cần Business Verification + App Review
  (1–4 tuần). TikTok cần audit; **chưa audit thì bài bị ép về riêng tư**.
- Nên đường mặc định đi qua **n8n** (đã chạy sẵn ở cổng 5678) — n8n giữ
  OAuth, hệ thống này không giữ token dài hạn của mạng xã hội.
- Không cấu hình gì thì bài vào **hàng đợi thủ công**: hệ thống không bao
  giờ chết vì thiếu quyền nền tảng.
- Bài **không bao giờ tự đi khi chưa có người duyệt**, kể cả khi đã hẹn giờ.

---

## Bài test nghiệm thu MVP

Nhắn từ điện thoại vào tài khoản Zalo đã quét QR:

| # | Nhắn | Phải thấy |
|---|---|---|
| 1 | "Ghế Aurora M1 giá bao nhiêu?" | Đúng 4.290.000đ, gọi qua tool, có trích nguồn |
| 2 | "Bàn nâng hạ còn hàng không?" | Nói hết hàng — không bịa |
| 3 | "Bảo hành mấy năm?" | Trả lời từ tài liệu, ghi rõ nguồn |
| 4 | **"Có ship sang Nhật không?"** | **Nói không biết và chuyển người.** Đây là bài test quan trọng nhất |
| 5 | "Làm video giới thiệu ghế Aurora M1" | Video xuất hiện ở mục Video, sau vài phút thành *chờ duyệt* |

Bài 4 mới là bài đáng giá. Một agent trả lời đúng bốn câu đầu nhưng bịa ở câu
thứ năm thì không dùng được trong doanh nghiệp.

---

## Vận hành

| Nút | Ở đâu | Tác dụng |
|---|---|---|
| **Ngắt** | Góc phải đầu trang | Agent ngừng ngay, mọi tin chuyển người. Không cần khởi động lại |
| **Gợi ý / Tự động** | Cạnh nút ngắt | *Gợi ý* = agent soạn, bạn bấm duyệt mới gửi. Chạy chế độ này vài ngày đầu |
| **Tôi tiếp quản** | Trong hội thoại | Khoá hội thoại lại cho người, agent không chen vào nữa |

Mặc định là **Gợi ý**. Đừng bật *Tự động* trước khi xem đủ vài chục hội thoại
thật.

---

## Tài liệu cho báo cáo

| Tài liệu | Nội dung | Sinh ra từ |
|---|---|---|
| [docs/co-so-ly-thuyet.md](docs/co-so-ly-thuyet.md) | 10 kỹ thuật hệ thống thực sự dùng, kèm nguồn gốc | viết tay |
| [docs/kien-truc.md](docs/kien-truc.md) | sơ đồ khối · luồng tin · use case · ERD 16 bảng | `agent/schema.sql` |
| [docs/thuc-nghiem.md](docs/thuc-nghiem.md) | phương pháp đo · kết quả 13 lần chạy · giới hạn | `data/eval/*.json` |

```bash
.venv/Scripts/python.exe -m scripts.sinh_so_do --ghi
.venv/Scripts/python.exe -m scripts.sinh_thuc_nghiem --ghi
```

Cả hai **sinh từ mã và dữ liệu thật**, không gõ tay — và có test canh việc
file trong repo khớp với thứ bộ sinh tạo ra. Con số gõ tay là con số sẽ
sai: README từng ghi bộ vàng "55/56 (98%)", tài liệu doanh nghiệp ghi
"56/56", trong khi lịch sử 13 lần chạy cho dải **50–56**.

---

## Kiến trúc — sơ đồ

[docs/kien-truc.md](docs/kien-truc.md): sơ đồ khối, luồng một tin nhắn,
trường hợp sử dụng, và ERD 16 bảng.

Phần ERD **sinh ra từ `agent/schema.sql`**, không vẽ tay — sơ đồ vẽ tay
đúng đúng một ngày, ngày người ta vẽ nó:

```bash
.venv/Scripts/python.exe -m scripts.sinh_so_do --ghi
```

Có test canh việc file trong repo khớp với thứ bộ sinh tạo ra, nên tài
liệu không thể lệch khỏi schema mà không ai biết.

---

## Cấu trúc

```
agent/
  main.py              webhook + phục vụ dashboard
  config.py            mọi cấu hình đọc từ .env
  runtime.py           công tắc ngắt, chế độ, ngưỡng (đổi lúc chạy)
  channels/
    base.py            ChannelAdapter — RANH GIỚI KIẾN TRÚC
    registry.py        định tuyến theo kênh, một chỗ duy nhất
    zalocrm.py         Zalo cá nhân — KÉO (chốt SSRF chặn webhook)
    zalocrm_accounts.py  đọc chỉ-đọc CSDL ZaloCRM để liệt kê nick
    chatwoot.py        Facebook/Instagram/WhatsApp/web — ĐẨY (webhook)
  core/
    llm.py             AnthropicVertex + cache_control thủ công + tính giá
    rag.py             pgvector + embedding tiếng Việt  ← cắm RAG pháp lý vào đây
    tools.py           tool nghiệp vụ  ← thay bằng ERP ở giai đoạn 2
    agent.py           vòng lặp tool + trần chi phí + escalation
  video/
    pipeline.py        điều phối dây chuyền
    tts.py             giọng đọc
    timing.py          ffprobe — mảnh làm nên video khớp lời
    renderer.py        hyperframes + lưới an toàn ffmpeg
  publish/
    base.py            PublishAdapter — RANH GIỚI PHÂN PHỐI
    registry.py        n8n -> API chính thức -> hàng đợi thủ công
    n8n.py             chạy được ngay, n8n giữ OAuth mạng xã hội
    meta.py            Facebook/Instagram — chờ App Review
    tiktok.py          TikTok — chờ audit
    manual.py          lưới an toàn cuối cùng
    copywriter.py      agent soạn caption, kiểm tuân thủ 2 lớp
    service.py         vòng đời bài: soạn -> duyệt -> đăng
    analytics.py       số liệu và vòng phản hồi về prompt
  api/routes.py        API dashboard
dashboard/             giao diện, không build step
scripts/               nạp tài liệu, dữ liệu trình diễn
```

---

## Chuyển sang giai đoạn 2 (production)

| Thay gì | Bằng gì | Sửa ở đâu |
|---|---|---|
| ZaloCRM (`zca-js`) | Zalo OA Open API | Thêm `agent/channels/zalo_oa.py`, xử lý cửa sổ 48h trong `can_send_now()` |
| Inbox ZaloCRM | Chatwoot (MIT) | Adapter mới, license sạch |
| Tool dữ liệu mẫu | ERP / KiotViet / MISA | Chỉ sửa thân hàm trong `core/tools.py` |

Phần agent, RAG, video, dashboard **không đổi** — đó là mục đích của
ChannelAdapter.

---

## Quota Claude trên Vertex — đọc trước khi bực

Project GCP **mới tạo có hạn mức Claude bằng 0**. Triệu chứng: mọi lời gọi trả

```
429 Quota exceeded for aiplatform.googleapis.com/
    global_online_prediction_requests_per_base_model
```

Điều này đúng với **mọi model** (Opus 5, Sonnet 5, Haiku 4.5…) và region `global`;
các region khác thường trả 404 vì model chưa bật cho project ở đó.

**Hai đường đi, đổi bằng một dòng trong `.env`:**

```
LLM_PROVIDER=vertex        # cần xin quota trước, vài giờ tới vài ngày
LLM_PROVIDER=anthropic     # chỉ cần ANTHROPIC_API_KEY, chạy được ngay
```

Xin quota: [Console → IAM & Admin → Quotas](https://console.cloud.google.com/iam-admin/quotas),
lọc `aiplatform.googleapis.com`, tìm `online_prediction_requests_per_base_model`,
chọn base model `anthropic-claude-*` rồi bấm *Edit quotas*.

Lấy API key: [console.anthropic.com](https://console.anthropic.com/settings/keys).
Giá token giống hệt nhau ở cả hai đường.

> **Embedding cho RAG không dính quota này.** Nó dùng
> `text-multilingual-embedding-002`, hạn mức riêng, chạy được ngay cả khi
> Claude trên Vertex đang bị chặn. Nên RAG hoạt động độc lập với lựa chọn trên.

---

## Gặp lỗi

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| `UnicodeEncodeError ... charmap` khi chạy script | Console Windows mặc định cp1252 | Đã vá sẵn trong `scripts/`. Với script tự viết, thêm `sys.stdout.reconfigure(encoding="utf-8")` |
| `npx hyperframes init` treo, không ra gì | Lệnh này hỏi tương tác | Chạy trong terminal thật, đừng chạy trong script nền |
| Dashboard trống dù DB có dữ liệu | JSONB về dạng chuỗi | Đã sửa bằng codec trong `agent/db.py` — nếu tự thêm bảng JSONB thì codec tự áp dụng |
| Webhook không tới app | Container không gọi được `localhost` của host | Dùng `http://host.docker.internal:8000/webhook` |
| Cổng 5432 bận | ZaloCRM cũng dùng Postgres | Compose này đã đặt sẵn **5433** |

---

## Đã biết còn thiếu

Mục này từng liệt kê sáu thiếu sót của bản MVP đầu. **Bốn trong số đó đã
làm xong** và danh sách cũ nằm lại quá lâu — một tài liệu nói hệ thống tệ
hơn thực tế cũng sai như một tài liệu nói nó tốt hơn. Ghi lại cả hai cột để
lần sau đối chiếu được:

| Từng thiếu | Nay |
|---|---|
| Chưa có eval gate / golden set | `scripts/eval.py` + 56 câu hỏi vàng |
| Chưa chống prompt injection | `agent/core/phong_thu.py`, quét trước khi gọi model |
| Chưa che PII trước khi vào log | `agent/core/du_lieu_ca_nhan.py` |
| Render video chạy trong tiến trình app | hàng đợi trong Postgres — `agent/video/worker.py` |
| Dashboard chưa có đăng nhập | `agent/core/xac_thuc.py`, 17/17 endpoint chặn |
| Chưa có Veo 3.1 | **vẫn chưa** — video dựng bằng template ba bậc |

Còn thiếu thật, tính tới hôm nay:

- **Chưa có chăm sóc chủ động.** Agent chỉ trả lời khi được hỏi. Không theo
  khách im lặng, không hỏi thăm sau khi giao hàng, không nhắc hết hạn dùng.
  Đây là nửa còn lại của bốn chữ "chăm sóc khách hàng" — và nó **không được
  làm trước khi chuyển sang Zalo OA**: nhắn chủ động hàng loạt từ nick cá
  nhân là cách nhanh nhất để bị khoá nick, và nick khoá thì mất luôn lịch
  sử hội thoại với khách.
- **Bộ đo nhiều lượt đã có nhưng chưa chạy lần nào.** 12 kịch bản · 43 lượt
  sẵn sàng, bộ chấm có 29 test canh — nhưng chạy thật thì gọi model thật,
  nên chưa có con số. Tới khi chạy, khả năng tư vấn nhiều lượt vẫn là ẩn số.
- **Chưa có Veo 3.1.**
- **Một máy, không có phương án khi máy hỏng.**

---

## MCP — ứng dụng ngoài cắm vào hệ thống

Hệ thống mở ra 9 công cụ và 2 tài nguyên qua Model Context Protocol, nên
Claude Desktop / Claude Code hỏi thẳng được:

> *"Aurora Skin còn bao nhiêu sữa rửa mặt cho da dầu?"*
> *"Tuần này bài nào chạy tốt nhất?"*

```bash
.venv/Scripts/python.exe -m scripts.mcp_thu
```

**Hai đường vào, cùng một máy chủ:**

| Đường | Dùng cho | Bật thế nào |
|---|---|---|
| stdio | Claude Desktop trên cùng máy | luôn có |
| HTTP `localhost:8000/mcp` | client HTTP bất kỳ | đặt `MCP_TOKEN` trong `.env` |

Đường HTTP nằm trên **chính cổng 8000**, không còn tiến trình riêng ở 8765,
nên nó đi qua đúng lớp bảo vệ của dashboard: nhận **hoặc** `Authorization:
Bearer <MCP_TOKEN>` **hoặc** phiên đăng nhập dashboard.

`MCP_TOKEN` để rỗng thì `/mcp` trả 404 — **tắt hẳn**, không phải mở sẵn chờ
ai đó nhớ ra mà khoá lại.

**Ranh giới an toàn:** MCP chỉ có công cụ ĐỌC và soạn bài nháp. Không có
công cụ đăng bài, chốt đơn hay nhắn tin cho khách — client MCP là một model
khác, không đi qua chốt tuân thủ nào của hệ thống này. Ràng buộc đó được
canh bằng test, không bằng lời hứa.

Chi tiết + cấu hình Claude Desktop: [docs/mcp.md](docs/mcp.md)

---

## Kiểm thử

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
```

419 ca, chạy dưới 2 giây, không gọi API. Đo phần logic quanh model — chốt
tuân thủ, lưới an toàn, bộ làm-tự-nhiên, chấm điểm, khớp sản phẩm, hàng đợi
trực, giới hạn đăng nhập.

Gõ `pytest` trần cũng chạy đúng bộ này: `pytest.ini` chặn không cho nó bò
vào submodule `ZaloCRM/` — trước khi có file đó, `pytest` không kèm đường
dẫn sẽ vỡ ngay lúc thu thập vì các file sao lưu Windows không đọc được.

## Đo tư vấn nhiều lượt

Bộ 56 câu vàng gọi `respond(history=[], ...)` — một câu hỏi, một câu trả
lời, rồi quên. Nó đo rất kỹ chuyện agent có nói bậy không. Nó **không** đo
được agent tư vấn giỏi tới đâu, vì tư vấn là việc nhiều lượt.

```bash
.venv/Scripts/python.exe -m scripts.eval_nhieu_luot --kho   # không tốn tiền
.venv/Scripts/python.exe -m scripts.eval_nhieu_luot         # chạy thật
```

12 kịch bản · 43 lượt, **bật trí nhớ khách** (`customer_ref`) — khác hẳn bộ
vàng vốn tắt đi để các ca độc lập. Chấm hai tầng:

| Tầng | Đo gì |
|---|---|
| Từng lượt | phải có gì, cấm gì, có chuyển người không — **ở mọi lượt**, không chỉ lượt đầu |
| Cả hội thoại | chào lại · hỏi lại điều khách đã nói · hỏi dồn · bỏ rơi khách ở cuối |

Ca quan trọng nhất là loại `tuan_thu_giua_chung`: khách nói *"à mà em đang
bầu 5 tháng"* ở **lượt thứ tư**. Bộ vàng chỉ hỏi ở lượt đầu nên mù hoàn
toàn với tình huống này — và đây đúng là tình huống có thật.

Chỉ số `hỏi lại điều đã biết` là **phép đo trực tiếp đầu tiên** cho
`ho_so_khach`: module được xây để chống đúng lỗi đó nhưng trước nay chưa
có con số nào chứng minh nó có tác dụng.

Bộ chấm nằm ở `agent/core/cham_nhieu_luot.py`, tách riêng khỏi bộ chạy để
kiểm thử được mà không gọi API. **Nó đo HÌNH THỨC cuộc tư vấn, không đo
NỘI DUNG lời khuyên** — "có hỏi lại loại da trước khi gợi ý không" thì đo
được, "gợi ý ấy có hợp với da khách không" thì phải người trong nghề đọc.

---

Bộ 56 câu hỏi vàng (`python -m scripts.eval`) đo hành vi thật của model:
mất ~13 phút, tốn tiền API, và **không tất định** — các lần chạy cho 51-55
điểm. Dùng nó để đo chất lượng, dùng pytest để chặn hồi quy.

---

## Chỉ số hệ thống

Đo trên bộ 56 câu hỏi vàng (`python -m scripts.eval`):

| Chỉ số | Giá trị |
|---|---|
| Đạt | **51–55 / 56** (bốn lần chạy liên tiếp: 51, 55, 52, 54) |
| Bỏ sót chuyển người | **0/16** |
| Dùng từ cấm quảng cáo | **0** |
| Dấu hiệu lộ bot — khách thật sự nhận | **0,09 / câu · 91% sạch** |
| Độ trễ | trung vị 3,6s · p90 8,6s |
| Chi phí | $0,0693 cho 56 ca (~1.732đ) |
| Token đọc từ cache | **86,8%** |

Báo cả dải chứ không báo mỗi lần tốt nhất. Bộ vàng gọi model thật nên
**không tất định**, và con số doanh nghiệp sẽ gặp là mức sàn (51/56 ≈ 91%),
không phải kỷ lục (55/56 ≈ 98%). Một tài liệu chỉ ghi kỷ lục là một tài liệu
sẽ làm người đọc thất vọng đúng vào ngày họ đo lại.

Chỉ số giọng văn đo ở **hai mốc**: văn bản model sinh ra (0,45 dấu hiệu/câu)
và thứ khách thật sự nhận sau khi tách tin (0,09). Cái đầu đo prompt, cái
sau đo trải nghiệm.

### Bộ vàng KHÔNG đo được cái gì

Quan trọng ngang phần nó đo được. Mỗi ca chạy với `history=[]` và **không
truyền `customer_ref`** — cố ý, để các ca độc lập với nhau. Hệ quả:

- **Không có ca nhiều lượt nào.** Cả 56 ca đều là một câu hỏi, một câu trả
  lời. Việc hỏi lại cho rõ trước khi khuyên, giữ mạch qua bảy lượt, không
  hỏi lại điều khách vừa nói, dẫn khách tới lúc chốt đơn — không đo.
- **Trí nhớ khách nằm ngoài vùng đo.** `agent/core/ho_so_khach.py` có 19
  test đơn vị chứng minh nó ghi và xoá đúng; không có con số nào chứng minh
  agent *dùng* hồ sơ đó khéo với người thật.
- **Cách chấm là khớp từ khoá** (`phai_co` / `khong_duoc_co`) cộng với kiểm
  chuyển người đúng lúc. Nó đo **"không sai"**, không đo **"khuyên hay"**.

20/56 ca — hơn một phần ba — thuộc nhóm tuân thủ, thẩm quyền và ngoài danh
mục, tức là các ca *đừng nói bậy*. Bộ này chứng minh agent không gây tai
nạn. Nó chưa chứng minh agent tư vấn giỏi.

Quan sát chi phí: `GET /api/cost` hoặc màn **Số hiệu** — dựng từ bảng
`messages`, không cần Langfuse hay hệ thống ngoài nào.

---

## Bảo vệ dữ liệu cá nhân

Hệ thống lưu tên, số điện thoại, địa chỉ và nội dung hội thoại của khách
thật, nên nó phải trả lời được ba câu của **Nghị định 13/2023/NĐ-CP**:

| Điều | Quyền | Ở đâu |
|---|---|---|
| 9.1.c | Biết hệ thống giữ gì | dashboard mục **Nhật ký** |
| 9.1.đ | Yêu cầu xoá | cùng chỗ, có chốt xác nhận |
| 16 | Thời hạn lưu trữ | 180 ngày, dọn tự động hằng ngày |

Đơn hàng được **ẩn danh** chứ không xoá — Luật Kế toán 2015 Điều 41 buộc
lưu chứng từ tối thiểu 10 năm. Hội thoại và tin nhắn thì xoá hẳn.

Chi tiết: [docs/du-lieu-ca-nhan.md](docs/du-lieu-ca-nhan.md)

---

## Đưa vào doanh nghiệp

Dashboard đọc PII khách hàng và gửi tin nhân danh doanh nghiệp, nên **phải
đăng nhập**. Tạo tài khoản đầu tiên trên máy chủ:

```bash
python -m scripts.tao_tai_khoan admin "mật khẩu mạnh" --quan-tri
```

Hai vai: `nhan_vien` xem hội thoại, xử lý đơn, nhập kho — `quan_tri` thêm
quyền xoá dữ liệu khách, đổi cấu hình agent, quản lý tài khoản.

Bảy việc bắt buộc trước khi chạy thật, và những chỗ còn hở:
[docs/dua-vao-doanh-nghiep.md](docs/dua-vao-doanh-nghiep.md)
