# DANH SÁCH VẤN ĐỀ TỒN ĐỌNG (BACKLOG) – KIỂM THỬ HỆ THỐNG

Danh sách ghi nhận các lỗi chức năng (BUG) và vấn đề trải nghiệm người dùng (UX) được phát hiện trong quá trình kiểm thử chấp nhận (UAT) và kiểm thử kỹ thuật, chuyển giao xử lý sau khi hoàn tất toàn bộ các gói kiểm thử.

---

## 1. STT 08 – Cấu hình API, Webhook và trạng thái kết nối

### [BUG-08-01] Bỏ sót sự kiện Audit khi kết nối lại tài khoản kênh (re-auth / refresh session)
- **Mức độ nghiêm trọng**: Medium (P2) - Tính toàn vẹn của Nhật ký kiểm toán.
- **Vị trí mã nguồn**: `agent/api/zalo_personal_webhook.py` (dòng 204–211).
- **Mô tả hiện tượng**:
  Khi người vận hành thực hiện kết nối lại tài khoản Zalo cá nhân (hoặc quét lại mã QR để làm mới phiên) trong lúc tài khoản đang ở trạng thái hoạt động (`status == 'active'`), backend kiểm tra điều kiện `if account.status != status:`. Do trạng thái không thay đổi (`active == active`), hàm `repository.update_status()` bị bỏ qua, dẫn đến không có sự kiện `channel_account.status_changed` nào được ghi vào bảng `events`.
- **Hệ quả**: Người vận hành không tìm thấy dấu vết kết nối lại trong màn hình **Hệ thống & Nhật ký → Nhật ký hoạt động**.
- **Hướng xử lý đề xuất**:
  Bổ sung ghi nhận sự kiện độc lập vào bảng `events` (ví dụ `kind = 'channel_account.reconnected'` hoặc `channel_account.session_refreshed`) bất kể trạng thái tài khoản có thay đổi hay không khi nhận callback `health` có `status == 'connected'`.

---

### [BUG-08-02] Hiển thị mã kỹ thuật thô và rỗng kết quả sự kiện kênh trong Nhật ký hoạt động
- **Mức độ nghiêm trọng**: Low/Medium (P2) - UX & Khả năng quan sát của người vận hành.
- **Vị trí mã nguồn**: `agent/core/nhat_ky_kiem_toan.py` (dòng 190–240 và dòng 380–415).
- **Mô tả hiện tượng**:
  1. Từ điển `NHAN_HANH_DONG` trong `nhat_ky_kiem_toan.py` thiếu ánh xạ nhãn tiếng Việt cho nhóm sự kiện `channel_account.*`. Tiêu đề dòng nhật ký hiển thị nguyên văn chuỗi tiếng Anh: `channel_account.status_changed`, `channel_account.identity_bound`, `channel_account.credentials_rotated`.
  2. Hàm `ket_qua(kind, sach)` chỉ tìm các khóa trong `_KHOA_KET_QUA = ("ket_qua", "ly_do", "reason", "loi", "error", "ghi_chu", "ma_don", "tieu_de", "trang_thai", "ten", "tag", "che_do")`. Trong khi sự kiện lưu `{"status": "active"}` hoặc `{"status": "disabled"}`. Do lệch tên khóa (`status` vs `trang_thai`), trường `ket_qua` bị rỗng `""`.
  3. Hàm truy vấn `tim()` chỉ JOIN với `conversations` và `nguoi_dung`, không JOIN với bảng `channel_accounts` để phân giải `ref_id` thành tên hiển thị của tài khoản kênh (như "Hoài Bảo", "CSKH").
- **Hệ quả**: Trên giao diện, người vận hành chỉ thấy dòng `channel_account.status_changed` do `Hệ thống` thực hiện, không biết hành động này là gì và thuộc tài khoản kênh nào.
- **Hướng xử lý đề xuất**:
  1. Thêm nhãn tiếng Việt vào `NHAN_HANH_DONG`:
     - `channel_account.status_changed`: `"Đổi trạng thái tài khoản kênh"`
     - `channel_account.identity_bound`: `"Liên kết danh tính tài khoản kênh"`
     - `channel_account.credentials_rotated`: `"Cập nhật thông tin xác thực kênh"`
  2. Bổ sung `status` vào `_KHOA_KET_QUA` hoặc chuẩn hóa lưu `trang_thai` trong `detail`.
  3. Bổ sung JOIN hoặc truy vấn phân giải `ref_id` sang `channel_accounts.display_name` khi `kind LIKE 'channel_account.%'`.

---

### [UX-08-09] Phân mảnh lịch sử cấu hình kết nối và thiếu dòng thời gian trạng thái kênh
- **Mức độ nghiêm trọng**: Low (P3) - Trải nghiệm người dùng.
- **Vị trí mã nguồn / giao diện**:
  - `agent/api/ket_noi_tich_hop.py` & `dashboard/app.js` (tab *Kết nối & Tích hợp*).
  - `agent/api/nhat_ky_api.py` & `dashboard/app.js` (tab *Nhật ký hoạt động*).
- **Mô tả hiện tượng**:
  1. Hệ thống có 2 bảng lưu vết cấu hình riêng biệt: bảng `lich_su_ket_noi` (hiển thị ở cuối tab *Kết nối & Tích hợp*) và bảng `events` (hiển thị ở tab *Nhật ký hoạt động*). Thao tác Bật/Tắt tài khoản kênh chỉ ghi vào `lich_su_ket_noi` với định danh rõ ràng ("Hoài Bảo", "tat", "admin"), trong khi ở màn hình Nhật ký hoạt động chung lại không có liên kết chéo.
  2. Lịch sử kiểm tra kết nối định kỳ và heartbeat (`account_health_events`) chỉ được dùng nội bộ cho panel thu gọn, người vận hành không có màn hình xem lịch sử kết nối/ngắt kết nối theo trục thời gian (timeline).
