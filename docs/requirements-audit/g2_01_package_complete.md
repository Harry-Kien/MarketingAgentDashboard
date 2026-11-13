# Gói Hồ Sơ Hoàn Chỉnh Nhóm G2-01 (Reset SLA khi Khách Mở Lại Hội Thoại)

> Tài liệu hợp nhất toàn bộ quy trình từ căn chỉnh BA, đề xuất thay đổi, biên bản bàn giao và báo cáo triển khai code cho nhóm yêu cầu G2-01.

---

## Phần 1: BA Alignment

# BÁO CÁO ĐỐI CHIẾU NGHIỆP VỤ: REOPEN CONVERSATION & SLA LIFECYCLE
## TÀI LIỆU ĐỐI CHIẾU GIỮA BẢN THẢO BA VÀ THỰC TẾ HỆ THỐNG (GAP-07C / AC-11.3)

- **Mã nhiệm vụ:** `TASK G2-01-BA`
- **Yêu cầu liên quan:** FR-11 (AC-11.3), FR-01 (AC-01.3), FR-24 (AC-24.1, AC-24.5, AC-24.6, AC-24.7), QR-06, DFR-03
- **Vấn đề kiểm toán:** `GAP-07C` (Trigger PostgreSQL ngăn reset SLA khi Reopen)
- **Tài liệu tham chiếu:** `Phân tích nghiệp vụ khoá luận (6).pdf` (Bản thảo BA gốc), `requirements_source_register.csv`, `verify_01_reopen_sla_report.md`
- **Vai trò:** Business Analyst (Chuyên viên Phân tích Nghiệp vụ)
- **Trạng thái:** Bản đối chiếu phân tích nghiệp vụ chính thức (Chưa thay đổi Baseline đã phê duyệt)

---

## 1. TỔNG QUAN BỐI CẢNH & PHẠM VI ĐỐI CHIẾU

