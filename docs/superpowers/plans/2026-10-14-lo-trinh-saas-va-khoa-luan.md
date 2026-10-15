# Lộ trình: từ hệ thống một cửa hàng tới SaaS vận hành được — và khóa luận đạt chuẩn

> Lộ trình tổng. Mỗi giai đoạn có **kế hoạch chi tiết riêng**, viết khi tới
> lượt — vì giai đoạn sau phụ thuộc vào thứ giai đoạn trước dựng ra. Viết
> chi tiết cả bốn ngay bây giờ là viết bốn bản đoán.

**Căn cứ:** đợt rà 14.10.2026 — sáu agent rà song song (tài liệu học thuật,
chất lượng mã, bảo mật, kiểm kê tính năng, đối thủ VN/quốc tế, repo GitHub
kèm giấy phép), mọi phát hiện quan trọng đã kiểm lại trực tiếp.

Số đo tại thời điểm rà: 3310 passed / 3 skipped (Postgres thật, 15 phút),
ruff sạch, 0 bí mật trong git, **0 bảng có khoá thuê bao**, không đo
coverage, không kiểm kiểu.

---

## Nguyên tắc xuyên suốt

1. **Khác biệt trước, đuổi kịp sau.** Không đua số tính năng với Pancake.
   Lợi thế thật là *AI CSKH tuân thủ luật quảng cáo mỹ phẩm, có bằng chứng
   đo được*. Tính năng "bắt buộc ở VN" chỉ làm tới mức đủ.
2. **Giấy phép là ràng buộc kiến trúc.** Chỉ nhúng MIT/Apache/BSD. AGPL,
   ELv2, FSL, BUSL, Sustainable Use: chỉ chạy riêng, không sửa, không cho
   khách thao tác. n8n KHÔNG được làm flow builder cho cửa hàng.
3. **Mượn thiết kế, không chép mã** (Chatwoot: `account_id` mọi bảng,
   automation rules dạng dữ liệu, canned responses, macros, CSAT).
4. Mọi quy ước trong `CLAUDE.md` giữ nguyên: ràng buộc hiện thực hai lần,
   mỗi ràng buộc có test canh, hỏng phải nổ to.

---

## Giai đoạn 0 — Khóa luận và bảo mật

Kế hoạch: `2026-10-14-giai-doan-0-khoa-luan-bao-mat.md`

- Sửa 4 điểm bảo mật + phiên lưu dạng băm + bí mật compose ra `.env`
- Sửa mâu thuẫn tài liệu (ca minh hoạ gõ cứng, "13 lần" vs "4 lần", số test cũ)
- Đo coverage trong CI
- Bộ đo **ablation** (tắt từng lớp lưới) + chạy lặp có kiểm soát + thống kê
  đúng (trung bình ± độ lệch, khoảng tin cậy Wilson)
- Khung chương khóa luận ánh xạ tới bằng chứng
- **Chạy đo thật** (tốn tiền API) — hỏi chủ dự án trước

## Giai đoạn 1 — Tính năng bắt buộc ở thị trường VN

Thứ tự theo tác động lên người trực mỗi ngày:

1. Trả lời nhanh (`/` + mã tắt), có lọc từ cấm quảng cáo ngay lúc lưu
2. Nhãn hội thoại + ghi chú nội bộ theo HỘI THOẠI (hiện chỉ có theo khách)
3. Tìm theo nội dung tin — Postgres FTS + `unaccent` + `pg_trgm`
4. Bình luận Facebook/Instagram: webhook `feed`, gom vào inbox, **tự ẩn
   bình luận có SĐT**, trả lời riêng (private reply, hạn 7 ngày)
5. Thẻ `HUMAN_AGENT` cho Messenger — nhân viên trả lời được trong 7 ngày
6. Báo cáo KPI theo nhân viên (FRT, thời gian xử lý, số đơn chốt) + biểu
   đồ thật + xuất Excel
7. VietQR (EMVCo, tự sinh) trong đơn; thêm GHTK bên cạnh GHN
8. Phân ca theo nhân viên; CSAT sau khi đóng hội thoại

## Giai đoạn 2 — Nền SaaS

Kế hoạch: `2026-10-15-giai-doan-2-nen-saas-silo.md`

> **Đổi hướng 15.10.2026:** đa thuê bao theo mô hình **silo** (mỗi cửa hàng
> một CSDL + một container), KHÔNG phải RLS. Khảo sát đo được app chạy bằng
> superuser (bỏ qua RLS), ~50 bảng không có khoá cửa hàng, 13 vòng nền và
> >10 bộ đệm xuyên dữ liệu — bật RLS sai một chỗ là "âm thầm thấy 0 dòng".
> Lý do đầy đủ trong kế hoạch Giai đoạn 2. Pool + RLS là dự án riêng khi
> vượt vài trăm cửa hàng.

1. ~~RLS trên một CSDL chung~~ → silo: `scripts/cua_hang.py` dựng CSDL,
   role, container, tên miền TLS cho từng cửa hàng.
2. **Vòng nền chạy được nhiều bản:** PgQueuer (MIT) cho việc bền vững;
   advisory lock bầu một "trưởng" cho vòng định kỳ (`schedule_loop` hiện có
   thể **đăng bài hai lần**).
3. Trạng thái trong bộ nhớ → CSDL (`runtime.STATE`, `cau_hinh_dong`, bộ đếm
   chống dò mật khẩu); tệp đính kèm → kho đối tượng (S3-tương thích).
4. 2FA TOTP (pyotp), API key theo cửa hàng, webhook ra ngoài có ký HMAC,
   giới hạn tốc độ theo cửa hàng (slowapi).
5. Quan sát: sentry-python + GlitchTip, prometheus-client, Langfuse.

## Giai đoạn 3 — Thương mại

1. Gói cước + hạn mức (số kênh, số nhân viên, số hội thoại AI/tháng) —
   bảng Postgres, không dùng Lago (AGPL)
2. Thu phí qua payOS/SePay (VietQR + webhook)
3. Đăng ký tự phục vụ, dùng thử 14 ngày, trình hướng dẫn kết nối kênh
4. Automation rules dạng dữ liệu (sự kiện → điều kiện → hành động) thay n8n
   phía khách
5. Tuân thủ Luật BVDLCN 91/2025 + NĐ 356/2025: đồng ý tách theo mục đích,
   xử lý yêu cầu chủ thể dữ liệu, ảnh da = dữ liệu sức khoẻ nhạy cảm, ghi
   nhận việc gửi dữ liệu ra nước ngoài (gọi model)
6. Đóng gói triển khai: image Docker, `docker-compose.prod.yml`, reverse
   proxy TLS, sao lưu ra ngoài máy, runbook

## Rủi ro đã biết, không giải được bằng mã

- **Zalo cá nhân qua zca-js** vi phạm điều khoản Zalo — có thể bị khoá tài
  khoản. Với SaaS: bán kèm cảnh báo, ưu tiên Zalo OA.
- **Meta App Review** (Advanced Access `pages_messaging`, `human_agent`) bắt
  buộc trước khi cho cửa hàng khác kết nối fanpage.
- **n8n**: chỉ chủ dự án dựng workflow. Hỏi license@n8n.io trước khi bán.
