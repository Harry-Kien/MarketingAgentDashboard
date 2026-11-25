"""
Dịch mã kỹ thuật của kênh sang lời người vận hành đọc được: chuyện gì, vì
sao, làm gì.

VÌ SAO CẦN
----------
Màn Kết nối từng hiện thẳng `reauth_required`, `degraded`, `provider.
unreachable`, `AccountAlreadyExists` (UX-20-05). Mã ấy đúng — nhưng một mã
không hành động được: `provider.unreachable` đúng cho cả "sidecar chưa bật",
"mạng chết" lẫn "token hết hạn", ba việc phải làm khác hẳn nhau. Người trực
thấy mã, không biết làm gì, đi hỏi — trong khi câu trả lời có thể viết sẵn.

VÌ SAO Ở MÁY CHỦ, KHÔNG Ở GIAO DIỆN
---------------------------------
Cùng lý do với `suc_khoe_kenh.py`: luật nằm ở một chỗ. Bảng ở giao diện thì
API (và nhật ký, và báo động) vẫn nói mã thô, hai nơi lệch nhau dần.

MÃ GỐC VẪN ĐI KÈM
-----------------
`ma` và `ly_do_goc` luôn trả lại, để giao diện đặt trong "Chi tiết nâng
cao": mã là thứ tra được trong tài liệu và nhắn cho người khác. Bỏ mã là
mất đường tra cứu.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GiaiThich:
    tieu_de: str       # chuyện gì đang xảy ra — một câu ngắn
    nguyen_nhan: str   # vì sao thường xảy ra
    cach_sua: str      # bấm gì / làm gì


_META = frozenset({"facebook", "instagram", "whatsapp", "messenger"})

BANG: dict[str, GiaiThich] = {
    # --- trạng thái tài khoản (khi không có mã sự kiện nào rõ hơn)
    "pending": GiaiThich(
        "Tài khoản chưa hoàn tất kết nối",
        "Đã tạo tài khoản nhưng chưa xác minh thành công với nền tảng.",
        "Bấm nút hành động trên dòng tài khoản (Quét QR / Nhận tin / Xác minh lại)."),
    "degraded": GiaiThich(
        "Kết nối đang gián đoạn",
        "Lần kiểm gần nhất với nền tảng không thành công — tin có thể không vào hoặc không gửi ra.",
        "Bấm Kiểm tra kết nối. Vẫn lỗi thì xem lý do gốc trong Chi tiết nâng cao."),
    "reauth_required": GiaiThich(
        "Cần đăng nhập / cấp quyền lại",
        "Phiên đăng nhập hoặc quyền truy cập do nền tảng cấp đã hết hạn hay bị thu hồi.",
        "Bấm nút xác thực lại trên dòng tài khoản (Quét QR với Zalo cá nhân, "
        "Đăng nhập Facebook với Trang Meta)."),
    "disabled": GiaiThich(
        "Tài khoản đang tạm ngắt",
        "Có người đã chủ động tạm ngắt tài khoản này.",
        "Bấm Bật lại khi muốn nhận và gửi tin trở lại."),
    "disconnected": GiaiThich(
        "Mất kết nối với nền tảng",
        "Phiên làm việc bị ngắt — thường do mạng, do máy chủ khởi động lại hoặc phiên hết hạn.",
        "Bấm Kiểm tra kết nối; với Zalo cá nhân, quét lại mã QR nếu vẫn ngắt."),
    # --- kết quả xác minh với nền tảng
    "provider.unreachable": GiaiThich(
        "Không liên lạc được với nền tảng",
        "Dịch vụ trung gian chưa chạy (sidecar Zalo cá nhân), mạng chập chờn, "
        "hoặc nền tảng đang gián đoạn.",
        "Kiểm tra dịch vụ trung gian đã chạy chưa rồi bấm Kiểm tra kết nối lại."),
    "provider.unauthorized": GiaiThich(
        "Nền tảng từ chối thông tin đăng nhập",
        "Token / khoá bí mật sai, đã hết hạn hoặc đã bị thu hồi.",
        "Kết nối lại tài khoản để lấy token mới (đăng nhập lại hoặc nhập lại khoá)."),
    "provider.token_expired": GiaiThich(
        "Token đã hết hạn",
        "Quyền truy cập do nền tảng cấp có thời hạn và đã quá hạn.",
        "Đăng nhập lại để gia hạn quyền."),
    "provider.rejected": GiaiThich(
        "Nền tảng từ chối yêu cầu",
        "Nền tảng trả lời nhưng không chấp nhận — thường do thiếu quyền hoặc cấu hình bên nền tảng.",
        "Đọc lý do gốc trong Chi tiết nâng cao, sửa cấu hình bên nền tảng rồi kiểm tra lại."),
    "provider.invalid_response": GiaiThich(
        "Nền tảng trả về dữ liệu không đọc được",
        "Nền tảng đổi định dạng hoặc đang lỗi tạm thời.",
        "Thử Kiểm tra kết nối sau ít phút; còn lỗi thì báo người quản trị kỹ thuật."),
    "provider.identity_missing": GiaiThich(
        "Chưa xác định được tài khoản trên nền tảng",
        "Nền tảng không trả về mã định danh (Page ID / OA ID / số điện thoại).",
        "Kiểm tra lại ID tài khoản đã nhập, rồi bấm Kiểm tra kết nối."),
    "provider.not_connected": GiaiThich(
        "Tài khoản chưa đăng nhập",
        "Chưa có phiên làm việc nào với nền tảng.",
        "Hoàn tất bước đăng nhập (Quét QR / Đăng nhập) cho tài khoản này."),
    "provider.verification_not_supported": GiaiThich(
        "Kênh này không có phép kiểm tự động",
        "Nền tảng không cho kiểm tra kết nối bằng một lời gọi chỉ đọc.",
        "Nhắn thử một tin vào kênh để chứng minh kết nối."),
    # --- Zalo cá nhân (sidecar)
    "zalo_personal.disconnected": GiaiThich(
        "Zalo cá nhân mất kết nối",
        "Phiên Zalo bị ngắt hoặc sidecar Zalo vừa khởi động lại.",
        "Đợi vài phút để phiên tự khôi phục; vẫn ngắt thì bấm Quét QR."),
    "zalo_personal.can_quet_lai": GiaiThich(
        "Phiên Zalo cá nhân đã hết",
        "Zalo đã đăng xuất phiên này (đổi mật khẩu, đăng nhập nơi khác, hoặc hết hạn).",
        "Bấm Quét QR và quét bằng app Zalo trên điện thoại."),
    "zalo_personal.qr_pending": GiaiThich(
        "Đang chờ quét mã QR",
        "Mã QR đã tạo nhưng chưa ai quét.",
        "Bấm Quét QR và quét bằng app Zalo trong khoảng hai phút."),
    "zalo_personal.qr_expired": GiaiThich(
        "Mã QR đã hết hạn",
        "Mã QR chỉ sống khoảng hai phút.",
        "Bấm Quét QR để lấy mã mới."),
    "zalo_personal.connecting": GiaiThich(
        "Zalo cá nhân đang kết nối",
        "Sidecar đang khôi phục phiên.",
        "Đợi một phút rồi tải lại màn hình."),
    "zalo_personal.lech_bi_mat_sidecar": GiaiThich(
        "Sidecar Zalo chạy với bí mật khác máy chủ",
        "Sidecar khởi động trước khi máy chủ đổi bí mật (ZALO_SIDECAR_SECRET).",
        "Khởi động lại sidecar Zalo — KHÔNG cần quét QR."),
    "zalo_personal.sidecar_khong_toi": GiaiThich(
        "Sidecar Zalo cá nhân không phản hồi",
        "Tiến trình sidecar Zalo chưa chạy hoặc đã dừng.",
        "Bật lại sidecar (python -m scripts.chay_sidecar_zalo), rồi bấm Kiểm tra kết nối."),
    # --- quyền Meta (vòng canh token)
    "meta.token_sap_het": GiaiThich(
        "Quyền Facebook sắp hết hạn",
        "Quyền dữ liệu Meta cấp cho Trang có thời hạn 90 ngày.",
        "Bấm Đăng nhập Facebook lại để gia hạn thêm 90 ngày."),
    "meta.token_chet": GiaiThich(
        "Quyền Facebook đã hết",
        "Quyền dữ liệu Meta đã hết hạn hoặc bị thu hồi — tin không còn về.",
        "Bấm Đăng nhập Facebook lại để nối lại Trang."),
    # --- lỗi nghiệp vụ khi thao tác
    "AccountAlreadyExists": GiaiThich(
        "Tài khoản này đã được kết nối trước đó",
        "Cùng một tài khoản trên nền tảng (cùng Page ID / OA ID / số) chỉ gắn được một lần.",
        "Tìm tài khoản ấy trong danh sách và bấm Kiểm tra kết nối thay vì tạo mới."),
    "AccountDisabled": GiaiThich(
        "Tài khoản đang tạm ngắt hoặc thiếu thông tin xác thực",
        "Tài khoản bị tạm ngắt, hoặc chưa có thông tin xác thực để hoạt động.",
        "Bật lại tài khoản, hoặc hoàn tất bước đăng nhập / nhập khoá."),
    "AccountNotFound": GiaiThich(
        "Không tìm thấy tài khoản kênh",
        "Tài khoản đã bị xoá hoặc bạn không có quyền xem nó.",
        "Tải lại màn hình Kết nối."),
}

# Mã chưa có trong bảng vẫn phải nói ĐƯỢC điều gì đó, theo họ của mã — không
# thì người dùng lại thấy đúng cái mã thô mà bảng này dựng ra để thay.
_THEO_TIEN_TO: tuple[tuple[str, GiaiThich], ...] = (
    ("provider.", GiaiThich(
        "Kiểm tra với nền tảng chưa thành công",
        "Nền tảng trả về một lỗi hệ thống chưa phân loại.",
        "Bấm Kiểm tra kết nối lại; còn lỗi thì gửi mã lỗi trong Chi tiết nâng cao cho "
        "người quản trị kỹ thuật.")),
    ("zalo_personal.", GiaiThich(
        "Zalo cá nhân báo trạng thái bất thường",
        "Sidecar Zalo gửi về một trạng thái chưa phân loại.",
        "Bấm Kiểm tra kết nối; nếu vẫn lỗi thì Quét QR lại.")),
)

# Cách sửa riêng theo KÊNH cho những mã mà việc phải làm khác nhau giữa nền tảng.
_CACH_SUA_THEO_KENH: dict[tuple[str, str], str] = {
    ("provider.unauthorized", "meta"): "Bấm Đăng nhập Facebook lại để Meta cấp token mới.",
    ("provider.unauthorized", "zalo_oa"): "Kết nối lại Zalo OA bằng nút cấp quyền để lấy khoá mới.",
    ("provider.unreachable", "zalo_personal"): (
        "Bật sidecar Zalo cá nhân (python -m scripts.chay_sidecar_zalo) rồi bấm Kiểm tra kết nối."),
    ("reauth_required", "meta"): "Bấm Đăng nhập Facebook lại để nối lại Trang.",
    ("reauth_required", "zalo_personal"): "Bấm Quét QR và quét bằng app Zalo trên điện thoại.",
}


def _nhom_kenh(kenh: str) -> str:
    return "meta" if kenh in _META else kenh


def tra(ma: str | None, *, kenh: str = "") -> GiaiThich | None:
    """Giải thích cho một mã; None khi mã rỗng. Mã lạ vẫn có câu theo họ của mã."""
    m = str(ma or "").strip()
    if not m:
        return None
    goc = BANG.get(m) or next((g for tien_to, g in _THEO_TIEN_TO if m.startswith(tien_to)), None)
    if goc is None:
        return None
    rieng = _CACH_SUA_THEO_KENH.get((m, _nhom_kenh(kenh)))
    return GiaiThich(goc.tieu_de, goc.nguyen_nhan, rieng) if rieng else goc


def giai_thich(ma: str | None, *, kenh: str = "", ly_do: str | None = None) -> dict[str, Any] | None:
    """Gói cho API: lời giải thích + mã gốc + lý do gốc (để ở Chi tiết nâng cao)."""
    g = tra(ma, kenh=kenh)
    if g is None:
        return None
    return {"ma": str(ma), "tieu_de": g.tieu_de, "nguyen_nhan": g.nguyen_nhan,
            "cach_sua": g.cach_sua, "ly_do_goc": (ly_do or "").strip()[:300] or None}


def cau_loi(ma: str, mac_dinh: str) -> str:
    """Một câu cho thông báo lỗi của API: lời gốc + cách sửa. Mã lạ: giữ lời gốc."""
    g = tra(ma)
    return f"{mac_dinh} — {g.cach_sua}" if g else mac_dinh
