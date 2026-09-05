"""
Cấu hình động: giá trị khoá API lấy từ CSDL trước, `.env` sau.

VÌ SAO CÓ LỚP NÀY
-----------------
Khoá model, ERP, GHN từng chỉ đọc từ `.env` một lần lúc khởi động. Đổi khoá
là mở file, sửa tay, khởi động lại; gõ sai một ký tự thì agent im lặng
ngừng trả lời. Dashboard giờ là chỗ nhập khoá, và mọi chỗ cần khoá hỏi
đúng một hàm: `lay("GEMINI_API_KEY")`.

VÌ SAO `lay()` ĐỒNG BỘ
----------------------
Chỗ gọi nằm sâu trong `llm.py`, `erpnext.py`, `ghn.py` — nơi không có
`await` tiện tay. Nên bộ nhớ tiến trình được nạp một lần lúc khởi động
(`nap()`) và cập nhật ngay khi `dat()`/`xoa()`.

KHÔNG BAO GIỜ LỘ GIÁ TRỊ
------------------------
Nhật ký chỉ ghi TÊN khoá. `liet_ke()` trả bốn ký tự cuối cho khoá bí mật.
Giá trị đầy đủ không có đường nào ra khỏi tiến trình.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent import db
from agent.config import settings
from agent.security.credential_vault import (
    CredentialVault,
    InvalidCredentialCiphertext,
    InvalidMasterKeyConfiguration,
    SealedCredential,
    parse_master_keys,
)

PHAM_VI = "cau-hinh"
PROVIDER_HOP_LE = ("gemini_api", "gemini", "anthropic", "vertex")


@dataclass(frozen=True, slots=True)
class MoTa:
    khoa: str
    nhom: str
    nhan: str
    bi_mat: bool
    chon: tuple[str, ...] = ()
    y_nghia: str = ""


# ERP_LOAI và SHIPPING_PROVIDER cố ý VẮNG MẶT: bật ERP thật có thứ tự năm
# bước trong docs/van-hanh.md, và shipping rời "mock" là tạo vận đơn không
# xoá được. Hai công tắc đó ở .env, nơi người ta phải mở file và đọc chú thích.
DANH_MUC: dict[str, MoTa] = {m.khoa: m for m in (
    MoTa("LLM_PROVIDER", "model", "Nhà cung cấp model", False, PROVIDER_HOP_LE,
         "gemini_api: chỉ cần API key từ Google AI Studio. gemini / vertex: cần "
         "dự án GCP và gcloud trên máy. anthropic: Claude trực tiếp."),
    MoTa("GEMINI_API_KEY", "model", "Gemini API key", True,
         y_nghia="Google AI Studio → Get API key. Dùng khi provider là gemini_api."),
    MoTa("ANTHROPIC_API_KEY", "model", "Anthropic API key", True,
         y_nghia="Dùng khi provider là anthropic."),
    MoTa("MODEL_CHAT", "model", "Model trả lời khách", False),
    MoTa("MODEL_HARD", "model", "Model việc khó", False),
    MoTa("MODEL_CHEAP", "model", "Model việc rẻ", False),
    MoTa("ERPNEXT_URL", "erp", "ERPNext URL", False),
    MoTa("ERPNEXT_API_KEY", "erp", "ERPNext API key", True),
    MoTa("ERPNEXT_API_SECRET", "erp", "ERPNext API secret", True),
    MoTa("GHN_TOKEN", "van_chuyen", "GHN token", True),
    MoTa("GHN_SHOP_ID", "van_chuyen", "GHN shop id", False),
)}


class KhoaKhongHopLe(ValueError):
    """Khoá ngoài danh mục, hoặc giá trị không hợp lệ cho khoá đó."""


class VaultChuaSanSang(RuntimeError):
    """Máy chủ chưa có CREDENTIAL_MASTER_KEYS nên không mã hoá được."""


class KhoBiMat:
    """Bảng `cau_hinh_bi_mat`. Tách lớp để test thay bằng kho giả."""

    async def doc_tat_ca(self) -> list[dict]:
        return await db.fetch(
            "SELECT khoa, key_version, nonce, ciphertext, sua_boi, sua_luc, "
            "kiem_luc, kiem_ket_qua FROM cau_hinh_bi_mat"
        )

    async def ghi(self, khoa: str, sealed: SealedCredential, sua_boi: str) -> None:
        await db.execute(
            """
            INSERT INTO cau_hinh_bi_mat
                (khoa, key_version, nonce, ciphertext, sua_boi, sua_luc)
            VALUES ($1, $2, $3, $4, $5, now())
            ON CONFLICT (khoa) DO UPDATE SET
                key_version = EXCLUDED.key_version, nonce = EXCLUDED.nonce,
                ciphertext = EXCLUDED.ciphertext, sua_boi = EXCLUDED.sua_boi,
                sua_luc = now(), kiem_luc = NULL, kiem_ket_qua = NULL
            """,
            khoa, sealed.key_version, sealed.nonce, sealed.ciphertext, sua_boi,
        )

    async def xoa(self, khoa: str) -> None:
        await db.execute("DELETE FROM cau_hinh_bi_mat WHERE khoa = $1", khoa)

    async def ghi_kiem(self, khoa: str, ket_qua: str) -> None:
        await db.execute(
            "UPDATE cau_hinh_bi_mat SET kiem_luc = now(), kiem_ket_qua = $2 "
            "WHERE khoa = $1",
            khoa, ket_qua,
        )


_kho: KhoBiMat = KhoBiMat()
_gia_tri: dict[str, str] = {}
_meta: dict[str, dict[str, Any]] = {}
_log = logging.getLogger("agent.cau_hinh_dong")


# Đường lui .env cho từng khoá, viết TƯỜNG MINH thay vì getattr(settings,
# khoa.lower()): tên trường gõ nhầm thì nổ lúc import chứ không lặng lẽ trả
# rỗng, và tests/test_ra_soat_ma_chet.py soi được rằng mỗi trường cấu hình
# có người đọc.
_DOC_ENV: dict[str, Callable[[], str]] = {
    "LLM_PROVIDER": lambda: settings.llm_provider,
    "GEMINI_API_KEY": lambda: settings.gemini_api_key,
    "ANTHROPIC_API_KEY": lambda: settings.anthropic_api_key,
    "MODEL_CHAT": lambda: settings.model_chat,
    "MODEL_HARD": lambda: settings.model_hard,
    "MODEL_CHEAP": lambda: settings.model_cheap,
    "ERPNEXT_URL": lambda: settings.erpnext_url,
    "ERPNEXT_API_KEY": lambda: settings.erpnext_api_key,
    "ERPNEXT_API_SECRET": lambda: settings.erpnext_api_secret,
    "GHN_TOKEN": lambda: settings.ghn_token,
    "GHN_SHOP_ID": lambda: settings.ghn_shop_id,
}


def _tu_env(khoa: str) -> str:
    return str(_DOC_ENV[khoa]() or "")


def _vault() -> CredentialVault:
    try:
        return CredentialVault(
            parse_master_keys(settings.credential_master_keys),
            active_version=settings.credential_active_key_version,
        )
    except InvalidMasterKeyConfiguration as exc:
        raise VaultChuaSanSang(
            "Máy chủ chưa cấu hình CREDENTIAL_MASTER_KEYS nên không lưu được "
            "khoá. Xem hướng dẫn trong .env.example"
        ) from exc


def vault_san_sang() -> bool:
    try:
        _vault()
        return True
    except VaultChuaSanSang:
        return False


def _pham_vi(khoa: str) -> str:
    return f"{PHAM_VI}:{khoa}"


async def nap() -> None:
    """Nạp toàn bộ bảng vào bộ nhớ. Không bao giờ chặn khởi động."""
    _gia_tri.clear()
    _meta.clear()
    try:
        rows = await _kho.doc_tat_ca()
    except Exception as exc:  # noqa: BLE001 — bảng chưa có thì chạy bằng .env
        # Kèm cả thông điệp, không chỉ tên lớp: "OSError" một mình không nói
        # được là Postgres chưa lên hay bảng chưa migrate, và người đọc log
        # phải đoán. Bí mật không lọt: bộ lọc nhat_ky quét mọi dòng log.
        _log.warning(
            "cau_hinh_dong: không đọc được bảng (%s: %s), dùng .env",
            type(exc).__name__, exc,
        )
        return
    if not rows:
        return
    try:
        vault = _vault()
    except VaultChuaSanSang:
        _log.warning("cau_hinh_dong: có %d khoá trong CSDL nhưng vault chưa cấu hình", len(rows))
        return
    for r in rows:
        try:
            d = vault.decrypt_pham_vi(
                SealedCredential(int(r["key_version"]), r["nonce"], r["ciphertext"]),
                pham_vi=_pham_vi(r["khoa"]),
            )
        except InvalidCredentialCiphertext:
            # Khoá chủ đổi hoặc bản mã hỏng. Không nuốt: san_sang đọc sự kiện
            # này. Nhưng cũng không chặn: các khoá khác vẫn phải nạp được.
            await db.log_event("cau_hinh_api.giai_ma_hong", khoa=r["khoa"])
            continue
        _gia_tri[r["khoa"]] = str(d.get("gia_tri") or "")
        _meta[r["khoa"]] = {
            "sua_boi": r.get("sua_boi"), "sua_luc": r.get("sua_luc"),
            "kiem_luc": r.get("kiem_luc"), "kiem_ket_qua": r.get("kiem_ket_qua"),
        }


def _mo_ta(khoa: str) -> MoTa:
    mo_ta = DANH_MUC.get(khoa)
    if mo_ta is None:
        raise KhoaKhongHopLe(f"khoá {khoa!r} không có trong danh mục")
    return mo_ta


def lay(khoa: str) -> str:
    """Giá trị hiện hành: CSDL trước, `.env` sau, rỗng nếu không đâu có."""
    _mo_ta(khoa)
    v = _gia_tri.get(khoa, "")
    if v:
        return v
    return _tu_env(khoa)


def nguon(khoa: str) -> str:
    _mo_ta(khoa)
    if _gia_tri.get(khoa):
        return "csdl"
    if _tu_env(khoa):
        return "env"
    return "trong"


def kiem_gia_tri(khoa: str, gia_tri: str) -> str:
    mo_ta = _mo_ta(khoa)
    gia_tri = str(gia_tri or "").strip()
    if not gia_tri:
        raise KhoaKhongHopLe(f"{mo_ta.nhan}: giá trị trống")
    if mo_ta.chon and gia_tri not in mo_ta.chon:
        raise KhoaKhongHopLe(f"{mo_ta.nhan}: chỉ nhận {' | '.join(mo_ta.chon)}")
    if khoa.startswith("MODEL_"):
        from agent.core.llm import PRICING

        if gia_tri not in PRICING:
            raise KhoaKhongHopLe(
                f"{mo_ta.nhan}: model {gia_tri!r} không có trong bảng giá; "
                f"nhận {', '.join(sorted(PRICING))}"
            )
    return gia_tri


def _sau_khi_doi(khoa: str) -> None:
    # Client Anthropic được cache theo khoá; đổi khoá mà giữ client cũ là
    # dashboard báo "đã lưu" trong khi model vẫn chạy khoá cũ.
    from agent import nhat_ky
    from agent.core import llm

    llm.xoa_cache_client()
    # Bộ lọc nhật ký nhớ danh sách bí mật một lần rồi dùng mãi. Không quên
    # ở đây thì khoá vừa dán không được che cho tới lần khởi động lại — và
    # đó đúng là lúc nó bị gọi nhiều nhất.
    nhat_ky.quen_bi_mat()


async def dat(khoa: str, gia_tri: str, *, sua_boi: str) -> None:
    gia_tri = kiem_gia_tri(khoa, gia_tri)
    vault = _vault()
    sealed = vault.encrypt_pham_vi({"gia_tri": gia_tri}, pham_vi=_pham_vi(khoa))
    await _kho.ghi(khoa, sealed, sua_boi)
    _gia_tri[khoa] = gia_tri
    _meta[khoa] = {
        "sua_boi": sua_boi, "sua_luc": datetime.now(timezone.utc),
        "kiem_luc": None, "kiem_ket_qua": None,
    }
    # KHÔNG ghi giá trị vào nhật ký, kể cả khoá không bí mật — một danh sách
    # trắng "khoá nào in được" là một chỗ để lần sau thêm nhầm.
    await db.log_event("cau_hinh_api.doi", actor=sua_boi, khoa=khoa)
    _sau_khi_doi(khoa)


async def xoa(khoa: str, *, sua_boi: str) -> None:
    _mo_ta(khoa)
    await _kho.xoa(khoa)
    _gia_tri.pop(khoa, None)
    _meta.pop(khoa, None)
    await db.log_event("cau_hinh_api.xoa", actor=sua_boi, khoa=khoa)
    _sau_khi_doi(khoa)


async def ghi_ket_qua_kiem(khoa: str, ok: bool, chi_tiet: str) -> None:
    _mo_ta(khoa)
    if khoa not in _gia_tri:
        return  # chỉ ghi cho khoá đang lưu trong CSDL
    ket_qua = ("đạt: " if ok else "hỏng: ") + chi_tiet[:200]
    await _kho.ghi_kiem(khoa, ket_qua)
    _meta.setdefault(khoa, {})
    _meta[khoa]["kiem_luc"] = datetime.now(timezone.utc)
    _meta[khoa]["kiem_ket_qua"] = ket_qua


def duoi(gia_tri: str) -> str:
    return "···" + gia_tri[-4:] if len(gia_tri) >= 8 else "···"


def liet_ke() -> list[dict]:
    ra = []
    for mo_ta in DANH_MUC.values():
        v = lay(mo_ta.khoa)
        meta = _meta.get(mo_ta.khoa, {})
        ra.append({
            "khoa": mo_ta.khoa, "nhom": mo_ta.nhom, "nhan": mo_ta.nhan,
            "bi_mat": mo_ta.bi_mat, "chon": list(mo_ta.chon), "y_nghia": mo_ta.y_nghia,
            "da_dat": bool(v), "nguon": nguon(mo_ta.khoa),
            "hien": (duoi(v) if mo_ta.bi_mat else v) if v else "",
            "sua_boi": meta.get("sua_boi"),
            "sua_luc": meta["sua_luc"].isoformat() if meta.get("sua_luc") else None,
            "kiem_luc": meta["kiem_luc"].isoformat() if meta.get("kiem_luc") else None,
            "kiem_ket_qua": meta.get("kiem_ket_qua"),
        })
    return ra
