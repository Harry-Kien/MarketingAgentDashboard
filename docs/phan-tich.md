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
| Mục tiêu sau chuyển giao | mỗi LƯỢT chuyển giao một hạn (`sla_chuyen_giao`, 0062): đạt / trễ / cảnh báo / đang chờ / không đặt hạn, thời gian lúc chuyển → tin nhân viên |
| Giải quyết — AI / nhân viên | lượt giải quyết (và đạt / trễ hạn giải quyết) quy cho nhân viên nếu trong lượt có người can thiệp, không thì cho AI |
| Thời gian giải quyết | tạo hội thoại (hoặc lần mở lại gần nhất) → giải quyết |

Màn **không** hiện "độ tin cậy" AI: model tự chấm con số ấy, hiện thành phần
trăm là mời người đọc tin nó như xác suất đúng. Báo tỉ lệ có / không căn cứ.

Mỗi thước đo thời gian đo theo **chế độ của mục tiêu SLA tương ứng**
(giờ làm việc của lịch chung, hoặc 24/7 — xem mục *Mục tiêu SLA và lịch làm
việc* bên dưới), cùng lịch với hạn của chính mục tiêu ấy. API trả
`che_do_muc_tieu` để màn hình nói rõ con số nào đo theo cách nào.

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

**Cảnh báo sớm**: ngưỡng chung `SLA_NGUONG_CANH_BAO` (mặc định **80%** thời
gian cho phép, 10–95), mỗi mục tiêu đặt được ngưỡng riêng — xem dưới
(`first_response_warning`, `resolution_warning`, `handover_response_warning`).

**Khi trễ**: KHÔNG sinh công việc — cảnh báo SLA đi qua chuông thông báo trong
ứng dụng (làm sau). Mỗi sự kiện `sla.*` trong `inbox_events` mang
`conversation_id`, `loai`, `chu_ky`, `nguoi_phu_trach`, `uu_tien`, `han`.
`SLA_KHI_TRE = bao_va_nang_uu_tien` thêm nâng ưu tiên một bậc (không rút hạn,
ghi nhật ký với actor `sla`).

Màn chi tiết hội thoại không thêm thông tin SLA nào; chỉ có nút **Đổi** cạnh
mức ưu tiên. Dashboard nghe mọi sự kiện `sla.*` và
`conversation.priority_changed` qua SSE.

## Mục tiêu SLA và lịch làm việc (mục 15 — 22.11.2026, migration 0062)

Cấu hình chung → **SLA & Giờ làm việc** (`dashboard/src/26-sla.js`, API
`/api/sla/*`, quyền `dinh_tuyen.doc` / `dinh_tuyen.sua`).

**Ba mục tiêu**, số phút theo kênh × mức ưu tiên (`sla_policies`):

| Mục tiêu | Từ | Tới (phản hồi THẬT) |
|---|---|---|
| Phản hồi đầu | bắt đầu chu kỳ SLA | tin AI hoặc nhân viên đầu tiên đã gửi tới kênh |
| Phản hồi sau chuyển giao (`handover_response_minutes`) | sự kiện `conversation.escalated` | tin NHÂN VIÊN đầu tiên đã gửi |
| Giải quyết | bắt đầu lượt phục vụ | `conversation.resolved` |

**Xác nhận tự động không phải phản hồi** (`agent/omnichannel/phan_hoi_that.py`):
tin vai `system` — thông báo minh bạch AI, câu báo chuyển người và câu báo
ngoài giờ, tin mẫu của quy tắc tự động, câu hỏi CSAT, báo mã vận đơn — không
bao giờ đạt hạn phản hồi đầu và không chốt lượt chuyển giao. Luật đi theo VAI
của tin (đặt một lần lúc xếp hàng), không theo nội dung.

**Mỗi mục tiêu một chế độ và một ngưỡng** (`sla_muc_tieu`): đồng hồ "giờ làm
việc" hoặc "24/7"; ngưỡng cảnh báo riêng, trống = ngưỡng chung.

