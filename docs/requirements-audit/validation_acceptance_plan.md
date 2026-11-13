# Validation & Acceptance Plan – Release 1 (RB-R1-002)

**Ngày lập:** 07/11/2026  
**Phiên bản:** v1.0 (Task G1-06A)  
**Phạm vi:** Kế hoạch kiểm chứng chất lượng và tiêu chuẩn nghiệm thu toàn diện cho Khóa luận Tốt nghiệp AI Agent (`AIAgent_mar`), tái sử dụng tối đa 338 file kiểm thử sẵn có trong repository.

---

## MỤC LỤC
1. [Nguyên tắc Kiểm chứng & Tiêu chuẩn Nghiệm thu](#1-nguyên-tắc-kiểm-chứng--tiêu-chuẩn-nghiệm-thu)
2. [Kế hoạch Kiểm chứng 6 Phân hệ Kỹ thuật Cốt lõi](#2-kế-hoạch-kiểm-chứng-6-phân-hệ-kỹ-thuật-cốt-lõi)
   - [2.1. Zalo OA & Facebook Messenger End-to-End](#21-zalo-oa--facebook-messenger-end-to-end)
   - [2.2. Native Inbox, Human Handover & SLA](#22-native-inbox-human-handover--sla)
   - [2.3. AI Agent, RAG Hybrid Search & Guardrails](#23-ai-agent-rag-hybrid-search--guardrails)
   - [2.4. ERPNext Integration, Pending Actions & Shipping](#24-erpnext-integration-pending-actions--shipping)
   - [2.5. RBAC, Bảo vệ PII & Structured Audit Trail](#25-rbac-bảo-vệ-pii--structured-audit-trail)
   - [2.6. Outbox Pattern, Idempotency, Timeout & Worker Recovery](#26-outbox-pattern-idempotency-timeout--worker-recovery)
3. [Ma trận Kiểm chứng 26 Quality Requirements (QR-01 đến QR-26)](#3-ma-trận-kiểm-chứng-26-quality-requirements-qr-01-đến-qr-26)
4. [Kế hoạch Nghiệm thu Toàn diện 18 Use Cases (UC-01 đến UC-18)](#4-kế-hoạch-nghiệm-thu-toàn-diện-18-use-cases-uc-01-đến-uc-18)
5. [Quy trình Thực thi Kiểm thử và Thu thập Bằng chứng](#5-quy-trình-thực-thi-kiểm-thử-và-thu-thập-bằng-chứng)

---

## 1. NGUYÊN TẮC KIỂM CHỨNG & TIÊU CHUẨN NGHIỆM THU

1. **Tái sử dụng tối đa bộ test hiện có:** Repository hiện có **338 file kiểm thử** trong thư mục `tests/` với độ bao phủ cao. Kế hoạch này ánh xạ trực tiếp các test suite sẵn có vào từng yêu cầu nghiệp vụ, không mặc định cần viết lại từ đầu. Chỉ bổ sung mới cho các điểm thiếu hụt đã phát hiện (`GAP-02`, `GAP-03`, `GAP-07B`, `GAP-07C`, `GAP-07D`, `GAP-07E`).
2. **Tôn trọng Executed Evidence:** Chỉ công nhận một yêu cầu ở mức `VERIFIED` khi có log chạy pytest thực tế trên snapshot mã nguồn hiện hành. Không chấp nhận việc suy diễn trạng thái chỉ dựa trên sự tồn tại của file mã nguồn (Static Evidence).
3. **Môi trường cách ly an toàn:** Toàn bộ quá trình kiểm chứng sử dụng CSDL test độc lập (PostgreSQL test container), mock network client (`httpx.MockTransport`) cho API bên ngoài (Meta, Zalo, GHN, ERPNext, Gemini LLM). Tuyệt đối không gọi tới endpoint production hoặc làm thay đổi CSDL thật.
4. **Tiêu chuẩn "Không chấp nhận ngoại lệ" đối với P0:** Hai lỗi logic P0 (`GAP-07C` - Trigger Reopen SLA và `GAP-02` - Đồng bộ Vận đơn sang ERPNext) bắt buộc phải đạt 100% assertions trước khi tiến hành nghiệm thu các phân hệ khác.

---

## 2. KẾ HOẠCH KIỂM CHỨNG 6 PHÂN HỆ KỸ THUẬT CỐT LÕI

### 2.1. Zalo OA & Facebook Messenger End-to-End
- **Mục tiêu:** Kiểm chứng tính toàn vẹn của chu trình tiếp nhận tin nhắn từ các kênh bên ngoài, phân giải tài khoản kênh (`channel_accounts`), bảo mật chữ ký HMAC, chuẩn hóa định dạng tin nhắn và phản hồi hai chiều.
- **Các file test sẵn có tái sử dụng:**
  - `tests/test_account_aware_channels.py`: Kiểm chứng tin nhắn inbound bắt buộc gắn `account_id`, kiểm tra tài khoản hoạt động/bị vô hiệu hóa, cô lập token giữa các kênh.
  - `tests/test_account_routing.py`: Kiểm thử định tuyến tài khoản kênh và không gọi provider trực tiếp từ web process.
  - `tests/test_native_webhooks.py`: Kiểm tra tiếp nhận webhook chuẩn hóa đa kênh.
  - `tests/test_oauth_zalo_oa.py`: Xác thực OAuth token và xác thực chữ ký Webhook Zalo OA.
- **Tiêu chuẩn nghiệm thu:**
  - 100% tin nhắn gửi từ Zalo OA và Messenger webhook được lưu bền vững vào bảng `messages` và `conversations`.
  - Webhook giả mạo chữ ký hoặc thiếu `account_id` hợp lệ bị từ chối với mã lỗi 401/403, không tạo bản ghi rác.

---

### 2.2. Native Inbox, Human Handover & SLA
- **Mục tiêu:** Kiểm chứng luồng điều phối hội thoại, chuyển đổi Handling Mode (`auto` $\rightarrow$ `assist` $\rightarrow$ `human` $\rightarrow$ `resolved`), phân công Optimistic Concurrency Control (OCC), và tính toán hạn SLA chính xác.
- **Các file test sẵn có tái sử dụng:**
  - `tests/test_inbox_api.py`: Kiểm thử API đọc danh sách hội thoại, chi tiết tin nhắn, nhân viên gửi phản hồi.
  - `tests/test_routing_service.py`: Kiểm thử tiếp quản (`takeover`), từ chối xung đột version khi hai nhân viên cùng nhận, và giải phóng hội thoại.
  - `tests/test_dat_che_do_hoi_thoai.py`: Kiểm thử chuyển đổi Handling Mode.
  - `tests/test_sla.py`: Kiểm thử SLA Monitor quét vi phạm `first_response_breached` và cơ chế heartbeat.
  - `tests/test_gio_lam_viec.py`: Kiểm thử nhận diện khung giờ làm việc 08:00–21:00 và câu chào tự động ngoài giờ.
  - `tests/test_dashboard_khong_nhap_nhay.py`: Kiểm thử giao diện Native Inbox không bị giật nhấp nháy khi có cập nhật mới.
- **Test bổ sung sau khi sửa code:**
  - `tests/test_reopen_sla_reset.py` (`TASK-TEST-01`): Xác minh SLA deadline được cấp mới thành công sau khi sửa trigger PostgreSQL.
  - `tests/test_chan_resolve_khi_con_task.py` (`TASK-TEST-02`): Xác minh từ chối Resolve khi còn task `moi` hoặc `dang_lam`.
  - `tests/test_auto_resolve_worker.py` (`TASK-TEST-03`): Xác minh worker quét idle 4 giờ tự động đóng hội thoại.
  - `tests/test_sla_warning_events.py` (`TASK-TEST-04`): Bắn cảnh báo SLA Warning ở mốc 5 phút (High) và 15 phút (Normal).
  - `tests/test_sla_gio_lam_viec_pause.py` (`TASK-TEST-05`): Tạm dừng và cộng dồn hạn SLA qua đêm ngoài khung 08:00–21:00.

---

### 2.3. AI Agent, RAG Hybrid Search & Guardrails
- **Mục tiêu:** Kiểm chứng khả năng sinh câu trả lời tự động, trích xuất căn cứ từ cơ sở tri thức RAG, kiểm soát trần chi phí và hàng rào phòng thủ an toàn (Guardrails).
- **Các file test sẵn có tái sử dụng:**
  - `tests/test_khach_cua_ai.py`: Kiểm thử pipeline AI Agent tiếp nhận và phản hồi khi ở Auto Mode.
  - `tests/test_cham_mot_luot.py` & `test_cham_nhieu_luot.py`: Kiểm thử độ nhất quán và phong cách phản hồi qua nhiều lượt chat.
  - `tests/test_phong_thu.py` & `test_api_phong_thu.py`: Kiểm thử chặn Prompt Injection, từ chối dọa kiện, dọa bắt đền.
  - `tests/test_agent_nhin_anh.py`: Kiểm thử chặn chẩn đoán da liễu / đơn thuốc y khoa từ ảnh khách gửi.
  - `tests/test_chuyen_nguoi_tre_em_va_cam_ket.py`: Chuyển người ngay khi phát hiện đối tượng nhạy cảm hoặc câu hứa hẹn.
  - `tests/test_bo_cau_vang_hang_that.py`: Kiểm thử AI từ chối suy đoán khi không tìm thấy tri thức.
  - `tests/test_rag_embedding_gemini_api.py`: Kiểm thử truy xuất RAG Hybrid Search (Vector + Full-text BM25/RRF).
  - `tests/test_ngan_sach_ngay.py`: Kiểm thử chạm trần chi phí ngày tự động dừng gọi LLM và leo thang cho nhân viên.
  - `tests/test_ky_nang.py` & `test_tools_khong_nap_danh_muc_thua.py`: AI chỉ được gọi tool nằm trong danh mục kích hoạt.
- **Test bổ sung sau khi sửa code:**
  - `tests/test_superseded_batch_cancellation.py` (`TASK-TEST-06`): Xác minh thu hồi batch AI cũ (`SUPERSEDED`) khi khách nhắn tin mới trong Auto Mode.

---

### 2.4. ERPNext Integration, Pending Actions & Shipping
- **Mục tiêu:** Kiểm chứng luồng tra cứu đơn hàng, quy trình chốt đơn 5 bước có xác nhận, tiếp nhận yêu cầu sửa/hủy đơn và tạo vận đơn GHN liên kết ERPNext.
- **Các file test sẵn có tái sử dụng:**
  - `tests/test_tra_cuu_don_that.py`: Tra cứu đơn hàng từ ERPNext, kiểm tra quyền sở hữu đơn theo `conversation_id`.
  - `tests/test_kho_gia_tu_erp.py`: Tra cứu giá và tồn kho trực tiếp từ CSDL/ERP.
  - `tests/test_chot_don_doc_ton_song.py`: Quy trình tạo đơn có kiểm soát 5 chốt (khách xác nhận, đủ thông tin, đọc tồn sống, trần tự duyệt, khóa chống trùng).
  - `tests/test_xin_huy_don.py`: Khách xin hủy đơn $\rightarrow$ Ghi nhận cờ `yeu_cau_huy_luc`, tạo Pending Action, không tự hủy trực tiếp.
  - `tests/test_sua_ban_nhap.py`: Ghi nhận yêu cầu sửa đơn và tạo Pending Action.
  - `tests/test_ghi_don_sang_erp.py`: Đồng bộ Sales Order sang ERPNext.
  - `tests/test_vong_dong_bo_erp.py`: Vòng đối soát 4 lưới bảo vệ tự động phục hồi đơn ERP bị kẹt.
  - `tests/test_van_chuyen_ghn.py`: Tạo vận đơn GHN, map enum trạng thái `InternalShippingStatus`.
  - `tests/test_hoan_thien_luong.py`: Kiểm tra Advisory Lock `pg_try_advisory_lock` chống bấm tạo vận đơn trùng lặp.
- **Test bổ sung sau khi sửa code:**
  - `tests/test_shipping_erp_sync.py` (`TASK-TEST-07`): Xác minh gọi REST API cập nhật mã vận đơn và trạng thái GHN sang ERPNext.

---

### 2.5. RBAC, Bảo vệ PII & Structured Audit Trail
- **Mục tiêu:** Kiểm chứng phân quyền kiểm soát truy cập theo vai trò (Role-Based Access Control), che giấu thông tin định danh cá nhân (PII) và ghi nhật ký kiểm toán có cấu trúc.
- **Các file test sẵn có tái sử dụng:**
  - `tests/test_can_quyen.py`: Middleware `can_quyen` chặn các truy cập trái thẩm quyền đối với `don.doc`, `don.sua`, `hoi_thoai.doc`, `hoi_thoai.sua`.
  - `tests/test_quyen_phien_that.py`: Kiểm tra phân quyền thực tế trên session người dùng.
  - `tests/test_api_vai_tro.py`: Quản lý danh sách vai trò người dùng (agent, manager, admin).
  - `tests/test_tra_cuu_don_that.py::test_chan_doc_don_nguoi_khac`: Che giấu PII (số điện thoại, địa chỉ) khi khách hỏi đơn không thuộc quyền sở hữu.
  - `tests/test_yeu_cau_chu_the.py`: Kiểm tra toàn bộ sổ yêu cầu chủ thể dữ liệu (DSR Xem/Sửa/Xóa dữ liệu cá nhân theo Luật 91/2025/QH15).

---

### 2.6. Outbox Pattern, Idempotency, Timeout & Worker Recovery
- **Mục tiêu:** Kiểm chứng tính bền vững của tầng truyền thông điệp, bảo đảm không mất tin nhắn, không gửi lặp và tự phục hồi khi tiến trình gặp sự cố đột ngột.
- **Các file test sẵn có tái sử dụng:**
  - `tests/test_outbound_enqueue.py`: Tin nhắn gửi ra được xếp hàng bền vững vào `outbox_jobs` với khóa idempotency.
  - `tests/test_webhook_ledger.py::test_claim_trung_dedupe_key`: Kiểm tra Dedupe key SHA256 chống trùng webhook từ nhà mạng.
  - `tests/test_inbox_outbox_schema.py`: Kiểm tra ràng buộc duy nhất và schema CSDL của Inbox/Outbox.
  - `tests/test_thu_lai_loi_thoang_qua.py`: Outbox Worker thực hiện exponential backoff retry khi gặp lỗi mạng tạm thời.
  - `tests/test_phuc_hoi_duoc.py`: Sử dụng `SELECT FOR UPDATE SKIP LOCKED` trên `outbox_jobs` giúp worker nhả khóa an toàn khi bị restart đột ngột, không gửi nhân đôi.
  - `tests/test_bang_nghiem_thu.py`: Kiểm thử tổng hợp các kịch bản lỗi kênh ngoại vi và phục hồi.

---

## 3. MA TRẬN KIỂM CHỨNG 26 QUALITY REQUIREMENTS (QR-01 ĐẾN QR-26)

| QR ID | Tên Yêu cầu Chất lượng | Chỉ tiêu kiểm định (Metric / Target) | File Test thực thi đối chiếu | Trạng thái Nghiệm thu |
|---|---|---|---|:---:|
| **QR-01** | Safety – Auto-Reply | 0 phản hồi AI trái quyền khi ở Manual Mode hoặc khi có tin mới | `tests/test_phong_thu.py`, `tests/test_superseded_batch_cancellation.py` | Sẵn sàng nghiệm thu (sau TASK-CODE-03) |
| **QR-02** | Safety – ERP Access | AI chỉ đọc và chuẩn bị đơn; 0 công cụ ghi/sửa ERP trực tiếp | `tests/test_xin_huy_don.py`, `tests/test_tools_khong_nap_danh_muc_thua.py` | **VERIFIED – Executed** |
| **QR-03** | Security – Order Authorization | 0 rò rỉ đơn hàng sang hội thoại khác | `tests/test_tra_cuu_don_that.py::test_chan_doc_don_nguoi_khac` | **VERIFIED – Executed** |
| **QR-04** | Security – RBAC | 100% API nhạy cảm được bảo vệ bởi middleware `can_quyen` | `tests/test_can_quyen.py`, `tests/test_quyen_phien_that.py` | **VERIFIED – Executed** |
| **QR-05** | Security – PII Protection | 100% số điện thoại và địa chỉ nhạy cảm được che giấu | `tests/test_tra_cuu_don_that.py` | **VERIFIED – Executed** |
| **QR-06** | Reliability – Assignment | Tối đa 1 Assignee hiệu lực; 0 xung đột gán việc đồng thời | `tests/test_routing_service.py::test_takeover_xung_dot_version` | **VERIFIED – Executed** |
| **QR-07** | Reliability – Message Deduplication | 0 xử lý nghiệp vụ trùng khi webhook gửi lặp | `tests/test_webhook_ledger.py::test_claim_trung_dedupe_key` | **VERIFIED – Executed** |
| **QR-08** | Reliability – Message Delivery | At-least-once delivery; Outbox retry có kiểm soát | `tests/test_outbound_enqueue.py`, `tests/test_thu_lai_loi_thoang_qua.py` | **VERIFIED – Executed** |
| **QR-09** | AI Answer Quality – Groundedness | Phản hồi căn cứ trên RAG tri thức, không bịa đặt | `tests/test_rag_embedding_gemini_api.py`, `tests/test_bo_cau_vang_hang_that.py` | **VERIFIED – Executed** |
| **QR-10** | AI Answer Quality – Safe Fallback | Tự động chuyển người khi độ tự tin thấp hoặc thiếu dữ liệu | `tests/test_cham_mot_luot.py`, `tests/test_chuyen_nguoi_tre_em_va_cam_ket.py` | **VERIFIED – Executed** |
| **QR-11** | Performance – AI Response | Thời gian xử lý phản hồi trong ngưỡng chấp nhận được | `tests/test_khach_cua_ai.py` | **VERIFIED – Executed** |
| **QR-12** | Performance – Staff Inbox | Tải danh sách hội thoại nhanh, không lag | `tests/test_dashboard_khong_nhap_nhay.py` | **VERIFIED – Executed** |
| **QR-13** | Usability – Conversation Visibility | Hiển thị đầy đủ nhãn kênh, trạng thái, SLA badge và Assignee | `tests/test_dashboard_khong_nhap_nhay.py` | **VERIFIED – Executed** |
| **QR-14** | Usability – Human Workflow | Luồng tiếp quản, xử lý công việc và resolve rõ ràng | `tests/test_api_cong_viec.py`, `tests/test_chan_resolve_khi_con_task.py` | Sẵn sàng nghiệm thu (sau TASK-CODE-04) |
| **QR-15** | Availability | Tự phục hồi sau khi restart nhờ Heartbeat và SKIP LOCKED | `tests/test_phuc_hoi_duoc.py`, `tests/test_sla.py` | **VERIFIED – Executed** |
| **QR-16** | Scalability | Tách biệt hoàn toàn web ingest và background worker | `tests/test_outbound_enqueue.py` | **VERIFIED – Executed** |
| **QR-17** | Interoperability | Tương thích chuẩn REST API và webhook chuẩn hóa đa kênh | `tests/test_account_aware_channels.py`, `tests/test_van_chuyen_ghn.py` | **VERIFIED – Executed** |
| **QR-18** | Maintainability | Kiến trúc module hóa, migration CSDL có phiên bản rõ ràng | `tests/test_inbox_outbox_schema.py` | **VERIFIED – Executed** |
| **QR-19** | Verifiability & Observability | Ghi nhật ký có cấu trúc đầy đủ cho mọi hành vi quan trọng | `tests/test_routing_service.py`, `tests/test_hoan_thien_luong.py` | **VERIFIED – Executed** |
| **QR-20** | Safety – Transaction Confirmation | Bắt buộc khách xác nhận bản tóm tắt trước khi tạo đơn | `tests/test_chot_don_doc_ton_song.py` | **VERIFIED – Executed** |
| **QR-21** | Reliability – ERP Write | Idempotency key, transaction nguyên tử chống tạo đơn trùng | `tests/test_chot_don_doc_ton_song.py`, `tests/test_ghi_don_sang_erp.py` | **VERIFIED – Executed** |
| **QR-22** | Reliability – ERP Reconciliation | Vòng đối soát 4 lưới bảo vệ tự động phục hồi đơn kẹt | `tests/test_vong_dong_bo_erp.py` | **VERIFIED – Executed** |
| **QR-23** | AI Answer Quality – Truthful Status | Không bịa đặt trạng thái đơn hàng khi ERP lỗi mạng | `tests/test_luong_loi_dau_cuoi.py` | **VERIFIED – Executed** |
| **QR-24** | Observability – AI Usage and Cost | Ghi nhận token, model ID, chi phí lượt và trần chi phí ngày | `tests/test_api_phong_thu.py`, `tests/test_ngan_sach_ngay.py` | **VERIFIED – Executed** |
| **QR-25** | Reliability – Shipping API Idempotency | Advisory lock chống bấm đúp tạo 2 vận đơn cho 1 đơn hàng | `tests/test_hoan_thien_luong.py` | **VERIFIED – Executed** |
| **QR-26** | Reliability – Shipment Status Validity | Map chuẩn enum trạng thái GHN và đồng bộ về ERPNext | `tests/test_van_chuyen_ghn.py`, `tests/test_shipping_erp_sync.py` | Sẵn sàng nghiệm thu (sau TASK-CODE-02) |

---

## 4. KẾ HOẠCH NGHIỆM THU TOÀN DIỆN 18 USE CASES (UC-01 ĐẾN UC-18)

Bộ kiểm thử tích hợp End-to-End (`tests/test_e2e_use_cases.py` - `TASK-TEST-08`) sẽ mô phỏng hoàn chỉnh 18 ca sử dụng thực tế:

| UC ID | Tên Ca Sử dụng | Luồng Kiểm chứng Tích hợp End-to-End (E2E Test Flow) | Kịch bản Kiểm tra Cụ thể |
|---|---|---|---|
| **UC-01** | Gửi yêu cầu hỗ trợ | Webhook Ingest $\rightarrow$ Chuẩn hóa payload $\rightarrow$ Lưu `messages` & `conversations` | Khách gửi tin nhắn từ Zalo/Messenger, hệ thống lưu tin và kích hoạt pipeline. |
| **UC-02** | Xử lý hội thoại bằng AI | Inbound Message $\rightarrow$ Kiểm tra `mode='auto'` $\rightarrow$ RAG $\rightarrow$ LLM $\rightarrow$ Outbox | AI tự động sinh câu trả lời dựa trên tri thức RAG và gửi ra Outbox. |
| **UC-03** | Yêu cầu hỗ trợ từ nhân viên | AI nhận diện từ khóa khiếu nại / khách yêu cầu $\rightarrow$ Đổi `mode='human'` $\rightarrow$ Tạo `cong_viec` | Hội thoại chuyển sang hàng đợi chờ nhân viên, AI bị khóa quyền tự trả lời. |
| **UC-04** | Xem hàng đợi hội thoại | Gọi API `GET /api/inbox/conversations` kèm quyền `hoi_thoai.doc` | Trả về danh sách hội thoại có gắn nhãn kênh, trạng thái Unread/Pending, SLA badge. |
| **UC-05** | Tiếp quản hội thoại từ AI | Gọi API `POST /api/routing/takeover` có kiểm tra version OCC | Nhân viên A nhận việc thành công; nhân viên B nhận đồng thời bị báo lỗi 409 Conflict. |
| **UC-06** | Xem lịch sử & bối cảnh | Gọi API `GET /api/inbox/conversations/{id}/messages` $\rightarrow$ Đọc Customer Profile | Hiển thị toàn bộ timeline tin nhắn, ghi chú nội bộ và thuộc tính Customer 360. |
| **UC-07** | Phản hồi thủ công | Gọi API `POST /api/inbox/conversations/{id}/reply` $\rightarrow$ Outbox Worker | Nhân viên gửi tin nhắn thành công qua Outbox khi đang ở Manual Mode. |
| **UC-08** | Kết thúc phiên hỗ trợ | Nhân viên bấm Resolve $\rightarrow$ Kiểm tra chốt chặn Pending Task $\rightarrow$ Đổi `state='resolved'` | Từ chối đóng nếu còn task mở; cho phép đóng khi task đã xong; kích hoạt hỏi CSAT. |
| **UC-09** | Theo dõi và điều phối | Gọi API `GET /api/routing/admin/workload` $\rightarrow$ Reassign hội thoại | Quản lý xem tải làm việc của từng nhân viên và phân công lại hội thoại cho người khác. |
| **UC-10** | Quản lý tài khoản & phân quyền | Quản lý người dùng, gán vai trò (`agent`, `manager`, `admin`) | Kiểm tra phân quyền thực tế: agent không xem được cấu hình hệ thống, admin toàn quyền. |
| **UC-11** | Cấu hình kênh giao tiếp | Gọi API kết nối Channel Account $\rightarrow$ Mã hóa bằng `CredentialVault` | Thêm tài khoản Zalo OA / Fanpage mới; token được niêm phong AES-GCM an toàn. |
| **UC-12** | Cấu hình chính sách AI | Gọi API cập nhật `cau_hinh_dong` (prompt, model ID, trần chi phí) | Tham số cấu hình cập nhật ngay vào CSDL và áp dụng trong lượt chat kế tiếp. |
| **UC-13** | Tra cứu thông tin đơn hàng | Khách hỏi mã đơn $\rightarrow$ AI gọi tool `tra_cuu_don_hang` kiểm tra quyền sở hữu | Trả về đúng thông tin đơn hàng nếu thuộc hội thoại; từ chối và che PII nếu đơn của người khác. |
| **UC-14** | Tạo đơn hàng thông qua AI | AI thu thập sản phẩm $\rightarrow$ Kiểm tra tồn kho live $\rightarrow$ Tóm tắt $\rightarrow$ Khách xác nhận $\rightarrow$ Tạo đơn | Đơn hàng tạo thành công trên Postgres và đồng bộ sang ERPNext Sales Order. |
| **UC-15** | Yêu cầu chỉnh sửa đơn hàng | Khách yêu cầu sửa $\rightarrow$ AI gọi `xin_doi_tra` $\rightarrow$ Handover $\rightarrow$ Dashboard xác nhận | Pending Action được tạo; nhân viên sửa trên ERPNext và xác nhận hoàn tất trên Dashboard. |
| **UC-16** | Yêu cầu hủy đơn hàng | Khách yêu cầu hủy $\rightarrow$ AI gọi `xin_huy_don` $\rightarrow$ Gán `yeu_cau_huy_luc` $\rightarrow$ Dashboard duyệt | Pending Action được tạo; nhân viên hủy trên ERPNext và xác nhận hoàn tất trên Dashboard. |
| **UC-17** | Tạo vận đơn & đồng bộ ERP | Nhân viên bấm "Tạo vận đơn" $\rightarrow$ Advisory Lock $\rightarrow$ GHN API $\rightarrow$ ERPNext API | Vận đơn GHN tạo thành công, mã vận đơn được ghi nhận vào Postgres và ERPNext. |
| **UC-18** | Tra cứu trạng thái vận chuyển | Khách hỏi hành trình $\rightarrow$ Backend tra cứu GHN API $\rightarrow$ Map enum nội bộ | Trả về trạng thái giao hàng chuẩn xác (đang giao, đã giao, hoàn hàng) cho khách. |

---

## 5. QUY TRÌNH THỰC THI KIỂM THỬ VÀ THU THẬP BẰNG CHỨNG

### 5.1. Lệnh Thực thi Kiểm thử Tự động Chuẩn hóa

Tất cả các lệnh kiểm thử được chạy trong môi trường ảo của dự án (`.venv`) với cờ cách ly:

```bash
# 1. Chạy kiểm thử đơn vị cho toàn bộ các phân hệ lõi (35 file trọng điểm)
PYTHONPATH=. /Users/huynhlehoaibao/Documents/AIAgent_mar/.venv/bin/pytest \
    tests/test_account_aware_channels.py \
    tests/test_routing_service.py \
    tests/test_xin_huy_don.py \
    tests/test_gio_lam_viec.py \
    tests/test_van_chuyen_ghn.py \
    tests/test_vong_dong_bo_erp.py \
    tests/test_sla.py \
    -v --tb=short

# 2. Chạy kiểm thử cho các tính năng mới bổ sung (sau khi code xong)
PYTHONPATH=. /Users/huynhlehoaibao/Documents/AIAgent_mar/.venv/bin/pytest \
    tests/test_reopen_sla_reset.py \
    tests/test_chan_resolve_khi_con_task.py \
    tests/test_auto_resolve_worker.py \
    tests/test_sla_warning_events.py \
    tests/test_sla_gio_lam_viec_pause.py \
    tests/test_superseded_batch_cancellation.py \
    tests/test_shipping_erp_sync.py \
    -v

# 3. Chạy toàn bộ bộ kiểm thử tích hợp E2E cho 18 Use Cases và xuất file log nghiệm thu
PYTHONPATH=. /Users/huynhlehoaibao/Documents/AIAgent_mar/.venv/bin/pytest \
    tests/test_e2e_use_cases.py \
    -v --tb=short | tee docs/requirements-audit/e2e_test_execution.log
```

### 5.2. Tiêu chuẩn Thu thập và Lưu trữ Bằng chứng
1. **File log thực thi:** Mọi kết quả nghiệm thu phải được lưu thành file log văn bản tại thư mục `docs/requirements-audit/` (ví dụ `e2e_test_execution.log`).
2. **Cấu trúc log chuẩn:** Log phải thể hiện rõ:
   - Phiên bản Python và Pytest.
   - Danh sách các ca kiểm thử với nhãn `PASSED` màu xanh.
   - Thống kê tóm tắt cuối cùng: `X passed in Y.YYs`, 0 failed, 0 errors.
3. **Cập nhật Bảng Traceability:** Sau khi có log thực thi, cập nhật đường dẫn file log và thời điểm chạy vào Bảng 18.1 của tài liệu BA để hoàn thiện hồ sơ bảo vệ khóa luận.

