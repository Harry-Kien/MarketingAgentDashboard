"""
VietQR — mã QR chuyển khoản theo chuẩn EMVCo của NAPAS. Hàm THUẦN.

VÌ SAO TỰ SINH, KHÔNG GỌI DỊCH VỤ NGOÀI
--------------------------------------
Có dịch vụ trả sẵn ảnh QR qua URL (img.vietqr.io…). Dùng nó là gửi số tài
khoản, số tiền và mã đơn của mọi đơn hàng cho một bên thứ ba, và mỗi lần
dịch vụ ấy chậm hay sập là khách không thanh toán được. Chuỗi EMVCo chỉ là
vài trường TLV cộng một CRC — tự sinh vừa không lộ dữ liệu vừa không thêm
một chỗ hỏng.

CẤU TRÚC (mỗi trường: mã 2 số + độ dài 2 số + giá trị)
-----------------------------------------------------
  00 = "01"                  phiên bản
  01 = "12"                  QR động (có số tiền, dùng một lần cho một đơn)
  38 = thông tin tài khoản:
       00 = "A000000727"     GUID của NAPAS
       01 = 00 BIN ngân hàng + 01 số tài khoản
       02 = "QRIBFTTA"       chuyển nhanh tới TÀI KHOẢN (không phải thẻ)
  53 = "704"                 VND
  54 = số tiền               số nguyên, không dấu phân cách
  58 = "VN"
  62 = 08 nội dung chuyển khoản
  63 = CRC-16/CCITT-FALSE của toàn bộ chuỗi tính tới hết "6304"
"""
from __future__ import annotations

import re
import unicodedata

GUID_NAPAS = "A000000727"
DICH_VU_TAI_KHOAN = "QRIBFTTA"
TOI_DA_TIEN = 999_999_999_999       # 13 chữ số — trần độ dài trường 54

_BIN = re.compile(r"^\d{6}$")
_SO_TK = re.compile(r"^[A-Za-z0-9]{6,19}$")


def _truong(ma: str, gia_tri: str) -> str:
    if len(gia_tri) > 99:
        raise ValueError(f"trường {ma} dài quá 99 ký tự")
    return f"{ma}{len(gia_tri):02d}{gia_tri}"


def crc16(du_lieu: str) -> str:
    """CRC-16/CCITT-FALSE: đa thức 0x1021, khởi tạo 0xFFFF, không đảo bit."""
    crc = 0xFFFF
    for b in du_lieu.encode("utf-8"):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def lam_sach_noi_dung(noi_dung: str, toi_da: int = 50) -> str:
    """
    Bỏ dấu, chỉ giữ chữ-số-khoảng trắng, tối đa 50 ký tự.

    App ngân hàng VN xử lý nội dung có dấu mỗi nơi một kiểu: nơi cắt, nơi
    đổi thành "?", nơi từ chối cả mã. Mã đơn trong nội dung là thứ duy nhất
    để đối soát tiền về với đơn — mất nó là kế toán phải dò tay.
    """
    s = unicodedata.normalize("NFD", noi_dung.replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Za-z0-9 ]+", " ", s)
    return " ".join(s.split())[:toi_da].strip()


def tao_payload(*, bin_nh: str, so_tk: str, so_tien: int, noi_dung: str) -> str:
    bin_nh, so_tk = str(bin_nh).strip(), str(so_tk).strip()
    if not _BIN.match(bin_nh):
        raise ValueError("BIN ngân hàng phải gồm đúng 6 chữ số (ví dụ Vietcombank 970436)")
    if not _SO_TK.match(so_tk):
        raise ValueError("Số tài khoản chỉ gồm chữ và số, 6–19 ký tự, không khoảng trắng")
    if not isinstance(so_tien, int) or so_tien <= 0 or so_tien > TOI_DA_TIEN:
        raise ValueError("Số tiền phải là số nguyên dương (đồng)")

    tai_khoan = _truong("00", GUID_NAPAS) \
        + _truong("01", _truong("00", bin_nh) + _truong("01", so_tk)) \
        + _truong("02", DICH_VU_TAI_KHOAN)
    nd = lam_sach_noi_dung(noi_dung)
    than = (_truong("00", "01") + _truong("01", "12") + _truong("38", tai_khoan)
            + _truong("53", "704") + _truong("54", str(so_tien)) + _truong("58", "VN")
            + (_truong("62", _truong("08", nd)) if nd else "")
            + "6304")
    return than + crc16(than)


def ve_svg(payload: str, *, co: int = 6) -> str:
    """Ảnh QR dạng SVG. Mức sửa lỗi M — chuẩn VietQR khuyến nghị."""
    import io

    import segno

    buf = io.BytesIO()
    segno.make(payload, error="m", micro=False).save(buf, kind="svg", scale=co, border=2)
    return buf.getvalue().decode("utf-8")
