# Audit và kế hoạch nâng cấp — 20.11.2026

Đối chiếu từng yêu cầu của bản "Nâng cấp và hoàn thiện hệ thống AI Agent" với
mã nguồn thật (commit `bd227a6`) và dữ liệu thật (đọc, không ghi). Trạng thái:

- **Có-tốt** — đã có, chạy đúng.
- **Có-cần sửa** — đã có nhưng có lỗi hoặc lệch yêu cầu.
- **Một phần** — có nền, thiếu một phần đáng kể.
- **Chưa có** — phải làm mới.

---

## 1. Lỗi thật tìm được khi Audit (ưu tiên sửa trước mọi tính năng mới)

| # | Lỗi | Hậu quả | Mức |
|---|---|---|---|
| L1 | **Hội thoại nhóm Zalo bị ghi đè danh tính bởi người nhắn cuối** (`zalo_personal.py:157-171` + upsert `inbox_service.py:262-267`) | Nhóm mang tên một cá nhân; nhóm dùng chung hồ sơ khách với chat riêng của người đó; **trí nhớ khách riêng bị đưa vào câu trả lời trong nhóm** (lộ dữ liệu cá nhân) | Nghiêm trọng |
| L2 | Bảng `messages` không có cột người gửi | Trong nhóm, mọi người hiện thành một "khách" | Nghiêm trọng |
| L3 | `thread_type` NULL trên mọi hội thoại cũ (backfill 0042 dựa vào bảng chỉ giữ 3 ngày) | Hệ thống không biết hội thoại nào là nhóm; trả lời nhóm bị Zalo từ chối "Tham số không hợp lệ" | Cao |
| L4 | **Leo thang quyền**: ai có `nguoi_dung.sua` tự gán được "Quản trị" hoặc tạo vai trò toàn quyền (`api/quyen.py`) | Một nhân viên được giao quản lý nhân sự chiếm toàn quyền hệ thống | Nghiêm trọng (bảo mật) |
| L5 | `GET /api/events` (toàn bộ nhật ký kiểm toán, kể cả đổi quyền) mở cho mọi người có `hoi_thoai.doc` | Nhân viên thường đọc được nhật ký quản trị | Cao (bảo mật) |
| L6 | Verify token Meta đọc được bằng quyền chỉ-đọc `kenh.doc` | Lộ bí mật kênh cho nhân viên thường | Trung bình (bảo mật) |
| L7 | "Duyệt trước khi gửi" của TỪNG hội thoại bị bỏ qua khi chế độ chung là Tự động (`xu_ly_tin_vao.py:403`) | Nhân viên tưởng đã khoá, AI vẫn tự gửi | Cao (chưa xảy ra vì đang ở chế độ Gợi ý) |
| L8 | Duyệt bản nháp AI không ghi ai duyệt | Không truy được trách nhiệm | Trung bình |
| L9 | Media khách gửi chỉ lưu URL CDN của hãng; `storage_key` lưu đường dẫn tuyệt đối Windows | Ảnh khách mất khi link hết hạn; ảnh sản phẩm hỏng khi chuyển lên VPS | Trung bình |
| L10 | Cột "Trễ SLA" của báo cáo nhân viên đếm sai (không lọc khoảng ngày, nhân lên theo số lần giao) | Đánh giá nhân viên sai | Trung bình |
| L11 | Nhân viên mới tạo bằng script không có dòng vai trò | Tài khoản không vào được chức năng nào dù script báo "quản trị" | Thấp |
| L12 | Facebook: Graph lỗi một lần là tên hội thoại quay về "Khách" | Tên khách chập chờn | Thấp |

---

## 2. Bảng Audit theo 14 phần

### Phần 1 + 8 — Phân quyền, phê duyệt, vai trò động
| Yêu cầu | Trạng thái | Ghi chú |
|---|---|---|
| Vai trò động: tạo/sửa/xoá, gán cho nhân viên, quyền theo `module.hành_động`, không cần sửa mã | Có-tốt | 40 quyền; chặn khoá-cửa-ngoài; route thiếu quyền thì máy chủ không lên |
| 3 cấp (không / cần duyệt / tự động) | **Chưa có** | Mỗi quyền chỉ có/không |
| Cơ chế phê duyệt chung | Một phần | 3 luồng duyệt viết riêng: đơn ≥ ngưỡng, xoá dữ liệu (2 người), bản nháp AI |
| Quyền theo phòng ban / cá nhân | Chưa có | Nhóm (`teams`) chỉ dùng cho định tuyến |
| Cấp Quản trị / Quản lý / Trưởng nhóm / Nhân viên | Một phần | Chỉ có sẵn "Quản trị", "Nhân viên" |
| Uỷ quyền khi vắng | Chưa có | |
| Lịch sử yêu cầu–duyệt; nhật ký đổi quyền | Có-cần sửa | Có sự kiện nhưng không có trước/sau, không có màn xem |

