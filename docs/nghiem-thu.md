# Nghiệm thu từng chức năng

<!-- SINH TỰ ĐỘNG bởi scripts/sinh_nghiem_thu.py — đừng sửa tay. -->

Chạy lúc 2026-11-22 02:24 UTC trên commit `e9df6a8`. **20/20 kịch bản đạt.**

Mỗi kịch bản chạy trên `agent.main.app` đầy đủ (middleware + lifespan) và Postgres thật, không kho giả, không gọi model. Các bước dưới đây là docstring của chính test — bảng không mô tả luồng nào khác luồng đã kiểm.

| # | Chức năng | Kết quả |
|---|---|---|
| 1 | Đăng nhập và phiên | đạt |
| 2 | Phân quyền: không được cấp thì không thấy | đạt |
| 3 | Nhân viên nghỉ việc | đạt |
| 4 | Kênh thêm bằng cấu hình; agent là tuỳ chọn | đạt |
| 5 | Khách hàng và người chịu trách nhiệm | đạt |
| 6 | Trường thông tin khách thêm từ dashboard, kiểm kiểu ở máy chủ | đạt |
| 7 | Phân task, quản lý task và thông báo nội bộ | đạt |
| 8 | Tin KHÔNG gửi được | đạt |
| 9 | Nhiều agent theo cấu hình; định tuyến theo cấu hình | đạt |
| 10 | Gộp khách trùng | đạt |
| 11 | Đếm dữ liệu sẽ xoá, có người thứ hai duyệt | đạt |
| 12 | Giao khách hàng loạt từ danh sách | đạt |
| 13 | Quy tắc tự động: khi khách nhắn → nếu … → thì … | đạt |
| 14 | Lịch ca trực: bộ định tuyến chỉ giao cho người đang trong ca | đạt |
| 15 | Sổ yêu cầu của khách (Luật BVDLCN 91/2025, NĐ 356/2025 Điều 5) | đạt |
| 16 | "Gặp nhân viên" — lời hứa trong câu thông báo AI được giữ bằng mã | đạt |
| 17 | Hãng vận chuyển GHTK báo trạng thái về (webhook DẠNG FORM) | đạt |
| 18 | Địa chỉ chắc chắn sai thì không lên đơn (danh mục hành chính sau sáp nhập 2025) | đạt |
| 19 | Đổi ưu tiên hội thoại và xem màn Phân tích | đạt |
| 20 | Quản lý nhãn: hai loại độc lập, gắn đúng màn, ngừng thay vì xoá | đạt |

## 1. Đăng nhập và phiên

Kết quả: **đạt** · `test_01_dang_nhap_that_bang_mat_khau`

1. Quản trị tạo nhân viên "lan" với mật khẩu ở màn Nhân sự.
2. "lan" đăng nhập bằng đúng mật khẩu -> nhận cookie phiên.
3. GET /api/toi trả về đúng tên và tập quyền của vai trò Nhân viên.
4. Sai mật khẩu -> 401, không có phiên.
5. Đăng xuất -> /api/toi trả 401.

## 2. Phân quyền: không được cấp thì không thấy

Kết quả: **đạt** · `test_02_phan_quyen_hong_dong_theo_vai_tro`

1. Nhân viên vai trò "Nhân viên" đọc được hội thoại (200).
2. Cùng người đó tạo nhân viên mới -> 403 (thiếu nguoi_dung.sua).
3. Quản trị tạo vai trò "Chỉ xem khách" chỉ có khach.doc.
4. Gán cho nhân viên thứ hai: đọc khách 200, tạo công việc 403.
5. Nhân viên không có vai trò nào: đăng nhập được, mọi màn 403.

## 3. Nhân viên nghỉ việc

Kết quả: **đạt** · `test_03_khoa_nhan_vien_da_moi_phien`

1. "lan" đang đăng nhập, /api/toi 200.
2. Quản trị bấm Khoá.
3. Ngay lập tức phiên cũ của "lan" -> 401; đăng nhập lại -> 401.
4. Danh sách nhân sự hiện khoa=true; tổng vẫn đếm người này.
5. Mở khoá -> đăng nhập lại được.

## 4. Kênh thêm bằng cấu hình; agent là tuỳ chọn

