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

from agent import db
from agent.omnichannel import hop_thu_ben
from agent.channels.zalo_personal import ZaloPersonalAdapter, ly_do_bo_qua
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


# Lần cuối đã ghi "bỏ tin nhóm" cho từng (tài khoản, nhóm) — theo monotonic.
_DA_GHI_NHOM: dict[tuple[str, str], float] = {}
GHI_BO_NHOM_MOI_GIAY = 3600

# Chống ghi trùng sự kiện `channel_account.reconnected` do heartbeat hoặc callback retry.
_DA_GHI_KET_NOI_LAI: dict[str, tuple[str, float]] = {}
_PHIEN_MOI_LAM_MOI: dict[str, float] = {}
KET_NOI_LAI_CHONG_TRUNG_GIAY = 300
_TRIGGER_KET_NOI_LAI = frozenset({"qr", "restore", "reauth", "reconnect", "session_refresh", "manual"})


def _la_heartbeat(payload: Mapping[str, Any], data: Mapping[str, Any]) -> bool:
    """Phân biệt ping sức khoẻ định kỳ (heartbeat) với sự kiện kết nối lại thật."""
    if bool(data.get("heartbeat") or payload.get("heartbeat")):
        return True
    for k in ("kind", "type", "reason", "trigger", "subtype"):
        val = str(data.get(k) or payload.get(k) or "").strip().lower()
        if val == "heartbeat":
            return True
    return False


def _trich_actor_callback(
    payload: Mapping[str, Any],
    data: Mapping[str, Any],
) -> tuple[str, str | None]:
    """Lấy actor hợp lệ từ metadata không nhạy cảm; mặc định là hệ thống."""
    raw_actor = str(
        data.get("actor_id")
        or payload.get("actor_id")
        or data.get("actor")
        or payload.get("actor")
        or ""
    ).strip()
    actor_name = str(
        data.get("nguoi_thuc_hien")
        or payload.get("nguoi_thuc_hien")
        or ""
    ).strip()[:120]
    if raw_actor and raw_actor.lower() not in {"system", "sidecar"}:
        return raw_actor[:80], (actor_name or raw_actor[:80])
    return str(SYSTEM_ACTOR_ID), (actor_name or None)


def _trich_event_id(
    payload: Mapping[str, Any],
    data: Mapping[str, Any],
    headers: Mapping[str, str],
) -> str:
    for val in (
        headers.get("x-sidecar-event-id"),
        payload.get("event_id"),
        data.get("event_id"),
        payload.get("callback_id"),
        data.get("callback_id"),
        payload.get("idempotency_key"),
        data.get("idempotency_key"),
    ):
        s = str(val or "").strip()
        if s:
            return s[:120]
    return ""


async def _da_ghi_su_kien_ket_noi_lai(
    account_id: UUID,
    dedup_key: str,
    *,
    event_id: str,
    co_id_rieng: bool,
    bay_gio: float | None = None,
) -> bool:
    """Trả True nếu callback này là bản retry/heartbeat trùng, không cần ghi thêm."""
    nay = time.monotonic() if bay_gio is None else bay_gio
    acc_key = str(account_id)
    if event_id:
        try:
            row = await db.fetchrow(
                "SELECT 1 FROM events "
                "WHERE kind = 'channel_account.reconnected' "
                "AND ref_id = $1 AND detail ->> 'event_id' = $2 LIMIT 1",
                account_id,
                event_id,
            )
            if row is not None:
                return True
        except Exception:  # noqa: BLE001 — unit test không mở pool CSDL dùng cache RAM
            pass
    truoc = _DA_GHI_KET_NOI_LAI.get(acc_key)
    if truoc is not None:
        khoa_cu, luc_cu = truoc
        if co_id_rieng:
            if khoa_cu == dedup_key:
                return True
        else:
            if nay - luc_cu < KET_NOI_LAI_CHONG_TRUNG_GIAY:
                return True
    return False


def _danh_dau_da_ghi_ket_noi_lai(
    account_id: UUID,
    dedup_key: str,
    *,
    bay_gio: float | None = None,
) -> None:
    nay = time.monotonic() if bay_gio is None else bay_gio
    if len(_DA_GHI_KET_NOI_LAI) > 5000:
        _DA_GHI_KET_NOI_LAI.clear()
    _DA_GHI_KET_NOI_LAI[str(account_id)] = (dedup_key, nay)


