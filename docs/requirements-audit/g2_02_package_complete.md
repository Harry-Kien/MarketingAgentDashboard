# Gói Hồ Sơ Hoàn Chỉnh Nhóm G2-02 (Cảnh Báo & Thu Hồi Batch Stale Tự Động)

> Tài liệu hợp nhất toàn bộ quy trình từ căn chỉnh BA, đề xuất thay đổi và biên bản bàn giao cho nhóm yêu cầu G2-02.

---

## Phần 1: BA Alignment

# BÁO CÁO ĐỐI CHIẾU NGHIỆP VỤ: PENDING ACTION & RESOLVE GUARD
## ĐỐI CHIẾU QUY TẮC CHẶN KẾT THÚC HỘI THOẠI KHI CÒN CÔNG VIỆC CHƯA HOÀN THÀNH (GAP-07B)

- **Mã nhiệm vụ:** `TASK G2-02-BA`
- **Yêu cầu liên quan:** FR-11 (AC-11.2), FR-23 (AC-23.2, AC-23.3), FR-19 (AC-19.3), FR-20 (AC-20.4), QR-14, DFR-11
- **Vấn đề kiểm toán:** `GAP-07B` (Thiếu chốt chặn Resolve khi còn công việc/Pending Action dở dang)
- **Tài liệu tham chiếu:** `Phân tích nghiệp vụ khoá luận (6).pdf` (Bản thảo BA gốc), `requirements_source_register.csv`, `implementation_backlog_v1_1.md`
- **Mã nguồn/Migration đối chiếu:** `agent/migrations/versions/0022_cong_viec.sql`, `0036_cong_viec_nguon_tu_dong.sql`, `0038_cong_viec_van_chuyen.sql`, `agent/core/cong_viec.py`, `agent/omnichannel/giai_quyet.py`, `agent/api/hoi_thoai_nhan.py`
- **Vai trò:** Business Analyst (Chuyên viên Phân tích Nghiệp vụ)
- **Trạng thái:** Bản phân tích đối chiếu nghiệp vụ chính thức (Chưa sửa Baseline đã phê duyệt)

---

## 1. TỔNG QUAN VẤN ĐỀ & PHẠM VI ĐỐI CHIẾU

Trong kiến trúc vận hành CSKH đa kênh của hệ thống `AIAgent_mar`, việc "Kết thúc hội thoại" (Resolve) đánh dấu thời điểm hoàn tất trách nhiệm phục vụ của nhân viên đối với một phiên tương tác.

Tuy nhiên, kết quả kiểm toán mã nguồn tại `agent/omnichannel/giai_quyet.py:42-46` cho thấy:
- Hàm `giai_quyet()` hiện tại chỉ thực thi một câu lệnh duy nhất:
  ```sql
  UPDATE conversations SET state = 'resolved', status = 'closed', outcome = 'resolved', resolved_at = now() ...
  ```
  mà **hoàn toàn không kiểm tra xem hội thoại có còn công việc dở dang trong bảng `cong_viec` hay không**.
- Bất kể nhân viên đang có task "Sửa đơn hàng", "Hủy đơn hàng", "Gọi lại cho khách", hay task tự động do AI chuyển người (`tao_tu_chuyen_nguoi`) đang ở trạng thái `moi` (chưa xử lý) hoặc `dang_lam` (đang xử lý), nhân viên vẫn có thể bấm Resolve thành công.
- Hậu quả: Hội thoại bị đóng, lượt giao kết thúc, khách hàng nhận tin nhắn mời chấm CSAT, trong khi yêu cầu của khách hàng (sửa đơn, hủy đơn, thắc mắc phức tạp) bị bỏ quên hoàn toàn trong hệ thống mà không ai tiếp tục xử lý.

Tài liệu này thực hiện đối chiếu chi tiết 7 câu hỏi nghiệp vụ cốt lõi từ tài liệu BA gốc (`Phân tích nghiệp vụ khoá luận (6).pdf`) và đối soát với cấu trúc CSDL thực tế để thiết lập giải pháp Resolve Guard chuẩn xác.

---

## 2. TRẢ LỜI CHI TIẾT 7 CÂU HỎI NGHIỆP VỤ CỐT LÕI

### 2.1. Điều kiện nào cho phép nhân viên Resolve hội thoại?

#### Căn cứ tài liệu gốc:
- **`FR-11` (Trang 142):**
  > "Hệ thống phải cho phép nhân viên có quyền gửi phản hồi trong Manual Mode và **chỉ Resolve Conversation theo luồng thông thường khi không còn Pending Action bắt buộc chưa hoàn tất và không còn yêu cầu khách chưa được giải quyết**."
- **`AC-11.2` (Trang 142):**
  > *Given:* Còn Pending Action chưa hoàn tất.  
  > *When:* Nhân viên yêu cầu Resolve.  
  > *Then:* Từ chối Resolve theo luồng thông thường.
- **Use Case `UC-08 – Kết thúc phiên hỗ trợ thủ công` (Trang 44–45):**
  > - *Preconditions (Trang 44):* Conversation ở Manual Mode; nhân viên có quyền; không có Pending Action bắt buộc chưa hoàn tất.  
  > - *Main Flow Bước 2 (Trang 44):* Nhân viên hoàn thành những công việc bắt buộc và bảo đảm không còn câu hỏi khách chưa được giải quyết.  
  > - *Main Flow Bước 4 (Trang 45):* Hệ thống kiểm tra quyền, trạng thái Pending Actions và yêu cầu chưa hoàn tất.  
  > - *Main Flow Bước 5 (Trang 45):* Hệ thống chuyển Conversation sang Resolved và lưu lịch sử thay đổi.
- **Event–Response Table `EVT-05` (Trang 72–73):**
  > - Khi đủ điều kiện (không còn Pending Action và không còn câu hỏi chưa giải quyết) $\rightarrow$ Chuyển Conversation sang Resolved, lưu lịch sử, không kích hoạt AI gửi phản hồi ngay.  
  > - Khi còn Pending Action chưa hoàn tất hoặc câu hỏi chưa giải quyết $\rightarrow$ Từ chối Resolve theo luồng thông thường; giữ Conversation ở trạng thái Open–Manual.

