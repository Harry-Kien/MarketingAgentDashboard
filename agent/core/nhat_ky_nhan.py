"""
Tên tiếng Việt và MỨC QUAN TRỌNG của từng loại sự kiện trong `events`.

Tách khỏi `nhat_ky_kiem_toan.py` vì đây là DỮ LIỆU (một bảng tra ~300
dòng), không phải luật đọc — để chung là tệp mô hình đọc vượt nghìn dòng
và một lần thêm nhãn trông như một lần sửa logic.

VÌ SAO MỖI KIND PHẢI CÓ NHÃN (UX-18-01)
--------------------------------------
Màn Nhật ký từng hiện thẳng mã `erp.ngat_mach`, `zalo_personal.tin_bo_qua`
cho người vận hành. Mã là thứ lập trình viên grep, không phải thứ chủ cửa
hàng đọc. `tests/test_nhat_ky_nhan_su_kien.py` quét MỌI nơi ghi `events`
trong `agent/`, `scripts/` và migration, rồi đỏ khi có kind chưa nằm ở
đây — thêm một `log_event("x.y")` mới mà quên nhãn là CI báo ngay, thay
vì người dùng thấy mã thô vài tháng sau.

Kind KHÔNG có trong bảng (dòng cũ của tính năng đã gỡ, hay dòng test) vẫn
không hiện mã thô: `nhan()` lui về nhãn theo TIỀN TỐ. Mã gốc chỉ nằm ở phần
chi tiết kỹ thuật.

BA MỨC QUAN TRỌNG (UX-18-02)
---------------------------
  nghiep_vu  — việc có nghĩa với cửa hàng: AI/nhân viên làm gì với khách,
               đơn, việc, cấu hình, quyền; hỏng mà KHÁCH bị ảnh hưởng.
  van_hanh   — hệ thống tự chạy: kết nối kênh, đồng bộ, sao lưu, SLA.
  ky_thuat   — bước nhỏ và vòng lặp nền: tra tài liệu trong một lượt, gọi
               công cụ, webhook bỏ qua, ngắt mạch ERP… cần khi gỡ lỗi.

Màn Nhật ký mặc định chỉ hiện `nghiep_vu`. Bước tra tài liệu/gọi công cụ
của AI vẫn đọc được trọn trong "Lượt AI" của dòng "AI tự gửi trả lời".
"""
from __future__ import annotations

NGHIEP_VU = "nghiep_vu"
VAN_HANH = "van_hanh"
KY_THUAT = "ky_thuat"

MUC_DO: dict[str, str] = {
    NGHIEP_VU: "Nghiệp vụ quan trọng",
    VAN_HANH: "Vận hành",
    KY_THUAT: "Kỹ thuật",
}

# Kind không có trong bảng: coi là kỹ thuật — kind thật của mã hiện hành
# đều đã có nhãn (test canh), nên kind lạ chỉ còn là dòng cũ / dòng thử.
MUC_DO_MAC_DINH = KY_THUAT

_N, _V, _K = NGHIEP_VU, VAN_HANH, KY_THUAT