- **Hướng xử lý đề xuất**:
  1. Đồng bộ sự kiện thay đổi cấu hình kết nối từ `lich_su_ket_noi` vào luồng `events` hoặc cung cấp bộ lọc/liên kết nhanh từ Nhật ký hoạt động tới Lịch sử cấu hình kết nối.
  2. Bổ sung tab/panel xem lịch sử kết nối của từng kênh trực tiếp trong chi tiết tài khoản kênh.

---

## 2. STT 09 – Nhận diện đúng hội thoại nhóm và cá nhân

### [UX-09-01] Badge Nhóm xuất hiện trùng lặp ở cả Header và danh sách hội thoại
- **Mức độ nghiêm trọng**: Low (P3) - Trải nghiệm người dùng.
- **Vị trí giao diện**: `dashboard/app.js` (phần render danh sách hội thoại `convlist` và header chi tiết `convo__head`).
- **Mô tả hiện tượng**:
  Khi mở một cuộc trò chuyện nhóm (Zalo cá nhân nhóm), nhãn/badge `Nhóm` (hoặc `Zalo cá nhân · Nhóm`) đã hiển thị rõ ràng tại dòng hội thoại trong cột danh sách bên trái. Tuy nhiên, ở phần Header chi tiết của cuộc trò chuyện (bên cạnh tên nhóm), badge `Nhóm` lại tiếp tục được render thêm một lần nữa.
- **Hệ quả**: Giao diện hiển thị lặp thừa badge `Nhóm`, giảm diện tích hiển thị tiêu đề và không cần thiết.
- **Hướng xử lý đề xuất**:
  Rà soát logic render header trong `03-hoi-thoai.js` / `app.js`, chỉ giữ badge loại kênh (`Zalo cá nhân`) hoặc tinh gọn hiển thị badge nhóm ở một vị trí thống nhất.

---

## 3. STT 12 – Hệ thống phân quyền và gán quyền động (RBAC)

### [BUG-12-01] Lỗi chức năng phân quyền UI: Menu "Công việc" vẫn hiển thị khi thiếu quyền `cong_viec.doc`
- **Loại vấn đề**: Lỗi chức năng phân quyền giao diện (liên quan `TC-12-007`).
- **Mức độ nghiêm trọng**: Medium (P1) - Lộ menu điều hướng trái quyền.
- **Vị trí mã nguồn**: `dashboard/src/01b-dieu-huong.js` (`QUYEN_TAB["cv-ca-truc"]`).
- **Mô tả hiện tượng (Đã xác minh thực tế trên UI `kiemthu`)**:
  Tài khoản thử nghiệm chỉ được cấp quyền xem hội thoại (`hoi_thoai.doc`, không có `cong_viec.doc`), nhưng thanh điều hướng bên trái vẫn hiển thị mục **Công việc** thay vì ẩn đi (bằng chứng: `scratch/evidence_stt12/TC-12-007_readonly_ui.png`), do tab `cv-ca-truc` khai báo quyền thấy là `["hoi_thoai.doc"]`.
- **Hướng xử lý đề xuất**: Tách riêng hoặc kiểm tra đồng thời điều kiện hiển thị tab/menu Công việc gắn với quyền `cong_viec.doc`.

### [BUG-12-02] Lỗi chức năng phân quyền UI: Ô soạn tin nhắn, nút Gửi/đính kèm và nút Customer 360 không tự ẩn khi thiếu quyền
- **Loại vấn đề**: Lỗi chức năng phân quyền giao diện (liên quan `TC-12-007`).
- **Mức độ nghiêm trọng**: Medium (P1) - Chưa vô hiệu hóa/ẩn thao tác trái quyền trên giao diện (Backend vẫn chặn HTTP 403).
- **Vị trí mã nguồn**: `dashboard/src/03-hoi-thoai.js` (dòng 395–406, `#replyform`), `dashboard/src/03b-thanh-hoi-thoai.js` (dòng 143–144, `#open-contact`).
- **Mô tả hiện tượng (Đã xác minh qua mã nguồn giao diện)**:
  Khi nhân viên chỉ có quyền xem (`hoi_thoai.doc`) mà không có quyền trả lời (`hoi_thoai.tra_loi`) hoặc quyền xem khách (`khach.doc`), giao diện chi tiết hội thoại vẫn vẽ khung soạn trả lời `#replyform` (ô textarea, nút Gửi, nút đính kèm `📎`) và nút mở Customer 360 (`#open-contact`). Người dùng vẫn thấy và bấm được thao tác rồi mới nhận lỗi HTTP 403 từ Backend thay vì được ẩn/vô hiệu hóa trên UI.
- **Hướng xử lý đề xuất**: Bổ sung kiểm tra `state.toiQuyen.has("hoi_thoai.tra_loi")` để ẩn hoặc vô hiệu hóa `#replyform` (chỉ giữ lại nếu có quyền trả lời hoặc quyền ghi chú `hoi_thoai.ghi_chu` ở chế độ ghi chú), và kiểm tra `state.toiQuyen.has("khach.doc")` trước khi vẽ `#open-contact`.