#### Làm rõ Nghiệp vụ:
Để một hội thoại được phép chuyển sang `state = 'resolved'`, hệ thống bắt buộc phải thỏa mãn đồng thời **4 điều kiện tiên quyết (Preconditions)**:
1. **Trạng thái hội thoại:** Hội thoại đang ở trạng thái hợp lệ để đóng (`state IN ('open', 'pending')`).
2. **Thẩm quyền người thao tác:** Nhân viên có quyền xử lý hội thoại (`can_quyen("hoi_thoai.nhan")` hoặc tương đương) và đang phụ trách hội thoại (hoặc là Quản lý/Admin).
3. **Chốt chặn công việc (Resolve Task Guard):** **KHÔNG CÒN BẤT KỲ CÔNG VIỆC NÀO** liên kết với hội thoại (`cong_viec.conversation_id = cid`) đang ở trạng thái chưa hoàn thành (`trang_thai IN ('moi', 'dang_lam')`).
4. **Trách nhiệm phản hồi:** Tin nhắn cuối cùng của khách hàng đã có phản hồi (không còn câu hỏi mở bị bỏ lửng).

---

### 2.2. Những công việc hoặc Pending Action nào bắt buộc phải hoàn thành trước khi Resolve?

#### Căn cứ tài liệu gốc & Schema CSDL:
Trong tài liệu BA, khái niệm "Pending Action" và "công việc bắt buộc" được hiện thực hóa thống nhất trong CSDL thông qua bảng **`cong_viec`** (tạo tại migration `0022_cong_viec.sql`, mở rộng tại `0036` và `0038`).

Bảng `cong_viec` quản lý 4 nhóm nguồn công việc phát sinh trong vòng đời hội thoại:
1. **Nguồn `agent` (AI Handover Task):**
   - Khi AI Agent vượt ngưỡng tự tin, gặp trường hợp nhạy cảm, hoặc khách yêu cầu gặp người $\rightarrow$ Hệ thống tự động tạo một bản ghi `cong_viec` với `nguon = 'agent'`, `uu_tien = 'cao'`, `tieu_de = 'Khách cần người trả lời: [Tên khách]'` (`agent/core/cong_viec.py:110-150`).
   - Đây là Pending Action cốt lõi yêu cầu nhân viên phải vào tiếp quản, đọc ngữ cảnh và trả lời khách.
2. **Nguồn `nguoi` (Manual Staff Task):**
   - Công việc do chính nhân viên hoặc quản lý chủ động tạo trong quá trình chat (ví dụ: "Gọi điện xác nhận địa chỉ giao hàng", "Kiểm tra màu sắc với bộ phận kho").
3. **Nguồn `tu_dong` (Rule-Engine Task):**
   - Công việc sinh ra do quy tắc tự động của cửa hàng (`0036_cong_viec_nguon_tu_dong.sql`, `agent/omnichannel/tu_dong.py`).
4. **Nguồn `van_chuyen` (Shipping Exception Task):**
   - Công việc phát sinh khi đơn vị vận chuyển (GHN) thông báo sự cố giao hàng (giao thất bại, lạc đơn, sai thông tin kiện hàng) cần nhân viên liên hệ xử lý (`0038_cong_viec_van_chuyen.sql`).

#### Quy tắc xác định:
Tất cả các bản ghi trong bảng `cong_viec` có trường `conversation_id = conversation.id` đều thuộc phạm vi kiểm tra của Resolve Guard. **Không có ngoại lệ bỏ qua theo nguồn**: Dù việc do AI tạo, do nhân viên tạo, do hệ thống tự sinh hay do vận chuyển báo về, chừng nào việc đó chưa đóng thì hội thoại không được phép Resolve.

---

### 2.3. Trạng thái `moi`, `dang_lam`, `xong`, `huy` được định nghĩa như thế nào trong database và nghiệp vụ?

Căn cứ định nghĩa CSDL tại `agent/migrations/versions/0022_cong_viec.sql:46-52` và module nghiệp vụ `agent/core/cong_viec.py:32-46`:

```sql
CHECK (trang_thai IN ('moi', 'dang_lam', 'xong', 'huy'))
CHECK ((trang_thai = 'xong') = (xong_luc IS NOT NULL))
```

Bảng phân tích ngữ nghĩa nghiệp vụ và phân nhóm trạng thái:

| Trạng thái CSDL | Tên hiển thị UI | Ngữ nghĩa Nghiệp vụ | Phân nhóm Resolve Guard | Ràng buộc Dữ liệu liên quan |
|---|---|---|:---:|---|
| **`moi`** | Mới | Công việc mới được tạo lập (chưa phân công hoặc nhân viên chưa bắt tay thực hiện). Yêu cầu chưa hề được giải quyết. | **CHƯA HOÀN TẤT** *(Chặn Resolve)* | `xong_luc IS NULL` |
| **`dang_lam`** | Đang làm | Nhân viên đã tiếp nhận và đang trong tiến trình xử lý (ví dụ: đang gọi điện, đang thao tác trên ERPNext, đang đợi bộ phận kho trả lời). | **CHƯA HOÀN TẤT** *(Chặn Resolve)* | `xong_luc IS NULL` |
| **`xong`** | Xong | Công việc đã được xử lý hoàn tất thành công. Mục tiêu của công việc đã đạt được. | **ĐÃ HOÀN TẤT** *(Cho phép Resolve)* | `xong_luc IS NOT NULL` (Bắt buộc phải có timestamp hoàn thành) |
| **`huy`** | Đã hủy | Công việc bị hủy bỏ hợp lệ (ví dụ: khách đổi ý không cần xử lý nữa; công việc tạo nhầm; hoặc vấn đề đã được giải quyết qua luồng khác). Công việc không còn đòi hỏi hành động tiếp theo. | **ĐÃ ĐÓNG / HOÀN TẤT** *(Cho phép Resolve)* | Không đòi hỏi hành động thêm từ nhân viên |

> [!IMPORTANT]
> **Định nghĩa Chốt chặn Nghiệp vụ (Resolve Guard Rule):**  
> Hội thoại chỉ được phép Resolve khi:
> $$\forall \text{ task } \in \text{cong\_viec}(\text{conversation\_id} = cid): \text{task.trang\_thai} \in \{\text{'xong'}, \text{'huy'}\}$$
> Tức là **hoàn toàn không tồn tại** công việc nào có `trang_thai IN ('moi', 'dang_lam')` (`CHUA_XONG`).

---

### 2.4. Nếu công việc chưa hoàn thành mà nhân viên bấm Resolve, hệ thống phải xử lý như thế nào?

#### Căn cứ tài liệu gốc:
- `AC-11.2`: "Từ chối Resolve theo luồng thông thường."
- `EVT-05` (Trang 73): "Từ chối Resolve theo luồng thông thường; giữ Conversation ở trạng thái Open–Manual."