SU_KIEN: dict[str, tuple[str, str]] = {
    # ---------------------------------------------------------------- AI
    "ai.tu_gui": ("AI tự gửi trả lời", _N),
    "ai.soan_nhap": ("AI soạn nháp chờ duyệt", _N),
    "ai.ban_nhap.tu_choi": ("Từ chối bản nháp AI", _N),
    "ai.de_xuat.tao": ("AI tạo đề xuất chờ duyệt", _N),
    "ai.de_xuat.trung": ("Gộp đề xuất AI trùng lặp", _K),
    "ai.de_xuat.duyet": ("Duyệt đề xuất hành động AI", _N),
    "ai.de_xuat.thuc_hien": ("Thực thi tự động đề xuất AI", _N),
    "ai.de_xuat.cho_xu_ly_thu_cong": ("Chờ xử lý thủ công đề xuất sửa đơn", _N),
    "ai.de_xuat.xu_ly_thu_cong": ("Xác nhận đã xử lý thủ công đề xuất sửa đơn", _N),
    "ai.de_xuat.tu_choi": ("Từ chối đề xuất hành động AI", _N),
    "ai.de_xuat.het_han": ("Đề xuất hành động AI hết hạn", _V),
    "ai.de_xuat.loi": ("Thực thi đề xuất hành động AI bị lỗi", _N),
    "ai.de_xuat.loi_tao": ("AI không tạo được đề xuất chờ duyệt", _V),
    "ai.de_xuat.loi_gan_tin": ("Không gắn được đề xuất AI vào tin nhắn", _K),
    "ai.de_xuat.loi_dong_theo_don": ("Không đóng được đề xuất AI theo đơn", _K),
    "ai.hanh_dong.tu_dong": ("AI tự thực hiện hành động", _N),
    "ai.hanh_dong.chan": ("Chặn hành động AI vượt uỷ quyền", _N),
    "ai.hanh_dong.loi": ("Hành động tự động của AI bị lỗi", _N),
    "ai.uy_quyen.sua": ("Đổi mức uỷ quyền của AI", _N),
    "ai.uy_quyen.sua_han": ("Đổi hạn mức uỷ quyền của AI", _N),
    "agent.error": ("AI lỗi, chuyển người", _N),
    "agent.dung_bat_thuong": ("AI dừng lượt trả lời bất thường", _V),
    "agent.superseded": ("Bỏ câu trả lời lỗi thời", _K),
    "knowledge.retrieved": ("AI tra tài liệu", _K),
    "cong_cu.goi": ("AI gọi công cụ", _K),
    "dau_vet_ai.loi": ("Không ghi được dấu vết lượt AI", _K),
    "che_du_lieu.ma_la": ("Gặp mã che dữ liệu lạ trong câu trả lời AI", _K),
    "ho_so.loi": ("Không nạp được hồ sơ AI", _V),
    "thong_bao_ai.loi": ("Không gửi được thông báo của AI cho khách", _V),
    "ngan_sach.cham_tran": ("Chi phí AI chạm trần ngân sách", _N),
    "bao_mat.injection": ("Chặn tin có dấu hiệu chèn lệnh vào AI", _N),
    "bao_mat.mcp_injection": ("Chặn dữ liệu MCP có dấu hiệu chèn lệnh", _N),
    "anh.queue_that_bai": ("Không xếp được ảnh khách vào hàng xử lý", _K),
    "anh_khach.tai_that_bai": ("Không tải được ảnh khách gửi", _V),

    # ---------------------------------------------------- hội thoại & bàn giao
    "conversation.escalated": ("Chuyển cho người", _N),
    "conversation.takeover": ("Nhân viên tiếp quản", _N),
    "conversation.released": ("Trả hội thoại cho AI", _N),
    "conversation.che_do": ("Đổi chế độ AI của hội thoại", _N),
    "conversation.resolved": ("Giải quyết hội thoại", _N),
    "conversation.reopened": ("Mở lại hội thoại", _N),
    "conversation.mo_lai_tay": ("Mở lại hội thoại thủ công", _N),
    "conversation.auto_assigned": ("Tự động phân công hội thoại", _V),
    "conversation.priority_changed": ("Đổi mức ưu tiên hội thoại", _V),
    "banGiao.trao_di": ("Bàn giao sang hộp thư khác", _N),
    "banGiao.nhan_lai": ("Nhận lại hội thoại", _N),
    "banGiao.nhan_lai_that_bai": ("Nhận lại hội thoại thất bại", _V),
    "chatwoot.staff_takeover": ("Chatwoot: nhân viên tiếp quản", _N),
    "chatwoot.agent_nhan_lai": ("Chatwoot: trả hội thoại cho AI", _N),
    "chatwoot.resolved": ("Chatwoot: đóng hội thoại", _N),
    "chatwoot.staff_khong_co_hoi_thoai": ("Chatwoot: nhân viên nhắn vào hội thoại không có", _K),
    "chatwoot.webhook_thieu_hoi_thoai": ("Chatwoot: webhook thiếu hội thoại", _K),
    "csat.diem": ("Khách chấm điểm hài lòng", _N),
    "csat.khong_hoi": ("Bỏ qua hỏi đánh giá hài lòng", _K),
    "csat.cam_on_that_bai": ("Không gửi được lời cảm ơn sau đánh giá", _V),
    "escalate.khong_gui_duoc": ("Không gửi được tin báo chuyển người cho khách", _N),
    "escalate.bao_that_bai": ("Không báo được nhân viên khi chuyển người", _V),
    "escalate.bao_kenh_that_bai": ("Không báo được kênh nội bộ khi chuyển người", _V),
    "khach.doi_gap_nguoi": ("Khách đòi gặp nhân viên", _N),
    "staff.gui_file": ("Nhân viên gửi tệp cho khách", _N),
    "binh_luan.da_an": ("Ẩn bình luận", _N),
    "binh_luan.an_that_bai": ("Không ẩn được bình luận", _V),
    "tin_vao.chet": ("Tin khách không xử lý được sau nhiều lần thử", _N),
    "tin_vao.chay_lai_chuyen_nguoi": ("Xử lý lại tin khách — chuyển người", _V),
    "tin_vao.error": ("Lỗi vòng xử lý tin khách", _K),
    "webchat.gioi_han": ("Chặn webchat gửi quá nhanh", _K),

    # ------------------------------------------------------- duyệt bản nháp
    "tin_nhan.duyet": ("Duyệt bản nháp AI", _N),
    "tin_nhan.sua_ban_nhap": ("Sửa bản nháp AI", _N),
    "tin_nhan.bo_qua_canh_bao_quang_cao": ("Gửi dù có cụm cấm quảng cáo", _N),

    # --------------------------------------------------------- hàng chờ gửi
    "outbox.tin_chet": ("Tin gửi khách thất bại sau nhiều lần thử", _N),
    "outbox.retried": ("Gửi lại tin trong hàng chờ", _N),
    "outbox.cancelled": ("Huỷ tin trong hàng chờ gửi", _N),
    "outbox.enqueue_error": ("Không đưa được tin vào hàng chờ gửi", _V),
    "outbox.error": ("Lỗi vòng gửi tin", _K),

    # ------------------------------------------------------------ đơn hàng
    "order.created": ("Lên đơn", _N),
    "order.approve": ("Duyệt đơn", _N),
    "order.cancel": ("Huỷ đơn", _N),
    "order.cancel_can_huy_tay": ("Huỷ đơn — cần huỷ tay bên ERP/vận chuyển", _N),
    "order.xin_huy": ("Ghi yêu cầu huỷ đơn", _N),
    "order.xin_doi_tra": ("Ghi yêu cầu đổi trả", _N),
    "order.giu_hang_loi": ("Không giữ được hàng cho đơn", _N),
    "order.luu_that_bai": ("Không lưu được đơn", _N),
    "order.trung_bo_qua": ("Bỏ qua đơn trùng", _V),
    "order.action_result.confirmed": ("Xác nhận kết quả xử lý đơn trên ERP", _N),
    "order.action_result.mismatch": ("Kết quả xử lý đơn lệch với ERP", _N),
    "order.action_result.pending": ("Kết quả xử lý đơn chờ đối soát", _V),
    "thanh_toan.da_thu_tien": ("Ghi nhận đã thu tiền", _N),
    "thanh_toan.gui_vietqr": ("Gửi mã VietQR cho khách", _N),
    "kho.nhap": ("Nhập kho", _N),
    "kho.kiem_ke": ("Kiểm kê kho", _N),
    "kho.nap_tu_danh_muc": ("Nạp tồn kho từ danh mục", _V),
    "kho.nap_tu_danh_muc_loi": ("Nạp tồn kho từ danh mục bị lỗi", _V),

    # ---------------------------------------------------------- vận chuyển
    "shipping.created": ("Tạo vận đơn", _N),
    "shipping.create_rejected": ("Hãng vận chuyển từ chối tạo vận đơn", _N),
    "shipping.tao_that_bai": ("Tạo vận đơn thất bại", _N),
    "shipping.save_after_create_failed": ("Tạo vận đơn xong nhưng không lưu được", _N),
    "shipping.delivery_alert": ("Cảnh báo giao hàng", _N),
    "shipping.giao_don_da_huy": ("Hãng giao đơn đã huỷ", _N),
    "shipping.van_don_cho_don_da_huy": ("Có vận đơn cho đơn đã huỷ", _N),
    "shipping.restocked": ("Hoàn hàng về kho", _N),
    "shipping.manual_confirm_found": ("Xác nhận tay: đã thấy vận đơn bên hãng", _N),
    "shipping.manual_confirm_absent": ("Xác nhận tay: không có vận đơn bên hãng", _N),
    "shipping.status_changed": ("Đổi trạng thái giao hàng", _V),
    "shipping.bao_khach_that_bai": ("Không báo được khách về vận đơn", _V),
    "shipping.create_blocked_reconcile": ("Chặn tạo vận đơn khi đang chờ đối soát", _V),
    "shipping.create_unknown_timeout": ("Tạo vận đơn quá giờ, chưa rõ kết quả", _V),
    "shipping.tao_chua_ro_ket_qua": ("Tạo vận đơn chưa rõ kết quả", _V),
    "shipping.erp_synced": ("Đồng bộ vận đơn sang ERP", _V),
    "shipping.erp_sync_failed": ("Đồng bộ vận đơn sang ERP thất bại", _V),
    "shipping.erp_sync_manual_retry": ("Thử lại đồng bộ vận đơn sang ERP", _V),
    "shipping.erp_sync_dispatch_failed": ("Không gửi được việc đồng bộ vận đơn sang ERP", _K),
    "shipping.erp_sync_loop_failed": ("Lỗi vòng đồng bộ vận đơn ERP", _K),
    "shipping.reconcile_found": ("Đối soát thấy vận đơn bên hãng", _V),
    "shipping.reconcile_recovered_local": ("Khôi phục vận đơn từ đối soát", _V),
    "shipping.reconcile_escalated_manual": ("Đối soát vận đơn chuyển cho người", _V),
    "shipping.reconcile_manual_trigger": ("Chạy đối soát vận đơn thủ công", _V),
    "shipping.reconcile_retry_scheduled": ("Hẹn đối soát lại vận đơn", _K),
    "shipping.reconcile_loop_error": ("Lỗi vòng đối soát vận đơn", _K),
    "shipping.thong_tin": ("Cập nhật thông tin vận đơn", _K),
    "shipping.trang_thai_la": ("Hãng vận chuyển báo trạng thái lạ", _K),
    "shipping.webhook_hang_la": ("Webhook từ hãng vận chuyển lạ", _K),
    "shipping.webhook_ignored": ("Bỏ qua webhook vận chuyển", _K),
    "shipping.webhook_invalid": ("Webhook vận chuyển không hợp lệ", _K),
    "shipping.webhook_khong_doc_duoc": ("Không đọc được webhook vận chuyển", _K),
    "shipping.webhook_orphan": ("Webhook vận chuyển không khớp đơn nào", _K),
    "shipping.webhook_tu_choi": ("Từ chối webhook vận chuyển", _K),

    # ----------------------------------------------------------------- ERP
    "erp.xac_nhan_bang_gia": ("Xác nhận bảng giá", _N),
    "erp.go_xac_nhan_bang_gia": ("Gỡ xác nhận bảng giá", _N),
    "erp.don_da_day": ("Đẩy đơn sang ERP", _N),
    "erp.don_bi_tu_choi": ("ERP từ chối đơn", _N),
    "erp.don_huy_nhung_erp_da_nhan": ("Đơn đã huỷ nhưng ERP đã nhận", _N),
    "erp.don_cho_dong_bo": ("Đơn chờ đồng bộ sang ERP", _V),
    "erp.don_chua_submit": ("Đơn đã lên ERP nhưng chưa xác nhận", _V),
    "erp.don_da_ton_tai": ("Đơn đã có sẵn trên ERP", _V),
    "erp.don_loi_la": ("Đẩy đơn sang ERP gặp lỗi lạ", _V),
    "erp.anh_xa_lech": ("Lệch ánh xạ sản phẩm với ERP", _V),
    "erp.doi_soat_loi": ("Đối soát với ERP bị lỗi", _V),
    "erp.thieu_ho_so": ("ERP thiếu hồ sơ sản phẩm", _V),
    "erp.ngat_mach": ("ERP lỗi liên tiếp — tạm ngừng gọi", _K),
    "erp.keo_trang_thai_loi": ("Không kéo được trạng thái đơn từ ERP", _K),
    "erp.vong_dong_bo_loi": ("Lỗi vòng đồng bộ ERP", _K),

    # ------------------------------------------------------------ công việc
    "cong_viec.tao": ("Tạo công việc", _N),
    "cong_viec.sua": ("Sửa công việc", _N),
    "cong_viec.xoa": ("Xoá công việc", _N),
    "cong_viec.tu_dong_giao": ("Tự động giao công việc", _N),
    "cong_viec.canh_loi": ("Lỗi vòng nhắc hạn công việc", _K),

    # ----------------------------------------------------- khách & nhãn
    "khach.giao": ("Giao khách cho nhân viên", _N),
    "khach.giao_hang_loat": ("Giao hàng loạt khách cho nhân viên", _N),
    "khach.thu_hoi": ("Thu hồi khách", _N),
    "khach.thu_hoi_hang_loat": ("Thu hồi hàng loạt khách", _N),
    "khach.truong": ("Sửa thông tin khách", _N),
    "contact.merged": ("Gộp hồ sơ khách", _N),
    "contact.unmerged": ("Tách hồ sơ khách đã gộp", _N),
    "contact.note_added": ("Thêm ghi chú khách", _N),
    "contact.consent_changed": ("Đổi đồng ý nhận tin của khách", _N),
    "truong_khach.them": ("Thêm trường thông tin khách", _N),
    "truong_khach.sua": ("Sửa trường thông tin khách", _N),
    "truong_khach.xoa": ("Xoá trường thông tin khách", _N),
    "tam_nhin_khach.dat": ("Đổi mức tầm nhìn khách", _N),
    "nhan.tao": ("Tạo nhãn", _N),
    "nhan.sua": ("Sửa nhãn", _N),
    "nhan.xoa": ("Xoá nhãn", _N),
    "nhan.ngung": ("Ngừng dùng nhãn", _N),
    "nhan.dung_lai": ("Dùng lại nhãn", _N),
    "nhan.gan_hoi_thoai": ("Gắn nhãn hội thoại", _N),
    "nhan.go_hoi_thoai": ("Gỡ nhãn hội thoại", _N),
    "nhan.gan_khach": ("Gắn nhãn khách", _N),
    "nhan.go_khach": ("Gỡ nhãn khách", _N),
    "nhan.chuyen_quy_tac": ("Chuyển quy tắc sang danh mục nhãn mới", _K),
    "nhan.chuyen_doi": ("Chuyển đổi dữ liệu nhãn khi nâng cấp", _K),

    # ------------------------------------------------- dữ liệu cá nhân
    "contact.retention_requested": ("Yêu cầu xoá dữ liệu khách", _N),
    "contact.retention_approved": ("Duyệt xoá dữ liệu khách", _N),
    "contact.retention_cancelled": ("Huỷ yêu cầu xoá dữ liệu khách", _N),
    "contact.retention_dry_run_completed": ("Chạy thử xoá dữ liệu theo hạn lưu", _V),
    "pdpd.xin_duyet_xoa": ("Xin duyệt xoá dữ liệu cá nhân", _N),
    "pdpd.xoa_du_lieu": ("Xoá dữ liệu cá nhân của khách", _N),
    "pdpd.don_theo_thoi_han": ("Dọn dữ liệu khách hết hạn lưu", _V),
    "pdpd.auto": ("Tự động dọn dữ liệu cá nhân", _V),
    "pdpd.error": ("Lỗi vòng dọn dữ liệu cá nhân", _K),
    "bvdlcn.yeu_cau_moi": ("Nhận yêu cầu về dữ liệu cá nhân", _N),
    "bvdlcn.da_phan_hoi": ("Phản hồi yêu cầu về dữ liệu cá nhân", _N),
    "bvdlcn.gia_han": ("Gia hạn xử lý yêu cầu dữ liệu cá nhân", _N),
    "bvdlcn.da_xong": ("Hoàn tất yêu cầu dữ liệu cá nhân", _N),
    "bvdlcn.tu_choi": ("Từ chối yêu cầu dữ liệu cá nhân", _N),

    # -------------------------------------------- đăng nhập & phân quyền
    "auth.dang_nhap": ("Đăng nhập", _V),
    "auth.that_bai": ("Đăng nhập thất bại", _V),
    "auth.khoa_tam": ("Tạm khoá đăng nhập do sai nhiều lần", _N),
    "auth.go_lai_mat_khau_sai": ("Nhập sai mật khẩu khi xác nhận lại", _V),
    "auth.doi_mat_khau": ("Đổi mật khẩu", _N),
    "auth.bat_hai_buoc": ("Bật xác thực hai bước", _N),
    "auth.tat_hai_buoc": ("Tắt xác thực hai bước", _N),
    "auth.dung_ma_du_phong": ("Đăng nhập bằng mã dự phòng", _N),
    "auth.tao_nguoi_dung": ("Tạo tài khoản nhân viên", _N),
    "auth.khoa_nguoi_dung": ("Khoá / mở khoá tài khoản nhân viên", _N),
    "nguoi_dung.sua": ("Sửa thông tin nhân viên", _N),
    "nguoi_dung.dat_lai_mat_khau": ("Đặt lại mật khẩu nhân viên", _N),
    "nguoi_dung.vai_tro": ("Đổi vai trò nhân viên", _N),
    "nguoi_dung.kenh": ("Đổi kênh được giao của nhân viên", _N),
    "nguoi_dung.chuyen_viec": ("Chuyển việc sang nhân viên khác", _N),
    "vai_tro.tao": ("Tạo vai trò", _N),
    "vai_tro.sua": ("Sửa vai trò", _N),
    "vai_tro.xoa": ("Xoá vai trò", _N),
    "vai_tro.ngung_dung": ("Ngừng dùng vai trò", _N),
    "vai_tro.dung_lai": ("Dùng lại vai trò", _N),
    "phien.don_het_han": ("Dọn phiên đăng nhập hết hạn", _K),
    "phien.don_loi": ("Lỗi vòng dọn phiên đăng nhập", _K),
    "lich_ca.dat": ("Đặt lịch ca", _N),
    "lich_ca.nghi": ("Ghi ngày nghỉ", _N),
    "lich_ca.xoa_nghi": ("Xoá ngày nghỉ", _N),
    "lich_lam_viec.doi": ("Đổi lịch làm việc", _N),
    "lich_lam_viec.xoa": ("Xoá lịch làm việc", _N),

    # --------------------------------------------- cấu hình AI & tài liệu
    "runtime.update": ("Đổi cấu hình AI", _N),
    "runtime.dat_lai_mac_dinh": ("Đặt lại cấu hình AI về mặc định", _N),
    "ho_so_agent.tao": ("Tạo hồ sơ AI", _N),
    "ho_so_agent.sua": ("Sửa hồ sơ AI", _N),
    "ho_so_agent.xoa": ("Xoá hồ sơ AI", _N),
    "knowledge.draft_saved": ("Lưu nháp tài liệu", _N),
    "knowledge.published": ("Xuất bản tài liệu", _N),
    "knowledge.rolled_back": ("Khôi phục phiên bản tài liệu", _N),
    "knowledge.archived": ("Lưu trữ tài liệu", _N),
    "ky_nang.bat_tat": ("Bật / tắt kỹ năng", _N),
    "ky_nang.plugin_luu": ("Lưu plugin", _N),
    "ky_nang.plugin_xoa": ("Xoá plugin", _N),
    "ky_nang.goi_cai": ("Cài gói kỹ năng", _N),
    "ky_nang.goi_bat_tat": ("Bật / tắt gói kỹ năng", _N),
    "ky_nang.goi_xoa": ("Gỡ gói kỹ năng", _N),
    "ky_nang.ban_mo_ta_hong": ("Bản mô tả kỹ năng bị hỏng", _V),
    "ky_nang.goi_tai_lieu_hong": ("Tài liệu của gói kỹ năng bị hỏng", _V),
    "mcp.may_chu": ("Nối / sửa máy chủ MCP", _N),
    "mcp.dong_bo": ("Đồng bộ công cụ máy chủ MCP", _V),
    "tich_hop.luu": ("Lưu ứng dụng tích hợp", _N),
    "tich_hop.xoa": ("Gỡ ứng dụng tích hợp", _N),
    "cau_hinh_api.doi": ("Đổi khoá / cấu hình API", _N),
    "cau_hinh_api.xoa": ("Xoá khoá / cấu hình API", _N),
    "cau_hinh_api.giai_ma_hong": ("Không giải mã được cấu hình bí mật", _V),
    "tra_loi_nhanh.tao": ("Tạo mẫu trả lời nhanh", _N),
    "tra_loi_nhanh.sua": ("Sửa mẫu trả lời nhanh", _N),
    "tra_loi_nhanh.xoa": ("Xoá mẫu trả lời nhanh", _N),
    "tu_dong.tao": ("Tạo quy tắc tự động", _N),
    "tu_dong.sua": ("Sửa quy tắc tự động", _N),
    "tu_dong.xoa": ("Xoá quy tắc tự động", _N),
    "tu_dong.sap_xep": ("Sắp xếp thứ tự quy tắc tự động", _N),
    "tu_dong.loi": ("Quy tắc tự động chạy lỗi", _V),
    "tu_dong.ai_nhuong": ("AI nhường lượt cho quy tắc tự động", _V),
    "routing.rule_created": ("Tạo luật định tuyến", _N),
    "routing.team_created": ("Tạo nhóm định tuyến", _N),
    "routing.member_upserted": ("Cập nhật thành viên nhóm định tuyến", _N),
    "routing.sla_upserted": ("Cập nhật SLA", _N),
    "sla.muc_tieu_doi": ("Đổi mục tiêu SLA", _N),
    "sla.error": ("Lỗi vòng theo dõi SLA", _K),
    "auto_routing.error": ("Lỗi vòng tự phân công", _K),
    "auto_resolve.error": ("Lỗi vòng tự đóng hội thoại", _K),

    # ------------------------------------------------- kênh & tài khoản kênh
    "channel_account.created": ("Tạo tài khoản kênh", _N),
    "channel_account.credentials_rotated": ("Cập nhật thông tin xác thực kênh", _N),
    "channel_account.status_changed": ("Đổi trạng thái tài khoản kênh", _V),
    "channel_account.identity_bound": ("Gắn định danh tài khoản kênh", _V),
    "channel_account.reconnected": ("Kết nối lại tài khoản kênh", _V),
    "channel.dang_ky_webhook": ("Đăng ký webhook kênh", _V),
    "channel.dang_ky_webhook_loi": ("Đăng ký webhook kênh thất bại", _V),
    "kenh.agent_bat_tat": ("Bật / tắt AI cho kênh", _N),
    "kenh.ho_so_agent": ("Đổi hồ sơ AI của kênh", _N),
    "kenh.tuy_chon": ("Đổi tuỳ chọn kênh", _N),
    "kenh.xoa_tai_khoan": ("Xoá tài khoản kênh", _N),
    "zalo.account.default": ("Đặt tài khoản Zalo mặc định", _N),
    "zalo.account.pinned": ("Ghim tài khoản Zalo cho hội thoại", _N),
    "zalo_oa.oauth": ("Kết nối Zalo OA", _N),
    "zalo_oa.oauth_loi": ("Kết nối Zalo OA thất bại", _V),
    "zalo_oa.webhook_ten_mien_moi": ("Zalo OA: cần dán lại địa chỉ webhook", _V),
    "zalo_personal.da_khoi_phuc": ("Khôi phục phiên Zalo cá nhân", _V),
    "zalo_personal.can_quet_lai": ("Zalo cá nhân mất phiên (cần quét QR)", _V),
    "zalo_personal.sidecar_khong_toi": ("Sidecar Zalo cá nhân không phản hồi", _V),
    "zalo_personal.lech_bi_mat_sidecar": ("Lệch bí mật sidecar Zalo cá nhân", _V),
    "zalo_personal.giu_phien.error": ("Lỗi giữ phiên Zalo cá nhân", _K),
    "zalo_personal.bo_tin_nhom": ("Bỏ qua tin nhóm Zalo cá nhân", _K),
    "zalo_personal.tin_bo_qua": ("Bỏ qua tin Zalo cá nhân không đọc được", _K),
    "oauth.meta.loi": ("Meta: kết nối tài khoản thất bại", _V),
    "oauth.meta.dang_ky_webhook_loi": ("Meta: đăng ký webhook thất bại", _V),
    "oauth.meta.tao_tai_khoan_loi": ("Meta: không tạo được tài khoản kênh", _V),
    "oauth.meta.tao_instagram_loi": ("Meta: không tạo được tài khoản Instagram", _V),
    "oauth.meta.hien_chon_trang": ("Meta: hiện danh sách trang để chọn", _K),
    "oauth.meta.state_khong_hop_le": ("Meta: phiên kết nối không hợp lệ", _K),
    "meta.token_sap_het": ("Token Meta sắp hết hạn", _V),
    "meta.token_chet": ("Token Meta hết hiệu lực", _V),
    "meta.canh_han_token_loi": ("Lỗi kiểm hạn token Meta", _K),
    "media.thu_lai": ("Tải lại tệp khách gửi", _V),
    "media.khong_tai_duoc": ("Không tải được tệp khách gửi", _V),
    "media.don": ("Dọn tệp media cũ", _K),
    "media.xem_truoc_don": ("Xem trước dọn tệp media", _K),
    "media.error": ("Lỗi vòng dọn tệp media", _K),
    "attachment.ngoai_thu_muc_du_lieu": ("Chặn tệp đính kèm ngoài thư mục dữ liệu", _K),

    # ------------------------------------------------ hệ thống & nhật ký
    "su_co.danh_dau": ("Đánh dấu sự cố", _N),
    "su_co.can_thiep": ("Bước can thiệp sự cố", _N),
    "su_co.ket_thuc": ("Kết thúc sự cố", _N),
    "nhat_ky.giai_trinh": ("Giải trình / đính chính", _N),
    "nhat_ky.xuat": ("Xuất nhật ký", _N),
    "bao_cao.xuat_excel": ("Xuất báo cáo Excel", _N),
    "backup.done": ("Sao lưu dữ liệu xong", _V),
    "backup.failed": ("Sao lưu dữ liệu thất bại", _V),
    "backup.error": ("Lỗi vòng sao lưu", _V),
    "canh_gac": ("Kiểm tra sức khoẻ hệ thống định kỳ", _K),
    "canh_gac.loi": ("Kiểm tra sức khoẻ phát hiện lỗi", _V),
    "canh_gac.loi_gui": ("Không gửi được cảnh báo sức khoẻ hệ thống", _V),
    "bao_nhan_vien.loi_gui": ("Không gửi được tin báo cho nhân viên", _V),
    "ket_noi.ghi_kiem_loi": ("Không ghi được kết quả kiểm tra kết nối", _K),
    "app.start": ("Khởi động ứng dụng", _K),
    "poll.start": ("Bắt đầu kéo tin", _K),
    "poll.error": ("Lỗi kéo tin", _K),
    "legacy.polling.bat": ("Bật chế độ kéo tin kiểu cũ", _K),
    "demo.seed": ("Nạp dữ liệu mẫu", _K),
}

