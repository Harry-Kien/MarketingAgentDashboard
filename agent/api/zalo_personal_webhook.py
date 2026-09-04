"""Callback riêng giữa Zalo personal sidecar và control plane."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Mapping, MutableMapping
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from agent.channels.zalo_personal import ZaloPersonalAdapter
from agent.config import settings
from agent.omnichannel.account_repository import PostgresAccountRepository
from agent.omnichannel.accounts import AccountStatus, Channel
from agent.omnichannel.bi_mat_may_chu import (ThieuBiMatMayChu,
                                              bo_sung_bi_mat_may_chu)
from agent.omnichannel.credential_loader import SYSTEM_ACTOR_ID, VaultCredentialLoader
from agent.security.credential_vault import CredentialVault, parse_master_keys


router = APIRouter(
    prefix="/webhook/native/zalo-personal",
    tags=["zalo-personal-sidecar"],
)
_SEEN_NONCES: dict[str, float] = {}


def la_tin_tu_chinh_minh(customer_ref: str, own_id: str | None) -> bool:
    """
    Người gửi có phải chính tài khoản đang kết nối không.

    VÌ SAO CHECK NÀY NẰM Ở CẢ HAI PHÍA
    -----------------------------------
    Sidecar đã lọc, nhưng nó là tiến trình riêng — có thể bị thay, chạy bản
    cũ, hoặc mất `own_id` trong RAM sau khi khôi phục phiên. Control plane
    giữ `own_id` bền hơn trong `channel_accounts.external_account_id`.

    Lọt một tin là agent trả lời chính nó; ở chế độ auto đó là vòng lặp vô
    hạn, spam khách và đốt tiền model, không có gì tự dừng.

    Chỉ chặn khi `own_id` đã được ghim thật. Account còn ở `pending:` mà
    chặn thì nuốt sạch tin khách trong giai đoạn chưa xác minh — im lặng.
    """
    ban_than = (own_id or "").strip()
    if not ban_than or ban_than.startswith("pending:"):
        return False
    return customer_ref.strip() == ban_than


def provider_identity_from_health(data: Mapping[str, Any]) -> str | None:
    """Chỉ tin own_id sau khi sidecar xác nhận phiên đã kết nối."""
    if data.get("status") != "connected":
        return None
    own_id = str(data.get("own_id") or "").strip()
    return own_id or None


def verify_sidecar_callback(
    secret: str,
    path: str,
    raw_body: bytes,
    headers: Mapping[str, str],
    seen_nonces: MutableMapping[str, float],
    *,
    now: float | None = None,
) -> bool:
    current = time.time() if now is None else now
    timestamp = str(headers.get("x-sidecar-timestamp") or "")
    nonce = str(headers.get("x-sidecar-nonce") or "")
    supplied = str(headers.get("x-sidecar-signature") or "")
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if not secret or not nonce or not supplied or abs(current - sent_at) > 60:
        return False
    if nonce in seen_nonces:
        return False
    canonical = b".".join(
        [timestamp.encode(), nonce.encode(), b"POST", path.encode(), raw_body]
    )
    expected = "sha256=" + hmac.new(
        secret.encode(), canonical, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        return False
    seen_nonces[nonce] = current
    for key, seen_at in list(seen_nonces.items()):
        if current - seen_at > 120:
            seen_nonces.pop(key, None)
    return True


def _vault_loader(repository: PostgresAccountRepository) -> VaultCredentialLoader:
    try:
        vault = CredentialVault(
            parse_master_keys(settings.credential_master_keys),
            active_version=settings.credential_active_key_version,
        )
    except ValueError as exc:
        raise HTTPException(503, "Kho credential native chưa sẵn sàng") from exc
    return VaultCredentialLoader(repository, vault)


@router.post("/{account_id}")
async def zalo_personal_callback(
    account_id: UUID,
    request: Request,
    tasks: BackgroundTasks,
) -> dict[str, Any]:
    repository = PostgresAccountRepository()
    account = await repository.get(account_id)
    if account is None or account.channel != Channel.ZALO_PERSONAL:
        raise HTTPException(404, "Không tìm thấy tài khoản Zalo cá nhân")
    loader = _vault_loader(repository)
    credentials = await loader.load(account_id)
    if not credentials:
        raise HTTPException(409, "Tài khoản chưa có credential sidecar")
    # Chữ ký kiểm bằng bí mật của MÁY CHỦ trong .env, không phải bản vault —
    # vault lệch từng làm callback bị 401 tám ngày mà sidecar không đọc
    # phản hồi, nên không ai biết. Xem bi_mat_may_chu.py.
    try:
        credentials = bo_sung_bi_mat_may_chu(Channel.ZALO_PERSONAL, credentials)
    except ThieuBiMatMayChu as exc:
        raise HTTPException(503, str(exc)) from exc

    raw_body = await request.body()
    if not verify_sidecar_callback(
        str(credentials.get("sidecar_secret") or ""),
        request.url.path,
        raw_body,
        request.headers,
        _SEEN_NONCES,
    ):
        raise HTTPException(401, "Chữ ký callback sidecar không hợp lệ")
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(400, "Callback sidecar không phải JSON") from exc

    event = str(payload.get("event") or "")
    data = payload.get("data") or {}
    if event == "session":
        updated = dict(credentials)
        updated["session"] = data
        await loader.store_rotated(account_id, updated)
        return {"ok": True, "stored": "session"}
    if event == "health":
        connected = data.get("status") == "connected"
        status = AccountStatus.ACTIVE if connected else AccountStatus.DEGRADED
        provider_identity = provider_identity_from_health(data)
        if provider_identity:
            await repository.bind_external_identity(
                account_id,
                provider_identity,
                actor_id=SYSTEM_ACTOR_ID,
            )
        await repository.record_health(
            account_id,
            status=status,
            code=f"zalo_personal.{data.get('status') or 'unknown'}",
            detail={"own_id": str(data.get("own_id") or "")},
        )
        if account.status != status:
            await repository.update_status(
                account_id,
                status,
                actor_id=SYSTEM_ACTOR_ID,
            )
        return {"ok": True, "health": status.value}
    if event == "message":
        adapter = ZaloPersonalAdapter(
            account_id=account_id,
            credentials=credentials,
        )
        message = adapter.parse(payload)
        await adapter.aclose()
        if message is None:
            return {"ok": True, "skipped": True}
        if la_tin_tu_chinh_minh(message.customer_ref, account.external_account_id):
            return {"ok": True, "skipped": "tin_tu_chinh_minh"}
        from agent.main import handle_inbound

        tasks.add_task(handle_inbound, message)
        return {"ok": True, "queued": 1}
    raise HTTPException(422, "Loại callback sidecar không được hỗ trợ")