#### Đặc tả Hành vi Hệ thống Chuẩn hóa:
Khi nhân viên bấm nút "Resolve" trên Dashboard đối với hội thoại còn task `moi` hoặc `dang_lam`:
1. **Tại tầng Backend / API (`POST /api/inbox/conversations/{id}/giai-quyet`):**
   - Thực hiện kiểm tra trước (Pre-check):
     ```sql
     SELECT id, tieu_de, trang_thai FROM cong_viec 
     WHERE conversation_id = $1 AND trang_thai IN ('moi', 'dang_lam')
     ```
   - Nếu tồn tại ít nhất 1 bản ghi: **Từ chối cập nhật**, Rollback giao dịch nếu có.
   - Trả về mã lỗi HTTP **`409 Conflict`** (hoặc `400 Bad Request`) kèm payload JSON chi tiết:
     ```json
     {
       "detail": "Không thể kết thúc hội thoại: Còn công việc chưa hoàn tất.",
       "code": "CONVERSATION_HAS_PENDING_TASKS",
       "pending_tasks": [
         {
           "id": "uuid-task-1",
           "tieu_de": "Khách cần người trả lời: Chị Lan",
           "trang_thai": "moi"
         }
       ]
     }
     ```
2. **Tại tầng CSDL:**
   - Trạng thái hội thoại được giữ nguyên: `state` vẫn là `'open'`, `status` giữ nguyên, `resolved_at` giữ nguyên `NULL`.
   - Lượt giao việc (`conversation_assignments`) không bị đóng (`ended_at IS NULL`), nhân viên tiếp tục chịu trách nhiệm với hội thoại.
   - Không phát sinh sự kiện `resolution_met` trong `sla_events`.
   - Không kích hoạt gửi tin nhắn khảo sát CSAT cho khách hàng.
3. **Tại tầng Giao diện (Native Dashboard):**
   - Hiển thị thông báo cảnh báo (Toast Warning / Modal): *"Không thể đóng hội thoại: Còn công việc '[Tên công việc]' chưa hoàn thành. Vui lòng hoàn tất hoặc hủy công việc trước khi Resolve."*
   - Tự động cuộn hoặc làm nổi bật (Highlight) tab/card Công việc để nhân viên thao tác.

---

### 2.5. Có cần phân biệt thao tác Resolve thủ công và Auto-Resolve hay không?

**CÓ, BẮT BUỘC PHẢI PHÂN BIỆT RÕ RÀNG VỀ TÁC NHÂN VÀ HÀNH VI XỬ LÝ NGOẠI LỆ.**

| Tiêu chí | Resolve Thủ công (Manual Resolve) | Tự động Đóng (Auto-Resolve / Idle Timeout) |
|---|---|---|
| **Yêu cầu quy định** | `FR-11` (AC-11.2), `UC-08` | `FR-23` (AC-23.2, AC-23.3), `AF-02` (Trang 45), `EVT-13` (Trang 74) |
| **Tác nhân kích hoạt** | Nhân viên CSKH bấm nút trên giao diện Dashboard. | Background Worker quét định kỳ các hội thoại hết hạn chờ (mặc định 4 giờ). |
| **Trạng thái hội thoại áp dụng** | Thường là `Manual Mode` (`mode = 'human'`). | `Auto Mode` (`mode = 'auto'`, `state IN ('open', 'pending')`). |
| **Hành vi khi KHÔNG còn task** | Chuyển `resolved`, kết thúc assignment, gửi CSAT. | Tự động chuyển `resolved`, ghi nhận lý do "Tự động đóng do hết thời gian chờ (4 giờ)". |
| **Hành vi khi CÒN task chưa xong** | **Bị từ chối ngay lập tức**, trả về mã lỗi 409 cho nhân viên kèm danh sách việc kẹt. | **Bỏ qua không đóng**, giữ nguyên hội thoại ở `state = 'open'`; không phát sinh CSAT; phát cảnh báo quá hạn cho quản lý (`EF-04` của `UC-08`). |

> [!NOTE]
> Cả hai luồng Resolve đều chia sẻ chung một **hàm kiểm tra điều kiện cốt lõi (Guard Condition)**:
> `has_uncompleted_tasks(conversation_id) == False`.
> Tuy nhiên, luồng thủ công sẽ trả lỗi cho người dùng, còn luồng tự động sẽ bỏ qua hội thoại để tiếp tục vòng quét.

---

### 2.6. Tài liệu BA có mâu thuẫn hoặc thiếu quy tắc nghiệp vụ nào?

Qua đối chiếu toàn diện giữa các phần trong tài liệu BA gốc (`Phân tích nghiệp vụ khoá luận (6).pdf`), nhóm BA nhận định:

1. **Tính nhất quán về nguyên tắc:**
   - Tài liệu BA **hoàn toàn nhất quán** về mặt nguyên lý: Cả 5 vị trí (`AC-11.2`, `AC-23.2`, `UC-08`, `EVT-05`, `EVT-13`) đều cấm Resolve khi còn công việc/Pending Action dở dang. Không có sự mâu thuẫn giữa các Use Case.
2. **Các điểm thiếu hụt cần làm rõ (Gaps in Specification):**
   - **Thiếu ánh xạ vào thực thể CSDL:** Tài liệu BA dùng thuật ngữ trừu tượng "Pending Action" và "công việc bắt buộc", nhưng không có phần nào trong Practice #8 (Data Modeling) hay Practice #10 làm rõ rằng Pending Action chính là các bản ghi trong bảng `cong_viec` với trạng thái `moi` hoặc `dang_lam`.
   - **Chưa quy định rõ số phận của trạng thái `huy`:** Tài liệu chỉ nói "công việc chưa hoàn tất", chưa khẳng định rõ ràng rằng một công việc bị "Hủy" (`trang_thai = 'huy'`) được coi là đã đóng và không ngăn cản Resolve.
   - **Chưa định lượng cách nhận diện "câu hỏi khách chưa được giải quyết":** Trong `AC-11.2` và `AC-23.2` có vế *"hoặc câu hỏi khách chưa được giải quyết"*. Trong code hiện tại, khi khách hỏi mà AI không trả lời được thì AI đã tạo một task trong `cong_viec` (`tao_tu_chuyen_nguoi`). Do đó, việc kiểm tra bảng `cong_viec` chính là cơ chế hữu hiệu nhất để bảo đảm câu hỏi của khách không bị bỏ rơi.

---

### 2.7. Quy tắc này liên quan thế nào đến yêu cầu sửa/hủy đơn đang chờ nhân viên xử lý?

Mối liên hệ giữa Resolve Guard và luồng Sửa/Hủy đơn hàng (`UC-15`, `UC-16`, `FR-19`, `FR-20`, `DFR-11`):

1. **Chu trình nghiệp vụ Sửa/Hủy đơn hàng:**
   - Khi khách hàng nhắn tin yêu cầu sửa hoặc hủy đơn hàng trên kênh chat:
     1. AI Agent tiếp nhận và nhận diện ý định.
     2. Hệ thống tạo một Pending Action trong bảng `cong_viec` (ví dụ: `tieu_de = 'Yêu cầu hủy đơn hàng #SO-2026-001'`).
     3. Đối với hủy đơn, hệ thống cập nhật cờ `orders.yeu_cau_huy_luc = now()` để tạm khóa đơn hàng (Hold).
     4. Hội thoại được Handover sang cho nhân viên (chuyển sang `Manual Mode`).
