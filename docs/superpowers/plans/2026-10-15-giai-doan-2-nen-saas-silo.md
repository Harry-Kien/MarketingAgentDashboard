# Giai đoạn 2 — Nền SaaS theo mô hình silo: kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một máy chủ Linux chạy được NHIỀU cửa hàng, mỗi cửa hàng cô lập hoàn toàn, dựng/dừng/sao lưu/cập nhật bằng một lệnh — host lên là vận hành được.

**Architecture:** Mô hình **silo** (AWS SaaS Lens: silo / bridge / pool): mỗi cửa hàng một CSDL + role Postgres riêng và một container app riêng (cùng một image), chung một máy chủ Postgres và một reverse proxy Caddy cấp TLS tự động theo tên miền con. Một "mặt phẳng điều khiển" nhỏ (`scripts/cua_hang.py` + CSDL `saas_dieu_khien`) giữ danh sách cửa hàng và sinh cấu hình.

**Tech Stack:** Docker, Docker Compose, Postgres 16 + pgvector, Caddy 2 (Apache-2.0), Python 3.12, Node 22 (sidecar).

**Spec:** `docs/superpowers/plans/2026-10-14-lo-trinh-saas-va-khoa-luan.md` (Giai đoạn 2) + khảo sát truy cập CSDL 15.10.2026.

## Vì sao silo chứ không RLS (quyết định kiến trúc)

Khảo sát 15.10.2026 đo được:
- App kết nối bằng **superuser** (`POSTGRES_USER: agent`) — superuser bỏ qua RLS kể cả `FORCE`.
- ~50 bảng không có khoá nào suy ra cửa hàng; ~20 ràng buộc UNIQUE toàn cục
  (`orders.ma_don`, `nguoi_dung.ten_dang_nhap`, `cau_hinh_bi_mat.khoa`…).
- 13 vòng nền chạy xuyên dữ liệu; >10 bộ đệm trong tiến trình không theo cửa hàng.
- Bật RLS sai một chỗ = **âm thầm thấy 0 dòng**: đăng nhập hỏng, outbox ứ,
  xoá dữ liệu cá nhân xoá 0 dòng, canh gác báo "khoẻ" vì không thấy gì.

Silo cô lập TUYỆT ĐỐI mà không sửa truy vấn nào; sao lưu/khôi phục/xoá theo
từng cửa hàng (khớp Luật BVDLCN 91/2025: xoá dữ liệu một khách hàng doanh
nghiệp = xoá một CSDL); một cửa hàng lỗi không kéo cửa hàng khác. Giá phải
trả: ~250–400 MB RAM mỗi cửa hàng — một máy 16 GB chở được vài chục cửa
hàng, đủ cho giai đoạn đầu. Chuyển sang pool + RLS khi vượt vài trăm cửa
hàng là một dự án riêng, đã có bản khảo sát làm đầu vào.

## Global Constraints

- Không đổi hành vi của app khi chạy một cửa hàng trên Windows như hiện nay.
- Mỗi cửa hàng: ĐÚNG MỘT bản app (vòng nền không chịu được hai bản) — compose ghi rõ, test canh.
- Bí mật sinh bằng `secrets`, ghi vào tệp env của cửa hàng, không in ra màn hình.
- Role Postgres của cửa hàng KHÔNG phải superuser, chỉ sở hữu CSDL của mình.
- Mọi lệnh phá huỷ (`xoa`) đòi sao lưu trước + gõ lại mã cửa hàng.
- Worktree `.claude/worktrees/giai-doan-2`, nhánh `giai-doan-2`.

---

### Task 1: Image cho app và sidecar

**Files:** Create `Dockerfile`, `.dockerignore`, `connectors/zalo-personal-sidecar/Dockerfile`; Test `tests/test_dong_goi_container.py`

- [ ] `Dockerfile`: `python:3.12-slim`, cài `ffmpeg` (video), `pip install -r requirements.txt`, user không phải root (`uid 10001`), `WORKDIR /app`, `ENV VAI_TRO_TIEN_TRINH=tat_ca`, `HEALTHCHECK` gọi `/healthz`, `CMD ["python","-m","uvicorn","agent.main:app","--host","0.0.0.0","--port","8000","--proxy-headers"]`.
- [ ] `.dockerignore`: `.env*` (trừ `.env.example`), `data/`, `.venv`, `.git`, `.claude`, `ZaloCRM`, `chatwoot-personal`, `video-studio`, `*.log`, `output/`.
- [ ] Sidecar: `node:22-slim`, `npm ci --omit=dev`, user `node`, `CMD ["node","src/server.mjs"]`.
- [ ] Test tĩnh: Dockerfile không chạy root, có HEALTHCHECK, `.dockerignore` chặn `.env` và `data/`; CI thêm bước `docker build` (không push).

### Task 2: Postgres dùng chung, mỗi cửa hàng một CSDL + role

**Files:** Create `trien_khai/docker-compose.nen.yml` (postgres + caddy), `trien_khai/postgres/khoi_tao.sql`; `scripts/cua_hang.py` (phần CSDL); Test `tests/test_cua_hang_csdl.py`

