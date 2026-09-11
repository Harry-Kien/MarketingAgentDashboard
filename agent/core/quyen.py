"""
Danh mục quyền, và chốt bắt route chưa khai quyền.

VÌ SAO DANH MỤC NẰM TRONG MÃ CHỨ KHÔNG TRONG CSDL
--------------------------------------------------
Vai trò do người tạo. Nhưng *tập quyền có thể tồn tại* thì mã quyết định.

Nếu danh mục là dữ liệu tự do, người thêm endpoint tháng sau sẽ gõ một chuỗi
quyền chưa từng tồn tại — hoặc quên gõ. Endpoint ấy thành không ai canh, và
không có gì phát hiện. Hằng trong mã cho phép chốt ở dưới quét mọi route và
bắt route nào chưa khai.

Đúng nguyên tắc của repo: ràng buộc nằm trong MÃ, không nằm trong cấu hình.
Cấu hình chỉ được SIẾT (gán ít quyền hơn), không được NỚI.

VÌ SAO CHỐT ĐẶT Ở LÚC KHỞI ĐỘNG
-------------------------------
Chốt đăng nhập ở `agent/main.py` hỏng-đóng được vì nó chặn theo TIỀN TỐ
đường dẫn — không cần biết endpoint nào tồn tại. Quyền thì không: mỗi
endpoint cần một quyền khác nhau, nên phải khai ở đâu đó.

Khai bằng `Depends` đọc dễ nhưng hỏng-mở; bảng ánh xạ tập trung hỏng-đóng
nhưng nằm xa endpoint nên lệch âm thầm khi đổi đường dẫn. Cách ở đây lấy cả
hai: khai cạnh endpoint, rồi `kiem_moi_route_co_quyen()` kiểm ĐỦ lúc khởi
động. Quên khai thì máy chủ không lên — không phải một endpoint phơi ra
lặng lẽ.
"""
from __future__ import annotations

from collections.abc import Iterator

# Mã quyền -> nhãn tiếng Việt hiện trên màn cấp quyền.
#
# Nhóm theo tiền tố trước dấu chấm. Dashboard gom theo nhóm ấy, nên tiền tố
# là thứ người vận hành đọc chứ không chỉ là quy ước đặt tên.
QUYEN: dict[str, str] = {
    "hoi_thoai.doc": "Đọc hội thoại",
    "hoi_thoai.tra_loi": "Trả lời khách",
    "hoi_thoai.nhan": "Nhận và chuyển hội thoại",

    "khach.doc": "Xem danh sách khách",
    "khach.sua": "Sửa thông tin khách",
    "khach.pii": "Xem số điện thoại, email, địa chỉ",
    "khach.giao": "Giao khách cho nhân viên",
    "khach.gop": "Gộp hai hồ sơ khách",
    "khach.xoa": "Xoá vĩnh viễn dữ liệu cá nhân",

    "kenh.doc": "Xem tài khoản kênh",
    "kenh.sua": "Sửa, bật tắt tài khoản kênh",
    "kenh.noi": "Nối kênh mới (OAuth, quét QR)",

    "dinh_tuyen.doc": "Xem luật định tuyến và SLA",
    "dinh_tuyen.sua": "Sửa luật định tuyến và SLA",

    "outbox.doc": "Xem hàng chờ gửi",
    "outbox.sua": "Gửi lại, huỷ tin trong hàng chờ",

    "agent.doc": "Xem trạng thái agent",
    "agent.dieu_khien": "Bật tắt agent, đổi chế độ và ngưỡng",
    "phong_thu.dung": "Dùng phòng thử agent",

    "ky_nang.doc": "Xem kỹ năng và plugin",
    "ky_nang.sua": "Cài, gỡ, bật tắt kỹ năng và plugin",

    "mcp.doc": "Xem máy chủ MCP",
    "mcp.sua": "Nối, đồng bộ, gỡ máy chủ MCP",

    "tich_hop.doc": "Xem và dùng ứng dụng đã nối",
    "tich_hop.sua": "Nối và gỡ ứng dụng",

    "cau_hinh.doc": "Xem cấu hình và kho tri thức",
    "cau_hinh.sua": "Sửa cấu hình và kho tri thức",
    "catalog.duyet": "Xác nhận bảng giá",

    "don.doc": "Xem đơn hàng và tồn kho",
    "don.sua": "Duyệt, huỷ đơn; nhập kho, kiểm kê",

    "noi_dung.doc": "Xem và soạn video, bài đăng",
    "noi_dung.duyet": "Duyệt đăng nội dung công khai",

    "bao_cao.doc": "Xem báo cáo, số đo và chi phí",

    "nguoi_dung.doc": "Xem danh sách nhân viên",
    "nguoi_dung.sua": "Tạo, khoá nhân viên; sửa vai trò và quyền",
}

