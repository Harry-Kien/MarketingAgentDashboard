# Báo Cáo Tổng Hợp: Phân Tích Khoảng Hở (GAP), Đề Xuất Hành Động & Danh Mục Ứng Viên

> Tài liệu hợp nhất toàn diện phân tích khoảng hở kỹ thuật/nghiệp vụ (Baseline RB-R1-002), các hành động đề xuất theo thứ tự ưu tiên (P0/P1/P2) và danh mục ứng viên kỹ thuật chuẩn bị cho Backlog thực thi.

---

## Phần 1: Nhật Ký Khoảng Hở Kỹ Thuật (Gap Issue Log)

# Gap Issue Log – Requirements Baseline Release 1 v1.1 (RB-R1-002)

| Gap ID | FR/AC | Priority | Gap Type | Actual Evidence | Code Action | BA Documentation Action |
|---|---|---|---|---|---|---|
| **GAP-01** | FR-27 / AC-27.1, AC-27.4 | P0 (ĐÃ ĐÓNG) | RESOLVED (IMPLEMENTATION) | [RESOLVED tại commit 69f5960]: Đã bổ sung endpoint `POST /api/orders/{order_id}/van-don` trong `agent/api/don_kho.py:203` (yêu cầu quyền `don.sua`, có Advisory Lock chống bấm đúp) và nút "Tạo vận đơn" tại `dashboard/app.js:2090` cùng cờ cấu hình `GET /api/van-chuyen/cau-hinh`. | Đã triển khai xong và có kiểm thử `tests/test_hoan_thien_luong.py`. | Cập nhật tài liệu BA xác nhận chức năng tạo vận đơn thủ công trên Dashboard đã hoàn thiện (đóng RV-05). |
| **GAP-02** | FR-27 / AC-27.3, FR-28 / AC-28.2, FR-29 / AC-29.4 | P0 | IMPLEMENTATION GAP | Sau khi tạo vận đơn GHN thành công (`agent/shipping/service.py:190-210`), mã vận đơn chỉ được cập nhật vào bảng `orders` của Postgres và gửi qua Outbox cho khách. Hệ thống **chưa gọi sang ERPNext** để cập nhật mã vận đơn vào Doctype `Delivery Note` hoặc `Sales Order`. | Thêm hàm đồng bộ mã vận đơn sang ERPNext trong `agent/erp/` và gọi sau khi tạo vận đơn thành công; bổ sung retry worker khi đồng bộ thất bại. | Đặc tả rõ trường dữ liệu nhận mã vận đơn trên ERPNext (`tracking_number`, `delivery_note`) trong DFR-18 và DEC-MVP-38. |
| **GAP-03** | FR-07 / AC-07.2 | P1 | IMPLEMENTATION GAP | Khi khách gửi tin mới trong lúc AI đang suy luận một Batch cũ, hệ thống chưa có cơ chế thu hồi/đánh dấu `SUPERSEDED` bằng generation token nguyên tử trong CSDL. Hiện tại chỉ kiểm tra `mode != 'human'` trước khi Enqueue Outbox (`agent/omnichannel/outbound_service.py:45`). | Bổ sung trường `active_batch_token` hoặc `epoch` trong `conversations`, kiểm tra token trước khi Outbox Worker gửi tin ra ngoài để hủy bỏ batch cũ khi có tin mới. | Làm rõ cơ chế nhận diện và hủy batch cũ (Stale Batch Suppression) trong AC-07.2 và DFR-05. |
| **GAP-04** | FR-13 / AC-13.1, AC-13.2, AC-13.3; FR-14 / AC-14.2; FR-15 / AC-15.2 | P1 | CODE–REQUIREMENT MISMATCH | Bảng `documents` và `chunks` trong `agent/schema.sql` không có cột `status` (`draft`/`published`), không có `version_id`. Mọi chunk được ingest (`rag.ingest`) đều có hiệu lực truy xuất ngay lập tức. Quy trình phê duyệt tài liệu 2 bước và cơ chế Rollback phiên bản tri thức chưa được hỗ trợ ở mức CSDL. | Bổ sung migration thêm cột `status`, `version`, `published_at` vào bảng `documents`; cập nhật query trong `agent/core/rag.py` chỉ tìm kiếm chunks có `status = 'published'`. | Cập nhật quy trình xuất bản tri thức trong CAP-04; cân nhắc chuyển cơ chế phân phiên bản nâng cao (Rollback) sang Release 2 nếu Release 1 chỉ dùng file Markdown tĩnh. |
| **GAP-05** | FR-19 / AC-19.3, FR-20 / AC-20.4 | P1 | IMPLEMENTATION GAP | Khi khách yêu cầu sửa/hủy đơn hàng, AI đã gọi đúng công cụ `xin_huy_don` / `xin_doi_tra` để tạo Pending Action và cờ `yeu_cau_huy_luc` (`agent/core/tools.py:1460-1540`). Tuy nhiên trên Dashboard, nhân viên bấm duyệt hủy chỉ cập nhật cục bộ bảng `orders`, chưa kích hoạt luồng đồng bộ hủy sang ERPNext/Odoo và chưa có giao diện sửa mặt hàng đơn dở dang. | Bổ sung router API duyệt hủy đơn đồng bộ sang ERPNext (`cancel_sales_order`), thêm modal sửa đơn gắn với mã đơn dở dang trên Dashboard. | Xác nhận lại ranh giới trách nhiệm: Nhân viên vào thẳng giao diện ERPNext để sửa/hủy đơn hay bắt buộc thực hiện trên Dashboard (RV-04). |
| **GAP-06** | FR-29 / AC-29.2, AC-29.3 | P1 | IMPLEMENTATION GAP | Khác với module ERP có `vong_dong_bo.py` quản lý retry và đối soát đơn kẹt với 4 lưới bảo vệ, module vận chuyển (`agent/shipping/`) chưa có tiến trình nền đối soát giao dịch kẹt (Pending Shipping Reconciliation Worker) khi GHN API bị Timeout ở bước tạo vận đơn. | Xây dựng worker đối soát vận chuyển tương tự `vong_dong_bo.py`, tra cứu lại theo `client_order_code` sang GHN trước khi thử lại hoặc kết luận thất bại. | Cập nhật luồng xử lý ngoại lệ Timeout của Shipping API trong BPMN và AC-29.2. |
| **GAP-07** | FR-10 / AC-10.1, AC-10.2 | P1 | REQUIREMENT AMBIGUITY | Tài liệu BA (Bảng 18.3 - RV-02) ghi nhận: Phạm vi giữa **Claim** (nhân viên nhận hội thoại đang trong hàng đợi Handover) và **Takeover** (nhân viên chủ động cướp quyền từ AI khi đang Auto) chưa được phân định ranh giới rõ ràng trong nghiệp vụ và giao diện. | Code hiện tại gom chung vào một hàm `takeover()` trong `agent/omnichannel/routing.py:50`. Cần tách biệt rõ hành vi nếu nghiệp vụ yêu cầu quyền hạn khác nhau. | Cần BA làm rõ: Claim và Takeover là hai hành động riêng biệt (với permission khác nhau) hay là cùng một thao tác tiếp quản hội thoại. |
| **GAP-08** | FR-01–29 (Toàn bộ) | P1 | TEST COVERAGE GAP | Tài liệu BA trong Practice #18 chưa hoàn thiện ánh xạ cụ thể giữa từng Acceptance Criteria với Test ID thực tế trong code (RV-01). Mặc dù codebase có 100+ file kiểm thử với độ bao phủ cao, việc thiếu ma trận ánh xạ 1-1 khiến BA không có bằng chứng chính thức để nghiệm thu yêu cầu. | Giữ nguyên bộ test; gắn tag decorator hoặc comment mã AC tương ứng trong các file `tests/test_*.py` để tự động hóa sinh báo cáo đối chiếu. | Bổ sung bảng ánh xạ Test ID chi tiết vào Practice #18 và #19 của tài liệu BA. |
| **GAP-09** | Toàn hệ thống | P2 | ARCHITECTURE DECISION | Repository đang duy trì song song hai kênh hội thoại: Native Inbox (`agent/omnichannel/`) và Chatwoot (`agent/channels/chatwoot.py`). Chatwoot đang đóng vai trò adapter bên ngoài hơn là nguồn dữ liệu chính, trong khi Native Inbox là Single Source of Truth nội bộ. | Cần văn bản hóa quyết định kiến trúc: Chatwoot được dùng làm kênh chuyển tiếp phụ hay sẽ được loại bỏ hoàn toàn để tập trung vào Native Dashboard. | Đưa quyết định lựa chọn Native Inbox làm kiến trúc trung tâm vào DEC-MVP hoặc Architecture Decision Record (ADR). |
| **GAP-10** | Practice #18, #19, #20 | P2 | DOCUMENTATION GAP | Tài liệu BA chưa cập nhật thông tin thực tế từ đợt Audit này: các số liệu kiểm thử mâu thuẫn (143 vs 155), thiếu kết quả kiểm thử an toàn nội bộ, chưa cập nhật Change Request CR-001 cho phân hệ Shipping và Kiến trúc dữ liệu Tri thức. | Không yêu cầu sửa code. | Cập nhật hồ sơ kiểm chứng Practice #18, Baseline RB-R1-002 trong Practice #19 và tạo đề xuất CR-001 trong Practice #20. |

