"""
Kiểm HÌNH DẠNG credential ngay lúc lưu, không đợi tới lúc gọi provider.

LỖI THẬT, NGƯỜI DÙNG GẶP HAI LẦN LIÊN TIẾP (03.09.2026)
-------------------------------------------------------
Người dùng dán **Access token** (424 ký tự) vào ô **Secret key** — hai thứ
nằm cạnh nhau trên cùng một trang của Zalo Developers, và ô nào cũng là một
chuỗi dài che bằng dấu chấm.

Hệ thống nhận, lưu vào kho mã hoá, báo thành công. Rồi tài khoản chuyển
`degraded` với `Invalid secret key` — một thông điệp đúng nhưng không nói
được rằng người dùng dán nhầm Ô.

Họ thử lại, dán y hệt, và hỏng y hệt. Vòng lặp ấy chỉ dừng khi có người đi
đếm độ dài chuỗi đang lưu.

VÌ SAO KIỂM ĐỘ DÀI LÀ ĐỦ, VÀ VÌ SAO KHÔNG KIỂM CHẶT HƠN
-------------------------------------------------------
Secret Key của Zalo là 32 ký tự. Nhưng ràng buộc đúng 32 sẽ hỏng vào ngày
Zalo đổi định dạng — và lúc đó nó chặn một cấu hình hoàn toàn hợp lệ, ở một
chỗ người dùng không sửa được.

Nên chỉ chặn thứ KHÔNG THỂ đúng: một chuỗi dài gấp mười lần. 424 ký tự
không phải Secret Key ở bất kỳ phiên bản nào — nó là token dán nhầm ô.

Ranh giới đặt rộng rãi (100) để không bao giờ chặn nhầm, mà vẫn bắt được
đúng ca đã xảy ra.
"""
from __future__ import annotations


class HinhDangSai(ValueError):
    """Credential có hình dạng không thể đúng. Thông điệp nói rõ sửa ô nào."""


# Trần độ dài cho từng khoá, theo TỪNG KÊNH.
#
# Chỉ khai những khoá có hình dạng ỔN ĐỊNH và ĐÃ TỪNG bị dán nhầm. Khai
# tràn lan là tạo ra một danh sách phải bảo trì mỗi lần provider đổi gì đó,
# và nó sẽ mục.
_TRAN: dict[str, dict[str, tuple[int, str]]] = {
    "zalo_oa": {
        # Zalo Secret Key = 32 ký tự. Access token và refresh token đều dài
        # hàng trăm — đó chính là hai thứ hay bị dán nhầm vào đây, vì trên
        # trang "Lấy Access Token" của Zalo chúng nằm ngay cạnh nhau.
        "secret_key": (
            100,
            "Secret Key của Zalo dài khoảng 32 ký tự. Chuỗi bạn dán dài hơn "
            "nhiều — nhiều khả năng đó là ACCESS TOKEN. Lấy Secret Key ở "
            "Zalo Developers → Ứng dụng của bạn → Cài đặt → Secret Key, "
            "KHÔNG phải ở trang 'Lấy Access Token'.",
        ),
    },
}


def kiem(kenh: str, credentials: dict | None) -> None:
    """
    Ném `HinhDangSai` nếu một khoá có hình dạng không thể đúng.

    Im lặng cho mọi thứ khác: đây là lưới bắt lỗi dán nhầm ô, không phải bộ
    xác thực credential. Thứ duy nhất xác thực được credential là provider.
    """
    if not credentials:
        return
    tran = _TRAN.get(kenh)
    if not tran:
        return
    for khoa, (toi_da, giai_thich) in tran.items():
        gia_tri = credentials.get(khoa)
        if not isinstance(gia_tri, str):
            continue
        n = len(gia_tri.strip())
        if n > toi_da:
            raise HinhDangSai(
                f"Ô {khoa!r} dài {n} ký tự — không thể đúng. {giai_thich}"
            )
