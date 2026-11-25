"""
Sức khoẻ kênh: MỘT dòng xanh / vàng / đỏ cho mỗi kênh, kèm ĐÚNG MỘT việc cần làm.

VÌ SAO CẦN MÀN NÀY KHI ĐÃ CÓ "XÁC MINH PROVIDER" VÀ BÁO ĐỘNG
------------------------------------------------------------
Đo được 19.11.2026: quyền dữ liệu của Trang Facebook duy nhất còn 5 ngày.
Vòng canh token đã phát hiện từ ngày 18 và báo đúng — nhưng báo vào webhook
báo động và bảng `events`, hai chỗ chủ cửa hàng không mở. Màn Kết nối vẫn
hiện Trang ấy "Đang chạy" màu xanh. Tới hạn, tin Facebook sẽ ngừng về mà
màn hình vẫn xanh.

Tương tự: Zalo OA "active" mà chưa từng có webhook nào tới — trạng thái
`active` chỉ nói "token gọi được API", không nói "khách nhắn thì tin về".

Nên mỗi dòng ở đây trả lời ba câu người vận hành thật sự hỏi: tin khách có
đang về không, sắp hỏng gì không, và nếu có thì bấm nút nào.

VÌ SAO HÀM ĐÁNH GIÁ LÀ HÀM THUẦN
--------------------------------
Mọi luật xanh/vàng/đỏ nằm trong `danh_gia()`, không chạm CSDL hay mạng, để
test được từng trường hợp — và để không có lời gọi Graph nào trên đường mở
màn hình (29 Trang × debug_token = màn hình treo vài giây mỗi lần làm mới).
Số ngày còn lại của token lấy từ sự kiện mà vòng canh token đã ghi.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

# Kênh mà tin khách đi vào qua WEBHOOK do hãng gọi tới. Với các kênh này,
# "active" mà chưa từng nhận tin nào là chưa chứng minh được địa chỉ webhook
# khai bên hãng là đúng.
KENH_WEBHOOK = frozenset({"facebook", "instagram", "whatsapp", "zalo_oa"})
KENH_META = frozenset({"facebook", "instagram", "whatsapp"})

# Cùng mốc với vòng canh token (agent/channels/suc_khoe_token_meta.py).
NGAY_BAO_TRUOC = 14

# Sự kiện token cũ hơn mốc này không còn phản ánh hiện tại: vòng canh chạy
# mỗi ngày, nên quá hai ngày không có sự kiện mới = token đã được cấp lại
# (hoặc vòng canh đã chết — chuyện đó có bảng sẵn sàng canh riêng).
SU_KIEN_TOKEN_SONG = timedelta(days=2)

XANH, VANG, DO, TAT = "xanh", "vang", "do", "tat"


@dataclass(frozen=True, slots=True)
class DongKenh:
    muc: str            # xanh | vang | do | tat
    viec: str           # một câu, người đọc hiểu không cần biết kỹ thuật
    hanh_dong: str      # mã nút: dang_nhap_meta, quet_qr, xac_minh, nhan_thu, bat_lai, ""


def _ngay(con_lai: float) -> str:
    n = max(0, int(con_lai))
    return "hôm nay" if n == 0 else f"{n} ngày"


def danh_gia(
    *,
    channel: str,
    status: str,
    ly_do_hong: str | None = None,
    tin_vao_gan_nhat: datetime | None = None,
    token: dict[str, Any] | None = None,
    bay_gio: datetime | None = None,
) -> DongKenh:
    """
    `token`: sự kiện mới nhất của vòng canh token Meta cho tài khoản này —
    `{"kind": "meta.token_sap_het" | "meta.token_chet", "ngay_con_lai": float,
    "luc": datetime}` — hoặc None khi không có (token ổn, hoặc không phải Meta).
    """
    bay_gio = bay_gio or datetime.now(timezone.utc)
    st = str(status or "")
    meta = channel in KENH_META

    if st == "disabled":
        return DongKenh(TAT, "Đang tạm ngắt — không nhận, không gửi tin.", "bat_lai")

    if st == "reauth_required":
        if channel == "zalo_personal":
            return DongKenh(DO, "Phiên Zalo đã hết — khách nhắn không vào. Quét lại mã QR.",
                            "quet_qr")
        if meta:
            return DongKenh(DO, "Mất quyền với Meta — đăng nhập Facebook lại để nối lại.",
                            "dang_nhap_meta")
        return DongKenh(DO, "Mất quyền với nhà cung cấp — kết nối lại tài khoản này.",
                        "xac_minh")

    if st in ("pending", "degraded"):
        ly_do = (ly_do_hong or "").strip()
        if channel == "zalo_personal":
            return DongKenh(DO, ly_do or "Chưa kết nối được — quét mã QR.", "quet_qr")
        if st == "pending" and channel in ("facebook", "instagram"):
            return DongKenh(VANG, "Đã nối nhưng chưa bật nhận tin — bấm Nhận tin.",
                            "nhan_tin")
        muc = VANG if st == "pending" else DO
        return DongKenh(muc, ly_do or "Chưa xác minh được với nhà cung cấp.", "xac_minh")

    # --- active
    if meta and token and bay_gio - token["luc"] <= SU_KIEN_TOKEN_SONG:
        con = token.get("ngay_con_lai")
        if token.get("kind") == "meta.token_chet" or (con is not None and con <= 0):
            return DongKenh(DO, "Quyền Facebook ĐÃ HẾT — tin không về nữa. Đăng nhập Facebook lại.",
                            "dang_nhap_meta")
        if con is not None and con <= NGAY_BAO_TRUOC:
            return DongKenh(
                VANG if con > 3 else DO,
                f"Quyền Facebook còn {_ngay(con)} — đăng nhập Facebook lại để gia hạn 90 ngày.",
                "dang_nhap_meta")

    if channel in KENH_WEBHOOK and tin_vao_gan_nhat is None:
        return DongKenh(
            VANG,
            "Chưa nhận được tin khách nào — nhắn thử một tin vào kênh để chứng minh webhook đúng.",
            "nhan_thu")

    return DongKenh(XANH, "Đang nhận tin bình thường.", "")


def danh_gia_dia_chi_cong_khai(url: str | None) -> DongKenh:
    """Địa chỉ mà Meta/Zalo gọi webhook và OAuth quay về."""
    u = (url or "").strip()
    if not u.startswith("https://"):
        return DongKenh(DO, "Chưa có địa chỉ HTTPS công khai — Facebook, Instagram, WhatsApp, "
                            "Zalo OA không gọi tin vào được (Zalo cá nhân và web vẫn chạy).",
                        "")
    host = urlparse(u).hostname or ""
    if host.endswith("trycloudflare.com"):
        return DongKenh(VANG, "Địa chỉ TẠM (trycloudflare) — đổi mỗi lần tunnel chạy lại, mỗi "
                              "lần đổi phải khai lại webhook ở Meta/Zalo. Dùng tên miền cố định.",
                        "")
    return DongKenh(XANH, "Địa chỉ cố định — khai webhook một lần là xong.", "")


# ------------------------------------------------------------------ một trạng thái
#
# VÌ SAO CẦN MỘT TRẠNG THÁI HỢP NHẤT
# --------------------------------
# Màn Kết nối từng hiện BA nhãn cho cùng một tài khoản: pill "Sẵn sàng" lấy từ
# `status`, chấm đỏ ở Sức khoẻ kênh lấy từ `danh_gia()`, và "Kết nối thành
# công" ở thẻ plugin. Zalo cá nhân hiện "Sẵn sàng" trong khi Sức khoẻ ghi lỗi
# kết nối — người vận hành tin dòng xanh, vì nó to hơn (UX-20-01).
#
# Nay chỉ còn MỘT nhãn, suy ra từ đúng thứ `danh_gia()` đã kết luận, nên hai
# chỗ không thể nói ngược nhau. "Nền tảng hỗ trợ" (khả năng của adapter) và
# "đã cấu hình" KHÔNG phải trạng thái — chúng nằm ở phần chi tiết.

CHUA_KET_NOI, HOAT_DONG, TAM_NGAT, CAN_XAC_THUC, LOI = (
    "chua_ket_noi", "hoat_dong", "tam_ngat", "can_xac_thuc", "loi")
NHAN_TRANG_THAI_KET_NOI = {
    CHUA_KET_NOI: "Chưa kết nối",
    HOAT_DONG: "Hoạt động",
    TAM_NGAT: "Tạm ngắt",
    CAN_XAC_THUC: "Cần xác thực lại",
    LOI: "Lỗi",
}
# Nút đưa người dùng đi ĐĂNG NHẬP / QUÉT LẠI — tức là mất quyền, không phải hỏng.
_HANH_DONG_XAC_THUC = frozenset({"dang_nhap_meta", "quet_qr"})


def trang_thai_ket_noi(*, status: str, muc: str, hanh_dong: str) -> str:
    """Trạng thái DUY NHẤT hiện cho người vận hành, suy từ kết luận của `danh_gia()`.

    Trạng thái lạ rơi về LỖI chứ không về "Chưa kết nối": xanh giả nguy hiểm
    hơn đỏ giả — đỏ thì người ta đi kiểm.
    """
    st = str(status or "")
    if st == "disabled":
        return TAM_NGAT
    if st == "reauth_required":
        return CAN_XAC_THUC
    if st == "pending":
        return CHUA_KET_NOI
    if st == "degraded":
        return LOI
    if st == "active":
        if muc == DO:
            # active mà đỏ: quyền Meta đã/sắp hết -> phải đăng nhập lại; còn
            # lại là hỏng thật.
            return CAN_XAC_THUC if hanh_dong in _HANH_DONG_XAC_THUC else LOI
        return HOAT_DONG
    return LOI
