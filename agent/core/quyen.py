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
    # Mẫu trả lời nhanh là câu MỌI người sẽ gửi cho khách — sửa nó là sửa
    # lời của cả cửa hàng, nên tách khỏi `hoi_thoai.tra_loi` (ai cũng có).
    "tra_loi_nhanh.sua": "Thêm, sửa, xoá mẫu trả lời nhanh",
    # Tách khỏi `hoi_thoai.tra_loi` (22.11.2026, phiếu việc mục 12): nhãn
    # và ghi chú nội bộ là việc SẮP XẾP, không phải nói với khách. Gộp chung
    # thì không có cách nào cho một người chỉ phân loại hội thoại mà không
    # nhắn được cho khách — hoặc ngược lại. Migration 0058 cấp nó cho mọi vai
    # trò đang có `hoi_thoai.tra_loi`, nên không ai mất việc đang làm được.
    "hoi_thoai.ghi_chu": "Gắn, gỡ nhãn và viết ghi chú nội bộ cho hội thoại",

    "khach.doc": "Xem danh sách khách",
    "khach.xem_tat_ca": "Xem khách của mọi kênh, kể cả kênh không được giao",
    "khach.sua": "Sửa thông tin khách",
    # NHÃN PHẢI NÓI ĐÚNG VIỆC QUYỀN NÀY LÀM.
    #
    # Nhãn cũ là "Xem số điện thoại, email, địa chỉ" — và nó sai ở chỗ quan
    # trọng nhất: quyền này KHÔNG mở số điện thoại trong màn Khách hàng.
    # Việc che PII ở đó do VAI TRÒ TRONG KÊNH quyết định (`owner`/`manager`
    # của `account_memberships`), còn `khach.pii` mở ba route tra cứu PDPD
    # theo số điện thoại. Quản trị đọc nhãn cũ rồi tick, tin là đã cấp quyền
    # xem SĐT — mà nhân viên vẫn thấy `*******456`, và không ai hiểu vì sao.
    # Đo và ghim bằng `tests/test_ai_thay_gi_ve_khach.py`.
    "khach.pii": "Tra cứu hồ sơ cá nhân theo số điện thoại (trang PDPD)",
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

    # Nhãn cũ "Xem đơn hàng và tồn kho" / "...; nhập kho, kiểm kê" thôi đúng
    # từ khi Kho có quyền riêng (0058): nhãn nói một việc quyền không còn làm
    # là ô tick nói dối.
    "don.doc": "Xem đơn hàng",
    "don.sua": "Duyệt, huỷ, cập nhật đơn hàng",

    # KHO TÁCH KHỎI ĐƠN (22.11.2026, phiếu việc mục 12). Trước đây xem tồn
    # kho đi kèm xem đơn, nhập kho đi kèm huỷ đơn: người kiểm kê buộc phải
    # được huỷ đơn của khách. Migration 0058 cấp `kho.doc` cho mọi vai trò
    # có `don.doc`, `kho.sua` cho mọi vai trò có `don.sua` — không ai mất
    # màn đang dùng.
    "kho.doc": "Xem sản phẩm, giá và tồn kho",
    "kho.sua": "Nhập kho, kiểm kê",

    "bao_cao.doc": "Xem báo cáo, số đo và chi phí",

    "nguoi_dung.doc": "Xem danh sách nhân viên",
    "nguoi_dung.sua": "Tạo, khoá nhân viên; sửa vai trò và quyền",

    # Tách khỏi `hoi_thoai.doc` (20.11.2026): nhật ký kiểm toán ghi cả đổi
    # quyền, khoá tài khoản, xoá dữ liệu khách — không phải thứ mọi nhân
    # viên đọc hội thoại cần thấy.
    "nhat_ky.doc": "Xem nhật ký kiểm toán",
    # GHI vào nhật ký (22.11.2026, phiếu việc mục 18): đánh dấu một hành
    # động AI là sự cố, ghi bước can thiệp, kết quả, lời giải trình. Tách
    # khỏi `nhat_ky.doc` vì đọc và ghi là hai trách nhiệm khác nhau — và
    # mọi dòng ghi ra là vĩnh viễn (bảng chỉ thêm, migration 0064). Migration
    # 0064 cấp nó cho mọi vai trò đang có `nhat_ky.doc`.
    "nhat_ky.su_co": "Đánh dấu sự cố AI, ghi bước can thiệp và giải trình",

    # PHÊ DUYỆT AI tách khỏi `hoi_thoai.tra_loi` (22.11.2026, phiếu việc mục
    # 12). Duyệt bản nháp là CHO PHÉP lời AI viết đi tới khách — trách nhiệm
    # khác với tự gõ một câu trả lời, và chủ cửa hàng muốn giao nó riêng
    # (ví dụ: nhân viên mới trả lời được nhưng chưa được duyệt lời AI).
    # Migration 0058 cấp nó cho mọi vai trò đang có `hoi_thoai.tra_loi`.
    #
    # KHÔNG phải ba mức uỷ quyền của AI (AI được tự làm gì — bảng
    # `ai_uy_quyen`, agent/core/uy_quyen.py). Đây là quyền của NGƯỜI: cho lời
    # AI đi tới khách, và (mục 17) cho một HÀNH ĐỘNG AI đề xuất được thi hành.
    # Duyệt hành động còn đòi thêm quyền nghiệp vụ của chính hành động ấy
    # (`don.sua` cho tạo/huỷ đơn) — xem agent/api/uy_quyen_ai.py.
    "ai.duyet": "Duyệt câu trả lời và đề xuất hành động do AI soạn sẵn",
}

