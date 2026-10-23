"""
Xác thực hai bước bằng TOTP (RFC 6238) — Google Authenticator, Authy, 1Password…

BA RÀNG BUỘC, MỖI CÁI MỘT CÁCH HỎNG
----------------------------------
1. Bí mật mã hoá AES-GCM, AAD gắn với id người dùng (0032_hai_buoc.sql).
   Lộ bản sao lưu CSDL không lộ được bí mật để sinh mã.
2. Mỗi bước 30 giây chỉ dùng được MỘT lần (`totp_buoc_cuoi`). Không chặn thì
   kẻ đứng giữa nhìn thấy mã là dùng lại được ngay trong cùng 30 giây.
3. Mã dự phòng băm scrypt và dùng một lần. Mất điện thoại không được thành
   mất tài khoản — nhưng mã dự phòng cũng không được thành mật khẩu thứ hai
   dùng mãi.

Bật 2FA là hai bước: `bat_dau` sinh bí mật (chưa bật), `xac_nhan` kiểm một
mã thật từ app rồi mới bật. Bật ngay khi sinh là khoá người dùng ra ngoài
nếu họ quét QR lỗi.
"""
from __future__ import annotations

import secrets
import time
from uuid import UUID

import pyotp

from agent import db
from agent.config import settings
from agent.core.xac_thuc import bam_mat_khau, kiem_mat_khau
from agent.security.credential_vault import (
    CredentialVault,
    SealedCredential,
    parse_master_keys,
)

BUOC_GIAY = 30
SO_MA_DU_PHONG = 8


def _pham_vi(uid: UUID | str) -> str:
    return f"totp:{uid}"


def _vault() -> CredentialVault:
    return CredentialVault(parse_master_keys(settings.credential_master_keys),
                           active_version=settings.credential_active_key_version)


def _buoc(t: float | None = None) -> int:
    return int((time.time() if t is None else t) // BUOC_GIAY)


async def bat_dau(uid: UUID, ten: str) -> str:
    """Sinh bí mật mới (CHƯA bật). Trả URI otpauth:// để vẽ QR."""
    bi_mat = pyotp.random_base32()
    niem = _vault().encrypt_pham_vi({"bi_mat": bi_mat}, pham_vi=_pham_vi(uid))
    await db.execute(
        "UPDATE nguoi_dung SET totp_phien_ban = $2, totp_nonce = $3, totp_ma_hoa = $4, "
        "hai_buoc_bat = false, totp_buoc_cuoi = NULL WHERE id = $1",
        uid, niem.key_version, niem.nonce, niem.ciphertext)
    nha = settings.public_base_url.split("//")[-1].split("/")[0] or "CSKH"
    return pyotp.TOTP(bi_mat).provisioning_uri(name=ten, issuer_name=nha)


def _giai(nd: dict) -> str | None:
    if not nd.get("totp_ma_hoa"):
        return None
    niem = SealedCredential(nd["totp_phien_ban"], bytes(nd["totp_nonce"]),
                            bytes(nd["totp_ma_hoa"]))
    return _vault().decrypt_pham_vi(niem, pham_vi=_pham_vi(nd["id"]))["bi_mat"]


def _buoc_khop(bi_mat: str, ma: str, t: float | None = None) -> int | None:
    """Bước 30 giây mà mã khớp (cho lệch ±1 bước — đồng hồ điện thoại lệch)."""
    ma = "".join(ch for ch in (ma or "") if ch.isdigit())
    if len(ma) != 6:
        return None
    totp = pyotp.TOTP(bi_mat)
    b = _buoc(t)
    for lech in (0, -1, 1):
        if secrets.compare_digest(totp.at((b + lech) * BUOC_GIAY), ma):
            return b + lech
    return None


async def _doc(uid: UUID) -> dict | None:
    return await db.fetchrow(
        "SELECT id, hai_buoc_bat, totp_phien_ban, totp_nonce, totp_ma_hoa, "
        "ma_du_phong, totp_buoc_cuoi FROM nguoi_dung WHERE id = $1", uid)


async def kiem(uid: UUID, ma: str, t: float | None = None) -> bool:
    """
    Mã TOTP hoặc mã dự phòng có hợp lệ không. Dùng được thì ĐÁNH DẤU đã dùng.
    """
    nd = await _doc(uid)
    if nd is None:
        return False
    bi_mat = _giai(dict(nd))
    if bi_mat:
        b = _buoc_khop(bi_mat, ma, t)
        if b is not None:
            # Chỉ nhận bước MỚI HƠN bước đã dùng — cập nhật có điều kiện để
            # hai yêu cầu đồng thời cùng mã chỉ một cái thắng.
            r = await db.fetchrow(
                "UPDATE nguoi_dung SET totp_buoc_cuoi = $2 WHERE id = $1 "
                "AND (totp_buoc_cuoi IS NULL OR totp_buoc_cuoi < $2) RETURNING id", uid, b)
            return r is not None
    ma_sach = (ma or "").strip().replace("-", "").lower()
    for i, bam in enumerate(nd["ma_du_phong"] or []):
        if kiem_mat_khau(ma_sach, bam):
            con_lai = [x for j, x in enumerate(nd["ma_du_phong"]) if j != i]
            await db.execute("UPDATE nguoi_dung SET ma_du_phong = $2 WHERE id = $1",
                             uid, con_lai)
            await db.log_event("auth.dung_ma_du_phong", ref_id=uid, con_lai=len(con_lai))
            return True
    return False


async def xac_nhan(uid: UUID, ma: str) -> list[str] | None:
    """Kiểm mã đầu tiên rồi BẬT. Trả mã dự phòng (hiện MỘT lần), None nếu sai."""
    nd = await _doc(uid)
    if nd is None or not nd["totp_ma_hoa"]:
        return None
    bi_mat = _giai(dict(nd))
    if bi_mat is None:
        return None
    b = _buoc_khop(bi_mat, ma)
    if b is None:
        return None
    ma_du_phong = [secrets.token_hex(5) for _ in range(SO_MA_DU_PHONG)]
    await db.execute(
        "UPDATE nguoi_dung SET hai_buoc_bat = true, totp_buoc_cuoi = $2, ma_du_phong = $3 "
        "WHERE id = $1", uid, b, [bam_mat_khau(m) for m in ma_du_phong])
    await db.log_event("auth.bat_hai_buoc", ref_id=uid)
    return [f"{m[:5]}-{m[5:]}" for m in ma_du_phong]


async def tat(uid: UUID) -> None:
    await db.execute(
        "UPDATE nguoi_dung SET hai_buoc_bat = false, totp_phien_ban = NULL, totp_nonce = NULL, "
        "totp_ma_hoa = NULL, ma_du_phong = '{}', totp_buoc_cuoi = NULL WHERE id = $1", uid)
    await db.log_event("auth.tat_hai_buoc", ref_id=uid)