# Nhãn theo TIỀN TỐ cho kind lạ — "Sự kiện khác · Vận chuyển" đọc được,
# `shipping.cai_gi_do_moi` thì không.
TIEN_TO: dict[str, str] = {
    "ai": "AI", "agent": "AI", "knowledge": "Tài liệu", "cong_cu": "Công cụ AI",
    "conversation": "Hội thoại", "banGiao": "Bàn giao", "chatwoot": "Chatwoot",
    "csat": "Đánh giá hài lòng", "escalate": "Chuyển người", "tin_nhan": "Bản nháp AI",
    "tin_vao": "Tin khách", "outbox": "Hàng chờ gửi", "order": "Đơn hàng",
    "thanh_toan": "Thanh toán", "kho": "Kho", "shipping": "Vận chuyển", "erp": "ERP",
    "cong_viec": "Công việc", "khach": "Khách hàng", "contact": "Khách hàng",
    "nhan": "Nhãn", "truong_khach": "Trường khách", "pdpd": "Dữ liệu cá nhân",
    "bvdlcn": "Dữ liệu cá nhân", "auth": "Đăng nhập", "nguoi_dung": "Nhân viên",
    "vai_tro": "Vai trò", "phien": "Phiên đăng nhập", "lich_ca": "Lịch ca",
    "runtime": "Cấu hình AI", "ho_so_agent": "Hồ sơ AI", "ky_nang": "Kỹ năng",
    "mcp": "Máy chủ MCP", "tich_hop": "Tích hợp", "cau_hinh_api": "Cấu hình API",
    "tra_loi_nhanh": "Trả lời nhanh", "tu_dong": "Tự động hoá", "routing": "Định tuyến",
    "sla": "SLA", "channel_account": "Tài khoản kênh", "channel": "Kênh", "kenh": "Kênh",
    "zalo": "Zalo", "zalo_oa": "Zalo OA", "zalo_personal": "Zalo cá nhân",
    "oauth": "Kết nối", "meta": "Meta", "media": "Tệp khách gửi", "su_co": "Sự cố",
    "nhat_ky": "Nhật ký", "backup": "Sao lưu", "canh_gac": "Sức khoẻ hệ thống",
    "poll": "Kéo tin", "webchat": "Webchat",
}