### Phần 2 + 5 + 10 — AI Agent, Rules, cấu hình chung, gợi ý & xác minh
| Yêu cầu | Trạng thái | Ghi chú |
|---|---|---|
| Khu cấu hình AI Agent riêng | Có-cần sửa | Có, nhưng rải ở Cấu hình / Kỹ năng / Tri thức / Phòng thử |
| Rules AI tuân thủ | Một phần | 6 lớp lưới cứng trong mã (đúng nguyên tắc) + hướng dẫn tự do theo hồ sơ; chưa có danh sách rule có cấu trúc |
| Cú pháp gửi theo từng kênh | Một phần | Có làm sạch/tách tin, chưa theo kênh |
| Nhiều Agent, vai trò, phạm vi, quyền | Một phần | Hồ sơ agent theo kênh (tên, hướng dẫn, ngưỡng, trần chi phí); chưa có quyền công cụ / phạm vi tri thức / chế độ theo agent |
| Kiểm soát trước hành động quan trọng | Một phần | Đơn ≥ 1.000.000 đ chờ duyệt; chế độ Gợi ý giữ bản nháp |
| **Trách nhiệm giải trình từng hành động AI** | Một phần | Lưu độ tin cậy, nguồn (tên tài liệu), model, chi phí; **chưa lưu** agent nào, lưới nào bật, công cụ đã gọi + kết quả, đoạn tri thức gắn với từng tin |
| Tin tự động, nhãn, trạng thái tin | Có-tốt / Một phần | Quy tắc tự động + mẫu trả lời; nhãn là chữ tự do (chưa có danh mục) |
| Nhận diện khách, phân loại hội thoại | Một phần / Chưa có | Ghép danh tính bảo thủ; chưa có phân loại theo chủ đề |
| Quy tắc chuyển giao AI↔người | Một phần | Có đủ luật trong mã, chưa cấu hình được |
| Giờ hoạt động, thông báo | Một phần | Nằm trong `.env`, ba nguồn "giờ" khác nhau |
| Tri thức trong cấu hình agent, theo quyền | Một phần | Có Draft/Publish + phiên bản; phạm vi theo kênh, chưa theo agent |
| Gợi ý & xác minh, ngưỡng tin cậy, các chế độ | Có-cần sửa | Ngưỡng + 2 chế độ có; độ tin cậy = điểm tra cứu, chưa kiểm câu trả lời có khớp căn cứ |

### Phần 3 — SLA
| Yêu cầu | Trạng thái | Ghi chú |
|---|---|---|
| Phản hồi đầu, thời gian xử lý, theo ưu tiên | Có-cần sửa | Có chính sách, nhưng **không đổi được ưu tiên hội thoại** → chính sách khác "normal" không bao giờ dùng |
| Lịch làm việc | Một phần | Một khung giờ mỗi ngày, chưa có thứ/ngày nghỉ |
| Chuyển cấp khi quá hạn | Chưa có | Chỉ ghi sự kiện |
| Cảnh báo | Một phần | Cảnh báo sớm 50% phản hồi đầu; không cảnh báo hạn xử lý; không báo quản lý |
| Dashboard SLA | Chưa có | Chỉ có số trễ theo nhân viên (đang đếm sai — L10) |

### Phần 4 + 11 — Kênh / Plugin, Webhook & API
| Yêu cầu | Trạng thái | Ghi chú |
|---|---|---|
| Connector độc lập theo hợp đồng chung, bật/tắt, kiểm kết nối, thử lại, dead-letter | Có-tốt | 6 kênh native: Zalo cá nhân, Zalo OA, Facebook, Instagram, WhatsApp, website |
| Thêm kênh không sửa lõi | Một phần | Tên kênh còn rải ở ~16 tệp |
| Telegram | Chưa có | ~10 tệp + 1 migration |
| Lịch sử webhook nhận | Một phần | Có sổ `webhook_deliveries`, chưa có màn xem |
| Lịch sử gửi, thử lại | Có-tốt | Màn chỉ hiện tin chết |
| Quản lý API key nhà cung cấp | Có-tốt | Chỉ hiện 4 ký tự cuối |
| API key cho bên ngoài gọi vào, phạm vi, giới hạn, nhật ký request | Một phần | MCP dùng một token tĩnh |

