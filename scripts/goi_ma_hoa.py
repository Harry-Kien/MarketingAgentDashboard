"""
Mã hoá gói chuyển nhà (máy này -> VPS).

Gói chứa CSDL khách hàng, khoá kho bí mật (giải mã được token Facebook,
Zalo) và tệp khách gửi — lạc một bản không mã hoá là lộ toàn bộ cửa hàng.
Nên gói LUÔN mã hoá, mật khẩu nằm ở tệp RIÊNG, và hai thứ đi hai đường.

ĐỊNH DẠNG
---------
    MAGIC(8) | SALT(16) | khối...

    khối = độ dài bản mã (4, big-endian) | nonce (12) | bản mã AES-256-GCM

AAD của mỗi khối = MAGIC | SALT | số thứ tự khối (8) | cờ khối cuối (1).
Đổi thứ tự, bỏ bớt khối, hay CẮT CỤT tệp (thiếu khối cuối) đều bị phát
hiện — cắt cụt là lỗi hay gặp nhất khi chép tệp lớn qua mạng chập chờn,
và một gói "giải mã được nhưng thiếu nửa CSDL" là thứ tệ nhất có thể có.

Khoá dẫn từ mật khẩu bằng scrypt (n=2^15): chậm có chủ đích với người dò.
"""
from __future__ import annotations

import os
import secrets
import struct
from collections.abc import Iterator
from typing import BinaryIO

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"CSKHGOI1"
KHOI = 4 * 1024 * 1024


class LoiGoi(Exception):
    """Gói hỏng, sai mật khẩu, hoặc bị cắt cụt."""


def sinh_mat_khau() -> str:
    return secrets.token_urlsafe(24)


def _khoa(mat_khau: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(mat_khau.encode("utf-8"))


def _aad(salt: bytes, i: int, cuoi: bool) -> bytes:
    return MAGIC + salt + struct.pack(">Q?", i, cuoi)


def ma_hoa(vao: BinaryIO, ra: BinaryIO, mat_khau: str) -> int:
    """Mã hoá luồng `vao` sang `ra`. Trả số byte bản rõ."""
    salt = os.urandom(16)
    aes = AESGCM(_khoa(mat_khau, salt))
    ra.write(MAGIC + salt)
    tong, i = 0, 0
    sau = vao.read(KHOI)
    while True:
        hien, sau = sau, vao.read(KHOI)
        cuoi = not sau
        nonce = os.urandom(12)
        bm = aes.encrypt(nonce, hien, _aad(salt, i, cuoi))
        ra.write(struct.pack(">I", len(bm)) + nonce + bm)
        tong += len(hien)
        i += 1
        if cuoi:
            return tong


def _doc_du(f: BinaryIO, n: int) -> bytes:
    b = f.read(n)
    if len(b) != n:
        raise LoiGoi("gói bị cắt cụt giữa chừng — chép lại tệp")
    return b


def giai_ma_tung_khoi(vao: BinaryIO, mat_khau: str) -> Iterator[bytes]:
    if vao.read(len(MAGIC)) != MAGIC:
        raise LoiGoi("không phải gói chuyển nhà CSKH (sai định dạng)")
    salt = _doc_du(vao, 16)
    aes = AESGCM(_khoa(mat_khau, salt))
    i = 0
    while True:
        dau = vao.read(4)
        if not dau:
            raise LoiGoi("gói bị cắt cụt — thiếu khối cuối; chép lại tệp")
        if len(dau) != 4:
            raise LoiGoi("gói bị cắt cụt giữa chừng — chép lại tệp")
        (n,) = struct.unpack(">I", dau)
        nonce = _doc_du(vao, 12)
        bm = _doc_du(vao, n)
        for cuoi in (False, True):
            try:
                ban_ro = aes.decrypt(nonce, bm, _aad(salt, i, cuoi))
                break
            except Exception:  # noqa: BLE001 — InvalidTag; thử cờ còn lại
                continue
        else:
            raise LoiGoi("sai mật khẩu hoặc gói đã bị sửa (khối "
                         f"{i} không xác thực được)")
        yield ban_ro
        i += 1
        if cuoi:
            if vao.read(1):
                raise LoiGoi("có dữ liệu thừa sau khối cuối — gói đã bị sửa")
            return


def giai_ma(vao: BinaryIO, ra: BinaryIO, mat_khau: str) -> int:
    tong = 0
    for b in giai_ma_tung_khoi(vao, mat_khau):
        ra.write(b)
        tong += len(b)
    return tong
