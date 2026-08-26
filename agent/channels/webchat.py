"""Kênh webchat first-party; provider chính là realtime stream nội bộ."""
from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from agent.channels.base import ChannelAdapter, ConnectionCheck, Delivery, InboundMessage


class WebchatAdapter(ChannelAdapter):
    name = "webchat"

    def __init__(
        self,
        *,
        account_id: UUID,
        credentials: Mapping[str, Any],
    ) -> None:
        super().__init__(account_id=account_id)
        self._widget_secret = str(credentials.get("widget_secret") or "")

    def parse(self, payload: dict) -> InboundMessage | None:
        visitor_id = str(payload.get("visitor_id") or "").strip()
        client_id = str(payload.get("client_message_id") or "").strip()
        text = str(payload.get("text") or "").strip()
        attachments = list(payload.get("attachments") or [])
        if not visitor_id or not client_id or (not text and not attachments):
            return None
        try:
            received_at = datetime.fromisoformat(str(payload.get("received_at") or ""))
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
        except ValueError:
            received_at = datetime.now(timezone.utc)
        return InboundMessage(
            account_id=self.account_id,
            channel=self.name,
            conversation_ref=visitor_id,
            customer_ref=visitor_id,
            customer_name=str(payload.get("visitor_name") or "Khách website")[:120],
            text=text,
            dedupe_key=f"{self.name}:{client_id}",
            received_at=received_at,
            attachments=attachments,
            meta={"nen_tang_goc": "webchat"},
        )

    async def send_text(self, conversation_ref: str, text: str) -> Delivery:
        # Message đã commit trước khi worker tới đây; SSE đọc trực tiếp timeline.
        return Delivery(True, provider_message_id=f"webchat:{uuid4()}")

    async def send_file(self, conversation_ref: str, path: str, caption: str = "") -> Delivery:
        if not os.path.isfile(path):
            return Delivery(False, "không tìm thấy tệp webchat")
        return Delivery(True, provider_message_id=f"webchat:{uuid4()}")

    async def verify_connection(self) -> ConnectionCheck:
        if len(self._widget_secret.encode("utf-8")) < 32:
            return ConnectionCheck(False, "webchat.weak_widget_secret")
        return ConnectionCheck(True, "webchat.ready", str(self.account_id))

    async def aclose(self) -> None:
        return None
