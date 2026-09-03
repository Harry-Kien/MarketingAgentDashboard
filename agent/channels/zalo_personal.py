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
from .ly_do_loi import chi_tiet_loi


def _received_at(value: Any) -> datetime:
    try:
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000
        return datetime.fromtimestamp(number, timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc)


def _kem_boi_canh(
    delivery: Delivery, thread_id: str, loai: int, do_dai: int
) -> Delivery:
    """
    Gắn bối cảnh vào lý do gửi hỏng.

    VÌ SAO: Zalo trả về những câu như "Tham số không hợp lệ" — đúng ngữ
    pháp và vô dụng, vì nó không nói THAM SỐ NÀO. Một job đã chết trong
    outbox với đúng câu đó, và truy ra nguyên nhân mất nhiều thời gian hơn
    hẳn mức đáng phải mất.

    Ba thứ dưới đây là ba nghi phạm thường gặp, và in kèm chúng không tốn
    gì. KHÔNG in nội dung tin nhắn: nhật ký lỗi không phải chỗ chứa lời
    khách, chỉ in độ dài là đủ để loại trừ nghi phạm "tin quá dài".
    """
    return Delivery(
        False,
        f"{delivery.detail} "
        f"[thread_id={thread_id!r} thread_type={loai} do_dai={do_dai}]"[:400],
    )


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
        # Loại thread của từng hội thoại, nhớ lại từ tin ĐẾN.
        #
        # VÌ SAO CẦN: Zalo phân biệt nhắn cho MỘT NGƯỜI (type 0) với nhắn
        # vào NHÓM (type 1). `parse()` đã đọc đúng giá trị này từ lâu và cất
        # vào `meta`, nhưng `send_text`/`send_file` lại gán cứng 0 — nên mọi
        # câu trả lời vào nhóm đều gửi sai loại và bị Zalo từ chối với
        # "Tham số không hợp lệ", một câu không nói được tham số nào sai.
        #
        # Adapter cũ `zalocrm.py:205` mang đúng `threadType` đi; bản native
        # này đánh rơi nó.
        #
        # GIỚI HẠN PHẢI NÓI RÕ: bộ nhớ này nằm trong tiến trình. Sau khi
        # khởi động lại, câu trả lời ĐẦU TIÊN vào một nhóm sẽ lại rơi về 0
        # cho tới khi có tin mới từ nhóm đó. Vẫn không tệ hơn hôm nay — hôm
        # nay nó luôn là 0 — nhưng đừng nhầm đây là bản vá kín.
        self._loai_thread: dict[str, int] = {}
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
        # Nhớ loại thread NGAY khi đọc tin đến, để câu trả lời đi ra đúng
        # loại. Ghi ở đây chứ không ghi ở tầng trên vì đây là chỗ duy nhất
        # còn nhìn thấy payload gốc của sidecar.
        self._loai_thread[thread_id] = int(message.get("thread_type") or 0)
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

    def _loai(self, conversation_ref: str) -> int:
        """Loại thread đã nhớ, mặc định 0 (nhắn riêng) khi chưa biết."""
        return self._loai_thread.get(conversation_ref, 0)

    async def send_text(self, conversation_ref: str, text: str) -> Delivery:
        loai = self._loai(conversation_ref)
        delivery, data = await self._request(
            "send-text",
            {"thread_id": conversation_ref, "thread_type": loai, "text": text},
        )
        if delivery.ok:
            return Delivery(
                True,
                provider_message_id=str(data.get("message_id") or ""),
            )
        return _kem_boi_canh(delivery, conversation_ref, loai, len(text))

    async def send_file(self, conversation_ref: str, path: str, caption: str = "") -> Delivery:
        loai = self._loai(conversation_ref)
        delivery, data = await self._request(
            "send-file",
            {
                "thread_id": conversation_ref,
                "thread_type": loai,
                "path": path,
                "caption": caption,
            },
        )
        if delivery.ok:
            return Delivery(
                True,
                provider_message_id=str(data.get("message_id") or ""),
            )
        return _kem_boi_canh(delivery, conversation_ref, loai, len(caption))

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
            return ConnectionCheck(False, "provider.unreachable", detail=chi_tiet_loi(exc))
        if data.get("status") != "connected":
            return ConnectionCheck(False, "provider.not_connected", detail={"status": str(data.get("status") or "unknown")})
        own_id = str(data.get("own_id") or "").strip()
        if not own_id:
            return ConnectionCheck(False, "provider.identity_missing")
        return ConnectionCheck(True, "provider.ok", own_id)

    async def aclose(self) -> None:
        await self._client.aclose()
