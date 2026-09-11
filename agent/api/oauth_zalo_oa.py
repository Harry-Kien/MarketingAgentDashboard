"""
Nối Zalo OA bằng OAuth — bù mảnh thiếu cuối cùng của luồng nối kênh.

TRẠNG THÁI TRƯỚC BẢN NÀY
-------------------------
Đo trên mã: Facebook / Instagram / WhatsApp đã có OAuth đủ đường
(`/start` -> `/callback` -> chọn Trang -> tạo tài khoản kênh), Zalo cá nhân
đã có quét QR. Riêng Zalo OA chỉ có `zalo_oa_oauth_url` dùng để LÀM MỚI
token — không có đường cấp quyền lần đầu.

Nghĩa là nối một OA mới phải: vào Zalo Developers, tự bấm cấp quyền, copy
`refresh_token`, dán vào `.env`, khởi động lại máy chủ. Và `.env` chỉ có
MỘT chỗ cho `ZALO_OA_REFRESH_TOKEN`, nên cửa hàng có hai OA thì OA thứ hai
không nối được — một giới hạn không nằm ở Zalo mà nằm ở chỗ ta cất khoá.

ZALO V4 BẮT BUỘC PKCE
----------------------
Khác Meta. Phải sinh `code_verifier` ngẫu nhiên, gửi `code_challenge` =
base64url(sha256(verifier)) ở bước xin quyền, rồi gửi lại chính
`code_verifier` ở bước đổi token.

Verifier phải sống qua hai request và là BÍ MẬT dùng một lần — nên nó nằm
cùng `state` trong một kho trong bộ nhớ, và biến mất cùng lúc.

KHOÁ ĐI VÀO VAULT THEO TỪNG OA, KHÔNG VÀO BẢNG `zalo_oa_token`
---------------------------------------------------------------
Bảng ấy là chỗ cất của OA cấu hình bằng `.env` — một app, một token, toàn
cục. Tài khoản tạo từ đây có credential riêng trong vault, và
`agent/channels/factory.py` đã nối sẵn `on_credentials_rotated` để token
xoay vòng ghi ngược vào đúng chỗ đó.

Ghi cả hai nơi là tạo HAI nguồn sự thật cho một khoá tự đổi mỗi giờ: bản
trong vault xoay, bản trong bảng đứng yên, và thứ đọc nhầm bản đứng yên sẽ
cầm một token đã chết — ngừng gửi được trong im lặng, đúng kiểu hỏng mà
CLAUDE.md xếp đầu bảng.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from agent import db
from agent.config import settings

from .routes import can_quyen

router = APIRouter(prefix="/api/connect/zalo-oa", tags=["oauth-zalo-oa"])

# Một lượt cấp quyền kéo dài chưa tới một phút. Để dài hơn là giữ một bí
# mật dùng một lần sống lâu hơn mức cần thiết.
STATE_SONG_GIAY = 600.0

URL_CAP_QUYEN = "https://oauth.zaloapp.com/v4/oa/permission"
URL_HO_SO_OA = "https://openapi.zalo.me/v2.0/oa/getoa"


class KhoPKCE:
    """
    Giữ `state` và `code_verifier` của các lượt đang dở. Dùng một lần rồi bỏ.

    Không có `state`, kẻ khác dụ được quản trị mở một link callback dựng
    sẵn và hệ thống nối MỘT OA CỦA CHÚNG vào — rồi tin khách đi qua tài
    khoản người lạ. Đó là CSRF, và OAuth sinh ra `state` đúng để chặn.
    """

    def __init__(self) -> None:
        # state -> (hạn, user_id, code_verifier)
        self._cho: dict[str, tuple[float, Any, str]] = {}

    def _don(self) -> None:
        bay_gio = time.time()
        for s in [s for s, (han, _, _) in self._cho.items() if han < bay_gio]:
            self._cho.pop(s, None)

    def tao(self, user_id: Any) -> tuple[str, str]:
        """Trả `(state, code_challenge)` và nhớ verifier + ai đã bấm nút."""
        self._don()
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        self._cho[state] = (time.time() + STATE_SONG_GIAY, user_id, verifier)
        return state, thach_thuc_tu(verifier)

    def nhan(self, state: str) -> tuple[Any, str]:
        """Lấy ra và XOÁ. Callback phát lại lần hai không nối thêm gì nữa."""
        muc = self._cho.pop(state or "", None)
        if muc is None or muc[0] < time.time():
            raise HTTPException(400, (
                "Lượt cấp quyền đã hết hạn hoặc không hợp lệ. "
                "Quay lại dashboard và bấm “Nối Zalo OA” lần nữa."))
        return muc[1], muc[2]


def thach_thuc_tu(verifier: str) -> str:
    """
    code_challenge = base64url(sha256(verifier)), KHÔNG có dấu `=` đệm.

    Tách ra thành hàm để test kiểm được bằng vector tự tính — sai một bước
    ở đây thì Zalo từ chối ở bước đổi token, cách chỗ sai hai request.
    """
    return base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")


_KHO = KhoPKCE()


def _app_id_va_secret() -> tuple[str, str]:
    if not settings.zalo_oa_app_id or not settings.zalo_oa_secret_key:
        raise HTTPException(503, (
            "Chưa cấu hình ZALO_OA_APP_ID và ZALO_OA_SECRET_KEY trong .env. "
            "Đây là thông tin của ỨNG DỤNG Zalo, khác token của từng OA — "
            "khai một lần, rồi nối được nhiều OA bằng nút này."))
    return settings.zalo_oa_app_id, settings.zalo_oa_secret_key


def _goc_cong_khai() -> str:
    goc = (settings.public_base_url or "").rstrip("/")
    if not goc.startswith("https://"):
        raise HTTPException(503, (
            "Zalo chỉ chấp nhận địa chỉ quay về dùng HTTPS. Dựng tunnel hoặc "
            "tên miền trước, rồi đặt PUBLIC_BASE_URL trỏ vào đó. "
            "Chạy: python -m scripts.chay_tunnel"))
    return goc


def _dia_chi_quay_ve() -> str:
    return _goc_cong_khai() + "/api/connect/zalo-oa/callback"


def dung_url_cap_quyen(*, app_id: str, redirect_uri: str, state: str,
                       code_challenge: str) -> str:
    return URL_CAP_QUYEN + "?" + urlencode({
        "app_id": app_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
    })


_CSS = (
    "body{font:15px/1.65 system-ui,-apple-system,sans-serif;margin:40px auto;"
    "max-width:60ch;padding:0 16px;color:#18181b}"
    "h2{margin:0 0 14px}"
    "code{background:#f4f4f5;padding:2px 6px;border-radius:4px;"
    "font:13px ui-monospace,monospace;word-break:break-all}"
    ".canh{border-left:3px solid #f59e0b;padding:2px 0 2px 14px;margin:18px 0}"
)


def _trang(tieu_de: str, than: str) -> HTMLResponse:
    """
    Trang kết quả hiện trong cửa sổ OAuth vừa mở.

    KHÔNG in token hay mã lỗi thô ra đây — người dùng hay chụp màn hình
    trang này để hỏi, và ảnh chụp thì đi khắp nơi.

    Tự làm mới cửa sổ cha nhưng KHÔNG tự đóng: trang này còn một địa chỉ
    webhook người dùng phải copy. Đóng hộ họ là làm mất thứ duy nhất khiến
    chiều nhận tin chạy được.
    """
    return HTMLResponse(
        "<!doctype html><meta charset='utf-8'>"
        f"<style>{_CSS}</style><h2>{tieu_de}</h2>{than}"
        "<p><button onclick='window.close()'>Đóng cửa sổ này</button></p>"
        "<script>setTimeout(function(){try{window.opener&&"
        "window.opener.location.reload()}catch(e){}},500)</script>")


@router.get("/start")
async def zalo_oa_start(
    user: dict = Depends(can_quyen("kenh.noi")),
) -> dict[str, Any]:
    """
    Địa chỉ màn hình cấp quyền của Zalo để dashboard mở ra.

    Không tự chuyển hướng: dashboard mở nó trong cửa sổ mới và giữ nguyên
    trang hiện tại, để lúc quay về người dùng không mất ngữ cảnh.
    """
    app_id, _ = _app_id_va_secret()
    state, thach_thuc = _KHO.tao(user["id"])
    return {"url": dung_url_cap_quyen(
        app_id=app_id, redirect_uri=_dia_chi_quay_ve(),
        state=state, code_challenge=thach_thuc)}


async def _doi_token(code: str, verifier: str) -> dict[str, Any]:
    app_id, secret = _app_id_va_secret()
    async with httpx.AsyncClient(timeout=20) as khach:
        tra = await khach.post(
            settings.zalo_oa_oauth_url,
            headers={"secret_key": secret},
            data={"code": code, "app_id": app_id,
                  "grant_type": "authorization_code",
                  "code_verifier": verifier},
        )
    d: dict[str, Any] = {}
    try:
        d = tra.json() or {}
    except ValueError:
        pass
    # Zalo trả HTTP 200 kèm thân lỗi — đây là cách lỗi Zalo OA sống lâu
    # trong repo này. Coi 200 là thành công là nối một tài khoản không có
    # khoá, và nó chỉ lộ ra ở tin khách đầu tiên không gửi được.
    if not d.get("refresh_token"):
        await db.log_event("zalo_oa.oauth_loi", actor="system",
                           ma=str(d.get("error") or "")[:40])
        raise HTTPException(502, (
            "Zalo không đổi được mã lấy token. Kiểm lại địa chỉ callback đã "
            "khai trong Zalo Developers có khớp PUBLIC_BASE_URL không."))
    return d


async def _ho_so_oa(access_token: str) -> dict[str, Any]:
    """
    Tên và id của OA vừa cấp quyền.

    `oa_id` KHÔNG phải đồ trang trí: nó là `external_account_id`, thứ giữ
    cho nối lại lần hai là cập nhật khoá chứ không phải đẻ thêm một tài
    khoản trùng. Nên hỏng ở đây thì dừng, không nối bừa.
    """
    async with httpx.AsyncClient(timeout=15) as khach:
        tra = await khach.get(URL_HO_SO_OA,
                              headers={"access_token": access_token})
    try:
        data = (tra.json() or {}).get("data") or {}
    except ValueError:
        data = {}
    if not data.get("oa_id"):
        raise HTTPException(502, (
            "Zalo cấp quyền xong nhưng không trả về thông tin OA. "
            "Kiểm quyền của ứng dụng trong Zalo Developers rồi thử lại."))
    return data


def _kho_tai_khoan():
    """Service tài khoản kênh + vault. Dựng muộn để lỗi cấu hình khoá nổ ở đây."""
    from agent.omnichannel.account_repository import PostgresAccountRepository
    from agent.omnichannel.account_service import ChannelAccountService
    from agent.security.credential_vault import CredentialVault, parse_master_keys

    try:
        vault = CredentialVault(
            parse_master_keys(settings.credential_master_keys),
            active_version=settings.credential_active_key_version,
        )
    except ValueError as exc:
        raise HTTPException(503, (
            "Kho credential chưa sẵn sàng: thiếu CREDENTIAL_MASTER_KEYS. "
            "Khoá của OA không có chỗ cất an toàn nên không nối."
        )) from exc
    repo = PostgresAccountRepository()
    return repo, ChannelAccountService(repo, vault)


async def _luu_tai_khoan(*, oa_id: str, ten: str, refresh_token: str,
                         nguoi_bam: Any) -> tuple[UUID, bool]:
    """
    Tạo tài khoản kênh cho OA, hoặc thay khoá nếu OA đã nối trước đó.

    Trả `(account_id, là_tài_khoản_mới)`.

    Nối lại một OA đã có PHẢI là thay khoá, không phải tạo bản sao: mỗi OA
    có một đường webhook riêng theo `account_id`, nên tài khoản thứ hai
    nghĩa là địa chỉ webhook đang khai ở Zalo trỏ vào bản cũ — bản có khoá
    đã hết hạn. Gửi được, nhận không được, và không có gì báo.
    """
    from agent.omnichannel.account_service import (
        AccountActor, CreateAccountCommand,
    )
    from agent.omnichannel.accounts import Channel

    app_id, secret = _app_id_va_secret()
    repo, service = _kho_tai_khoan()

    # NGƯỜI THẬT đã bấm nút. `account_memberships.user_id` có khoá ngoại tới
    # `nguoi_dung`; một id bịa làm mọi lượt tạo chết vì ForeignKeyViolation.
    #
    # `kenh.sua` cấp thẳng ở đây là hệ quả tất yếu của `kenh.noi` mà endpoint
    # `/start` đã kiểm, không phải đường tắt.
    actor = AccountActor(
        user_id=nguoi_bam if isinstance(nguoi_bam, UUID) else UUID(str(nguoi_bam)),
        quyen=frozenset({"kenh.sua"}),
    )
    khoa = {"app_id": app_id, "secret_key": secret,
            "refresh_token": refresh_token}

    cu = await repo.find_by_external(Channel.ZALO_OA, oa_id)
    if cu is not None:
        await service.rotate_credentials(cu.id, khoa, actor=actor)
        return cu.id, False

    moi = await service.create_account(
        CreateAccountCommand(
            channel=Channel.ZALO_OA,
            display_name=ten,
            external_account_id=oa_id,
            capabilities={"send_text": True, "receive_message": True},
            metadata={"nguon": "oauth"},
            credentials=khoa,
        ),
        actor=actor,
    )
    return moi.id, True


@router.get("/callback")
async def zalo_oa_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
) -> HTMLResponse:
    """
    Zalo gọi vào đây sau khi người dùng cấp quyền.

    KHÔNG đòi đăng nhập dashboard: Zalo gọi tới và không mang cookie phiên
    của ta. Chốt thay thế là `state` dùng một lần, sinh ra ở `/start` — nơi
    VẪN đòi quyền `kenh.noi`. Không có state hợp lệ thì callback từ chối,
    nên mở đường này không mở thêm quyền gì.
    """
    if error:
        return _trang("Chưa nối được",
                      "<p>Zalo báo lỗi cấp quyền. Thử lại từ dashboard.</p>")
    if not code:
        return _trang("Chưa nối được",
                      "<p>Zalo không trả về mã cấp quyền.</p>")

    nguoi_bam, verifier = _KHO.nhan(state)
    token = await _doi_token(code, verifier)
    ho_so = await _ho_so_oa(str(token.get("access_token") or ""))

    oa_id = str(ho_so["oa_id"])
    ten = str(ho_so.get("name") or "").strip() or f"Zalo OA {oa_id}"

    account_id, moi = await _luu_tai_khoan(
        oa_id=oa_id, ten=ten,
        refresh_token=str(token["refresh_token"]),
        nguoi_bam=nguoi_bam,
    )
    await db.log_event("zalo_oa.oauth", actor=str(nguoi_bam),
                       oa_id=oa_id, account_id=str(account_id), moi=moi)

    webhook = f"{_goc_cong_khai()}/webhook/native/zalo-oa/{account_id}"
    return _trang(
        ("Đã nối “%s”" % ten) if moi else ("Đã cấp lại khoá cho “%s”" % ten),
        # Zalo KHÔNG có API đăng ký webhook — chỗ này buộc phải làm tay, và
        # thiếu nó thì gửi đi được mà tin khách không vào. Nói thẳng ra đây
        # thay vì để người dùng phát hiện bằng một khách không được trả lời.
        "<p>Khoá đã cất vào kho mã hoá, không nằm trong <code>.env</code> — "
        "Zalo xoay vòng nó mỗi giờ nên máy phải tự ghi lấy.</p>"
        "<div class='canh'><p><b>Còn một bước làm tay.</b> Zalo không cho "
        "đăng ký webhook bằng API. Vào Zalo Developers → OA của bạn → "
        "<i>Webhook</i>, dán đúng địa chỉ này:</p>"
        f"<p><code>{webhook}</code></p>"
        "<p>Bỏ bước này thì OA gửi đi được nhưng <b>tin khách không vào</b>, "
        "và không có dấu hiệu nào báo.</p></div>"
        "<p>Xong thì vào <b>Kết nối</b> → <b>Xác minh provider</b> để kiểm.</p>")