### [UX-12-03] Hiển thị mã kỹ thuật thô trong bảng tick quyền và thiếu bộ lọc tìm kiếm
- **Mức độ nghiêm trọng**: Low (P3) - Trải nghiệm quản trị.
- **Vị trí mã nguồn**: `dashboard/src/24-nhan-su.js` (`nsvBangQuyen`, dòng 64).
- **Mô tả hiện tượng**:
  Form Tạo/Sửa vai trò hiển thị mã kỹ thuật (`<code>hoi_thoai.doc</code>`, `<code>cau_hinh.sua</code>`) bên cạnh nhãn tiếng Việt trên toàn bộ 40+ checkbox; đồng thời chưa có ô tìm kiếm nhanh tên quyền hay cảnh báo nổi bật cho các quyền nhạy cảm (như xóa khách, sửa cấu hình AI/API).
- **Hướng xử lý đề xuất**: Ẩn bớt hoặc thu gọn mã kỹ thuật vào tooltip/title, bổ sung ô lọc tìm kiếm nhanh và thẻ phân loại nhóm quyền nhạy cảm.

### [UX-12-04] Dùng hộp thoại `confirm()` mặc định của trình duyệt khi Ngừng dùng/Xoá vai trò
- **Mức độ nghiêm trọng**: Low (P3) - Đồng nhất giao diện.
- **Vị trí mã nguồn**: `dashboard/src/24-nhan-su.js` (dòng 480, 525).
- **Mô tả hiện tượng**:
  Thao tác "Ngừng dùng", "Dùng lại" và "Xoá" vai trò vẫn gọi `confirm(...)` nguyên bản của trình duyệt, không đồng nhất với hệ thống modal hộp thoại chung (`hoiHop`) của ứng dụng.
- **Hướng xử lý đề xuất**: Chuyển sang dùng modal hộp thoại xác nhận thống nhất của dashboard.

### [UX-12-05] Vai trò Quản trị không xem được danh sách quyền và tiêu đề panel bị rớt dòng
- **Mức độ nghiêm trọng**: Low (P3) - Trải nghiệm quản trị.
- **Vị trí mã nguồn**: `dashboard/src/24-nhan-su.js` (dòng 432, 490–492).
- **Mô tả hiện tượng**:
  Hàng vai trò **Quản trị** ẩn hoàn toàn nút thao tác nên không thể bấm để xem nhanh danh sách quyền bên trong; phần tiêu đề panel "Vai trò & Quyền" chứa ghi chú giải thích quá dài khiến nút "Tạo vai trò" bị đẩy xuống hàng dưới.
- **Hướng xử lý đề xuất**: Thêm nút "Xem quyền" (chỉ đọc) cho vai trò Quản trị và tách dòng ghi chú ra dưới tiêu đề để giữ nút "Tạo vai trò" nằm gọn cùng hàng tiêu đề.

---

## 4. STT 13 – Vai trò động và quản lý nhân viên

### [Cảnh báo vận hành] Tài khoản `staff_view` trên `marketing_agent` đang giữ vai trò Quản trị
- **Phạm vi**: Dữ liệu thật `marketing_agent` (chỉ kiểm tra đọc, chưa chỉnh sửa).
- **Chi tiết**: Tài khoản `staff_view` (`Nhân viên Xem`, trạng thái `khoa: True`) hiện đang được gán `['Quản trị', 'Nhân viên']`. Nếu mở khoá mà chưa gỡ vai trò `Quản trị`, tài khoản này sẽ sở hữu toàn quyền hệ thống. Đề nghị quản trị viên rà soát và gỡ vai trò `Quản trị` khỏi `staff_view` trước khi mở khoá.

### [UX-13-01] Thiếu ô tìm kiếm và bộ lọc trong danh sách Nhân viên
- **Mức độ nghiêm trọng**: Low (P3) - Trải nghiệm quản trị.
- **Vị trí mã nguồn**: `dashboard/src/24-nhan-su.js` (`GAN_TAB["ns-nhan-vien"]`).
- **Mô tả hiện tượng**: Tab *Nhân viên* hiện chỉ liệt kê toàn bộ danh sách tài khoản, không có ô tìm kiếm theo tên/email/username hay bộ lọc theo vai trò và trạng thái (Đang làm / Đã khoá).
- **Hướng xử lý đề xuất**: Bổ sung thanh tìm kiếm và bộ lọc trạng thái/vai trò ở đầu panel Nhân viên.

### [UX-13-02] Thiếu thao tác Đặt lại mật khẩu cho nhân viên từ màn hình quản trị
- **Mức độ nghiêm trọng**: Low/Medium (P2) - Vận hành nhân sự.
- **Vị trí mã nguồn**: `dashboard/src/24-nhan-su.js` (`nsvDongNguoi`, `nsvFormNguoi`).
- **Mô tả hiện tượng**: Quản trị viên tạo được mật khẩu ban đầu và sửa họ tên/email/vai trò, nhưng không có nút hỗ trợ đặt lại mật khẩu tạm nếu nhân viên quên mật khẩu (chỉ có cơ chế nhân viên tự đổi mật khẩu của bản thân).
- **Hướng xử lý đề xuất**: Bổ sung nút "Đặt lại mật khẩu" (kèm thu hồi phiên cũ) cho quản trị viên có quyền `nguoi_dung.sua`.

