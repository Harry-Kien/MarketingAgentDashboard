# Bảng yêu cầu chức năng và phi chức năng

<!-- SINH TỰ ĐỘNG bởi scripts/sinh_bang_yeu_cau.py — đừng sửa tay. -->

Đối chiếu từng mục của bảng "Check list công việc" (21.11.2026, mục 1–21; bảng không có mục 11) với mã nguồn, test canh và kịch bản nghiệm thu. Phạm vi ràng buộc và các khác biệt đã chốt: `docs/nang-cap/ke-hoach-check-list.md`.

**Cách đọc.** Phần ánh xạ (yêu cầu → mã → test) do người viết, nhưng mỗi lần sinh, bộ sinh kiểm từng đường dẫn, từng tên test, từng route API (trên app thật), từng tab giao diện và từng kịch bản nghiệm thu — thiếu một thứ là không sinh được bảng. Mọi con số đếm từ mã. Trạng thái của MỤC suy từ yêu cầu con, không gõ tay. Sinh lại: `python -m scripts.sinh_bang_yeu_cau --ghi`.

Trạng thái: **Đạt** — có mã và test canh; **Đạt một phần** — làm được phần chính, phần còn lại ghi rõ ở cột yêu cầu; **Chưa làm**; **Ngoài phạm vi theo bảng** — bảng ghi tạm hoãn/ẩn/hướng sau, không tính vào trạng thái mục.

Nghiệm thu (`docs/nghiem-thu.md`, sinh từ lượt chạy thật): **22/22** kịch bản đạt.

## Tổng quan

| Mục | Yêu cầu | Trạng thái | Yêu cầu con đạt | Test canh nêu tên | Nghiệm thu |
|---|---|---|---|---|---|
| 1 | Nút "← Quay lại" ở màn hai lớp (xác thực hai bước) | Đạt | 3/3 | 5 | 1 |
| 2 | Dòng "Thời gian · Người gửi · Trạng thái" dưới mỗi tin | Đạt một phần | 4/5 | 8 | — |
| 3 | Nhãn động cho khách hàng và hội thoại, danh mục chung | Đạt | 6/6 | 17 | 20 |
| 4 | Tái cấu trúc menu: 6 menu chính + "Cài đặt & Quản trị", chuông thông báo | Đạt | 9/9 (+1 ngoài phạm vi) | 20 | 19 |
| 5 | Cấu hình AI Agent: 5 tab, bật/tắt AI, chế độ chung mọi kênh | Đạt một phần | 6/7 | 15 | 4, 9 |
| 6 | Thanh thông tin hội thoại gọn; ghi chú nội bộ trong ô soạn tin | Đạt | 6/6 | 14 | — |
| 7 | Mẫu trả lời và quy tắc tự động: ưu tiên, xung đột, chống trùng với AI | Đạt | 11/11 | 25 | 13 |
| 8 | Kết nối & Tích hợp: kênh, ERPNext, GHN, GHTK, webhook, nhà cung cấp AI, thông báo minh bạch AI | Đạt | 12/12 (+2 ngoài phạm vi) | 33 | 4, 16, 17 |
| 9 | Phân biệt hội thoại nhóm và cá nhân | Đạt | 7/7 (+1 ngoài phạm vi) | 17 | — |
| 10 | Media khách gửi | Đạt | 8/8 | 26 | — |
| 12 | Phân quyền RBAC theo chức năng | Đạt | 7/7 (+1 ngoài phạm vi) | 22 | 2 |
| 13 | Vai trò động và quản lý nhân viên | Đạt | 7/7 | 15 | 3 |
| 14 | Phân công công việc | Đạt | 9/9 | 23 | 7, 14, 21 |
| 15 | SLA | Đạt | 9/9 | 22 | 19 |
| 16 | Gợi ý có căn cứ và "Xem căn cứ" | Đạt | 5/5 | 15 | — |
| 17 | Ba cấp ủy quyền hành động của AI | Đạt một phần | 8/9 | 26 | 22 |
| 18 | Trách nhiệm giải trình của AI | Đạt | 8/8 | 22 | — |
| 19 | Thông báo nội bộ (chuông) | Đạt | 6/6 | 17 | 7, 21 |
| 20 | Kênh theo kiến trúc plugin | Đạt | 4/4 (+1 ngoài phạm vi) | 11 | 4 |
| 21 | Bảng yêu cầu chức năng và phi chức năng | Đạt | 3/3 | 6 | — |

Tổng: Đạt 17, Đạt một phần 3 (trên 20 mục).

---

# Phần A — Yêu cầu chức năng

## Mục 1. Nút "← Quay lại" ở màn hai lớp (xác thực hai bước)

**Trạng thái: Đạt**

Nghiệm thu trên app đầy đủ + Postgres thật: kịch bản 1 — Đăng nhập và phiên (**đạt**).

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 1.1 | Hộp hỏi hai lớp (`#congHoi` — bật/tắt xác thực hai bước và các hộp xác nhận khác) dùng chữ "← Quay lại", không còn "Thôi, quay lại" | Đạt | `test_cay_menu::test_nut_quay_lai_hai_buoc` |
| 1.2 | Các hộp phụ khác (giao khách, đổi mật khẩu) dùng cùng chữ "← Quay lại" *Test soi `#congHoi`; hai hộp còn lại cùng chữ trong index.html.* | Đạt | `test_cay_menu::test_nut_quay_lai_hai_buoc` |
| 1.3 | Xác thực hai bước chạy thật: hỏi mã, mã sai tính lần sai, không lộ tài khoản có bật hai bước | Đạt | `test_hai_buoc::test_vong_doi_2fa_tren_csdl_that`<br>`test_hai_buoc::test_thieu_ma_thi_hoi_ma_khong_tao_phien`<br>`test_hai_buoc::test_sai_mat_khau_khong_lo_la_co_2fa` |

Test canh nêu tên: **5**; các tệp test ấy (2 tệp) có tổng **33** hàm test.

**Nơi hiện thực**

- Mã: `dashboard/index.html`, `dashboard/src/07-noi-dung.js`, `dashboard/src/14-cskh.js`, `agent/core/hai_buoc.py`
- API (quyền đọc từ route thật):
    - `GET /api/toi/hai-buoc` — miễn trừ (đăng nhập hoặc chữ ký riêng)
    - `POST /api/toi/hai-buoc/bat-dau` — miễn trừ (đăng nhập hoặc chữ ký riêng)
    - `POST /api/toi/hai-buoc/xac-nhan` — miễn trừ (đăng nhập hoặc chữ ký riêng)
    - `POST /api/toi/hai-buoc/tat` — miễn trừ (đăng nhập hoặc chữ ký riêng)

**Câu hỏi mở — cần chủ dự án xác nhận**

- Màn ĐĂNG NHẬP khi máy chủ đòi mã hai bước hiện ô mã ngay trong biểu mẫu, không có nút "← Quay lại" riêng (người dùng sửa thẳng tên/mật khẩu). Nếu bảng muốn cả chỗ này thì còn thiếu.

## Mục 2. Dòng "Thời gian · Người gửi · Trạng thái" dưới mỗi tin

**Trạng thái: Đạt một phần**

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 2.1 | Đúng MỘT dòng meta dưới mỗi tin theo thứ tự Thời gian · Người gửi · Trạng thái | Đạt | `test_trach_nhiem_giao_dien::test_mot_dong_meta_thoi_gian_nguoi_gui_trang_thai` |
| 2.2 | Người gửi theo quy ước: AI Agent / Nhân viên (tên) / Khách hàng (tên) / Hệ thống; người sửa, người duyệt ghi tên | Đạt | `test_trach_nhiem_hoi_thoai::test_chi_tiet_hoi_thoai_noi_ten_nguoi_gui_nguoi_sua_nguoi_duyet`<br>`test_tin_nhom_zalo::test_api_chi_tiet_tra_ten_nguoi_gui_tung_tin` |
| 2.3 | Thông tin kỹ thuật (độ tin cậy, nguồn, model, chi phí, thời gian xử lý) chỉ nằm trong "Chi tiết" của từng tin | Đạt | `test_trach_nhiem_giao_dien::test_khong_hien_ky_thuat_mac_dinh_va_khong_phan_tram_tin_cay`<br>`test_trach_nhiem_giao_dien::test_xem_can_cu_tren_ban_nhap_va_chi_tiet_tung_tin` |
| 2.4 | Trạng thái lấy từ `delivery_status` thật, không bịa (Đang gửi / Đã gửi / Lỗi) | Đạt | `test_outbox_trang_thai_tin::test_moi_trang_thai_job_deu_anh_xa_ra_gia_tri_hop_le`<br>`test_outbox_trang_thai_tin::test_retry_khong_bao_gio_ro_ri_ra_cot_tin_nhan` |
| 2.5 | Trạng thái "Đã nhận" / "Đã đọc" hiện được *Giao diện có nhãn, nhưng chưa kênh nào đọc biên nhận từ webhook — xem số đếm bên dưới.* | Đạt một phần | `test_kha_nang_kenh::test_khong_khai_bien_nhan_khi_chua_co_ma_doc_bien_nhan` |

Test canh nêu tên: **8**; các tệp test ấy (5 tệp) có tổng **50** hàm test.

Số plugin kênh khai đọc được biên nhận "Đã nhận"/"Đã đọc": **0** (đếm từ `KHA_NANG_KENH`).

**Nơi hiện thực**

- Mã: `dashboard/src/03-hoi-thoai.js`, `dashboard/src/19-trach-nhiem.js`, `agent/api/inbox.py`
- API (quyền đọc từ route thật):
    - `GET /api/inbox/conversations/{conversation_id}` — `hoi_thoai.doc`
- Giao diện: màn `hoithoai`

## Mục 3. Nhãn động cho khách hàng và hội thoại, danh mục chung

**Trạng thái: Đạt**

Nghiệm thu trên app đầy đủ + Postgres thật: kịch bản 20 — Quản lý nhãn: hai loại độc lập, gắn đúng màn, ngừng thay vì xoá (**đạt**).

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 3.1 | Danh mục nhãn: tên duy nhất (không phân biệt hoa thường, kể cả nhãn đã ngừng), màu, mô tả, thứ tự; ngừng dùng thay vì xoá khi đang gắn | Đạt | `test_nhan_dong::test_danh_muc_tao_sua_trung_ten_ngung_xoa`<br>`test_nhan_dong::test_chuan_ten_gop_khoang_trang_va_NFC`<br>`test_nhan_dong::test_chuan_mau`<br>`test_nhan_dong::test_quyen_danh_muc` |
| 3.2 | Hai loại độc lập — nhãn khách, nhãn hội thoại; CSDL chặn gắn nhầm loại và xoá nhãn đang gắn | Đạt | `test_nhan_dong::test_csdl_chan_sai_loai_va_xoa_nhan_dang_gan`<br>`test_nhan_dong::test_migration_khoa_ngoai_dung_chieu` |
| 3.3 | Gắn/gỡ đúng màn: nhãn hội thoại ở đầu hội thoại, nhãn khách ở Customer 360; theo quyền và phạm vi kênh; lọc hộp thư và danh sách khách theo nhãn | Đạt | `test_nhan_dong::test_nhan_hoi_thoai_gan_go_loc_quyen_va_pham_vi`<br>`test_nhan_dong::test_nhan_khach_gan_go_loc_quyen_va_pham_vi`<br>`test_nhan_dong::test_dau_hoi_thoai_chi_co_nhan_hoi_thoai`<br>`test_nhan_dong::test_o_chon_chi_lay_nhan_dang_dung_va_chip_nhan_da_ngung_hien_xam` |
| 3.4 | Nhãn chữ tự do cũ chuyển sang danh mục; không còn đường ghi chữ tự do | Đạt | `test_nhan_dong::test_migration_chuyen_du_lieu_cu`<br>`test_nhan_dong::test_khong_ma_nao_con_ghi_bang_chu_tu_do_cu`<br>`test_nhan_dong::test_khong_con_o_go_nhan_chu_tu_do` |
| 3.5 | Quy tắc tự động tách điều kiện/hành động theo nhãn khách và nhãn hội thoại (theo id) | Đạt | `test_nhan_dong::test_quy_tac_tach_nhan_khach_va_nhan_hoi_thoai`<br>`test_nhan_dong::test_bieu_mau_quy_tac_tach_hai_loai_nhan` |
| 3.6 | Gộp khách gộp nhãn (hoàn tác gỡ đúng phần đã chép); PDPD tra cứu kể tên nhãn và xoá liên kết | Đạt | `test_nhan_dong::test_gop_khach_gop_nhan_va_hoan_tac_go_dung_phan_chep`<br>`test_nhan_dong::test_pdpd_tra_cuu_ke_ten_nhan_va_xoa_lien_ket` |

Test canh nêu tên: **17**; các tệp test ấy (1 tệp) có tổng **22** hàm test.

**Nơi hiện thực**

- Mã: `agent/core/nhan.py`, `agent/api/nhan.py`, `agent/api/hoi_thoai_nhan.py`, `agent/migrations/versions/0056_danh_muc_nhan.sql`, `dashboard/src/21-nhan.js`
- API (quyền đọc từ route thật):
    - `GET /api/nhan` — `cau_hinh.doc`
    - `POST /api/nhan` — `cau_hinh.sua`
    - `PUT /api/nhan/{nhan_id}` — `cau_hinh.sua`
    - `POST /api/nhan/{nhan_id}/ngung` — `cau_hinh.sua`
    - `GET /api/nhan/hoi-thoai` — `hoi_thoai.doc`
    - `GET /api/nhan/khach` — `khach.doc`
    - `POST /api/inbox/conversations/{conversation_id}/nhan` — `hoi_thoai.ghi_chu`
- Giao diện: tab `cc-nhan`

**Lệch so với bảng / ghi chú**

- Bảng cũ `contact_tags`, `hoi_thoai_nhan` giữ nguyên trong CSDL (dữ liệu thật, migration đã chốt) nhưng không mã nào ghi vào nữa — có test canh.

## Mục 4. Tái cấu trúc menu: 6 menu chính + "Cài đặt & Quản trị", chuông thông báo

**Trạng thái: Đạt**

