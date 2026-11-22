# Kế hoạch thực hiện "Check list công việc" — 21.11.2026

Nguồn: bảng Google Sheets "Check list công việc" (21 mục, 4 mức). Bảng này là
**phạm vi ràng buộc**; chỗ nào khác bản yêu cầu nâng cấp trước thì theo bảng.

## Khác biệt chính so với bản yêu cầu trước
- Phân quyền chỉ **RBAC qua vai trò** (mục 12, 13): không cấp quyền riêng
  từng người, không ABAC, không phạm vi Cá nhân/Nhóm/Tất cả.
- "Ba cấp độ" (Không / Có phê duyệt / Tự động) áp dụng cho **hành động của
  AI Agent** (mục 17), không phải cho nhân viên.
- AI chuyển giao **không tự tạo công việc** (mục 14.2) — báo qua chuông
  thông báo (mục 19).
- **Không hiển thị độ tin cậy dạng %** (mục 16.8) — chỉ "có / thiếu căn cứ".
- Một cấu hình AI Agent **chung cho mọi kênh** (mục 5.4).
- Tạm hoãn **CSAT**, ẩn cấu hình **VietQR** khỏi giao diện (mục 4.8, 8.10–11) —
  giữ mã nguồn.
- Nhóm Zalo **không** là khách hàng trong Customer 360 (mục 9.7).

## Trạng thái từng mục

| # | Mục | Đã có trước | Việc làm | Đợt |
|---|---|---|---|---|
| 1 | Nút "← Quay lại" ở màn 2 bước | — | Đổi chữ nút | 2 |
| 2 | Dòng "Thời gian · Người gửi · Trạng thái" dưới mỗi tin | Một phần | Chuẩn hoá dòng; thông tin kỹ thuật vào chi tiết | 1 (đang làm) |
| 3 | Nhãn động: khách hàng + hội thoại, danh mục chung | Nhãn chữ tự do | Danh mục nhãn (màu, mô tả, ngừng dùng), gắn/gỡ đúng màn | 2 |
| 4 | Tái cấu trúc menu: 6 menu chính + "Cài đặt & Quản trị" (4 mục con) + chuông | — | Dựng lại sidebar, gộp Ca trực vào Công việc, đổi Số hiệu → Phân tích | 2 |
| 5 | Cấu hình AI Agent 5 tab; chế độ Gợi ý/Tự động + bật/tắt AI | Rải rác | Gom Tri thức, Kỹ năng, Phòng thử; chuyển công tắc khỏi Header | 2 |
| 6 | Thanh thông tin hội thoại gọn; ghi chú nội bộ ở ô soạn tin | — | Tên khách · Nhãn · C360 · Hành động · Chi tiết | 3 |
| 7 | Mẫu trả lời + Quy tắc tự động: ưu tiên, xung đột, chống trùng với AI | Có cơ bản | Thứ tự ưu tiên, xử lý xung đột, phân biệt nhãn | 3 |
| 8 | Kết nối & Tích hợp: kênh, ERPNext, GHN, GHTK; nhà cung cấp AI; thông báo minh bạch | Một phần | Nhập/sửa/kiểm tra trên dashboard, che bí mật, lịch sử thay đổi | 2 |
| 9 | Nhóm vs cá nhân | **Đã làm** (Đợt A) | Thêm: tin cuối kèm tên người gửi ở danh sách; ẩn nhóm khỏi Customer 360 | 3 |
| 10 | Media | — (bảng ghi "cần làm rõ") | Theo quyết định đã chốt: tải về máy chủ, giữ 180 ngày, chống trùng | 4 |
| 12 | RBAC theo chức năng | Có (41 quyền) | Sắp danh mục theo nhóm chức năng của bảng; lịch sử đổi quyền có trước/sau | 2 |
| 13 | Vai trò động, quản lý nhân viên | Có phần lớn | 2 tab; ngừng dùng vai trò; khoá có cảnh báo việc dở + chuyển giao; không xoá | 2 |
| 14 | Phân công công việc | Có | Trạng thái chuẩn, tự giao xoay vòng theo ca, lịch sử, liên kết | 3 |
| 15 | SLA | Có một phần | Phản hồi sau chuyển giao, ngưỡng cảnh báo cấu hình được, báo qua chuông | 1 (đang làm) + 3 |
| 16 | Gợi ý có căn cứ + "Xem căn cứ" | Một phần | Trạng thái đủ/thiếu/không/mâu thuẫn căn cứ, không % | 1 (đang làm) + 4 |
| 17 | Ba cấp uỷ quyền hành động AI + thẻ phê duyệt | Một phần (đơn ≥ ngưỡng) | Chính sách theo hành động, thẻ phê duyệt trong hội thoại, Backend kiểm lại | 4 |
| 18 | Trách nhiệm giải trình AI | Một phần | Dấu vết từng lượt (đang làm), tra cứu nhật ký ở Hệ thống & Nhật ký | 1 + 4 |
| 19 | Thông báo nội bộ (chuông) | — | Bảng thông báo, API, chuông Header, các nguồn sự kiện | 1 (đang làm) |
| 20 | Kênh theo kiến trúc plugin | Có hợp đồng adapter | Danh sách plugin + khả năng mỗi kênh trong Kết nối & Tích hợp | 4 |
| 21 | Bảng yêu cầu chức năng / phi chức năng | — | Sinh từ mã + kết quả kiểm thử | 4 |

## Thứ tự đợt
- **Đợt 1 (đang chạy):** minh bạch hội thoại (2, 16, 18); Phân tích + SLA (4.3, 15); thông báo nội bộ (19, 14.2).
- **Đợt 2:** khung menu mới (1, 4, 5); nhãn động (3); Kết nối & Tích hợp + cấu hình AI cơ bản (8, 5); nhân sự & phân quyền (12, 13).
- **Đợt 3:** thanh thông tin hội thoại + ô soạn tin (6, 9 phần còn lại); quy tắc tự động (7); công việc (14); cấu hình SLA (15).
- **Đợt 4:** uỷ quyền AI 3 cấp + thẻ phê duyệt (17); xem căn cứ đầy đủ (16); tra cứu nhật ký (18); media (10); plugin (20); bảng yêu cầu (21).

Mỗi đợt: chạy toàn bộ test với Postgres thật, nghiệm thu, đẩy GitHub, sao lưu, áp vào máy.
