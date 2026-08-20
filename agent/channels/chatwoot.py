"""
Adapter Chatwoot — cửa vào đa nền tảng.

VÌ SAO THÊM CHATWOOT KHI ĐÃ CÓ ZALOCRM
--------------------------------------
ZaloCRM chỉ nói chuyện được với Zalo. Chatwoot gom Facebook Messenger,
Instagram DM, WhatsApp, khung chat trên website và email về CÙNG một hộp
thư, với cùng một hình dạng dữ liệu. Thêm một adapter ở đây là thêm bốn
nền tảng cho agent, không phải bốn lần viết lại agent.

Khác biệt kỹ thuật đáng chú ý so với ZaloCRM: Chatwoot KHÔNG có chốt chặn
SSRF, nên webhook về `http://host.docker.internal:8000` chạy được thật.
Nghĩa là kênh này đi bằng WEBHOOK (đẩy, tức thì) trong khi ZaloCRM phải đi
bằng POLLING (kéo, trễ vài giây). Hai cơ chế trái ngược nhau, mà phần trên
— agent, RAG, video, dashboard — không biết và không cần biết. Đó chính là
điều lớp ChannelAdapter được dựng ra để làm.

Lưu ý thực tế: Chatwoot kết nối Facebook/Instagram vẫn cần Meta App Review
như mọi cách khác. Khung chat website và email thì dùng được ngay.

HỢP ĐỒNG API
  Webhook (Chatwoot -> ta), sự kiện message_created:
    {event, message_type: "incoming"|"outgoing", content,
     conversation: {id, ...}, sender: {id, name}, account: {id}}
  Gửi (ta -> Chatwoot):
    POST /api/v1/accounts/{acc}/conversations/{conv}/messages
    body {content, message_type: "outgoing"}
    header api_access_token
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from agent.channels.base import ChannelAdapter, Delivery, InboundMessage
from agent.config import settings


class ChatwootAdapter(ChannelAdapter):
    name = "chatwoot"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.chatwoot_base_url.rstrip("/"),
            headers={"api_access_token": settings.chatwoot_api_token},
            timeout=20.0,
        )

    def cau_hinh_du(self) -> bool:
        return bool(settings.chatwoot_base_url and settings.chatwoot_api_token
                    and settings.chatwoot_account_id)

    # ---------------- vào ----------------

    def parse(self, payload: dict) -> InboundMessage | None:
        """
        Chatwoot bắn nhiều loại sự kiện về cùng một URL. Chỉ nhận tin nhắn
        ĐẾN từ khách — bỏ qua tin đi (chính ta vừa gửi, nếu không sẽ tự trả
        lời chính mình thành vòng lặp vô tận) và các sự kiện vòng đời khác.
        """
        if payload.get("event") != "message_created":
            return None
        if payload.get("message_type") != "incoming":
            return None

        text = payload.get("content")
        if not isinstance(text, str) or not text.strip():
            return None      # ảnh, file, tin hệ thống — chưa xử lý

        conv = payload.get("conversation") or {}
        conv_id = str(conv.get("id") or "")
        if not conv_id:
            return None

        sender = payload.get("sender") or {}
        # Nền tảng gốc nằm trong conversation.channel, ví dụ
        # "Channel::FacebookPage". Giữ lại để dashboard gắn đúng huy hiệu.
        goc = str(conv.get("channel") or "").replace("Channel::", "") or "Chatwoot"

        return InboundMessage(
            channel=self.name,
            conversation_ref=conv_id,
            customer_ref=str(sender.get("id") or conv_id),
            customer_name=str(sender.get("name") or "Khách"),
            text=text.strip(),
            dedupe_key=f"{self.name}:{payload.get('id')}",
            received_at=_thoi_diem(payload.get("created_at")),
            meta={"nen_tang_goc": goc},
        )

    async def fetch_new(self, per_conversation: int = 8) -> list[InboundMessage]:
        """Chatwoot đẩy bằng webhook, không cần kéo."""
        return []

    # ---------------- ra ----------------

    async def send_text(self, conversation_ref: str, text: str) -> Delivery:
        if not self.cau_hinh_du():
            return Delivery(False, "Chưa cấu hình CHATWOOT_* trong .env")
        try:
            r = await self._client.post(
                f"/api/v1/accounts/{settings.chatwoot_account_id}"
                f"/conversations/{conversation_ref}/messages",
                json={"content": text, "message_type": "outgoing"},
            )
        except httpx.HTTPError as exc:
            return Delivery(False, str(exc)[:200])
        if r.status_code < 400:
            return Delivery(True)
        return Delivery(False, f"{r.status_code} {r.text[:200]}")

    async def send_file(
        self, conversation_ref: str, path: str, caption: str = ""
    ) -> Delivery:
        """Chatwoot nhận file qua multipart, khác hẳn ZaloCRM chỉ có văn bản."""
        if not os.path.exists(path):
            return Delivery(False, f"không thấy file: {path}")
        try:
            with open(path, "rb") as fh:
                r = await self._client.post(
                    f"/api/v1/accounts/{settings.chatwoot_account_id}"
                    f"/conversations/{conversation_ref}/messages",
                    data={"content": caption, "message_type": "outgoing"},
                    files={"attachments[]": (os.path.basename(path), fh)},
                )
        except httpx.HTTPError as exc:
            return Delivery(False, str(exc)[:200])
        if r.status_code < 400:
            return Delivery(True)
        return Delivery(False, f"{r.status_code} {r.text[:200]}")

    async def aclose(self) -> None:
        await self._client.aclose()


def _thoi_diem(value) -> datetime:
    if isinstance(value, (int, float)):      # Chatwoot trả epoch giây
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