Nghiệm thu trên app đầy đủ + Postgres thật: kịch bản 19 — Đổi ưu tiên hội thoại và xem màn Phân tích (**đạt**).

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 4.1 | Sáu màn nghiệp vụ đúng thứ tự: Hội thoại, Khách hàng, Đơn hàng, Kho, Công việc, Phân tích | Đạt | `test_cay_menu::test_dung_sau_man_nghiep_vu_dung_thu_tu`<br>`test_cay_menu::test_moi_muc_thanh_ben_co_dung_mot_man` |
| 4.2 | Nhóm "Cài đặt & Quản trị" thu gọn được, đúng bốn mục con chia tab | Đạt | `test_cay_menu::test_nhom_cai_dat_thu_gon_duoc_va_dung_bon_con`<br>`test_cay_menu::test_tab_dung_id_hop_dong_va_nam_dung_man` |
| 4.3 (bảng 4.3) | Phân tích thay chỗ "Số hiệu": hiệu quả CSKH, AI Agent, nhân viên, SLA, tin nhắn; lọc ngày, nền tảng, tài khoản kênh, nhân viên, hồ sơ AI; tôn trọng phạm vi kênh | Đạt | `test_phan_tich_va_sla::test_phan_tich_ai_theo_ho_so_dem_theo_su_kien`<br>`test_phan_tich_va_sla::test_phan_tich_chi_thay_kenh_duoc_giao`<br>`test_phan_tich_va_sla::test_dashboard_co_man_phan_tich_doi_uu_tien_va_nghe_moi_su_kien_sla` |
| 4.4 | Công việc gộp Ca trực: tab Tổng quan ca trực + Danh sách công việc | Đạt | `test_cay_menu::test_noi_dung_cu_nam_dung_tab`<br>`test_he_thong_giao_viec::test_man_danh_sach_cong_viec_gan_vao_tab` |
| 4.5 | Chuông thông báo ở thanh trên, không là mục điều hướng; thanh bên không còn Video / Đăng bài / Thông báo | Đạt | `test_thong_bao_noi_bo::test_chuong_nam_o_thanh_tren_khong_co_muc_dieu_huong`<br>`test_cay_menu::test_khong_con_video_dang_bai_hay_thong_bao_tren_thanh_ben` |
| 4.6 | Mục menu và tab ẩn theo quyền (máy chủ vẫn là chốt thật); tên màn cũ vẫn dẫn tới đúng tab | Đạt | `test_cay_menu::test_menu_an_theo_quyen_sau_khi_dang_nhap`<br>`test_cay_menu::test_moi_tab_co_quyen_va_quyen_co_that`<br>`test_cay_menu::test_ten_man_cu_van_dan_toi_dung_tab` |
| 4.7 | Sức khoẻ hệ thống chỉ còn ở Hệ thống & Nhật ký (trước ở ba nơi) | Đạt | `test_cay_menu::test_suc_khoe_he_thong_chi_o_he_thong_va_nhat_ky` |
| 4.8 | Mô-đun gắn vào tab theo id cố định (GAN_TAB); mô-đun hỏng thì nội dung gốc hiện lại và có thông báo | Đạt | `test_cay_menu::test_gan_khe_an_noi_dung_goc_va_lui_lai_khi_mo_dun_hong`<br>`test_cay_menu::test_gan_khe_chay_that_trong_node` |
| 4.9 | Khổ hẹp: thanh bên thu gọn, mở bằng ☰ | Đạt | `test_cay_menu::test_thanh_ben_thu_gon_o_kho_hep` |
| 4.10 (bảng 4.8) | Ẩn CSAT và cấu hình VietQR khỏi giao diện, giữ mã nguồn và API *Bảng ghi tạm hoãn — đã ẩn đúng như bảng, có test canh.* | Ngoài phạm vi theo bảng | `test_cay_menu::test_csat_va_vietqr_khong_hien_nhung_ma_con`<br>`test_cay_menu::test_csat_mac_dinh_tat` |

Test canh nêu tên: **20**; các tệp test ấy (4 tệp) có tổng **89** hàm test.

**Cây menu đọc từ `dashboard/index.html`:**

1. Hội thoại (`hoithoai`)
2. Khách hàng (`khachhang`)
3. Đơn hàng (`donhang`)
4. Kho (`kho`)
5. Công việc (`congviec`) — tab: Tổng quan ca trực (`cv-ca-truc`), Danh sách công việc (`cv-danh-sach`)
6. Phân tích (`sohieu`)
7. Cài đặt & Quản trị (thu gọn được)
    - Cấu hình chung (`cauhinhchung`) — tab: Quản lý nhãn (`cc-nhan`), Tin nhắn & Quy tắc tự động (`cc-tu-dong`), Kết nối & Tích hợp (`cc-ket-noi`), SLA & Giờ làm việc (`cc-sla`), Điều phối hội thoại (`cc-dieu-phoi`)
    - Cấu hình AI Agent (`cauhinhai`) — tab: Cấu hình cơ bản (`ai-co-ban`), Tri thức (RAG) (`ai-tri-thuc`), Kỹ năng & Công cụ (`ai-ky-nang`), Chính sách & Ủy quyền (`ai-chinh-sach`), Phòng thử (`ai-phong-thu`)
    - Nhân sự & Phân quyền (`nhansu`) — tab: Nhân viên (`ns-nhan-vien`), Vai trò & Quyền (`ns-vai-tro`), Lịch sử (`ns-lich-su`), Lịch ca (`ns-lich-ca`)
    - Hệ thống & Nhật ký (`hethong`) — tab: Sức khoẻ hệ thống (`ht-suc-khoe`), Sao lưu & Bảo trì (`ht-sao-luu`), Nhật ký hoạt động (`ht-nhat-ky`)

**Nơi hiện thực**

- Mã: `dashboard/index.html`, `dashboard/src/00-gan-tab.js`, `dashboard/src/01b-dieu-huong.js`, `dashboard/src/10-vong-lam-moi.js`, `dashboard/src/19-phan-tich.js`, `agent/api/phan_tich.py`
- API (quyền đọc từ route thật):
    - `GET /api/phan-tich` — `bao_cao.doc`
    - `GET /api/phan-tich/bo-loc` — `bao_cao.doc`
- Giao diện: màn `hoithoai`, màn `khachhang`, màn `donhang`, màn `kho`, màn `congviec`, màn `sohieu`, màn `cauhinhchung`, màn `cauhinhai`, màn `nhansu`, màn `hethong`

**Lệch so với bảng / ghi chú**

- Màn Phân tích giữ id cũ `sohieu` (chỉ đổi nhãn) để đường dẫn và quyền cũ không gãy.
- Bảng "Khách đến từ đâu" (đếm theo trạng thái, sai nghĩa) đã gỡ khỏi Phân tích.

## Mục 5. Cấu hình AI Agent: 5 tab, bật/tắt AI, chế độ chung mọi kênh

**Trạng thái: Đạt một phần**

Nghiệm thu trên app đầy đủ + Postgres thật: kịch bản 4 — Kênh thêm bằng cấu hình; agent là tuỳ chọn (**đạt**); kịch bản 9 — Nhiều agent theo cấu hình; định tuyến theo cấu hình (**đạt**).

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 5.1 | Năm tab: Cấu hình cơ bản, Tri thức (RAG), Kỹ năng & Công cụ, Chính sách & Ủy quyền, Phòng thử; ba màn cũ chuyển vào nguyên vẹn | Đạt | `test_cay_menu::test_tab_dung_id_hop_dong_va_nam_dung_man`<br>`test_cay_menu::test_noi_dung_cu_nam_dung_tab` |
| 5.2 | Công tắc bật/tắt AI Agent toàn cục: bền qua khởi động lại, ghi nhật ký, máy chủ từ chối thì công tắc trả về | Đạt | `test_cay_menu::test_cong_tac_ai_ghi_dung_duong_runtime`<br>`test_cong_tac_ai_toan_cuc::test_ai_TAT_khong_tra_loi_khong_nhap_va_vao_hang_cho_nguoi` |
| 5.3 | Hội thoại nhân viên đã tiếp quản thì AI không chen vào, dù công tắc đang bật; bật lại không giành hội thoại | Đạt | `test_cong_tac_ai_toan_cuc::test_nhan_vien_da_tiep_quan_thi_AI_khong_tra_loi_du_dang_BAT`<br>`test_cong_tac_ai_toan_cuc::test_bat_lai_AI_khong_gianh_hoi_thoai_nhan_vien_dang_cam`<br>`test_cong_tac_ai_toan_cuc::test_agent_bat_xet_nguoi_tiep_quan_TRUOC_cong_tac` |
| 5.4 | Chế độ Gợi ý / Tự động rời thanh trên vào Cấu hình cơ bản (ngắt khẩn cấp ở lại thanh trên) | Đạt | `test_cay_menu::test_bo_chon_che_do_roi_thanh_tren_vao_cau_hinh_co_ban` |
| 5.5 (bảng 5.4) | Một cấu hình AI chung cho mọi kênh *Luồng chính là một cấu hình; hồ sơ agent theo kênh và công tắc agent theo kênh vẫn còn, gói trong mục "Nâng cao".* | Đạt một phần | `test_cay_menu::test_khe_nha_cung_cap_nam_trong_ai_co_ban`<br>`test_agent_bat_theo_kenh::test_tat_theo_kenh_thi_chan_va_NOI_RO_LY_DO`<br>`test_ho_so_agent::test_main_truyen_ho_so_theo_kenh` |
| 5.6 | Nhà cung cấp AI, khoá, model chỉnh ở Cấu hình cơ bản và có hiệu lực ngay | Đạt | `test_ket_noi_tich_hop::test_model_chat_tren_dashboard_co_hieu_luc`<br>`test_ket_noi_tich_hop::test_kiem_ai_dung_model_chat_va_endpoint_vua_go` |
| 5.7 | Phòng thử mô phỏng công cụ ghi (không gọi thật); công cụ ghi đã cho phép chỉ gọi thật ở chế độ Tự động | Đạt | `test_thu_nghiem_mcp::test_ghi_trong_sandbox_khong_goi_that`<br>`test_thu_nghiem_mcp::test_ghi_da_cho_phep_thi_goi_that` |

Test canh nêu tên: **15**; các tệp test ấy (6 tệp) có tổng **86** hàm test.

**Nơi hiện thực**

- Mã: `agent/runtime.py`, `agent/core/agent_bat.py`, `agent/api/ho_so_agent.py`, `dashboard/src/23-ai-co-ban.js`, `dashboard/src/11-ky-nang.js`
- API (quyền đọc từ route thật):
    - `POST /api/runtime` — `agent.dieu_khien`
    - `GET /api/ket-noi/ai` — `cau_hinh.sua`
- Giao diện: màn `cauhinhai`, tab `ai-co-ban`, tab `ai-tri-thuc`, tab `ai-ky-nang`, tab `ai-chinh-sach`, tab `ai-phong-thu`

**Câu hỏi mở — cần chủ dự án xác nhận**

- Giữ hay gỡ hồ sơ agent theo kênh và công tắc agent theo kênh (đang ở "Nâng cao")? Bảng 5.4 chỉ nói một cấu hình chung.

## Mục 6. Thanh thông tin hội thoại gọn; ghi chú nội bộ trong ô soạn tin

**Trạng thái: Đạt**

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 6.1 | Thứ tự: Tên khách · Nhãn hội thoại (ngay dưới tên) · Customer 360 · Hành động xử lý · Chi tiết | Đạt | `test_thanh_thong_tin_hoi_thoai::test_thu_tu_ten_nhan_c360_hanh_dong_chi_tiet` |
| 6.2 | Gỡ trạng thái, kênh, Mode, SLA khỏi thanh; ưu tiên (kèm Đổi), version, chế độ AI vào panel Chi tiết | Đạt | `test_thanh_thong_tin_hoi_thoai::test_load_thread_khong_ve_lai_nhung_thu_da_go`<br>`test_thanh_thong_tin_hoi_thoai::test_chi_tiet_hoi_thoai_co_uu_tien_version_che_do_khong_co_sla` |
| 6.3 | Nút xử lý: một nút chính + menu "⋯", theo trạng thái × quyền (hàm thuần, test chạy bằng node) | Đạt | `test_thanh_thong_tin_hoi_thoai::test_bang_nut_theo_trang_thai_va_quyen`<br>`test_thanh_thong_tin_hoi_thoai::test_khong_bao_gio_qua_nhieu_nut_mot_luc`<br>`test_thanh_thong_tin_hoi_thoai::test_tu_gui_moi_duyet_truoc_va_nguoc_lai` |
| 6.4 | Ô soạn hai kiểu "Trả lời khách" / "Ghi chú nội bộ"; kiểu ghi chú không bao giờ gọi đường gửi; bản nháp tách theo kiểu | Đạt | `test_thanh_thong_tin_hoi_thoai::test_o_soan_kieu_ghi_chu_khong_bao_gio_goi_duong_gui`<br>`test_nhom_khong_phai_khach::test_route_ghi_chu_khong_cham_toi_duong_gui`<br>`test_thanh_thong_tin_hoi_thoai::test_ban_nhap_tach_theo_kieu_soan`<br>`test_thanh_thong_tin_hoi_thoai::test_nop_form_doc_kieu_soan_truoc_khi_cho_mang` |
| 6.5 | Ghi chú xen trong luồng tin theo thời gian, kèm tên nhân viên và giờ; chỉ người có quyền ghi chú mới thấy kiểu ghi chú | Đạt | `test_thanh_thong_tin_hoi_thoai::test_ghi_chu_xen_trong_luong_theo_thoi_gian`<br>`test_thanh_thong_tin_hoi_thoai::test_che_do_soan_chi_cho_nguoi_co_quyen_ghi_chu` |
| 6.6 | Mở lại hội thoại đã giải quyết (cần quyền nhận hội thoại) | Đạt | `test_nhom_khong_phai_khach::test_mo_lai_tay_hoi_thoai_da_giai_quyet`<br>`test_nhom_khong_phai_khach::test_mo_lai_tay_can_quyen_nhan` |

Test canh nêu tên: **14**; các tệp test ấy (2 tệp) có tổng **24** hàm test.

**Nơi hiện thực**

- Mã: `dashboard/src/03b-thanh-hoi-thoai.js`, `dashboard/src/03-hoi-thoai.js`, `agent/api/hoi_thoai_nhan.py`
- API (quyền đọc từ route thật):
    - `GET /api/inbox/conversations/{conversation_id}/ghi-chu` — `hoi_thoai.doc`
    - `POST /api/inbox/conversations/{conversation_id}/ghi-chu` — `hoi_thoai.ghi_chu`
    - `POST /api/inbox/conversations/{conversation_id}/giai-quyet` — `hoi_thoai.nhan`
    - `POST /api/inbox/conversations/{conversation_id}/mo-lai` — `hoi_thoai.nhan`
- Giao diện: màn `hoithoai`

## Mục 7. Mẫu trả lời và quy tắc tự động: ưu tiên, xung đột, chống trùng với AI

**Trạng thái: Đạt**

Nghiệm thu trên app đầy đủ + Postgres thật: kịch bản 13 — Quy tắc tự động: khi khách nhắn → nếu … → thì … (**đạt**).

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 7.1 | Mẫu trả lời nhanh: tạo/tìm/sửa/xoá, mã tắt; nhân viên dùng được, không sửa được | Đạt | `test_api_tra_loi_nhanh::test_tao_tim_sua_xoa`<br>`test_api_tra_loi_nhanh::test_ma_trung_la_409`<br>`test_api_tra_loi_nhanh::test_nhan_vien_dung_duoc_khong_sua_duoc` |
| 7.2 | Cụm cấm của luật quảng cáo mỹ phẩm bị chặn cả lúc tạo lẫn lúc sửa mẫu; mẫu bị sửa thành câu cấm thì quy tắc không gửi | Đạt | `test_api_tra_loi_nhanh::test_cum_cam_quang_cao_khong_luu_duoc`<br>`test_api_tra_loi_nhanh::test_sua_mau_thanh_cau_cam_cung_bi_chan`<br>`test_tu_dong::test_mau_bi_sua_thanh_cau_cam_thi_khong_gui` |
| 7.3 | Chèn mẫu bằng "/" trong ô soạn | Đạt | `test_tu_dong_giao_dien::test_go_gach_cheo_chen_mau_tra_loi_nhanh`<br>`test_tu_dong_giao_dien::test_o_nhan_tin_gan_khung_mau` |
| 7.4 | Thứ tự ưu tiên ổn định (thứ tự → lúc tạo → id); "dừng xét quy tắc sau" | Đạt | `test_tu_dong::test_thu_tu_on_dinh_cung_so_uu_tien`<br>`test_tu_dong::test_dung_xet_quy_tac_sau` |
| 7.5 | Xung đột: tối đa MỘT tin tự động mỗi tin khách; nhãn/việc gộp; chuyển người quy tắc đầu thắng; mẫu của quy tắc chuyển người thay câu báo cố định | Đạt | `test_tu_dong::test_nhieu_quy_tac_khop_khach_nhan_mot_tin_nhan_gop`<br>`test_tu_dong::test_chuyen_nguoi_uu_tien_hon_thi_mau_sau_nhuong`<br>`test_tu_dong::test_mau_cua_quy_tac_chuyen_nguoi_la_cau_bao`<br>`test_tu_dong::test_viec_cung_tieu_de_chi_tao_mot` |
| 7.6 | Kiểm lúc lưu chặn quy tắc mâu thuẫn; "một lần" tính theo từng loại hành động | Đạt | `test_tu_dong::test_kiem_luc_luu_chan_mau_thuan`<br>`test_tu_dong::test_mot_lan_tinh_theo_tung_loai_hanh_dong` |
| 7.7 | Chống trùng với AI: AI nhường đúng tin quy tắc đã gửi mẫu (trừ khi bật "cho AI trả lời"); nhường đặt sau các nhánh giao người | Đạt | `test_tu_dong::test_cho_ai_tra_loi_thi_ai_khong_nhuong`<br>`test_tu_dong::test_ai_nhuong_dat_sau_cac_nhanh_chuyen_nguoi` |
| 7.8 | Không gửi mẫu khi nhân viên đang tiếp, đang duyệt trước khi gửi, khách đòi gặp người, hội thoại nhóm — gắn nhãn/tạo việc vẫn chạy | Đạt | `test_tu_dong::test_nguoi_dang_tiep_thi_khong_gui_mau`<br>`test_tu_dong::test_khong_gui_mau_nhung_van_gan_nhan` |
| 7.9 | Mẫu đang được quy tắc bật dùng thì không đổi mã / xoá được (409) | Đạt | `test_api_tra_loi_nhanh::test_doi_ma_hoac_xoa_mau_quy_tac_dang_dung_la_409` |
| 7.10 | Biểu mẫu ba nhóm Thông tin · Nếu · Thì; câu chính sách; lần chạy cuối, lỗi cuối, nhật ký từng quy tắc | Đạt | `test_tu_dong_giao_dien::test_bieu_mau_quy_tac_ba_nhom_dung_thu_tu_va_du_o`<br>`test_tu_dong_giao_dien::test_chinh_sach_hien_cho_nguoi_van_hanh`<br>`test_tu_dong_giao_dien::test_dong_quy_tac_hien_dau_vet_chay` |
| 7.11 | Quy tắc cấu hình trên dashboard chạy đúng trên luồng tin vào thật (đầu–cuối) | Đạt | `test_tu_dong_dau_cuoi::test_quy_tac_cau_hinh_tren_dashboard_chay_dung_tren_luong_tin_vao` |

