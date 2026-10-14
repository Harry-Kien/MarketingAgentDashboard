"""
VietQR cho đơn hàng — chuỗi EMVCo đúng chuẩn NAPAS, kiểm không cần mạng.

Một mã QR sai một ký tự thì app ngân hàng báo "mã không hợp lệ" — hoặc tệ
hơn, quét ra đúng tài khoản nhưng SAI SỐ TIỀN. Nên mỗi trường được kiểm
riêng, và CRC được đối chiếu với một bản cài đặt độc lập viết lại ở đây.
"""
from __future__ import annotations

import pytest

from agent.thanh_toan import vietqr


def _crc_doc_lap(du_lieu: str) -> str:
    """CRC-16/CCITT-FALSE viết lại từng bit — KHÔNG dùng bảng như bản chính."""
    crc = 0xFFFF
    for b in du_lieu.encode("utf-8"):
        for i in range(8):
            bit = (b >> (7 - i)) & 1
            c15 = (crc >> 15) & 1
            crc = (crc << 1) & 0xFFFF
            if c15 ^ bit:
                crc ^= 0x1021
    return f"{crc:04X}"


def test_crc_khop_vec_to_chuan():
    # Véc-tơ kiểm chuẩn của CRC-16/CCITT-FALSE: "123456789" -> 29B1.
    assert vietqr.crc16("123456789") == "29B1"
    assert _crc_doc_lap("123456789") == "29B1"


def _tach(payload: str) -> dict[str, str]:
    """Tách TLV cấp một: id(2) + độ dài(2) + giá trị."""
    ra, i = {}, 0
    while i < len(payload):
        ma, dai = payload[i:i + 2], int(payload[i + 2:i + 4])
        ra[ma] = payload[i + 4:i + 4 + dai]
        i += 4 + dai
    assert i == len(payload), "TLV lệch độ dài"
    return ra


def test_payload_dung_tung_truong():
    p = vietqr.tao_payload(bin_nh="970436", so_tk="0011001234567",
                           so_tien=245000, noi_dung="AS251014")
    t = _tach(p)
    assert t["00"] == "01"
    assert t["01"] == "12"                          # QR động: có số tiền
    assert t["53"] == "704"                         # VND
    assert t["54"] == "245000"
    assert t["58"] == "VN"
    tk = _tach(t["38"])
    assert tk["00"] == "A000000727"                 # GUID NAPAS
    assert tk["02"] == "QRIBFTTA"                   # chuyển tới tài khoản
    nh = _tach(tk["01"])
    assert nh == {"00": "970436", "01": "0011001234567"}
    assert _tach(t["62"]) == {"08": "AS251014"}
    assert t["63"] == _crc_doc_lap(p[:-4])


def test_noi_dung_bo_dau_va_ky_tu_la():
    """App ngân hàng cắt hoặc từ chối ký tự ngoài ASCII trong nội dung CK."""
    p = vietqr.tao_payload(bin_nh="970436", so_tk="123456", so_tien=1000,
                           noi_dung="Đơn AS-25/10 của chị Hoà")
    nd = _tach(_tach(p)["62"])["08"]
    assert nd.isascii() and nd == "Don AS 25 10 cua chi Hoa"


@pytest.mark.parametrize("sai", [
    dict(bin_nh="97043", so_tk="123456", so_tien=1000),          # BIN 5 số
    dict(bin_nh="970436", so_tk="12 34", so_tien=1000),          # khoảng trắng
    dict(bin_nh="970436", so_tk="123456", so_tien=0),            # 0 đồng
    dict(bin_nh="970436", so_tk="123456", so_tien=-5),
    dict(bin_nh="970436", so_tk="123456", so_tien=10_000_000_000_000),
])
def test_dau_vao_sai_thi_no(sai):
    with pytest.raises(ValueError):
        vietqr.tao_payload(noi_dung="x", **sai)


def test_svg_ve_duoc():
    svg = vietqr.ve_svg(vietqr.tao_payload(bin_nh="970436", so_tk="123456",
                                           so_tien=1000, noi_dung="AS1"))
    assert svg.lstrip().startswith("<svg") or svg.lstrip().startswith("<?xml")