Kết quả: **đạt** · `test_04_noi_kenh_va_tat_agent_theo_kenh`

1. Quản trị tạo kênh webchat, credential vào vault, bật kênh.
2. Kênh hiện trong danh sách.
3. Tắt agent cho kênh, có lý do -> agent_bat=false.
4. Khách nhắn -> hội thoại chuyển người, chuông báo quản trị (không sinh việc), KHÔNG gọi model.
5. Bật lại agent -> agent_bat=true.

## 5. Khách hàng và người chịu trách nhiệm

Kết quả: **đạt** · `test_05_giao_khach_va_tam_nhin`

1. Khách nhắn qua webchat -> có hồ sơ khách, chưa có chủ.
2. Ô "Khách chưa có chủ" đếm 1.
3. Quản trị giao khách cho "lan" (có lý do) -> hết vô chủ; lịch sử 1 dòng.
4. Mức tầm nhìn "an": "minh" (cùng kênh) KHÔNG thấy khách của lan; lan thấy.
5. Mức "tat": minh thấy lại. Thu hồi -> khách về của chung.

## 6. Trường thông tin khách thêm từ dashboard, kiểm kiểu ở máy chủ

Kết quả: **đạt** · `test_06_truong_thong_tin_khach_them_tren_dashboard`

1. Quản trị thêm trường "tuoi" kiểu số và "loai_da" kiểu chọn.
2. Ghi tuoi=30, loai_da="dau" cho một khách -> 200, đọc lại đúng.
3. tuoi="ba mươi" -> 422; loai_da="xanh" (ngoài lựa chọn) -> 422.
4. Khoá lạ "chieu_cao" -> 422, không bị nuốt im.
5. Xoá trường -> máy chủ nói rõ bao nhiêu hồ sơ mất giá trị.

## 7. Phân task, quản lý task và thông báo nội bộ

Kết quả: **đạt** · `test_07_chuyen_giao_bao_nguoi_va_giao_viec`

1. Agent tắt -> khách nhắn -> KHÔNG sinh công việc (mục 14.2); Ca trực đếm 0 việc chưa giao.
2. "lan" chưa thuộc kênh -> chuông không có gì (không lộ khách kênh khác).
3. "lan" vào kênh, khách khác nhắn -> chuông "AI chuyển giao" trỏ tới hội thoại.
4. "lan" bấm đã đọc -> hội thoại KHÔNG đổi (đọc không phải là nhận).
5. Quản trị tạo việc giao cho "minh" -> chuông của minh có "Được giao việc".
6. "lan" (không có cong_viec.giao) đẩy việc sang mình -> 403.
7. Quản trị đặt hạn, đánh dấu xong -> xong_luc có, qua_han=false.
8. Quản trị tạo việc tay với hạn đã qua -> qua_han=true.

## 8. Tin KHÔNG gửi được

Kết quả: **đạt** · `test_08_tin_khong_gui_duoc_xem_va_xu_ly`

1. Một job outbox chết (8/8 lần) thuộc hội thoại đã chuyển người.
2. Ô Ca trực "Tin KHÔNG gửi được" đếm 1; danh sách hiện lỗi cuối.
3. Gửi lại bị TỪ CHỐI (409): người đã tiếp quản, gửi lại là khách nhận hai lần.
4. Bỏ qua -> trạng thái cancelled, ô đếm về 0.

## 9. Nhiều agent theo cấu hình; định tuyến theo cấu hình

Kết quả: **đạt** · `test_09_ho_so_agent_va_dinh_tuyen_cau_hinh_duoc`

1. Tạo hồ sơ agent "Tư vấn nhẹ" với ngưỡng LỎNG hơn toàn cục.
2. API trả cả giá trị đã lưu lẫn giá trị có hiệu lực (đã siết).
3. Gán hồ sơ cho kênh -> kênh hiện agent_ho_so_id.
4. Tạo đội, thêm thành viên, tạo luật, đặt SLA qua API.
5. GET /api/routing phản ánh 1 đội, 1 luật, 1 SLA.

## 10. Gộp khách trùng

Kết quả: **đạt** · `test_10_gop_hai_khach_lam_mot`