Test canh nêu tên: **25**; các tệp test ấy (4 tệp) có tổng **52** hàm test.

**Nơi hiện thực**

- Mã: `agent/omnichannel/tu_dong.py`, `agent/api/tu_dong_api.py`, `agent/api/tra_loi_nhanh.py`, `agent/migrations/versions/0060_quy_tac_uu_tien_va_xung_dot.sql`, `dashboard/src/15-tu-dong.js`
- API (quyền đọc từ route thật):
    - `GET /api/tu-dong` — `dinh_tuyen.doc`
    - `POST /api/tu-dong` — `dinh_tuyen.sua`
    - `PUT /api/tu-dong/{quy_tac_id}` — `dinh_tuyen.sua`
    - `GET /api/tu-dong/lan-chay` — `dinh_tuyen.doc`
    - `GET /api/tra-loi-nhanh` — `hoi_thoai.tra_loi`
    - `POST /api/tra-loi-nhanh` — `tra_loi_nhanh.sua`
- Giao diện: tab `cc-tu-dong`

## Mục 8. Kết nối & Tích hợp: kênh, ERPNext, GHN, GHTK, webhook, nhà cung cấp AI, thông báo minh bạch AI

**Trạng thái: Đạt**

Nghiệm thu trên app đầy đủ + Postgres thật: kịch bản 4 — Kênh thêm bằng cấu hình; agent là tuỳ chọn (**đạt**); kịch bản 16 — "Gặp nhân viên" — lời hứa trong câu thông báo AI được giữ bằng mã (**đạt**); kịch bản 17 — Hãng vận chuyển GHTK báo trạng thái về (webhook DẠNG FORM) (**đạt**).

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 8.1 | ERPNext, GHN, GHTK mỗi dịch vụ một thẻ, bốn trạng thái; nhập/sửa trên dashboard; đổi khoá thì kết quả kiểm cũ về "chưa kiểm tra" | Đạt | `test_ket_noi_tich_hop::test_bon_trang_thai_va_doi_khoa_thi_ve_chua_kiem_tra`<br>`test_ket_noi_tich_hop::test_chua_cau_hinh_khi_thieu_truong_bat_buoc`<br>`test_ket_noi_tich_hop::test_luu_tu_choi_truong_cua_dich_vu_khac`<br>`test_ket_noi_tich_hop_pg::test_so_kiem_va_trang_thai` |
| 8.2 | "Kiểm tra kết nối" chỉ gọi hàm ĐỌC của dịch vụ; báo rõ lỗi (vd. 401) | Đạt | `test_ket_noi_tich_hop::test_kiem_ghn_va_ghtk_goi_dung_ham_chi_doc_va_che_token`<br>`test_ket_noi_tich_hop::test_kiem_erpnext_bao_ro_401`<br>`test_ket_noi_tich_hop::test_kiem_bang_gia_tri_vua_go_thi_khong_ghi` |
| 8.3 | Che bí mật: không trả giá trị khoá về giao diện; xem cũng cần quyền sửa cấu hình | Đạt | `test_ket_noi_tich_hop::test_tong_quan_khong_lo_bi_mat`<br>`test_ket_noi_tich_hop::test_xem_cung_can_quyen_sua_cau_hinh` |
| 8.4 | Lịch sử thay đổi: ai, lúc nào, trường nào — không lưu giá trị | Đạt | `test_ket_noi_tich_hop::test_lich_su_ghi_ten_truong_khong_ghi_gia_tri`<br>`test_ket_noi_tich_hop_pg::test_lich_su_ghi_that_khong_co_gia_tri` |
| 8.5 | Sổ webhook vào: mọi lời gọi `/webhook/*` kể cả lời bị từ chối, thống kê, lỗi gần nhất; không ghi token | Đạt | `test_ket_noi_tich_hop::test_middleware_ghi_webhook_bi_tu_choi_va_khong_ghi_token`<br>`test_ket_noi_tich_hop_pg::test_so_webhook_ghi_thong_ke_va_lich_su` |
| 8.6 | Đổi cấu hình trên dashboard có hiệu lực không cần khởi động lại (token GHN, khoá ERPNext, MODEL_CHAT) | Đạt | `test_ket_noi_tich_hop::test_token_ghn_doi_tren_dashboard_khong_can_khoi_dong_lai`<br>`test_ket_noi_tich_hop::test_doi_khoa_erpnext_bo_cong_cu`<br>`test_ket_noi_tich_hop::test_model_chat_tren_dashboard_co_hieu_luc` |
| 8.7 | Nhà cung cấp AI: nhà cung cấp, khoá, endpoint (OpenAI), model; chỉ khai nhà cung cấp gọi được thật; cảnh báo model khác họ | Đạt | `test_ket_noi_tich_hop::test_ai_chi_khai_nha_cung_cap_llm_that_su_goi_duoc`<br>`test_ket_noi_tich_hop::test_canh_bao_model_khac_ho_nha_cung_cap` |
| 8.8 | Thông báo minh bạch AI sửa được, bốn luật giữ lời hứa "gặp nhân viên"; một lần mỗi hội thoại | Đạt | `test_ket_noi_tich_hop::test_noi_dung_sai_bi_chan`<br>`test_ket_noi_tich_hop::test_luu_noi_dung_sai_bi_422_va_dung_thi_khach_nhan_cau_moi`<br>`test_ket_noi_tich_hop::test_noi_dung_env_hong_thi_lui_ve_mac_dinh_khong_im`<br>`test_ket_noi_tich_hop_pg::test_hai_tin_toi_cung_luc_chi_mot_thong_bao` |
| 8.9 | Kênh: danh sách plugin kênh, nhiều tài khoản mỗi nền tảng, trạng thái từng tài khoản (chi tiết ở mục 20) | Đạt | `test_ket_noi_tich_hop_pg::test_tuy_chon_an_binh_luan_theo_trang_va_danh_sach_plugin` |
| 8.10 | Mỗi tài khoản kênh MỘT trạng thái suy từ sức khoẻ thật (Chưa kết nối / Hoạt động / Tạm ngắt / Cần xác thực lại / Lỗi); mã kỹ thuật dịch thành nguyên nhân + cách sửa | Đạt | `test_ket_noi_hop_nhat::test_trang_thai_hop_nhat`<br>`test_ket_noi_hop_nhat::test_moi_trang_thai_tai_khoan_deu_co_loi_giai_thich`<br>`test_ket_noi_hop_nhat_pg::test_suc_khoe_tong_tra_mot_trang_thai_va_giai_thich` |
| 8.11 | Dòng thời gian từng tài khoản kênh (sức khoẻ, sự kiện, cấu hình) và lịch sử cấu hình lọc theo dịch vụ, thời gian; theo quyền và phạm vi kênh | Đạt | `test_ket_noi_hop_nhat_pg::test_dong_thoi_gian_gop_ba_so_va_bo_nhip_tim`<br>`test_ket_noi_hop_nhat::test_dong_thoi_gian_ngoai_pham_vi_kenh_la_404`<br>`test_ket_noi_hop_nhat_pg::test_lich_su_cau_hinh_loc_thoi_gian_o_may_chu` |
| 8.12 | Ẩn bình luận có SĐT: tuỳ chọn riêng từng Trang thắng cấu hình chung | Đạt | `test_ket_noi_tich_hop::test_tuy_chon_rieng_cua_trang_thang_cau_hinh_chung`<br>`test_ket_noi_tich_hop::test_tuy_chon_trang_can_quyen_kenh_sua` |
| 8.13 (bảng 8.10–8.11) | Cấu hình VietQR không hiện trên giao diện (mã giữ nguyên) | Ngoài phạm vi theo bảng | `test_cay_menu::test_csat_va_vietqr_khong_hien_nhung_ma_con` |
| 8.14 (bảng 8.10–8.11) | CSAT tạm hoãn, mặc định tắt | Ngoài phạm vi theo bảng | `test_cay_menu::test_csat_mac_dinh_tat` |

Test canh nêu tên: **33**; các tệp test ấy (5 tệp) có tổng **91** hàm test.

**Nơi hiện thực**

- Mã: `agent/ket_noi_tich_hop.py`, `agent/api/ket_noi_tich_hop.py`, `agent/omnichannel/thong_bao_ai.py`, `agent/migrations/versions/0057_ket_noi_tich_hop.sql`, `dashboard/src/22-ket-noi-tich-hop.js`, `dashboard/src/23-ai-co-ban.js`, `agent/omnichannel/giai_thich_loi_kenh.py`, `dashboard/src/18a-ket-noi-tai-khoan.js`, `dashboard/src/22b-ket-noi-lich-su.js`
- API (quyền đọc từ route thật):
    - `GET /api/ket-noi` — `cau_hinh.sua`
    - `GET /api/ket-noi/ai` — `cau_hinh.sua`
    - `PUT /api/ket-noi/dich-vu/{ma}` — `cau_hinh.sua`
    - `POST /api/ket-noi/dich-vu/{ma}/kiem-tra` — `cau_hinh.sua`
    - `GET /api/ket-noi/webhook` — `cau_hinh.sua`
    - `GET /api/ket-noi/lich-su` — `cau_hinh.sua`
    - `PUT /api/ket-noi/kenh/{account_id}/tuy-chon` — `kenh.sua`
    - `GET /api/ket-noi/kenh/{account_id}/dong-thoi-gian` — `kenh.doc`
- Giao diện: tab `cc-ket-noi`, tab `ai-co-ban`

**Lệch so với bảng / ghi chú**

- Bản này sửa hai lỗi hỏng im lặng: MODEL_CHAT đổi trên dashboard trước đây không có hiệu lực; token GHN và khoá ERPNext đổi trên dashboard trước đây cần khởi động lại.

## Mục 9. Phân biệt hội thoại nhóm và cá nhân

**Trạng thái: Đạt**

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 9.1 | Hội thoại nhóm mang danh tính NHÓM; người gửi tách riêng từng tin; thiếu tên nhóm thì tên dự phòng, không lấy tên người gửi | Đạt | `test_tin_nhom_zalo::test_tin_nhom_danh_tinh_la_nhom_nguoi_gui_tach_rieng`<br>`test_tin_nhom_zalo::test_ingest_nhom_hai_nguoi_gui_khong_doi_danh_tinh`<br>`test_tin_nhom_zalo::test_thieu_ten_nhom_thi_ten_du_phong_khong_lay_ten_nguoi_gui` |
| 9.2 | Huy hiệu Nhóm và tên người gửi trên giao diện; lọc nhóm / riêng ở hộp thư | Đạt | `test_tin_nhom_zalo::test_dashboard_gan_nhan_nhom_va_ten_nguoi_gui`<br>`test_trach_nhiem_hoi_thoai::test_bo_loc_chua_giao_nhom_va_qua_han_sla` |
| 9.3 | Danh sách hội thoại: tin cuối của nhóm kèm tên người gửi | Đạt | `test_thanh_thong_tin_hoi_thoai::test_tin_cuoi_trong_nhom_kem_ten_nguoi_gui`<br>`test_thanh_thong_tin_hoi_thoai::test_api_danh_sach_tra_vai_va_ten_nguoi_gui_tin_cuoi` |
| 9.4 | Trí nhớ khách riêng không đọc, không ghi cho nhóm (chống lộ dữ liệu cá nhân) | Đạt | `test_tin_nhom_zalo::test_tri_nho_khach_khong_doc_khong_ghi_cho_nhom` |
| 9.5 | Trả lời vào nhóm đúng loại thread | Đạt | `test_tin_nhom_zalo::test_tra_loi_nhom_thread_type_rong_van_gui_dung_loai` |
| 9.6 | Hệ thống không tự nói vào nhóm: AI không chạy, CSAT không hỏi, tin hệ thống bị chặn ở outbox; nhóm được giao cho người | Đạt | `test_tin_nhom_zalo::test_handle_inbound_nhom_AI_khong_chay_khong_nhap_giao_nguoi`<br>`test_tin_nhom_zalo::test_outbox_that_chan_he_thong_noi_vao_nhom_cho_nhan_vien_gui`<br>`test_tin_nhom_zalo::test_csat_khong_hoi_trong_nhom` |
| 9.7 (bảng 9.7) | Nhóm Zalo KHÔNG là khách hàng trong Customer 360: không vào danh sách, tìm kiếm, đếm khách vô chủ/khách mới; không gộp được; không có nút Customer 360 | Đạt | `test_nhom_khong_phai_khach::test_danh_sach_va_tim_khach_khong_co_nhom`<br>`test_nhom_khong_phai_khach::test_khach_vo_chu_va_khach_moi_khong_dem_nhom`<br>`test_nhom_khong_phai_khach::test_khong_gop_duoc_nhom_vao_mot_nguoi`<br>`test_nhom_khong_phai_khach::test_dich_vu_gop_tu_chan_nhom_khong_chi_route`<br>`test_thanh_thong_tin_hoi_thoai::test_nhom_khong_co_nut_customer_360` |
| 9.8 (bảng 9.10) | AI tham gia trả lời trong nhóm *Bảng ghi là hướng phát triển sau; hiện AI không chạy trong nhóm (test ở yêu cầu 9.6).* | Ngoài phạm vi theo bảng | — |

Test canh nêu tên: **17**; các tệp test ấy (4 tệp) có tổng **59** hàm test.

**Nơi hiện thực**

- Mã: `agent/channels/zalo_personal.py`, `agent/omnichannel/inbox_service.py`, `agent/omnichannel/identity.py`, `agent/core/lien_he_nhom.py`, `agent/migrations/versions/0051_tin_nhom_nguoi_gui.sql`
- API (quyền đọc từ route thật):
    - `GET /api/inbox/conversations` — `hoi_thoai.doc`
- Giao diện: màn `hoithoai`, màn `khachhang`

