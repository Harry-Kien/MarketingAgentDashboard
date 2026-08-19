"""
Ranh giới kênh — mảnh kiến trúc quan trọng nhất của hệ thống.

Mọi thứ phía trên lớp này (agent, RAG, video, dashboard) KHÔNG được biết
mình đang chạy trên Zalo cá nhân hay Zalo OA. Chuyển giai đoạn 1 -> 2
chỉ là viết thêm một lớp con, không đụng phần còn lại.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class InboundMessage:
    """Tin nhắn đã chuẩn hoá, không còn dấu vết của kênh gốc."""

    channel: str
    conversation_ref: str          # id hội thoại phía kênh
    customer_ref: str              # id khách phía kênh
    customer_name: str
    text: str
    dedupe_key: str                # để chống xử lý trùng
    received_at: datetime
    attachments: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Delivery:
    ok: bool
    detail: str = ""


class ChannelAdapter(ABC):
    """Hợp đồng mà mọi kênh phải tuân thủ."""

    name: str = "base"

    @abstractmethod
    def parse(self, payload: dict) -> InboundMessage | None:
        """Chuyển payload webhook thô thành InboundMessage. None = bỏ qua."""

    @abstractmethod
    async def send_text(self, conversation_ref: str, text: str) -> Delivery: ...

    @abstractmethod
    async def send_file(
        self, conversation_ref: str, path: str, caption: str = ""
    ) -> Delivery: ...

    async def can_send_now(self, conversation_ref: str) -> bool:
        """
        Kênh có cho phép gửi chủ động lúc này không?

        Zalo cá nhân (GĐ1): luôn True.
        Zalo OA (GĐ2): chỉ True trong cửa sổ 48h kể từ tin cuối của khách;
        ngoài cửa sổ phải dùng ZNS với template đã duyệt.
        Toàn bộ phần trên chỉ cần hỏi hàm này, không cần biết luật của kênh.
        """
        return True
