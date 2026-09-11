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
| `[hong] Agent KHÔNG PHẢN HỒI` | App chết hoặc máy ngủ; lần sau còn hỏng người canh sẽ tự dựng lại | Chờ 5 phút xem có `[tu_dung_lai]` không |
| `[tu_dung_lai] Agent chết — đã tự dựng lại` | Người canh đã gọi bốn bước của `khoi_dong` (Docker, Postgres, app, sidecar) và app đã trả lời lại | Xem `app.log` để biết vì sao chết; không cần bật gì |
| `[tu_dung_lai_hong] tự dựng lại THẤT BẠI` | Một bước không lên được (Docker tắt, Postgres không nhận kết nối, app không lên sau 60 giây) | Đọc chi tiết trong tin, sửa tầng đó, chạy `python -m scripts.khoi_dong` |
| `[bo_cuoc]` | Đã dựng lại 3 lần trong một giờ mà vẫn chết — lỗi không phải kiểu bật lại là xong | Xem `app.log`, chạy `san_sang`; sửa xong thì app tự được canh lại |
| `[phuc_hoi] Agent đã sống lại` | Đã tự hồi phục | Không cần làm gì |
| `[hong] Hệ thống đang hỏng` | App sống nhưng một thành phần hỏng | Chạy `san_sang` xem mục nào đỏ |
| `[khach_cho] Có khách đang chờ người` | Có hội thoại đã chuyển người mà chưa ai nhận | Mở dashboard, vào mục Hội thoại |

Cổng ERP không gửi Telegram — nó hiện trên **dashboard mục Sức khoẻ**, hai
dòng `Kho / ERP` và `Đơn chờ đồng bộ ERP`. Bấm *Kiểm sức khoẻ* để chạy thật.

Báo động **chỉ gửi khi ĐỔI trạng thái**, không gửi lặp mỗi 5 phút. Im lặng
kéo dài nghĩa là mọi thứ ổn — hoặc người canh cũng chết.

Người canh **tự dựng lại** app sau hai lần hỏng liên tiếp (10 phút), tối đa
ba lần mỗi giờ, và không đụng tunnel hay `.env`. Đo được 06.09.2026: app
chết 5 tiếng mà chỉ có một tin báo — báo đúng mà không làm gì thì với khách
cũng như không báo. Một lần trượt mạng không đủ để bật lại app đang sống,
nên mới chờ hai lần.

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
5. `san_sang` mục *Bí mật sidecar Zalo* đỏ? → sidecar đang chạy với
   `ZALO_SIDECAR_SECRET` cũ (bật trước khi `.env` đổi). Khởi động lại nó
   bằng `python -m scripts.chay_sidecar_zalo`; quét QR không chữa được.

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

## Nhập khoá API trên dashboard

Cấu hình → **Cài đặt API**. Ba thẻ: Model, ERP, Vận chuyển. Khoá được mã
hoá trong CSDL bằng vault của tài khoản kênh và có hiệu lực ngay. `.env`
vẫn là đường lui: chưa đặt ở dashboard thì hệ thống dùng `.env`.

Thứ tự đúng: **Kiểm tra → Lưu**. Kiểm chạy bằng đúng thứ bạn vừa gõ,
chưa lưu gì; "HẾT HẠN MỨC" nghĩa là khoá đúng nhưng nhà cung cấp từ chối.

**Đổi provider sang `gemini_api`** (chỉ cần API key, không cần gcloud): kho
tri thức phải **nạp lại** vì model embedding đổi. Màn Sức khoẻ có dòng
*Embedding kho tri thức* báo đỏ cho tới khi nạp lại — đừng bỏ qua, tìm
kiếm sẽ sai mà không lỗi.

Khoá chủ vault (`CREDENTIAL_MASTER_KEYS`) đổi thì mọi khoá đã lưu không
mở được: `san_sang` mục *Khoá API* chặn, nhật ký có
`cau_hinh_api.giai_ma_hong`. Nhập lại khoá là xong.

---

## Thử agent trước khi cho khách gặp

Dashboard → **Phòng thử**. Nhắn như khách, nhiều lượt. Bên phải hiện agent
ĐÃ LÀM GÌ trong lượt vừa rồi: lớp lưới nào bắt và vì sao, công cụ nào được
gọi với tham số gì và trả gì, trích tài liệu nào, tốn bao nhiêu.