## Mục 10. Media khách gửi

**Trạng thái: Đạt**

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 10.1 | Tải ảnh/video/tệp khách gửi về máy chủ SAU khi tin đã lưu (không chặn luồng tin); vòng tải bật lúc khởi động | Đạt | `test_media_khach_gui::test_tin_vao_danh_dau_cho_tai`<br>`test_media_khach_gui::test_vong_tai_duoc_dung_luc_khoi_dong`<br>`test_media_khach_gui::test_whatsapp_hoi_kenh_lay_link` |
| 10.2 | Chống trùng theo sha256 (một tệp mỗi nội dung) | Đạt | `test_media_khach_gui::test_tai_ve_chong_trung_va_phuc_vu`<br>`test_media_khach_gui::test_duong_luu_theo_nam_thang_va_sha` |
| 10.3 | Thời hạn lưu tính từ lần gửi GẦN NHẤT, đổi được trên dashboard; dọn tệp mồ côi; xem trước rồi mới xoá; không bao giờ xoá ngoài thư mục media/uploads | Đạt | `test_media_khach_gui::test_mac_dinh_180_ngay_theo_quyet_dinh_chu_du_an`<br>`test_media_khach_gui::test_cau_hinh_thoi_han_kiem_gia_tri`<br>`test_media_khach_gui::test_don_theo_thoi_han_tinh_lan_gui_gan_nhat`<br>`test_media_khach_gui::test_don_mo_coi_va_danh_dau_mat_tep`<br>`test_media_khach_gui::test_khong_bao_gio_xoa_anh_san_pham_hay_tai_lieu` |
| 10.4 | Trần dung lượng mỗi tệp, đọc theo luồng; nhận dạng kiểu theo chữ ký đầu tệp, không tin header | Đạt | `test_media_khach_gui::test_vuot_tran_thi_dung_doc_ngay_khong_doc_tron`<br>`test_media_khach_gui::test_content_length_vuot_tran_thi_khong_tai`<br>`test_media_khach_gui::test_nhan_dang_theo_chu_ky_dau_tep`<br>`test_media_khach_gui::test_html_gia_anh_bi_bo_va_khong_de_lai_tep` |
| 10.5 | Thử lại có giãn cách, có trần; link chết thành "hết hạn"; lỗi mạng không ném | Đạt | `test_media_khach_gui::test_gian_cach_thu_lai_tang_dan_co_tran`<br>`test_media_khach_gui::test_hong_tam_thi_hen_thu_lai_roi_bao_loi`<br>`test_media_khach_gui::test_ma_http_ra_trang_thai`<br>`test_media_khach_gui::test_mang_hong_la_hong_tam_khong_nem` |
| 10.6 | Phục vụ bản trên máy với kiểu máy chủ nhận dạng (nosniff); hộp thư và AI ưu tiên bản trên máy | Đạt | `test_media_khach_gui::test_duong_phuc_vu_tep_dung_kieu_may_chu_nhan_dang`<br>`test_media_khach_gui::test_hop_thu_dashboard_uu_tien_ban_tren_may`<br>`test_media_khach_gui::test_agent_hoi_ban_tren_may_truoc` |
| 10.7 | Xoá dữ liệu khách (PDPD) xoá ngay media của khách, trừ nội dung người khác còn giữ; sao lưu gồm media | Đạt | `test_media_khach_gui::test_pdpd_xoa_media_cua_khach_tru_noi_dung_nguoi_khac_con_giu`<br>`test_media_khach_gui::test_pdpd_ghi_tham_chieu_TRUOC_khi_xoa_hoi_thoai`<br>`test_media_khach_gui::test_sao_luu_gom_media_bo_tep_tam_va_khong_de_ban_ro` |
| 10.8 | Khung "Media khách gửi" ở Hệ thống > Sao lưu & Bảo trì; mọi route media khai quyền | Đạt | `test_media_khach_gui::test_dashboard_gan_khung_media`<br>`test_media_khach_gui::test_route_media_deu_khai_quyen` |

Test canh nêu tên: **26**; các tệp test ấy (1 tệp) có tổng **39** hàm test.

Mặc định đọc từ `agent/config.py`: giữ **180 ngày** kể từ lần gửi gần nhất, trần **25 MB** mỗi tệp.

**Nơi hiện thực**

- Mã: `agent/omnichannel/media.py`, `agent/omnichannel/media_don.py`, `agent/api/media_api.py`, `agent/core/anh_khach.py`, `agent/migrations/versions/0063_media_khach_gui.sql`, `dashboard/src/25-media.js`
- API (quyền đọc từ route thật):
    - `GET /api/media/tong-quan` — `cau_hinh.doc`
    - `POST /api/media/don` — `cau_hinh.sua`
    - `POST /api/media/thu-lai` — `cau_hinh.sua`
- Giao diện: tab `ht-sao-luu`

**Lệch so với bảng / ghi chú**

- Bảng ghi mục này "cần làm rõ"; hiện thực theo quyết định đã chốt khi rà soát 20.11.2026: tải về máy chủ, giữ theo thời hạn, chống trùng.
- Trước bản này media khách gửi KHÔNG được lưu: `attachments.url` chỉ giữ link CDN của hãng, hết hạn là mất hẳn.

**Câu hỏi mở — cần chủ dự án xác nhận**

- Chưa có trần TỔNG dung lượng cho thư mục media (chỉ trần từng tệp và thời hạn lưu). Có cần trần tổng / cảnh báo đầy đĩa không?

## Mục 12. Phân quyền RBAC theo chức năng

**Trạng thái: Đạt**

Nghiệm thu trên app đầy đủ + Postgres thật: kịch bản 2 — Phân quyền: không được cấp thì không thấy (**đạt**).

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 12.1 | Danh mục quyền nhóm theo chức năng của dashboard, mỗi quyền đúng một nhóm, đúng thứ tự phiếu việc | Đạt | `test_nhan_su_phan_quyen::test_moi_quyen_nam_trong_dung_mot_nhom_hien_thi`<br>`test_nhan_su_phan_quyen::test_nhom_dung_thu_tu_phieu_viec`<br>`test_nhan_su_phan_quyen::test_quyen_tach_rieng_theo_phieu_viec`<br>`test_quyen_danh_muc::test_moi_quyen_co_nhan_tieng_viet` |
| 12.2 | Hỏng-đóng: route `/api` chưa khai quyền thì máy chủ không khởi động; tên quyền lạ nổ lúc import | Đạt | `test_quyen_danh_muc::test_moi_route_deu_da_khai_quyen`<br>`test_quyen_danh_muc::test_chot_that_su_chan_route_quen_khai_quyen`<br>`test_quyen_danh_muc::test_khoi_dong_that_su_goi_chot`<br>`test_can_quyen::test_nem_ngay_luc_goi_neu_quyen_khong_co_trong_danh_muc` |
| 12.3 | Thiếu quyền thì 403 nói rõ thiếu gì; chưa đăng nhập thì 401; nhiều quyền là phải đủ tất cả | Đạt | `test_can_quyen::test_thieu_quyen_thi_403_va_noi_ro_thieu_gi`<br>`test_can_quyen::test_chua_dang_nhap_thi_401_chu_khong_403`<br>`test_can_quyen::test_nhieu_quyen_la_phai_co_du_khong_phai_mot_trong_so` |
| 12.4 | Chống leo thang: không tự gán Quản trị, không tạo/sửa vai trò mạnh hơn mình, không hạ cấp hay khoá cấp trên | Đạt | `test_chan_leo_thang_quyen::test_khong_tu_gan_quan_tri_cho_minh`<br>`test_chan_leo_thang_quyen::test_khong_tao_vai_tro_co_quyen_minh_khong_co`<br>`test_chan_leo_thang_quyen::test_khong_sua_hay_xoa_vai_tro_manh_hon_minh`<br>`test_chan_leo_thang_quyen::test_khong_ha_cap_hay_khoa_cap_tren` |
| 12.5 | Lịch sử đổi quyền có trước/sau, ghi trong cùng giao dịch; xem cần quyền nhân sự | Đạt | `test_nhan_su_phan_quyen::test_lich_su_doi_quyen_ghi_truoc_sau`<br>`test_nhan_su_phan_quyen::test_lich_su_can_quyen_doc_nhan_su`<br>`test_nhan_su_phan_quyen::test_moi_loai_lich_su_deu_hien_tren_man_lich_su` |
| 12.6 | Đổi vai trò có hiệu lực ngay với người đang đăng nhập | Đạt | `test_nhan_su_phan_quyen::test_doi_vai_tro_co_hieu_luc_ngay_voi_nguoi_dang_dang_nhap` |
| 12.7 | Quyền tách theo việc: duyệt nháp AI cần `ai.duyet`, Kho có quyền riêng; tên quyền đã gỡ không bao giờ dùng lại | Đạt | `test_nhan_su_phan_quyen::test_duyet_ban_nhap_can_ai_duyet_khong_phai_tra_loi`<br>`test_nhan_su_phan_quyen::test_kho_co_quyen_rieng`<br>`test_quyen_danh_muc::test_quyen_da_go_khong_bao_gio_dung_lai_ten` |
| 12.8 | Quyền riêng từng người, ABAC, phạm vi Cá nhân/Nhóm/Tất cả *Bảng chốt chỉ RBAC qua vai trò.* | Ngoài phạm vi theo bảng | — |

Test canh nêu tên: **22**; các tệp test ấy (4 tệp) có tổng **54** hàm test.

**Danh mục quyền đọc từ `agent/core/quyen.py`:** 46 quyền trong 11 nhóm chức năng; 2 tên đã gỡ, không bao giờ dùng lại.

| Nhóm | Số quyền | Quyền |
|---|---|---|
| Hội thoại | 5 | `hoi_thoai.doc`, `hoi_thoai.xem_tat_ca`, `hoi_thoai.tra_loi`, `hoi_thoai.nhan`, `hoi_thoai.ghi_chu` |
| Khách hàng | 7 | `khach.doc`, `khach.xem_tat_ca`, `khach.sua`, `khach.giao`, `khach.gop`, `khach.pii`, `khach.xoa` |
| Đơn hàng | 2 | `don.doc`, `don.sua` |
| Kho | 3 | `kho.doc`, `kho.sua`, `catalog.duyet` |
| Công việc | 4 | `cong_viec.doc`, `cong_viec.xem_tat_ca`, `cong_viec.sua`, `cong_viec.giao` |
| Phân tích | 1 | `bao_cao.doc` |
| Cấu hình chung | 8 | `tra_loi_nhanh.sua`, `dinh_tuyen.doc`, `dinh_tuyen.sua`, `kenh.doc`, `kenh.sua`, `kenh.noi`, `tich_hop.doc`, `tich_hop.sua` |
| Cấu hình AI Agent | 9 | `agent.doc`, `agent.dieu_khien`, `phong_thu.dung`, `cau_hinh.doc`, `cau_hinh.sua`, `ky_nang.doc`, `ky_nang.sua`, `mcp.doc`, `mcp.sua` |
| Nhân sự & Phân quyền | 2 | `nguoi_dung.doc`, `nguoi_dung.sua` |
| Hệ thống & Nhật ký | 4 | `nhat_ky.doc`, `nhat_ky.su_co`, `outbox.doc`, `outbox.sua` |
| Phê duyệt AI | 1 | `ai.duyet` |

**Nơi hiện thực**

- Mã: `agent/core/quyen.py`, `agent/api/quyen.py`, `agent/api/phu_thuoc.py`, `agent/core/xac_thuc.py`
- API (quyền đọc từ route thật):
    - `GET /api/quyen` — `nguoi_dung.doc`
    - `GET /api/vai-tro` — `nguoi_dung.doc`
    - `POST /api/vai-tro` — `nguoi_dung.sua`
    - `PUT /api/vai-tro/{vai_tro_id}` — `nguoi_dung.sua`
    - `PUT /api/nguoi-dung/{nguoi_dung_id}/vai-tro` — `nguoi_dung.sua`
    - `GET /api/nhan-su/lich-su` — `nguoi_dung.doc`
- Giao diện: tab `ns-vai-tro`

**Lệch so với bảng / ghi chú**

- Phạm vi theo KÊNH (thành viên kênh — người chỉ thấy hội thoại/khách của kênh mình được giao) có từ trước bảng và vẫn giữ; nó không phải quyền riêng từng người mà là phạm vi dữ liệu.

**Câu hỏi mở — cần chủ dự án xác nhận**

- Giữ phạm vi theo kênh (thành viên kênh) như hiện nay — có mâu thuẫn với câu "không phạm vi Cá nhân/Nhóm/Tất cả" của bảng không?

## Mục 13. Vai trò động và quản lý nhân viên

**Trạng thái: Đạt**

Nghiệm thu trên app đầy đủ + Postgres thật: kịch bản 3 — Nhân viên nghỉ việc (**đạt**).

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 13.1 | Hai tab Nhân viên / Vai trò trong Nhân sự & Phân quyền | Đạt | `test_nhan_su_phan_quyen::test_hai_tab_nhan_su_gan_vao_khung_tab`<br>`test_nhan_su_phan_quyen::test_giao_dien_goi_dung_cac_duong_moi` |
| 13.2 | Vai trò động tạo/sửa không cần sửa mã; ngừng dùng / dùng lại; xoá hẳn chỉ khi chưa từng gán; vai trò dựng sẵn luôn dùng | Đạt | `test_nhan_su_phan_quyen::test_vai_tro_ngung_dung_khong_gan_moi_duoc_va_khong_xoa_duoc`<br>`test_nhan_su_phan_quyen::test_csdl_chan_gan_vai_tro_ngung_dung_va_ngung_vai_tro_he_thong`<br>`test_nhan_su_phan_quyen::test_khong_ngung_dung_hay_dung_lai_vai_tro_manh_hon_minh` |
| 13.3 | Vai trò ngừng dùng không cấp quyền ở BẤT KỲ chỗ tính quyền nào (phiên, chuông, PDPD, giao khách...) | Đạt | `test_nhan_su_phan_quyen::test_moi_cho_tinh_quyen_deu_loc_vai_tro_ngung_dung`<br>`test_nhan_su_phan_quyen::test_phep_quet_tren_that_su_bat_duoc_cho_quen` |
| 13.4 | Nhân viên: tạo kèm email + vai trò một lượt; sửa họ tên/email; email duy nhất | Đạt | `test_nhan_su_phan_quyen::test_sua_thong_tin_nhan_vien_va_email_duy_nhat` |
| 13.5 | Khoá nhân viên: cảnh báo việc đang giữ, chuyển việc hàng loạt qua đúng luật giao; bỏ qua phải nói rõ và được ghi lại; khoá là mất phiên ngay | Đạt | `test_nhan_su_phan_quyen::test_khoa_nguoi_dang_giu_viec_thi_canh_bao_roi_chuyen_viec`<br>`test_nhan_su_phan_quyen::test_khoa_de_lai_viec_phai_noi_ro_va_duoc_ghi_lai`<br>`test_nhan_su_phan_quyen::test_chuyen_viec_can_dung_quyen_va_khong_lay_viec_cap_tren`<br>`test_nhan_su_phan_quyen::test_khoa_tren_man_hinh_hoi_ve_viec_dang_giu`<br>`test_nghiem_thu_saas::test_03_khoa_nhan_vien_da_moi_phien` |
| 13.6 | Không xoá nhân viên (chỉ khoá) — bộ sinh bảng kiểm không có route DELETE nào dưới `/api/nguoi-dung` | Đạt | `test_bang_yeu_cau::test_khong_co_route_bi_cam` |
| 13.7 | Nâng cấp CSDL giữ nguyên ai làm được gì (cấp quyền mới cho đúng vai trò đang làm được việc ấy) | Đạt | `test_nhan_su_phan_quyen::test_migration_0058_giu_nguyen_ai_lam_duoc_gi` |