### [UX-13-03] Quy trình Khoá/Mở khoá còn dùng `confirm()` trình duyệt và xác nhận hai lớp
- **Mức độ nghiêm trọng**: Low (P3) - Đồng nhất giao diện.
- **Vị trí mã nguồn**: `dashboard/src/24-nhan-su.js` (`nsvKhoa`, dòng 194, 209, 213, 214).
- **Mô tả hiện tượng**: Các bước xác nhận Mở khoá / Khoá tài khoản vẫn gọi hộp thoại `confirm()` mặc định của trình duyệt; khi nhân viên đang giữ việc, quản trị viên phải qua modal chuyển việc rồi lại bấm tiếp `confirm()` lần nữa.
- **Hướng xử lý đề xuất**: Gộp bước xác nhận khoá vào modal chuẩn `hoiHop` của hệ thống.

### [UX-13-04] Khung xem quyền nhân viên chỉ hiện quyền đang có, khó đối chiếu quyền thiếu
- **Mức độ nghiêm trọng**: Low (P3) - Khả năng quan sát.
- **Vị trí mã nguồn**: `dashboard/src/24-nhan-su.js` (`nsvVeQuyenNguoi`, dòng 336–349).
- **Mô tả hiện tượng**: Bấm nút "Quyền" trên hàng nhân viên chỉ liệt kê các quyền họ đang sở hữu (kèm tên vai trò cấp), không có chế độ xem toàn bộ danh mục để đối chiếu nhanh quyền nào chưa có.
- **Hướng xử lý đề xuất**: Thêm tuỳ chọn "Hiện cả quyền chưa cấp" trong bảng xem quyền cá nhân.

### [UX-13-05] Thông báo hướng dẫn đổi mật khẩu sau khi tạo nhân viên biến mất quá nhanh
- **Mức độ nghiêm trọng**: Low (P3) - Trải nghiệm nhập liệu.
- **Vị trí mã nguồn**: `dashboard/src/24-nhan-su.js` (`nsvLuuNguoi`, dòng 313–314).
- **Mô tả hiện tượng**: Sau khi tạo nhân viên thành công, hướng dẫn quan trọng ("Báo họ đổi mật khẩu ở mục Tôi" hoặc "Chưa có vai trò nên mọi màn đều trống") chỉ hiện bằng `toast` thoáng qua và tự tắt.
- **Hướng xử lý đề xuất**: Hiển thị thông báo kết quả cố định kèm thông tin bàn giao tài khoản sau khi tạo thành công cho tới khi người dùng đóng.

### [UX-13-06] Hàng nhân viên bị dài và rớt dòng khi gán nhiều vai trò cùng nút thao tác
- **Mức độ nghiêm trọng**: Low (P3) - Bố cục hiển thị.
- **Vị trí mã nguồn**: `dashboard/src/24-nhan-su.js` (`nsvDongNguoi`, dòng 249–256).
- **Mô tả hiện tượng**: Phần `.row__side` đặt chung tất cả pill vai trò, pill số hội thoại/công việc đang giữ và 3–4 nút thao tác (`Quyền`, `Sửa`, `Chuyển việc`, `Khoá`), dễ gây chật hoặc rớt dòng lộn xộn khi nhân viên mang 3+ vai trò.
- **Hướng xử lý đề xuất**: Tách hàng pill vai trò nằm gọn dưới phần thông tin chính `.row__main`, giữ `.row__side` chỉ cho các nút hành động.

---

## 5. STT 14 – Quản lý công việc CSKH (Hệ thống phân công công việc)

### [UX-14-01] Thiếu chip chọn nhanh và chỉ báo số lượng kết quả theo điều kiện lọc
- **Mức độ nghiêm trọng**: Medium (P2) - Năng suất vận hành CSKH.
- **Vị trí mã nguồn**: `dashboard/src/25-cong-viec.js` (`cvxVeKhung`, dòng 397–410).
- **Mô tả hiện tượng**:
  Thanh bộ lọc hiện tại sử dụng các thẻ `<select>` truyền thống cho Trạng thái, Ưu tiên, Nguồn. Chưa có các chip lọc nhanh (Quick Filters) kèm badge đếm số lượng công việc theo từng trạng thái (ví dụ: "Chờ xử lý (5)", "Đang làm (2)", "Quá hạn (1)").
- **Hướng xử lý đề xuất**: Bổ sung thanh chip lọc nhanh kèm số lượng badge tương tự màn hình Hội thoại để nhân viên nắm bắt nhanh khối lượng tồn đọng.

### [UX-14-02] Thiếu gợi ý tự động mã đơn hàng khi tạo việc thủ công
- **Mức độ nghiêm trọng**: Low (P3) - Trải nghiệm nhập liệu.
- **Vị trí mã nguồn**: `dashboard/src/25-cong-viec.js` (`cvxTaoViec`, dòng 334–342).
- **Mô tả hiện tượng**:
  Trường `ma_don` trong form tạo việc là ô input text thông thường. Nhân viên phải tự gõ chính xác mã đơn (ví dụ `DH-TEST-1401`), không có autocomplete hoặc danh sách gợi ý các đơn hàng gần nhất của khách hàng đang xét.
- **Hướng xử lý đề xuất**: Tích hợp autocomplete/gợi ý đơn hàng dựa trên số điện thoại hoặc mã đơn gần nhất khi người dùng gõ từ 2 ký tự.

