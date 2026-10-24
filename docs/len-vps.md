# Đưa cửa hàng lên VPS — từng bước

Tài liệu cho **chủ dự án**: chuyển cửa hàng đang chạy trên máy cá nhân lên
một máy chủ thuê (VPS) để chạy 24/7. Toàn bộ quy trình đã được **diễn tập
thật** ngày 24.10.2026 (Docker của máy cũ đóng vai VPS): dữ liệu thật
198/198 tin, ERPNext khôi phục và xác thực bằng khoá API cũ, token
Facebook/Zalo giải mã được, sao lưu + thử phục hồi chạy được.

Mô hình kỹ thuật (nhiều cửa hàng một máy, mỗi cửa hàng một CSDL riêng):
`docs/trien-khai-saas.md`. Tài liệu này chỉ đi đường ngắn nhất cho MỘT cửa hàng.

Thời gian: ~1 giờ lần đầu, trong đó cửa hàng **gián đoạn khoảng 15 phút**
(từ bước 5 tới hết bước 7).

---

## 0. Chuẩn bị (làm trước, không gián đoạn gì)

**Thuê VPS** — cấu hình tối thiểu, vì ERPNext chạy chung máy:

| | Tối thiểu | Ghi chú |
|---|---|---|
| Hệ điều hành | **Ubuntu 24.04 LTS** | script cài chỉ viết cho bản này |
| CPU / RAM | 4 vCPU / **8 GB** | ERPNext ~2,5 GB, app + sidecar ~1 GB, Postgres |
| Ổ đĩa | 80 GB SSD | sao lưu giữ 14 ngày nằm trên máy |
| Vị trí | Việt Nam hoặc Singapore | gần khách, gần máy chủ Zalo |

Nhà cung cấp nào cũng được miễn có Ubuntu 24.04 và địa chỉ IPv4 riêng.

**Mua tên miền** (hoặc dùng tên miền sẵn có), định hai tên con, ví dụ:
`cskh.blanica.vn` (dashboard + webhook) và `erp.blanica.vn` (ERPNext).

**Tạo khoá Vertex AI** (Google Cloud Console, đúng dự án đang dùng — giá trị
`GCP_PROJECT_ID` trong `.env` máy này):

1. IAM & Admin → **Service Accounts** → Create service account, tên `cskh-vps`.
2. Cấp vai trò **Vertex AI User**.
3. Vào tài khoản vừa tạo → **Keys** → Add key → **JSON** → tải về.

Tệp JSON này là chìa khoá trả tiền model — đừng gửi qua chat, đừng để trong
thư mục dự án.

**Trỏ DNS**: hai bản ghi **A** của hai tên con về IP của VPS. Trỏ sớm, vì DNS
cần vài phút tới vài giờ để có hiệu lực; Caddy chỉ xin được chứng chỉ HTTPS
khi tên miền đã trỏ đúng.

---

## 1. Cài máy chủ (một lệnh)

SSH vào VPS bằng tài khoản root, rồi:

```bash
git clone <địa chỉ repo> /srv/cskh
cd /srv/cskh
bash trien_khai/cai_vps.sh --email-tls ban@vi-du.vn --erp erp.blanica.vn
```

Repo riêng tư thì `git clone` cần quyền: thêm **deploy key** (SSH, chỉ đọc)
vào repo trên GitHub, hoặc dùng token cá nhân.

Script cài Docker, tường lửa (chỉ mở SSH/80/443), swap, cập nhật bảo mật tự
động, dựng image, chạy Postgres + Caddy + ERPNext, và đặt lịch: người canh
5 phút một lần, sao lưu 2 giờ sáng, thử phục hồi mỗi Chủ nhật. Chạy lại
script lần nữa là vô hại.

Chờ ERPNext khởi động xong (~2 phút): `python3 -m scripts.cua_hang erp ping`.

---

## 2. Chép khoá Vertex lên VPS

Từ máy này (PowerShell):

```powershell
scp C:\duong\dan\khoa-cskh-vps.json root@IP_VPS:/root/gcp.json
```

---

## 3. Kiểm ERPNext máy này đang chạy

Gói chuyển nhà mang theo dữ liệu ERPNext, nên nó phải đang chạy:

```powershell
curl.exe -s http://127.0.0.1:8080/api/method/ping
```

Phải ra `{"message":"pong"}`. Không ra thì bật: Docker Desktop →
khởi động các container `erpnext-*`.

---

## 4. Diễn tập (tuỳ chọn, khuyên làm)

Đóng gói NÓNG (máy này vẫn phục vụ khách), nhập lên VPS ở chế độ diễn tập —
không gửi tin, không giữ phiên Zalo, không đụng khách:

```powershell
python -m scripts.chuyen_nha dong_goi
```

Chép gói lên VPS (bước 6), chạy lệnh bước 7 **thêm `--dien-tap`** và một mã
khác (ví dụ `thu`), kiểm dashboard, rồi xoá: `python3 -m scripts.cua_hang xoa thu --xac-nhan thu`.

---

## 5. Đóng gói THẬT — bắt đầu gián đoạn

```powershell
python -m scripts.chuyen_nha dong_goi --dung-may-nay
```

