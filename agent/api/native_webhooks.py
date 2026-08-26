"""Webhook Meta native: fan-out một batch về đúng từng channel account."""
from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from agent.channels.factory import AccountAdapterFactory
from agent.config import settings
from agent.omnichannel.account_repository import PostgresAccountRepository
from agent.channels.ten_khach import can_lay_ten
from agent.omnichannel.accounts import Channel, ChannelAccount
from agent.omnichannel.credential_loader import VaultCredentialLoader
from agent.security.credential_vault import CredentialVault, parse_master_keys


router = APIRouter(prefix="/webhook/native", tags=["native-webhooks"])


class AccountLookup(Protocol):
    async def get(self, account_id: UUID) -> ChannelAccount | None: ...

    async def find_active_by_external_ids(
        self, channel: Channel, external_ids: set[str]
    ) -> list[ChannelAccount]: ...


class AdapterFactory(Protocol):
    async def create(self, account_id): ...


def extract_meta_targets(payload: dict) -> tuple[Channel, set[str]]:
    object_name = str(payload.get("object") or "")
    if object_name == "page":
        return Channel.FACEBOOK, {
            str(entry.get("id"))
            for entry in (payload.get("entry") or [])
            if entry.get("id")
        }
    if object_name == "instagram":
        return Channel.INSTAGRAM, {
            str(entry.get("id"))
            for entry in (payload.get("entry") or [])
            if entry.get("id")
        }
    if object_name == "whatsapp_business_account":
        identities: set[str] = set()
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                phone_id = str(
                    ((change.get("value") or {}).get("metadata") or {}).get(
                        "phone_number_id"
                    )
                    or ""
                )
                if phone_id:
                    identities.add(phone_id)
        return Channel.WHATSAPP, identities
    raise HTTPException(422, "Loại webhook Meta không được hỗ trợ")


class MetaWebhookDispatcher:
    def __init__(self, accounts: AccountLookup, factory: AdapterFactory) -> None:
        self._accounts = accounts
        self._factory = factory

    async def dispatch(
        self,
        *,
        raw_body: bytes,
        signature: str,
        payload: dict,
    ) -> list:
        channel, identities = extract_meta_targets(payload)
        if not identities:
            raise HTTPException(422, "Webhook Meta không có account identity")
        accounts = await self._accounts.find_active_by_external_ids(
            channel, identities
        )
        if not accounts:
            raise HTTPException(404, "Không tìm thấy tài khoản nhận webhook")

        adapters = [await self._factory.create(account.id) for account in accounts]
        if any(
            not getattr(adapter, "verify_signature", lambda *_: False)(
                raw_body, signature
            )
            for adapter in adapters
        ):
            raise HTTPException(401, "Chữ ký webhook Meta không hợp lệ")

        messages = []
        for adapter in adapters:
            phan = adapter.parse_nhieu(payload)
            await self._lam_giau_ten(adapter, phan)
            messages.extend(phan)
        return messages

    @staticmethod
    async def _lam_giau_ten(adapter, messages: list) -> None:
        """
        Hỏi Graph API tên thật của khách, thay cho chữ "Khách" chung chung.

        VÌ SAO Ở ĐÂY, KHÔNG PHẢI SAU
        ----------------------------
        Làm sau khi tin đã vào InboxService thì hội thoại đã được tạo với tên
        mặc định, và sửa lại là thêm một đường ghi nữa — phức tạp hơn mà kết
        quả kém hơn.

        VÌ SAO CHỈ GỌI KHI TÊN CÒN MẶC ĐỊNH
        -----------------------------------
        Mỗi lượt gọi Graph là một chặng mạng nằm trên đường trả lời khách.
        Tên người gần như không đổi — lấy một lần là đủ.

        Hỏng thì im lặng bỏ qua: tên chỉ để hiển thị, tin nhắn mới là việc
        chính. `lay_ten_khach` đã tự nuốt lỗi và trả rỗng.
        """
        lay = getattr(adapter, "lay_ten_khach", None)
        if lay is None:
            return
        # Một khách gửi nhiều tin liền là chuyện thường; hỏi một lần cho mỗi
        # người thay vì mỗi tin.
        da_hoi: dict[str, str] = {}
        for msg in messages:
            if not can_lay_ten(getattr(msg, "customer_name", "")):
                continue
            ref = str(getattr(msg, "customer_ref", "") or "")
            if not ref:
                continue
            if ref not in da_hoi:
                da_hoi[ref] = await lay(ref)
            if da_hoi[ref]:
                msg.customer_name = da_hoi[ref]

    async def verify_tokens_dang_dung(self) -> set[str]:
        """
        Mọi verify token của tài khoản Meta đang hoạt động.

        Đọc từ vault chứ không từ `.env`: credential nằm theo từng tài khoản,
        và đường native không đọc `.env` — trộn hai nguồn là lúc nào đó chúng
        lệch nhau mà không ai biết.
        """
        ra: set[str] = set()
        for kenh in (Channel.FACEBOOK, Channel.INSTAGRAM, Channel.WHATSAPP):
            for account in await self._accounts.list_active_by_channel(kenh):
                try:
                    adapter = await self._factory.create(account.id)
                except Exception:  # noqa: BLE001 — một tài khoản hỏng không chặn phần còn lại
                    continue
                token = str(getattr(adapter, "_verify_token", "") or "")
                if token:
                    ra.add(token)
        return ra

    async def verify_account_challenge(
        self,
        account_id: UUID,
        params: dict[str, str],
    ) -> str:
        account = await self._accounts.get(account_id)
        if account is None or account.status.value not in {"active", "degraded"}:
            raise HTTPException(404, "Không tìm thấy tài khoản Meta hoạt động")
        if account.channel not in {
            Channel.FACEBOOK,
            Channel.INSTAGRAM,
            Channel.WHATSAPP,
        }:
            raise HTTPException(422, "Tài khoản không thuộc kênh Meta")
        adapter = await self._factory.create(account_id)
        challenge = getattr(adapter, "verify_challenge", lambda *_: None)(params)
        if challenge is None:
            raise HTTPException(403, "Verify token Meta không hợp lệ")
        return str(challenge)

    async def dispatch_account(
        self,
        *,
        account_id: UUID,
        raw_body: bytes,
        signature: str,
        payload: dict,
    ) -> list:
        account = await self._accounts.get(account_id)
        if account is None or account.status.value not in {"active", "degraded"}:
            raise HTTPException(404, "Không tìm thấy tài khoản Meta hoạt động")
        channel, identities = extract_meta_targets(payload)
        if channel != account.channel or account.external_account_id not in identities:
            raise HTTPException(422, "Payload không thuộc tài khoản Meta trên URL")
        adapter = await self._factory.create(account_id)
        if not getattr(adapter, "verify_signature", lambda *_: False)(
            raw_body, signature
        ):
            raise HTTPException(401, "Chữ ký webhook Meta không hợp lệ")
        return adapter.parse_nhieu(payload)


