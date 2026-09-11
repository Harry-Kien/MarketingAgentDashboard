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
    # Hai quyền `xem_tat_ca` dưới đây là thứ trước bản này gọi là `is_admin`
    # và truyền thẳng vào mệnh đề WHERE.
    #
    # Chúng phải đứng RIÊNG, không gộp vào `.doc`: `.doc` nằm trong tập của
    # vai trò `Nhân viên`, nên gộp là mọi nhân viên bỗng thấy khách và hội
    # thoại của mọi kênh — một lần nới quyền toàn hệ thống mà không có gì
    # hỏng để ai đó nhận ra.
    "hoi_thoai.xem_tat_ca": "Xem hội thoại của mọi kênh, kể cả kênh không được giao",

    "khach.doc": "Xem danh sách khách",
    "khach.xem_tat_ca": "Xem khách của mọi kênh, kể cả kênh không được giao",
    "khach.sua": "Sửa thông tin khách",
    "khach.pii": "Xem số điện thoại, email, địa chỉ",
    "khach.giao": "Giao khách cho nhân viên",
    "khach.gop": "Gộp hai hồ sơ khách",
    "khach.xoa": "Xoá vĩnh viễn dữ liệu cá nhân",

    "cong_viec.doc": "Xem công việc được giao cho mình",
    "cong_viec.xem_tat_ca": "Xem công việc của mọi người",
    "cong_viec.sua": "Tạo, sửa, đổi trạng thái công việc",
    "cong_viec.giao": "Giao việc cho người khác",

    "kenh.doc": "Xem tài khoản kênh",
    "kenh.sua": "Sửa, bật tắt tài khoản kênh",
    "kenh.noi": "Nối kênh mới (OAuth, quét QR)",

    "dinh_tuyen.doc": "Xem luật định tuyến và SLA",
    "dinh_tuyen.sua": "Sửa luật định tuyến và SLA",

    "outbox.doc": "Xem hàng chờ gửi",
    "outbox.sua": "Gửi lại, huỷ tin trong hàng chờ",

    # `agent.doc` từng bị xoá khỏi danh mục vì không endpoint nào dùng —
    # chính test "mọi quyền đều có chỗ dùng" bắt được. Nó quay lại khi có
    # màn hồ sơ agent, và lần này có chỗ dùng thật: xem danh sách hồ sơ.
    "agent.doc": "Xem hồ sơ agent và trạng thái",
    "agent.dieu_khien": "Bật tắt agent, đổi chế độ, đổi ngưỡng, sửa hồ sơ",
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
    ("GET", "/api/connect/zalo-oa/callback"),  # xác thực bằng state + PKCE
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


def kiem_moi_route_co_quyen(app) -> None:
    """
    Ném nếu còn route chưa khai quyền. Gọi lúc KHỞI ĐỘNG, không lúc chạy.

    Cùng hàm này chạy trong test, nên CI bắt trước khi kịp triển khai — và
    test với thực tế không thể lệch nhau.

    Không có tham số "bỏ qua tạm". Trong lúc dựng lớp quyền đã từng có một
    `DANH_SACH_HOAN` để thu nhỏ dần; giữ lại nó sau khi xong là giữ đúng cái
    lỗ mà cả lớp này sinh ra để bịt — một chỗ để nhét route mới vào cho khỏi
    phải nghĩ.
    """
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
            if da_khai or (pt, duong) in MIEN_TRU:
                continue
            thieu.append(f"{pt} {duong}")
    if thieu:
        raise RuntimeError(
            "Route chưa khai quyền — thêm Depends(can_quyen(...)) hoặc khai "
            "vào MIEN_TRU:\n  " + "\n  ".join(sorted(thieu))
        )