### Phần 6 + 7 + 9 — Giao diện chat, phân công, menu, phân tích
| Yêu cầu | Trạng thái | Ghi chú |
|---|---|---|
| Đúng tin của hội thoại, phân biệt khách/NV/AI, nguồn kênh | Có-tốt | |
| Tên nhân viên gửi, người đang phụ trách | Một phần | Có dữ liệu, giao diện chỉ ghi "Nhân viên" |
| Agent nào tham gia, lịch sử chuyển giao | Chưa có | Bảng `conversation_assignments` có, chưa có màn xem |
| Nhóm vs cá nhân | Chưa có (giao diện) | Xem L1–L3 |
| Tìm kiếm, lọc | Một phần | Thiếu lọc kênh / người phụ trách / SLA / ngày |
| Giao hội thoại cho người khác / cho nhóm / cho agent | Một phần | API có, giao diện chỉ tự nhận |
| Tự phân công theo rule / kỹ năng / tải / ca | Có-cần sửa | Có; nhưng **hội thoại AI chuyển người không bao giờ được tự giao** |
| Menu Video, Đăng bài | Đã gỡ 19.11.2026 | |
| Menu Phân tích | Một phần | Có "Số hiệu"; thiếu lọc kênh/nhân viên/agent, thiếu hiệu suất AI, tin gửi/nhận, SLA |
| Trùng lặp menu | Có | "Sức khoẻ" ở 3 nơi; cấu hình agent rải 4 màn |

### Phần 13 — Media
| Câu hỏi | Hiện trạng |
|---|---|
| Nhận thế nào | Zalo cá nhân: URL CDN; ảnh khách chỉ tải vào RAM để AI xem |
| Lưu ở đâu | **Không lưu** media khách gửi; ảnh nhân viên gửi lưu `data/uploads` |
| Dung lượng hiện tại | CSDL 22 MB; `data/uploads` 152 KB; `data/products` 14 MB |
| Trùng lặp / lỗi / dọn dẹp / thời hạn | Chưa có (chỉ có thời hạn lưu hội thoại 180 ngày) |
| Sao lưu | CSDL + tri thức; **chưa** sao lưu `data/uploads`, `data/products` |

---

## 3. Kế hoạch triển khai

**Đợt A — Sửa lỗi và bảo mật (không cần quyết định nghiệp vụ)**
1. L1–L3 nhóm/cá nhân: tên nhóm lấy từ Zalo, người gửi theo từng tin (migration), hội thoại nhóm không dùng hồ sơ khách riêng, backfill `thread_type`, huy hiệu Nhóm + tên người gửi trên giao diện.
2. L4–L6, L11 bảo mật quyền: "không cấp được quyền mình không có", nhật ký kiểm toán cần quyền riêng, verify token cần `kenh.sua`.
3. L7, L8: cờ "duyệt trước khi gửi" riêng của hội thoại; ghi người duyệt.
4. L10, L12, đường dẫn media tương đối, sao lưu `data/uploads` + `data/products`.

**Đợt B — Nâng cấp phần đã có**
5. Trách nhiệm giải trình AI: mỗi tin AI lưu agent, lưới bật, công cụ đã gọi + kết quả, đoạn tri thức; xem được ngay trong khung chat.
6. Giao diện chat: tên người gửi/duyệt/phụ trách, dòng thời gian chuyển giao, ngày giờ đầy đủ, lọc theo kênh/người/SLA/nhóm-cá nhân; giao hội thoại cho người khác/nhóm; tự giao hội thoại AI đã chuyển.
7. SLA: đổi ưu tiên hội thoại, cảnh báo hạn xử lý, chuyển cấp khi quá hạn, lịch làm việc theo thứ.
8. Menu Phân tích: hội thoại, khách, nhân viên, AI, tỉ lệ AI xử lý, tỉ lệ chuyển người, SLA, tin gửi/nhận; lọc thời gian/kênh/nhân viên/agent.
9. Gom menu: một mục "AI Agent" (hồ sơ agent, quy tắc, tri thức, kỹ năng, phòng thử, cấu hình chung); một mục "Sức khoẻ".