**"ĐANG THỬ" cạnh tên công cụ** nghĩa là công cụ đó chỉ được mô phỏng:
`tao_don_hang`, `tao_video`, `xin_huy_don`, `xin_doi_tra` không ghi gì
vào Postgres, ERP hay hàng đợi. Các công cụ tra cứu chạy thật với dữ liệu
thật. Không có gì được gửi ra kênh nào, và hồ sơ khách không bị đụng.

**Mô phỏng tái hiện được gì.** Đơn thử vẫn đi qua đúng những chốt của bản
thật: khách phải xác nhận, phải đủ họ tên / số điện thoại / địa chỉ, mã
hàng phải có trong danh mục, ngưỡng duyệt vẫn áp (đơn to ra `cho_duyet`
chứ không `da_chot`), và tồn kho ghi trong danh mục vẫn chặn. Nó KHÔNG tái
hiện: tồn kho sống hỏi thẳng ERP lúc chốt (phòng thử đọc số trong danh
mục, có thể cũ hơn), và trần chi phí một hội thoại (hội thoại thử không
tích luỹ chi phí trong bảng `conversations` nên lưới ấy không bao giờ nổ).

**Tiền.** Mỗi lượt là một lời gọi model thật. Chi phí vào sổ riêng với
trần riêng — *Cấu hình → Trần chi phí phòng thử mỗi ngày* (mặc định 1
USD). Hết trần thì phòng thử dừng, khách thật không bị ảnh hưởng. Ngược
lại thì có: hệ thống chạm trần ngày chung thì phòng thử cũng dừng, vì đó
là một túi tiền.

**Gợi ý từ bộ câu vàng.** Bấm một câu là điền sẵn và mang theo kỳ vọng
(có phải chuyển người không, từ khoá phải có, từ cấm). Lượt trả lời sẽ
được chấm ĐẠT / KHÔNG ĐẠT so với kỳ vọng ấy.

**Phòng thử không thay bộ vàng.** Nó trả lời "hôm nay agent làm gì với câu
này"; `python -m scripts.eval` trả lời "nó có ổn định qua 56 câu không".
Sửa prompt xong vẫn phải chạy bộ vàng.

---

## Cài một gói kỹ năng

Một gói gộp hướng dẫn tư vấn + công cụ tra cứu + tài liệu làm một, cài một
lần từ dashboard — xem `docs/ky-nang.md` mục "Gói kỹ năng" để biết định
dạng và luật. Ba bước:

1. **Kiểm.** Dashboard → **Kỹ năng** → khối **Thêm kỹ năng** →
   chọn **Cài gói có sẵn** → dán JSON
   (hoặc chọn tệp `.json`) → nút **Kiểm**. Không ghi gì, chỉ nói hợp lệ
   hay không và tóm tắt (số công cụ, số tài liệu, từ khoá). Có gói mẫu
   sẵn ở `data/goi-ky-nang/tu-van-da-nhay-cam.example.json` để thử ngay
   mà không phải tự viết JSON.

   Đã chọn tệp thì **tệp thắng ô dán** — nút Kiểm đọc tệp, không đọc phần
   còn sót trong ô. Riêng tệp `.zip` thì nút Kiểm báo là không nhận: bộ
   giải nén nằm ở máy chủ và chỉ chạy trên đường **Cài**, nơi nó vẫn kiểm
   toàn bộ trước khi ghi bất cứ thứ gì.
2. **Cài.** Nút **Cài**. Nhận cả `.json` lẫn `.zip`. Có hiệu lực ngay —
   không cần khởi động lại gì.
   Cài cùng tên khác phiên bản thì bản cũ tự vào lịch sử (giữ tối đa 10
   bản), có nút Khôi phục nếu bản mới có vấn đề.