**Lịch làm việc chung** (`lich_lam_viec`, `agent/core/lich_lam_viec.py`): giờ
mở/đóng từng thứ, ngày nghỉ trong tuần, ngày lễ. MỘT nguồn cho: hạn SLA của
mục tiêu chọn giờ làm việc (SQL `sla_han_lich`), cảnh báo sớm và thời gian ở
màn Phân tích (`lich_lam_viec.tieu_thu` — test canh hai phép tính khớp nhau),
câu báo khách khi chuyển người ngoài giờ (giờ mở của lần mở cửa kế tiếp),
điều kiện "ngoài giờ" của quy tắc tự động, cảnh báo sức khoẻ.

**Thứ tự ưu tiên**

| Thứ | Nguồn 1 (dashboard) | Không có thì |
|---|---|---|
| Giờ làm việc | bảng `lich_lam_viec` | `.env` `GIO_LAM_VIEC_BAT/_BAT_DAU/_KET_THUC`, mọi ngày như nhau, không ngày lễ |
| Giờ riêng của chính sách (`business_hours`) | **không còn tác dụng** khi đã có lịch chung | có tác dụng như trước khi lịch lui về `.env` |
| Chế độ của mục tiêu | `sla_muc_tieu.che_do` | `.env` `SLA_THEO_GIO_LAM_VIEC` (cho cả ba) |
| Ngưỡng cảnh báo | `sla_muc_tieu.nguong_canh_bao` | `SLA_NGUONG_CANH_BAO` (dashboard → `.env`) → 80 |

Màn chia bốn khu (UX-15, 26.11.2026): **Mục tiêu & Thời hạn**, **Giờ làm
việc**, **Cảnh báo** (ô khoá kỹ thuật `SLA_*` dời vào phần "Nâng cao"),
**Thứ tự áp dụng & Thử tính**. Máy tính hạn gọi
`GET /api/sla/xem-truoc-han?account_id=&uu_tien=&bat_dau=` (quyền
`dinh_tuyen.doc`, chỉ đọc): máy chủ chạy CHÍNH biểu thức đặt hạn thật
(`sla_gio.bieu_thuc_han` với mốc giả định thay `now()`) và CHÍNH luật chọn
chính sách của đường đổi ưu tiên — test canh cả hai
(`tests/test_sla_xem_truoc_han.py`). Màn Phân tích tách **Tổng quan SLA**
(ô số + biểu đồ tỷ lệ đúng hạn theo ngày) khỏi bảng chi tiết thu gọn.

Chưa ai lưu gì trên dashboard thì mọi thứ chạy y như trước bản này. Lịch và
mục tiêu nạp vào bộ nhớ lúc khởi động, sau mỗi lần lưu, mỗi vòng canh SLA
(15 giây) và tối đa 30 giây một lần ở đường nhận tin. Hội thoại đang chạy
giữ hạn đã đặt; lịch mới áp cho hạn đặt sau khi lưu.

**Hạn phản hồi sau chuyển giao**: mỗi lượt chuyển giao một dòng
`sla_chuyen_giao` (không dùng `sla_events`, vì khoá (hội thoại, chu kỳ, loại)
của bảng ấy nuốt vi phạm của lần chuyển giao thứ hai). Vòng canh SLA mở lượt
từ sự kiện `conversation.escalated` (mọi đường chuyển giao đều ghi), outbox
chốt lượt khi tin nhân viên gửi xong, hội thoại giải quyết / trả AI trước khi
ai nhắn thì lượt thành `huy`. Chuyển giao trước khi 0062 chạy không mở lượt.
Cảnh báo và vi phạm đi qua chuông (`sla_sap_tre` / `sla_tre`) tới người đang
phụ trách — chưa giao thì thành viên kênh có `hoi_thoai.nhan` — cộng người
quản lý; phát `sla.handover_response_warning` / `_breached` qua SSE. Vi phạm
và cảnh báo đã ghi không xoá được (trigger 0062), kể cả khi thông báo đã đọc.

SLA KHÔNG hiện thường trực trong khung hội thoại — cảnh báo đi qua chuông,
số liệu ở màn Phân tích.