async def _ghi_su_kien_ket_noi_lai(
    account: Any,
    *,
    status_truoc: AccountStatus,
    status_sau: AccountStatus,
    payload: Mapping[str, Any],
    data: Mapping[str, Any],
    headers: Mapping[str, str],
    bay_gio: float | None = None,
) -> bool:
    """
    Ghi nhận `channel_account.reconnected` khi kết nối lại / xác thực lại thành công,
    kể cả khi `status_truoc == status_sau == AccountStatus.ACTIVE`, đồng thời chặn trùng
    lặp do heartbeat hoặc callback retry và KHÔNG lưu token/session secret/QR.
    """
    nay = time.monotonic() if bay_gio is None else bay_gio
    acc_key = str(account.id)
    is_heartbeat = _la_heartbeat(payload, data)
    session_ts = _PHIEN_MOI_LAM_MOI.get(acc_key)
    sau_session = session_ts is not None and (nay - session_ts) <= 120

    if is_heartbeat and status_truoc == AccountStatus.ACTIVE and not sau_session:
        return False

    event_id = _trich_event_id(payload, data, headers)
    epoch = str(data.get("epoch") or payload.get("epoch") or "").strip()
    trigger = str(
        data.get("trigger")
        or data.get("reason")
        or payload.get("trigger")
        or ("session_refresh" if sau_session else ("status_recovery" if status_truoc != status_sau else "reconnect"))
    ).strip()[:60]
    own_id = str(data.get("own_id") or "").strip()[:80]
    explicit_reconnect = bool(data.get("reconnected") or payload.get("reconnected")) or (
        trigger.lower() in _TRIGGER_KET_NOI_LAI
    ) or str(payload.get("event") or "") == "reconnected"

    if event_id:
        dedup_key = f"id:{event_id}"
        co_id_rieng = True
    elif epoch:
        dedup_key = f"epoch:{epoch}:{own_id}"
        co_id_rieng = True
    elif sau_session:
        dedup_key = f"session:{int(session_ts)}"
        co_id_rieng = False
    else:
        dedup_key = f"health:{own_id}:{trigger}:{status_truoc.value}"
        co_id_rieng = False

    if status_truoc == status_sau and not explicit_reconnect and not sau_session:
        # Không có cờ reconnect/session rõ ràng: vẫn ghi lần đầu (như callback từ attach),
        # nhưng chặn các lần lặp/heartbeat kế tiếp trong cửa sổ chống trùng.
        if await _da_ghi_su_kien_ket_noi_lai(
            account.id, dedup_key, event_id=event_id, co_id_rieng=False, bay_gio=nay
        ):
            return False
    else:
        # Đã có sự kiện chuyển trạng thái / reconnect tường minh / session refresh:
        # vẫn chống trùng nếu cùng event_id hoặc cùng retry giống hệt ngay sát nhau.
        if status_truoc == status_sau and await _da_ghi_su_kien_ket_noi_lai(
            account.id, dedup_key, event_id=event_id, co_id_rieng=co_id_rieng, bay_gio=nay
        ):
            return False
        if status_truoc != status_sau and event_id and await _da_ghi_su_kien_ket_noi_lai(
            account.id, dedup_key, event_id=event_id, co_id_rieng=True, bay_gio=nay
        ):
            return False

    actor_str, actor_name = _trich_actor_callback(payload, data)
    chi_tiet: dict[str, Any] = {
        "account_id": acc_key,
        "channel": account.channel.value,
        "status": status_sau.value,
        "previous_status": status_truoc.value,
        "ket_qua": "thanh_cong",
        "trigger": trigger,
        "reconnected": True,
    }
    if own_id:
        chi_tiet["own_id"] = own_id
    if event_id:
        chi_tiet["event_id"] = event_id
    if epoch:
        chi_tiet["epoch"] = epoch[:40]
    if actor_name:
        chi_tiet["nguoi_thuc_hien"] = actor_name

    await db.log_event(
        "channel_account.reconnected",
        actor=actor_str,
        ref_id=account.id,
        **chi_tiet,
    )
    _danh_dau_da_ghi_ket_noi_lai(account.id, dedup_key, bay_gio=nay)
    _PHIEN_MOI_LAM_MOI.pop(acc_key, None)
    return True


