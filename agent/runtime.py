"""
Trạng thái vận hành thay đổi được lúc chạy — không cần khởi động lại.

`enabled = False` là công tắc ngắt: mọi tin nhắn chuyển thẳng cho người.
Doanh nghiệp sẽ hỏi về nút này trước khi hỏi bất cứ điều gì khác.
"""
from __future__ import annotations

from agent.config import settings

STATE: dict[str, object] = {
    "enabled": settings.agent_enabled,
    "mode": settings.agent_mode,               # assist | auto
    "confidence_floor": settings.confidence_floor,
    "max_cost_per_conversation": settings.max_cost_per_conversation,
}


def enabled() -> bool:
    return bool(STATE["enabled"])


def mode() -> str:
    return str(STATE["mode"])


def update(**fields) -> dict:
    allowed = set(STATE)
    for k, v in fields.items():
        if k in allowed and v is not None:
            STATE[k] = v
    return dict(STATE)


# Hội thoại agent đang soạn trả lời — dashboard dùng để vẽ bong bóng "đang gõ".
BUSY: set[str] = set()


def mark_busy(conversation_id) -> None:
    BUSY.add(str(conversation_id))


def clear_busy(conversation_id) -> None:
    BUSY.discard(str(conversation_id))


def is_busy(conversation_id) -> bool:
    return str(conversation_id) in BUSY
