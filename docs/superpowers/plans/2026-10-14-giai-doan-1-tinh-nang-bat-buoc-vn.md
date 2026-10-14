# Giai đoạn 1 — Tính năng bắt buộc ở thị trường VN: kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bịt hai lỗ phân quyền/hỏng-im-lặng tìm ra khi khảo sát, rồi thêm những tính năng mà mọi phần mềm CSKH đa kênh ở VN (Pancake, Haravan, Sapo) đều có và hệ thống này chưa có.

**Architecture:** Mỗi tính năng = một migration (`0027…`), một router riêng dưới `agent/api/` có khai quyền, một khối giao diện trong `dashboard/`. Bảng mới đặt tên tiếng Việt như phần còn lại của lược đồ. Không thêm dịch vụ ngoài; QR dùng `segno` (BSD-3, thuần Python).

**Tech Stack:** FastAPI, asyncpg, Postgres 16 (`unaccent`, `pg_trgm`), openpyxl (đã có), segno, JS thuần.

**Spec:** `docs/superpowers/plans/2026-10-14-lo-trinh-saas-va-khoa-luan.md` (Giai đoạn 1) + khảo sát kiến trúc inbox 14.10.2026.

## Global Constraints

- Migration mới bắt đầu từ `0027_`; KHÔNG sửa migration đã có (checksum).
- Chỉ mục trên cột do migration thêm: đặt trong migration, không trong `schema.sql`.
- Hàm SQL ghi đủ schema (`public.unaccent`) — `tests/test_phuc_hoi_duoc.py`.
- Route mới dưới `/api` phải có `Depends(can_quyen("..."))`; quyền mới vào `QUYEN` và phải có ít nhất một route dùng; muốn vai trò Nhân viên có nó thì INSERT `vai_tro_quyen` trong migration.
- Router mới `include_router` trong `agent/main.py`.
- Mọi đường đọc/ghi hội thoại tôn trọng `account_memberships` (trừ `hoi_thoai.xem_tat_ca`) và mức tầm nhìn (`chan_neu_khong_duoc_tra_loi`).
- Test API dùng Postgres thật (`csdl_kiem_thu`) theo mẫu `tests/test_api_cong_viec.py`.
- Làm trong worktree `.claude/worktrees/giai-doan-1`, nhánh `giai-doan-1`.

---

### Task 1: Phạm vi tài khoản kênh trên các route hội thoại cũ

**Lỗ:** `GET /api/conversations` và `GET /api/conversations/{id}` (`agent/api/routes.py:351,420`) trả MỌI hội thoại kèm toàn bộ tin cho ai có `hoi_thoai.doc` — bỏ qua `account_memberships` mà `agent/api/inbox.py` áp. `send`, `send-file`, `approve`, `takeover`, `release`, `account` cũng không kiểm thành viên.

**Files:** Modify `agent/api/routes.py`; Test `tests/test_pham_vi_kenh_route_cu.py`

- [ ] Test (Postgres thật): hai `channel_accounts` A, B; người dùng `nguoi_thu("hoi_thoai.doc","hoi_thoai.tra_loi","hoi_thoai.nhan")` là thành viên A; hội thoại ở B → `GET /api/conversations` không chứa nó; `GET /api/conversations/{b}` → 404; `POST …/send`, `…/takeover`, `…/release` → 404; người có `hoi_thoai.xem_tat_ca` thấy cả hai.
- [ ] Thêm `async def chan_neu_ngoai_kenh(cid, nguoi)` cạnh `chan_neu_khong_duoc_tra_loi`: `SELECT EXISTS(... account_memberships WHERE account_id = cv.account_id AND user_id = $2)`; ngoài phạm vi → 404 (không lộ hội thoại tồn tại). Gọi ở mọi route liệt kê trên; danh sách thêm mệnh đề `($n OR EXISTS(...))` như `inbox.py:80-85`.
- [ ] Test canh cấu trúc: mọi route có `{conv_id}` trong `routes.py` gọi `chan_neu_ngoai_kenh`.
- [ ] Commit.

### Task 2: Tin nhân viên ngoài cửa sổ 24 giờ không được chết im lặng

**Lỗ:** tin nhân viên không qua `can_send_now()` — Meta từ chối, outbox retry rồi `dead`, khách chờ mãi.

**Files:** `agent/config.py`, `agent/api/routes.py` (`staff_send`, `send-file`), `agent/omnichannel/outbound_service.py`, `agent/workers/outbox_worker.py`, `agent/channels/messenger.py`, `agent/channels/meta_channels.py`; Test `tests/test_cua_so_tin_nhan_vien.py`