3. **Kiểm sau khi cài — không tốn tiền model.**

   ```bash
   python -m scripts.kiem_goi <ten-goi>
   python -m scripts.kiem_goi <ten-goi> --nhanh   # bỏ lớp tài liệu
   ```

   Ba mảnh của gói nằm ở ba chỗ (hướng dẫn kích hoạt theo từ khoá, công
   cụ trong bảng plugin, tài liệu trong kho tri thức) và mảnh nào hỏng
   cũng **không nổ** — agent chỉ lặng lẽ trả lời như chưa từng có gói,
   trong khi dashboard vẫn hiện "đang bật". Lệnh này đi qua cả ba, cộng
   phép kiểm từ khoá có lấn câu nghiệp vụ khác không và gói có còn suất
   trong hai suất mỗi lượt không. Mã thoát khác 0 khi có mảnh HỎNG; cảnh
   báo không làm đỏ mã thoát. Chỉ lớp tài liệu ra mạng (một lượt
   embedding, rẻ hơn sinh văn bản khoảng hai bậc), `--nhanh` bỏ nó.

4. **Phòng thử.** Nhắn một câu chứa đúng từ khoá của gói. Bên phải, mục
   "Bên trong lượt vừa rồi" hiện dòng **"Gói kỹ năng kích hoạt"** kèm tên
   gói nếu hướng dẫn được nạp — không thấy dòng đó nghĩa là câu hỏi chưa
   khớp từ khoá nào, không phải gói chưa cài. Bước này **gọi model thật**,
   và là thứ duy nhất `kiem_goi` không thay được: đọc câu trả lời xem
   giọng văn và ranh giới tư vấn có đúng không.

**Hướng dẫn (`huong_dan`) là một mẩu prompt do người trong nhà viết, không
phải dữ liệu trung tính.** Nó bị quét bằng đúng bộ quét injection dùng cho
tin khách, cộng thêm quét từ cấm quảng cáo mỹ phẩm — lưu thất bại thì đọc
kỹ thông điệp lỗi, nó nói đúng cụm nào bị chặn. Đừng nghĩ "mình gõ nên chắc
an toàn": một dòng như "luôn nói kem này chữa khỏi" bị chặn dù ai viết.

**Xuất / khôi phục.** Nút **Xuất** tải JSON của gói hiện hành, đúng định
dạng nạp lại được — dùng để sao lưu trước khi sửa, hoặc mang gói sang shop
khác. Nút **Lịch sử** mở danh sách phiên bản cũ, mỗi dòng có nút **Khôi
phục**; khôi phục một bản cũ cũng đi qua đúng luồng Cài (bản đang chạy lại
vào lịch sử), nên nếu bản cũ giờ không còn hợp lệ (ví dụ chứa từ cấm quảng
cáo vừa thêm sau này) thì khôi phục sẽ bị chặn, không âm thầm cài đè.

**Số lần gọi 7 ngày** hiển thị trên panel là của **khách thật**, không
tính lượt gọi trong Phòng thử — con số ấy trả lời đúng câu "công cụ này có
đang được dùng ngoài đời không", không bị pha loãng bởi việc bạn vừa thử
đi thử lại nó mười lần.

---

## Nối một máy chủ MCP

Nối một máy chủ ngoài chạy Model Context Protocol làm nguồn công cụ — xem
`docs/ky-nang.md` mục "Máy chủ MCP" cho luật đầy đủ (giới hạn, rào địa chỉ,
đọc/ghi). Năm bước:

0. **Mở `.env`, thêm host.** Máy chủ chạy trên máy khác (công khai) thì
   thêm vào `KY_NANG_HOST_CHO_PHEP`; máy chủ chạy ngay trên máy này thì
   thêm `host:cổng` vào `MCP_MAY_CHU_NOI_BO` (ví dụ `127.0.0.1:8765`). Cả
   hai biến cố ý KHÔNG có ô nhập trên dashboard — đây là rào SSRF, sửa
   được từ dashboard là cho một tài khoản nhân viên tự mở đường agent gọi
   ra một host bất kỳ mà không ai duyệt. Sửa xong **khởi động lại** agent.
1. **Kiểm.** Dashboard → **Kỹ năng** → panel **Máy chủ MCP** → điền địa
   chỉ (và header xác thực nếu cần) → nút **Kiểm**. Không ghi gì, chỉ nối
   thử và liệt kê công cụ sẽ có, kèm công cụ bị bỏ và lý do (mô tả có câu
   ra lệnh, lược đồ quá lớn...).
2. **Thêm.** Nút **Thêm** tạo máy chủ rồi đồng bộ ngay — công cụ ĐỌC tự
   bật nếu còn chỗ dưới trần 12 plugin, công cụ GHI luôn để tắt.