Test canh nêu tên: **15**; các tệp test ấy (3 tệp) có tổng **55** hàm test.

**Nơi hiện thực**

- Mã: `agent/api/tai_khoan.py`, `agent/api/nhan_su.py`, `agent/api/quyen.py`, `agent/migrations/versions/0058_nhan_su_phan_quyen.sql`, `dashboard/src/24-nhan-su.js`
- API (quyền đọc từ route thật):
    - `GET /api/nguoi-dung` — `nguoi_dung.doc`
    - `POST /api/nguoi-dung` — `nguoi_dung.sua`
    - `PUT /api/nguoi-dung/{nguoi_dung_id}` — `nguoi_dung.sua`
    - `POST /api/nguoi-dung/{ten}/khoa` — `nguoi_dung.sua`
    - `GET /api/nguoi-dung/{nguoi_dung_id}/viec-dang-giu` — `nguoi_dung.doc`
    - `POST /api/nguoi-dung/{nguoi_dung_id}/chuyen-viec` — `nguoi_dung.sua`
    - `POST /api/vai-tro/{vai_tro_id}/trang-thai` — `nguoi_dung.sua`
    - `DELETE /api/vai-tro/{vai_tro_id}` — `nguoi_dung.sua`
- Giao diện: màn `nhansu`, tab `ns-nhan-vien`, tab `ns-vai-tro`

## Mục 14. Phân công công việc

**Trạng thái: Đạt**

Nghiệm thu trên app đầy đủ + Postgres thật: kịch bản 7 — Phân task, quản lý task và thông báo nội bộ (**đạt**); kịch bản 14 — Lịch ca trực: bộ định tuyến chỉ giao cho người đang trong ca (**đạt**); kịch bản 21 — Hệ thống giao việc: phân công theo ca trực, chuyển việc, tiến độ, kết quả, lịch sử, chuông (**đạt**).

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 14.1 | Trạng thái chuẩn: Chờ xử lý, Đang thực hiện, Hoàn thành, Đã hủy; "Chưa phân công" là bộ lọc, không phải trạng thái | Đạt | `test_he_thong_giao_viec::test_nhan_trang_thai_theo_phieu_viec_ma_giu_nguyen` |
| 14.2 (bảng 14.2) | AI chuyển giao KHÔNG tự tạo công việc — báo qua chuông thông báo | Đạt | `test_thong_bao_noi_bo::test_ai_chuyen_giao_sinh_THONG_BAO_khong_sinh_CONG_VIEC`<br>`test_thong_bao_noi_bo::test_khong_con_duong_tu_sinh_viec_khi_chuyen_giao` |
| 14.3 | Tự phân công xoay vòng: người trong ca CÓ lịch, sẵn sàng, đúng kênh, lâu nhất chưa được giao; không ai thì Chưa phân công và báo người điều phối | Đạt | `test_he_thong_giao_viec::test_tu_dong_xoay_vong_nguoi_trong_ca_lau_nhat_chua_duoc_giao`<br>`test_he_thong_giao_viec::test_tu_dong_loai_nguoi_ngoai_ca_chua_co_lich_tat_san_sang`<br>`test_he_thong_giao_viec::test_khong_ai_du_dieu_kien_thi_chua_phan_cong_va_bao_dieu_phoi`<br>`test_he_thong_giao_viec::test_tu_dong_chi_giao_nguoi_thuoc_kenh_cua_hoi_thoai` |
| 14.4 | Lịch sử mọi đường đổi người nhận / trạng thái / kết quả (trigger CSDL, kể cả đường không qua API công việc) | Đạt | `test_he_thong_giao_viec::test_lich_su_ghi_tao_giao_chuyen_trang_thai_ket_qua_tien_do`<br>`test_he_thong_giao_viec::test_lich_su_ghi_ca_duong_khong_qua_api_cong_viec`<br>`test_he_thong_giao_viec::test_chuyen_viec_o_man_nhan_su_ghi_lich_su_dung_nguoi` |
| 14.5 | Liên kết hội thoại / khách / đơn bấm được; tạo việc từ hội thoại; chặn gắn hội thoại kênh khác; không giao cho người không xem được việc | Đạt | `test_he_thong_giao_viec::test_lien_ket_hoi_thoai_khach_don_bam_duoc`<br>`test_he_thong_giao_viec::test_tao_cong_viec_tu_hoi_thoai`<br>`test_he_thong_giao_viec::test_tao_tu_hoi_thoai_kenh_khac_thi_404`<br>`test_he_thong_giao_viec::test_giao_cho_nguoi_khong_xem_duoc_viec_thi_422` |
| 14.6 | Chuông cho việc chưa giao, bị huỷ, quá hạn (báo một lần, báo lại khi đổi hạn) | Đạt | `test_he_thong_giao_viec::test_qua_han_bao_mot_lan_va_bao_lai_khi_doi_han`<br>`test_he_thong_giao_viec::test_huy_viec_bao_nguoi_dang_lam`<br>`test_he_thong_giao_viec::test_chuong_cong_viec_mo_chi_tiet_viec` |
| 14.7 | Tổng quan ca trực theo phạm vi: ai trong ca, hội thoại chưa ai nhận, cảnh báo SLA; nhân viên thường không thấy tải của đồng nghiệp | Đạt | `test_he_thong_giao_viec::test_tong_quan_dem_theo_pham_vi_va_nguoi_trong_ca`<br>`test_he_thong_giao_viec::test_tong_quan_nhan_vien_thuong_khong_thay_tai_dong_nghiep` |
| 14.8 | Lịch ca trực và lịch nghỉ; bộ định tuyến chỉ giao cho người đang trong ca | Đạt | `test_lich_ca::test_bo_dinh_tuyen_bo_qua_nguoi_het_ca`<br>`test_lich_ca::test_lich_nghi_thang_ca_truc`<br>`test_lich_ca::test_bo_dinh_tuyen_khong_giao_cho_nguoi_bi_khoa` |
| 14.9 | Quy tắc tự động tạo việc có tuỳ chọn tự phân công | Đạt | `test_he_thong_giao_viec::test_quy_tac_tao_viec_nhan_giao_tu_dong_va_chan_gia_tri_la` |

Test canh nêu tên: **23**; các tệp test ấy (3 tệp) có tổng **60** hàm test.

**Nơi hiện thực**

- Mã: `agent/core/cong_viec.py`, `agent/core/giao_viec.py`, `agent/api/cong_viec.py`, `agent/api/lich_ca.py`, `agent/migrations/versions/0061_he_thong_giao_viec.sql`, `dashboard/src/25-cong-viec.js`, `dashboard/src/16-lich-ca.js`
- API (quyền đọc từ route thật):
    - `GET /api/cong-viec` — `cong_viec.doc`
    - `POST /api/cong-viec` — `cong_viec.sua`
    - `GET /api/cong-viec/tong-quan` — `cong_viec.doc`
    - `GET /api/cong-viec/{cong_viec_id}` — `cong_viec.doc`
    - `PUT /api/cong-viec/{cong_viec_id}` — `cong_viec.sua`
    - `POST /api/cong-viec/{cong_viec_id}/tien-do` — `cong_viec.sua`
    - `POST /api/cong-viec/{cong_viec_id}/tu-dong-giao` — `cong_viec.giao`
- Giao diện: màn `congviec`, tab `cv-ca-truc`, tab `cv-danh-sach`

**Lệch so với bảng / ghi chú**

- Việc do AI đề xuất (yêu cầu huỷ đơn chuyển cho người) giữ nguồn agent, chưa phân công và báo người điều phối — AI không tự tạo việc rời.

## Mục 15. SLA

**Trạng thái: Đạt**

Nghiệm thu trên app đầy đủ + Postgres thật: kịch bản 19 — Đổi ưu tiên hội thoại và xem màn Phân tích (**đạt**).

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 15.1 | Ba mục tiêu: phản hồi đầu, phản hồi sau chuyển giao, giải quyết; mỗi mục tiêu chế độ riêng (theo giờ làm việc / 24-7) và ngưỡng cảnh báo riêng | Đạt | `test_sla_muc_tieu_lich::test_che_do_va_nguong_theo_muc_tieu`<br>`test_sla_muc_tieu_lich::test_chuan_hoa_muc_tieu_chan_luc_luu`<br>`test_sla_muc_tieu_lich::test_luu_chinh_sach_khong_gui_o_nao_thi_giu_o_ay` |
| 15.2 | Một lịch làm việc chung (giờ từng thứ, ngày nghỉ, ngày lễ) là nguồn duy nhất cho hạn SLA, câu báo ngoài giờ và điều kiện ngoài giờ của quy tắc | Đạt | `test_sla_muc_tieu_lich::test_lich_tuan_ngay_nghi_ngay_le_va_cau_bao_ngoai_gio`<br>`test_sla_muc_tieu_lich::test_moi_noi_doc_gio_lam_viec_deu_qua_lich_chung`<br>`test_sla_muc_tieu_lich::test_sla_han_lich_trong_sql_khop_python`<br>`test_sla_muc_tieu_lich::test_tinh_tay_qua_ngay_nghi_va_ngay_le` |
| 15.3 | Hạn phản hồi sau chuyển giao: mỗi lượt chuyển một hạn; cảnh báo, vi phạm, chuông, chốt khi nhân viên trả lời | Đạt | `test_sla_muc_tieu_lich::test_chuyen_giao_mo_luot_canh_bao_vi_pham_chuong_va_chot`<br>`test_sla_muc_tieu_lich::test_nhan_vien_nhan_truoc_khi_vong_quet_mo_luot_thi_dat`<br>`test_sla_muc_tieu_lich::test_moc_chuyen_giao_tra_dung_ten_migration` |
| 15.4 | Xác nhận tự động (tin hệ thống) không tính là phản hồi đầu | Đạt | `test_sla_muc_tieu_lich::test_xac_nhan_tu_dong_khong_dat_phan_hoi_dau`<br>`test_sla_muc_tieu_lich::test_moi_nguon_xac_nhan_tu_dong_xep_hang_vai_system` |
| 15.5 | Ngưỡng cảnh báo cấu hình được, áp cho cả phản hồi đầu và giải quyết | Đạt | `test_phan_tich_va_sla::test_canh_bao_han_giai_quyet_o_nguong_mac_dinh_80`<br>`test_phan_tich_va_sla::test_nguong_canh_bao_cau_hinh_duoc_va_ap_ca_phan_hoi_dau` |
| 15.6 | Trễ SLA báo chuông người phụ trách và quản lý; KHÔNG sinh công việc | Đạt | `test_phan_tich_va_sla::test_tre_sla_ghi_su_kien_du_thong_tin_va_khong_sinh_cong_viec`<br>`test_thong_bao_noi_bo::test_sla_tre_bao_nguoi_phu_trach_va_quan_ly` |
| 15.7 | Đổi ưu tiên bắt buộc lý do, ghi nhật ký; nâng ưu tiên rút hạn từ bây giờ, hạ ưu tiên giữ hạn (trigger CSDL chỉ cho rút ngắn) | Đạt | `test_phan_tich_va_sla::test_nang_uu_tien_rut_han_tu_bay_gio_ha_uu_tien_giu_han`<br>`test_phan_tich_va_sla::test_trigger_chi_cho_rut_ngan_han_con_o_tuong_lai`<br>`test_phan_tich_va_sla::test_doi_uu_tien_ngoai_kenh_la_404_va_can_quyen` |
| 15.8 | Chỉ số SLA ở Phân tích: đúng hạn, vi phạm, xu hướng; mục tiêu sau chuyển giao; giải quyết AI / nhân viên | Đạt | `test_sla_muc_tieu_lich::test_phan_tich_muc_tieu_chuyen_giao_va_giai_quyet_ai_nhan_vien` |
| 15.9 | Tab SLA & Giờ làm việc; lịch và mục tiêu lưu trên dashboard có hiệu lực ở mọi nơi | Đạt | `test_sla_muc_tieu_lich::test_giao_dien_sla_gan_tab_va_khong_trung_o_cau_hinh`<br>`test_sla_muc_tieu_lich::test_api_lich_va_muc_tieu_co_hieu_luc_o_moi_noi` |

Test canh nêu tên: **22**; các tệp test ấy (3 tệp) có tổng **59** hàm test.

Ngưỡng cảnh báo mặc định (`Settings.sla_nguong_canh_bao`): **80%** thời hạn.

**Nơi hiện thực**

- Mã: `agent/omnichannel/sla.py`, `agent/omnichannel/sla_muc_tieu.py`, `agent/omnichannel/sla_chuyen_giao.py`, `agent/omnichannel/phan_hoi_that.py`, `agent/core/lich_lam_viec.py`, `agent/api/sla_cau_hinh.py`, `agent/api/uu_tien.py`, `agent/migrations/versions/0054_phan_tich_va_sla.sql`, `agent/migrations/versions/0062_sla_muc_tieu_va_lich_lam_viec.sql`, `dashboard/src/26-sla.js`
- API (quyền đọc từ route thật):
    - `GET /api/sla/cau-hinh` — `dinh_tuyen.doc`
    - `PUT /api/sla/lich-lam-viec` — `dinh_tuyen.sua`
    - `PUT /api/sla/muc-tieu` — `dinh_tuyen.sua`
    - `PUT /api/conversations/{cid}/uu-tien` — `hoi_thoai.nhan`
- Giao diện: tab `cc-sla`

**Lệch so với bảng / ghi chú**

- Chưa ai lưu lịch/mục tiêu trên dashboard thì hệ thống lui về `.env` như trước (`SLA_THEO_GIO_LAM_VIEC` áp cho MỌI mục tiêu).

**Câu hỏi mở — cần chủ dự án xác nhận**

- "Leo thang khi quá hạn" hiện là báo chuông thêm người quản lý (và tuỳ chọn `SLA_KHI_TRE` nâng ưu tiên, không rút hạn) — không có chuỗi leo thang nhiều bậc. Đủ chưa?

## Mục 16. Gợi ý có căn cứ và "Xem căn cứ"

**Trạng thái: Đạt**

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 16.1 | Bản nháp AI được phân loại căn cứ ở MÁY CHỦ: đủ / chưa đầy đủ (nói rõ thiếu gì) / không có / mâu thuẫn | Đạt | `test_can_cu_ban_nhap::test_du_can_cu`<br>`test_can_cu_ban_nhap::test_chua_day_du_noi_ro_thieu_gi`<br>`test_can_cu_ban_nhap::test_khong_co_can_cu_kem_cau_cho_trung_lap`<br>`test_can_cu_ban_nhap::test_mau_thuan_cung_cong_cu_hai_ket_qua`<br>`test_can_cu_ban_nhap::test_mau_thuan_gia_danh_muc_va_tai_lieu`<br>`test_can_cu_ban_nhap::test_mau_thuan_trang_thai_don_giua_hai_cong_cu`<br>`test_can_cu_ban_nhap::test_tai_lieu_cung_gia_thi_khong_mau_thuan` |
| 16.2 | "Xem căn cứ": tài liệu kèm trích đoạn, dữ liệu công cụ trả về, quy tắc và lớp lưới đã áp | Đạt | `test_trach_nhiem_giao_dien::test_xem_can_cu_tren_ban_nhap_va_chi_tiet_tung_tin`<br>`test_dau_vet_ai::test_tri_thuc_kem_trich_doan_cat_ngan_cho_nut_xem_can_cu` |
| 16.3 (bảng 16.8) | Không hiển thị độ tin cậy dạng % ở bất kỳ đâu (kể cả Phòng thử) | Đạt | `test_can_cu_ban_nhap::test_nhan_khong_co_phan_tram`<br>`test_trach_nhiem_giao_dien::test_khong_hien_ky_thuat_mac_dinh_va_khong_phan_tram_tin_cay`<br>`test_uy_quyen_ai::test_mo_ta_khong_co_phan_tram` |
| 16.4 | Không có căn cứ thì lưới tin cậy thấp chuyển người; tin chuyển người không bao giờ tự gửi | Đạt | `test_can_cu_ban_nhap::test_khong_tai_lieu_khong_du_lieu_thi_luoi_tin_cay_thap_chuyen_nguoi`<br>`test_can_cu_ban_nhap::test_tin_chuyen_nguoi_khong_bao_gio_tu_gui` |
| 16.5 | Phân loại hỏng không làm mất dấu vết, và nói là hỏng | Đạt | `test_can_cu_ban_nhap::test_dau_vet_mang_phan_loai_va_khong_lam_vo_dau_vet_khi_hong` |