- [ ] `Settings.meta_the_human_agent: bool = False` (cần Meta duyệt tính năng Human Agent cho app).
- [ ] Trước khi xếp hàng tin nhân viên: hỏi adapter `can_send_now(ref)`. Trong cửa sổ → như cũ. Ngoài cửa sổ: Messenger/Instagram và cờ bật và tin khách cuối ≤ 7 ngày → payload `{"the": "HUMAN_AGENT"}`; còn lại → **409** với lời giải thích tiếng Việt (ngoài 24h, ngoài 7 ngày, hay chưa bật Human Agent).
- [ ] Payload outbox mang `the`; worker truyền xuống `send_text(ref, text, the=...)`; Messenger gửi `messaging_type: "MESSAGE_TAG", tag: "HUMAN_AGENT"`. Chữ ký `send_text` các adapter khác nhận `**_` để không vỡ.
- [ ] Test: ngoài cửa sổ + cờ tắt → 409 và KHÔNG có dòng outbox; cờ bật + 3 ngày → job có `the`; adapter Messenger dựng đúng body (mock httpx).
- [ ] Commit.

### Task 3: Trả lời nhanh

**Files:** Create `agent/migrations/versions/0027_tra_loi_nhanh.sql`, `agent/api/tra_loi_nhanh.py`; Modify `agent/core/quyen.py`, `agent/main.py`, `dashboard/app.js`, `dashboard/index.html`, `dashboard/app.css`; Test `tests/test_api_tra_loi_nhanh.py`

- [ ] Bảng `tra_loi_nhanh(id uuid pk, ma_tat text unique check ~ '^[a-z0-9_-]{1,32}$', noi_dung text check 1..2000, tao_boi uuid fk nguoi_dung, tao_luc, sua_luc)`.
- [ ] Quyền `tra_loi_nhanh.sua` ("Thêm, sửa mẫu trả lời nhanh"). Đọc danh sách cần `hoi_thoai.tra_loi`.
- [ ] `GET /api/tra-loi-nhanh?q=` · `POST` · `PUT /{id}` · `DELETE /{id}`. Lưu: chạy bộ soi từ cấm quảng cáo đang dùng cho câu trả lời agent; dính từ cấm → 422 nêu từ nào. Ràng buộc hai lần: mẫu nhân viên bấm gửi cũng không được vi phạm luật quảng cáo.
- [ ] UI: gõ `/` đầu ô soạn tin → danh sách lọc theo mã tắt/nội dung, ↑↓ Enter chèn; màn Cấu hình có khối quản lý mẫu.
- [ ] Test: CRUD, mã trùng → 409, từ cấm → 422, thiếu quyền → 403.
- [ ] Commit.

### Task 4: Nhãn và ghi chú nội bộ theo hội thoại

**Files:** `0028_nhan_ghi_chu_hoi_thoai.sql`, `agent/api/hoi_thoai_nhan.py`; UI; Test `tests/test_api_nhan_ghi_chu_hoi_thoai.py`

- [ ] `hoi_thoai_nhan(conversation_id fk on delete cascade, nhan text 1..40, tao_boi, tao_luc, pk(conversation_id, nhan))`; `hoi_thoai_ghi_chu(id, conversation_id fk cascade, noi_dung 1..5000, tao_boi, tao_luc)`; chỉ mục `(nhan)` và `(conversation_id, tao_luc desc)`.
- [ ] Route dưới `/api/inbox/conversations/{id}/nhan` (POST/DELETE, `hoi_thoai.tra_loi`) và `/ghi-chu` (GET `hoi_thoai.doc`, POST `hoi_thoai.tra_loi`), cùng chốt phạm vi kênh của Task 1. `list_conversations` nhận `nhan=`; mỗi dòng trả `nhan: [...]`.
- [ ] Ghi chú KHÔNG BAO GIỜ đi ra kênh: test khẳng định không tạo `outbox_jobs`.
- [ ] UI: chip nhãn trên đầu luồng tin + lọc theo nhãn; khung ghi chú màu khác hẳn tin khách.
- [ ] Commit.

### Task 5: Tìm hội thoại theo nội dung tin

**Files:** `0029_tim_noi_dung_tin.sql`; Modify `agent/api/inbox.py`; UI; Test `tests/test_tim_noi_dung_tin.py`

- [ ] `CREATE EXTENSION IF NOT EXISTS pg_trgm`; `CREATE INDEX … ON messages USING gin (public.bo_dau(content) gin_trgm_ops)`.
- [ ] `list_conversations(q=…)`: `EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id AND public.bo_dau(m.content) LIKE '%'||public.bo_dau($q)||'%')` cộng tên khách/SĐT; `q` < 2 ký tự bỏ qua; thoát `%`/`_` trong `q`.
- [ ] Test: "kem chong nang" tìm ra tin "Kem chống nắng"; ký tự `%` không thành ký tự đại diện; vẫn tôn trọng phạm vi kênh.
- [ ] UI: ô tìm trên danh sách hội thoại, gõ chậm 300ms.
- [ ] Commit.

### Task 6: Người gửi + báo cáo KPI theo nhân viên + xuất Excel

**Files:** `0030_nguoi_gui_tin.sql`, `agent/api/bao_cao_nhan_vien.py`; Modify `outbound_service.py`, `routes.py`; UI; Test `tests/test_bao_cao_nhan_vien.py`