### [UX-14-03] Nút tạo việc từ hội thoại chưa tự điền tóm tắt nội dung trao đổi
- **Mức độ nghiêm trọng**: Low/Medium (P2) - Tiết kiệm thời gian xử lý.
- **Vị trí mã nguồn**: `dashboard/src/25-cong-viec.js` (dòng 471–475) & `dashboard/src/03-hoi-thoai.js`.
- **Mô tả hiện tượng**:
  Khi nhân viên bấm nút "+ Tạo việc" trong khung hội thoại (`#btn-tao-viec-ht`), hệ thống gắn sẵn `conversation_id`, `contact_id` và tên khách, nhưng ô "Mô tả công việc" đang để trống hoàn toàn. Nhân viên phải copy thủ công tin nhắn của khách hoặc tự gõ lại tóm tắt.
- **Hướng xử lý đề xuất**: Tự động trích xuất nội dung tin nhắn gần nhất của khách hoặc bản tóm tắt hội thoại (nếu AI đã tạo) điền sẵn vào ô mô tả để nhân viên xác nhận nhanh.

### [UX-14-04] Luồng chuyển trạng thái và ghi kết quả cần modal xác nhận nhanh
- **Mức độ nghiêm trọng**: Low (P3) - Tiện ích tương tác.
- **Vị trí mã nguồn**: `dashboard/src/25-cong-viec.js` (`cvxThaoTac`, dòng 164, 250–265).
- **Mô tả hiện tượng**:
  Khi nhân viên bấm nút "Hoàn thành…" trên panel chi tiết công việc, hệ thống mở một modal hỏi ghi kết quả xử lý. Tuy nhiên với các công việc đơn giản chỉ cần ghi chú ngắn, việc phải qua modal nhiều bước làm chậm thao tác hoàn tất nhiệm vụ.
- **Hướng xử lý đề xuất**: Cho phép nhập nhanh kết quả xử lý trực tiếp trên giao diện chi tiết hoặc lưu kết quả mặc định "Đã xử lý xong" nếu không nhập thêm.

### [UX-14-05] Thiếu chỉ báo trạng thái ca trực của nhân viên trong ô chọn phân công thủ công
- **Mức độ nghiêm trọng**: Medium (P2) - Điều phối nhân sự.
- **Vị trí mã nguồn**: `dashboard/src/25-cong-viec.js` (`cvxSua`, dòng 292–302).
- **Mô tả hiện tượng**:
  Khi người quản trị/trưởng ca mở form sửa hoặc phân công thủ công, dropdown danh sách nhân viên chỉ hiện họ tên, không hiển thị trạng thái thực tế: ai đang trong ca, ai ngoài ca, ai đang bận quá tải hoặc ai đang nghỉ phép.
- **Hướng xử lý đề xuất**: Thêm icon/chấm màu trực quan cạnh tên nhân viên trong dropdown (Xanh: Đang trong ca & sẵn sàng, Vàng: Ngoài ca, Đỏ: Đang nghỉ phép) kèm số việc họ đang giữ.

### [UX-14-06] Lịch sử hoạt động công việc thiếu bộ lọc theo loại sự kiện
- **Mức độ nghiêm trọng**: Low (P3) - Khả năng tra cứu kiểm toán.
- **Vị trí mã nguồn**: `dashboard/src/25-cong-viec.js` (`cvxVeChiTiet`, dòng 212–230).
- **Mô tả hiện tượng**:
  Danh sách lịch sử hoạt động hiển thị toàn bộ chuỗi sự kiện theo thứ tự thời gian. Đối với các công việc xử lý kéo dài nhiều ngày với nhiều tiến độ cập nhật, việc tìm lại thời điểm chuyển giao nhân viên hoặc thời điểm sửa hạn hoàn thành bị rối mắt.
- **Hướng xử lý đề xuất**: Bổ sung bộ lọc phân loại sự kiện (Tất cả / Phân công / Tiến độ / Trạng thái & Kết quả) ở đầu khối Lịch sử hoạt động.

### [UX-14-07] Thiếu thanh cảnh báo trực quan việc quá hạn ở đầu danh sách công việc
- **Mức độ nghiêm trọng**: Low/Medium (P2) - Cảnh báo SLA vận hành.
- **Vị trí mã nguồn**: `dashboard/src/25-cong-viec.js` (`cvxVeKhung`, dòng 394–412).
- **Mô tả hiện tượng**:
  Công việc quá hạn hiện tại được phân biệt bằng viền đỏ (`halt`) trên từng dòng riêng lẻ hoặc khi bấm lọc "Quá hạn". Chưa có một dải banner cảnh báo nổi bật ở đầu trang khi có việc quá hạn nghiêm trọng để nhắc nhở toàn đội trực ca.
- **Hướng xử lý đề xuất**: Hiển thị dải banner cảnh báo ở đầu danh sách (ví dụ: "⚠️ Có 2 công việc đã quá hạn xử lý cần ưu tiên!") kèm nút "Xem ngay".

---

## 6. STT 17 – Phân quyền thực thi hành động AI Agent

### [GAP-17-01] Chưa hỗ trợ công cụ sửa đơn đã xác nhận (`sua_don`) cho AI Agent
- **Mức độ nghiêm trọng**: Medium (P2) - Khoảng trống tính năng (BLOCKED tại `TC-17-007`).
- **Vị trí mã nguồn**: `agent/core/uy_quyen.py` (`DANH_MUC["sua_don"]`, dòng 121–125; `CONG_CU_HANH_DONG`, dòng 151–154).
- **Mô tả hiện tượng**:
  Mục `sua_don` ("Sửa đơn đã xác nhận") hiển thị trong danh sách chính sách ủy quyền với `ho_tro=False` ("AI không có công cụ sửa đơn — chuyển nhân viên"). Hiện tại hệ thống chỉ hỗ trợ `tao_don_hang` và `xin_huy_don`, chưa có công cụ đề xuất sửa sản phẩm/số lượng/giá trị đơn hàng vào bảng `ai_de_xuat` để nhân viên duyệt như mô tả của `TC-17-007`.