Test canh nêu tên: **15**; các tệp test ấy (4 tệp) có tổng **53** hàm test.

**Nơi hiện thực**

- Mã: `agent/core/dau_vet_ai.py`, `agent/core/agent.py`, `dashboard/src/19-trach-nhiem.js`
- Giao diện: màn `hoithoai`

**Lệch so với bảng / ghi chú**

- "Mâu thuẫn" phát hiện theo LUẬT, ba loại: cùng công cụ cùng tham số trả hai giá trị khác nhau; trạng thái đơn ở sổ đơn khác tra vận chuyển; giá danh mục khác giá ghi trong tài liệu về chính sản phẩm ấy. Mâu thuẫn ngữ nghĩa giữa hai đoạn văn xuôi KHÔNG được phát hiện.

## Mục 17. Ba cấp ủy quyền hành động của AI

**Trạng thái: Đạt một phần**

Nghiệm thu trên app đầy đủ + Postgres thật: kịch bản 22 — Ba mức ủy quyền thực thi của AI: chế độ Gợi ý không tự làm, phê duyệt có kiểm lại (**đạt**).

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 17.1 | Chính sách theo từng hành động: Không sử dụng / Có phê duyệt / Tự động; mặc định đúng phiếu việc; ngưỡng tự chốt đơn là chính sách của "tạo đơn" | Đạt | `test_uy_quyen_ai::test_mac_dinh_dung_phieu_viec`<br>`test_uy_quyen_ai::test_tu_dong_theo_muc_va_nguong`<br>`test_uy_quyen_ai::test_moi_cong_cu_viet_san_deu_duoc_xep_loai`<br>`test_uy_quyen_ai::test_cong_cu_hanh_dong_tro_vao_hanh_dong_co_duong_thi_hanh` |
| 17.2 | Chốt ở cửa thi hành công cụ (backend), không ở prompt: hành động lạ = Không sử dụng; mức rác trong CSDL về mặc định, không về Tự động; plugin loại lạ bị chặn | Đạt | `test_uy_quyen_ai::test_hanh_dong_la_la_khong_su_dung`<br>`test_uy_quyen_ai::test_muc_rac_trong_csdl_ve_mac_dinh_khong_ve_tu_dong`<br>`test_uy_quyen_ai::test_plugin_loai_la_bi_chan`<br>`test_uy_quyen_ai::test_ba_tap_cong_cu_khong_giao_nhau` |
| 17.3 | Chế độ Gợi ý (và hội thoại "Duyệt trước khi gửi") biến mọi hành động ghi thành đề xuất — kể cả công cụ ghi MCP | Đạt | `test_uy_quyen_ai::test_goi_y_KHONG_ghi_don_chi_de_xuat`<br>`test_uy_quyen_ai::test_duyet_rieng_cua_hoi_thoai_tinh_nhu_goi_y`<br>`test_uy_quyen_ai::test_khong_doc_duoc_co_rieng_thi_xu_ly_nhu_goi_y`<br>`test_uy_quyen_ai::test_mcp_ghi_bi_chan_o_che_do_goi_y` |
| 17.4 | Thẻ phê duyệt trong hội thoại; duyệt chạy lại đúng hàm của người làm tay và KIỂM LẠI điều kiện (giá đổi thì từ chối); một đề xuất mở mỗi việc; hết hạn | Đạt | `test_uy_quyen_ai::test_thi_hanh_de_xuat_tu_choi_khi_gia_doi`<br>`test_uy_quyen_ai::test_mot_de_xuat_dang_mo_cho_moi_viec`<br>`test_uy_quyen_ai_csdl::test_huy_don_de_xuat_duyet_mot_lan_va_thi_hanh_kiem_lai`<br>`test_uy_quyen_ai_csdl::test_goi_y_khong_ghi_don_duyet_thi_len_don_kiem_lai`<br>`test_uy_quyen_ai_csdl::test_tu_choi_don_cho_duyet_tra_kho_va_het_han_khong_thi_hanh` |
| 17.5 | Người duyệt cần `ai.duyet` + quyền nghiệp vụ của hành động + phạm vi kênh; duyệt ở màn Đơn hàng đóng thẻ đề xuất | Đạt | `test_uy_quyen_ai_csdl::test_quyen_va_pham_vi_kenh_khi_duyet`<br>`test_uy_quyen_ai_csdl::test_duyet_o_man_don_hang_dong_the_de_xuat` |
| 17.6 | AI không có đường ghi chính sách; sửa chính sách cần `agent.dieu_khien`, kiểm hết trước khi ghi; đổi sang Không sử dụng thì đề xuất cũ không chạy | Đạt | `test_uy_quyen_ai::test_ai_khong_co_duong_ghi_chinh_sach`<br>`test_uy_quyen_ai::test_api_sua_chinh_sach_doi_agent_dieu_khien`<br>`test_uy_quyen_ai_csdl::test_api_chinh_sach_quyen_va_kiem_het_truoc_khi_ghi`<br>`test_uy_quyen_ai_csdl::test_chinh_sach_doi_sang_khong_su_dung_thi_de_xuat_cu_khong_chay` |
| 17.7 | "Chuyển nhân viên" luôn bật (bốn trong sáu lớp lưới kết thúc bằng chuyển người) | Đạt | `test_uy_quyen_ai::test_chuyen_nhan_vien_khong_tat_duoc` |
| 17.8 | Từ chối bản nháp AI: bản nháp thành huỷ, không gửi được nữa | Đạt | `test_uy_quyen_ai_csdl::test_tu_choi_ban_nhap_ai_khong_gui_duoc_nua` |
| 17.9 | Mọi hành động trong danh mục áp được ba mức *Hành động chưa có đường thi hành hiện "Chưa hỗ trợ — chuyển nhân viên", không đặt mức được — xem bảng bên dưới.* | Đạt một phần | `test_uy_quyen_ai::test_hanh_dong_chua_ho_tro_khong_bao_gio_tu_dong` |

Test canh nêu tên: **26**; các tệp test ấy (2 tệp) có tổng **39** hàm test.

**Danh mục hành động AI đọc từ `agent/core/uy_quyen.py`:** 9 hành động, 3 có đường thi hành; còn lại hiện "Chưa hỗ trợ — chuyển nhân viên".

| Hành động | Có đường thi hành | Mức mặc định | Đặt mức được |
|---|---|---|---|
| Tạo đơn hàng | có | Tự động | có |
| Huỷ đơn hàng | có | Có phê duyệt | có |
| Chuyển nhân viên theo quy tắc | có | Tự động | không |
| Sửa đơn đã xác nhận | không | Có phê duyệt | không |
| Hoàn tiền | không | Có phê duyệt | không |
| Giảm giá ngoài chính sách | không | Có phê duyệt | không |
| Đổi / trả hàng ngoài chính sách | không | Có phê duyệt | không |
| Tạo vận đơn | không | Tự động | không |
| Tạo công việc | không | Tự động | không |

**Nơi hiện thực**

- Mã: `agent/core/uy_quyen.py`, `agent/core/tools.py`, `agent/core/thao_tac_don.py`, `agent/api/uy_quyen_ai.py`, `agent/migrations/versions/0065_uy_quyen_ai.sql`, `dashboard/src/28-uy-quyen-ai.js`
- API (quyền đọc từ route thật):
    - `GET /api/ai-uy-quyen` — `cau_hinh.doc`
    - `PUT /api/ai-uy-quyen` — `agent.dieu_khien`
    - `GET /api/ai-de-xuat` — `hoi_thoai.doc`
    - `POST /api/ai-de-xuat/{de_xuat_id}/duyet` — `ai.duyet`
    - `POST /api/ai-de-xuat/{de_xuat_id}/tu-choi` — `ai.duyet`
    - `POST /api/messages/{message_id}/tu-choi` — `ai.duyet`
- Giao diện: tab `ai-chinh-sach`

**Lệch so với bảng / ghi chú**

- Huỷ đơn qua AI chỉ huỷ trong hệ thống và trả hàng về kho — KHÔNG huỷ bên ERP hay hãng vận chuyển; kết quả thi hành nói rõ phần cần huỷ tay.

**Câu hỏi mở — cần chủ dự án xác nhận**

- Thứ tự làm tiếp cho các hành động "Chưa hỗ trợ" (sửa đơn, hoàn tiền, giảm giá, đổi trả, tạo vận đơn, tạo công việc) — làm hành động nào trước?

## Mục 18. Trách nhiệm giải trình của AI

**Trạng thái: Đạt**

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 18.1 | Dấu vết từng tin AI: hồ sơ agent, chế độ, ngưỡng, lưới đã bắt, công cụ (tham số đã che), tri thức, model, chi phí; có trần dung lượng; không chứa dữ liệu cá nhân | Đạt | `test_dau_vet_ai::test_ghi_ho_so_nguong_luoi_va_tri_thuc`<br>`test_dau_vet_ai::test_ket_qua_khong_lo_van_vuot_tran_thi_rut_gon_ma_van_la_json`<br>`test_dau_vet_ai::test_che_so_dien_thoai_va_an_danh_tinh_ca_khi_tat_che_du_lieu`<br>`test_trach_nhiem_hoi_thoai::test_dau_vet_ai_ghi_vao_ban_nhap_va_khong_chua_du_lieu_ca_nhan`<br>`test_trach_nhiem_hoi_thoai::test_dau_vet_ai_ghi_vao_tin_tu_gui` |
| 18.2 | Mã lượt AI nối mọi dòng nhật ký của một lượt; lượt đóng ở mọi lối ra | Đạt | `test_nhat_ky_kiem_toan::test_gan_vao_chi_trong_luot_va_khong_de_khoa`<br>`test_nhat_ky_kiem_toan::test_pham_vi_luot_dong_luot_o_moi_loi_ra`<br>`test_nhat_ky_kiem_toan::test_handle_inbound_mo_luot_dung_cho`<br>`test_nhat_ky_kiem_toan::test_luot_ai_noi_moi_dong_va_tra_ca_luot` |
| 18.3 | Nhật ký chỉ thêm: CSDL chặn UPDATE/DELETE/TRUNCATE trên `events` | Đạt | `test_nhat_ky_kiem_toan::test_events_chi_them_va_loi_ra_chi_cho_delete`<br>`test_nhat_ky_kiem_toan::test_han_luu_tru_van_chay_khi_nhat_ky_chi_them` |
| 18.4 | Tra cứu lọc + phân trang con trỏ, chi tiết, theo lượt, theo hội thoại; xuất CSV (việc xuất cũng được ghi lại) | Đạt | `test_nhat_ky_kiem_toan::test_quyen_va_che_tren_app_that`<br>`test_nhat_ky_kiem_toan::test_mo_hinh_doc_chuan_hoa_tac_nhan_hoi_thoai_trang_thai` |
| 18.5 | Làm sạch lúc đọc: khoá bí mật, token theo hình dạng, giá trị bí mật đang cấu hình, SĐT/email, danh tính, suy luận model | Đạt | `test_nhat_ky_kiem_toan::test_lam_sach_che_bi_mat_danh_tinh_va_suy_luan`<br>`test_nhat_ky_kiem_toan::test_lam_sach_che_gia_tri_bi_mat_dang_cau_hinh`<br>`test_nhat_ky_kiem_toan::test_lam_sach_co_tran_va_khong_nem` |
| 18.6 | Sự cố, bước can thiệp, kết thúc, giải trình là DÒNG MỚI; dòng gốc không đổi | Đạt | `test_nhat_ky_kiem_toan::test_su_co_la_dong_moi_dong_goc_khong_doi`<br>`test_nhat_ky_kiem_toan::test_ghi_can_quyen_su_co_doc_can_nhat_ky_hoac_hoi_thoai` |
| 18.7 | Lịch sử đề xuất / phê duyệt cùng một hình dạng | Đạt | `test_nhat_ky_kiem_toan::test_de_xuat_co_hinh_dang_on_dinh`<br>`test_nhat_ky_kiem_toan::test_de_xuat_gom_ca_hanh_dong_ai_cung_hinh_dang` |
| 18.8 | Giao diện: tab Nhật ký ở Hệ thống & Nhật ký; "Nhật ký hội thoại" trong panel Chi tiết hội thoại; người sửa/duyệt ghi tên | Đạt | `test_nhat_ky_kiem_toan::test_dashboard_gan_tab_nhat_ky_va_nhat_ky_hoi_thoai`<br>`test_trach_nhiem_hoi_thoai::test_chi_tiet_hoi_thoai_noi_ten_nguoi_gui_nguoi_sua_nguoi_duyet` |

Test canh nêu tên: **22**; các tệp test ấy (3 tệp) có tổng **32** hàm test.

**Nơi hiện thực**

- Mã: `agent/core/nhat_ky_kiem_toan.py`, `agent/core/luot_ai.py`, `agent/core/dau_vet_ai.py`, `agent/api/nhat_ky_api.py`, `agent/migrations/versions/0053_dau_vet_ai_tung_tin.sql`, `agent/migrations/versions/0064_nhat_ky_chi_them.sql`, `dashboard/src/27-nhat-ky.js`
- API (quyền đọc từ route thật):
    - `GET /api/nhat-ky` — `nhat_ky.doc`
    - `GET /api/nhat-ky/xuat.csv` — `nhat_ky.doc`
    - `GET /api/nhat-ky/luot/{luot_id}` — `nhat_ky.doc`
    - `GET /api/nhat-ky/hoi-thoai/{cid}` — `hoi_thoai.doc`
    - `GET /api/nhat-ky/de-xuat` — `nhat_ky.doc`
    - `POST /api/nhat-ky/{event_id}/su-co` — `nhat_ky.su_co`
    - `POST /api/nhat-ky/{event_id}/giai-trinh` — `nhat_ky.su_co`
- Giao diện: tab `ht-nhat-ky`

**Câu hỏi mở — cần chủ dự án xác nhận**

- Bảng `events` hiện không có đường xoá nào (hạn lưu trữ và PDPD không đụng bảng này), nên nhật ký lớn dần mãi. Có cần hạn lưu cho nhật ký kiểm toán không, và bao lâu?

## Mục 19. Thông báo nội bộ (chuông)

**Trạng thái: Đạt**

