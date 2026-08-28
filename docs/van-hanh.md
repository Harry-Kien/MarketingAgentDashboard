# Sổ tay vận hành

Tài liệu này dành cho **người trực hệ thống**, không phải người viết mã.
Nó trả lời ba câu: hệ thống đang sống không, hỏng thì làm gì, và những gì
đã từng hỏng thật.

Khác `docs/dua-vao-doanh-nghiep.md` — ở đó là cách đưa hệ thống vào dùng;
ở đây là cách giữ nó chạy sau khi đã dùng.

---

## Bốn tiến trình phải sống

| Tiến trình | Cổng | Chết thì mất gì |
|---|---|---|
| PostgreSQL (Docker) | 127.0.0.1:5433 | **Mất tất cả** — không nhận, không trả lời, dashboard trắng |
| App (uvicorn) | 127.0.0.1:8000 | Mất tất cả trừ dữ liệu đã lưu |
| Sidecar Zalo (Node) | 127.0.0.1:3210 | Chỉ mất kênh Zalo cá nhân |
| n8n (Docker) | 127.0.0.1:5678 | Mất đường đăng bài tự động |
| **Kho / ERP** (Odoo hoặc ERPNext) | máy khác | Agent **không nói được giá và tồn kho** — nó chuyển hết cho người thay vì đoán bừa |

Dòng cuối khác ba dòng trên ở một chỗ quan trọng: ERP **không phải tiến
trình của ta**. Nó chết thì hệ thống vẫn nhận tin, vẫn trả lời chính sách,
vẫn tra kho tri thức — chỉ mất khả năng nói về giá và hàng. Đó là thiết kế,
không phải suy giảm: cổng thà im còn hơn đọc số cũ.

Chạy bằng `ERP_LOAI=tep` thì dòng này không áp dụng — nhưng khi đó agent
đang tư vấn bằng một file JSON trên đĩa, và dashboard sẽ hiện cảnh báo
"CHƯA nối ERP thật".

Kiểm nhanh cả bốn:

```bash
python -m scripts.san_sang
```

Dòng cuối nói thẳng: `SẴN SÀNG` hoặc `CHƯA CHẠY ĐƯỢC: còn N việc CHẶN`.

---

## Khởi động lại từ đầu

Theo đúng thứ tự — app cần CSDL, sidecar cần app để gọi ngược về.

```bash
docker compose up -d
```

```bash
.venv\Scripts\python.exe -m uvicorn agent.main:app --host 127.0.0.1 --port 8000
```

Sidecar Zalo cá nhân chạy bằng tiến trình Node riêng, đọc `ZALO_SIDECAR_SECRET`
và `ZALO_CONTROL_PLANE_URL` từ `.env`.

Sidecar KHÔNG tự đọc `.env` — phải xuất biến ra môi trường trước khi chạy,
nếu không nó thoát ngay ở dòng đầu. Lệnh đầy đủ nằm ở README.

### Agent không gửi được ảnh cho khách Zalo

Dấu hiệu: hàng đợi có job `dead`, lý do
`Missing imageMetadataGetter`. Trên dashboard không có gì bất thường — chỉ
khách là không nhận được ảnh.

`zca-js` cần width/height/size để dựng khung xem trước. Trên trình duyệt nó
tự đọc từ thẻ `<img>`; ở Node không có DOM nên sidecar phải tự cấp qua
`imageMetadataGetter` — xem `connectors/zalo-personal-sidecar/src/anh-metadata.mjs`.

Sau khi sửa, đưa job về hàng chờ bằng API outbox rồi worker gửi lại; không
phải bảo khách nhắn lại.

**Không cần đăng nhập Zalo lại.** Phiên đã mã hoá trong vault, và
`giu_phien_zalo_loop` tự khôi phục trong vòng 60 giây sau khi sidecar lên.
Chỉ phải quét QR lại khi Zalo tự vô hiệu phiên — lúc đó nhật ký ghi
`zalo_personal.can_quet_lai`.

---

## Dừng đúng cách trên Windows

`pkill` **không** giết được tiến trình Windows. Dùng cổng để tìm chủ:

```powershell
$pids = (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess | Sort-Object -Unique
foreach ($p in $pids) { Stop-Process -Id $p -Force }
```

Đây không phải chi tiết vặt: lệnh dừng không ăn khiến bản mới chết vì
`EADDRINUSE` còn **bản cũ vẫn phục vụ với cấu hình cũ** — đã xảy ra thật,
và triệu chứng là "sửa cấu hình rồi mà không thấy đổi gì".

---

## Báo động Telegram nghĩa là gì

| Tin nhận được | Nghĩa | Việc cần làm |
|---|---|---|
| `[hong] Agent KHÔNG PHẢN HỒI` | App chết hoặc máy ngủ | Khởi động lại theo mục trên |
| `[phuc_hoi] Agent đã sống lại` | Đã tự hồi phục | Không cần làm gì |
| `[hong] Hệ thống đang hỏng` | App sống nhưng một thành phần hỏng | Chạy `san_sang` xem mục nào đỏ |
| `[khach_cho] Có khách đang chờ người` | Có hội thoại đã chuyển người mà chưa ai nhận | Mở dashboard, vào mục Hội thoại |

Cổng ERP không gửi Telegram — nó hiện trên **dashboard mục Sức khoẻ**, hai
dòng `Kho / ERP` và `Đơn chờ đồng bộ ERP`. Bấm *Kiểm sức khoẻ* để chạy thật.

Báo động **chỉ gửi khi ĐỔI trạng thái**, không gửi lặp mỗi 5 phút. Im lặng
kéo dài nghĩa là mọi thứ ổn — hoặc người canh cũng chết.

Người canh bên ngoài là task Windows tên `CanhGacMarketingAgent`, chạy mỗi
5 phút. Kiểm nó còn sống:

```powershell
Get-ScheduledTaskInfo -TaskName 'CanhGacMarketingAgent'
```

---

## Sao lưu và phục hồi

Sao lưu tự chạy hằng ngày trong app. Chạy tay:

```bash
python -m scripts.sao_luu
```

**Sao lưu chưa từng phục hồi thử thì chưa phải sao lưu.** Diễn tập vào CSDL
nháp, không đụng bản đang chạy:

```bash
docker compose exec -T db psql -U agent -d postgres -c "CREATE DATABASE thu_phuc_hoi;"
```

Rồi đổ bản mới nhất vào đó và **đếm bảng**: phải ra đúng bằng bản gốc. Lần
diễn tập đầu tiên trong dự án này cho 41/42 bảng — thiếu đúng bảng `chunks`,
tức toàn bộ kho tri thức RAG. Không đếm thì không ai biết.

`scripts/sao_luu.py` **không** sao lưu volume Docker. Volume `n8n_data` giữ
OAuth Facebook/Instagram/TikTok — mất là phải xin duyệt lại 1–4 tuần. Sao
lưu riêng nếu đã nối OAuth thật.

---

## Những gì đã hỏng thật, và dấu hiệu nhận ra

Ghi lại để lần sau nhận ra trong vài phút thay vì vài giờ. Cả bốn đều
**không nổ, không ghi lỗi** — chỉ im lặng.

### Tin khách không vào hệ thống

Kiểm theo thứ tự này, dừng ở chỗ đầu tiên sai:

1. Tài khoản trên dashboard còn `pending:` hay `Gián đoạn`? → chưa quét QR xong
2. `webhook_deliveries` có tăng không? → không tăng nghĩa là tin chưa tới app
3. Sidecar báo `disconnected`? → phiên chết, chờ 60 giây tự khôi phục
4. `ZALO_CONTROL_PLANE_URL` có **đủ đường dẫn** `/webhook/native/zalo-personal` không?

Điểm 4 đã xảy ra thật: thiếu đường dẫn thì sidecar POST vào 404, phiên
không tới nơi, tin biến mất — mà sidecar vẫn `healthz` xanh và app cũng
xanh. Có test canh: `tests/test_sidecar_callback_url.py`.

### Trang Facebook đã nối nhưng không nhận tin nào

Trang có token là **gửi** tin đi được ngay — nên mọi dấu hiệu đều nói đã
xong: trạng thái xanh, xác minh kết nối PASS, gửi tin chủ động PASS. Nhưng
**nhận** tin cần thêm một bước hoàn toàn khác: Trang phải được đăng ký vào
webhook của app (`POST /{page-id}/subscribed_apps`).