2. **Tác dụng bảo vệ của Resolve Guard:**
   - Nhân viên CSKH sau khi nhận hội thoại bắt buộc phải mở phần mềm ERPNext (hoặc thao tác qua màn hình tích hợp) để thực hiện hủy/sửa đơn hàng thực tế trên ERP.
   - Sau khi hoàn thành, nhân viên cập nhật Pending Action sang trạng thái `xong` (hoặc `huy` nếu khách không đồng ý hủy nữa).
   - **Nếu không có Resolve Guard:** Nhân viên có thể vô tình bấm "Resolve" trên màn hình chat ngay khi mới đọc tin nhắn mà quên thao tác trên ERPNext. Đơn hàng vẫn bị treo cờ `yeu_cau_huy_luc`, kho không xuất hàng được, và việc hủy đơn trên ERPNext bị lãng quên.
   - **Khi có Resolve Guard:** Thao tác bấm Resolve bị chặn đứng ngay lập tức với thông báo: *"Còn công việc 'Yêu cầu hủy đơn hàng #SO-2026-001' chưa hoàn tất"*. Nhân viên buộc phải xử lý dứt điểm đơn hàng mới được phép đóng hội thoại.
   - Cơ chế này hiện thực hóa đúng yêu cầu của `DFR-11`: *"Tạo Pending Action và Handover cho yêu cầu sửa/hủy; không tự đánh dấu hoàn tất khi chưa có kết quả nghiệp vụ."*

---

## 3. MA TRẬN ĐỐI CHIẾU HIỆN TRẠNG BA VS SOURCE CODE & DATABASE

| Thành phần Kiểm toán | Quy định trong Tài liệu BA | Hiện trạng trong Source Code / DB | Đánh giá Trạng thái | Hành động Cần thiết |
|---|---|---|:---:|---|
| **Chốt chặn hàm `giai_quyet()`** | `FR-11 (AC-11.2)`: Từ chối Resolve khi còn Pending Action chưa xong. | `agent/omnichannel/giai_quyet.py:38-46` UPDATE trực tiếp `state = 'resolved'` không kiểm tra `cong_viec`. | ❌ **LỖI LOGIC (`GAP-07B`)** | Sửa `giai_quyet()` kiểm tra `cong_viec` (`TASK-CODE-04`). |
| **Mã phản hồi API Resolve** | `AC-11.2`: Từ chối theo luồng thông thường. | `agent/api/hoi_thoai_nhan.py:109-112` chỉ kiểm tra 404 hội thoại tồn tại, sau đó gọi `giai_quyet()`. | ❌ **THIẾU KIỂM TRA** | Bổ sung bắt lỗi 409 Conflict khi còn task mở. |
| **Phân loại trạng thái Task** | Bảng 16.1 & UC-08: Phân biệt việc hoàn thành và chưa hoàn thành. | `agent/core/cong_viec.py:46`: `CHUA_XONG = ('moi', 'dang_lam')`. | ✅ **KHỚP 100%** | Tái sử dụng hằng số `CHUA_XONG` trong câu query chặn. |
| **Chốt chặn Auto-Resolve** | `AC-23.2`: Không tự Resolve khi còn Pending Action hoặc câu hỏi mở. | Chưa có background worker Auto-Resolve trong codebase (`TASK-CODE-05`). | ⚠️ **CHƯA TRIỂN KHAI** | Khi triển khai `TASK-CODE-05`, bắt buộc tích hợp điều kiện này. |
| **Bảo vệ luồng Sửa/Hủy đơn** | `DFR-11`, `AC-19.3`, `AC-20.4`: Không đánh dấu xong khi chưa có kết quả ERP. | Cờ `yeu_cau_huy_luc` được gán nhưng không chặn Resolve trên giao diện chat. | ❌ **HỔNG NGHIỆP VỤ** | Resolve Guard sẽ bảo vệ tự nhiên luồng này qua Pending Action. |

---

## 4. KẾT LUẬN CỦA BUSINESS ANALYST