Nghiệm thu trên app đầy đủ + Postgres thật: kịch bản 7 — Phân task, quản lý task và thông báo nội bộ (**đạt**); kịch bản 21 — Hệ thống giao việc: phân công theo ca trực, chuyển việc, tiến độ, kết quả, lịch sử, chuông (**đạt**).

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 19.1 | Chuông + số chưa đọc ở thanh trên; danh sách phân trang; bấm đi tới hội thoại / việc / đơn; đọc / đọc hết | Đạt | `test_thong_bao_noi_bo::test_chuong_nam_o_thanh_tren_khong_co_muc_dieu_huong`<br>`test_thong_bao_noi_bo::test_phan_trang`<br>`test_he_thong_giao_viec::test_chuong_cong_viec_mo_chi_tiet_viec` |
| 19.2 | Nguồn sự kiện: AI chuyển giao, giao hội thoại (tay và định tuyến tự động), bản nháp chờ duyệt, đơn chờ duyệt, giao việc, SLA sắp trễ / đã trễ, việc | Đạt | `test_thong_bao_noi_bo::test_loai_trong_ma_khop_check_cua_migration`<br>`test_thong_bao_noi_bo::test_giao_hoi_thoai_cho_nguoi_khac_thi_bao`<br>`test_thong_bao_noi_bo::test_dinh_tuyen_tu_dong_giao_xong_thi_bao`<br>`test_thong_bao_noi_bo::test_ban_nhap_cho_duyet_thi_bao`<br>`test_thong_bao_noi_bo::test_giao_viec_cho_nguoi_khac_thi_bao_tu_giao_thi_khong` |
| 19.3 | Luật người nhận: người được giao → thành viên kênh có quyền → người quản lý; SLA báo thêm quản lý | Đạt | `test_thong_bao_noi_bo::test_nguoi_nhan_thanh_vien_kenh_co_quyen_khong_phai_nguoi_ngoai`<br>`test_thong_bao_noi_bo::test_kenh_khong_ai_phu_trach_thi_bao_nguoi_quan_ly`<br>`test_thong_bao_noi_bo::test_hoi_thoai_da_giao_thi_chi_bao_nguoi_dang_cam_sla_bao_them_quan_ly` |
| 19.4 | Chống dội: khách nhắn thêm không đổ chuông lại; một thông báo chờ duyệt mỗi hội thoại | Đạt | `test_thong_bao_noi_bo::test_khach_nhan_them_khong_doi_chuong_va_khong_doi_tin_bao`<br>`test_thong_bao_noi_bo::test_che_do_goi_y_ban_nhap_cho_duyet_thi_bao_mot_lan_moi_hoi_thoai` |
| 19.5 | API chỉ trả thông báo của chính người đăng nhập; đánh dấu đã đọc không làm xong việc gì | Đạt | `test_thong_bao_noi_bo::test_api_chi_thay_cua_minh_doc_khong_lam_xong_viec_gi`<br>`test_thong_bao_noi_bo::test_api_doi_dang_nhap`<br>`test_thong_bao_noi_bo::test_moi_duong_thong_bao_duoc_khai_mien_tru_tung_cai` |
| 19.6 | Sinh thông báo hỏng không bao giờ làm hỏng lượt trả lời khách, nhưng ghi lỗi | Đạt | `test_thong_bao_noi_bo::test_hong_CSDL_khong_nem_vao_luot_tra_loi_nhung_ghi_loi_va_van_bao_ngoai` |

Test canh nêu tên: **17**; các tệp test ấy (2 tệp) có tổng **49** hàm test.

**Loại thông báo đọc từ `agent/core/thong_bao_noi_bo.py`** (9): Được giao hội thoại, AI chuyển giao, Cần duyệt, Được giao việc, SLA sắp trễ, SLA đã trễ, Việc chưa phân công, Việc bị hủy, Việc quá hạn.

**Nơi hiện thực**

- Mã: `agent/core/thong_bao_noi_bo.py`, `agent/api/thong_bao_noi_bo.py`, `agent/migrations/versions/0055_thong_bao_noi_bo.sql`, `dashboard/src/19-thong-bao.js`
- API (quyền đọc từ route thật):
    - `GET /api/toi/thong-bao` — miễn trừ (đăng nhập hoặc chữ ký riêng)
    - `GET /api/toi/thong-bao/so-chua-doc` — miễn trừ (đăng nhập hoặc chữ ký riêng)
    - `POST /api/toi/thong-bao/da-doc-het` — miễn trừ (đăng nhập hoặc chữ ký riêng)
    - `POST /api/toi/thong-bao/{thong_bao_id}/da-doc` — miễn trừ (đăng nhập hoặc chữ ký riêng)

**Lệch so với bảng / ghi chú**

- Thông báo nội bộ chỉ hiện trong ứng dụng (chuông). Báo động vận hành (hệ thống hỏng, khách chờ) là kênh khác — đi qua webhook của người canh gác.

**Câu hỏi mở — cần chủ dự án xác nhận**

- Có cần đẩy thông báo nội bộ ra ngoài ứng dụng (email, Zalo, thông báo trình duyệt) cho người không mở dashboard không?

## Mục 20. Kênh theo kiến trúc plugin

**Trạng thái: Đạt**

Nghiệm thu trên app đầy đủ + Postgres thật: kịch bản 4 — Kênh thêm bằng cấu hình; agent là tuỳ chọn (**đạt**).

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 20.1 | Hợp đồng adapter chung (`ChannelAdapter`); bộ quét ra đúng các adapter; móc chưa cài đặt phải khai báo | Đạt | `test_hop_dong_kenh::test_quet_ra_dung_cac_adapter_da_biet`<br>`test_hop_dong_kenh::test_moc_chua_cai_dat_phai_duoc_khai_bao`<br>`test_hop_dong_kenh::test_moc_tuy_chon_khop_voi_base` |
| 20.2 | Mỗi plugin khai khả năng; khoá lạ nổ ngay lúc import; không khai biên nhận khi chưa có mã đọc biên nhận | Đạt | `test_kha_nang_kenh::test_moi_adapter_khai_du_moi_kha_nang`<br>`test_kha_nang_kenh::test_khoa_kha_nang_la_thi_no_ngay`<br>`test_kha_nang_kenh::test_khong_khai_bien_nhan_khi_chua_co_ma_doc_bien_nhan`<br>`test_kha_nang_kenh::test_chi_kenh_co_ham_an_binh_luan_moi_khai_an_binh_luan` |
| 20.3 | Danh sách plugin + khả năng + tài khoản + webhook ở Kết nối & Tích hợp | Đạt | `test_kha_nang_kenh::test_moi_kenh_co_mo_ta_tren_man_ket_noi`<br>`test_ket_noi_tich_hop_pg::test_tuy_chon_an_binh_luan_theo_trang_va_danh_sach_plugin` |
| 20.4 | Nhiều tài khoản mỗi nền tảng; kênh thêm bằng cấu hình; bật/tắt agent theo kênh | Đạt | `test_nghiem_thu_saas::test_04_noi_kenh_va_tat_agent_theo_kenh`<br>`test_xoa_tai_khoan_kenh::test_co_duong_xem_truoc_rieng` |
| 20.5 | Nạp mã plugin kênh từ bên ngoài lúc chạy *Không làm, có chủ ý: mã tuỳ ý chạy trong tiến trình agent nằm cùng phía với sáu lớp lưới. Plugin KỸ NĂNG là dữ liệu chỉ đọc (docs/ky-nang.md).* | Ngoài phạm vi theo bảng | — |

Test canh nêu tên: **11**; các tệp test ấy (5 tệp) có tổng **48** hàm test.

**Khả năng từng plugin kênh, đọc từ `KHA_NANG_KENH` của adapter** (9 plugin, 10 khả năng):

| Plugin | Nhận và gửi văn bản | Nhận ảnh khách gửi | Nhận tệp khác (video, tài liệu…) | Gửi ảnh cho khách | Gửi tệp không phải ảnh | Trạng thái Đã gửi (nền tảng đã nhận tin) | Biên nhận đã tới máy khách | Biên nhận khách đã xem | Hiện “đang gõ…” | Ẩn bình luận công khai |
|---|---|---|---|---|---|---|---|---|---|---|
| Facebook Messenger | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ | ✓ |
| Zalo OA | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — | — | — |
| Instagram | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — | — | — |
| WhatsApp | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| Zalo cá nhân | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | — |
| Chat trên website | ✓ | — | — | — | — | ✓ | — | — | — | — |
| ZaloCRM (kênh cũ) | ✓ | — | — | — | — | ✓ | — | — | — | — |
| Chatwoot (kênh cũ) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | — |
| Messenger (kênh cũ, token trong .env) | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ | ✓ |

**Nơi hiện thực**

- Mã: `agent/channels/base.py`, `agent/channels/factory.py`, `agent/channels/registry.py`, `agent/api/ket_noi_tich_hop.py`, `agent/api/channel_accounts.py`, `dashboard/src/22-ket-noi-tich-hop.js`
- API (quyền đọc từ route thật):
    - `GET /api/ket-noi` — `cau_hinh.sua`
- Giao diện: tab `cc-ket-noi`

**Lệch so với bảng / ghi chú**

- Thêm một NỀN TẢNG mới vẫn cần viết một lớp adapter Python trong `agent/channels/` và đăng ký vào `factory`; thêm TÀI KHOẢN mới cho nền tảng đã có thì chỉ cần cấu hình.
- Telegram trong repo là kênh BÁO ĐỘNG cho người vận hành (`scripts/noi_telegram.py`), không phải kênh chăm sóc khách.

**Câu hỏi mở — cần chủ dự án xác nhận**

- Mức "plugin" hiện nay (hợp đồng + đăng ký + khai khả năng, thêm nền tảng cần mã) có đúng ý bảng không?

## Mục 21. Bảng yêu cầu chức năng và phi chức năng

**Trạng thái: Đạt**

| # | Yêu cầu | Trạng thái | Test canh |
|---|---|---|---|
| 21.1 | Bảng sinh từ mã và kết quả kiểm thử; mọi tham chiếu kiểm mỗi lần sinh; test canh bảng cũ | Đạt | `test_bang_yeu_cau::test_tai_lieu_khop_ban_sinh`<br>`test_bang_yeu_cau::test_moi_tham_chieu_ton_tai`<br>`test_bang_yeu_cau::test_bo_kiem_bat_duoc_tham_chieu_chet` |
| 21.2 | Trạng thái mục suy từ yêu cầu con; nghiệm thu không đạt thì mục không thể "Đạt" | Đạt | `test_bang_yeu_cau::test_trang_thai_muc_suy_tu_yeu_cau_con`<br>`test_bang_yeu_cau::test_nghiem_thu_khong_dat_thi_muc_khong_dat` |
| 21.3 | Phần phi chức năng và hạn chế đã biết | Đạt | `test_bang_yeu_cau::test_moi_tham_chieu_ton_tai` |

Test canh nêu tên: **6**; các tệp test ấy (1 tệp) có tổng **9** hàm test.

**Nơi hiện thực**

- Mã: `scripts/sinh_bang_yeu_cau.py`, `tests/test_bang_yeu_cau.py`, `docs/nang-cap/ke-hoach-check-list.md`

---

# Phần B — Yêu cầu phi chức năng

Số liệu đếm từ mã lúc sinh:

- Route `/api` và `/tich-hop` trên app thật: **298** — **282** khai quyền bằng `can_quyen`, **16** nằm trong `MIEN_TRU` có lý do; còn lại **0** (phải bằng 0, nếu không máy chủ không khởi động).
- Outbox thử tối đa **8** lần (mặc định cột `max_attempts`, migration 0002) rồi vào dead-letter và kêu người.
- Migration SQL đã chốt checksum: **65** tệp.
- Hạn lưu hội thoại mặc định: **180 ngày**; media khách gửi: **180 ngày**.

## Bảo mật

| Yêu cầu | Cách đáp ứng | Trạng thái | Bằng chứng |
|---|---|---|---|
| Phân quyền hỏng-đóng | Chốt lúc khởi động duyệt ĐỆ QUY mọi route; route `/api` thiếu `can_quyen` và không ở `MIEN_TRU` thì máy chủ không lên | Đạt | `test_quyen_danh_muc::test_moi_route_deu_da_khai_quyen`<br>`test_quyen_danh_muc::test_duyet_route_phai_di_de_quy`<br>`test_quyen_danh_muc::test_khong_con_duong_lui_bo_qua_tam`<br>`agent/core/quyen.py` |
| Chống leo thang quyền | Không cấp được quyền mình không có; không động tới vai trò/người mạnh hơn mình | Đạt | `test_chan_leo_thang_quyen::test_khong_tu_gan_quan_tri_cho_minh`<br>`test_chan_leo_thang_quyen::test_khong_ha_cap_hay_khoa_cap_tren`<br>`agent/api/quyen.py` |
| Xác thực | Mật khẩu + xác thực hai bước; chặn dò theo IP kể cả khi đổi tên; cookie tự bật Secure khi HTTPS | Đạt | `test_hai_buoc::test_do_doi_ten_moi_luot_van_bi_chan_theo_ip`<br>`test_bao_mat_giai_doan_0::test_cookie_tu_bat_secure_khi_https`<br>`test_bao_mat_giai_doan_0::test_token_mcp_so_hang_thoi_gian`<br>`agent/core/xac_thuc.py`<br>`agent/core/hai_buoc.py` |
| Che bí mật | Bộ lọc nhật ký che tham số/URL/header bí mật; `httpx` không ghi URL ở mức INFO; API Kết nối không trả giá trị khoá; khoá kênh mã hoá trong vault; metadata từ chối khoá trông như bí mật | Đạt | `test_nhat_ky_che_bi_mat::test_che_moi_tham_so_bi_mat`<br>`test_nhat_ky_che_bi_mat::test_httpx_khong_con_ghi_o_muc_INFO`<br>`test_ket_noi_tich_hop::test_tong_quan_khong_lo_bi_mat`<br>`test_metadata_khong_chua_bi_mat::test_tu_choi_khoa_nghe_giong_bi_mat`<br>`test_san_sang::test_co_credential_ma_thieu_master_key_thi_chan`<br>`agent/nhat_ky.py`<br>`agent/security/credential_vault.py` |
| Webhook không cho qua khi chưa cấu hình bí mật | Thiếu secret là từ chối; so sánh không thoát sớm | Đạt | `test_webhook_khong_cho_qua_khi_chua_cau_hinh::test_khong_co_bi_mat_thi_tu_choi`<br>`test_webhook_khong_cho_qua_khi_chua_cau_hinh::test_so_sanh_khong_thoat_som` |
| Nhật ký kiểm toán chỉ thêm | Trigger CSDL chặn UPDATE/DELETE/TRUNCATE trên `events` | Đạt | `test_nhat_ky_kiem_toan::test_events_chi_them_va_loi_ra_chi_cho_delete`<br>`agent/migrations/versions/0064_nhat_ky_chi_them.sql` |
| Chống SSRF | Tải media và plugin `goi_api_doc` chặn địa chỉ nội bộ, kể cả tên miền phân giải về nội bộ và sau chuyển hướng | Đạt | `test_media_khach_gui::test_chan_dia_chi_noi_bo`<br>`test_media_khach_gui::test_ten_may_phan_giai_ra_dia_chi_noi_bo_cung_bi_chan`<br>`test_media_khach_gui::test_chuyen_huong_vao_noi_bo_bi_chan`<br>`test_ky_nang_plugin::test_dia_chi_noi_bo_bi_chan`<br>`test_ky_nang_plugin::test_khong_di_theo_redirect` |
| Che dữ liệu cá nhân trước khi gửi model | SĐT, email... thay bằng mã trước khi tới nhà cung cấp model, mặc định bật | Đạt | `test_che_du_lieu::test_che`<br>`test_che_du_lieu::test_mac_dinh_bat`<br>`test_che_du_lieu::test_chi_agent_gui_chu_khach_sang_model`<br>`agent/core/che_du_lieu.py` |

## Độ tin cậy