async def _ghi_bo_tin_nhom(account_id: UUID, nhom: str, *,
                           bay_gio: float | None = None) -> bool:
    """
    Ghi sự kiện bỏ tin nhóm — tối đa MỘT lần mỗi giờ mỗi nhóm.

    Chỉ chạy khi người vận hành TẮT ZALO_NHAN_TIN_NHOM. Mặc định tin nhóm
    vào hộp thư cho nhân viên đọc; AI thì không bao giờ nói trong nhóm —
    chốt ấy nằm ở `xu_ly_tin_vao` và outbox, không nằm ở việc bỏ tin. Bản
    trước bỏ tin nhóm theo mặc định vì AI từng soạn câu tư vấn mỹ phẩm cho
    cả nhóm khoá luận; bỏ tin thì cũng bỏ luôn khách hỏi hàng trong nhóm.

    VÌ SAO THƯA: nhóm sôi nổi có hàng trăm tin một giờ; ghi từng tin là
    nhấn chìm bảng sự kiện. Một dòng mỗi giờ đủ để ai thắc mắc "sao nhóm X
    không vào" tìm được câu trả lời.
    """
    nay = time.monotonic() if bay_gio is None else bay_gio
    khoa = (str(account_id), nhom)
    truoc = _DA_GHI_NHOM.get(khoa)
    if truoc is not None and nay - truoc < GHI_BO_NHOM_MOI_GIAY:
        return False
    _DA_GHI_NHOM[khoa] = nay
    if len(_DA_GHI_NHOM) > 5000:        # không phình RAM vô hạn
        _DA_GHI_NHOM.clear()
        _DA_GHI_NHOM[khoa] = nay
    await db.log_event("zalo_personal.bo_tin_nhom", ref_id=account_id,
                       nhom=nhom[:64], cau_hinh="ZALO_NHAN_TIN_NHOM=false")
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
        if len(_PHIEN_MOI_LAM_MOI) > 5000:
            _PHIEN_MOI_LAM_MOI.clear()
        _PHIEN_MOI_LAM_MOI[str(account_id)] = time.monotonic()
        return {"ok": True, "stored": "session"}
    if event in {"health", "reconnected"}:
        connected = (
            data.get("status", "connected") == "connected"
            if event == "reconnected"
            else data.get("status") == "connected"
        )
        status = AccountStatus.ACTIVE if connected else AccountStatus.DEGRADED
        provider_identity = provider_identity_from_health(
            {"status": "connected" if connected else data.get("status"), "own_id": data.get("own_id")}
        )
        if provider_identity and account.external_account_id != provider_identity:
            await repository.bind_external_identity(
                account_id,
                provider_identity,
                actor_id=SYSTEM_ACTOR_ID,
            )
        await repository.record_health(
            account_id,
            status=status,
            code=f"zalo_personal.{data.get('status') or ('connected' if connected else 'unknown')}",
            detail={"own_id": str(data.get("own_id") or "")},
        )
        status_truoc = account.status
        if status_truoc != status:
            await repository.update_status(
                account_id,
                status,
                actor_id=SYSTEM_ACTOR_ID,
            )
        da_ghi_kn = False
        if connected:
            da_ghi_kn = await _ghi_su_kien_ket_noi_lai(
                account,
                status_truoc=status_truoc,
                status_sau=status,
                payload=payload,
                data=data,
                headers=request.headers,
            )
        return {"ok": True, "health": status.value, "reconnected_logged": da_ghi_kn}
    if event == "message":
        adapter = ZaloPersonalAdapter(
            account_id=account_id,
            credentials=credentials,
        )
        message = adapter.parse(payload)
        await adapter.aclose()
        if message is None:
            # KHÔNG bỏ câm. Đây đúng là chỗ ảnh khách gửi từng biến mất
            # (sidecar không đọc ảnh → tin rỗng → parse None → `skipped`):
            # 80 tin, 0 tệp, không một dòng nhật ký. Trả 200 vẫn đúng — gửi
            # lại cũng ra None — nhưng phải để lại dấu vết.
            await db.log_event("zalo_personal.tin_bo_qua", ref_id=account_id,
                               **ly_do_bo_qua(payload))
            return {"ok": True, "skipped": True}
        # So NGƯỜI GỬI, không so danh tính hội thoại: trong nhóm,
        # `customer_ref` là `group:<id>` và không bao giờ trùng own_id — so
        # nó thì tin nhân viên gửi vào nhóm vọng về lọt qua như tin khách.
        if la_tin_tu_chinh_minh(message.sender_ref or message.customer_ref,
                                account.external_account_id):
            return {"ok": True, "skipped": "tin_tu_chinh_minh"}
        if message.la_nhom and not settings.zalo_nhan_tin_nhom:
            await _ghi_bo_tin_nhom(account_id, message.conversation_ref)
            return {"ok": True, "skipped": "tin_nhom"}
        await hop_thu_ben.nhan(message, tasks)
        return {"ok": True, "queued": 1}
    raise HTTPException(422, "Loại callback sidecar không được hỗ trợ")
