"""
Adapter cho ZaloCRM (giai đoạn 1 — Zalo cá nhân).

QUAN TRỌNG: chạy ZaloCRM NGUYÊN BẢN, không fork, không sửa.
Ta chỉ gọi Public API của nó. Nhờ vậy nghĩa vụ copyleft AGPL được giữ
trong đúng container đó, không lan sang mã nguồn này.

VÌ SAO POLLING CHỨ KHÔNG PHẢI WEBHOOK
-------------------------------------
ZaloCRM CÓ bắn webhook `message.received`, nhưng `webhook-service.ts` chạy
mọi URL qua một chốt chặn SSRF (`shared/utils/ssrf-guard.ts`) từ chối:
  - mọi giao thức không phải HTTPS
  - localhost, 127.0.0.0/8, RFC1918 (10/8, 172.16/12, 192.168/16), link-local
`http://host.docker.internal:8000/webhook` vi phạm cả hai, nên webhook sẽ bị
chặn ngay trước lúc gửi và chỉ ghi một dòng cảnh báo. Không sửa được nếu
không đụng vào mã ZaloCRM — mà đó là điều ta cố ý tránh.

Nên giai đoạn 1 dùng polling. Giai đoạn 2 (Zalo OA) là webhook thật, và nhờ
lớp ChannelAdapter, phần trên không đổi một dòng nào.

HỢP ĐỒNG API (đọc từ backend/src/modules/api/public-api-routes.ts)
  GET  /api/public/conversations?limit=N
       -> {conversations:[{id, threadType, externalThreadId, lastMessageAt,
                           unreadCount, isReplied, contact:{id,fullName,...}}]}
  GET  /api/public/conversations/{id}/messages?limit=N     (mới nhất trước)
       -> {messages:[{id, senderType, senderName, content, contentType, sentAt}]}
  POST /api/public/messages/send
       body {zaloAccountId, threadId, content, threadType}
  Xác thực: header X-API-Key
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from agent.channels.base import ChannelAdapter, Delivery, InboundMessage
from agent import db, runtime
from agent.config import settings

# senderType trong ZaloCRM: 'contact' = khách, 'self' = mình, 'ai_assistant' = AI
INBOUND_SENDER = "contact"


class ZaloCRMAdapter(ChannelAdapter):
    name = "zalocrm"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.zalocrm_base_url.rstrip("/"),
            headers={"X-API-Key": settings.zalocrm_api_key},
            timeout=20.0,
        )
        # conversation id -> (externalThreadId, threadType). Nạp dần khi polling,
        # dùng lúc gửi vì API gửi cần thread id phía Zalo, không phải id nội bộ.
        self._threads: dict[str, tuple[str, str]] = {}

    # ---------------- vào: polling ----------------

    async def fetch_new(self, per_conversation: int = 8) -> list[InboundMessage]:
        """
        Lấy tin nhắn khách mới. KHÔNG tự chống trùng — việc đó do
        db.seen_webhook() làm, dựa trên dedupe_key.
        """
        if not settings.zalocrm_api_key:
            return []

        try:
            r = await self._client.get(
                "/api/public/conversations", params={"limit": 40}
            )
            r.raise_for_status()
            conversations = r.json().get("conversations", [])
        except (httpx.HTTPError, ValueError):
            return []

        out: list[InboundMessage] = []
        for conv in conversations:
            conv_id = str(conv.get("id") or "")
            if not conv_id:
                continue

            self._threads[conv_id] = (
                str(conv.get("externalThreadId") or ""),
                str(conv.get("threadType") or "user"),
            )
            contact = conv.get("contact") or {}
            customer_name = contact.get("fullName") or "Khách"
            customer_ref = str(contact.get("id") or conv_id)

            try:
                m = await self._client.get(
                    f"/api/public/conversations/{conv_id}/messages",
                    params={"limit": per_conversation},
                )
                m.raise_for_status()
                messages = m.json().get("messages", [])
            except (httpx.HTTPError, ValueError):
                continue

            # API trả mới nhất trước; đảo lại để xử lý theo thứ tự thời gian.
            for msg in reversed(messages):
                if str(msg.get("senderType") or "") != INBOUND_SENDER:
                    continue
                text = msg.get("content")
                if not isinstance(text, str) or not text.strip():
                    continue  # MVP chỉ xử lý tin văn bản

                out.append(
                    InboundMessage(
                        channel=self.name,
                        conversation_ref=conv_id,
                        customer_ref=customer_ref,
                        customer_name=customer_name,
                        text=text.strip(),
                        dedupe_key=f"{self.name}:{msg.get('id')}",
                        received_at=_parse_time(msg.get("sentAt")),
                    )
                )
        return out

    # `parse` giữ lại cho đường webhook (Zalo OA ở giai đoạn 2).
    def parse(self, payload: dict) -> InboundMessage | None:
        body = payload.get("data", payload)
        text = body.get("content") or body.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        conv_id = str(body.get("conversationId") or body.get("threadId") or "")
        if not conv_id:
            return None
        return InboundMessage(
            channel=self.name,
            conversation_ref=conv_id,
            customer_ref=str(body.get("contactId") or conv_id),
            customer_name=str(body.get("senderName") or "Khách"),
            text=text.strip(),
            dedupe_key=f"{self.name}:{body.get('messageId') or body.get('id')}",
            received_at=_parse_time(body.get("sentAt")),
        )

    # ---------------- ra ----------------

    async def _thread_of(self, conversation_ref: str) -> tuple[str, str] | None:
        if conversation_ref in self._threads:
            return self._threads[conversation_ref]
        try:  # chưa có trong cache -> nạp lại danh sách một lần
            r = await self._client.get(
                "/api/public/conversations", params={"limit": 100}
            )
            r.raise_for_status()
            for c in r.json().get("conversations", []):
                self._threads[str(c.get("id"))] = (
                    str(c.get("externalThreadId") or ""),
                    str(c.get("threadType") or "user"),
                )
        except (httpx.HTTPError, ValueError):
            return None
        return self._threads.get(conversation_ref)

    async def _nick_gui(self, conversation_ref: str) -> str:
        """
        Chọn nick Zalo để gửi, theo thứ tự:
            nick đã ghim cho hội thoại này  ->  nick đang chọn trên
            dashboard  ->  nick trong .env

        Ghim theo hội thoại là bắt buộc khi doanh nghiệp chạy nhiều nick:
        khách nhắn vào nick A mà trả lời đi ra từ nick B thì với khách đó
        là một người lạ nhắn tin, không phải câu trả lời.
        """
        row = await db.fetchrow(
            "SELECT zalo_account_id FROM conversations "
            "WHERE channel = $1 AND external_id = $2",
            self.name, conversation_ref,
        )
        if row and row["zalo_account_id"]:
            return str(row["zalo_account_id"])
        return str(runtime.STATE.get("zalo_account_id") or
                   settings.zalocrm_account_id or "")

    async def send_text(self, conversation_ref: str, text: str) -> Delivery:
        account_id = await self._nick_gui(conversation_ref)
        if not account_id:
            return Delivery(
                False,
                "Chưa chọn nick Zalo để gửi. Vào màn Hội thoại trên dashboard "
                "chọn nick, hoặc chạy: python -m scripts.zalo_link sau khi quét QR.",
            )
        thread = await self._thread_of(conversation_ref)
        if not thread or not thread[0]:
            return Delivery(False, f"Không tra được thread cho hội thoại {conversation_ref}")

        external_id, thread_type = thread
        try:
            r = await self._client.post(
                "/api/public/messages/send",
                json={
                    "zaloAccountId": account_id,
                    "threadId": external_id,
                    "content": text,
                    "threadType": thread_type,
                },
            )
        except httpx.HTTPError as exc:
            return Delivery(False, str(exc))

        if r.status_code < 400:
            return Delivery(True)
        return Delivery(False, f"{r.status_code} {r.text[:200]}")

    async def send_file(
        self, conversation_ref: str, path: str, caption: str = ""
    ) -> Delivery:
        """
        Public API của ZaloCRM chưa có endpoint gửi file. Gửi kèm đường dẫn
        dưới dạng văn bản để nhân viên tự đính kèm — thà nói rõ còn hơn im lặng.
        """
        if not os.path.exists(path):
            return Delivery(False, f"không thấy file: {path}")
        note = f"{caption}\n[Video đã dựng xong: {os.path.basename(path)}]".strip()
        result = await self.send_text(conversation_ref, note)
        if result.ok:
            return Delivery(True, "đã gửi thông báo (API chưa hỗ trợ đính kèm file)")
        return result

    async def aclose(self) -> None:
        await self._client.aclose()


def _parse_time(value) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