1. Hai khách web khác nhau nhắn -> 2 hồ sơ.
2. Xem trước gộp: đủ số hội thoại, danh tính, can_manage=true (quản trị).
3. Gộp với version đúng -> 200, danh sách còn 1 khách.
4. Khách giữ lại có 2 danh tính.
5. Hoàn tác -> lại 2 khách.

## 11. Đếm dữ liệu sẽ xoá, có người thứ hai duyệt

Kết quả: **đạt** · `test_11_dem_truoc_khi_xoa_can_nguoi_thu_hai_duyet`

1. Khách nhắn -> có hồ sơ. Quản trị A tạo yêu cầu đếm (dry-run) kèm lý do.
2. Danh sách ở màn Nhật ký hiện yêu cầu, trạng thái chờ duyệt.
3. Chính A bấm Duyệt -> 409: người tạo không tự duyệt được.
4. Quản trị B duyệt -> đã duyệt. Chạy đếm -> kết quả có số hội thoại, tin nhắn.
5. Sức khoẻ kênh đọc được qua API (chưa có lần kiểm nào -> null, không lỗi).

## 12. Giao khách hàng loạt từ danh sách

Kết quả: **đạt** · `test_12_giao_nhieu_khach_mot_luot_va_thu_hoi`

1. Ba khách web nhắn -> 3 hồ sơ, ô "Khách chưa có chủ" đếm 3.
2. Quản trị tick cả ba, giao cho "lan" một lượt -> 3 khách có chủ, vô chủ = 0.
3. Mỗi khách có đúng 1 dòng lịch sử giao, cùng lý do.
4. Giao cho người đã KHOÁ -> 422, không khách nào đổi chủ (một giao dịch).
5. Thu hồi hàng loạt (không chọn ai) -> cả ba về của chung.

## 13. Quy tắc tự động: khi khách nhắn → nếu … → thì …

Kết quả: **đạt** · `test_13_quy_tac_tu_dong_chan_agent_va_chuyen_nguoi`

1. Quản trị tạo mẫu /doitra và nhãn hội thoại «đổi trả»; quy tắc gửi mẫu KHÔNG tồn tại bị từ chối lúc lưu (422).
2. Tạo quy tắc «có từ đổi trả → gắn nhãn hội thoại, gửi mẫu /doitra, chuyển người».
3. Kênh BẬT agent; khách nhắn "em muốn DOI TRA" (không dấu) → khớp, agent không chạy.
4. Hội thoại chuyển người, có nhãn "đổi trả", MỘT thông báo chuyển giao (không sinh việc), mẫu đã vào hàng gửi.
5. Nhật ký lần chạy ghi "đã làm"; khách nhắn tiếp không sinh mẫu thứ hai.
6. Nhân viên XEM được quy tắc nhưng không sửa được — thiếu quyền sửa định tuyến (403).

## 14. Lịch ca trực: bộ định tuyến chỉ giao cho người đang trong ca

Kết quả: **đạt** · `test_14_lich_ca_va_lich_nghi`

1. Nhân viên mới chưa xếp ca → "luôn trực".
2. Quản trị xếp ca ở một khung giờ KHÔNG phủ lúc này → nhân viên ngoài ca.
3. Nhân viên tự xem "ca của tôi" → thấy mình ngoài ca và lịch tuần.
4. Ca chồng nhau (ca đêm Chủ nhật vắt sang sáng thứ Hai) bị từ chối (422).
5. Đội có luật định tuyến mà không ai trong ca → cảnh báo hiện ra.
6. Xoá hết ca → về "luôn trực"; thêm lịch nghỉ phủ lúc này → ngoài ca.

## 15. Sổ yêu cầu của khách (Luật BVDLCN 91/2025, NĐ 356/2025 Điều 5)

Kết quả: **đạt** · `test_15_so_yeu_cau_cua_khach_dem_han_luat_dinh`

1. Quản trị ghi yêu cầu xoá khách gửi hôm nay → "trong hạn".
2. Ghi yêu cầu xem dữ liệu khách gửi 25 ngày trước → vào sổ đã "QUÁ HẠN".
3. Sổ đếm 1 quá hạn; yêu cầu quá hạn KHÔNG gia hạn được (422).
4. Phản hồi ban đầu, gia hạn một lần; lần gia hạn thứ hai bị từ chối.
5. Từ chối phải nêu căn cứ; đóng xong yêu cầu biến khỏi danh sách đang mở.
6. Sổ không lưu số điện thoại thật; người không có quyền PII không xem được (403).