- [ ] `messages.gui_boi uuid NULL REFERENCES nguoi_dung(id)`; `queue_text(..., gui_boi=)` ghi người gửi cho tin role='staff'.
- [ ] `GET /api/bao-cao/nhan-vien?tu=&den=` (`bao_cao.doc`): mỗi nhân viên — số hội thoại được giao, số tin đã gửi, thời gian phản hồi đầu tiên trung vị và p90 (`first_responded_at - created_at` của hội thoại được giao), số đơn tạo (`orders.tao_boi`), số lần trễ SLA (`sla_events`).
- [ ] `GET /api/bao-cao/nhan-vien.xlsx` cùng tham số → openpyxl, `StreamingResponse`, tên file có khoảng ngày.
- [ ] Test: dữ liệu dựng tay cho hai nhân viên → con số đúng; xlsx mở lại được bằng openpyxl và khớp JSON.
- [ ] UI: khối "Hiệu suất nhân viên" ở màn Báo cáo, chọn khoảng ngày, nút Xuất Excel.
- [ ] Commit.

### Task 7: VietQR cho đơn hàng

**Files:** `agent/thanh_toan/vietqr.py`, route trong `routes.py` hoặc `agent/api/thanh_toan.py`; cấu hình động; Test `tests/test_vietqr.py`

- [ ] `tao_payload(bin, so_tk, so_tien, noi_dung) -> str` theo EMVCo/NAPAS: trường 00, 01 (12 động), 38 (GUID `A000000727`, BIN, số TK, `QRIBFTTA`), 53=704, 54 số tiền, 58=VN, 62.08 nội dung, 63 CRC16-CCITT (0x1021, init 0xFFFF). Kiểm bằng véc-tơ đã biết: CRC của chuỗi mẫu tự tính hai cách.
- [ ] Cấu hình ngân hàng (BIN, số TK, tên) trong cấu hình động, sửa ở màn Cấu hình (quyền `cau_hinh.sua`). Thiếu cấu hình → endpoint 409 nói rõ thiếu gì.
- [ ] `GET /api/orders/{id}/vietqr` (`don.doc`) → `{payload, svg}` (segno); nội dung chuyển khoản = mã đơn. Nút "QR thanh toán" ở màn Đơn hàng.
- [ ] Commit.

### Task 8: Bình luận Facebook vào inbox + ẩn bình luận có SĐT + trả lời riêng

**Files:** `agent/channels/binh_luan_meta.py`, Modify `messenger.py` (`parse_nhieu` đọc `entry.changes` field `feed`, item `comment`), `dang_ky_webhook_meta.py` (`feed`), `oauth_meta.py` (scope `pages_read_engagement`, `pages_manage_engagement`); Test `tests/test_binh_luan_meta.py`

- [ ] Bình luận → `InboundMessage` với `meta={"loai": "binh_luan", "comment_id", "post_id"}`, hội thoại riêng theo người bình luận (`conversation_ref = "cmt:<psid hoặc from.id>"`).
- [ ] Có SĐT VN (regex `(0|\+84)(3|5|7|8|9)\d{8}`, cả dạng có dấu cách/chấm) và cấu hình `an_binh_luan_co_sdt` bật → `POST /{comment_id}?is_hidden=true`; ghi `events` để biết đã ẩn; lỗi Graph → ghi nhật ký cảnh báo, không nuốt.
- [ ] Trả lời riêng: tin nhân viên trong hội thoại bình luận đi qua `POST /{page_id}/messages` với `recipient: {comment_id}` (hạn 7 ngày).
- [ ] Test với payload webhook mẫu chính thức + httpx giả: đúng InboundMessage, đúng lời gọi ẩn, không ẩn khi không có SĐT.
- [ ] Commit.

### Task 9: CSAT sau khi đóng hội thoại

**Files:** `0031_csat.sql`, `agent/omnichannel/csat.py`; hook ở chỗ đóng hội thoại và ở `handle_inbound`; báo cáo; Test `tests/test_csat.py`

- [ ] Bảng `csat(id, conversation_id unique, nguoi_xu_ly uuid, gui_luc, diem smallint check 1..5 null, tra_loi_luc)`.
- [ ] Cấu hình `csat_bat` (mặc định tắt). Đóng hội thoại → xếp hàng một tin hỏi chấm 1–5 (qua outbox, tôn trọng cửa sổ 24h — ngoài cửa sổ thì không gửi và ghi lý do).
- [ ] Tin khách tiếp theo trong 24h chỉ gồm một chữ số 1–5 → ghi điểm, KHÔNG chuyển cho agent trả lời.
- [ ] Báo cáo nhân viên (Task 6) thêm cột CSAT trung bình và số phản hồi.
- [ ] Commit.

### Task 10: Gộp và đo lại

- [ ] `python -m scripts.sinh_so_do --ghi` (schema đổi), `python -m pytest -q` (Postgres bật), `ruff check .`
- [ ] Kiểm giao diện thật bằng Browser pane ở 1366px và 375px (memory: rà giao diện bằng DOM).
- [ ] `git merge --ff-only giai-doan-1` từ thư mục chính.