---

## Phần 2: Đề Xuất Hành Động Kỹ Thuật & Nghiệp Vụ (Recommended Actions)

# Recommended Actions – Requirements Baseline Release 1 v1.1 (RB-R1-002)

Tài liệu này tổng hợp các đề xuất hành động kỹ thuật và nghiệp vụ được phân cấp theo thứ tự ưu tiên (P0, P1, P2) nhằm đưa hệ thống AI Agent Customer Service đạt chuẩn nghiệm thu đầy đủ theo Baseline RB-R1-002.

---

## 1. Hành động ưu tiên P0 (Bắt buộc hoàn thành trước nghiệm thu Release 1)

### ACT-P0-01: [ĐÃ HOÀN THÀNH] Hoàn thiện API và Giao diện Dashboard tạo vận đơn (FR-27)
- **Trạng thái**: **RESOLVED** (Triển khai tại commit `69f5960`).
- **Bằng chứng thực tế**:
  - API endpoint: [`POST /api/orders/{order_id}/van-don`](file:///Users/huynhlehoaibao/Documents/AIAgent_mar/agent/api/don_kho.py#L203) yêu cầu phân quyền `can_quyen('don.sua')`, kiểm tra hãng thật (`HANG_THAT = ('ghn', 'ghtk')`), áp dụng khóa `pg_try_advisory_lock(hashtext('van_don:' || ma_don))` chống bấm đúp, gọi `service.tao_van_don_cho_don()`.
  - Endpoint cấu hình: [`GET /api/van-chuyen/cau-hinh`](file:///Users/huynhlehoaibao/Documents/AIAgent_mar/agent/api/don_kho.py#L245) cung cấp cờ hãng thật cho client.
  - Dashboard: [`dashboard/app.js:2090-2130`](file:///Users/huynhlehoaibao/Documents/AIAgent_mar/dashboard/app.js#L2090-L2130) đã có nút "Tạo vận đơn" cho đơn `da_chot` và hiển thị kết quả tạo thành công hoặc báo lỗi rõ ràng.
  - Test kiểm chứng: `tests/test_hoan_thien_luong.py::test_tao_van_don_goi_ham_bon_chot_va_bao_loi_ro`, `test_man_don_co_nut_van_don_va_bao_dung_ket_qua`.
- **Hành động còn lại**: BA cập nhật tài liệu đóng Issue RV-05.

---

### ACT-P0-02: Kết nối đồng bộ mã vận đơn về ERPNext (FR-27, FR-28)
- **Module/File liên quan**:
  - `agent/shipping/service.py:195-215`
  - `agent/erp/day_don.py` & `agent/erp/erpnext.py`
  - `agent/erp/hop_dong.py`
- **Nguyên nhân và bằng chứng**:
  - Sau khi GHN trả mã vận đơn, code chỉ cập nhật vào bảng `orders` của Postgres nội bộ mà không gọi sang ERPNext để cập nhật Doctype `Delivery Note` hoặc `Sales Order`.
- **Hành động cần thực hiện**:
  1. Bổ sung phương thức `cap_nhat_van_don(erp_order_id, ma_van_don, carrier)` vào giao diện cổng ERP (`agent/erp/hop_dong.py`).
  2. Triển khai phương thức này trong `ERPNextCong` (`agent/erp/erpnext.py`).
  3. Gọi hàm đồng bộ này ngay sau khi cập nhật bảng `orders` trong `agent/shipping/service.py`.
- **Tiêu chí hoàn thành**:
  - Khi tạo vận đơn thành công, Doctype tương ứng trên ERPNext được cập nhật đúng trường `tracking_number` và `carrier_name`.
- **Change Request (CR)**: Cần đưa vào **CR-001** (Thống nhất schema và Doctype nhận mã vận đơn trên ERPNext).

---

## 2. Hành động ưu tiên P1 (Cải tiến chất lượng, an toàn và xử lý ngoại lệ)

### ACT-P1-01: Triển khai Stale Batch Suppression Token cho Outbound AI (FR-07 / AC-07.2)
- **Module/File liên quan**:
  - `agent/omnichannel/inbox_service.py`
  - `agent/omnichannel/outbound_service.py`
  - `agent/schema.sql` (bảng `conversations`)
- **Nguyên nhân và bằng chứng**:
  - Khi khách gửi tin nhắn dồn dập trong lúc LLM đang xử lý batch cũ, batch cũ có nguy cơ gửi phản hồi lỗi thời trước khi tin mới được trả lời nếu không có cơ chế hủy bỏ nguyên tử.
- **Hành động cần thực hiện**:
  1. Thêm trường `active_turn_token` kiểu UUID vào bảng `conversations`.
  2. Mỗi khi có tin nhắn inbound mới, sinh token mới.
  3. Trước khi Outbox Worker đẩy tin AI đi, kiểm tra token của lượt có khớp với `active_turn_token` hiện hành hay không. Nếu không, đánh dấu batch là `SUPERSEDED` và hủy gửi.
- **Tiêu chí hoàn thành**:
  - Kiểm thử mô phỏng khách gửi tin mới giữa lúc sinh câu trả lời chứng minh batch cũ bị hủy và không xuất hiện trên kênh chat của khách.
- **Change Request (CR)**: Không cần CR (đã được bao hàm trong DFR-05 và AC-07.2).

---

### ACT-P1-02: Bổ sung trạng thái Draft/Published cho cơ sở tri thức RAG (FR-13, FR-14)
- **Module/File liên quan**:
  - `agent/schema.sql` (bảng `documents`)
  - `agent/core/rag.py`
  - `agent/api/routes.py`
- **Nguyên nhân và bằng chứng**:
  - AC-14.2 quy định: "Chỉ có tài liệu Draft -> Không sử dụng Draft làm nguồn trả lời". Tuy nhiên CSDL hiện tại coi mọi chunk là có hiệu lực ngay khi nạp.
- **Hành động cần thực hiện**:
  1. Thêm cột `status VARCHAR(20) DEFAULT 'published'` vào bảng `documents`.
  2. Cập nhật câu truy vấn tìm kiếm chunks trong `agent/core/rag.py` bổ sung điều kiện `WHERE d.status = 'published'`.
  3. Bổ sung API phê duyệt tài liệu cho vai trò Quản trị (`cau_hinh.sua`).
- **Tiêu chí hoàn thành**:
  - Tài liệu ở trạng thái Draft không được vector search hay full-text search truy xuất vào ngữ cảnh của AI Agent.
- **Change Request (CR)**: Cần đưa vào **CR-001** hoặc xem xét điều chỉnh phạm vi tài liệu tĩnh trong Release 1.

---

### ACT-P1-03: Hoàn thiện Worker đối soát vận chuyển kẹt (FR-29 / AC-29.2)
- **Module/File liên quan**:
  - `agent/shipping/service.py`
  - `agent/shipping/vong_doi_soat.py` (tạo mới)
  - `agent/main.py` (đăng ký lifespan background worker)
- **Nguyên nhân và bằng chứng**:
  - Khi gọi GHN API gặp Timeout, đơn hàng có thể đã được tạo trên hệ thống đối tác nhưng local chưa nhận được mã. Chưa có cơ chế đối soát tự động tra cứu lại định danh giao dịch (`client_order_code`).
- **Hành động cần thực hiện**:
  1. Xây dựng background worker đối soát vận chuyển định kỳ tương tự `vong_dong_bo.py` của ERP.
  2. Tra cứu lại trạng thái đơn qua GHN Open API trước khi cho phép tạo lại hoặc hủy giao dịch.
- **Tiêu chí hoàn thành**:
  - Giao dịch kẹt được tự động gỡ và cập nhật mã vận đơn khi kết nối mạng phục hồi, không tạo vận đơn trùng.
- **Change Request (CR)**: Không cần CR (đáp ứng đúng tiêu chí AC-29.2 và DFR-18).

---

### ACT-P1-04: Phân định ranh giới nghiệp vụ Claim và Takeover (FR-10 / RV-02)
- **Module/File liên quan**:
  - Tài liệu BA (PRACTICE #10 & PRACTICE #18)
  - `agent/omnichannel/routing.py`
  - `dashboard/app.js`
- **Nguyên nhân và bằng chứng**:
  - Bảng 18.3 (RV-02) ghi nhận phạm vi giữa Claim và Takeover chưa được phân biệt rành mạch trong đặc tả nghiệp vụ.
- **Hành động cần thực hiện**:
  1. Làm việc với Stakeholder/BA để thống nhất:
     - **Claim**: Tiếp nhận hội thoại đang chờ trong hàng đợi Handover (`mode='human'`, `assigned_to IS NULL`).
     - **Takeover**: Chủ động ngắt bot từ chế độ Auto (`mode='auto'` -> `mode='human'`).
  2. Cập nhật tài liệu BA và giao diện nút bấm tương ứng trên Dashboard.
- **Tiêu chí hoàn thành**:
  - Đóng Issue RV-02 trong tài liệu BA và có luồng kiểm thử riêng biệt cho từng hành vi.
- **Change Request (CR)**: Cần cập nhật vào tài liệu BA trong đợt Release 1.1 Revision.

---

## 3. Hành động ưu tiên P2 (Tối ưu hóa tài liệu, kiểm thử và kiến trúc)

### ACT-P2-01: Chuẩn hóa bộ Test ID và ánh xạ 1-1 với Acceptance Criteria (Practice #18)
- **Module/File liên quan**:
  - Toàn bộ thư mục `tests/`
  - Tài liệu BA (PRACTICE #18 - Bảng 18.2 & 18.3)
- **Nguyên nhân và bằng chứng**:
  - Bảng 18.2 và 18.3 ghi nhận RV-01: "Chưa hoàn thiện ánh xạ AC với Test ID và kết quả thực thi".
- **Hành động cần thực hiện**:
  1. Sử dụng kết quả Audit tại `requirements_coverage_matrix.md` để bổ sung trực tiếp cột Test ID vào tài liệu BA.
  2. Thêm docstring chuẩn hóa `[Test ID: TC-FRxx-yy]` trong các file kiểm thử pytest.
- **Tiêu chí hoàn thành**:
  - 100% AC có Test ID tương ứng và có thể chạy kiểm thử tự động sinh báo cáo đối chiếu.
- **Change Request (CR)**: Không cần CR code, cập nhật tài liệu BA.

---

### ACT-P2-02: Thống nhất vai trò chính thức của Chatwoot và Native Inbox (DEC-MVP)
- **Module/File liên quan**:
  - `agent/channels/chatwoot.py`
  - `agent/omnichannel/`
  - Tài liệu BA (Kiến trúc tích hợp)
- **Nguyên nhân và bằng chứng**:
  - Hệ thống hiện tại đã xây dựng toàn bộ Native Inbox & Dashboard hoàn chỉnh làm Single Source of Truth. Chatwoot chỉ còn đóng vai trò bridge phụ.
- **Hành động cần thực hiện**:
  1. Văn bản hóa quyết định kiến trúc: Khẳng định Native Inbox là kênh quản trị chính thức của hệ thống; Chatwoot được giữ lại như một Connector/Adapter mở rộng tuỳ chọn.
- **Tiêu chí hoàn thành**:
  - Tài liệu kiến trúc và hướng dẫn vận hành phản ánh đúng thực tế codebase hiện hành.
- **Change Request (CR)**: Cập nhật tài liệu BA / Architecture Decision.

---

## Phần 3: Danh Mục Ứng Viên Triển Khai Kỹ Thuật (Implementation Candidates)

# Implementation Candidates Backlog – Release 1 (RB-R1-002)

> [!IMPORTANT]
> **Tuyên bố về phạm vi và thẩm quyền (Cập nhật sau kiểm toán G1-04D):**
> 1. Danh mục dưới đây là **Danh sách đề xuất ứng viên (Candidate Backlog)** mang tính phương án kỹ thuật, **KHÔNG PHẢI** là lệnh thực thi hoặc backlog đã được phê duyệt chính thức.
> 2. Mọi đề xuất thay đổi về mã nguồn và tài liệu cần được Tech Lead, BA và Product Owner đánh giá, lựa chọn phương án và ký duyệt nội bộ trước khi đưa vào sprint phát triển.
> 3. Tuyệt đối **không tự ý phê duyệt Change Request** (CR-001, CR-002) hoặc Baseline khi chưa có văn bản xác nhận chính thức từ nhóm dự án.

---

## 1. NHÓM ỨNG VIÊN SỬA MÃ NGUỒN (CODE FIX CANDIDATES)
*Tổng cộng: **11 ứng viên Code** (2 P0, 7 P1, 2 P2).*

### Ưu tiên P0 – Khắc phục lỗi logic và đứt gãy dữ liệu nghiêm trọng

| Mã Ứng viên | Yêu cầu liên quan | Vị trí mã nguồn | Hiện trạng & Các phương án kỹ thuật đề xuất | Tác động nếu không xử lý |
|---|---|---|---|---|
| **CODE-P0-01** | FR-11 / AC-11.3 (`GAP-07C`) | `agent/migrations/versions/0005_routing_sla.sql` | **Sửa trigger chống reset deadline SLA khi Reopen:** Trigger `trg_prevent_sla_deadline_reset` hiện tại vô tình ghi đè lại deadline cũ khi khách gửi tin nhắn mở lại hội thoại đã `resolved`.<br>• *Phương án đề xuất:* Tạo migration mới sửa trigger function: chỉ áp dụng logic giữ nguyên deadline khi `OLD.state NOT IN ('resolved', 'closed')`. | Hội thoại vừa reopen lập tức bị đánh dấu vi phạm SLA Breach oan sai. |
| **CODE-P0-02** | FR-27, 28, 29 / AC-27.3, AC-28.2, AC-29.4 (`GAP-02`) | `agent/shipping/service.py:213`, `agent/erp/` | **Đồng bộ mã vận đơn và trạng thái GHN sang ERPNext:** Bổ sung bước đồng bộ kết quả tạo vận đơn thành công về ERPNext.<br>• *Phương án A (Sales Order custom field):* Ghi nhận `tracking_number` và `carrier` trực tiếp vào Doctype `Sales Order` trên ERPNext (phù hợp mô hình bán lẻ tinh gọn).<br>• *Phương án B (Delivery Note standard):* Tạo Doctype `Delivery Note` liên kết với `Sales Order` trên ERPNext và điền `tracking_number` (chuẩn quy trình ERPNext Fulfillment).<br>*(Cần nhóm BA/ERP thống nhất hợp đồng dữ liệu trước khi chọn phương án).* | ERPNext không có mã vận đơn để in phiếu xuất kho và theo dõi hành trình giao nhận. |

---

### Ưu tiên P1 – Hoàn thiện chốt chặn nghiệp vụ và kiểm soát an toàn

| Mã Ứng viên | Yêu cầu liên quan | Vị trí mã nguồn | Hiện trạng & Các phương án kỹ thuật đề xuất | Tác động nếu không xử lý |
|---|---|---|---|---|
| **CODE-P1-01** | FR-07 / AC-07.2, QR-01 (`GAP-03`) | `agent/omnichannel/outbox.py`, `agent/omnichannel/outbox_worker.py` | **Cơ chế thu hồi Batch AI lỗi thời (SUPERSEDED):** Khi khách gửi tin mới trong lúc AI đang sinh phản hồi ở Auto Mode, batch cũ cần bị vô hiệu hóa.<br>• *Phương án A:* Thêm trường `generation_epoch` hoặc `active_batch_id` trong `conversations`. Khi có tin mới đến, tăng epoch để Outbox Worker tự bỏ qua (discard) job thuộc epoch cũ.<br>• *Phương án B:* Kiểm tra so sánh timestamp: Outbox Worker chỉ dispatch phản hồi nếu `created_at` của job lớn hơn hoặc bằng `conversation.last_message_at` của tin nhắn khách gần nhất. | Khách nhận phản hồi lạc đề cho câu hỏi trước đó khi đã gửi câu hỏi mới. |
| **CODE-P1-02** | FR-11, FR-23 / AC-11.2, AC-23.2 (`GAP-07B`) | `agent/omnichannel/giai_quyet.py:38`, `agent/api/inbox.py:240` | **Chốt chặn Resolve khi còn Pending Action / Task:** Chặn đóng hội thoại khi còn công việc chưa hoàn thành.<br>• *Nguyên tắc nghiệp vụ:* Phải kiểm tra **toàn bộ các trạng thái chưa hoàn tất** của bảng `cong_viec` (`trang_thai NOT IN ('hoan_thanh', 'da_huy')`), không chỉ kiểm tra riêng trạng thái `moi`.<br>• *Ràng buộc:* Tuyệt đối **không mở cờ bypass (force Resolve)** khi còn pending task trừ khi có quy tắc nghiệp vụ chính thức được phê duyệt. | Nhân viên vô tình đóng hội thoại trong khi yêu cầu hủy/sửa đơn của khách chưa xử lý xong. |
| **CODE-P1-03** | FR-23 / AC-23.3 (`GAP-07B`) | `agent/workers/` hoặc background scheduler | **Xây dựng tiến trình tự động Resolve khi hết thời gian chờ (Auto-Resolve):** Hiện tại codebase chưa có worker/scheduler nền thực hiện quét idle timeout.<br>• *Phương án A:* Bổ sung cron task / background loop quét `conversations` có `state in ('open', 'pending')` quá thời gian cấu hình không có tương tác và không có task mở.<br>• *Phương án B:* Tích hợp vào SLA Monitor loop quét định kỳ để chuyển trạng thái `resolved` kèm lý do hết thời gian chờ. | Hội thoại không có người tiếp tục bị treo ở trạng thái mở vô thời hạn. |
| **CODE-P1-04** | FR-24 / AC-24.5, AC-24.6 (`GAP-07D`) | `agent/omnichannel/sla.py:31`, migration `0005_routing_sla.sql` | **Bổ sung sự kiện cảnh báo SLA Warning (50% thời hạn):** Cập nhật check constraint trong `sla_events` để cho phép `first_response_warning` và `resolution_warning`. Thêm logic trong `mark_breaches()` bắn event warning tại mốc 5 phút (High) và 15 phút (Normal). | Nhân viên và quản lý không nhận được cảnh báo sớm trước khi hội thoại bị Breach. |
| **CODE-P1-05** | FR-24 / AC-24.7 (`GAP-07E`) | `agent/core/gio_lam_viec.py`, `agent/omnichannel/inbox_service.py` | **Tính toán hạn SLA theo Giờ làm việc 08:00–21:00:** Xây dựng hàm `tinh_deadline_theo_gio_lam_viec(start_time, minutes)`: nếu thời gian cộng vượt qua 21:00, thời gian còn lại sẽ được cộng dồn tiếp tục từ 08:00 sáng hôm sau. | Hội thoại đến vào 20:55 bị tính trễ hạn vào lúc nửa đêm khi không có nhân viên trực ca. |
| **CODE-P1-06** | FR-13, FR-14 / AC-13.1, AC-14.2 (`GAP-04`) | `agent/schema.sql`, `agent/core/rag.py` | **Phân biệt tri thức Draft/Published trong CSDL:** Tạo migration thêm cột `status` (`draft`/`published`), `published_at` vào bảng `documents`. Cập nhật hàm `rag.retrieve()` chỉ tìm kiếm các chunk thuộc tài liệu có `status = 'published'`. | AI có thể vô tình trích xuất các tài liệu nháp nội bộ chưa được phê duyệt để trả lời khách. |
| **CODE-P1-07** | FR-29 / AC-29.2, AC-29.3 (`GAP-06`) | `agent/shipping/` hoặc `agent/erp/vong_dong_bo.py` | **Tiến trình đối soát vận chuyển tự động (Shipping Reconciliation):** Xử lý giao dịch tạo vận đơn bị timeout.<br>• *Phương án A:* Xây dựng tiến trình nền đối soát vận chuyển độc lập định kỳ tra cứu GHN theo `client_order_code`.<br>• *Phương án B:* Mở rộng worker `vong_dong_bo.py` hiện có để quản lý chung cả đối soát ERP và đối soát Shipping.<br>• *Phương án C:* Kiểm tra đối soát theo cơ chế On-demand (check-before-retry) khi nhân viên tải lại đơn hoặc bấm thử lại. | Vận đơn bị treo lơ lửng khi mạng chập chờn, nhân viên phải kiểm tra thủ công ngoài cổng GHN. |
| **CODE-P1-08** | FR-19, FR-20 / AC-19.3, AC-20.4 (`GAP-05`) | `agent/api/erp.py`, `dashboard/app.js` | **Cơ chế ghi nhận kết quả sửa/hủy đơn vào Pending Action:**<br>• *Phương án 1 (Thao tác thủ công trên Dashboard - Khuyến nghị):* Nhân viên thao tác trên ERPNext, sau đó quay lại màn hình Native Dashboard bấm nút "Xác nhận kết quả sửa/hủy" để cập nhật trạng thái Pending Action và gửi tin thông báo cho khách.<br>• *Phương án 2 (Webhook tự động):* Thiết lập Server Script Webhook trên ERPNext để tự động bắn sự kiện về Backend CSKH khi Sales Order bị hủy hoặc sửa. | Pending Action trên Dashboard không được giải phóng, nhân viên không có luồng kết thúc xử lý. |

---

### Ưu tiên P2 – Tối ưu hóa và hoàn thiện nâng cao

| Mã Ứng viên | Yêu cầu liên quan | Vị trí mã nguồn | Hiện trạng & Mô tả công việc kỹ thuật |
|---|---|---|---|
| **CODE-P2-01** | FR-13 / AC-13.3 (`GAP-04`) | `agent/core/rag.py` | Bổ sung bảng `document_versions` lưu snapshot nội dung tài liệu tri thức để hỗ trợ tính năng Rollback phiên bản khi cần thiết. |
| **CODE-P2-02** | Toàn hệ thống (`GAP-09`) | `agent/channels/chatwoot.py` | Đóng gói hoặc tách riêng Chatwoot adapter, bổ sung kiểm tra cảnh báo cấu hình nếu phát hiện cùng kết nối chung một Fanpage với Native Webhook. |

---

## 2. NHÓM ỨNG VIÊN ĐIỀU CHỈNH TÀI LIỆU (DOCUMENTATION CANDIDATES)
*Tổng cộng: **5 ứng viên Tài liệu**.*

| Mã Ứng viên | Tài liệu cần điều chỉnh | Nội dung kiến nghị cập nhật | Mục tiêu |
|---|---|---|---|
| **DOC-01** | `Phân tích nghiệp vụ khoá luận (6).pdf` (Practice #20, System Architecture) | **Đề xuất Change Request CR-001 (Proposed – Pending Confirmation):** Đệ trình đề xuất đưa kiến trúc Native Inbox vào tài liệu lõi làm Single Source of Truth; điều chỉnh Chatwoot thành adapter tham khảo/tùy chọn (chờ xác nhận nội bộ). | Thống nhất ranh giới kiến trúc và chuẩn bị phương án bảo vệ khóa luận. |
| **DOC-02** | `Phân tích nghiệp vụ khoá luận (6).pdf` (Practice #18 & #19) | **Cập nhật Bảng Ánh xạ Kiểm thử (Test Traceability Matrix):** Phân định rõ giữa Unit Tests (thực thi trên từng component) và Integration/E2E Tests; cập nhật Test ID chính xác từ thư mục `tests/`. | Cung cấp hồ sơ kiểm chứng minh bạch, phân biệt rõ Executed Evidence và Static Evidence. |
| **DOC-03** | `Phân tích nghiệp vụ khoá luận (6).pdf` (Mô hình Dữ liệu & Bảo mật) | **Bổ sung các thành phần kiến trúc đã hiện diện trong code:** Bổ sung đặc tả kỹ thuật cho `CredentialVault` (quản lý khóa AES-GCM), thực thể `channel_accounts`, và hệ thống cấu hình động `cau_hinh_dong`. | Phản ánh đầy đủ năng lực bảo mật và khả năng mở rộng đa kênh của hệ thống. |
| **DOC-04** | `Phân tích nghiệp vụ khoá luận (6).pdf` (Practice #20 - CR-002, AC-23.5) | **Hiệu chỉnh mô tả CR-002 (Handling Extension):** Làm rõ nội dung CR-002 là "Gia hạn thời gian xử lý hội thoại Manual Mode" (không phải Proactive AI Re-engagement). Xác định trạng thái là Đề xuất xem xét (Pending CR-002) cho giai đoạn tiếp theo. | Đồng bộ chuẩn xác định danh và nội dung yêu cầu với Bảng 199 của tài liệu BA. |
| **DOC-05** | `Phân tích nghiệp vụ khoá luận (6).pdf` (Phụ lục Tuân thủ) | **Bổ sung Phụ lục Tuân thủ Quyền Chủ thể Dữ liệu (DSR Compliance):** Ghi nhận module `agent/core/yeu_cau_chu_the.py` triển khai theo Luật BV dữ liệu cá nhân 91/2025/QH15. | Nâng cao giá trị học thuật và tính pháp lý thực tiễn cho đề tài khóa luận. |

---

## 3. NHÓM ỨNG VIÊN BỔ SUNG KIỂM THỬ (TEST ADDITION CANDIDATES)
*Tổng cộng: **7 ứng viên Kiểm thử**.*

| Mã Ứng viên | Yêu cầu cần kiểm chứng | File kiểm thử đề xuất | Kịch bản kiểm thử cần bổ sung |
|---|---|---|---|
| **TEST-01** | AC-11.3 (`GAP-07C`) | `tests/test_reopen_sla_reset.py` | Kiểm thử việc mở lại hội thoại đã resolved (`mo_lai_neu_da_giai_quyet`) và xác nhận rằng `first_response_due_at` được cấp mới thành công sau khi sửa trigger PostgreSQL. |
| **TEST-02** | AC-11.2 & AC-23.2 (`GAP-07B`) | `tests/test_chan_resolve_khi_con_task.py` | Kiểm thử chốt chặn: gửi yêu cầu resolve một hội thoại đang có bản ghi `cong_viec` ở các trạng thái chưa hoàn tất (`moi`, `dang_xu_ly`), kỳ vọng hệ thống từ chối và giữ nguyên trạng thái mở. |
| **TEST-03** | AC-23.3 (`GAP-07B`) | `tests/test_auto_resolve_worker.py` | Kiểm thử tiến trình nền quét idle timeout tự động chuyển `state = 'resolved'` khi hội thoại quá hạn chờ và không còn task mở. |
| **TEST-04** | AC-24.5 & AC-24.6 (`GAP-07D`) | `tests/test_sla_warning_events.py` | Giả lập thời gian trôi qua 50% hạn SLA (5 phút với High, 15 phút với Normal); xác nhận sự kiện `first_response_warning` được tạo thành công trong `sla_events`. |
| **TEST-05** | AC-24.7 (`GAP-07E`) | `tests/test_sla_gio_lam_viec_pause.py` | Tạo hội thoại lúc 20:50 với hạn 30 phút; kiểm chứng deadline được tính là 08:20 sáng hôm sau, không phát sinh vi phạm breach trong đêm. |
| **TEST-06** | AC-07.2, QR-01 (`GAP-03`) | `tests/test_superseded_batch_cancellation.py` | Giả lập khách gửi tin nhắn thứ hai trong khi AI tương tác lượt một đang chạy ở Auto Mode; kiểm chứng rằng batch phản hồi cũ bị đánh dấu `SUPERSEDED` và không được gửi ra Outbox. |
| **TEST-07** | AC-27.3, AC-28.2, AC-29.4 (`GAP-02`) | `tests/test_shipping_erp_sync.py` | Mock GHN API tạo vận đơn thành công; kiểm chứng hệ thống gọi tiếp sang mock ERPNext cập nhật mã vận đơn và trạng thái giao nhận. |

---

## 4. TỔNG HỢP VÀ PHÂN BỔ NGUỒN LỰC ƯỚC TÍNH

- **Tổng số ứng viên Code:** 11 ứng viên (2 P0, 7 P1, 2 P2)
- **Tổng số ứng viên Tài liệu:** 5 ứng viên
- **Tổng số ứng viên Kiểm thử:** 7 ứng viên
- **Trạng thái thực thi:** Toàn bộ danh mục trên ở trạng thái **Đề xuất (Candidate)** chờ Tech Lead và Nhóm dự án xem xét.