Lệnh này **tắt task người canh và dừng app + sidecar trên máy này** trước
khi gói — hai bản cùng chạy là khách nhận tin trả lời đôi, và Zalo đá văng
một trong hai phiên. Ra hai tệp trong `chuyen_nha\`:

- `goi-<thời điểm>.cskh` — gói đã mã hoá (CSDL, tệp, cấu hình, ERPNext)
- `goi-<thời điểm>.mat-khau.txt` — mật khẩu của gói

---

## 6. Chép gói lên VPS — HAI lần riêng

```powershell
scp chuyen_nha\goi-XXXX.cskh root@IP_VPS:/root/
scp chuyen_nha\goi-XXXX.mat-khau.txt root@IP_VPS:/root/
```

Gói chứa toàn bộ dữ liệu khách và khoá giải mã token Facebook/Zalo. Mật
khẩu đi riêng để một tệp lạc không lộ được gì.

---

## 7. Nhập cửa hàng trên VPS

```bash
cd /srv/cskh
python3 -m scripts.cua_hang nhap blanica --ten "BLANICA" --ten-mien cskh.blanica.vn \
  --goi /root/goi-XXXX.cskh --mat-khau-tep /root/goi-XXXX.mat-khau.txt --gcp-khoa /root/gcp.json
```

Lệnh khôi phục ERPNext, CSDL, tệp dữ liệu, rồi **so số tin nhắn với gói** —
thiếu dù một tin là dừng và dọn sạch, không bật cửa hàng dở dang. Xong ra
dòng `Đã nhập cửa hàng blanica: … 198/198 tin …`.

Mở `https://cskh.blanica.vn` — đăng nhập bằng **tài khoản cũ** (đi theo CSDL).

---

## 8. Khai lại địa chỉ ở Meta và Zalo — hết gián đoạn

Tên miền đã cố định, nên đây là **lần khai cuối** (không còn cảnh tunnel
đổi tên miền rồi kênh chết im lặng).

**Meta (Facebook/Instagram)** — developers.facebook.com → ứng dụng của bạn:

| Mục | Giá trị mới |
|---|---|
| Webhooks → Callback URL | `https://cskh.blanica.vn/webhook/native/meta` |
| Verify token | giữ nguyên như cũ |
| Facebook Login → Valid OAuth Redirect URIs | `https://cskh.blanica.vn/api/connect/meta/callback` |
| App Domains | `cskh.blanica.vn` |

**Zalo OA** — developers.zalo.me → ứng dụng:

| Mục | Giá trị mới |
|---|---|
| Webhook URL | `https://cskh.blanica.vn/webhook/native/zalo-oa/<account_id>` — lệnh ở bước 9 in đúng địa chỉ |
| Callback URL (đăng nhập OA) | `https://cskh.blanica.vn/api/connect/zalo-oa/callback` |

Zalo cá nhân KHÔNG cần khai gì: phiên đăng nhập đi theo CSDL và tự khôi
phục. Zalo đôi khi đòi đăng nhập lại khi thấy địa chỉ IP mới — khi đó vào
dashboard → **Kết nối** → quét QR.

---

## 9. Kiểm — đừng tin, hãy chạy

```bash
docker exec cskh-blanica-app python -m scripts.san_sang
```

Mục nào `[CHẶN]` thì làm theo dòng `└─` ngay dưới nó. Sau đó nhắn thử một
tin vào Trang Facebook, một tin vào Zalo OA, một tin vào Zalo cá nhân — và
xem chúng hiện trong dashboard.

---

## 10. Dọn dẹp

- Xoá gói và mật khẩu trên **cả hai máy** khi đã chạy ổn một tuần:
  `rm /root/goi-*` trên VPS, xoá thư mục `chuyen_nha\` trên máy này.
- Điền `CANH_GAC_WEBHOOK` trong `/srv/cskh/trien_khai/.env.nen` để nhận báo
  động khi người canh phải bật lại container hay thử phục hồi hỏng.
- **Chép sao lưu ra ngoài VPS**: thư mục `/srv/cskh/trien_khai/sao_luu/` và
  `/srv/cskh/trien_khai/erp/sao_luu/` — sao lưu nằm cùng máy với CSDL không
  cứu được khi máy hỏng.

---

## Quay lại máy cũ (nếu VPS có sự cố trong ngày đầu)

Máy này vẫn giữ nguyên dữ liệu tới lúc đóng gói. Bật lại:

```powershell
schtasks /change /tn CanhGacMarketingAgent /enable
```

```powershell
schtasks /run /tn CanhGacMarketingAgent
```

rồi dừng cửa hàng trên VPS (`python3 -m scripts.cua_hang tam_dung blanica`)
và khai lại địa chỉ ở Meta/Zalo về tunnel. Tin nhắn khách gửi tới VPS trong
khoảng ấy nằm trên VPS — đừng chạy hai nơi cùng lúc.

---

## Vận hành hằng ngày trên VPS

| Việc | Lệnh (trong `/srv/cskh`) |
|---|---|
| Sức khoẻ | `python3 -m scripts.cua_hang kiem` |
| Sẵn sàng chạy thật | `docker exec cskh-blanica-app python -m scripts.san_sang` |
| Nhật ký app | `docker logs --tail 100 cskh-blanica-app` |
| Sao lưu ngay | `python3 -m scripts.cua_hang sao_luu blanica` |
| Thử phục hồi | `python3 -m scripts.cua_hang thu_phuc_hoi blanica` |
| Cập nhật phiên bản | `git pull && docker build -t cskh-app:latest . && python3 -m scripts.cua_hang khoi_dong_lai blanica` |
| Nhật ký người canh | `tail /var/log/cskh-canh.log` |
