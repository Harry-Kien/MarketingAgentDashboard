"""Instagram Messaging và WhatsApp Cloud native, account-scoped."""
from __future__ import annotations

import hashlib
import hmac
import mimetypes
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

from agent.config import settings
from agent.channels.base import (
    ChannelAdapter,
    ConnectionCheck,
    Delivery,
    InboundMessage,
    con_trong_cua_so,
)
from .ly_do_loi import chi_tiet_loi


def _timestamp_ms(value: Any) -> datetime:
    try:
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000
        return datetime.fromtimestamp(number, timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc)


def _error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
        error = data.get("error") or data
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or "provider error")[:200]
    except ValueError:
        pass
    return f"HTTP {response.status_code}"


class _MetaAdapter(ChannelAdapter):
    def __init__(
        self,
        *,
        account_id: UUID,
        credentials: Mapping[str, Any],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(account_id=account_id)
        creds = dict(credentials)
        self._access_token = str(creds.get("access_token") or "")
        self._app_secret = str(creds.get("app_secret") or "")
        self._verify_token = str(creds.get("verify_token") or "")
        self._window_hours = float(creds.get("window_hours") or 24)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=str(
                creds.get("api_base") or settings.graph_base
            ).rstrip("/"),
            timeout=20,
        )

    def verify_signature(self, raw_body: bytes, signature: str) -> bool:
        if not self._app_secret or not signature:
            return False
        expected = "sha256=" + hmac.new(
            self._app_secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_challenge(self, params) -> str | None:
        if (
            params.get("hub.mode") == "subscribe"
            and self._verify_token
            and params.get("hub.verify_token") == self._verify_token
        ):
            return params.get("hub.challenge")
        return None

    async def _post(self, path: str, body: Mapping[str, Any]) -> tuple[Delivery, dict]:
        if not self._access_token:
            return Delivery(False, "tài khoản Meta chưa có access token"), {}
        try:
            response = await self._client.post(
                path,
                headers={"Authorization": f"Bearer {self._access_token}"},
                json=dict(body),
            )
        except httpx.HTTPError as exc:
            return Delivery(False, f"{type(exc).__name__}: kết nối Meta lỗi"), {}
        if response.is_error:
            return Delivery(False, _error_detail(response)), {}
        try:
            data = response.json()
        except ValueError:
            return Delivery(False, "Meta trả response không phải JSON"), {}
        return Delivery(True), data

    async def verify_connection(self) -> ConnectionCheck:
        if not self._access_token:
            return ConnectionCheck(False, "provider.unauthorized")
        external_id = str(getattr(self, "_external_account_id", "") or "")
        target = "me" if not external_id or external_id.startswith("pending:") else external_id
        try:
            response = await self._client.get(
                f"/{target}",
                params={"fields": "id,name"},
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
        except httpx.HTTPError as exc:
            return ConnectionCheck(False, "provider.unreachable", detail=chi_tiet_loi(exc))
        if response.status_code in {401, 403}:
            return ConnectionCheck(False, "provider.unauthorized")
        if response.is_error:
            return ConnectionCheck(False, "provider.rejected", detail={"http_status": response.status_code})
        try:
            data = response.json()
        except ValueError:
            return ConnectionCheck(False, "provider.invalid_response")
        verified_id = str(data.get("id") or "").strip()
        if not verified_id:
            return ConnectionCheck(False, "provider.identity_missing")
        return ConnectionCheck(
            True,
            "provider.ok",
            verified_id,
            {"name": str(data.get("name") or "")[:120]},
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class InstagramAdapter(_MetaAdapter):
    name = "instagram"

    def __init__(self, *, account_id: UUID, credentials, client=None) -> None:
        super().__init__(account_id=account_id, credentials=credentials, client=client)
        self._instagram_id = str(
            credentials.get("instagram_id") or credentials.get("external_account_id") or "me"
        )
        # Định danh dùng để LỌC webhook phải là thứ Meta đặt vào `entry.id`,
        # tức chính IG business ID. Trước đây trường này chỉ đọc
        # `external_account_id`, nên tài khoản khai bằng `instagram_id` có
        # định danh rỗng — và phép lọc cũ (fail-open) im lặng bỏ qua, khiến
        # adapter đọc luôn entry của tài khoản khác. Lấy cả hai khoá, và
        # KHÔNG nhận "me": đó là bí danh gọi API, không phải định danh.
        self._external_account_id = str(
            credentials.get("external_account_id")
            or credentials.get("instagram_id")
            or ""
        )
        self._public_media_base = str(credentials.get("public_media_base") or "")

    def parse(self, payload: dict) -> InboundMessage | None:
        messages = self.parse_nhieu(payload)
        return messages[0] if messages else None

    def parse_nhieu(self, payload: dict) -> list[InboundMessage]:
        if payload.get("object") != "instagram":
            return []
        # Chưa gắn định danh thì KHÔNG đọc gì, thay vì đọc tất cả.
        #
        # Một webhook Meta mang entry[] của nhiều tài khoản, và bộ điều phối
        # đưa cả payload cho từng adapter. Bỏ phép lọc khi thiếu định danh là
        # để adapter này nuốt tin của tài khoản khác — rồi trả lời khách từ
        # đúng tài khoản sai, mà không có gì lệch để ai nhận ra.
        if not self._external_account_id:
            return []
        result: list[InboundMessage] = []
        for entry in payload.get("entry") or []:
            if str(entry.get("id") or "") != self._external_account_id:
                continue
            for event in entry.get("messaging") or []:
                message = event.get("message") or {}
                sender = str((event.get("sender") or {}).get("id") or "")
                if not sender or message.get("is_echo"):
                    continue
                attachments = []
                for item in message.get("attachments") or []:
                    url = str((item.get("payload") or {}).get("url") or "")
                    if url:
                        attachments.append(
                            {
                                "loai": str(item.get("type") or "file"),
                                "url": url,
                                "goc": url,
                            }
                        )
                text = str(message.get("text") or "").strip()
                if not text and not attachments:
                    continue
                mid = str(message.get("mid") or event.get("timestamp") or "")
                result.append(
                    InboundMessage(
                        account_id=self.account_id,
                        channel=self.name,
                        conversation_ref=sender,
                        customer_ref=sender,
                        customer_name="Khách Instagram",
                        text=text,
                        dedupe_key=f"{self.name}:{mid}",
                        received_at=_timestamp_ms(event.get("timestamp")),
                        attachments=attachments,
                        meta={"nen_tang_goc": "instagram"},
                    )
                )
        return result

    async def send_text(self, conversation_ref: str, text: str) -> Delivery:
        delivery, data = await self._post(
            f"/{self._instagram_id}/messages",
            {"recipient": {"id": conversation_ref}, "message": {"text": text}},
        )
        if delivery.ok:
            return Delivery(True, provider_message_id=str(data.get("message_id") or ""))
        return delivery

    async def send_file(self, conversation_ref: str, path: str, caption: str = "") -> Delivery:
        if not self._public_media_base:
            return Delivery(False, "Instagram cần public_media_base để gửi tệp")
        url = self._public_media_base.rstrip("/") + "/" + path.replace("\\", "/").lstrip("/")
        if caption:
            caption_result = await self.send_text(conversation_ref, caption)
            if not caption_result.ok:
                return caption_result
        delivery, data = await self._post(
            f"/{self._instagram_id}/messages",
            {
                "recipient": {"id": conversation_ref},
                "message": {
                    "attachment": {"type": "image", "payload": {"url": url}}
                },
            },
        )
        if delivery.ok:
            return Delivery(True, provider_message_id=str(data.get("message_id") or ""))
        return delivery

    async def can_send_now(self, conversation_ref: str) -> bool:
        return await con_trong_cua_so(
            self.name,
            conversation_ref,
            self._window_hours,
            account_id=self.account_id,
        )


class WhatsAppAdapter(_MetaAdapter):
    name = "whatsapp"

    def __init__(self, *, account_id: UUID, credentials, client=None) -> None:
        super().__init__(account_id=account_id, credentials=credentials, client=client)
        self._phone_number_id = str(credentials.get("phone_number_id") or "")
        if not self._phone_number_id:
            self._phone_number_id = str(credentials.get("external_account_id") or "")
        self._external_account_id = self._phone_number_id

    def parse(self, payload: dict) -> InboundMessage | None:
        messages = self.parse_nhieu(payload)
        return messages[0] if messages else None

    def parse_nhieu(self, payload: dict) -> list[InboundMessage]:
        if payload.get("object") != "whatsapp_business_account":
            return []
        # Fail closed — xem chú thích cùng lý do ở InstagramAdapter.parse_nhieu.
        if not self._phone_number_id:
            return []
        result: list[InboundMessage] = []
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                metadata = value.get("metadata") or {}
                if (
                    str(metadata.get("phone_number_id") or "")
                    != self._phone_number_id
                ):
                    continue
                names = {
                    str(contact.get("wa_id") or ""): str(
                        (contact.get("profile") or {}).get("name") or "Khách WhatsApp"
                    )
                    for contact in value.get("contacts") or []
                }
                for message in value.get("messages") or []:
                    sender = str(message.get("from") or "")
                    message_id = str(message.get("id") or "")
                    if not sender or not message_id:
                        continue
                    kind = str(message.get("type") or "")
                    text = ""
                    attachments = []
                    if kind == "text":
                        text = str((message.get("text") or {}).get("body") or "")
                    elif kind in {"image", "video", "audio", "document", "sticker"}:
                        media = message.get(kind) or {}
                        text = str(media.get("caption") or "")
                        attachments.append(
                            {
                                "loai": kind,
                                "provider_media_id": str(media.get("id") or ""),
                                "mime_type": str(media.get("mime_type") or ""),
                            }
                        )
                    else:
                        continue
                    result.append(
                        InboundMessage(
                            account_id=self.account_id,
                            channel=self.name,
                            conversation_ref=sender,
                            customer_ref=sender,
                            customer_name=names.get(sender, "Khách WhatsApp"),
                            text=text,
                            dedupe_key=f"{self.name}:{message_id}",
                            received_at=_timestamp_ms(message.get("timestamp")),
                            attachments=attachments,
                            meta={"nen_tang_goc": "whatsapp"},
                        )
                    )
        return result

    async def send_text(self, conversation_ref: str, text: str) -> Delivery:
        delivery, data = await self._post(
            f"/{self._phone_number_id}/messages",
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": conversation_ref,
                "type": "text",
                "text": {"preview_url": False, "body": text},
            },
        )
        if delivery.ok:
            provider_id = str(((data.get("messages") or [{}])[0]).get("id") or "")
            return Delivery(True, provider_message_id=provider_id)
        return delivery

    async def send_file(self, conversation_ref: str, path: str, caption: str = "") -> Delivery:
        if not os.path.isfile(path):
            return Delivery(False, "không tìm thấy tệp outbound")
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        kind = "image" if mime.startswith("image/") else "document"
        try:
            with open(path, "rb") as handle:
                upload = await self._client.post(
                    f"/{self._phone_number_id}/media",
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    data={"messaging_product": "whatsapp"},
                    files={"file": (os.path.basename(path), handle, mime)},
                )
        except (OSError, httpx.HTTPError) as exc:
            return Delivery(False, f"{type(exc).__name__}: tải tệp WhatsApp lỗi")
        if upload.is_error:
            return Delivery(False, _error_detail(upload))
        media_id = str(upload.json().get("id") or "")
        if not media_id:
            return Delivery(False, "WhatsApp không trả media id")
        media: dict[str, Any] = {"id": media_id}
        if caption:
            media["caption"] = caption
        delivery, data = await self._post(
            f"/{self._phone_number_id}/messages",
            {
                "messaging_product": "whatsapp",
                "to": conversation_ref,
                "type": kind,
                kind: media,
            },
        )
        if delivery.ok:
            provider_id = str(((data.get("messages") or [{}])[0]).get("id") or "")
            return Delivery(True, provider_message_id=provider_id)
        return delivery

    async def can_send_now(self, conversation_ref: str) -> bool:
        return await con_trong_cua_so(
            self.name,
            conversation_ref,
            self._window_hours,
            account_id=self.account_id,
        )