## 16. "Gặp nhân viên" — lời hứa trong câu thông báo AI được giữ bằng mã

Kết quả: **đạt** · `test_16_khach_doi_gap_nhan_vien_thi_chuyen_nguoi_that`

1. Kênh BẬT agent; khách nhắn "cho em gặp nhân viên!" → chuyển người NGAY, agent không chạy.
2. Hội thoại ở chế độ người, KHÔNG sinh việc, có MỘT thông báo "Khách đòi gặp nhân viên".
3. Khách KHÔNG nhận câu "em là trợ lý AI" — người đang tiếp, không phải máy.
4. Công tắc thông báo AI có trên Cấu hình (nhóm Bảo vệ dữ liệu cá nhân).

## 17. Hãng vận chuyển GHTK báo trạng thái về (webhook DẠNG FORM)

Kết quả: **đạt** · `test_17_webhook_ghtk_dang_form_cap_nhat_don`

1. Đơn đã có mã vận đơn GHTK; gọi webhook sai bí mật → 401, đơn không đổi.
2. GHTK báo "shipper báo đã giao" (45) — chỉ để tham khảo → đơn KHÔNG đổi.
3. GHTK báo "đã giao" (5) dạng form → đơn chuyển "đã giao".
4. Thân rác (không JSON, không form) → 400, có ghi nhật ký.
5. Hãng không có ("/webhook/shipping/abc") → 404, không đụng đơn.

## 18. Địa chỉ chắc chắn sai thì không lên đơn (danh mục hành chính sau sáp nhập 2025)

Kết quả: **đạt** · `test_18_dia_chi_mau_thuan_khong_len_don`

1. Công cụ lên đơn nhận "Phường Ba Đình, TP Hồ Chí Minh" → không lên đơn, bảo hỏi lại khách.
2. Không đơn nào được ghi vào CSDL.
3. Địa chỉ cũ ba cấp ("Phường Bến Nghé, Quận 1, TP HCM") không bị chặn vì lý do địa chỉ.

## 19. Đổi ưu tiên hội thoại và xem màn Phân tích

Kết quả: **đạt** · `test_19_doi_uu_tien_rut_han_sla_va_man_phan_tich`

1. Quản trị đặt SLA mức thường (60/1440 phút) và gấp (5/30 phút); khách web nhắn → hội thoại có hạn.
2. Nhân viên KHÔNG thuộc kênh đổi ưu tiên → 404, không lộ hội thoại tồn tại.
3. Quản trị nâng lên "gấp" kèm lý do → hạn phản hồi đầu rút còn tối đa 5 phút từ bây giờ.
4. Hạ về "thấp" → hạn KHÔNG kéo dài lại; cả hai lần đổi nằm trong nhật ký kiểm toán.
5. Màn Phân tích: quản trị thấy 1 hội thoại mới, 1 khách mới; nhân viên ngoài kênh thấy 0.

## 20. Quản lý nhãn: hai loại độc lập, gắn đúng màn, ngừng thay vì xoá

Kết quả: **đạt** · `test_20_quan_ly_nhan_va_gan_nhan_hai_loai`

1. Quản trị tạo nhãn khách «Khách sỉ» và nhãn hội thoại «Chờ hàng»; tạo trùng tên «khách sỉ» → 409.
2. Khách web nhắn. Nhân viên trong kênh gắn «Chờ hàng» lên hội thoại; gắn nhãn KHÁCH lên hội thoại → 422.
3. Hộp thư lọc theo nhãn «Chờ hàng» ra đúng hội thoại ấy; nhân viên NGOÀI kênh gắn nhãn → 404.
4. Customer 360: quản trị gắn «Khách sỉ» cho khách; danh sách khách lọc theo nhãn ra đúng khách ấy.
5. Xoá «Khách sỉ» đang dùng → 409; Ngừng sử dụng → biến khỏi ô chọn, khách vẫn mang nhãn (đã ngừng).
6. Nhân viên không có quyền cấu hình không sửa được danh mục (403); mọi thao tác nằm trong nhật ký.