- **Hướng xử lý đề xuất**: Nếu nghiệp vụ cần quy trình AI đề xuất sửa đơn chờ duyệt, bổ sung công cụ `xin_sua_don` (tương tự `xin_huy_don`) và nhánh thực thi kiểm tra điều kiện trong `uy_quyen_ai.py`; nếu giữ nguyên thiết kế hiện tại (luôn chuyển nhân viên), cập nhật lại kỳ vọng của `TC-17-007`.

### [NOTE-17-01] Các hành động ngoại lệ chưa có công cụ thực thi tự động (`ho_tro=False`)
- **Phạm vi**: `hoan_tien`, `giam_gia`, `doi_tra`, `tao_van_don`, `tao_cong_viec` (`agent/core/uy_quyen.py`, dòng 126–147).
- **Ghi nhận**: Các hành động này được đánh dấu rõ `ho_tro=False` (không đặt mức Tự động được), AI chỉ ghi nhận yêu cầu (`xin_doi_tra`) hoặc chuyển nhân viên xử lý, không giả thành công.

---

## 7. STT 18 – Nhật ký kiểm toán và truy vết

### [UX-18-01] Nhật ký hệ thống hiển thị nhiều mã kỹ thuật thô và sự kiện nền lặp dày đặc (M18-01)
- **Mức độ nghiêm trọng**: Medium (P2) - Trải nghiệm vận hành & tra cứu kiểm toán.
- **Vị trí mã nguồn**: `agent/core/nhat_ky_kiem_toan.py` & `dashboard/src/27-nhat-ky.js`.
- **Mô tả hiện tượng**:
  Màn hình *Hệ thống & Nhật ký* ghi nhận đầy đủ dữ liệu phía Backend nhưng vẫn hiển thị nhiều mã kỹ thuật chưa dịch sang tiếng Việt thân thiện (ví dụ: `erp.ngat_mach`, `zalo_personal.tin_bo_qua`, `ly_do: khong_co_chu_va_khong_co_tep`) và các sự kiện nền lặp lại liên tục, làm loãng và khó theo dõi các hoạt động nghiệp vụ quan trọng của AI và nhân viên.
- **Hướng xử lý đề xuất**: Bổ sung bảng ánh xạ nhãn tiếng Việt cho các mã kỹ thuật còn thiếu trong `nhat_ky_kiem_toan.py`, mặc định ẩn/gom nhóm các sự kiện nhiễu nền (hoặc thêm bộ lọc nhanh "Chỉ hiện hoạt động nghiệp vụ").

### [UX-18-02] Giao diện hội thoại chưa có nút mở rộng xem cây truy vết toàn diện của lượt AI (M18-02)
- **Mức độ nghiêm trọng**: Low/Medium (P2) - Trải nghiệm người dùng CSKH.
- **Vị trí mã nguồn**: `dashboard/src/03-hoi-thoai.js`.
- **Mô tả hiện tượng**:
  Phía Backend cung cấp đầy đủ API truy vết đầu-cuối `/api/nhat-ky/luot/{luot_id}` (kết nối từ tin khách -> tra cứu RAG chunk & version -> gọi công cụ ERP -> soạn nháp -> duyệt). Tuy nhiên, trên giao diện chat của nhân viên, khung thông tin hiện tại chỉ hiển thị tóm tắt căn cứ tài liệu và nhãn người duyệt, chưa có modal hoặc popover trực quan mở rộng toàn bộ cây sự kiện của lượt AI để nhân viên đối chiếu nhanh.
- **Hướng xử lý đề xuất**: Bổ sung nút "Xem chi tiết lượt xử lý" trên tin nhắn AI hoặc thẻ Chi tiết hội thoại, mở modal hiển thị cây quy trình đầy đủ của `luot_id`.







---

## 8. STT 19 – Bổ sung hệ thống thông báo nội bộ

### [BUG-19-01] Nút "Xem thêm" không ẩn khi đã tải hết thông báo hoặc khi danh sách rỗng do xung đột CSS `.btn` với `[hidden]` (M19-03)
- **Loại vấn đề**: Lỗi hiển thị giao diện / CSS Bug.
- **Mức độ nghiêm trọng**: Medium (P2) - Gây hiểu nhầm tính năng bị treo/không phản hồi.
- **Vị trí mã nguồn**: `dashboard/app.css` (dòng 842, rule `.btn`), `dashboard/index.html` (dòng 62, `#chuongThem`), `dashboard/src/19-thong-bao.js` (dòng 50).
- **Mô tả hiện tượng (Đã xác minh thực tế qua Playwright)**:
  1. Khi danh sách thông báo đã tải hết (`con_nua: false`) hoặc tài khoản không có thông báo nào (0 bản ghi), hàm `veDanhSachChuong()` thực thi lệnh `$('#chuongThem').hidden = true`.
  2. Thuộc tính `hidden` đã được gán vào phần tử HTML (`<button class="btn btn--sm btn--ghost chuong__them" id="chuongThem" hidden>`).
  3. Tuy nhiên, class `.btn` trong `app.css` định nghĩa thuộc tính `display: inline-flex;` có độ đặc hiệu class `(0, 1, 0)`, ghi đè thuộc tính `[hidden] { display: none; }` mặc định của trình duyệt.
  4. Hệ quả: Nút "Xem thêm" vẫn hiển thị sờ sờ trên màn hình với kích thước đầy đủ (85.8px x 29.4px). Khi người dùng nhấn nút này, hệ thống gửi request `GET /api/toi/thong-bao` với `bo_qua=...`, backend trả về mảng rỗng `[]`, không có phần tử mới nào được thêm vào DOM và nút vẫn tiếp tục hiển thị trơ ra, khiến người dùng lầm tưởng nút bấm bị liệt/không có phản hồi.