Trong quá trình kiểm toán mã nguồn và CSDL tại nhiệm vụ `TASK-VERIFY-01` ([`verify_01_reopen_sla_report.md`](file:///Users/huynhlehoaibao/Documents/AIAgent_mar/docs/requirements-audit/verify_01_reopen_sla_report.md)), nhóm kỹ thuật đã xác nhận một lỗi nghiêm trọng (**`CONFIRMED BUG`**):
- Khi một hội thoại đã được giải quyết hợp lệ (`state = 'resolved'`) nhận được tin nhắn mới từ khách hàng, hệ thống thực hiện mở lại hội thoại (Reopen).
- Về mặt nghiệp vụ, đây là sự khởi đầu của một **chu kỳ phục vụ mới (New Service Session)**, đòi hỏi hệ thống phải cấp một hạn thời gian phản hồi mới (`first_response_due_at`) tương ứng với chính sách SLA.
- Tuy nhiên, một cơ chế kỹ thuật ở tầng CSDL (Trigger `prevent_sla_deadline_reset` trong migration `0005_routing_sla.sql`) đã can thiệp thô bạo và ghi đè hạn SLA mới bằng mốc thời gian quá khứ của phiên tương tác trước đó.
- Hậu quả: Ngay tại giây thứ 0 khi khách gửi tin nhắn mở lại, tiến trình giám sát `SlaMonitor` quét thấy hạn phản hồi nằm trong quá khứ nên lập tức bắn sự kiện vi phạm **`first_response_breached`** oan sai, làm sai lệch chỉ số KPI của nhân viên và báo cáo vận hành.

Tài liệu này thực hiện đối chiếu toàn diện 5 câu hỏi nghiệp vụ cốt lõi từ tài liệu BA gốc (`Phân tích nghiệp vụ khoá luận (6).pdf`), phân định rõ ràng giữa **Yêu cầu nghiệp vụ gốc (Original Business Intent)** và **Ràng buộc kỹ thuật phòng chống gian lận (Anti-Cheating Technical Constraint)**.

---

## 2. ĐỐI CHIẾU 5 NGUYÊN TẮC NGHIỆP VỤ CỐT LÕI

### 2.1. Điều kiện Reopen hội thoại đã Resolved

#### Căn cứ tài liệu gốc:
- **`FR-01` & `AC-01.3` (Trang 135–136):**
  > *Given:* Conversation đã Resolved.  
  > *When:* Nhận tin mới hợp lệ.  
  > *Then:* Conversation được Reopen và Handling Mode được đánh giá lại.
- **`FR-11` & `AC-11.3` (Trang 142):**
  > *Given:* Conversation được Resolve hợp lệ.  
  > *When:* Khách gửi tin nhắn mới.  
  > *Then:* Hệ thống Reopen và kiểm tra điều kiện Auto Mode.
- **Use Case `UC-08` – Kết thúc phiên hỗ trợ thủ công (Trang 44–45):**
  > *Postconditions:* Conversation được Resolved hợp lệ; tin nhắn mới từ khách có thể Reopen và khôi phục Auto Mode sau kiểm tra an toàn.  
  > *Main Flow (Bước 6):* Khi khách hàng gửi tin nhắn mới, hệ thống Reopen Conversation.
- **Event–Response Table `EVT-01` (Trang 72):**
  > *System State:* Conversation Resolved.  
  > *Event:* Khách gửi yêu cầu.  
  > *Response:* Reopen Conversation và kiểm tra điều kiện chuyển Auto Mode hoặc tiếp tục Manual Mode.

#### Phân tích & Làm rõ Nghiệp vụ:
1. **Phân biệt Tin nhắn Đánh giá CSAT vs Tin nhắn Mở phiên mới:**
   - Khi hội thoại vừa được Resolve, hệ thống tự động gửi tin nhắn mời khách chấm điểm hài lòng CSAT (1–5 sao).
   - Nếu khách phản hồi đúng định dạng điểm số (1–5) trong vòng 24 giờ, tin nhắn đó được định danh là **Điểm đánh giá CSAT**, không phải câu hỏi mới. Hội thoại được ghi nhận điểm và duy trì trạng thái `resolved` (`agent/omnichannel/giai_quyet.py:118-138`).
   - Nếu khách gửi bất kỳ tin nhắn văn bản nào khác hoặc gửi sau khi đã hoàn tất CSAT, tin nhắn đó chính thức kích hoạt sự kiện **Reopen**.
2. **Tính chất phiên:**
   - Trạng thái hội thoại chuyển đổi: `state: 'resolved'` $\rightarrow$ `'open'`, `status: 'closed'` $\rightarrow$ `'auto'`.
   - Cờ kết thúc được giải phóng: `resolved_at := NULL`, `outcome := NULL`.

---

### 2.2. Cách Đánh giá lại Handling Mode khi Reopen

#### Căn cứ tài liệu gốc:
- **`FR-11` (Trang 142):**
  > "Sau khi Resolve, AI không tự kích hoạt Auto-Reply. Handling Mode chỉ được đánh giá lại khi khách gửi tin nhắn mới và đáp ứng điều kiện an toàn."
- **Use Case `UC-08` – Main Flow Bước 7 & Exception `EF-03` (Trang 45):**
  > *Bước 7:* Hệ thống kiểm tra điều kiện an toàn và chỉ chuyển Auto Mode nếu được phép.  
  > *EF-03:* Conversation Reopen nhưng chưa đạt điều kiện Auto Mode $\rightarrow$ tiếp tục xử lý theo Manual Mode.
- **`DFR-03` (Trang 128):**
  > "Kiểm tra Handling Mode và hiệu lực Batch trước khi gửi; chặn phản hồi AI lỗi thời hoặc trái quyền."

#### Phân tích & Làm rõ Nghiệp vụ:
Khi Reopen xảy ra, hệ thống **không mặc định trao quyền cho AI trả lời ngay**, mà phải thực thi chuỗi kiểm tra an toàn 3 nấc (Safety Gateways):
1. **Công tắc kênh & Tài khoản (`agent_bat`):** Kênh giao tiếp và tài khoản kênh (`channel_accounts`) có đang kích hoạt chế độ AI phục vụ tự động hay không?
2. **Quy tắc tự động & Phòng thủ an toàn (`tu_dong.py`, `phong_thu.py`):** Khách nhắn nội dung có chứa từ khóa nhạy cảm, khiếu nại gay gắt, dọa kiện, dọa bắt đền, hoặc yêu cầu gặp người hay không? Nếu có $\rightarrow$ ép chuyển ngay sang `Manual Mode` (`mode = 'human'`).
3. **Trạng thái phân công:** Phiên hỗ trợ trước đó đã kết thúc hoàn toàn, nhân viên cũ đã được giải phóng trách nhiệm (`conversation_assignments.ended_at` đã được ghi nhận lúc Resolve). Do đó, nếu chuyển `Manual Mode`, hội thoại được đưa vào hàng đợi chờ phân công mới, không bị giữ khóa bởi người cũ.

---

### 2.3. Quy tắc SLA của Chu kỳ Phục vụ Mới (New Service Session SLA)

#### Căn cứ tài liệu gốc:
- **`FR-24` / `AC-24.5` & `AC-24.6` (Trang 150):**
  > Xác định thời hạn First Response SLA tích lũy trong giờ làm việc (High: 5m Warning / 10m Breach; Normal: 15m Warning / 30m Breach).
- **`FR-24` / `AC-24.7` (Trang 150) & Quy tắc áp dụng SLA (Trang 74):**
  > "Giờ tính SLA là 08:00–21:00... Thời gian ngoài giờ không được tính vào đồng hồ SLA nghiệp vụ."
- **Ghi chú phân tích tại Trang 84:**
  > "Quy tắc SLA chi tiết được xác định tại DEC-MVP-23/24 và Event–Response Table."

#### Phân tích & Làm rõ Nghiệp vụ:
1. **Khái niệm Chu kỳ Phục vụ (Service Cycle / Session):**
   - Một `conversation_id` trong hệ thống Omnichannel đại diện cho toàn bộ lịch sử tương tác giữa một khách hàng và doanh nghiệp trên một kênh.
   - Vòng đời của hội thoại là chuỗi lặp: `Open` $\rightarrow$ `Resolved` $\rightarrow$ `Reopen (Open)` $\rightarrow$ `Resolved`.
   - Mỗi chu kỳ từ lúc `Open` (hoặc `Reopen`) đến khi `Resolved` là một **lượt phục vụ độc lập (Distinct Service Session)**.
2. **Thiết lập lại Đồng hồ SLA First Response:**
   - Khách gửi tin nhắn mới ở phiên Reopen là một thắc mắc / yêu cầu mới phát sinh.
   - Trách nhiệm phản hồi đầu tiên được kích hoạt lại: `first_responded_at := NULL`.
   - Hạn phản hồi đầu tiên phải được **tái lập dựa trên thời điểm tin nhắn Reopen đến**:
     $$\text{first\_response\_due\_at}_{\text{new}} = \text{CalculateDeadline}(\text{received\_at}, \text{first\_response\_minutes})$$
     (có tính toán khung giờ làm việc 08:00–21:00 theo AC-24.7).
   - Tương tự, hạn hoàn tất xử lý tổng thể được tính lại:
     $$\text{resolution\_due\_at}_{\text{new}} = \text{CalculateDeadline}(\text{received\_at}, \text{resolution\_minutes})$$
3. **Hệ quả nếu không cấp hạn mới:**
   - Nếu giữ hạn cũ của phiên trước (đã trôi qua hàng giờ hoặc hàng ngày), hệ thống lập tức coi tin nhắn mới là "quá hạn ngay khi vừa nhận", triệt tiêu toàn bộ ý nghĩa giám sát SLA và làm sai lệch báo cáo hiệu suất CSKH.

---

### 2.4. Quy tắc Bảo toàn Lịch sử SLA của Phiên trước

#### Căn cứ tài liệu gốc:
- **`DEC-MVP-40` & Bảng 20.2 / `CR-002` (Trang 45, Trang 200):**
  > "Hệ thống ghi nhận lịch sử và giữ nguyên các vi phạm SLA đã phát sinh."
- **`UC-08` Postconditions (Trang 44):**
  > "Lưu lịch sử thay đổi."

#### Phân tích & Làm rõ Nghiệp vụ:
1. **Tính Bất biến của Lịch sử Sự kiện SLA:**
   - Mọi sự kiện đo lường của phiên cũ (`first_response_met`, `first_response_breached`, `resolution_met`, `resolution_breached`) đã được lưu bền vững trong bảng `sla_events` và `inbox_events`.
   - Hành vi Reopen **tuyệt đối không được xóa, sửa, hoặc ghi đè các bản ghi sự kiện SLA đã sinh ra trong quá khứ**.
   - Khi báo cáo thống kê KPI tháng/quý được trích xuất, các vi phạm hoặc thành tích của phiên trước vẫn được tính toán đầy đủ cho nhân viên đã phụ trách phiên đó.
2. **Khởi tạo Theo dõi cho Phiên mới:**
   - Các sự kiện SLA của phiên mới sẽ được bổ sung tiếp nối vào bảng sự kiện với mốc thời gian `created_at` tương ứng của phiên mới.

---

### 2.5. Điều kiện Không được Reset Deadline Trong Cùng Chu kỳ Phục vụ (Anti-Cheating Rule)

#### Căn cứ tài liệu gốc & Ý định Kiến trúc CSDL:
- **Bình luận nghiệp vụ trong migration `0005_routing_sla.sql` (Dòng 1–2):**
  > *"Deadline là mốc nghiệp vụ bất biến: tin mới cập nhật activity nhưng không được 'tặng thêm giờ' cho hàng chờ."*
- **Quy tắc Nghiệp vụ Chống gian lận (Anti-Cheating Constraint):**
  - Khi một hội thoại đang trong trạng thái chờ xử lý (`state = 'open'` hoặc `state = 'pending'`), thời hạn First Response SLA đã được chốt ngay từ tin nhắn đầu tiên của phiên đó.
  - Nếu trong lúc chờ nhân viên trả lời, khách hàng gửi thêm tin nhắn thứ 2, thứ 3... thì các tin nhắn này chỉ cập nhật thời gian hoạt động gần nhất (`last_message_at`), **tuyệt đối không được kéo dài hoặc đặt lại deadline SLA**.
  - Nhân viên hoặc tiến trình cập nhật không được phép thay đổi giá trị `first_response_due_at` để trốn tránh việc bị ghi nhận Breach.

#### Phân định Ranh giới Nghiệp vụ vs Lỗi Cài đặt Kỹ thuật:
- **Quy tắc đúng:** Ngăn chặn đặt lại deadline **trong khi hội thoại đang MỞ (`state IN ('open', 'pending')`)**.
- **Lỗi cài đặt của trigger `prevent_sla_deadline_reset`:** Trigger áp dụng quy tắc này một cách mù quáng cho **mọi câu lệnh UPDATE**, kể cả khi hội thoại đang từ trạng thái `resolved` chuyển sang `open` (tức là chuyển giao giữa hai chu kỳ phục vụ khác nhau).
- **Kết luận đối chiếu:** Việc cho phép cấp deadline mới khi Reopen hội thoại đã `resolved` hoàn toàn nhất quán với tài liệu BA gốc và không hề vi phạm quy tắc chống gian lận trong cùng một phiên phục vụ.

---

## 3. MA TRẬN ĐỐI CHIẾU THÀNH PHẦN TÀI LIỆU BA CHỊU ẢNH HƯỞNG

| Thành phần Tài liệu BA | Vị trí trong PDF gốc | Hiện trạng Nội dung trong PDF | Đánh giá Mức độ Đầy đủ | Hướng Xử lý Tài liệu |
|---|---|---|---|---|
| **Conversation Lifecycle & State Machine** | Mục 1.2 (Trang 133–134), `EVT-01` (Trang 72) | Đã mô tả trạng thái `Open` $\rightarrow$ `Resolved` $\rightarrow$ `Reopen`. | **Đúng về luồng trạng thái, nhưng thiếu đặc tả về chu kỳ đồng hồ SLA.** | Bổ sung phụ lục thiết kế làm rõ khái niệm Session-based SLA Clock. Giữ nguyên Baseline. |
| **Handling Mode Evaluation** | `AC-11.3` (Trang 142), `UC-08` (Trang 44–45) | Đã quy định: Reopen kiểm tra điều kiện an toàn trước khi vào Auto Mode. | **Đầy đủ và chính xác.** | Giữ nguyên văn AC-11.3 trong Baseline. |
| **SLA Business Rules** | `AC-24.5`–`AC-24.7` (Trang 150), Bảng 7.2 (Trang 74) | Đã quy định ngưỡng 5m/10m, 15m/30m và khung giờ 08:00–21:00. | **Thiếu quy tắc tường minh: "Mỗi chu kỳ Reopen khởi tạo một đồng hồ First Response SLA mới".** | Soạn thảo đề xuất bổ sung vào Bảng quy tắc SLA tại `g2_01_ba_change_proposal.md`. |
| **SLA Anti-Cheating Invariance** | Migration `0005_routing_sla.sql` | Chưa được văn bản hóa tường minh trong phần Business Rules của PDF. | **Thiếu đặc tả bằng văn bản nghiệp vụ.** | Đưa vào đặc tả bàn giao Codex (`g2_01_ba_handoff.md`) và đề xuất bổ sung vào Practice #16. |
| **Test Scenarios & Traceability** | Practice #18 (Trang 192), Practice #7 (Trang 84) | Chưa có Test Case riêng biệt cho Reopen SLA Reset. | **Thiếu ca kiểm thử hồi quy.** | Thiết lập kịch bản `TC-REOPEN-SLA-01` trong tài liệu bàn giao Codex. |

---

## 4. KẾT LUẬN CỦA BUSINESS ANALYST

1. Tài liệu phân tích nghiệp vụ gốc (`Phân tích nghiệp vụ khoá luận (6).pdf`) đã định nghĩa hoàn toàn chính xác hành vi Reopen tại `FR-01 (AC-01.3)`, `FR-11 (AC-11.3)` và `UC-08`.
2. Lỗi `GAP-07C` thuần túy là **lỗi thiếu điều kiện ngoại lệ ở tầng cài đặt trigger CSDL PostgreSQL** (`prevent_sla_deadline_reset` không loại trừ `OLD.state IN ('resolved', 'closed')`), không phải là sự thay đổi yêu cầu nghiệp vụ gốc.
3. Không cần thay đổi Requirements Baseline hiện hành. Các tài liệu bàn giao kỹ thuật và đề xuất bổ sung sẽ làm rõ ranh giới:
   - **Bất biến trong phiên (Within-Session Invariance):** Chống gian lận kéo dài deadline khi đang xử lý.
   - **Tái lập theo phiên (Inter-Session Reset):** Cấp deadline mới khi khách mở lại lượt phục vụ mới sau khi đã giải quyết xong.

---

## Phần 2: BA Change Proposal

# ĐỀ XUẤT CHỈNH SỬA TÀI LIỆU PHÂN TÍCH NGHIỆP VỤ (BA CHANGE PROPOSAL)
## BỔ SUNG ĐẶC TẢ VÒNG ĐỜI HỘI THOẠI & ĐỒNG HỒ SLA KHI REOPEN (GAP-07C)

- **Mã tài liệu:** `G2-01-BA-CHANGE-PROPOSAL`
- **Tài liệu gốc tham chiếu:** `Phân tích nghiệp vụ khoá luận (6).pdf` (Bản thảo báo cáo khóa luận 204 trang)
- **Người đề xuất:** Business Analyst
- **Ngày lập:** 07/11/2026
- **Trạng thái:** Dự thảo Đề xuất Chỉnh sửa (Proposal – Pending Internal Approval, Không tự ý sửa PDF gốc)

---

## 1. NGUYÊN TẮC QUẢN LÝ THAY ĐỔI TÀI LIỆU

1. **Bảo tồn Requirements Baseline:** Không tự ý thay đổi mã định danh, cấu trúc Given–When–Then của `AC-11.3` hay bất kỳ yêu cầu chức năng nào đã được chốt trong Baseline Draft.
2. **Bổ sung Diễn giải Làm rõ (Clarification Specification):** Các đề xuất dưới đây tập trung vào việc làm rõ cơ chế vận hành của đồng hồ SLA giữa các phiên phục vụ, bổ sung quy tắc chống gian lận SLA và ma trận kiểm thử truy vết để khắc phục sự thiếu hụt chi tiết kỹ thuật dẫn đến lỗi `GAP-07C`.
3. **Phân định rõ phiên bản:** Các thay đổi sẽ được tổng hợp để trình Nhóm tác giả và Giảng viên Hướng dẫn xem xét cập nhật trong đợt xuất bản tài liệu BA phiên bản tiếp theo.

---

## 2. DANH MỤC ĐỀ XUẤT CHỈNH SỬA CHI TIẾT THEO SỐ TRANG / MỤC

### Đề xuất 1: Bổ sung diễn giải chu kỳ SLA vào Use Case `UC-08` (Mục 2.3, Trang 44–45)

- **Vị trí hiện tại trong PDF:** Trang 44–45, Mục `2.3. UC-08 – Kết thúc phiên hỗ trợ thủ công`.
- **Hiện trạng:**
  - *Postconditions (Trang 44):* "Conversation được Resolved hợp lệ; tin nhắn mới từ khách có thể Reopen và khôi phục Auto Mode sau kiểm tra an toàn."
  - *Main Flow Bước 6–7 (Trang 45):*
    > 6. Khi khách hàng gửi tin nhắn mới, hệ thống Reopen Conversation.  
    > 7. Hệ thống kiểm tra điều kiện an toàn và chỉ chuyển Auto Mode nếu được phép.
- **Nội dung đề xuất bổ sung:**
  - Thêm vào *Postconditions:*
    > "Hội thoại chuyển sang `Resolved` đồng thời chốt lại chu kỳ phục vụ hiện tại và lưu lịch sử đo lường SLA. Khi Reopen, một chu kỳ phục vụ mới được khởi tạo với đồng hồ đo lường SLA riêng."
  - Bổ sung chi tiết vào *Main Flow Bước 6:*
    > "6. Khi khách hàng gửi tin nhắn mới hợp lệ, hệ thống Reopen Conversation, chuyển trạng thái về `Open`, **khởi tạo lại thời hạn First Response SLA và Resolution SLA tính từ thời điểm nhận tin nhắn mới** (tuân thủ khung giờ làm việc), và xóa mốc `first_responded_at` để bắt đầu đo lường phản hồi cho phiên mới."
  - Bổ sung vào *Alternative Flows (AF-03 – Gia hạn xử lý, Trang 45):*
    > Giữ nguyên diễn giải gia hạn của CR-002: gia hạn chỉ áp dụng trong phiên Manual Mode đang mở, không làm thay đổi hay reset mốc SLA ban đầu của phiên đó.

---

### Đề xuất 2: Bổ sung quy tắc đồng hồ SLA vào Event–Response Table (Practice #7, Trang 72 & 74)

- **Vị trí 1 trong PDF:** Trang 72, Bảng 7.1, dòng sự kiện `EVT-01` khi `System State = Conversation Resolved`.
  - **Hiện trạng:**
    > *Response:* "Reopen Conversation và kiểm tra điều kiện chuyển Auto Mode hoặc tiếp tục Manual Mode."
  - **Nội dung đề xuất chỉnh sửa:**
    > *Response:* "Reopen Conversation, **thiết lập hạn First Response SLA mới cho phiên phục vụ tiếp theo dựa trên thời điểm nhận tin nhắn mới**, và kiểm tra điều kiện chuyển Auto Mode hoặc tiếp tục Manual Mode."
- **Vị trí 2 trong PDF:** Trang 74, phần ghi chú *Quy tắc áp dụng SLA* (dưới dòng `EVT-29`).
  - **Hiện trạng:**
    > "Quy tắc áp dụng SLA: Giờ tính SLA là 08:00–21:00. Priority High cảnh báo sau 5 phút và Breach sau 10 phút; Priority Normal cảnh báo sau 15 phút và Breach sau 30 phút. Thời gian ngoài giờ không được tính vào đồng hồ SLA nghiệp vụ."
  - **Nội dung đề xuất bổ sung thêm 2 gạch đầu dòng:**
    > - "• **Phân định theo phiên tương tác:** Mỗi khi hội thoại được Reopen từ trạng thái Resolved, hệ thống kích hoạt một chu kỳ tính First Response SLA mới độc lập. Lịch sử vi phạm hoặc đạt SLA của các phiên trước đó được bảo lưu nguyên vẹn trong nhật ký sự kiện, không bị xóa hoặc ghi đè."  
    > - "• **Quy tắc bất biến trong phiên (Anti-Cheating):** Trong thời gian hội thoại đang ở trạng thái Open hoặc Pending (chưa Resolve), mốc thời gian First Response SLA là bất biến. Các tin nhắn tiếp theo của khách hàng chỉ cập nhật thời gian hoạt động mới nhất, tuyệt đối không được kéo dài hoặc đặt lại hạn SLA của phiên đang mở."

---

### Đề xuất 3: Bổ sung Ghi chú Nghiệp vụ cho `AC-11.3` (Practice #10, Trang 142)

- **Vị trí trong PDF:** Trang 142, Bảng 10.13: Acceptance Criteria – FR-11.
- **Hiện trạng:**
  - `AC-11.3`:
    > *Given:* Conversation được Resolve hợp lệ  
    > *When:* Khách gửi tin nhắn mới  
    > *Then:* Hệ thống Reopen và kiểm tra điều kiện Auto Mode.
- **Nội dung đề xuất:**
  - **Giữ nguyên văn bản tiêu chí của `AC-11.3`** để đảm bảo tính toàn vẹn của Baseline đã đăng ký trong `requirements_source_register.csv`.
  - Bổ sung một đoạn **"Ghi chú kiểm chứng Acceptance Criteria (Verification Note)"** ngay dưới Bảng 10.13:
    > *"Ghi chú kỹ thuật cho AC-11.3: Hành vi Reopen hội thoại bao hàm việc thiết lập lại mốc thời gian phản hồi đầu tiên (first_response_due_at) theo chính sách SLA của kênh và mức ưu tiên, tính từ thời điểm nhận tin nhắn Reopen. Hệ thống kiểm soát CSDL không được áp dụng quy tắc chống gian lận để ghi đè mốc thời gian quá khứ vào phiên Reopen mới."*

---

### Đề xuất 4: Bổ sung vào Danh mục Quy tắc Nghiệp vụ Hợp nhất (Practice #16, Trang 187–188)

- **Vị trí trong PDF:** Trang 187–188, Bảng 16.1: Consolidated Business Rules Catalog.
- **Nội dung đề xuất bổ sung thêm 2 bản ghi quy tắc:**

| Mã nguồn | Loại | Nội dung quy tắc nghiệp vụ | Yêu cầu liên quan |
|---|:---:|---|:---:|
| **BR-SLA-01** *(Bổ sung)* | Action Enabler | **Khởi tạo SLA khi Reopen:** Khi hội thoại được mở lại (Reopen) từ trạng thái Resolved hợp lệ, hệ thống phải khởi tạo lại hạn First Response SLA và Resolution SLA tương ứng với chu kỳ phục vụ mới. Toàn bộ lịch sử sự kiện SLA của các phiên phục vụ trước đó được giữ nguyên vẹn. | FR-01, FR-11, FR-24 |
| **BR-SLA-02** *(Bổ sung)* | Constraint | **Bất biến hạn SLA trong phiên (Chống gian lận):** Trong suốt thời gian hội thoại duy trì trạng thái Open hoặc Pending, hạn First Response SLA là mốc bất biến. Các tin nhắn tiếp theo của khách không được phép làm thay đổi hoặc kéo dài hạn phản hồi đã chốt của phiên đó. | FR-11, FR-24, QR-06 |

---

### Đề xuất 5: Bổ sung Ma trận Truy vết Kiểm thử (Practice #18, Trang 192–195)

- **Vị trí trong PDF:** Trang 192–195, Bảng 18.1 và 18.2: Requirements Traceability Matrix.
- **Hiện trạng:**
  - Yêu cầu `AC-11.3` mới chỉ được gắn với ca kiểm thử vòng đời chung `test_giai_quyet_csat.py` (vốn chỉ kiểm tra trạng thái `state = 'open'`, chưa kiểm tra trường `first_response_due_at`).
- **Nội dung đề xuất bổ sung:**
  - Bổ sung mã kiểm thử tích hợp: **`TC-REOPEN-SLA-01`** (File kiểm thử: `tests/test_reopen_sla_reset.py`).
  - Phân loại bằng chứng: **Executed Evidence** (yêu cầu chạy trực tiếp trên PostgreSQL test container).
  - Ánh xạ liên kết: `FR-11 (AC-11.3)` + `FR-24 (AC-24.1, AC-24.7)` $\rightarrow$ `TC-REOPEN-SLA-01`.

---

## 3. KẾ HOẠCH BÀN GIAO VÀ ĐỒNG BỘ TIẾP THEO

1. **Lập trình và Kiểm thử (`TASK-CODE-01` & `TASK-TEST-01`):**
   - Đội ngũ kỹ thuật sử dụng tài liệu bàn giao [`g2_01_ba_handoff.md`](file:///Users/huynhlehoaibao/Documents/AIAgent_mar/docs/requirements-audit/g2_01_ba_handoff.md) để tiến hành viết migration sửa trigger và file kiểm thử `tests/test_reopen_sla_reset.py`.
2. **Nghiệm thu:**
   - Khi `test_reopen_sla_reset.py` chạy đạt 100% assertions trên CSDL kiểm thử, issue `GAP-07C` sẽ được chuyển trạng thái sang **VERIFIED** kèm Executed Evidence.
3. **Cập nhật Báo cáo Khóa luận:**
   - Các đề xuất chỉnh sửa trên sẽ được biên tập đồng bộ vào bản Word/LaTeX chính thức của báo cáo khóa luận khi thực hiện đợt review tài liệu bảo vệ.

---

## Phần 3: BA Handoff

# ĐẶC TẢ YÊU CẦU BÀN GIAO CHO KỸ THUẬT (CODEX HANDOFF SPEC)
## KHẮC PHỤC LỖI TÁI LẬP HẠN SLA KHI REOPEN HỘI THOẠI (GAP-07C)

- **Mã tài liệu:** `G2-01-BA-HANDOFF`
- **Mã công việc kế tiếp:** `TASK-CODE-01` & `TASK-TEST-01` (Implementation Backlog v1.1)
- **Người lập:** Business Analyst
- **Đối tượng bàn giao:** Đội ngũ Lập trình viên Backend (Codex / Engineering Team)
- **Trạng thái:** Sẵn sàng triển khai (Ready for Implementation)

---

## 1. THÔNG TIN ĐỊNH DANH YÊU CẦU (REQUIREMENT IDS)

- **Functional Requirements:**
  - `FR-11` (AC-11.3): Phản hồi thủ công và kết thúc phiên hỗ trợ – Reopen hội thoại khi nhận tin nhắn mới từ khách sau Resolve.
  - `FR-01` (AC-01.3): Tiếp nhận tin nhắn đa kênh – Reopen hội thoại và đánh giá lại Handling Mode.
  - `FR-24` (AC-24.1, AC-24.5, AC-24.6, AC-24.7): Phân công, cảnh báo SLA và tính toán hạn phản hồi trong khung giờ làm việc 08:00–21:00.
- **Quality / Non-Functional Requirements:**
  - `QR-06`: Reliability – Assignment & SLA Integrity.
  - `DFR-03`: Kiểm tra Handling Mode và hiệu lực phản hồi.
- **Mã vấn đề theo dõi:** `GAP-07C` (Khắc phục đứt gãy tính toán SLA khi Reopen).

---

## 2. BỐI CẢNH & VẤN ĐỀ NGHIỆP VỤ HIỆN TẠI (CURRENT PROBLEM)

1. **Thực trạng phát hiện qua kiểm toán:**
   - Khi một hội thoại đã được nhân viên CSKH giải quyết xong (`state = 'resolved'`), nếu khách hàng nhắn tin trở lại sau đó vài giờ hoặc vài ngày, hệ thống đã mở lại hội thoại thành công (`state = 'open'`, `first_responded_at = NULL`).
   - Tuy nhiên, cơ chế bảo vệ tầng CSDL đang áp dụng quy tắc chống gian lận SLA một cách tuyệt đối trên mọi thao tác `UPDATE conversations`: **mọi nỗ lực cập nhật deadline mới đều bị cơ chế này can thiệp và ép quay về hạn cũ của phiên phục vụ trước**.
2. **Hậu quả vận hành:**
   - Hạn phản hồi đầu tiên (`first_response_due_at`) của hội thoại bị giữ nguyên ở mốc thời gian quá khứ (của phiên đã đóng).
   - Tiến trình kiểm tra vi phạm SLA (`SlaMonitor`) nhận diện hội thoại đang mở, chưa có phản hồi (`first_responded_at IS NULL`), và hạn phản hồi đã nằm trong quá khứ $\rightarrow$ **Tự động ghi nhận vi phạm First Response SLA (Breach) ngay tại giây thứ 0**.
   - Nhân viên CSKH hoặc AI Agent bị phạt vi phạm oan sai đối với một tin nhắn mới vừa được tiếp nhận.

---

## 3. HÀNH VI NGHIỆP VỤ KỲ VỌNG (EXPECTED BUSINESS BEHAVIOR)

Hệ thống phải phân định rõ ràng giữa hai ngữ cảnh nghiệp vụ:

### A. Ngữ cảnh 1: Chuyển giao giữa hai phiên phục vụ (Inter-Session Transition / Reopen)
- **Điều kiện:** Hội thoại đang ở trạng thái đã kết thúc (`state = 'resolved'` hoặc `state = 'closed'`) và nhận được tin nhắn hợp lệ mới từ khách hàng.
- **Hành vi kỳ vọng:**
  1. Trạng thái hội thoại chuyển sang `state = 'open'`.
  2. Xóa các mốc thời gian kết thúc của phiên cũ (`resolved_at := NULL`, `outcome := NULL`, `first_responded_at := NULL`).
  3. **Hệ thống PHẢI cấp một hạn phản hồi đầu tiên mới (`first_response_due_at`) và hạn hoàn tất mới (`resolution_due_at`)** được tính từ thời điểm tiếp nhận tin nhắn mới theo chính sách SLA tương ứng với kênh và mức ưu tiên của hội thoại (có áp dụng khung giờ làm việc 08:00–21:00).
  4. Cơ chế chống gian lận ở tầng CSDL không được phép ngăn cản việc thiết lập các mốc thời gian mới này.
  5. Lịch sử các sự kiện SLA (`sla_events`) của phiên phục vụ trước đó được bảo lưu vĩnh viễn, không bị xóa hay sửa đổi.

### B. Ngữ cảnh 2: Đang trong cùng một phiên phục vụ (Within-Session Invariance / Anti-Cheating)
- **Điều kiện:** Hội thoại đang ở trạng thái chờ hoặc đang xử lý (`state IN ('open', 'pending')`).
- **Hành vi kỳ vọng:**
  1. Hạn SLA (`first_response_due_at`) đã chốt là **bất biến (Immutable)** cho đến khi nhân viên thực hiện phản hồi đầu tiên.
  2. Mọi tin nhắn tiếp theo của khách hàng gửi đến trong lúc chờ chỉ cập nhật thời gian hoạt động mới nhất (`last_message_at`, `updated_at`), **tuyệt đối không được kéo dài hoặc đặt lại hạn SLA**.
  3. Mọi thao tác cập nhật từ API, ứng dụng hoặc giao diện cố tình thay đổi `first_response_due_at` sang mốc tương lai xa hơn trong lúc hội thoại đang mở đều phải bị chặn đứng.

---

## 4. QUY TẮC NGHIỆP VỤ BẮT BUỘC (BUSINESS RULES)

- **BR-SLA-01 (Session Demarcation):** Mỗi chu kỳ từ trạng thái `Resolved` được mở lại sang `Open` cấu thành một lượt phục vụ mới độc lập. Lượt phục vụ mới có đồng hồ đo lường First Response SLA và Resolution SLA riêng.
- **BR-SLA-02 (Anti-Cheating Guard):** Trong suốt thời gian hội thoại duy trì trạng thái `open` hoặc `pending`, mốc thời gian `first_response_due_at` là bất biến, không được phép điều chỉnh lùi lại vì bất kỳ lý do gì.
- **BR-SLA-03 (Audit & History Immutability):** Các bản ghi vi phạm hoặc hoàn thành SLA (`first_response_met`, `first_response_breached`, `resolution_met`, `resolution_breached`) đã ghi nhận trong bảng lịch sử sự kiện SLA của phiên cũ không được phép bị xóa hoặc sửa đổi khi Reopen.
- **BR-SLA-04 (Working Hours Enforcement):** Hạn SLA mới của phiên Reopen phải tuân thủ khung giờ làm việc 08:00–21:00 theo quy định tại `AC-24.7`.

---

## 5. TIÊU CHÍ NGHIỆM THU (ACCEPTANCE CRITERIA)

Dành cho việc nghiệm thu kỹ thuật `TASK-CODE-01`:

- **AC-CODEX-01 (Cấp hạn mới khi Reopen từ Resolved):**
  - **Given:** Một hội thoại đang ở trạng thái `state = 'resolved'` có `first_response_due_at = T_cu` (trong quá khứ).
  - **When:** Hệ thống thực thi luồng Reopen với giá trị `first_response_due_at = T_moi` (trong tương lai).
  - **Then:** CSDL chấp nhận cập nhật; giá trị `first_response_due_at` sau câu lệnh mang đúng giá trị `T_moi`; `first_responded_at` có giá trị `NULL`.
- **AC-CODEX-02 (Chống gian lận khi hội thoại đang Open):**
  - **Given:** Một hội thoại đang ở trạng thái `state = 'open'` có `first_response_due_at = T_goc`.
  - **When:** Có câu lệnh cập nhật `UPDATE conversations SET first_response_due_at = T_gian_lan WHERE id = ...`.
  - **Then:** CSDL không chấp nhận giá trị mới, bảo lưu nguyên vẹn `first_response_due_at = T_goc`.
- **AC-CODEX-03 (Không phát sinh False Breach):**
  - **Given:** Hội thoại vừa Reopen thành công với hạn SLA mới trong tương lai.
  - **When:** Tiến trình `SlaMonitor.scan_once()` thực thi quét vi phạm.
  - **Then:** Không có sự kiện `first_response_breached` nào được sinh ra cho hội thoại này.
- **AC-CODEX-04 (Bảo toàn lịch sử sự kiện SLA cũ):**
  - **Given:** Hội thoại đã từng phát sinh sự kiện SLA ở phiên trước trong bảng sự kiện.
  - **When:** Hội thoại được Reopen và tiếp tục chu trình xử lý.
  - **Then:** Toàn bộ bản ghi lịch sử cũ trong bảng `sla_events` giữ nguyên vẹn số lượng và mốc thời gian ban đầu.

---

## 6. KỊCH BẢN KIỂM THỬ ĐỀ XUẤT (TEST SCENARIOS)

Đội ngũ kỹ thuật cần hiện thực hóa thành file kiểm thử tự động `tests/test_reopen_sla_reset.py` (`TASK-TEST-01`):

| Test ID | Tên kịch bản | Dữ liệu đầu vào | Các bước thực hiện | Kết quả mong đợi |
|---|---|---|---|---|
| **TC-SLA-REOPEN-01** | Cấp mới SLA khi khách mở lại hội thoại | Hội thoại có SLA Normal (15m), đã Resolved lúc 2 giờ trước. | 1. Gọi Reopen.<br>2. Đọc giá trị CSDL. | `state == 'open'`; `first_response_due_at` nằm trong khoảng $[now + 14m, now + 16m]$. |
| **TC-SLA-REOPEN-02** | Không phạt vi phạm SLA khi vừa Reopen | Hội thoại vừa Reopen xong từ TC-SLA-REOPEN-01. | Chạy tiến trình quét vi phạm SLA (`scan_once`). | Kết quả trả về không có breach mới; bảng `sla_events` không có bản ghi `first_response_breached` của phiên mới. |
| **TC-SLA-REOPEN-03** | Chống gian lận kéo dài deadline khi đang Open | Hội thoại đang Open với `first_response_due_at = now() + 10m`. | Thực hiện `UPDATE conversations SET first_response_due_at = now() + 60m`. | Giá trị `first_response_due_at` trong CSDL vẫn giữ nguyên mốc $now + 10m$, không bị đẩy lùi lên $60m$. |
| **TC-SLA-REOPEN-04** | Bảo tồn sự kiện SLA của phiên trước | Hội thoại phiên trước có 1 sự kiện `resolution_met`. | Thực hiện Resolve $\rightarrow$ Reopen $\rightarrow$ Kiểm tra bảng sự kiện. | Bản ghi `resolution_met` của phiên trước vẫn tồn tại nguyên vẹn. |

---

## 7. NGOÀI PHẠM VI (OUT OF SCOPE)

- **Không thay đổi nghiệp vụ khảo sát CSAT:** Logic nhận diện điểm số CSAT (1–5 sao) trong vòng 24 giờ sau Resolve giữ nguyên như hiện hành, không bị ảnh hưởng bởi thay đổi này.
- **Không thay đổi các ngưỡng phút SLA:** Ngưỡng 15m/30m (Normal) và 5m/10m (High) giữ nguyên theo chính sách đã cấu hình.
- **Không thay đổi giao diện Dashboard:** Thao tác của nhân viên và giao diện Native Dashboard không thay đổi.

---

## 8. CÂU HỎI MỞ & LƯU Ý KỸ THUẬT (OPEN QUESTIONS & TECH NOTES)

1. **Khuyến nghị kỹ thuật:** Lập trình viên nên xử lý điều kiện tại tầng CSDL bằng cách thêm mệnh đề loại trừ trạng thái cũ:
   `IF OLD.state NOT IN ('resolved', 'closed') THEN ...` vào hàm trigger kiểm tra thay đổi deadline.
2. **Lưu ý kiểm thử môi trường:** Bộ test `TASK-TEST-01` phải được cấu hình chạy trên PostgreSQL test container thật (thông qua fixture `csdl_kiem_thu`) để kiểm chứng trực tiếp hành vi của trigger PL/pgSQL trong CSDL, không thể dùng mock repository.

---

## Phần 4: Code Implementation Report

# G2-01 Code Implementation Report — GAP-07C

- **Task:** `G2-01-CODE – FIX REOPEN SLA TRIGGER`
- **Ngày thực hiện:** 07/11/2026
- **Phạm vi:** PostgreSQL trigger chống reset SLA khi Reopen và regression tests
- **Kết luận:** **Fixed & Verified**

## 1. Kiểm tra trước khi sửa

### Working tree

Lệnh `git status --short --branch` không chạy được vì Git hệ thống của máy phụ
thuộc macOS Command Line Tools đang thiếu:

```text
xcrun: error: invalid active developer path (/Library/Developer/CommandLineTools),
missing xcrun at: /Library/Developer/CommandLineTools/usr/bin/xcrun
```

Đã kiểm tra read-only trực tiếp từ Git index v2 để không bỏ qua yêu cầu bảo toàn
thay đổi đang tồn tại:

```text
tracked_modified=16
tracked_missing=0
```

16 file tracked đã sửa sẵn đều nằm ngoài GAP-07C. Không file nào trùng với các
file được tạo trong task này. Không chỉnh sửa, hoàn nguyên hoặc ghi đè các thay
đổi đó.

### Thứ tự migration

- Trước sửa: 38 migration, từ `0001_account_aware_foundation.sql` đến
  `0038_cong_viec_van_chuyen.sql`.
- Migration runner sắp thứ tự theo version bốn chữ số và kiểm checksum migration
  đã áp dụng.
- Bản sửa được thêm ở version kế tiếp `0039`; không sửa migration `0005` cũ.

### Trigger và luồng Reopen

- Trigger cũ trong `0005_routing_sla.sql` bảo toàn hai deadline trên mọi
  `UPDATE` nếu deadline cũ khác `NULL`.
- `mo_lai_neu_da_giai_quyet()` thực hiện một câu `UPDATE` nguyên tử từ
  `resolved` sang `open`, xóa `first_responded_at`, đồng thời tính lại cả
  `first_response_due_at` và `resolution_due_at`.
- Trigger `BEFORE UPDATE` cũ ghi đè hai giá trị mới về deadline của phiên cũ,
  làm SLA monitor tạo breach ngay sau Reopen.
- Hành vi này khớp nguyên nhân GAP-07C và trái AC-CODEX-01/03 trong BA Handoff.

### PostgreSQL test độc lập

Đã xác nhận môi trường PostgreSQL thật tại `127.0.0.1:5433`. Fixture
`csdl_kiem_thu` tạo database riêng tên `kt_<random>` cho từng test, áp schema và
toàn bộ migration, sau đó terminate connection và drop database. Không kết nối
hoặc chạy migration trên production database.

## 2. Thay đổi triển khai

### File đã tạo

1. `agent/migrations/versions/0039_fix_sla_reopen_trigger.sql`
   - Thay function `prevent_sla_deadline_reset()` bằng migration tiến tới.
   - Chỉ cho phép thay deadline khi transition đúng là
     `OLD.state IN ('resolved', 'closed') AND NEW.state = 'open'`.
   - Với mọi transition khác, tiếp tục bảo toàn deadline cũ nếu đã được cấp.
   - Không xóa hoặc cập nhật `sla_events`.
2. `tests/test_reopen_sla_reset.py`
   - 13 test PostgreSQL thật, bao phủ deadline First Response, deadline
     Resolution, chống kéo dài trong Open/Pending, false breach, lịch sử SLA,
     trạng thái không hợp lệ và các trường hợp biên.
3. `docs/requirements-audit/g2_01_code_implementation_report.md`
   - Báo cáo triển khai và bằng chứng thực thi này.

### File không thay đổi

- Không sửa BA Handoff, Requirements Baseline hoặc các tài liệu BA gốc.
- Không sửa source module Reopen/SLA monitor vì nguyên nhân nằm ở trigger.
- Không mở rộng sang Auto Resolve, SLA Warning, Shipping hoặc Pending Action.

## 3. Regression coverage

| Yêu cầu | Test coverage | Kết quả |
|---|---|---:|
| Resolved → Open cấp mới First Response deadline | `test_resolved_to_open_gets_new_first_response_deadline` | PASS |
| Resolved → Open cấp mới Resolution deadline | `test_resolved_to_open_gets_new_resolution_deadline` | PASS |
| Open/Pending không reset deadline trái phép | 4 tổ hợp transition parametrized | PASS |
| Không tạo False Breach ngay sau Reopen | `test_reopen_does_not_create_immediate_false_breach` | PASS |
| Không mất SLA Events phiên cũ | `test_reopen_preserves_previous_sla_events` | PASS |
| Từ chối Reopen từ trạng thái không hợp lệ | Open, Pending và Closed qua service | PASS |
| Edge: Closed → Open ở trigger | `test_closed_to_open_is_a_valid_trigger_level_reopen` | PASS |
| Edge: cấp lần đầu khi deadline đang NULL | `test_open_cycle_can_receive_initial_deadlines_when_they_are_null` | PASS |

## 4. Test execution log

### 4.1. Tái hiện trước bản vá

Command:

```text
python -m pytest -q tests/test_reopen_sla_reset.py -rs
```

Result:

```text
FF....F....F. [100%]
4 failed, 9 passed in 12.65s
```

Sai lệch đo được:

```text
first_response_due_at sau Reopen == deadline cũ
resolution_due_at sau Reopen == deadline cũ
SlaMonitor.scan_once() == {'first_response': 1, 'resolution': 1}
```

### 4.2. Regression GAP-07C sau bản vá

Command:

```text
python -m pytest -q tests/test_reopen_sla_reset.py -rs
```

Result:

```text
............. [100%]
13 passed in 9.77s
```

- Passed: **13**
- Failed: **0**
- Skipped: **0**

### 4.3. SLA, lifecycle, inbox và migration tests hiện hữu

Command:

```text
python -m pytest -q \
  tests/test_sla.py \
  tests/test_routing_sla_schema.py \
  tests/test_chatwoot_lifecycle.py \
  tests/test_giai_quyet_csat.py \
  tests/test_inbox_api.py \
  tests/test_inbox_service.py \
  tests/test_inbox_outbox_schema.py \
  tests/test_inbox_read_schema.py \
  tests/test_migrations.py \
  tests/test_migration_xuong_dong.py -rs
```

Result:

```text
........................................................... [100%]
59 passed, 16 warnings in 5.55s
```

- Passed: **59**
- Failed: **0**
- Skipped: **0**
- Warnings: **16** — deprecation warnings hiện hữu của FastAPI `on_event`,
  không liên quan GAP-07C.

### 4.4. Static check

Command:

```text
python -m ruff check tests/test_reopen_sla_reset.py
```

Result:

```text
All checks passed!
```

### 4.5. Lượt xác minh cuối cùng (gộp)

Chạy chung regression GAP-07C với toàn bộ nhóm SLA, lifecycle, inbox và
migration nêu trên để loại trừ phụ thuộc thứ tự test.

```text
........................................................................ [100%]
72 passed, 16 warnings in 14.42s
```

- Passed: **72**
- Failed: **0**
- Skipped: **0**
- Warnings: **16** — cùng nhóm deprecation warning FastAPI hiện hữu.

## 5. Rủi ro và vấn đề tồn đọng

1. Git CLI trên máy đang không dùng được vì thiếu macOS Command Line Tools.
   Việc này không ảnh hưởng kết quả test hoặc migration, nhưng nên sửa môi trường
   để quy trình review/commit dùng được `git status` và `git diff` bình thường.
2. 16 file tracked có thay đổi tồn tại ngoài phạm vi GAP-07C đã được giữ nguyên.
   Cần review riêng trước khi commit chung.
3. Khung giờ làm việc trong `business_hours` không được thay đổi hay thiết kế lại
   trong task này. Regression xác nhận trigger chấp nhận đúng deadline mà luồng
   Reopen hiện hành tính; logic lịch làm việc rộng hơn vẫn thuộc phạm vi riêng.
4. Unique key hiện hành của `sla_events` là `(conversation_id, kind)`. Bản sửa
   bảo toàn nguyên vẹn các event cũ theo yêu cầu và không thay đổi mô hình lịch
   sử; việc hỗ trợ nhiều event cùng kind qua nhiều phiên là thay đổi schema ngoài
   GAP-07C.

## 6. Kết luận

**GAP-07C: Fixed & Verified.**

Migration mới chỉ nới trigger cho transition Reopen hợp lệ, giữ nguyên chốt
chống kéo dài deadline trong chu kỳ Open/Pending. Bằng chứng PostgreSQL thật cho
thấy deadline mới được lưu, SLA monitor không tạo false breach, lịch sử SLA cũ
không bị thay đổi, và toàn bộ test chuyên biệt cùng nhóm regression hiện hữu đều
PASS, không skipped.

---

---

## Phần 5: Báo Cáo Kiểm Chứng Kỹ Thuật (Task-Verify-01 Report)

# BÁO CÁO KIỂM CHỨNG KỸ THUẬT: TASK-VERIFY-01
## XÁC MINH ẢNH HƯỞNG CỦA TRIGGER `prevent_sla_deadline_reset` KHI REOPEN HỘI THOẠI

- **Mã nhiệm vụ:** `TASK-VERIFY-01` (Implementation Backlog v1.1)
- **Yêu cầu liên quan:** FR-11 (AC-11.3), FR-24 (AC-24.1), QR-06
- **Mã vấn đề:** `GAP-07C`
- **Ngày thực hiện:** 07/11/2026
- **Người thực hiện:** Antigravity Engine (Advanced Agentic Pair-Programmer)
- **Phân loại kết quả:** **`CONFIRMED BUG`** (Đã xác minh và tái hiện 100% bằng chứng thực thi)

---

## 1. THÔNG TIN MÔI TRƯỜNG KIỂM THỬ (TEST ENVIRONMENT)

Quá trình kiểm chứng được thực thi trên môi trường cơ sở dữ liệu độc lập, hoàn toàn cách ly với cơ sở dữ liệu thật, tuân thủ nghiêm ngặt chỉ thị an toàn:

- **Hệ quản trị CSDL:** PostgreSQL 16.15 (Debian 16.15-1.pgdg12+2) kèm phần mở rộng `pgvector` (`pg16`), `uuid-ossp`, `pg_trgm`.
- **Hạ tầng thực thi:** Docker container `marketing-agent-db-1` trên máy trạm lập trình macOS (Apple Silicon aarch64).
- **Cổng kết nối kiểm thử:** `127.0.0.1:5433` (cổng dành riêng cho test runner theo quy ước tại `tests/conftest.py`).
- **Tên CSDL kiểm thử độc lập:** `kt_verify_reopen_sla` (được tạo mới hoàn toàn từ CSDL quản trị `postgres` cho lượt kiểm thử và tự động drop sau khi hoàn tất).
- **Mức độ di trú:** Áp dụng đầy đủ `agent/schema.sql` và **toàn bộ 38 migrations** hiện hành (`0001_account_aware_foundation.sql` đến `0038_cong_viec_van_chuyen.sql`) thông qua `agent.migrations.runner.apply_all`.
- **Tài khoản thực thi:** `agent` (tài khoản test cục bộ không chứa mật khẩu hay thông tin thực).

---

## 2. KẾT QUẢ KIỂM TRA HIỆN TRẠNG MÃ NGUỒN & SCHEMA

### 2.1. Nguồn gốc Trigger trong CSDL (`0005_routing_sla.sql`)
Hàm và trigger được khởi tạo tại file migration `agent/migrations/versions/0005_routing_sla.sql` (dòng 168–186):

```sql
CREATE OR REPLACE FUNCTION prevent_sla_deadline_reset()
RETURNS trigger AS $$
BEGIN
    IF OLD.first_response_due_at IS NOT NULL
       AND NEW.first_response_due_at IS DISTINCT FROM OLD.first_response_due_at THEN
        NEW.first_response_due_at := OLD.first_response_due_at;
    END IF;
    IF OLD.resolution_due_at IS NOT NULL
       AND NEW.resolution_due_at IS DISTINCT FROM OLD.resolution_due_at THEN
        NEW.resolution_due_at := OLD.resolution_due_at;
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_sla_deadline_reset ON conversations;
CREATE TRIGGER trg_prevent_sla_deadline_reset
BEFORE UPDATE ON conversations
FOR EACH ROW EXECUTE FUNCTION prevent_sla_deadline_reset();
```

### 2.2. Kiểm tra các Migration kế tiếp
Rà soát toàn bộ 33 migration tiếp theo (`0006` đến `0038`):
- Không có bất kỳ migration nào chỉnh sửa hoặc thay thế hàm `prevent_sla_deadline_reset()` hoặc trigger `trg_prevent_sla_deadline_reset`.
- Kết quả truy vấn `pg_trigger` và `pg_proc` trực tiếp trên CSDL `kt_verify_reopen_sla` sau khi chạy hết 38 migrations xác nhận trigger này đang hoạt động với nguyên văn định nghĩa trên bảng `conversations`.

### 2.3. Luồng Reopen hiện hành trong Code (`agent/omnichannel/giai_quyet.py`)
Tại hàm `mo_lai_neu_da_giai_quyet()` (dòng 96–115):

```python
async def mo_lai_neu_da_giai_quyet(cid: UUID) -> bool:
    """
    Khách nhắn tiếp vào hội thoại đã giải quyết: mở lại, trả cho agent.
    Lượt phục vụ MỚI: hạn SLA tính lại từ bây giờ, first_responded_at xoá
    để đo phản hồi của lượt này.
    """
    r = await db.fetchrow(
        """
        UPDATE conversations SET
            state = 'open', status = 'auto', mode = 'auto', outcome = NULL,
            resolved_at = NULL, first_responded_at = NULL,
            first_response_due_at = (
                SELECT now() + p.first_response_minutes * interval '1 minute'
                FROM sla_policies p WHERE p.active AND p.priority = 'normal'
                  AND (p.account_id = conversations.account_id OR p.account_id IS NULL)
                ORDER BY (p.account_id = conversations.account_id) DESC LIMIT 1),
            resolution_due_at = (
                SELECT now() + p.resolution_minutes * interval '1 minute'
                FROM sla_policies p WHERE p.active AND p.priority = 'normal'
                  AND (p.account_id = conversations.account_id OR p.account_id IS NULL)
                ORDER BY (p.account_id = conversations.account_id) DESC LIMIT 1),
            version = version + 1, updated_at = now()
        WHERE id = $1 AND state = 'resolved'
        RETURNING id
        """, cid)
    return r is not None
```

**Nhận định phân tích tĩnh:**
Mặc dù lập trình viên đã viết câu lệnh SQL rất rõ ràng: gán lại `first_response_due_at = now() + interval` cho lượt phục vụ mới, nhưng vì trigger `trg_prevent_sla_deadline_reset` là trigger `BEFORE UPDATE`, nó chặn ngay lệnh cập nhật này:
- `OLD.first_response_due_at` mang giá trị của phiên phục vụ trước (quá khứ).
- `NEW.first_response_due_at` là giá trị tương lai (`now() + interval`).
- Trigger thấy `NEW IS DISTINCT FROM OLD` và `OLD IS NOT NULL` $\rightarrow$ Nó âm thầm ghi đè: `NEW.first_response_due_at := OLD.first_response_due_at`.
- Câu lệnh `UPDATE` vẫn thực thi thành công (trả về `RETURNING id`), `state` đổi sang `open`, `first_responded_at` bị xóa về `NULL`, nhưng **deadline SLA vẫn là mốc thời gian quá khứ của phiên trước**.

---

## 3. THIẾT KẾ KỊCH BẢN KIỂM CHỨNG & THỰC THI (EXECUTION EVIDENCE)

### 3.1. Kịch bản Kiểm thử
1. **Khởi tạo:** Tạo tài khoản kênh `webchat`, khách hàng `Khach Hang Test`, chính sách SLA `normal` (First Response: 15 phút, Resolution: 60 phút).
2. **Phiên 1 (Quá khứ 2 giờ trước):** Tạo hội thoại lúc `now() - 2 hours`, `first_response_due_at` = 105 phút trước, `first_responded_at` = 115 phút trước.
3. **Resolve:** Gọi `giai_quyet.giai_quyet()` để đóng hội thoại (`state = 'resolved'`).
4. **Khách nhắn tin mới $\rightarrow$ Reopen:** Gọi `giai_quyet.mo_lai_neu_da_giai_quyet(conv_id)` theo đúng luồng khi webhook nhận tin từ khách đã đóng.
5. **Đo đạc:** Truy vấn CSDL đọc giá trị `first_response_due_at`, `state`, `mode`, `first_responded_at`.
6. **Kiểm tra SLA Monitor:** Kích hoạt `SlaMonitor.scan_once()` để kiểm tra xem hệ thống có tự sinh sự kiện `first_response_breached` sai hay không.

### 3.2. Log Thực thi Thực tế từ Terminal

```text
[*] Kết nối CSDL quản trị postgresql://agent:agent@127.0.0.1:5433/postgres để tạo CSDL test độc lập 'kt_verify_reopen_sla'...
[+] Đã tạo CSDL test độc lập 'kt_verify_reopen_sla' thành công.
[*] Nạp schema và áp dụng toàn bộ migration vào 'kt_verify_reopen_sla'...
[+] Đã áp dụng toàn bộ migrations (0001 đến 0038) thành công.

--- THÔNG TIN TRIGGER HIỆN HÀNH TRÊN BẢNG conversations ---
Trigger Name: trg_prevent_sla_deadline_reset
Table: conversations
Function: prevent_sla_deadline_reset
Definition:
BEGIN
    IF OLD.first_response_due_at IS NOT NULL
       AND NEW.first_response_due_at IS DISTINCT FROM OLD.first_response_due_at THEN
        NEW.first_response_due_at := OLD.first_response_due_at;
    END IF;
    IF OLD.resolution_due_at IS NOT NULL
       AND NEW.resolution_due_at IS DISTINCT FROM OLD.resolution_due_at THEN
        NEW.resolution_due_at := OLD.resolution_due_at;
    END IF;
    RETURN NEW;
END

--- BƯỚC 1: KHỞI TẠO DỮ LIỆU BAN ĐẦU ---
Hội thoại tạo ban đầu (quá khứ 2 giờ trước):
  - state: open
  - first_response_due_at: 2026-11-07 06:42:33.193746+00:00
  - resolution_due_at: 2026-11-07 07:27:33.193746+00:00

--- BƯỚC 2: GIẢI QUYẾT HỘI THOẠI (RESOLVE) ---
Sau khi Resolve:
  - state: resolved
  - resolved_at: 2026-11-07 08:27:33.228775+00:00
  - first_response_due_at (vẫn lưu): 2026-11-07 06:42:33.193746+00:00

--- BƯỚC 3: KHÁCH NHẮN TIN MỚI -> THỰC HIỆN REOPEN ---
Kết quả gọi mo_lai_neu_da_giai_quyet: True
Trạng thái sau Reopen:
  - state: open (kỳ vọng: 'open')
  - status: auto (kỳ vọng: 'auto')
  - mode: auto (kỳ vọng: 'auto')
  - resolved_at: None (kỳ vọng: None)
  - first_responded_at: None (kỳ vọng: None)
Kiểm tra Deadline SLA:
  - Deadline cũ (quá khứ): 2026-11-07 06:42:33.193746+00:00
  - Deadline kỳ vọng mới: now() + 15 phút (> 2026-11-07T08:27:33.239995+00:00)
  - Deadline thực tế trong CSDL sau Reopen: 2026-11-07 06:42:33.193746+00:00

=> KẾT QUẢ SO SÁNH DEADLINE:
   [!] CONFIRMED BUG: Deadline thực tế BỊ TRIGGER GIỮ NGUYÊN GIÁ TRỊ CŨ QUÁ KHỨ!
       Giá trị cũ: 2026-11-07 06:42:33.193746+00:00
       Giá trị sau reopen: 2026-11-07 06:42:33.193746+00:00
       Trigger trg_prevent_sla_deadline_reset đã chặn cập nhật deadline mới!

--- BƯỚC 4: KIỂM TRA QUÉT VI PHẠM SLA MONITOR ---
Kết quả SLA Monitor scan_once: {'first_response': 1, 'resolution': 1}
   [!] PHÁT HIỆN SỰ KIỆN VI PHẠM SAI (FALSE BREACH):
       ID: 1
       Kind: first_response_breached
       Due at: 2026-11-07 06:42:33.193746+00:00
       Created at: 2026-11-07 08:27:33.243390+00:00
       Hội thoại vừa mở lại cho tin nhắn mới, nhưng ngay lập tức bị tính là vi phạm First Response SLA!

[*] Dọn dẹp: Xóa CSDL test độc lập 'kt_verify_reopen_sla'...
[+] Đã xóa CSDL test 'kt_verify_reopen_sla' an toàn.
```

---

## 4. BẢNG ĐỐI CHIẾU THỰC TẾ CHI TIẾT

| Chỉ số / Trường dữ liệu | Giá trị trước Reopen (Resolved) | Giá trị Kỳ vọng Nghiệp vụ sau Reopen | Giá trị Thực tế Ghi nhận trong CSDL | Đánh giá Sai lệch |
|---|---|---|---|:---:|
| **`conversations.state`** | `resolved` | `open` | `open` | Đạt |
| **`conversations.status`** | `closed` | `auto` | `auto` | Đạt |
| **`conversations.mode`** | `auto` | `auto` | `auto` | Đạt |
| **`conversations.resolved_at`** | `08:27:33.228` | `NULL` | `NULL` | Đạt |
| **`conversations.first_responded_at`** | `06:32:33.193` | `NULL` | `NULL` | Đạt |
| **`first_response_due_at`** | **`06:42:33.193`** *(quá khứ 1h45m)* | **`08:42:33`** *(now + 15m)* | **`06:42:33.193`** *(quá khứ)* | **LỖI NGHIÊM TRỌNG** *(Bị trigger đè)* |
| **`resolution_due_at`** | **`07:27:33.193`** *(quá khứ 1h00m)* | **`09:27:33`** *(now + 60m)* | **`07:27:33.193`** *(quá khứ)* | **LỖI NGHIÊM TRỌNG** *(Bị trigger đè)* |
| **Sự kiện `sla_events` phát sinh** | Không | Không có breach | Tạo bản ghi **`first_response_breached`** (due_at: `06:42:33`) | **SAI NGHIỆP VỤ (False Breach)** |

---

## 5. PHÂN LOẠI KẾT LUẬN & ĐÁNH GIÁ MỨC ĐỘ ẢNH HƯỞNG

### 5.1. Phân loại Kết quả
> [!CAUTION]
> **KẾT LUẬN: `CONFIRMED BUG` (Lỗi logic dữ liệu CSDL được xác nhận 100%)**

### 5.2. Cơ chế Gây lỗi
1. Mục đích thiết kế ban đầu của trigger `prevent_sla_deadline_reset` là **chống gian lận SLA**: ngăn nhân viên hoặc tiến trình cập nhật tin nhắn đẩy lùi deadline của một hội thoại đang chờ xử lý (`state = 'open'`).
2. Tuy nhiên, hàm trigger thiếu điều kiện kiểm tra trạng thái cũ `OLD.state`. Khi hội thoại đã ở trạng thái `resolved` hoặc `closed`, khách hàng quay lại mở ra một **phiên tương tác hoàn toàn mới (New Session)**.
3. Việc trigger cưỡng bức giữ lại deadline cũ kết hợp với việc `first_responded_at` bị xóa về `NULL` khiến câu truy vấn của `SlaMonitor`:
   ```sql
   WHERE conversation.state IN ('open', 'pending')
     AND conversation.first_responded_at IS NULL
     AND conversation.first_response_due_at < now()
   ```
   ngay lập tức thỏa mãn. Kết quả là nhân viên CSKH hoặc AI Agent bị gán nhãn "Vi phạm SLA phản hồi đầu tiên" ngay tại giây thứ 0 sau khi khách gửi tin nhắn Reopen.

---

## 6. ĐỀ XUẤT THỰC THI CHO TASK-CODE-01 & REGRESSION TESTS

### 6.1. Khẳng định Cần thực thi TASK-CODE-01
- **Khuyến nghị:** **BẮT BUỘC THỰC HIỆN `TASK-CODE-01`**. Mức ưu tiên **`P0`**.
- Không thể nghiệm thu AC-11.3 và FR-24 nếu không sửa trigger này.

### 6.2. Đề xuất Bản sửa (Migration Patch)
Tạo file migration mới `agent/migrations/versions/0039_fix_sla_reopen_trigger.sql` (hoặc số thứ tự kế tiếp sau `0038`):

```sql
-- Sửa hàm prevent_sla_deadline_reset: chỉ bảo lưu deadline khi hội thoại đang mở/chờ.
-- Khi hội thoại đang ở 'resolved' hoặc 'closed' mà mở lại, cho phép thiết lập deadline mới.

CREATE OR REPLACE FUNCTION prevent_sla_deadline_reset()
RETURNS trigger AS $$
BEGIN
    -- Chỉ ngăn chặn đổi deadline nếu hội thoại cũ ĐANG MỞ hoặc ĐANG CHỜ (tránh gian lận SLA)
    IF OLD.state NOT IN ('resolved', 'closed') THEN
        IF OLD.first_response_due_at IS NOT NULL
           AND NEW.first_response_due_at IS DISTINCT FROM OLD.first_response_due_at THEN
            NEW.first_response_due_at := OLD.first_response_due_at;
        END IF;
        IF OLD.resolution_due_at IS NOT NULL
           AND NEW.resolution_due_at IS DISTINCT FROM OLD.resolution_due_at THEN
            NEW.resolution_due_at := OLD.resolution_due_at;
        END IF;
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;
```

### 6.3. Danh mục Ca kiểm thử Hồi quy Cần thiết (Regression Test Suite)
Khi triển khai `TASK-TEST-01`, bộ test phải bao quát 3 kịch bản:

1. **Ca 1 (Reopen từ Resolved - Happy Path):**
   - Given: Hội thoại ở trạng thái `resolved` có deadline cũ trong quá khứ.
   - When: Khách gửi tin nhắn mới $\rightarrow$ gọi `mo_lai_neu_da_giai_quyet()`.
   - Then: `first_response_due_at` và `resolution_due_at` được cập nhật giá trị tương lai mới (`> now()`); `SlaMonitor.scan_once()` không tạo bản ghi breach nào.

2. **Ca 2 (Chống gian lận SLA khi đang Open - Negative Path):**
   - Given: Hội thoại đang ở `state = 'open'` có `first_response_due_at = T1`.
   - When: Một câu lệnh `UPDATE conversations SET first_response_due_at = T2 WHERE id = ...` cố tình đẩy lùi deadline.
   - Then: Trigger can thiệp, giữ nguyên `first_response_due_at = T1`.

3. **Ca 3 (Reopen từ Closed):**
   - Given: Hội thoại ở trạng thái `closed`.
   - When: Mở lại hội thoại kèm deadline mới.
   - Then: CSDL chấp nhận deadline mới thành công.

---
*Báo cáo được lưu trữ chính thức tại [`docs/requirements-audit/verify_01_reopen_sla_report.md`](file:///Users/huynhlehoaibao/Documents/AIAgent_mar/docs/requirements-audit/verify_01_reopen_sla_report.md).*