def nhan(kind: str) -> str:
    """Tên tiếng Việt của một kind — KHÔNG BAO GIỜ trả mã thô."""
    if kind in SU_KIEN:
        return SU_KIEN[kind][0]
    dau = (kind or "").split(".", 1)[0]
    if dau in TIEN_TO:
        return f"Sự kiện khác · {TIEN_TO[dau]}"
    return "Sự kiện hệ thống chưa phân loại"


def muc_do(kind: str) -> str:
    return SU_KIEN[kind][1] if kind in SU_KIEN else MUC_DO_MAC_DINH


def gia_tri(khoa: str, v: object) -> str:
    """Giá trị một khoá `detail` để đọc: mã lý do/chế độ dịch sang tiếng Việt."""
    s = str(v)
    return NHAN_GIA_TRI.get(s, s) if khoa in KHOA_CO_MA else s


# Tên tiếng Việt của khoá và giá trị hay gặp trong `detail`, cho câu tóm
# tắt kết quả. "ly_do: khong_co_chu_va_khong_co_tep" là đúng thứ UX-18-01
# chỉ ra — khoá và mã lý do đều là chữ của lập trình viên.
NHAN_KHOA: dict[str, str] = {
    "ket_qua": "kết quả", "ly_do": "lý do", "reason": "lý do", "loi": "lỗi",
    "error": "lỗi", "ghi_chu": "ghi chú", "ma_don": "mã đơn", "tieu_de": "tiêu đề",
    "ten": "tên", "tag": "nhãn", "che_do": "chế độ",
    "external_account_id": "định danh", "so_tien": "số tiền", "tong_tien": "tổng tiền",
}

# Chỉ dịch giá trị dưới các khoá MÃ (lý do, chế độ, mức uỷ quyền) — dịch
# "auto" ở một khoá tự do như `ghi_chu` là sửa lời người viết.
KHOA_CO_MA = frozenset({"ly_do", "reason", "che_do", "muc_uy_quyen"})

NHAN_GIA_TRI: dict[str, str] = {
    "khong_co_chu_va_khong_co_tep": "tin không có chữ cũng không có tệp",
    "thieu_thread_id_hoac_msg_id": "tin thiếu mã cuộc trò chuyện hoặc mã tin",
    "message_khong_phai_object": "dữ liệu tin không đúng dạng",
    "duplicate_or_stale": "trùng hoặc đã cũ",
    "erp_tu_choi": "ERP từ chối",
    "hoan_hang": "hoàn hàng",
    "auto": "AI tự trả lời", "assist": "AI soạn nháp chờ duyệt",
    "tu_dong": "tự động", "co_phe_duyet": "cần phê duyệt",
    "khong_su_dung": "không dùng", "goi_y": "gợi ý",
}