# Route không cần quyền. Khai TỪNG CÁI, không dùng mẫu tiền tố.
#
# Mẫu kiểu "mọi thứ bắt đầu bằng /webhook" là chỗ để endpoint mới lọt vào mà
# không ai để ý — đúng loại lỗ mà `_MO` trong main.py đã cẩn thận tránh.
#
# `/api/toi/doi-mat-khau` đổi mật khẩu của CHÍNH MÌNH nên cũng ở đây: bắt
# buộc quyền tại đó nghĩa là người bị thu hết quyền không đổi nổi mật khẩu
# của mình, kể cả khi mật khẩu ấy vừa lộ.
MIEN_TRU: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/api/dang-nhap"),
    ("POST", "/api/dang-xuat"),
    ("GET", "/api/toi"),
    ("POST", "/api/toi/doi-mat-khau"),
    ("GET", "/api/suc-khoe"),
    ("GET", "/api/he-thong"),
    ("GET", "/api/connect/meta/callback"),   # xác thực bằng state token
})

# Route CHƯA khai quyền, hoãn tạm trong lúc A1 đang chạy.
#
# Danh sách này chỉ được PHÉP NHỎ ĐI. Việc cuối của A1 xoá hẳn nó cùng tham
# số `hoan` — để lại một danh sách hoãn sau khi xong là để lại đúng cái lỗ
# mà cả khối này sinh ra để bịt.
DANH_SACH_HOAN: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/api/analytics"),
    ("GET", "/api/analytics/khach"),
    ("GET", "/api/attachments/{attachment_id}/file"),
    ("POST", "/api/campaigns"),
    ("GET", "/api/catalog/products"),
    ("GET", "/api/cau-hinh"),
    ("GET", "/api/cau-hinh/lich-su"),
    ("POST", "/api/cau-hinh/mac-dinh"),
    ("GET", "/api/channels"),
    ("GET", "/api/contacts"),
    ("POST", "/api/contacts/merge"),
    ("GET", "/api/contacts/merge/preview"),
    ("POST", "/api/contacts/merges/{merge_id}/undo"),
    ("GET", "/api/contacts/{contact_id}"),
    ("PUT", "/api/contacts/{contact_id}/consents/{purpose}"),
    ("POST", "/api/contacts/{contact_id}/notes"),
    ("POST", "/api/contacts/{contact_id}/retention-jobs"),
    ("POST", "/api/contacts/{contact_id}/tags"),
    ("GET", "/api/conversations"),
    ("GET", "/api/conversations/{conv_id}"),
    ("POST", "/api/conversations/{conv_id}/account"),
    ("POST", "/api/conversations/{conv_id}/release"),
    ("POST", "/api/conversations/{conv_id}/send"),
    ("POST", "/api/conversations/{conv_id}/send-file"),
    ("POST", "/api/conversations/{conv_id}/takeover"),
    ("GET", "/api/cost"),
    ("DELETE", "/api/erp/xac-nhan-bang-gia"),
    ("GET", "/api/erp/xac-nhan-bang-gia"),
    ("POST", "/api/erp/xac-nhan-bang-gia"),
    ("GET", "/api/events"),
    ("GET", "/api/inbox/conversations"),
    ("GET", "/api/inbox/conversations/{conversation_id}"),
    ("POST", "/api/inbox/conversations/{conversation_id}/che-do"),
    ("POST", "/api/inbox/conversations/{conversation_id}/read"),
    ("POST", "/api/inbox/conversations/{conversation_id}/release"),
    ("POST", "/api/inbox/conversations/{conversation_id}/takeover"),
    ("GET", "/api/inbox/events"),
    ("GET", "/api/kho"),
    ("GET", "/api/kho/bien-dong"),
    ("POST", "/api/kho/{ma}/kiem-ke"),
    ("POST", "/api/kho/{ma}/nhap"),
    ("GET", "/api/knowledge"),
    ("POST", "/api/knowledge"),
    ("POST", "/api/knowledge/probe"),
    ("DELETE", "/api/knowledge/{doc_id}"),
    ("GET", "/api/ky-nang"),
    ("POST", "/api/ky-nang/bat-tat"),
    ("POST", "/api/ky-nang/plugin"),
    ("POST", "/api/ky-nang/plugin/thu"),
    ("DELETE", "/api/ky-nang/plugin/{ten}"),
    ("POST", "/api/ky-nang/plugin/{ten}/khoi-phuc/{id_ban}"),
    ("GET", "/api/ky-nang/plugin/{ten}/lich-su"),
    ("POST", "/api/messages/{message_id}/approve"),
    ("GET", "/api/nguoi-dung"),
    ("POST", "/api/nguoi-dung"),
    ("POST", "/api/nguoi-dung/{ten}/khoa"),
    ("GET", "/api/orders"),
    ("POST", "/api/orders/{order_id}/approve"),
    ("POST", "/api/orders/{order_id}/cancel"),
    ("GET", "/api/overview"),
    ("GET", "/api/pdpd"),
    ("POST", "/api/pdpd/don-theo-han"),
    ("GET", "/api/pdpd/{sdt}"),
    ("POST", "/api/pdpd/{sdt}/xoa"),
    ("GET", "/api/posts"),
    ("POST", "/api/posts"),
    ("POST", "/api/posts/approve-all"),
    ("POST", "/api/posts/draft"),
    ("POST", "/api/posts/{post_id}/approve"),
    ("POST", "/api/posts/{post_id}/callback"),
    ("POST", "/api/posts/{post_id}/cancel"),
    ("GET", "/api/posts/{post_id}/kit"),
    ("POST", "/api/posts/{post_id}/mark-posted"),
    ("GET", "/api/posts/{post_id}/metrics"),
    ("POST", "/api/posts/{post_id}/metrics"),
    ("GET", "/api/posts/{post_id}/video"),
    ("GET", "/api/publish/channels"),
    ("POST", "/api/runtime"),
    ("GET", "/api/san-pham/{ma}/anh"),
    ("GET", "/api/tich-hop/ung-dung"),
    ("POST", "/api/tich-hop/ung-dung"),
    ("POST", "/api/tich-hop/ung-dung/thu"),
    ("DELETE", "/api/tich-hop/ung-dung/{ten}"),
    ("GET", "/api/videos"),
    ("POST", "/api/videos"),
    ("POST", "/api/videos/upload"),
    ("POST", "/api/videos/{video_id}/approve"),
    ("GET", "/api/videos/{video_id}/assets"),
    ("GET", "/api/videos/{video_id}/assets/{ord}/file"),
    ("GET", "/api/videos/{video_id}/file"),
    ("POST", "/api/videos/{video_id}/retry"),
    ("POST", "/api/zalo/account"),
    ("GET", "/api/zalo/accounts"),
    ("GET", "/tich-hop/{ten}"),
    ("DELETE", "/tich-hop/{ten}/{duong:path}"),
    ("GET", "/tich-hop/{ten}/{duong:path}"),
    ("PATCH", "/tich-hop/{ten}/{duong:path}"),
    ("POST", "/tich-hop/{ten}/{duong:path}"),
    ("PUT", "/tich-hop/{ten}/{duong:path}"),
})