1. Yêu cầu chặn Resolve khi còn công việc dở dang là **nguyên tắc nghiệp vụ cốt lõi, hoàn toàn đúng đắn và đã có sẵn trong tài liệu BA gốc** (`AC-11.2`, `AC-23.2`, `UC-08`, `EVT-05`).
2. Hiện tượng lỗi `GAP-07B` xuất phát từ việc **mã nguồn Backend (`giai_quyet.py`) bị thiếu bước truy vấn kiểm tra CSDL bảng `cong_viec`**, chứ không phải do tài liệu BA bị sai.
3. Việc khắc phục `GAP-07B` thông qua [`TASK-CODE-04`](file:///Users/huynhlehoaibao/Documents/AIAgent_mar/docs/requirements-audit/implementation_backlog_v1_1.md#task-code-04) là hoàn toàn cấp thiết, giúp bảo vệ tính toàn vẹn của dữ liệu giao dịch và luồng xử lý đơn hàng.
4. Tài liệu BA chỉ cần bổ sung diễn giải kỹ thuật làm rõ ánh xạ giữa "Pending Action" và bảng `cong_viec`, đồng thời quy định cụ thể mã phản hồi HTTP 409 khi bị chặn.

---

## Phần 2: BA Change Proposal

# ĐỀ XUẤT CHỈNH SỬA TÀI LIỆU PHÂN TÍCH NGHIỆP VỤ (BA CHANGE PROPOSAL)
## BỔ SUNG ĐẶC TẢ CHỐT CHẶN RESOLVE KHI CÒN PENDING ACTION CHƯA HOÀN THÀNH (GAP-07B)

- **Mã tài liệu:** `G2-02-BA-CHANGE-PROPOSAL`
- **Tài liệu gốc tham chiếu:** `Phân tích nghiệp vụ khoá luận (6).pdf` (Bản thảo báo cáo khóa luận 204 trang)
- **Người đề xuất:** Business Analyst
- **Ngày lập:** 07/11/2026
- **Trạng thái:** Dự thảo Đề xuất Chỉnh sửa (Proposal – Chờ người dùng cập nhật trực tiếp vào file Word/LaTeX báo cáo)

---

## 1. NGUYÊN TẮC QUẢN LÝ THAY ĐỔI TÀI LIỆU

1. **Bảo tồn Requirements Baseline:** Không thay đổi mã định danh, cấu trúc Given–When–Then của `AC-11.2` và `AC-23.2` trong Baseline Draft.
2. **Cụ thể hóa Kỹ thuật & Bổ sung Rõ nghĩa:** Làm rõ định nghĩa "Pending Action" gắn liền với thực thể `cong_viec` trong CSDL, quy định cụ thể danh mục trạng thái chưa hoàn tất (`moi`, `dang_lam`), và cơ chế xử lý phản hồi lỗi HTTP 409 khi nhân viên bấm Resolve vi phạm chốt chặn.
3. **Phân định rõ ràng từng vị trí:** Cung cấp đầy đủ 7 trường thông tin bắt buộc cho từng đề xuất để người dùng có thể đối chiếu và chỉnh sửa trực tiếp vào tài liệu Word báo cáo khóa luận.

---

## 2. DANH MỤC CÁC ĐỀ XUẤT CHỈNH SỬA CHI TIẾT

---

### Đề xuất 1: Cụ thể hóa điều kiện kiểm tra Pending Action trong Use Case `UC-08`

1. **Số trang PDF gốc:** Trang 44–45.
2. **Practice, mục và số bảng:** Practice #6, Mục `2.3. UC-08 – Kết thúc phiên hỗ trợ thủ công`.
3. **Nội dung hiện tại được trích từ tài liệu:**
   - *Preconditions (Trang 44):*
     > "Conversation ở Manual Mode; nhân viên có quyền; không có Pending Action bắt buộc chưa hoàn tất."
   - *Main Flow Bước 4 (Trang 45):*
     > "4. Hệ thống kiểm tra quyền, trạng thái Pending Actions và yêu cầu chưa hoàn tất."
   - *Exceptions EF-01 (Trang 45):*
     > "EF-01: Còn Pending Action chưa hoàn tất $\rightarrow$ không tự Resolve."
4. **Hành động:** **Bổ sung** (Bổ sung diễn giải chi tiết cho các bước kiểm tra, giữ nguyên cấu trúc luồng).
5. **Nội dung đề xuất hoàn chỉnh bằng tiếng Việt:**
   - *Cập nhật Preconditions (Trang 44):*
     > "Conversation ở Manual Mode; nhân viên có quyền thao tác trên hội thoại; **toàn bộ các công việc/Pending Actions liên kết với hội thoại trong bảng `cong_viec` đã ở trạng thái hoàn thành (`xong` hoặc `huy`), không còn công việc nào ở trạng thái `moi` hoặc `dang_lam`**."
   - *Cập nhật Main Flow Bước 4 (Trang 45):*
     > "4. Hệ thống kiểm tra quyền người dùng và thực thi truy vấn kiểm tra chốt chặn Resolve (Resolve Guard): xác minh không tồn tại bản ghi công việc nào thuộc hội thoại có `trang_thai IN ('moi', 'dang_lam')`. Đồng thời kiểm tra tin nhắn cuối cùng của khách hàng đã được phản hồi."
   - *Cập nhật Exceptions EF-01 (Trang 45):*
     > "EF-01: Còn công việc/Pending Action ở trạng thái `moi` hoặc `dang_lam` $\rightarrow$ **Hệ thống từ chối thao tác Resolve, trả về mã lỗi 409 Conflict kèm danh sách công việc chưa hoàn tất, giữ nguyên hội thoại ở trạng thái `Open` và thông báo cho nhân viên trên giao diện**."
6. **Requirement ID liên quan:** `FR-11`, `AC-11.2`, `DFR-11`.
7. **Lý do chỉnh sửa:** Làm rõ cách thức hệ thống kiểm tra và phản hồi khi phát hiện công việc chưa hoàn thành, giúp lập trình viên không bỏ sót logic chặn tại tầng API và Backend.

---

### Đề xuất 2: Chuẩn hóa hành vi phản hồi trong Event–Response Table (`EVT-05`)

1. **Số trang PDF gốc:** Trang 72–73.
2. **Practice, mục và số bảng:** Practice #7, Bảng 7.1: Omnichannel & AI Agent Event–Response Table, dòng sự kiện `EVT-05`.
3. **Nội dung hiện tại được trích từ tài liệu:**
   - *Dòng 1 (Trang 72):*
     > - *Event:* EVT-05 – Nhân viên Resolve  
     > - *System State:* Manual Mode; nhân viên đủ quyền; không còn Pending Action chưa hoàn tất và không còn yêu cầu khách chưa giải quyết  
     > - *Response:* Chuyển Conversation sang Resolved, lưu lịch sử; không kích hoạt AI gửi phản hồi ngay.
   - *Dòng 2 (Trang 73):*
     > - *Event:* EVT-05 – Nhân viên Resolve  
     > - *System State:* Còn Pending Action chưa hoàn tất hoặc yêu cầu khách chưa giải quyết  
     > - *Response:* Từ chối Resolve theo luồng thông thường; giữ Conversation ở trạng thái Open–Manual.
4. **Hành động:** **Thay thế** phần mô tả Response của Dòng 2.
5. **Nội dung đề xuất hoàn chỉnh bằng tiếng Việt:**
   - *Dòng 1:* **Giữ nguyên**.
   - *Dòng 2 (Trang 73):*
     > - *Event:* EVT-05 – Nhân viên Resolve  
     > - *System State:* Tồn tại công việc (`cong_viec`) liên kết có trạng thái `moi` hoặc `dang_lam`, hoặc yêu cầu khách chưa giải quyết  
     > - *Response:* **Từ chối yêu cầu Resolve; trả về lỗi HTTP 409 Conflict kèm danh sách mã và tiêu đề công việc chưa hoàn tất; giữ nguyên Conversation ở trạng thái Open–Manual; duy trì lượt phân công và không phát sinh sự kiện CSAT**.
6. **Requirement ID liên quan:** `FR-11`, `AC-11.2`, `QR-14`.
7. **Lý do chỉnh sửa:** Cụ thể hóa phản ứng của hệ thống (Response) ở cấp độ giao thức API và CSDL thay vì chỉ dùng cụm từ định tính "từ chối theo luồng thông thường".

---

### Đề xuất 3: Chuẩn hóa hành vi Auto-Resolve khi gặp Pending Action (`EVT-13`)

1. **Số trang PDF gốc:** Trang 74.
2. **Practice, mục và số bảng:** Practice #7, Bảng 7.1: Omnichannel & AI Agent Event–Response Table, dòng sự kiện `EVT-13`.
3. **Nội dung hiện tại được trích từ tài liệu:**
   - *Dòng 2 (Trang 74):*
     > - *Event:* EVT-13 – Idle Timeout  
     > - *System State:* Còn Pending Action hoặc câu hỏi khách chưa được trả lời  
     > - *Response:* Không tự Resolve; duy trì hội thoại mở và trách nhiệm xử lý.
4. **Hành động:** **Bổ sung** chi tiết vào phần Response.
5. **Nội dung đề xuất hoàn chỉnh bằng tiếng Việt:**
   > - *Event:* EVT-13 – Idle Timeout (Hết thời gian chờ cấu hình, mặc định 4 giờ)  
   > - *System State:* Còn Pending Action ở trạng thái `moi` hoặc `dang_lam`, hoặc câu hỏi khách chưa được trả lời  
   > - *Response:* **Tiến trình nền bỏ qua không đóng hội thoại; duy trì Conversation ở trạng thái `Open`; ghi nhận cảnh báo quá hạn cho quản lý nếu thời gian chờ vượt ngưỡng an toàn; không kích hoạt khảo sát CSAT**.
6. **Requirement ID liên quan:** `FR-23`, `AC-23.2`, `AC-23.3`.
7. **Lý do chỉnh sửa:** Thống nhất ngưỡng thời gian chờ cấu hình (mặc định 4 giờ theo Backlog v1.1) và mô tả rõ tiến trình nền sẽ xử lý thế nào khi quét gặp hội thoại còn task.

---

### Đề xuất 4: Bổ sung Ghi chú Kiểm chứng cho `AC-11.2` và `AC-23.2` trong Danh mục FR

1. **Số trang PDF gốc:** Trang 142 và Trang 149.
2. **Practice, mục và số bảng:** Practice #10, Bảng 10.13 (Trang 142) và Bảng 10.25 (Trang 149).
3. **Nội dung hiện tại được trích từ tài liệu:**
   - *Bảng 10.13 (Trang 142) – `AC-11.2`:*
     > *Given:* Còn Pending Action chưa hoàn tất  
     > *When:* Nhân viên yêu cầu Resolve  
     > *Then:* Từ chối Resolve theo luồng thông thường.
   - *Bảng 10.25 (Trang 149) – `AC-23.2`:*
     > *Given:* Còn Pending Action chưa hoàn tất hoặc câu hỏi khách chưa được trả lời  
     > *When:* Hệ thống xử lý Idle Timeout  
     > *Then:* Không tự Resolve.
4. **Hành động:** **Giữ nguyên văn** tiêu chí Given–When–Then; **Bổ sung** đoạn "Ghi chú kỹ thuật nghiệm thu" ngay dưới mỗi bảng.
5. **Nội dung đề xuất hoàn chỉnh bằng tiếng Việt:**
   - *Bổ sung dưới Bảng 10.13 (Trang 142):*
     > *"Ghi chú kỹ thuật cho AC-11.2: Pending Action được định nghĩa là các bản ghi trong thực thể `cong_viec` có `conversation_id = id` của hội thoại đang xét và `trang_thai IN ('moi', 'dang_lam')`. Thao tác Resolve chỉ thành công khi toàn bộ các công việc liên kết đều ở trạng thái `xong` hoặc `huy`. Khi bị từ chối, API trả về HTTP 409 Conflict."*
   - *Bổ sung dưới Bảng 10.25 (Trang 149):*
     > *"Ghi chú kỹ thuật cho AC-23.2: Cơ chế Auto-Resolve định kỳ (quét idle timeout mặc định 4 giờ) bắt buộc phải kiểm tra điều kiện chốt chặn tương tự như AC-11.2. Nếu hội thoại còn task `moi` hoặc `dang_lam`, worker phải bỏ qua không thực hiện Resolve."*
6. **Requirement ID liên quan:** `FR-11 (AC-11.2)`, `FR-23 (AC-23.2, AC-23.3)`.
7. **Lý do chỉnh sửa:** Giữ nguyên vẹn Requirements Baseline đã được thống kê trong Source Register, đồng thời cung cấp căn cứ kỹ thuật chính xác cho quá trình kiểm thử nghiệm thu.

---

### Đề xuất 5: Bổ sung Quy tắc Chốt chặn Nghiệp vụ vào Practice #16

1. **Số trang PDF gốc:** Trang 187–188.
2. **Practice, mục và số bảng:** Practice #16, Bảng 16.1: Consolidated Business Rules Catalog.
3. **Nội dung hiện tại được trích từ tài liệu:** Bảng 16.1 hiện chưa có mục riêng mô tả chi tiết quy tắc Resolve Task Guard.
4. **Hành động:** **Bổ sung** 1 quy tắc Constraint vào Bảng 16.1.
5. **Nội dung đề xuất hoàn chỉnh bằng tiếng Việt:**
   - *Thêm bản ghi mới vào Bảng 16.1:*
     > - **Mã nguồn:** `BR-CONV-RESOLVE-GUARD` (Kế thừa từ `DEC-MVP-06`, `DEC-MVP-10`)  
     > - **Loại:** `Constraint`  
     > - **Nội dung quy tắc nghiệp vụ:** **"Chốt chặn kết thúc hội thoại: Một hội thoại chỉ được phép chuyển sang trạng thái Resolved (thủ công hoặc tự động) khi toàn bộ các công việc trong bảng `cong_viec` liên kết với hội thoại đã ở trạng thái hoàn thành (`xong` hoặc `huy`). Hệ thống phải từ chối thao tác Resolve và thông báo lỗi nếu tồn tại bất kỳ công việc nào ở trạng thái `moi` hoặc `dang_lam`."**  
     > - **Yêu cầu liên quan:** `FR-11 (AC-11.2)`, `FR-23 (AC-23.2)`, `FR-19 (AC-19.3)`, `FR-20 (AC-20.4)`, `DFR-11`.
6. **Requirement ID liên quan:** `FR-11`, `FR-23`, `DFR-11`.
7. **Lý do chỉnh sửa:** Hợp nhất các quyết định rải rác (`DEC-MVP-06`, `DEC-MVP-10`) thành một quy tắc nghiệp vụ tập trung, phục vụ bảo vệ đồ án trước hội đồng.

---

### Đề xuất 6: Bổ sung Ca kiểm thử Truy vết vào Practice #18

1. **Số trang PDF gốc:** Trang 192–195.
2. **Practice, mục và số bảng:** Practice #18, Bảng 18.1 và Bảng 18.2: Requirements Traceability Matrix.
3. **Nội dung hiện tại được trích từ tài liệu:** `AC-11.2` và `AC-23.2` mới chỉ được ánh xạ chung tới file test vòng đời `test_giai_quyet_csat.py` (vốn chưa kiểm tra bảng `cong_viec`).
4. **Hành động:** **Bổ sung** liên kết kiểm thử chuyên biệt.
5. **Nội dung đề xuất hoàn chỉnh bằng tiếng Việt:**
   - Bổ sung ca kiểm thử tự động chuyên biệt:
     - **Test ID:** `TC-RESOLVE-GUARD-01` (File kiểm thử: `tests/test_chan_resolve_khi_con_task.py`).
     - **Loại bằng chứng:** `Executed Evidence`.
     - **Ánh xạ yêu cầu:** `FR-11 (AC-11.2)`, `FR-23 (AC-23.2)`.
     - **Mục tiêu kiểm thử:** Xác nhận API trả về HTTP 409 khi task ở `moi`/`dang_lam`, và cho phép Resolve thành công khi task ở `xong`/`huy`.
6. **Requirement ID liên quan:** `AC-11.2`, `AC-23.2`.
7. **Lý do chỉnh sửa:** Khắc phục khoảng trống kiểm thử truy vết đã được phát hiện trong báo cáo kiểm toán GAP-07B.

---

## Phần 3: BA Handoff

# ĐẶC TẢ YÊU CẦU BÀN GIAO CHO KỸ THUẬT (CODEX HANDOFF SPEC)
## TRIỂN KHAI CHỐT CHẶN RESOLVE KHI CÒN CÔNG VIỆC CHƯA HOÀN THÀNH (GAP-07B)

- **Mã tài liệu:** `G2-02-BA-HANDOFF`
- **Mã công việc kế tiếp:** `TASK-CODE-04` & `TASK-TEST-02` (Implementation Backlog v1.1)
- **Người lập:** Business Analyst
- **Đối tượng bàn giao:** Đội ngũ Lập trình viên Backend (Codex / Engineering Team)
- **Trạng thái:** Sẵn sàng triển khai (Ready for Implementation)

---

## 1. THÔNG TIN ĐỊNH DANH YÊU CẦU (REQUIREMENT IDS)

- **Functional Requirements:**
  - `FR-11` (AC-11.2): Phản hồi thủ công và kết thúc phiên hỗ trợ – Từ chối Resolve khi còn Pending Action chưa hoàn tất.
  - `FR-23` (AC-23.2): Quản lý Conversation Lifecycle – Không tự động Auto-Resolve khi còn Pending Action hoặc câu hỏi khách chưa được giải quyết.
  - `FR-19` (AC-19.3) & `FR-20` (AC-20.4): Bảo vệ luồng Sửa/Hủy đơn hàng – Phải hoàn tất xử lý trên ERPNext và đóng Pending Action trước khi kết thúc hội thoại.
- **Quality / Safety Requirements:**
  - `QR-14`: Quản lý lỗi và kiểm soát ngoại lệ hội thoại.
  - `DFR-11`: Tạo Pending Action và Handover cho yêu cầu sửa/hủy; không tự đánh dấu hoàn tất khi chưa có kết quả nghiệp vụ.
- **Mã vấn đề theo dõi:** `GAP-07B` (Resolve Guard for Incomplete Tasks).

---

## 2. HÀNH VI NGHIỆP VỤ KỲ VỌNG (EXPECTED BUSINESS BEHAVIOR)

1. **Chặn thao tác Resolve khi còn công việc chưa xong:**
   - Khi nhân viên CSKH gửi yêu cầu kết thúc hội thoại qua API `POST /api/inbox/conversations/{id}/giai-quyet` (hoặc qua hàm `agent.omnichannel.giai_quyet.giai_quyet`):
   - Hệ thống **BẮT BUỘC KIỂM TRA** bảng `cong_viec` xem có bản ghi nào gắn với `conversation_id` đang ở trạng thái chưa hoàn thành (`trang_thai IN ('moi', 'dang_lam')`) hay không.
   - Nếu tồn tại ít nhất một công việc chưa hoàn thành:
     - Hệ thống **từ chối thực hiện Resolve**.
     - API trả về mã phản hồi HTTP **`409 Conflict`** kèm thông báo lỗi và danh sách các công việc còn tồn đọng.
     - CSDL không thay đổi trạng thái hội thoại: `conversations.state` vẫn giữ nguyên `'open'`, không gán `resolved_at`, không kết thúc lượt giao (`conversation_assignments`), và không gửi tin nhắn mời chấm CSAT cho khách hàng.
2. **Cho phép Resolve khi toàn bộ công việc đã đóng:**
   - Nếu toàn bộ các công việc gắn với hội thoại đều đã ở trạng thái hoàn tất (`trang_thai = 'xong'`) hoặc đã hủy (`trang_thai = 'huy'`), hoặc hội thoại hoàn toàn không có công việc nào gắn kèm:
   - Hệ thống cho phép cập nhật `conversations.state = 'resolved'`, `status = 'closed'`, `outcome = 'resolved'`, `resolved_at = now()`, đóng assignment và kích hoạt khảo sát CSAT như bình thường.
3. **Tuyệt đối không mở cờ vượt rào trái phép (No Force-Resolve Bypass):**
   - Không cung cấp tham số `force=true` cho phép nhân viên bỏ qua chốt chặn khi chưa xử lý công việc. Nhân viên muốn Resolve bắt buộc phải bấm hoàn thành (`xong`) hoặc hủy (`huy`) các công việc tương ứng trước.

---

## 3. QUY TẮC NGHIỆP VỤ BẮT BUỘC (BUSINESS RULES)

- **BR-GUARD-01 (Task Completion Precondition):**  
  Một hội thoại chỉ được coi là đủ điều kiện Resolve khi thỏa mãn:
  $$\text{COUNT}(\text{cong\_viec WHERE conversation\_id} = cid \text{ AND trang\_thai IN ('moi', 'dang\_lam')}) = 0$$
- **BR-GUARD-02 (Permitted Terminal Task States):**  
  Hai trạng thái công việc được coi là "đã kết thúc" và không ngăn cản Resolve gồm:
  - `'xong'`: Công việc đã xử lý hoàn tất (`xong_luc IS NOT NULL`).
  - `'huy'`: Công việc đã bị hủy bỏ hợp lệ, không cần tiếp tục thực hiện.
- **BR-GUARD-03 (Source Agnostic):**  
  Chốt chặn kiểm tra áp dụng bình đẳng cho mọi nguồn công việc (`nguon IN ('agent', 'nguoi', 'tu_dong', 'van_chuyen')`). Bất kể công việc do AI tự sinh hay nhân viên tự tạo đều có giá trị ràng buộc như nhau.
- **BR-GUARD-04 (Atomic Transaction):**  
  Bước kiểm tra công việc và bước cập nhật trạng thái hội thoại phải nằm trong cùng một transaction CSDL (hoặc kiểm tra đồng thời với khóa hợp lý) để tránh race condition khi có tiến trình khác thêm công việc cùng thời điểm.

---

## 4. TIÊU CHÍ NGHIỆM THU (ACCEPTANCE CRITERIA DẠNG GIVEN–WHEN–THEN)

- **AC-GUARD-01 (Từ chối Resolve khi có task ở trạng thái `moi`):**
  - **Given:** Hội thoại đang ở trạng thái `open` và có 1 công việc liên kết trong bảng `cong_viec` với `trang_thai = 'moi'`.
  - **When:** Nhân viên gửi request `POST /api/inbox/conversations/{id}/giai-quyet`.
  - **Then:** API trả về mã HTTP `409 Conflict`; Body chứa thông điệp lỗi và ID của công việc; Bảng `conversations` vẫn giữ `state = 'open'` và `resolved_at IS NULL`.
- **AC-GUARD-02 (Từ chối Resolve khi có task ở trạng thái `dang_lam`):**
  - **Given:** Hội thoại đang ở trạng thái `open` và có 1 công việc liên kết trong bảng `cong_viec` với `trang_thai = 'dang_lam'`.
  - **When:** Nhân viên gửi request `POST /api/inbox/conversations/{id}/giai-quyet`.
  - **Then:** API trả về mã HTTP `409 Conflict`; Hội thoại không bị chuyển sang `resolved`.
- **AC-GUARD-03 (Chấp nhận Resolve khi toàn bộ task đã `xong`):**
  - **Given:** Hội thoại có các công việc liên kết đều đã được cập nhật `trang_thai = 'xong'`.
  - **When:** Nhân viên gửi request `POST /api/inbox/conversations/{id}/giai-quyet`.
  - **Then:** API trả về HTTP `200 OK`; Bảng `conversations` cập nhật `state = 'resolved'`, `resolved_at IS NOT NULL`; Lượt giao `conversation_assignments` được kết thúc.
- **AC-GUARD-04 (Chấp nhận Resolve khi task ở trạng thái `huy`):**
  - **Given:** Hội thoại có 1 công việc liên kết ở trạng thái `trang_thai = 'huy'`.
  - **When:** Nhân viên gửi request `POST /api/inbox/conversations/{id}/giai-quyet`.
  - **Then:** API trả về HTTP `200 OK`; Hội thoại được Resolve thành công.
- **AC-GUARD-05 (Chấp nhận Resolve khi không có task nào liên kết):**
  - **Given:** Hội thoại không có bất kỳ bản ghi nào trong bảng `cong_viec`.
  - **When:** Nhân viên gửi request `POST /api/inbox/conversations/{id}/giai-quyet`.
  - **Then:** API trả về HTTP `200 OK`; Hội thoại được Resolve thành công.

---

## 5. KỊCH BẢN KIỂM THỬ ĐỀ XUẤT (POSITIVE / NEGATIVE TEST SCENARIOS)

Đội ngũ kỹ thuật hiện thực hóa thành file kiểm thử `tests/test_chan_resolve_khi_con_task.py` (`TASK-TEST-02`):

| Test ID | Phân loại | Điều kiện Tiền đề (Given) | Hành động (When) | Kết quả Mong đợi (Then) |
|---|:---:|---|---|---|
| **TC-GUARD-NEG-01** | Negative | Có task `moi` do Agent tạo (`nguon = 'agent'`). | Gọi API Resolve. | HTTP 409 Conflict; `state` vẫn là `'open'`. |
| **TC-GUARD-NEG-02** | Negative | Có task `dang_lam` do Nhân viên tạo (`nguon = 'nguoi'`). | Gọi API Resolve. | HTTP 409 Conflict; `state` vẫn là `'open'`. |
| **TC-GUARD-NEG-03** | Negative | Có 2 task: 1 task `xong`, 1 task `moi`. | Gọi API Resolve. | HTTP 409 Conflict; danh sách lỗi chỉ ra đúng task `moi`. |
| **TC-GUARD-POS-01** | Positive | Có 1 task `xong` (`xong_luc` có giá trị). | Gọi API Resolve. | HTTP 200 OK; `state == 'resolved'`; `resolved_at IS NOT NULL`. |
| **TC-GUARD-POS-02** | Positive | Có 1 task `huy` (đã hủy). | Gọi API Resolve. | HTTP 200 OK; `state == 'resolved'`. |
| **TC-GUARD-POS-03** | Positive | Có nhiều task hỗn hợp đều ở `xong` hoặc `huy`. | Gọi API Resolve. | HTTP 200 OK; `state == 'resolved'`. |
| **TC-GUARD-POS-04** | Positive | Hội thoại chat thông thường, không có task nào trong `cong_viec`. | Gọi API Resolve. | HTTP 200 OK; `state == 'resolved'`. |

---

## 6. NGOÀI PHẠM VI (OUT OF SCOPE)

- **Không xây dựng Worker Auto-Resolve trong nhiệm vụ này:** Việc hiện thực hóa background loop quét idle timeout tự động đóng hội thoại thuộc phạm vi của [`TASK-CODE-05`](file:///Users/huynhlehoaibao/Documents/AIAgent_mar/docs/requirements-audit/implementation_backlog_v1_1.md#task-code-05). Tuy nhiên, hàm kiểm tra task (`has_uncompleted_tasks`) phải được thiết kế dạng module tái sử dụng để `TASK-CODE-05` gọi lại sau này.
- **Không thay đổi cấu trúc bảng `cong_viec`:** Schema CSDL của bảng `cong_viec` đã hoàn chỉnh, không cần thêm migration sửa đổi cột.
- **Không thay đổi các quyền danh mục:** Quyền `hoi_thoai.nhan` và `cong_viec.doc`/`cong_viec.sua` giữ nguyên như hiện hành.

---

## 7. CÁC ĐIỂM CẦN XÁC MINH KỸ THUẬT TRƯỚC KHI SỬA CODE

Trước khi lập trình `TASK-CODE-04`, lập trình viên cần đối soát các điểm kỹ thuật sau:
1. **Import hằng số `CHUA_XONG`:**  
   Module `agent/core/cong_viec.py` đã định nghĩa sẵn:
   ```python
   TRANG_THAI = ("moi", "dang_lam", "xong", "huy")
   CHUA_XONG = ("moi", "dang_lam")
   ```
   Khuyến nghị tái sử dụng hằng số này trong logic kiểm tra để đảm bảo tính nhất quán toàn hệ thống.
2. **Vị trí đặt hàm kiểm tra:**  
   Nên đặt logic kiểm tra trong hàm `agent.omnichannel.giai_quyet.giai_quyet()` trước khi mở transaction cập nhật conversation. Nếu phát hiện task chưa xong, hàm có thể ném một custom exception (ví dụ `ConversationHasPendingTasksError`) hoặc trả về mã lỗi đặc thù để router `agent/api/hoi_thoai_nhan.py` chuyển đổi thành HTTP 409.
3. **Mã phản hồi HTTP:**  
   Thống nhất sử dụng mã HTTP **`409 Conflict`** (chuẩn RESTful cho xung đột trạng thái tài nguyên) thay vì `400 Bad Request`.

---