Thiếu bước đó thì không có dòng lỗi nào ở đâu cả, và người trực sẽ tưởng
khách không nhắn.

Chữa: mở **Kết nối**, bấm nút **"Nhận tin"** trên thẻ Trang đó. Nối bằng
"Kết nối Facebook" từ nay tự làm bước này; nút chỉ cần cho Trang nối từ
trước, hoặc khi Meta huỷ đăng ký (họ làm vậy khi app đổi trạng thái duyệt
hoặc quyền bị thu hồi).

Nút báo đỏ thường là thiếu quyền `pages_manage_metadata` — nối lại
Facebook và cấp đủ quyền. Lý do đầy đủ nằm ở mục Nhật ký, sự kiện
`channel.dang_ky_webhook_loi`.

### Bấm "Duyệt và gửi" mà khách không nhận

Xem trạng thái job:

```bash
docker compose exec -T db psql -U agent -d marketing_agent -c "SELECT status, attempts, left(last_error,100) FROM outbox_jobs ORDER BY updated_at DESC LIMIT 5;"
```

- `processing` mãi không đổi → worker claim rồi kẹt
- `retry` kèm lý do → đọc `last_error`
- `dead` → xử lý qua API outbox, **nhưng kiểm hội thoại có ai đang tiếp quản không** trước khi gửi lại

### Agent im lặng dù khách đang nhắn

Hội thoại đang ở `mode=human` — có người bấm *Tôi tiếp quản*, hoặc nhân
viên đã nhắn trực tiếp. Đây là **đúng thiết kế**, không phải lỗi. Bấm
*Kết thúc tiếp quản* để trả lại cho agent.

### Agent trả lời chính nó

Tin do hệ thống gửi quay ngược vào như tin khách. Đã chặn hai lớp (sidecar
và control plane), nhưng nếu thấy lại: kiểm `external_account_id` của tài
khoản có đúng `own_id` thật không, hay còn `pending:`.

---

## Bật cổng ERP — thứ tự bắt buộc

Cổng mặc định **tắt hai lần**: `ERP_LOAI=tep` (đọc file) và
`ERP_GHI_DON=false` (không đẩy đơn). Bật sai thứ tự là ghi dữ liệu hỏng vào
ERP thật, mà ERP thì không có nút hoàn tác.

**Bước 1 — điền cấu hình, chưa bật ghi.**

```
ERP_LOAI=erpnext        # hoặc odoo
ERP_MA_KHO=KHO-HN       # mã kho, KHÔNG bỏ trống
ERP_PRICELIST=Bán lẻ    # ERPNext; Odoo hiện đọc list_price
ERP_GHI_DON=false       # vẫn TẮT ở bước này
```

**Bước 2 — gọi thật và đọc kết quả.**

```bash
python -m scripts.thu_erp
```

Lệnh này CHỈ ĐỌC. Nó trả lời bốn câu mà không gọi thật thì không ai biết:
tên trường có đúng bản ERP của bạn không, bao nhiêu mã nội bộ khớp mã ERP,
bảng giá nào đang được dùng, và ERP chậm bao nhiêu ms.

Phải **xanh hết** mới đi tiếp. Ba đèn đỏ hay gặp:

| Đèn | Nghĩa | Chữa |
|---|---|---|
| Ánh xạ mã | Mã nội bộ không khớp mã ERP | Lập `data/anh_xa_ma.json` |
| Giá | Không tra được giá | `ERP_PRICELIST` trỏ sai bảng |
| Danh mục RỖNG | Đọc được nhưng không món nào | Quyền tài khoản API, hoặc chưa có hàng nào bật bán |

**Bước 3 — người xác nhận bảng giá.** Máy không tự biết bảng nào là bảng
bán lẻ. `thu_erp` in tên bảng nó dùng; bạn phải nhìn và gật. Sai bảng giá
thì agent báo giá sỉ cho khách lẻ, rất tự tin.