3. **Xem công cụ, bật cái cần.** Bảng công cụ dưới mỗi máy chủ có công tắc
   Bật cho từng cái. Công cụ GHI có thêm công tắc "cho phép ghi ngoài
   phòng thử" — **chỉ bật nó SAU KHI đã thử công cụ đó trong Phòng thử**
   (bước 4); bật trước khi thử là cho một công cụ chưa ai kiểm được phép
   đổi dữ liệu ở hệ thống người khác ngay lượt khách kế tiếp.
4. **Phòng thử.** Nhắn một câu khiến model gọi tới công cụ vừa bật. Công
   cụ GHI trong Phòng thử luôn bị MÔ PHỎNG — không gọi thật máy chủ ngoài,
   dù đã bật "cho phép ghi" — nên bước này an toàn để thử trước khi bật cờ
   đó ngoài đời.

**Đọc dòng đỏ đồng bộ.** Panel hiện lần đồng bộ gần nhất ok/lỗi. Đỏ vì
"không nối được" nghĩa là mạng hoặc địa chỉ có vấn đề — công cụ CŨ vẫn giữ
nguyên, agent không mất năng lực giữa chừng. Dòng "N công cụ bị bỏ" kèm
tên và lý do là chuyện khác: máy chủ vẫn nối được, nhưng một vài công cụ
của nó không qua bộ kiểm bản mô tả (mô tả có câu ra lệnh, lược đồ sai
dạng, tên đụng plugin khác) — sửa ở phía máy chủ MCP rồi Đồng bộ lại, hoặc
chấp nhận thiếu công cụ đó.

**Kiểm sau khi thêm — không tốn tiền model.**

```bash
python -m scripts.kiem_mcp <ten-may-chu>
```

Kiểm một máy chủ đã lưu: địa chỉ có qua rào không, nối được không, công cụ
máy chủ đang khai so với công cụ đã lưu (thiếu/thừa), công cụ nào bị bỏ ở
lần Đồng bộ gần nhất, và gọi thử THẬT một công cụ ĐỌC đang bật không có
tham số bắt buộc (nếu có công cụ nào đủ điều kiện — không có thì bỏ qua,
không phải lỗi). Không có cờ `--nhanh`: khác `kiem_goi`, cả lệnh chỉ có
đúng một việc và việc đó vốn đã cần ra mạng. Mã thoát khác 0 khi có mục
HỎNG.

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

## Giao khách cho nhân viên

Dashboard → **Khách hàng** → chọn một khách → **Giao / thu hồi**. Gõ tên
đăng nhập của nhân viên; để trống là thu hồi, khách quay về của chung.

Ba chip lọc ngay trên danh sách: *Tất cả* · *Khách của tôi* · *Chưa có chủ*.

**Không giao được cho người không có quyền `hoi_thoai.tra_loi`** — hệ thống
chặn ở 422. Lý do: khách ấy sẽ chết câm. Có chủ nên người khác thấy "đã có
người phụ trách" và không vào, mà chủ thì không gửi được tin. Nó không hỏng,
nó chỉ im, và triệu chứng duy nhất là một khách hàng thôi nhắn lại.

Mọi lần giao và thu hồi đều ghi vào `contact_owner_history` kèm lý do và
người thao tác. Bấm **Lịch sử giao** để xem.

### Nhân viên thấy khách của nhau tới đâu

Dashboard → **Cấu hình** → panel đầu tiên. Bốn mức:

| Mức | Nhân viên B thấy gì về khách của A |
|---|---|
| **Không áp dụng** | Thấy và trả lời được như thường. **Mặc định xuất xưởng.** |
| Thấy tên, không đọc được | Thấy trong danh sách, biết A phụ trách; không đọc tin, không thấy số điện thoại và email |
| Đọc được, không trả lời được | Đọc đủ hội thoại — tiện bàn giao ca — nhưng nút gửi bị khoá |
| Ẩn hẳn | Biến mất khỏi danh sách, không mở được, tìm không ra |

Mặc định là **Không áp dụng** có chủ ý: bật một tính năng phân quyền mà đổi
ngay quyền của mọi người đang làm việc là cách tạo sự cố. Giao khách xong
rồi hãy bật.

Ba điều luôn đúng ở mọi mức:

- **Khách chưa giao là của chung** — mọi nhân viên đều thấy và trả lời được.
- Quản trị, và ai có `khach.xem_tat_ca`, không bị mức nào hạn chế.
- Trục `account_memberships` vẫn siết tiếp phía sau: mức tầm nhìn không cho
  ai thấy kênh họ không phải thành viên.

### Ô "Khách chưa có chủ" trên trang Ca trực

Nó chỉ hiện khi **có**, và hiện kèm tuổi của khách vô chủ lâu nhất.

Vì đã chọn "khách chưa giao là của chung, không tự gán chủ", khách vô chủ
sẽ tích lại — đó là hệ quả biết trước, không phải lỗi. Ô này để nó không
tích lại trong im lặng. "412 khách" là con số quen mắt sau một tuần; "lâu
nhất 62 ngày" thì không.

---

## Thêm trường thông tin khách

Dashboard → **Cấu hình** → *Trường thông tin khách* → **Thêm trường**.

Mỗi trường cần một **mã** (chữ thường không dấu, ví dụ `loai_da`) và một
**kiểu**: Chữ · Số · Ngày · Chọn một · Chọn nhiều · Đúng/sai. Thêm xong là ô
nhập hiện ngay trong hồ sơ của **mọi** khách.

Ba điều dễ vấp:

**Mã không đổi được sau khi tạo.** Nó là khoá lưu giá trị trong hồ sơ khách;
đổi mã là mọi giá trị đã lưu thành mồ côi. Nhãn thì sửa thoải mái.

**Kiểu cũng không đổi được.** Đổi `Chữ` sang `Số` không biến các giá trị đã
lưu thành số — chúng nằm nguyên đó dưới dạng chuỗi, và từ đó kiểu nói một
đằng dữ liệu một nẻo. Muốn đổi kiểu thì xoá trường rồi tạo lại.

**Xoá trường thì xoá luôn giá trị.** Hệ thống hỏi lại kèm **số hồ sơ** sắp
mất dữ liệu, không hỏi "bạn có chắc không". Để giá trị nằm lại sau khi xoá
định nghĩa là giữ dữ liệu cá nhân không hiện ở đâu trên màn hình, không ai
gỡ được, và không ai biết mình đang giữ — trái Nghị định 13/2023/NĐ-CP.

Kiểu được **kiểm ở máy chủ**, không chỉ ở giao diện. Gõ chữ vào ô số, hay
gửi một lựa chọn ngoài danh sách, đều bị từ chối kèm lý do nói rõ trường
nào và nhận được gì — chứ không lặng lẽ lưu một ô rỗng.

---

## Công việc

Dashboard → **Công việc**. Mỗi việc có tiêu đề, hạn, mức ưu tiên, người
nhận, và bốn trạng thái: Mới · Đang làm · Xong · Đã huỷ.

**Agent chuyển người thì tự sinh một việc.** Trước đây, agent chuyển người
xong chỉ để lại một dòng nhật ký và một hội thoại đổi màu — không ai được
giao gì cả. Nếu người trực đang bận lúc ấy thì việc không nằm ở đâu, và nó
chỉ được nhớ tới nếu tình cờ có người mở đúng hội thoại.

Việc tự sinh mang nhãn **agent chuyển**, ưu tiên *Cao*, và **chưa giao cho
ai** — ai cũng thấy, ai cũng bấm **Nhận** được. Một hội thoại chỉ sinh đúng
một việc đang mở; khách nhắn thêm không đẻ việc thứ hai. Việc cũ xong rồi
mà khách quay lại thì sinh việc mới.

**Ai thấy việc nào.** Nhân viên thấy việc mình nhận, việc mình giao, và
việc chưa giao cho ai. Ai có `cong_viec.xem_tat_ca` thì thấy hết.

**Giao việc cho người khác cần quyền `cong_viec.giao`.** Tự nhận một việc
chưa ai nhận thì không cần — đó là nhận việc, không phải đẩy việc.

### Ô "Việc quá hạn" trên trang Ca trực

Chỉ hiện khi có, kèm số việc **chưa giao cho ai** — đó là thứ dễ rơi nhất,
vì không ai thấy nó trong danh sách "việc của tôi".