# =====================================================================
#  NHÓM HIỂN THỊ (phiếu việc mục 12.2)
# =====================================================================
# Màn cấp quyền gom ô tick theo CHỨC NĂNG của dashboard, không theo tiền tố
# mã. Tiền tố là quy ước của người viết mã (`outbox`, `dinh_tuyen`, `mcp`),
# còn chủ cửa hàng nghĩ theo màn hình: "người này được đụng vào phần Cấu hình
# chung không". Đổi MÃ quyền để khớp nhóm là làm vỡ mọi vai trò đang lưu —
# nên mã giữ nguyên, nhóm chỉ là lớp trình bày.
#
# Mỗi quyền nằm trong ĐÚNG MỘT nhóm — có test canh. Quyền mới quên xếp nhóm
# thì không hiện trên màn cấp quyền, tức là không ai cấp được: hỏng im lặng.
NHOM_QUYEN: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("hoi_thoai", "Hội thoại", (
        "hoi_thoai.doc", "hoi_thoai.xem_tat_ca", "hoi_thoai.tra_loi",
        "hoi_thoai.nhan", "hoi_thoai.ghi_chu",
    )),
    ("khach_hang", "Khách hàng", (
        "khach.doc", "khach.xem_tat_ca", "khach.sua", "khach.giao",
        "khach.gop", "khach.pii", "khach.xoa",
    )),
    ("don_hang", "Đơn hàng", ("don.doc", "don.sua")),
    ("kho", "Kho", ("kho.doc", "kho.sua", "catalog.duyet")),
    ("cong_viec", "Công việc", (
        "cong_viec.doc", "cong_viec.xem_tat_ca", "cong_viec.sua",
        "cong_viec.giao",
    )),
    ("phan_tich", "Phân tích", ("bao_cao.doc",)),
    ("cau_hinh_chung", "Cấu hình chung", (
        "tra_loi_nhanh.sua", "dinh_tuyen.doc", "dinh_tuyen.sua",
        "kenh.doc", "kenh.sua", "kenh.noi", "tich_hop.doc", "tich_hop.sua",
    )),
    ("cau_hinh_ai", "Cấu hình AI Agent", (
        "agent.doc", "agent.dieu_khien", "phong_thu.dung",
        "cau_hinh.doc", "cau_hinh.sua", "ky_nang.doc", "ky_nang.sua",
        "mcp.doc", "mcp.sua",
    )),
    ("nhan_su", "Nhân sự & Phân quyền", ("nguoi_dung.doc", "nguoi_dung.sua")),
    ("he_thong", "Hệ thống & Nhật ký", (
        "nhat_ky.doc", "nhat_ky.su_co", "outbox.doc", "outbox.sua",
    )),
    ("phe_duyet_ai", "Phê duyệt AI", ("ai.duyet",)),
)

# Quyền ĐÃ GỠ khỏi danh mục. Không bao giờ được dùng lại tên này.
#
# `noi_dung.*` canh màn video và đăng bài — gỡ ngày 19.11.2026 khi chủ dự án
# chốt hệ thống chỉ làm chăm sóc khách hàng.
#
# VÌ SAO KHÔNG XOÁ DÒNG TRONG CSDL MÀ GIỮ DANH SÁCH NÀY
# ----------------------------------------------------
# `vai_tro_quyen` của cửa hàng đang chạy vẫn còn dòng `noi_dung.doc` (migration
# 0019 nạp nó cho vai trò Nhân viên), và migration thì đã chốt checksum —
# không sửa được. Không cần xoá: mọi chỗ đọc quyền (`xac_thuc.doc_phien`,
# màn vai trò, màn giải thích quyền) đã lọc theo `QUYEN`, nên dòng mồ côi
# không cấp gì; lưu lại vai trò thì nó tự rơi khỏi CSDL.
#
# Danh sách này để hai việc: test cho phép migration cũ nhắc các tên ấy, và
# test cấm đặt lại đúng tên ấy cho một quyền MỚI — dùng lại tên là mọi vai
# trò còn dòng cũ bỗng có quyền mới mà không ai cấp.
QUYEN_DA_GO: frozenset[str] = frozenset({"noi_dung.doc", "noi_dung.duyet"})

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
    # 2FA của CHÍNH mình — ai đăng nhập cũng phải tự bảo vệ được tài khoản.
    # Route vẫn đòi đăng nhập (bat_buoc_dang_nhap); tắt đòi gõ lại mật khẩu.
    ("GET", "/api/toi/hai-buoc"),
    ("POST", "/api/toi/hai-buoc/bat-dau"),
    ("POST", "/api/toi/hai-buoc/xac-nhan"),
    ("POST", "/api/toi/hai-buoc/tat"),
    # Chuông thông báo của CHÍNH mình — mọi câu SQL lọc theo người đăng
    # nhập (xem agent/api/thong_bao_noi_bo.py). Vẫn đòi đăng nhập.
    ("GET", "/api/toi/thong-bao"),
    ("GET", "/api/toi/thong-bao/so-chua-doc"),
    ("POST", "/api/toi/thong-bao/da-doc-het"),
    ("POST", "/api/toi/thong-bao/{thong_bao_id}/da-doc"),
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