- **Hướng xử lý đề xuất**:
  - Bổ sung quy tắc CSS toàn cục: `[hidden] { display: none !important; }` trong `app.css` hoặc đặt class `.is-hidden { display: none !important; }` để ẩn triệt để nút khi hết dữ liệu.

---

### [UX-19-01] Điều hướng từ thông báo công việc khi bộ lọc màn hình Công việc đang giới hạn
- **Loại vấn đề**: Trải nghiệm điều hướng người dùng (UX).
- **Mức độ nghiêm trọng**: Low/Medium (P2) - Trải nghiệm điều hướng.
- **Vị trí mã nguồn**: `dashboard/src/19-thong-bao.js` (`diToiLienKet`, dòng 90–101) & `dashboard/src/25-cong-viec.js` (`cvxTaiChiTiet`, dòng 147–152).
- **Mô tả hiện tượng (Đã kiểm chứng kỹ thuật)**:
  1. Khi người dùng bấm vào thông báo công việc (`loai: duoc_giao_viec`), hệ thống gọi hàm `moCongViec(lk.id)`. Hàm này chuyển tab sang `cv-danh-sach` và tải thành công chi tiết việc mở drawer bên phải `#cvxCt`.
  2. Tuy nhiên, ở danh sách bên trái (`#cvxDs`), nếu người dùng trước đó đang chọn một bộ lọc khác (ví dụ: đang lọc trạng thái "Hoàn thành" mà công việc mới ở trạng thái "Chờ xử lý"), bộ lọc `#cvxTrangThai` không tự động đặt lại về "Mọi trạng thái". Dòng công việc không xuất hiện trong danh sách bên trái và không có hiệu ứng highlight tương ứng.
  3. Ở nhánh dự phòng nếu `moCongViec` lỗi/không khả dụng, code cũ tại `19-thong-bao.js` bắn toast cảnh báo *"Việc này không nằm trong bộ lọc đang chọn ở màn Công việc"* mà không tự động reset bộ lọc.
- **Hướng xử lý đề xuất**:
  - Khi mở công việc từ thông báo chuông, nếu công việc không nằm trong bộ lọc hiện tại, tự động chuyển dropdown bộ lọc về "Mọi trạng thái" (`""`) và tải lại danh sách `#cvxDs` để định vị và highlight dòng công việc.

---

### [UX-19-02] Nút "Xem thêm" thiếu trạng thái loading, không disable khi tải và không tự cuộn tới dữ liệu mới (M19-03)
- **Loại vấn đề**: Trải nghiệm người dùng (UX Feedback).
- **Mức độ nghiêm trọng**: Low/Medium (P2) - Phản hồi tương tác người dùng.
- **Vị trí mã nguồn**: `dashboard/src/19-thong-bao.js` (`taiDanhSachChuong`, dòng 53–69; `veDanhSachChuong`, dòng 44–51).
- **Mô tả hiện tượng (Đã xác minh qua Playwright)**:
  - Khi danh sách còn dữ liệu (`con_nua: true`), người dùng bấm nút "Xem thêm", API backend thực sự gửi request `GET /api/toi/thong-bao?gioi_han=20&bo_qua=20` và gắn thêm 20 thông báo vào DOM (tổng số lượng DOM tăng từ 20 lên 40).
  - Tuy nhiên:
    1. Nút "Xem thêm" không có icon loading spinner, chữ trên nút không đổi thành "Đang tải...", không bị `disabled` trong lúc request đang gửi.
    2. Vùng danh sách `#chuongDs` có thuộc tính `overflow-y: auto`, khi 20 bản ghi mới được nối vào cuối danh sách, thanh cuộn vẫn giữ nguyên vị trí cũ (`scrollTop: 0`), không tự động cuộn xuống dưới.
    3. Vì toàn bộ 20 bản ghi mới nằm ngoài tầm nhìn (bên dưới khung nhìn) và nút không có hiệu ứng gì, người dùng nhìn vào màn hình cảm thấy nút bấm "không có phản hồi".
- **Hướng xử lý đề xuất**:
  - Khi đang fetch dữ liệu: disable nút `#chuongThem`, đổi text thành "Đang tải...", hiển thị spinner xoay tròn nhỏ.
  - Sau khi chèn thêm bản ghi: tự động cuộn nhẹ xuống phần tử thứ 21 vừa tải để người dùng nhận biết dữ liệu mới đã vào.

---