**Bước 4 — chạy vài ngày ở chế độ chỉ đọc.** Agent tư vấn bằng giá và tồn
thật, đơn vẫn chỉ nằm trong Postgres. Đây là lúc phát hiện lệch mà chưa phải
trả giá.

**Bước 5 — bật ghi đơn.**

```
ERP_GHI_DON=true
```

Đơn đầu tiên phải **mở ERP xem tận mắt**: đúng khách, đúng kho, đúng giá,
đúng số lượng. Rồi mới để nó chạy.

---

## Dấu hiệu cổng ERP đang hỏng

Khác mục trên, đây là các kiểu hỏng **đã lường trước và có lưới chặn**, chưa
phải chuyện đã xảy ra thật. Ghi ra để khi gặp thì nhận ra ngay.

### Agent đột nhiên chuyển người rất nhiều

Dashboard mục Sức khoẻ, dòng `Kho / ERP`. Thấy `NGẮT MẠCH đang mở` nghĩa là
cổng đã gọi hỏng liên tiếp và tự ngắt — mọi câu hỏi về giá và tồn đang trả
"không biết", và agent chuyển người là **đúng thiết kế**.

Mạch tự đóng lại sau 30 giây nếu ERP sống lại. Không đóng thì ERP vẫn đang
chết.

### Khách xác nhận đơn xong mới bị báo hết hàng

Chốt đơn đọc tồn **sống**, bỏ qua cache. Nên nếu tư vấn nói còn mà chốt nói
hết, có ba khả năng: (1) món cuối vừa bán mất thật trong lúc tư vấn — đúng
và không sửa được; (2) `ERP_MA_KHO` trỏ sai kho; (3) tồn kho hai bên lệch.
Khả năng (3) sẽ có `erp.lech_ton_kho` trong nhật ký.

### Có đơn "đã ghi nhận" mà không ai gọi khách

Dashboard, dòng `Đơn chờ đồng bộ ERP`. Đơn `cho_dong_bo` nghĩa là khách đã
được hứa "sẽ có người gọi xác nhận". Vòng nền thử lại 8 lần với giãn cách
tăng dần; quá số đó nó **dừng và đưa đơn về `cho_duyet`** — máy bỏ cuộc,
người quyết định.

Đơn kẹt quá 30 phút hiện thành **đỏ**, vì đó là một lời hứa đang bị bỏ.

### Agent giới thiệu một sản phẩm nghe rất chung chung

ERP có SKU mới mà chưa ai viết hồ sơ tư vấn cho nó. Cổng gắn cờ
`duoc_gioi_thieu=false` và ghi `erp.thieu_ho_so`. Viết bổ sung phần tư vấn
vào `data/catalog.json` — nửa đó **không** nằm trong ERP, và cố ý như vậy.

---

## Việc định kỳ

| Khi nào | Việc |
|---|---|
| Hằng ngày | Liếc dashboard mục *Ca trực* xem có khách chờ |
| Hằng tuần | `python -m scripts.san_sang` — đèn đỏ mới xuất hiện? |
| Hằng tuần | Dashboard → *Kiểm sức khoẻ*: hai dòng ERP còn xanh không |
| Sau khi đổi danh mục bên ERP | `python -m scripts.thu_erp` — mã mới có khớp không |
| Hằng tháng | **Diễn tập phục hồi** sao lưu, đếm bảng |
| Khi đổi schema | `python -m scripts.sinh_so_do --ghi` |
| Trước khi báo xong việc gì | `pytest -q` và `ruff check .` |

---

## Giới hạn phải biết

**Hệ thống chạy trên máy tính cá nhân.** Máy ngủ, mất điện, Windows cập
nhật — khách nhắn vào không ai nhận. Báo động cho bạn biết, nhưng không tự
bật lại được. Máy chủ chạy 24/7 là cách duy nhất giải quyết.

**Zalo cá nhân dùng thư viện không chính thức.** Zalo có thể khoá tài khoản
bất cứ lúc nào. Dùng số phụ, và chuẩn bị Zalo OA làm đường chính thức.

**Bốn kênh Meta và Zalo OA cần URL HTTPS công khai.** Chúng gọi *vào* hệ
thống, khác Zalo cá nhân là sidecar chủ động nối *ra*.