**Đợt C — Tính năng mới**
10. Bộ máy phê duyệt chung 3 cấp + uỷ quyền + quyền riêng từng người + vai trò Quản lý / Trưởng nhóm.
11. Agent nhiều vai trò: quyền công cụ, phạm vi tri thức, chế độ theo agent; cú pháp tin theo kênh.
12. Quản lý tích hợp: lịch sử webhook nhận/gửi, API key cho bên ngoài (phạm vi, giới hạn, nhật ký).
13. Connector Telegram; phân loại hội thoại theo chủ đề.
14. Lưu media khách gửi về máy chủ, chống trùng, thời hạn lưu cấu hình được, dọn tệp mồ côi.

---

## 4. Bảng chức năng và chi phí (Phần 14)

Giả định: công sức tính bằng ngày làm việc của một lập trình viên có trợ giúp AI;
đơn giá phát triển **không** được nêu vì phụ thuộc người làm — nhân số ngày với
đơn giá của anh/chị. Chi phí AI dựa trên số đo thật: lượt đo tuân thủ 19.11.2026
tốn **0,00246 USD/câu** (~62 đ) với Gemini.

| STT | Module | Chức năng | Hiện trạng | Ưu tiên | Công sức | Chi phí vận hành |
|---|---|---|---|---|---|---|
| 1 | Kênh | Sửa nhóm/cá nhân Zalo (L1–L3) | Có-cần sửa | P0 | 2–3 ngày | 0 |
| 2 | Bảo mật | Chặn leo thang quyền, khoá nhật ký, verify token (L4–L6) | Có-cần sửa | P0 | 1 ngày | 0 |
| 3 | Hội thoại | Cờ duyệt riêng hội thoại, ghi người duyệt (L7–L8) | Có-cần sửa | P0 | 1 ngày | 0 |
| 4 | AI | Trách nhiệm giải trình từng tin AI | Nâng cấp | P1 | 2–3 ngày | Lưu trữ tăng nhẹ (vài MB/tháng) |
| 5 | Hội thoại | Tên người gửi/duyệt/phụ trách, dòng thời gian, bộ lọc, giao cho người khác | Nâng cấp | P1 | 3–4 ngày | 0 |
| 6 | SLA | Ưu tiên, cảnh báo xử lý, chuyển cấp, lịch theo thứ | Nâng cấp | P1 | 3 ngày | 0 |
| 7 | Phân tích | Menu Phân tích có bộ lọc | Nâng cấp | P1 | 3–4 ngày | 0 |
| 8 | Menu | Gom "AI Agent", "Sức khoẻ" | Nâng cấp | P2 | 1–2 ngày | 0 |
| 9 | Quyền | Phê duyệt 3 cấp + uỷ quyền + quyền cá nhân | Mới | P1 | 5–7 ngày | 0 |
| 10 | AI | Agent nhiều vai trò (công cụ, tri thức, chế độ) | Mới | P2 | 4–5 ngày | Chi phí model theo lượt (~62 đ/lượt) |
| 11 | Tích hợp | Lịch sử webhook, API key bên ngoài, giới hạn, nhật ký | Mới | P2 | 4–5 ngày | 0 |
| 12 | Kênh | Telegram | Mới | P3 | 2–3 ngày | 0 (API miễn phí) |
| 13 | AI | Phân loại hội thoại theo chủ đề | Mới | P3 | 2–3 ngày | Thêm ~1 lượt model rẻ/tin nếu dùng model |
| 14 | Media | Lưu media khách, chống trùng, thời hạn, dọn dẹp | Mới | P2 | 3 ngày | Lưu trữ: phụ thuộc lượng ảnh (ước 1–5 GB/năm cho shop nhỏ — giả định) |
| 15 | Hạ tầng | VPS + tên miền cố định | Cần làm | P0 vận hành | 1 ngày | VPS ~150–250 nghìn đ/tháng; tên miền ~250–500 nghìn đ/năm (giá tham khảo thị trường VN) |
| 16 | Kênh | Ứng dụng Meta Live (App Review) | Cần làm | P0 vận hành | 1–3 tuần chờ Meta | 0 |
| 17 | Kênh | Zalo OA gửi tin chủ động (ZNS) | Ngoài phạm vi hiện tại | — | — | Zalo tính phí theo tin ZNS (cần báo giá Zalo) |

Tổng công sức Đợt A ≈ 5–6 ngày; Đợt B ≈ 12–16 ngày; Đợt C ≈ 20–26 ngày.
