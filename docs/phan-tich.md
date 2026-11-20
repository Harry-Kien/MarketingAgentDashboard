# Phân tích và SLA

Màn **Phân tích** (thanh bên → Phân tích) và các nâng cấp SLA đi kèm, rà soát
20.11.2026. Định nghĩa đầy đủ nằm trong docstring của
`agent/api/phan_tich.py` — tài liệu này tóm tắt và giải thích lựa chọn.

## Nguyên tắc: đếm SỰ KIỆN, không đếm ảnh chụp trạng thái

Số "Agent tự xử lý" cũ chia hội thoại có `status = 'auto'` cho tổng. Duyệt
một bản nháp AI lật `assist` → `auto`, nên hội thoại người phải đọc và bấm
duyệt từng câu cũng thành "AI tự xử lý". Mọi số ở màn Phân tích đếm một sự
kiện có thời điểm (tin nhắn, `events`, `sla_events`) trong khoảng ngày, nên
hỏi lại tuần trước vẫn ra số của tuần trước. Hai ô là ảnh chụp "bây giờ" —
**Đang mở** và **Đang quá hạn** — và nhãn nói vậy.

Ô **AI tự lo (không người can thiệp)** ở Ca trực (`/api/overview`) dùng
cùng định nghĩa, cửa sổ 24 giờ.

## Bộ lọc

Khoảng ngày theo giờ Việt Nam (0h–24h), nền tảng, tài khoản kênh, nhân viên,
hồ sơ AI. Ai không có `hoi_thoai.xem_tat_ca` chỉ thấy số của kênh mình là
thành viên — cùng luật với `/api/overview`. Quyền xem màn: `bao_cao.doc`.

## Định nghĩa chính

| Số | Đếm gì |
|---|---|
| Hội thoại mới | hội thoại tạo trong khoảng |
| Lượt giải quyết | sự kiện `conversation.resolved` (một hội thoại giải quyết hai lần = 2) |
| Mở lại | sự kiện `conversation.reopened` — chỉ có từ 20.11.2026 |
| Khách mới / quay lại | khách có nhắn trong khoảng; mới = `first_seen` trong khoảng |
| Có người can thiệp | chuyển người, tiếp quản, nhân viên gửi tin, **hoặc duyệt nháp AI** |
| AI tự giải quyết | hội thoại có tin AI, được giải quyết, không người can thiệp |
| Tỉ lệ thành công AI | tự giải quyết / (tự giải quyết + cần người) — chỉ hội thoại đã có kết cục; số chưa kết cục trả kèm |
| Tỉ lệ cần người | cần người / hội thoại có tin AI |
| Tin cậy TB, có căn cứ | chỉ tin AI do model sinh (câu cố định không có độ tin cậy) |
| SLA đúng hạn | đạt / (đạt + trễ), chỉ mục tiêu CÓ hạn |
| Phản hồi đầu | từ lúc bắt đầu chu kỳ SLA tới tin đầu tiên gửi xong; **AI và nhân viên tách riêng**, trung bình kèm trung vị |

Hồ sơ AI của mỗi tin được **chụp lúc ghi tin** (trigger migration 0054), không
tra hồ sơ đang gán cho kênh — đổi hồ sơ hôm nay không quy công tháng trước
cho hồ sơ mới. Tin trước 0054 hiện là "Không rõ".

Mọi tin AI vẫn tính là đã phản hồi đầu (quy ước cũ của `outbox.py`), nhưng
sự kiện phản hồi đầu giờ ghi **ai** trả lời (`vai`, `gui_boi`, `ho_so`) và
**lúc nào** (`phan_hoi_luc`), nên lời chào tự động hai giây không che ca chờ
bốn mươi phút của nhân viên.

## SLA

**Đổi ưu tiên** (`PUT /api/conversations/{id}/uu-tien`, quyền
`hoi_thoai.nhan`, bắt buộc lý do, ghi `events` +
`inbox_events`): đổi được hai chiều, nhưng hạn của chu kỳ đang chạy **chỉ được
rút ngắn**.

- Nâng: hạn = min(hạn cũ, *bây giờ* + số phút của chính sách mới). Tính từ
  bây giờ để người nâng ưu tiên không bị tính trễ ngay tức khắc.
- Hạ: hạn giữ nguyên; mức mới áp dụng từ chu kỳ sau.
- Trigger `prevent_sla_deadline_reset` (0054) giữ luật ấy ở CSDL: trong cùng
  chu kỳ, hạn chỉ đổi được khi hạn mới sớm hơn, hạn cũ còn ở tương lai và hạn
  mới không ở quá khứ.

**Cảnh báo sớm hạn giải quyết** (`resolution_warning`): khi đã tiêu một nửa
khoảng từ lúc bắt đầu chu kỳ tới hạn, theo đúng công tắc 24/7
(`SLA_THEO_GIO_LAM_VIEC`). Giờ riêng của chính sách chưa được tính vào ngưỡng
cảnh báo (cùng giới hạn với cảnh báo phản hồi đầu).

**Leo thang khi trễ** (`agent/omnichannel/sla.py`): mỗi vi phạm còn treo sinh
**một** việc gấp (khoá chống trùng `sla:<hội thoại>:<chu kỳ>:<loại>`) và một
tin báo nhân viên (không kèm tên khách). Việc ấy không chặn nút "Đã giải
quyết" và tự đóng khi hội thoại được giải quyết. Cấu hình `SLA_KHI_TRE`
(Cấu hình → Cài đặt API): `bao` (mặc định) hoặc `bao_va_nang_uu_tien` — nâng
ưu tiên một bậc nhưng **không** rút hạn.

Dashboard nghe `sla.resolution_warning`, `sla.resolution_breached` và
`conversation.priority_changed` qua SSE. Form chính sách SLA có ô giờ mở/đóng
riêng (`business_hours`), kiểm hợp lệ lúc lưu.