| Yêu cầu | Cách đáp ứng | Trạng thái | Bằng chứng |
|---|---|---|---|
| Hàng đợi gửi (outbox) có thử lại và dead-letter | Giãn cách lũy tiến có trần; đủ lượt thì `dead` và KÊU người (không im lặng); claim bằng SKIP LOCKED, nhặt lại job treo | Đạt | `test_outbox::test_retry_backoff_co_gioi_han_va_den_max_thi_dead`<br>`test_outbox::test_postgres_claim_dung_skip_locked_va_nhat_lai_stale_job`<br>`test_tin_chet_phai_keu::test_tin_chet_bat_ra_canh_bao_NGHIEM_TRONG`<br>`test_tin_chet_phai_keu::test_canh_bao_hong_KHONG_lam_chet_worker`<br>`agent/omnichannel/outbox.py`<br>`agent/workers/outbox_worker.py` |
| Worker và nhịp tim | Worker ghi heartbeat; `san_sang` chặn khi có hàng chờ mà worker không đập; tách vai api / worker | Đạt | `test_outbox::test_postgres_worker_heartbeat_upsert_theo_ten_worker`<br>`test_san_sang::test_outbox_co_queue_ma_worker_khong_heartbeat_thi_chan`<br>`test_tach_worker::test_vai_worker_chay_vong_nen` |
| Canh gác | Canh gác trong app báo khi trạng thái ĐỔI (không báo mỗi lần kiểm); người canh ngoài (task Windows 5 phút) tự dựng lại app/sidecar, tối đa ba lần mỗi giờ | Đạt | `test_canh_gac::test_bao_khi_doi_trang_thai_khong_bao_moi_lan_kiem`<br>`test_canh_gac::test_vong_canh_gac_khong_bao_gio_chet`<br>`test_canh_gac_ngoai::test_hong_lan_hai_lien_tiep_thi_dung_lai`<br>`test_canh_gac_ngoai::test_toi_da_ba_lan_moi_gio_roi_bo_cuoc`<br>`agent/canh_gac.py`<br>`scripts/canh_gac_ngoai.py` |
| Sao lưu | Mã hoá khi có mật khẩu; không chép bản chưa mã hoá ra ngoài máy; thử phục hồi thật; gồm tệp (sản phẩm, uploads, media) | Đạt | `test_sao_luu_ma_hoa::test_co_mat_khau_thi_khong_con_ban_thuong`<br>`test_sao_luu_ma_hoa::test_chep_ra_ngoai_chi_ban_ma_hoa`<br>`test_sao_luu_ma_hoa::test_khong_mat_khau_thi_noi_ro_la_chua_ma_hoa`<br>`test_sao_luu_thu_phuc_hoi::test_thieu_bang_so_voi_csdl_that_thi_hong`<br>`test_sao_luu_tep::test_goi_ca_products_va_uploads`<br>`scripts/sao_luu.py` |
| Lỗi phụ không làm chết luồng tin | Quy tắc tự động, chuông thông báo hỏng thì ghi lỗi, không ném vào lượt trả lời | Đạt | `test_tu_dong::test_csdl_hong_khong_nem`<br>`test_tu_dong::test_mot_quy_tac_hong_khong_chan_quy_tac_sau`<br>`test_thong_bao_noi_bo::test_hong_CSDL_khong_nem_vao_luot_tra_loi_nhung_ghi_loi_va_van_bao_ngoai` |

## Hiệu năng

| Yêu cầu | Cách đáp ứng | Trạng thái | Bằng chứng |
|---|---|---|---|
| Hàng đợi và tải tệp không nghẽn | Outbox claim SKIP LOCKED (nhiều worker không giành nhau); media đọc theo luồng có trần, không đọc trọn tệp vào RAM; sao lưu ghi theo luồng ra đĩa | Đạt | `test_outbox::test_postgres_claim_dung_skip_locked_va_nhat_lai_stale_job`<br>`test_media_khach_gui::test_vuot_tran_thi_dung_doc_ngay_khong_doc_tron` |
| Đo hiệu năng | Nhật ký kiểm toán có chỉ mục theo hội thoại/lượt và phân trang con trỏ. CHƯA có phép đo tải sinh tự động; số đo thời gian truy vấn trong báo cáo mục 18 không tái lập được bằng script nên không chép vào đây. Độ trễ và chi phí model: `docs/thuc-nghiem.md` (sinh từ eval) | Đạt một phần | `test_nhat_ky_kiem_toan::test_quyen_va_che_tren_app_that`<br>`agent/migrations/versions/0064_nhat_ky_chi_them.sql`<br>`docs/thuc-nghiem.md` |

## Quyền riêng tư (Luật BVDLCN 91/2025)

| Yêu cầu | Cách đáp ứng | Trạng thái | Bằng chứng |
|---|---|---|---|
| Hạn lưu dữ liệu | Hội thoại quá hạn tự dọn (đơn hàng không bị đụng — chứng từ kế toán); dọn có chạy thử và phê duyệt | Đạt | `test_du_lieu_ca_nhan::test_don_theo_han_khong_dung_toi_don_hang`<br>`test_retention_api::test_retention_can_admin_approve_va_dry_run_co_audit_actor`<br>`agent/core/du_lieu_ca_nhan.py`<br>`agent/api/retention.py` |
| Xoá theo từng khách | Cần người thứ hai duyệt (phiếu); đơn hàng ẩn danh chứ không xoá; nhật ký chỉ ghi dấu vân tay SĐT | Đạt | `test_pdpd_bon_mat::test_khong_co_phieu_thi_nem_va_khong_xoa_gi`<br>`test_pdpd_bon_mat::test_gianh_phieu_la_mot_cau_lenh_nguyen_tu`<br>`test_du_lieu_ca_nhan::test_don_hang_duoc_an_danh_chu_khong_xoa`<br>`test_du_lieu_ca_nhan::test_nhat_ky_chi_ghi_dau_van_tay_khong_ghi_so_that`<br>`agent/api/pdpd_api.py` |
| Truy cập / xuất dữ liệu của khách | Tra cứu toàn bộ dữ liệu theo SĐT (kể cả hồ sơ CRM, nhãn) để trả lời yêu cầu truy cập. Chưa có tệp xuất máy-đọc-được riêng cho chủ thể dữ liệu | Đạt một phần | `test_pdpd_bon_mat::test_tra_cuu_noi_ca_ho_so_crm`<br>`test_nhan_dong::test_pdpd_tra_cuu_ke_ten_nhan_va_xoa_lien_ket` |
| Sổ yêu cầu của chủ thể dữ liệu | Hạn xử lý theo NĐ 356/2025 Điều 5, tính theo giờ Việt Nam; quá hạn thì `san_sang` chặn; hồ sơ BVDLCN sinh từ cấu hình thật | Đạt | `test_yeu_cau_chu_the::test_han_xu_ly_theo_nd_356_dieu_5`<br>`test_yeu_cau_chu_the::test_san_sang_qua_han_la_chan`<br>`test_yeu_cau_chu_the::test_ho_so_doc_cau_hinh_that`<br>`agent/core/yeu_cau_chu_the.py`<br>`scripts/sinh_ho_so_bvdlcn.py` |

## Bảo trì

| Yêu cầu | Cách đáp ứng | Trạng thái | Bằng chứng |
|---|---|---|---|
| Tài liệu sinh ra, có test canh cũ | Sơ đồ kiến trúc, thực nghiệm, kỹ năng, nghiệm thu, bảng này — sửa tay là lần sau bị ghi đè | Đạt | `test_so_do::test_file_tai_lieu_da_duoc_sinh_lai`<br>`test_thuc_nghiem::test_file_tai_lieu_da_duoc_sinh_lai`<br>`test_ky_nang::test_tai_lieu_ky_nang_khong_cu`<br>`test_bang_nghiem_thu::test_moi_kich_ban_deu_co_trong_bang`<br>`test_bang_yeu_cau::test_tai_lieu_khop_ban_sinh` |
| Migration chốt checksum | Sửa migration đã áp thì app không lên; CRLF/LF cho cùng checksum (`.gitattributes`) | Đạt | `test_migrations::test_apply_migrations_chan_file_da_bi_sua`<br>`test_migration_xuong_dong::test_crlf_va_lf_cho_cung_checksum`<br>`test_migration_xuong_dong::test_co_gitattributes_ep_sql_giu_LF`<br>`agent/migrations/runner.py` |
| Dashboard đóng gói từ nguồn | `dashboard/app.js` sinh từ `dashboard/src/*.js`; lệch là đỏ | Đạt | `test_dong_goi_dashboard::test_app_js_khop_voi_src`<br>`scripts/dong_goi_dashboard.py` |
| Kiểm tĩnh và CI | `ruff` (chỉ bắt lỗi) và `mypy` cho `agent/` phải sạch; CI chạy toàn bộ test | Đạt | `test_claude_md::test_co_muc_kiem_truoc_khi_bao_xong`<br>`.github/workflows/kiem-thu.yml`<br>`pyproject.toml` |

## Vận hành

| Yêu cầu | Cách đáp ứng | Trạng thái | Bằng chứng |
|---|---|---|---|
| Một lệnh kiểm sẵn sàng | `scripts.san_sang` kiểm từng tầng, chỉ in tên khoá không in giá trị | Đạt | `test_san_sang::test_chi_in_ten_khoa_khong_in_gia_tri`<br>`test_san_sang::test_dich_vu_tat_thi_khong_ket_luan_an_toan`<br>`scripts/san_sang.py` |
| Một lệnh dựng cả hệ thống | `scripts.khoi_dong` dựng năm tiến trình, mã thoát khác 0 khi còn tầng hỏng; chạy được không tunnel | Đạt | `test_khoi_dong::test_con_gi_hong_thi_ma_thoat_KHAC_khong`<br>`test_khoi_dong::test_co_duong_chay_khong_tunnel`<br>`scripts/khoi_dong.py` |
| Chuyển nhà lên VPS | Đóng gói cửa hàng (mã hoá) và dựng lại trên VPS; đã diễn tập | Đạt | `test_sao_luu_silo::test_huong_dan_vps_noi_cat_khoa_ngoai_may`<br>`scripts/chuyen_nha.py`<br>`docs/len-vps.md` |

## Bản địa hoá

| Yêu cầu | Cách đáp ứng | Trạng thái | Bằng chứng |
|---|---|---|---|
| Tiếng Việt | Giao diện, thông báo lỗi, nhãn quyền, tên plugin, tài liệu tiếng Việt; hạn pháp lý tính theo giờ Việt Nam | Đạt | `test_quyen_danh_muc::test_moi_quyen_co_nhan_tieng_viet`<br>`test_dashboard_plugin_tieng_viet::test_danh_sach_plugin_hien_ten_loai_tieng_viet`<br>`test_yeu_cau_chu_the::test_phan_hoi_tinh_theo_GIO_VIET_NAM_khong_theo_UTC` |

## Số test theo vùng

Toàn repo: **400+** tệp test, **4100+** hàm test (đếm `def test_` bằng `ast`, làm tròn xuống để bảng không cũ mỗi lần thêm một test ở chỗ không liên quan; một hàm `parametrize` sinh nhiều ca, nên số ca pytest chạy lớn hơn).

| Mục | Tệp test canh | Hàm test trong các tệp ấy |
|---|---|---|
| 1. Nút "← Quay lại" ở màn hai lớp (xác thực hai bước) | 2 | 33 |
| 2. Dòng "Thời gian · Người gửi · Trạng thái" dưới mỗi tin | 5 | 50 |
| 3. Nhãn động cho khách hàng và hội thoại, danh mục chung | 1 | 22 |
| 4. Tái cấu trúc menu: 6 menu chính + "Cài đặt & Quản trị", chuông thông báo | 4 | 89 |
| 5. Cấu hình AI Agent: 5 tab, bật/tắt AI, chế độ chung mọi kênh | 6 | 86 |
| 6. Thanh thông tin hội thoại gọn; ghi chú nội bộ trong ô soạn tin | 2 | 24 |
| 7. Mẫu trả lời và quy tắc tự động: ưu tiên, xung đột, chống trùng với AI | 4 | 52 |
| 8. Kết nối & Tích hợp: kênh, ERPNext, GHN, GHTK, webhook, nhà cung cấp AI, thông báo minh bạch AI | 5 | 91 |
| 9. Phân biệt hội thoại nhóm và cá nhân | 4 | 59 |
| 10. Media khách gửi | 1 | 39 |
| 12. Phân quyền RBAC theo chức năng | 4 | 54 |
| 13. Vai trò động và quản lý nhân viên | 3 | 55 |
| 14. Phân công công việc | 3 | 60 |
| 15. SLA | 3 | 59 |
| 16. Gợi ý có căn cứ và "Xem căn cứ" | 4 | 53 |
| 17. Ba cấp ủy quyền hành động của AI | 2 | 39 |
| 18. Trách nhiệm giải trình của AI | 3 | 32 |
| 19. Thông báo nội bộ (chuông) | 2 | 49 |
| 20. Kênh theo kiến trúc plugin | 5 | 48 |
| 21. Bảng yêu cầu chức năng và phi chức năng | 1 | 9 |
| Phi chức năng (Phần B) | 40 | 595 |

## Tài liệu sinh ra và test canh tài liệu cũ

| Tài liệu | Lệnh sinh lại |
|---|---|
| `docs/kien-truc.md` | `python -m scripts.sinh_so_do --ghi` |
| `docs/thuc-nghiem.md` | `python -m scripts.sinh_thuc_nghiem --ghi` |
| `docs/ky-nang.md` | `python -m scripts.sinh_ky_nang --ghi` |
| `docs/nghiem-thu.md` | `python -m scripts.sinh_nghiem_thu --ghi` |
| `docs/yeu-cau-chuc-nang.md` | `python -m scripts.sinh_bang_yeu_cau --ghi` |

---

# Phần C — Hạn chế đã biết

1. **Chạy trên máy cá nhân.** Tắt máy là cả hệ thống tắt — không lệnh nào cứu được lúc đó. Sau khi đăng nhập lại, người canh ngoài tự dựng lại app và sidecar trong vòng một chu kỳ canh, TRỪ tunnel. Bằng chứng: `scripts/canh_gac_ngoai.py`, `scripts/khoi_dong.py`.

2. **Tunnel tạm.** Tên miền tunnel đổi mỗi lần chạy; phải dán lại URL webhook. Không tunnel thì Zalo OA và Facebook mất chiều NHẬN (máy chủ của họ cần địa chỉ công khai); Zalo cá nhân không bị ảnh hưởng. Bằng chứng: `scripts/chay_tunnel.py`.

3. **Token Facebook / Meta hết hạn.** Token Trang hết hạn hoặc bị thu hồi thì kênh ngừng; canh gác báo, phải nối lại. Bằng chứng: `agent/channels/suc_khoe_token_meta.py`, `scripts/noi_lai_facebook.py`.

4. **Zalo cá nhân.** Đi qua sidecar không chính thức, chạy ngoài Docker; phiên hết hạn phải quét QR lại; sidecar tắt là tin nhân viên chết sau khi outbox thử hết lượt. Bằng chứng: `connectors/zalo-personal-sidecar`, `scripts/chay_sidecar_zalo.py`.

5. **Meta App Review.** Chưa qua duyệt ứng dụng của Meta thì chỉ Trang của người có vai trò trong app nối được. Bằng chứng: `docs/trien-khai-saas.md`.

6. **Mật khẩu sao lưu.** Chưa đặt `SAO_LUU_MAT_KHAU` thì bản sao lưu CSDL KHÔNG mã hoá và không được chép ra ngoài máy; `scripts.san_sang` báo mục này. Bảng này không đọc `.env` nên không khẳng định trạng thái trên máy đang chạy — chạy `san_sang` để biết. Bằng chứng: `scripts/sao_luu.py`, `scripts/san_sang.py`.

7. **Biên nhận Đã nhận / Đã đọc.** Chưa kênh nào đọc biên nhận từ webhook (mục 2.5, mục 20); bộ sinh đếm lại từ `KHA_NANG_KENH` mỗi lần. Bằng chứng: `agent/channels/base.py`.

8. **AI không chạy trong hội thoại nhóm.** Theo bảng, đây là hướng sau (mục 9.8).

9. **Nhật ký kiểm toán không có hạn lưu.** Bảng `events` chỉ thêm và chưa có đường xoá; dung lượng tăng dần (mục 18). Bằng chứng: `agent/migrations/versions/0064_nhat_ky_chi_them.sql`.

10. **Chưa có phép đo hiệu năng tái lập được.** Xem Phần B, nhóm Hiệu năng.