- [ ] `tao_csdl(ma)`: `CREATE ROLE ch_<ma> LOGIN PASSWORD <ngẫu nhiên> NOSUPERUSER NOCREATEDB NOCREATEROLE`; `CREATE DATABASE ch_<ma> OWNER ch_<ma>`; trong CSDL ấy (bằng superuser): `CREATE EXTENSION vector, unaccent, pg_trgm, "uuid-ossp"` (role thường không tạo được `vector`), `REVOKE CONNECT ON DATABASE ch_<ma> FROM PUBLIC`.
- [ ] `ma` chỉ `[a-z0-9]{3,20}` — đi vào tên role/CSDL, kiểm trước khi ghép SQL (định danh, không tham số hoá được).
- [ ] Test Postgres thật: tạo `ch_kta`, `ch_ktb`; role A không kết nối được CSDL B; app chạy migration đầy đủ trên CSDL A bằng role A (không superuser) — chứng minh migration không đòi quyền superuser.

### Task 3: Mặt phẳng điều khiển `scripts/cua_hang.py`

**Files:** Create `scripts/cua_hang.py`, `trien_khai/mau/env.cua_hang`, `trien_khai/mau/compose.cua_hang.yml`; Test `tests/test_cua_hang_cli.py`

- [ ] CSDL `saas_dieu_khien`, bảng `cua_hang(ma pk, ten, ten_mien unique, goi, trang_thai ∈ {chay,tam_dung,da_xoa}, tao_luc, cap_nhat_luc)`.
- [ ] `tao <ma> --ten --ten-mien`: CSDL+role (Task 2) → sinh `trien_khai/cua_hang/<ma>/.env` từ mẫu (DATABASE_URL tới `ch_<ma>`, `CREDENTIAL_MASTER_KEYS`, `WEBHOOK_SECRET`, `ZALO_SIDECAR_SECRET`, `PUBLIC_BASE_URL=https://<ten_mien>`, `COOKIE_BAO_MAT=true`) → sinh `compose.yml` (app, sidecar, mạng nội bộ, volume `data`) → `docker compose -p cskh-<ma> up -d` → tạo quản trị viên đầu tiên, mật khẩu ghi vào `trien_khai/cua_hang/<ma>/quan_tri_lan_dau.txt` (không in) → ghi Caddy → reload.
- [ ] `liet_ke` · `kiem` (gọi `/healthz` từng cửa hàng, mã thoát ≠ 0 nếu có cửa hàng hỏng) · `tam_dung` · `chay` · `sao_luu <ma>|--tat-ca` (`pg_dump -Fc` + nén volume `data`) · `cap_nhat` (kéo image mới, khởi động lại từng cửa hàng, dừng nếu một cửa hàng không lên lại) · `xoa <ma> --xac-nhan <ma>` (sao lưu trước, rồi drop CSDL/role, xoá thư mục, đánh dấu `da_xoa`).
- [ ] Test: sinh tệp vào thư mục tạm với docker giả (subprocess bị thay); env không chứa giá trị trùng giữa hai cửa hàng; compose có `deploy.replicas: 1` / không `scale`; `ma` sai dạng bị từ chối trước khi chạm CSDL.

### Task 4: Caddy — TLS tự động, tên miền con, header bảo mật

**Files:** `trien_khai/caddy/Caddyfile.mau`; phần sinh trong `scripts/cua_hang.py`; Test trong `tests/test_cua_hang_cli.py`

- [ ] Mỗi cửa hàng: `<ten_mien> { reverse_proxy cskh-<ma>-app:8000; header { Strict-Transport-Security "max-age=31536000"; X-Content-Type-Options nosniff; Referrer-Policy strict-origin-when-cross-origin; X-Frame-Options SAMEORIGIN } }`.
- [ ] `/webhook/*` không qua giới hạn đăng nhập; giới hạn kích thước body 20 MB (ảnh khách gửi).

### Task 5: Chặn dò mật khẩu theo IP + 2FA TOTP

**Files:** `agent/core/xac_thuc.py`, `agent/api/routes.py`, migration `0032_hai_buoc.sql`, UI đăng nhập + màn Tài khoản; Test `tests/test_hai_buoc.py`

- [ ] Đếm sai mật khẩu theo (IP, tên) trong bảng `dang_nhap_that_bai` thay bộ nhớ tiến trình (khởi động lại không xoá bộ đếm).
- [ ] TOTP (pyotp, MIT): bật/tắt ở màn Tài khoản (hiện QR bằng segno), mã dự phòng băm scrypt; đăng nhập có 2FA đòi mã thứ hai; quản trị viên bắt buộc được bật bằng cấu hình.

### Task 6: Quan sát — lỗi và số đo

**Files:** `agent/quan_sat.py`, `agent/main.py`; Test `tests/test_quan_sat.py`

- [ ] `SENTRY_DSN` có thì bật sentry-sdk (MIT; tự host GlitchTip được), `send_default_pii=False`, lọc token như `nhat_ky.py`.
- [ ] `/metrics` (prometheus-client, Apache-2.0) chỉ trả cho IP nội bộ hoặc token: số tin vào/ra, độ dài outbox, job dead, độ trễ agent, chi phí model.

### Task 7: Tài liệu vận hành + nghiệm thu trên Linux

**Files:** `docs/trien-khai-saas.md`; Test `tests/test_tai_lieu_trien_khai.py`

- [ ] Từng bước: thuê VPS (Ubuntu 24.04, ≥4 vCPU/16 GB), cài Docker, trỏ DNS wildcard `*.<tên miền>`, `docker compose -f trien_khai/docker-compose.nen.yml up -d`, `python -m scripts.cua_hang tao …`, đăng ký webhook Meta/Zalo theo tên miền cửa hàng, lịch sao lưu (cron `cua_hang sao_luu --tat-ca`), khôi phục, cập nhật phiên bản.
- [ ] Mọi lệnh và đường dẫn trong tài liệu tồn tại (test).