Việc đã Xong hoặc Đã huỷ **không** tính là quá hạn dù hạn đã qua. Đếm chúng
vào là con số chỉ tăng và không bao giờ giảm, và một con số chỉ tăng là con
số người ta thôi nhìn.

---

## Agent là tuỳ chọn — bật tắt theo từng kênh

Dashboard → **Kết nối** → nút **Tắt agent** / **Bật agent** trên từng tài
khoản kênh. Hệ thống hỏi lý do khi tắt; lý do hiện ngay trên thẻ kênh dưới
dạng huy hiệu **agent TẮT**, và vào nhật ký kiểm toán.

Ba nấc, kiểm theo đúng thứ tự này:

| Nấc | Ở đâu | Ý nghĩa |
|---|---|---|
| Toàn cục | Nút **Đang chạy** trên đầu dashboard | Cắt tất cả, mọi kênh |
| **Theo kênh** | Màn Kết nối | Nấc thật sự hay dùng |
| Theo hội thoại | Nút tiếp quản trong hội thoại | Người đã cầm cuộc này |

Cách dùng điển hình: mở agent cho Zalo vì tin ở đó đơn giản và nhiều, để
Facebook cho người trực vì khách ở đó hỏi khó hơn.

### Tắt agent KHÔNG phải là kênh chết

Đây là điều quan trọng nhất, và nó được hiện thực trong **mã**:

- Tin khách vẫn vào, vẫn lưu, vẫn hiện trên dashboard.
- Hội thoại chuyển thẳng sang trạng thái **đã chuyển người**.
- Hệ thống **tự tạo một công việc** cho mỗi hội thoại, mang nhãn
  *agent chuyển*, chưa giao cho ai — ai cũng thấy trên màn Công việc.

Không có vế cuối thì "agent là tuỳ chọn" biến thành "kênh chết im lặng":
tin vào, không ai trả lời, và dashboard vẫn xanh vì không có gì hỏng cả.

Mặc định của mọi kênh, kể cả kênh nối sau này, là **bật**.

---

## Nhiều agent — thêm bằng cấu hình

Dashboard → **Cấu hình** → *Hồ sơ agent* → **Thêm hồ sơ**. Rồi sang
**Kết nối**, chọn hồ sơ cho từng kênh ở ô ngay cạnh nút *Tắt agent*.

Một hồ sơ gồm: tên, mô tả, **hướng dẫn thêm**, và hai ngưỡng — *ngưỡng tự
tin* và *trần chi phí mỗi hội thoại*.

Ví dụ dùng thật: *"Bán hàng Zalo"* nói ngắn, chốt đơn nhanh; *"Chăm sóc sau
bán"* kiên nhẫn hơn và đặt ngưỡng tự tin cao hơn nên chuyển người sớm hơn.

### Cấu hình chỉ SIẾT được, không nới được

Đây là ràng buộc quan trọng nhất của phần này, và nó nằm trong **mã**:

| Ô | Đặt chặt hơn toàn cục | Đặt lỏng hơn toàn cục |
|---|---|---|
| Ngưỡng tự tin | Có hiệu lực — chuyển người sớm hơn | **Bị ép về ngưỡng toàn cục** |
| Trần chi phí | Có hiệu lực — dừng sớm hơn | **Bị ép về trần toàn cục** |
| Hướng dẫn | Thêm vào cuối ngữ cảnh | Không thay được prompt gốc |

Màn hình hiện cả giá trị đã lưu lẫn giá trị **có hiệu lực**, và gắn nhãn
*đã siết về ngưỡng toàn cục* khi hai bên khác nhau. Chỉ hiện giá trị đã lưu
là màn hình nói dối: gõ 0.3, thấy 0.3, hệ thống chạy 0.55.

Vì sao chặt như vậy: sáu lớp lưới trong `agent/core/agent.py` canh luật
quảng cáo mỹ phẩm và ranh giới tư vấn y tế. Nếu một ô nhập trên dashboard
hạ được ngưỡng hay thay được prompt gốc thì nó vừa trở thành đường đi vòng
qua sáu lớp lưới ấy — và người điền ô đó không hề biết mình đang mở.

Xoá một hồ sơ **không** làm kênh ngừng trả lời: chúng rơi về cấu hình mặc
định. Hệ thống nói rõ số kênh bị ảnh hưởng trước khi xoá.

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
