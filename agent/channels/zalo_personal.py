"""Zalo cá nhân native qua sidecar Node được cách ly và ký HMAC."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

from agent.channels.base import ChannelAdapter, ConnectionCheck, Delivery, InboundMessage


def _received_at(value: Any) -> datetime:
    try:
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000
        return datetime.fromtimestamp(number, timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc)


class ZaloPersonalAdapter(ChannelAdapter):
    name = "zalo_personal"

    def __init__(
        self,
        *,
        account_id: UUID,
        credentials: Mapping[str, Any],
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(account_id=account_id)
        self._secret = str(credentials.get("sidecar_secret") or "")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=str(
                credentials.get("sidecar_url") or "http://127.0.0.1:3210"
            ).rstrip("/"),
            timeout=30,
        )

    def parse(self, payload: dict) -> InboundMessage | None:
        if payload.get("event") != "message":
            return None
        message = payload.get("message") or {}
        thread_id = str(message.get("thread_id") or "")
        sender_id = str(message.get("sender_id") or thread_id)
        msg_id = str(message.get("msg_id") or "")
        if not thread_id or not msg_id:
            return None
        attachments = []
        for raw in message.get("attachments") or []:
            url = str(raw.get("url") or "")
            if not url:
                continue
            attachments.append(
                {
                    "loai": str(raw.get("type") or "file"),
                    "url": url,
                    "goc": url,
                    "mime_type": str(raw.get("mime_type") or ""),
                }
            )
        text = str(message.get("text") or "").strip()
        if not text and not attachments:
            return None
        return InboundMessage(
            account_id=self.account_id,
            channel=self.name,
            conversation_ref=thread_id,
            customer_ref=sender_id,
            customer_name=str(message.get("sender_name") or "Khách Zalo"),
            text=text,
            dedupe_key=f"{self.name}:{msg_id}",
            received_at=_received_at(message.get("timestamp")),
            attachments=attachments,
            meta={
                "nen_tang_goc": "zalo_personal",
                "thread_type": int(message.get("thread_type") or 0),
            },
        )

    async def _request(self, action: str, payload: Mapping[str, Any]) -> tuple[Delivery, dict]:
        if not self._secret:
            return Delivery(False, "sidecar secret chưa được cấu hình"), {}
        path = f"/v1/accounts/{self.account_id}/{action}"
        body = json.dumps(
            dict(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(16)
        canonical = b".".join(
            [
                timestamp.encode(),
                nonce.encode(),
                b"POST",
                path.encode(),
                body,
            ]
        )
        signature = "sha256=" + hmac.new(
            self._secret.encode(), canonical, hashlib.sha256
        ).hexdigest()
        try:
            response = await self._client.post(
                path,
                content=body,
                headers={
                    "content-type": "application/json",
                    "x-sidecar-timestamp": timestamp,
                    "x-sidecar-nonce": nonce,
                    "x-sidecar-signature": signature,
                },
            )
        except httpx.HTTPError as exc:
            return Delivery(False, f"{type(exc).__name__}: sidecar không phản hồi"), {}
        try:
            data = response.json()
        except ValueError:
            return Delivery(False, f"sidecar HTTP {response.status_code}"), {}
        if response.is_error or not data.get("ok"):
            return Delivery(False, str(data.get("error") or "sidecar từ chối")[:200]), data
        return Delivery(True), data

    async def send_text(self, conversation_ref: str, text: str) -> Delivery:
        delivery, data = await self._request(
            "send-text",
            {"thread_id": conversation_ref, "thread_type": 0, "text": text},
        )
        if delivery.ok:
            return Delivery(
                True,
                provider_message_id=str(data.get("message_id") or ""),
            )
        return delivery

    async def send_file(self, conversation_ref: str, path: str, caption: str = "") -> Delivery:
        delivery, data = await self._request(
            "send-file",
            {
                "thread_id": conversation_ref,
                "thread_type": 0,
                "path": path,
                "caption": caption,
            },
        )
        if delivery.ok:
            return Delivery(
                True,
                provider_message_id=str(data.get("message_id") or ""),
            )
        return delivery

    async def start_qr(self) -> dict[str, Any]:
        delivery, data = await self._request("login-qr", {})
        if not delivery.ok:
            raise RuntimeError(delivery.detail)
        return data

    async def restore_session(self, session: Mapping[str, Any]) -> dict[str, Any]:
        delivery, data = await self._request("restore-session", {"session": dict(session)})
        if not delivery.ok:
            raise RuntimeError(delivery.detail)
        return data

    async def status(self) -> dict[str, Any]:
        delivery, data = await self._request("status", {})
        if not delivery.ok:
            raise RuntimeError(delivery.detail)
        return data

    async def verify_connection(self) -> ConnectionCheck:
        try:
            data = await self.status()
        except RuntimeError as exc:
            return ConnectionCheck(False, "provider.unreachable", detail={"error_type": type(exc).__name__})
        if data.get("status") != "connected":
            return ConnectionCheck(False, "provider.not_connected", detail={"status": str(data.get("status") or "unknown")})
        own_id = str(data.get("own_id") or "").strip()
        if not own_id:
            return ConnectionCheck(False, "provider.identity_missing")
        return ConnectionCheck(True, "provider.ok", own_id)

    async def aclose(self) -> None:
        await self._client.aclose()
