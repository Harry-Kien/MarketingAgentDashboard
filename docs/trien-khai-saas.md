# Triển khai SaaS — nhiều cửa hàng trên một máy chủ

Tài liệu này dành cho người VẬN HÀNH dịch vụ (bạn), không dành cho chủ cửa
hàng. Mô hình và lý do chọn nó: `docs/superpowers/plans/2026-10-15-giai-doan-2-nen-saas-silo.md`.

```
Internet ──► Caddy (TLS tự động, *.ten-mien-cua-ban.vn)
               ├─► cskh-shopa-app ──► Postgres: CSDL ch_shopa (role ch_shopa)
               │      └─ cskh-shopa-sidecar (Zalo cá nhân)
               └─► cskh-shopb-app ──► Postgres: CSDL ch_shopb (role ch_shopb)
                      └─ cskh-shopb-sidecar
```

Mỗi cửa hàng: CSDL + role riêng (không phải superuser), container riêng,
volume dữ liệu riêng, bí mật riêng. Một cửa hàng hỏng không kéo cửa hàng
khác; xoá một cửa hàng là xoá một CSDL và một volume.

## 1. Máy chủ

- Ubuntu 24.04, **4 vCPU / 16 GB RAM** chở được khoảng 20–30 cửa hàng
  (app ~400 MB + sidecar ~150 MB mỗi cửa hàng, Postgres dùng chung).
- Mở cổng 80 và 443. Không mở 5432 — Postgres chỉ nghe trong mạng Docker.
- Cài Docker Engine + Compose plugin theo tài liệu chính thức của Docker.
- Trỏ DNS **wildcard** `*.ten-mien-cua-ban.vn` về IP máy chủ (bản ghi A).

## 2. Dựng lớp nền (một lần)

```bash
git clone <repo> cskh && cd cskh
python3 -m scripts.cua_hang khoi_tao --email-tls ban@ten-mien-cua-ban.vn
docker build -t cskh-app:latest .
docker build -t cskh-sidecar:latest connectors/zalo-personal-sidecar
docker compose -f trien_khai/docker-compose.nen.yml --env-file trien_khai/.env.nen up -d
```

`khoi_tao` sinh `trien_khai/.env.nen` (mật khẩu superuser Postgres) và
Caddyfile rỗng. Tệp này KHÔNG lên git và KHÔNG có app cửa hàng nào đọc nó.

## 3. Thêm một cửa hàng

```bash
python3 -m scripts.cua_hang tao shopa --ten "Shop A" --ten-mien shopa.ten-mien-cua-ban.vn
```

Lệnh này: tạo CSDL `ch_shopa` + role riêng → sinh `.env` với bí mật riêng →
chạy app + sidecar → chờ app khoẻ → tạo quản trị viên đầu tiên → thêm tên
miền vào Caddy (TLS tự cấp trong vài giây).

Mật khẩu quản trị viên đầu tiên **không in ra màn hình**: nằm ở
`trien_khai/cua_hang/shopa/quan_tri_lan_dau.txt`. Gửi cho chủ cửa hàng qua
kênh an toàn, dặn đổi mật khẩu và bật **bảo mật 2 bước** ngay lần đầu.

Sau đó trong dashboard của cửa hàng:
1. **Cấu hình → Model**: dán khoá Gemini/Anthropic của cửa hàng.
2. **Kết nối**: nối Trang Facebook (đăng nhập Meta), Zalo OA, Zalo cá nhân (quét QR).
3. Khai URL webhook ở Meta/Zalo bằng tên miền của cửa hàng.

## 4. Vận hành hằng ngày

| Việc | Lệnh |
|---|---|
| Danh sách cửa hàng | `python3 -m scripts.cua_hang liet_ke` |
| Kiểm sức khoẻ (mã thoát ≠ 0 nếu hỏng) | `python3 -m scripts.cua_hang kiem` |
| Tạm dừng / chạy lại | `python3 -m scripts.cua_hang tam_dung shopa` · `chay shopa` |
| Khởi động lại sau khi sửa `.env` | `python3 -m scripts.cua_hang khoi_dong_lai shopa` |
| Sao lưu một / tất cả | `python3 -m scripts.cua_hang sao_luu shopa` · `sao_luu --tat-ca` |
| Xoá hẳn (sao lưu trước) | `python3 -m scripts.cua_hang xoa shopa --xac-nhan shopa` |

**Lịch sao lưu** (crontab, 2 giờ sáng): `0 2 * * * cd /srv/cskh && python3 -m scripts.cua_hang sao_luu --tat-ca`.
Chép thư mục `trien_khai/sao_luu/` ra NGOÀI máy chủ (ổ khác, dịch vụ lưu trữ) —
bản sao lưu nằm cùng máy với CSDL không cứu được khi máy hỏng.

**Khôi phục** một cửa hàng: tạm dừng cửa hàng, rồi
`docker exec -i cskh-postgres pg_restore -U quan_tri -d ch_shopa --clean < tep.dump`,
rồi `chay shopa`.

## 5. Cập nhật phiên bản

```bash
git pull
docker build -t cskh-app:latest .
python3 -m scripts.cua_hang khoi_dong_lai shopa      # thử MỘT cửa hàng trước
python3 -m scripts.cua_hang kiem
```

Migration chạy tự động khi app khởi động, trên CSDL của từng cửa hàng, bằng
role của chính cửa hàng ấy (không cần superuser). Cửa hàng đầu lên khoẻ rồi
mới khởi động lại các cửa hàng còn lại.

## 6. Quan sát

- `SENTRY_DSN` trong `.env` của cửa hàng → lỗi về Sentry hoặc GlitchTip tự host.
- `METRICS_TOKEN` → `/metrics` cho Prometheus: outbox theo trạng thái (cảnh
  báo khi `dead` > 0), tin vào/ra, hội thoại chờ người, tuổi nhịp đập từng
  vòng nền, chi phí model. Xem `agent/quan_sat.py`.

## 7. Giới hạn đã biết

- **Một bản app mỗi cửa hàng.** Vòng nền (outbox, lịch đăng bài, giữ phiên
  Zalo) không chịu được hai bản cùng chạy. Muốn chịu tải hơn: tăng CPU/RAM
  cho container, không tăng số bản.
- **Zalo cá nhân** dùng API không chính thức (zca-js) — có thể bị Zalo khoá
  tài khoản. Nói rõ với chủ cửa hàng; ưu tiên Zalo OA.
- **Meta App Review**: cửa hàng ngoài chủ app chỉ nối được Trang sau khi Meta
  duyệt `pages_messaging`, `pages_manage_engagement`, Human Agent.
- Trên vài trăm cửa hàng, chi phí bộ nhớ của mô hình silo lớn dần — lúc đó
  cân nhắc mô hình pool (một CSDL + RLS), đã có bản khảo sát làm đầu vào.