def moi_route(gom) -> Iterator:
    """
    Duyệt ĐỆ QUY mọi route của app.

    Bản FastAPI đang dùng gói router đã `include_router` vào một
    `_IncludedRouter`; route thật nằm trong `.original_router`. Duyệt phẳng
    cho 7 route thay vì 166, và chốt dưới sẽ báo xanh trong khi 159 route
    chưa khai quyền.
    """
    for r in gom:
        goc = getattr(r, "original_router", None)
        if goc is not None:
            yield from moi_route(goc.routes)
        else:
            yield r


def kiem_moi_route_co_quyen(app, *, hoan: frozenset | None = None) -> None:
    """
    Ném nếu còn route chưa khai quyền. Gọi lúc KHỞI ĐỘNG, không lúc chạy.

    Cùng hàm này chạy trong test, nên CI bắt trước khi kịp triển khai —
    và test với thực tế không thể lệch nhau.
    """
    cho_qua = DANH_SACH_HOAN if hoan is None else hoan
    thieu = []
    for route in moi_route(app.routes):
        duong = getattr(route, "path", "")
        if not duong.startswith(("/api", "/tich-hop")):
            continue
        phu_thuoc = getattr(getattr(route, "dependant", None), "dependencies", ())
        da_khai = any(getattr(x.call, "quyen_yeu_cau", None) for x in phu_thuoc)
        for pt in sorted(getattr(route, "methods", None) or set()):
            if pt in {"HEAD", "OPTIONS"}:
                continue
            if da_khai or (pt, duong) in MIEN_TRU or (pt, duong) in cho_qua:
                continue
            thieu.append(f"{pt} {duong}")
    if thieu:
        raise RuntimeError(
            "Route chưa khai quyền — thêm Depends(can_quyen(...)) hoặc khai "
            "vào MIEN_TRU:\n  " + "\n  ".join(sorted(thieu))
        )