def _dispatcher() -> MetaWebhookDispatcher:
    try:
        vault = CredentialVault(
            parse_master_keys(settings.credential_master_keys),
            active_version=settings.credential_active_key_version,
        )
    except ValueError as exc:
        raise HTTPException(503, "Kho credential native chưa sẵn sàng") from exc
    repository = PostgresAccountRepository()
    return MetaWebhookDispatcher(
        repository,
        AccountAdapterFactory(
            repository,
            VaultCredentialLoader(repository, vault),
        ),
    )


def doc_thach_thuc(params: dict, token_hop_le: set[str]) -> str | None:
    """
    Đọc `hub.challenge` nếu yêu cầu xác minh của Meta hợp lệ.

    TẬP TOKEN RỖNG KHÔNG PHẢI LÀ "CHẤP NHẬN TẤT CẢ"
    ------------------------------------------------
    Chưa nối tài khoản nào thì `token_hop_le` rỗng, và lúc đó phải TỪ CHỐI.
    Cho qua là fail-open: ai gõ đúng URL cũng xác minh được webhook, rồi Meta
    bắt đầu đẩy tin vào một hệ thống chưa có tài khoản nào để nhận — tin rơi
    vào hư không và không có gì báo.
    """
    if params.get("hub.mode") != "subscribe":
        return None
    token = params.get("hub.verify_token")
    thach_thuc = params.get("hub.challenge")
    if not token or not thach_thuc or not token_hop_le:
        return None
    return str(thach_thuc) if token in token_hop_le else None


@router.post("/meta")
async def native_meta_webhook(
    request: Request,
    tasks: BackgroundTasks,
) -> JSONResponse:
    raw_body = await request.body()
    try:
        payload: dict[str, Any] = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(400, "Payload Meta không phải JSON") from exc
    messages = await _dispatcher().dispatch(
        raw_body=raw_body,
        signature=request.headers.get("x-hub-signature-256", ""),
        payload=payload,
    )
    # Import muộn để tránh vòng main -> router -> main lúc khởi động.
    from agent.main import handle_inbound

    for message in messages:
        tasks.add_task(handle_inbound, message)
    return JSONResponse({"ok": True, "queued": len(messages)})


@router.get("/meta")
async def verify_native_meta_gop(request: Request) -> PlainTextResponse:
    """
    Xác minh webhook cho ĐƯỜNG GỘP.

    Meta chỉ cho khai MỘT url webhook cho mỗi ứng dụng, nên nhiều Trang đều
    đi qua `/webhook/native/meta`. Lúc bấm "Xác minh và lưu", Meta gửi GET
    tới chính url đó — thiếu route này là nhận 405 và không lưu được, với
    thông báo lỗi không nói gì về nguyên nhân thật.

    Chấp nhận nếu verify token khớp BẤT KỲ tài khoản Meta nào đang hoạt
    động: các Trang trên cùng một app dùng chung một verify token, vì Meta
    chỉ có một ô để khai nó.
    """
    tokens = await _dispatcher().verify_tokens_dang_dung()
    thach_thuc = doc_thach_thuc(dict(request.query_params), tokens)
    if thach_thuc is None:
        raise HTTPException(403, "Verify token Meta không hợp lệ")
    return PlainTextResponse(thach_thuc)


@router.get("/meta/{account_id}")
async def verify_native_meta_account(
    account_id: UUID,
    request: Request,
) -> PlainTextResponse:
    challenge = await _dispatcher().verify_account_challenge(
        account_id,
        dict(request.query_params),
    )
    return PlainTextResponse(challenge)


@router.post("/meta/{account_id}")
async def native_meta_account_webhook(
    account_id: UUID,
    request: Request,
    tasks: BackgroundTasks,
) -> JSONResponse:
    raw_body = await request.body()
    try:
        payload: dict[str, Any] = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(400, "Payload Meta không phải JSON") from exc
    messages = await _dispatcher().dispatch_account(
        account_id=account_id,
        raw_body=raw_body,
        signature=request.headers.get("x-hub-signature-256", ""),
        payload=payload,
    )
    from agent.main import handle_inbound

    for message in messages:
        tasks.add_task(handle_inbound, message)
    return JSONResponse({"ok": True, "queued": len(messages)})
