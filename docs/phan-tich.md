# Phân tích và SLA

Màn **Phân tích** (thanh bên → Phân tích — trước đây là "Số hiệu"; id view vẫn
là `sohieu`) và các nâng cấp SLA đi kèm, rà soát 20.11.2026 theo phiếu việc
của chủ dự án. Định nghĩa đầy đủ nằm trong docstring của
`agent/api/phan_tich.py` — tài liệu này tóm tắt và giải thích lựa chọn.

## Nguyên tắc: đếm SỰ KIỆN, không đếm ảnh chụp trạng thái

Số "Agent tự xử lý" cũ chia hội thoại có `status = 'auto'` cho tổng. Duyệt
một bản nháp AI lật `assist` → `auto`, nên hội thoại người phải đọc và bấm
duyệt từng câu cũng thành "AI tự xử lý". Mọi số ở màn Phân tích đếm một sự
kiện có thời điểm (tin nhắn, `events`, `sla_events`) trong khoảng ngày, nên
hỏi lại tuần trước vẫn ra số của tuần trước. Hai ô là ảnh chụp "bây giờ" —
**Đang mở** và **Đang quá hạn** — và nhãn nói vậy.

Ô **AI tự lo (không người can thiệp)** ở Ca trực (`/api/overview`) dùng cùng
định nghĩa, cửa sổ 24 giờ. Bảng "Khách đến từ đâu" (đếm theo `status`) đã gỡ
khỏi màn; endpoint `/api/analytics/khach` vẫn còn.

## Bộ lọc

Khoảng ngày theo giờ Việt Nam (0h–24h), nền tảng, tài khoản kênh, nhân viên,
hồ sơ AI. Ai không có `hoi_thoai.xem_tat_ca` chỉ thấy số của kênh mình là
thành viên — cùng luật với `/api/overview`. Quyền xem màn: `bao_cao.doc`.

## Các phần của màn

| Phần | Số chính |
|---|---|
| Hiệu quả chăm sóc khách hàng | hội thoại có hoạt động / mới, **tỷ lệ xử lý** (được giải quyết / có hoạt động), phản hồi đầu và thời gian giải quyết (trung vị), mở lại, khách mới / quay lại |
| Hiệu quả AI Agent | hội thoại AI xử lý, **tỷ lệ chuyển giao nhân viên**, **hiệu quả tự động hoá** (AI tự giải quyết / có hoạt động), bảng theo hồ sơ AI |
| Hiệu suất nhân viên | cùng câu với báo cáo cũ, thu hẹp theo bộ lọc; nút Xuất Excel (báo cáo gốc, mọi kênh) |
| Chỉ số SLA | tỷ lệ đáp ứng phản hồi đầu / giải quyết, số vi phạm, đang quá hạn, bảng thời gian, xu hướng theo ngày |
| Chi phí AI | chi phí trong khoảng (theo hồ sơ, theo ngày) và bảng chi phí 7 ngày cũ |
| Tin nhắn | gửi / nhận / lỗi / chưa gửi theo nền tảng và vai |

## Định nghĩa chính

| Số | Đếm gì |
|---|---|
| Lượt giải quyết | sự kiện `conversation.resolved` (một hội thoại giải quyết hai lần = 2) |
| Mở lại | sự kiện `conversation.reopened` — chỉ có từ 20.11.2026 |
| Có người can thiệp | chuyển người, tiếp quản, nhân viên gửi tin, **hoặc duyệt nháp AI** |
| AI tự giải quyết | hội thoại có tin AI, được giải quyết, không người can thiệp |
| Tỉ lệ thành công AI | tự giải quyết / (tự giải quyết + cần người) — chỉ hội thoại đã có kết cục; số chưa kết cục trả kèm |
| Có / không căn cứ | trên tin AI do model sinh (câu cố định không qua tra cứu) |
| Đáp ứng SLA | đạt / (đạt + trễ), chỉ mục tiêu CÓ hạn |
| Phản hồi đầu | bắt đầu chu kỳ SLA → tin đầu tiên gửi xong; **AI và nhân viên tách riêng** |
| Phản hồi sau chuyển giao | sự kiện chuyển người (lần đầu trong khoảng) → tin nhân viên đầu tiên sau đó; kèm số "chưa ai nhắn" |
| Thời gian giải quyết | tạo hội thoại (hoặc lần mở lại gần nhất) → giải quyết |

Màn **không** hiện "độ tin cậy" AI: model tự chấm con số ấy, hiện thành phần
trăm là mời người đọc tin nó như xác suất đúng. Báo tỉ lệ có / không căn cứ.

Ba thước đo thời gian đo theo **cùng công tắc với hạn SLA**
(`SLA_THEO_GIO_LAM_VIEC`): bật thì chỉ đếm giờ làm việc, tắt (mặc định) thì
24/7. Một công tắc chung — chọn riêng 24/7 hay giờ làm việc cho TỪNG thước đo
là đổi cả cách đặt hạn ở ba chỗ, chưa làm.

Hồ sơ AI của mỗi tin được **chụp lúc ghi tin** (trigger migration 0054), không
tra hồ sơ đang gán cho kênh. Tin trước 0054 hiện là "Không rõ". Sự kiện phản
hồi đầu giờ ghi **ai** trả lời (`vai`, `gui_boi`, `ho_so`) và **lúc nào**
(`phan_hoi_luc`).

## SLA

**Đổi ưu tiên** (`PUT /api/conversations/{id}/uu-tien`, quyền
`hoi_thoai.nhan`, bắt buộc lý do, ghi `events` + `inbox_events`): đổi được hai
chiều, nhưng hạn của chu kỳ đang chạy **chỉ được rút ngắn**.

- Nâng: hạn = min(hạn cũ, *bây giờ* + số phút của chính sách mới). Tính từ
  bây giờ để người nâng ưu tiên không bị tính trễ ngay tức khắc.
- Hạ: hạn giữ nguyên; mức mới áp dụng từ chu kỳ sau.
- Trigger `prevent_sla_deadline_reset` (0054) giữ luật ấy ở CSDL: trong cùng
  chu kỳ, hạn chỉ đổi được khi hạn mới sớm hơn, hạn cũ còn ở tương lai và hạn
  mới không ở quá khứ.

**Cảnh báo sớm**: một ngưỡng `SLA_NGUONG_CANH_BAO` (Cấu hình → Cài đặt API,
mặc định **80%** thời gian cho phép, 10–95) cho cả phản hồi đầu lẫn giải quyết
(`first_response_warning`, `resolution_warning`).

**Khi trễ**: KHÔNG sinh công việc — cảnh báo SLA đi qua chuông thông báo trong
ứng dụng (làm sau). Mỗi sự kiện `sla.*` trong `inbox_events` mang
`conversation_id`, `loai`, `chu_ky`, `nguoi_phu_trach`, `uu_tien`, `han`.
`SLA_KHI_TRE = bao_va_nang_uu_tien` thêm nâng ưu tiên một bậc (không rút hạn,
ghi nhật ký với actor `sla`).

Màn chi tiết hội thoại không thêm thông tin SLA nào; chỉ có nút **Đổi** cạnh
mức ưu tiên. Dashboard nghe mọi sự kiện `sla.*` và
`conversation.priority_changed` qua SSE. Form chính sách SLA có ô giờ mở/đóng
riêng (`business_hours`), kiểm hợp lệ lúc lưu.
