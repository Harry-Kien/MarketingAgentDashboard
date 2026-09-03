"""API quản trị nhiều tài khoản trên từng kênh native."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from agent import db
from agent.config import settings
from agent.channels.zalo_personal import ZaloPersonalAdapter
from agent.omnichannel.credential_loader import VaultCredentialLoader
from agent.omnichannel.account_verification import (
    NativeConnectionVerifier,
    NativeVerificationAdapterFactory,
)
from agent.omnichannel.account_repository import PostgresAccountRepository
from agent.omnichannel.account_service import (
    AccountActor,
    AccountAlreadyExists,
    AccountDisabled,
    AccountNotFound,
    ChannelAccountService,
    CreateAccountCommand,
)
from agent.omnichannel.accounts import Channel
from agent.omnichannel.bi_mat_may_chu import (
    ThieuBiMatMayChu,
    bo_sung_bi_mat_may_chu,
)
from agent.security.credential_vault import (
    CredentialVault,
    InvalidMasterKeyConfiguration,
    parse_master_keys,
)

from .routes import bat_buoc_dang_nhap, bat_buoc_quan_tri


router = APIRouter(prefix="/api/channel-accounts", tags=["channel-accounts"])


class CreateChannelAccountIn(BaseModel):
    channel: Channel
    display_name: str = Field(min_length=1, max_length=120)
    external_account_id: str | None = Field(default=None, max_length=240)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] | None = None


class RotateCredentialsIn(BaseModel):
    credentials: dict[str, Any]


def get_account_repository() -> PostgresAccountRepository:
    return PostgresAccountRepository()


def get_account_service(
    repository: PostgresAccountRepository = Depends(get_account_repository),
) -> ChannelAccountService:
    try:
        keys = parse_master_keys(settings.credential_master_keys)
        vault = CredentialVault(
            keys,
            active_version=settings.credential_active_key_version,
        )
    except InvalidMasterKeyConfiguration as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Kho bí mật của tài khoản kênh chưa được cấu hình an toàn",
        ) from exc
    return ChannelAccountService(repository, vault)


def get_connection_verifier(
    repository: PostgresAccountRepository = Depends(get_account_repository),
) -> NativeConnectionVerifier:
    try:
        vault = CredentialVault(
            parse_master_keys(settings.credential_master_keys),
            active_version=settings.credential_active_key_version,
        )
    except InvalidMasterKeyConfiguration as exc:
        raise HTTPException(503, "Kho credential native chưa sẵn sàng") from exc
    loader = VaultCredentialLoader(repository, vault)
    return NativeConnectionVerifier(
        repository,
        NativeVerificationAdapterFactory(loader),
    )


def _loader(repository: PostgresAccountRepository) -> VaultCredentialLoader:
    """Mở vault. Lỗi cấu hình khoá thì nói rõ, đừng để 500 trắng."""
    try:
        vault = CredentialVault(
            parse_master_keys(settings.credential_master_keys),
            active_version=settings.credential_active_key_version,
        )
    except InvalidMasterKeyConfiguration as exc:
        raise HTTPException(503, "Kho credential native chưa sẵn sàng") from exc
    return VaultCredentialLoader(repository, vault)


def _actor(user: dict) -> AccountActor:
    return AccountActor(user_id=UUID(str(user["id"])), role=user["vai_tro"])


def _raise_public(exc: Exception) -> None:
    if isinstance(exc, AccountNotFound):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, AccountAlreadyExists):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, AccountDisabled):
        raise HTTPException(409, str(exc)) from exc
    raise exc


@router.get("")
async def list_accounts(
    user: dict = Depends(bat_buoc_dang_nhap),
    repository: PostgresAccountRepository = Depends(get_account_repository),
) -> list[dict[str, Any]]:
    accounts = await repository.list_for_user(
        UUID(str(user["id"])),
        is_admin=user["vai_tro"] == "quan_tri",
    )
    return [
        account.to_public(
            has_credentials=await repository.has_credentials(account.id)
        )
        for account in accounts
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_account(
    body: CreateChannelAccountIn,
    user: dict = Depends(bat_buoc_quan_tri),
    service: ChannelAccountService = Depends(get_account_service),
) -> dict[str, Any]:
    if body.channel.value.startswith("legacy_") or body.channel in {
        Channel.LEGACY_ZALOCRM,
        Channel.LEGACY_CHATWOOT,
        Channel.LEGACY_MESSENGER,
    }:
        raise HTTPException(422, "Không thể tạo mới kết nối legacy")
    # Phần credential thuộc về MÁY CHỦ do máy chủ điền, người dùng không
    # phải đi chép từ `.env`. Xem agent/omnichannel/bi_mat_may_chu.py
    try:
        credentials = bo_sung_bi_mat_may_chu(body.channel, body.credentials)
    except ThieuBiMatMayChu as exc:
        raise HTTPException(503, str(exc)) from exc

    try:
        account = await service.create_account(
            CreateAccountCommand(
                channel=body.channel,
                display_name=body.display_name,
                external_account_id=body.external_account_id,
                capabilities=body.capabilities,
                metadata=body.metadata,
                credentials=credentials or None,
            ),
            actor=_actor(user),
        )
    except (AccountAlreadyExists, AccountDisabled, AccountNotFound) as exc:
        _raise_public(exc)
    return account.to_public(has_credentials=bool(credentials))


@router.get("/{account_id}")
async def get_account(
    account_id: UUID,
    user: dict = Depends(bat_buoc_dang_nhap),
    repository: PostgresAccountRepository = Depends(get_account_repository),
) -> dict[str, Any]:
    allowed = await repository.list_for_user(
        UUID(str(user["id"])),
        is_admin=user["vai_tro"] == "quan_tri",
    )
    account = next((item for item in allowed if item.id == account_id), None)
    if account is None:
        raise HTTPException(404, "Không tìm thấy tài khoản kênh")
    return account.to_public(
        has_credentials=await repository.has_credentials(account.id)
    )


@router.put("/{account_id}/credentials", status_code=status.HTTP_204_NO_CONTENT)
async def rotate_credentials(
    account_id: UUID,
    body: RotateCredentialsIn,
    user: dict = Depends(bat_buoc_quan_tri),
    service: ChannelAccountService = Depends(get_account_service),
    repository: PostgresAccountRepository = Depends(get_account_repository),
) -> Response:
    # Đổi credential mà KHÔNG bổ sung lại phần của máy chủ là ghi đè một
    # secret đang đúng bằng chuỗi rỗng: tài khoản vẫn xanh trên dashboard,
    # chỉ có sidecar là im lặng từ chối mọi lệnh kể từ đó.
    account = await repository.get(account_id)
    if account is None:
        raise HTTPException(404, "Không tìm thấy tài khoản kênh")
    try:
        credentials = bo_sung_bi_mat_may_chu(account.channel, body.credentials)
    except ThieuBiMatMayChu as exc:
        raise HTTPException(503, str(exc)) from exc

    try:
        await service.rotate_credentials(
            account_id,
            credentials,
            actor=_actor(user),
        )
    except (AccountNotFound, AccountDisabled) as exc:
        _raise_public(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{account_id}/disable")
async def disable_account(
    account_id: UUID,
    user: dict = Depends(bat_buoc_quan_tri),
    service: ChannelAccountService = Depends(get_account_service),
    repository: PostgresAccountRepository = Depends(get_account_repository),
) -> dict[str, Any]:
    try:
        account = await service.disable_account(account_id, actor=_actor(user))
    except (AccountNotFound, AccountDisabled) as exc:
        _raise_public(exc)
    return account.to_public(
        has_credentials=await repository.has_credentials(account.id)
    )


@router.post("/{account_id}/enable")
async def enable_account(
    account_id: UUID,
    user: dict = Depends(bat_buoc_quan_tri),
    service: ChannelAccountService = Depends(get_account_service),
) -> dict[str, Any]:
    try:
        account = await service.enable_account(account_id, actor=_actor(user))
    except (AccountNotFound, AccountDisabled) as exc:
        _raise_public(exc)
    return account.to_public(has_credentials=True)


# Bảng giữ dấu vết của KHÁCH. Xoá tài khoản kênh không được đụng tới chúng,
# và lược đồ đã canh việc đó bằng `ON DELETE RESTRICT`.
#
#   conversations        hội thoại đã diễn ra
#   contact_points       danh tính khách trên kênh đó
#   outbox_jobs          tin đang chờ gửi
#   webhook_deliveries   webhook đã nhận, dùng để chống trùng
#
# Ta hỏi TRƯỚC thay vì để Postgres ném lỗi ràng buộc, vì thông điệp của
# Postgres nói tên constraint chứ không nói "còn 12 hội thoại". Người vận
# hành cần biết CÁI GÌ đang giữ, để chọn giữa xoá và tạm ngắt.
_BANG_GIU = (
    ("conversations", "account_id", "hội thoại"),
    ("contact_points", "channel_account_id", "danh tính khách"),
    ("outbox_jobs", "account_id", "tin đang chờ gửi"),
    ("webhook_deliveries", "account_id", "webhook đã nhận"),
)


async def _dang_giu(account_id: UUID) -> list[str]:
    """Những gì đang giữ tài khoản này lại, viết bằng tiếng người."""
    giu: list[str] = []
    for bang, cot, nhan in _BANG_GIU:
        r = await db.fetchrow(
            f"SELECT count(*) AS n FROM {bang} WHERE {cot} = $1", account_id
        )
        n = int(r["n"]) if r else 0
        if n:
            giu.append(f"{n} {nhan}")
    return giu


@router.get("/{account_id}/co-xoa-duoc")
async def kiem_xoa_duoc(
    account_id: UUID,
    _: dict = Depends(bat_buoc_quan_tri),
) -> dict[str, Any]:
    """
    Xem trước: xoá được hay không, và nếu không thì vì sao.

    Có đường xem trước riêng để dashboard nói thẳng trong hộp thoại xác
    nhận, thay vì để người dùng bấm Xoá rồi nhận một lỗi.
    """
    giu = await _dang_giu(account_id)
    return {"xoa_duoc": not giu, "dang_giu": giu}


@router.delete("/{account_id}")
async def xoa_tai_khoan(
    account_id: UUID,
    user: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresAccountRepository = Depends(get_account_repository),
) -> dict[str, Any]:
    """
    Xoá hẳn một tài khoản kênh.

    KHÔNG BAO GIỜ XOÁ LỊCH SỬ KHÁCH. Tài khoản đã có hội thoại thì từ chối
    xoá và bảo người vận hành dùng "Tạm ngắt" — hội thoại cũ là bằng chứng
    của cửa hàng, và một nút dọn dẹp giao diện không được phép xoá nó.

    Cái ĐƯỢC xoá theo (lược đồ khai `ON DELETE CASCADE`): credential, sự
    kiện sức khoẻ, phân quyền, luật định tuyến, SLA, inbox_events. Trong đó
    credential là thứ QUAN TRỌNG phải đi: để lại bí mật của một tài khoản
    không còn dùng là để lại một chiếc chìa khoá không ai canh.
    """
    account = await repository.get(account_id)
    if account is None:
        raise HTTPException(404, "Không tìm thấy tài khoản kênh")

    giu = await _dang_giu(account_id)
    if giu:
        raise HTTPException(
            409,
            f"Không xoá được: còn {', '.join(giu)}. Lịch sử khách không bị "
            "xoá theo tài khoản. Dùng \"Tạm ngắt\" để ngừng kênh mà vẫn giữ "
            "dữ liệu.",
        )

    # Ghi nhật ký TRƯỚC khi xoá. Ghi sau thì lần xoá thành công cuối cùng
    # có thể không để lại dấu vết nào nếu tiến trình chết giữa chừng — và
    # đúng lúc ấy là lúc người ta cần biết ai đã xoá cái gì.
    await db.log_event(
        "kenh.xoa_tai_khoan",
        # `_actor()` trả về AccountActor — đúng cho `service.*`, SAI cho
        # `db.log_event`: cột `events.actor` là TEXT và asyncpg từ chối một
        # đối tượng. Chép khuôn từ dòng `disable_account` ngay bên trên là
        # rơi thẳng vào bẫy này.
        actor=user["ten_dang_nhap"],
        ref_id=account_id,      # cột uuid — str() cũng bị từ chối
        channel=str(account.channel.value if hasattr(account.channel, "value")
                    else account.channel),
        display_name=account.display_name or "",
    )
    await db.execute("DELETE FROM channel_accounts WHERE id = $1", account_id)
    return {"da_xoa": str(account_id)}


@router.get("/{account_id}/health")
async def account_health(
    account_id: UUID,
    user: dict = Depends(bat_buoc_dang_nhap),
    repository: PostgresAccountRepository = Depends(get_account_repository),
) -> dict[str, Any]:
    allowed = await repository.list_for_user(
        UUID(str(user["id"])),
        is_admin=user["vai_tro"] == "quan_tri",
    )
    if not any(account.id == account_id for account in allowed):
        raise HTTPException(404, "Không tìm thấy tài khoản kênh")
    return {"latest": await repository.latest_health(account_id)}


@router.post("/{account_id}/verify")
async def verify_account_connection(
    account_id: UUID,
    user: dict = Depends(bat_buoc_quan_tri),
    verifier: NativeConnectionVerifier = Depends(get_connection_verifier),
) -> dict[str, Any]:
    try:
        result = await verifier.verify(
            account_id,
            actor_id=UUID(str(user["id"])),
        )
    except AccountNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "ok": result.ok,
        "code": result.code,
        "external_account_id": result.external_account_id,
        "detail": result.detail,
    }


async def _zalo_personal_adapter(
    account_id: UUID,
    repository: PostgresAccountRepository,
) -> tuple[ZaloPersonalAdapter, dict[str, Any]]:
    account = await repository.get(account_id)
    if account is None or account.channel != Channel.ZALO_PERSONAL:
        raise HTTPException(404, "Không tìm thấy tài khoản Zalo cá nhân")
    try:
        vault = CredentialVault(
            parse_master_keys(settings.credential_master_keys),
            active_version=settings.credential_active_key_version,
        )
    except InvalidMasterKeyConfiguration as exc:
        raise HTTPException(503, "Kho credential native chưa sẵn sàng") from exc
    credentials = await VaultCredentialLoader(repository, vault).load(account_id)
    if not credentials:
        raise HTTPException(409, "Tài khoản chưa có cấu hình sidecar")
    return (
        ZaloPersonalAdapter(account_id=account_id, credentials=credentials),
        credentials,
    )


@router.post("/{account_id}/zalo-personal/qr", status_code=202)
async def start_zalo_personal_qr(
    account_id: UUID,
    _: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresAccountRepository = Depends(get_account_repository),
) -> dict[str, Any]:
    adapter, _credentials = await _zalo_personal_adapter(account_id, repository)
    try:
        return await adapter.start_qr()
    finally:
        await adapter.aclose()


@router.post("/{account_id}/zalo-personal/restore")
async def restore_zalo_personal_session(
    account_id: UUID,
    _: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresAccountRepository = Depends(get_account_repository),
) -> dict[str, Any]:
    adapter, credentials = await _zalo_personal_adapter(account_id, repository)
    session = credentials.get("session")
    if not isinstance(session, dict) or not session:
        await adapter.aclose()
        raise HTTPException(409, "Chưa có session đã mã hóa để khôi phục")
    try:
        return await adapter.restore_session(session)
    finally:
        await adapter.aclose()


@router.get("/{account_id}/zalo-personal/status")
async def zalo_personal_status(
    account_id: UUID,
    _: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresAccountRepository = Depends(get_account_repository),
) -> dict[str, Any]:
    adapter, _credentials = await _zalo_personal_adapter(account_id, repository)
    try:
        return await adapter.status()
    finally:
        await adapter.aclose()


@router.get("/{account_id}/verify-token")
async def doc_verify_token(
    account_id: UUID,
    _: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresAccountRepository = Depends(get_account_repository),
) -> dict[str, Any]:
    """
    Đọc verify token của một tài khoản Meta để dán sang Meta.

    VÌ SAO RIÊNG TRƯỜNG NÀY ĐƯỢC RA KHỎI VAULT
    -------------------------------------------
    Ba loại bí mật của một tài khoản Meta không cùng mức nhạy cảm:

      access_token  -> đọc tin khách và nhắn thay Trang. Lộ là mất Trang.
      app_secret    -> giả mạo chữ ký webhook. Lộ là bị bơm tin giả.
      verify_token  -> chuỗi Meta dội lại khi bắt tay. Tự nó không mở gì.

    Verify token còn PHẢI được người vận hành dán sang Meta bằng tay. Giấu nó
    không tăng an toàn — chỉ khiến tính năng nối kênh bế tắc ở bước cuối, sau
    khi người ta đã làm xong toàn bộ phần khó.

    Endpoint RIÊNG cho MỘT trường, không thêm vào `to_public()`: ở đó mọi
    trường đi ra cùng lúc, và lần sau ai thêm trường mới là lọt luôn.
    """
    account = await repository.get(account_id)
    if account is None:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    if account.channel not in {
        Channel.FACEBOOK,
        Channel.INSTAGRAM,
        Channel.WHATSAPP,
    }:
        raise HTTPException(422, "Kênh này không dùng verify token")

    credentials = await _loader(repository).load(account_id) or {}
    gia_tri = str(credentials.get("verify_token") or "")
    if not gia_tri:
        raise HTTPException(
            409,
            "Tài khoản chưa có verify token. Nối lại bằng đăng nhập Facebook.",
        )
    return {"verify_token": gia_tri}


KENH_META = {Channel.FACEBOOK, Channel.INSTAGRAM}


@router.post("/{account_id}/dang-ky-webhook")
async def dang_ky_webhook(
    account_id: UUID,
    _user: dict = Depends(bat_buoc_quan_tri),
    repository: PostgresAccountRepository = Depends(get_account_repository),
) -> dict[str, Any]:
    """
    Đăng ký một Trang ĐÃ nối vào webhook của app.

    VÌ SAO CÓ ĐƯỜNG RIÊNG THAY VÌ CHỈ LÀM TRONG OAUTH
    -------------------------------------------------
    Những Trang nối trước khi có bước đăng ký vẫn đang không nhận được tin,
    và không có gì trên màn hình nói ra điều đó. Bắt người dùng gỡ ra nối
    lại là mất lịch sử hội thoại của chính những Trang đó.

    Còn dùng được khi Meta huỷ đăng ký — điều họ làm khi app đổi trạng thái
    duyệt hoặc quyền bị thu hồi.
    """
    from agent.channels.dang_ky_webhook_meta import dang_ky_webhook_trang

    account = await repository.get(account_id)
    if account is None or account.channel not in KENH_META:
        raise HTTPException(404, "Không tìm thấy tài khoản Meta")

    creds = await _loader(repository).load(account_id) or {}
    page_id = str(account.external_account_id or "")
    ok, ly_do = await dang_ky_webhook_trang(
        page_id=page_id,
        page_token=str(creds.get("access_token") or ""),
    )
    if not ok:
        await db.log_event(
            "channel.dang_ky_webhook_loi", actor="admin",
            trang=account.display_name[:80], error=ly_do,
        )
        # 502 chứ không 200-kèm-cờ-false: chỗ gọi phía dashboard đã có sẵn
        # đường hiện lỗi đỏ, còn 200 thì nó báo xanh.
        raise HTTPException(502, "Đăng ký webhook thất bại: " + ly_do)

    await db.log_event(
        "channel.dang_ky_webhook", actor="admin",
        trang=account.display_name[:80],
    )
    return {"da_dang_ky": True, "trang": account.display_name}