### [UX-19-03] Thông báo nội bộ chứa mã kỹ thuật thô và mô tả lập trình không thân thiện (M19-01 & M19-05)
- **Loại vấn đề**: Trải nghiệm giao diện & Ngôn ngữ hiển thị (Copywriting / UX).
- **Mức độ nghiêm trọng**: Low/Medium (P2) - Tính dễ hiểu cho nhân viên vận hành.
- **Vị trí mã nguồn**: `agent/core/agent.py` (dòng 1115), `agent/omnichannel/xu_ly_tin_vao.py` (dòng 662), trường `thong_bao.noi_dung`.
- **Mô tả hiện tượng**:
  - Khi AI dừng bất thường hoặc chuyển giao hội thoại cho nhân viên, chuỗi `escalate_reason` từ mã nguồn Python (ví dụ: `"Model dừng bất thường (tool_calls)"` hoặc `"Độ tin cậy thấp (0.00)"`) được đưa nguyên văn vào trường `noi_dung` của bản ghi `thong_bao`.
  - Trên popup thông báo chuông, nhân viên CSKH nhìn thấy các dòng chữ như *"Model dừng bất thường (tool_calls)"* hoặc *"Độ tin cậy thấp (0.00)"*. Các thuật ngữ này mang tính kỹ thuật lập trình backend, gây hoang mang và không có ý nghĩa nghiệp vụ đối với nhân viên CSKH.
- **Hướng xử lý đề xuất**:
  - Bổ sung bộ chuyển đổi ngôn ngữ thân thiện (Mapping / Translation):
    - `"Model dừng bất thường (tool_calls)"` -> *"Hệ thống gặp sự cố xử lý câu hỏi chuyên sâu, cần nhân viên hỗ trợ."*
    - `"Độ tin cậy thấp (0.00)"` -> *"AI chưa đủ thông tin chắc chắn để trả lời, chuyển nhân viên tiếp quản."*

---

## 9. STT 20 – Channel Adapter / Plugin

### [UX-20-01] Giao diện tab "Kết nối & Tích hợp" quá dài và dồn dập thông tin kỹ thuật (M20-05)
- **Loại vấn đề**: Trải nghiệm giao diện (UX).
- **Mức độ nghiêm trọng**: Low/Medium (P2) - Bố cục giao diện quản trị.
- **Vị trí giao diện**: `dashboard/src/22-ket-noi-tich-hop.js` và `dashboard/index.html` (tab `cc-ket-noi`).
- **Mô tả hiện tượng**:
  - Tab *Kết nối & Tích hợp* hiện tại gánh quá nhiều khối chức năng trên cùng một trang dọc:
    1. Khối đánh giá Sức khoẻ kênh (`#kn-suckhoe`).
    2. Form thêm kết nối kênh mới (`#connectionform`).
    3. Grid danh sách tài khoản 6 kênh kết nối (`#connectiongrid`).
    4. Checklist hướng dẫn kích hoạt 4 bước.
    5. Khối quản lý Khoá API tích hợp.
    6. Các Thẻ dịch vụ đối tác ngoài (ERPNext, GHN, GHTK) kèm cấu hình webhook và nút lịch sử nhận.
  - Chiều cao trang vượt quá 2500px, người vận hành phải cuộn rất nhiều và khó bao quát nhanh trạng thái hệ thống.
- **Hướng xử lý đề xuất**:
  - Tách hoặc phân nhóm tab con bên trong (Sub-tabs hoặc Accordion):
    - Sub-tab 1: Kênh khách hàng (Zalo, Facebook, Instagram, WhatsApp, Webchat).
    - Sub-tab 2: Tích hợp hệ thống ngoài (ERPNext, Đơn vị vận chuyển GHN/GHTK, Khoá API).

---

### [UX-20-02] Thiếu chú thích phân biệt giữa "Năng lực của Plugin" và "Trạng thái phiên tài khoản" (M20-01)
- **Loại vấn đề**: Trải nghiệm giao diện / Nhận thức người dùng (UX).
- **Mức độ nghiêm trọng**: Low (P3) - Tính rõ ràng của thông tin.
- **Vị trí giao diện**: `dashboard/src/22-ket-noi-tich-hop.js` (phần render badge khả năng của plugin).
- **Mô tả hiện tượng**:
  - Trên các thẻ plugin kênh, hệ thống hiển thị các badge năng lực chuẩn hóa (ví dụ: *Nhận và gửi văn bản*, *Gửi ảnh cho khách*, *Nhận tệp*, v.v.). Đây là khả năng của **lớp mã nguồn Adapter chung** (`lop.KHA_NANG_KENH`), không đồng nghĩa với việc tài khoản cụ thể đã được cấp đủ quyền hoặc đang hoạt động tốt.
  - Người dùng mới nhìn vào dễ lầm tưởng rằng tài khoản của họ đã sẵn sàng gửi ảnh, dù tài khoản thực tế đang ở trạng thái `disabled` hoặc `reauth_required`.
- **Hướng xử lý đề xuất**:
  - Đặt tiêu đề rõ ràng: *"Năng lực hỗ trợ của nền tảng"* hoặc thêm tooltip chú thích: *"Tính năng này được adapter hỗ trợ khi tài khoản ở trạng thái Hoạt động"*.

---

### [NOTE-20-01] Giải thích trạng thái "0 tài khoản" của các kênh Facebook, Instagram, Zalo OA, WhatsApp (M20-04)
- **Phạm vi**: `FacebookAdapter`, `InstagramAdapter`, `WhatsAppAdapter`, `ZaloOAAdapter`.
- **Ghi nhận kỹ thuật**:
  - Việc Dashboard hiển thị "0 tài khoản" là do môi trường kiểm thử chưa cấu hình tài khoản kết nối cụ thể (Page Token, App Secret, OA ID).
  - Phía backend đã triển khai **100% đầy đủ các lớp Adapter** tương ứng (`agent/channels/messenger.py`, `agent/channels/meta_channels.py`, `agent/channels/zalo_oa.py`) với đầy đủ logic xử lý Graph API, Zalo Open API, xác thực webhook HMAC và test suite kiểm chứng. Không phải là tính năng chưa hỗ trợ.
