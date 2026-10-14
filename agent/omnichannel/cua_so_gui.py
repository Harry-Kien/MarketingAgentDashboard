"""
Tin của NGƯỜI (nhân viên) có gửi được lúc này không — xét TRƯỚC khi xếp hàng.

VÌ SAO PHẢI XÉT Ở API, KHÔNG ĐỂ WORKER TỰ THẤT BẠI
-------------------------------------------------
Đo được 14.10.2026: agent tự gửi và thông báo chuyển người đều hỏi
`can_send_now()` trước khi xếp hàng (`agent/main.py`), tin nhân viên thì
không. Người trực trả lời một khách nhắn từ hôm qua: tin vào outbox, Meta
từ chối vì ngoài cửa sổ 24 giờ, outbox thử tám lần rồi `dead`. Trên màn
hình tin hiện như đã gửi, khách không bao giờ nhận, không ai biết.

Thất bại ở API thì người trực thấy NGAY, kèm lý do, và còn chọn được việc
khác: gọi điện, nhắn Zalo cá nhân, chờ khách nhắn lại.

THẺ HUMAN_AGENT
---------------
Meta cho nhân viên trả lời tới 7 ngày sau tin cuối của khách nếu tin mang
thẻ HUMAN_AGENT — nhưng chỉ khi ứng dụng đã được Meta duyệt tính năng Human
Agent. Gửi thẻ khi chưa được duyệt thì Meta từ chối y như cũ, nên thẻ chỉ
gắn khi `META_THE_HUMAN_AGENT=true` — người vận hành bật SAU khi được duyệt.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from agent import db
from agent.channels.base import con_trong_cua_so
from agent.channels.registry import get_for_account
from agent.config import settings

log = logging.getLogger(__name__)

# Messenger (cả bản "facebook" kế thừa) và Instagram nhận thẻ HUMAN_AGENT.
# WhatsApp dùng mẫu tin đã duyệt — cơ chế khác hẳn, không phải thẻ.
KENH_HUMAN_AGENT = frozenset({"messenger", "facebook", "instagram"})
GIO_HUMAN_AGENT = 24 * 7


@dataclass(frozen=True)
class QuyetDinhGui:
    duoc: bool
    the: str | None = None
    ly_do: str = ""


async def xet_tin_nhan_vien(conversation_id: UUID) -> QuyetDinhGui:
    conv = await db.fetchrow(
        "SELECT account_id, channel, external_id FROM conversations WHERE id = $1",
        conversation_id)
    if conv is None:
        return QuyetDinhGui(True)          # để route trả 404 như cũ

    try:
        adapter = await get_for_account(conv["account_id"])
    except Exception:  # noqa: BLE001 — xem docstring test cùng tên
        # Không dựng được adapter ở đây thì worker cũng không dựng được, và
        # job thất bại CÓ ghi lỗi. Chặn ở đây là chặn luôn kênh đang cấu
        # hình dở mà người trực không biết vì sao. Ghi lại để có dấu vết.
        log.warning("không dựng được adapter cho %s khi xét cửa sổ gửi",
                    conv["account_id"], exc_info=True)
        return QuyetDinhGui(True)

    ref = conv["external_id"]
    if await adapter.can_send_now(ref):
        return QuyetDinhGui(True)

    if adapter.name in KENH_HUMAN_AGENT:
        if not settings.meta_the_human_agent:
            return QuyetDinhGui(False, ly_do=(
                "Khách nhắn lần cuối đã hơn 24 giờ. Meta chỉ cho trả lời sau "
                "24 giờ khi ứng dụng đã được duyệt tính năng Human Agent — được "
                "duyệt rồi thì bật META_THE_HUMAN_AGENT=true. Trong lúc chờ: "
                "gọi điện hoặc đợi khách nhắn lại."))
        if await con_trong_cua_so(adapter.name, ref, GIO_HUMAN_AGENT,
                                  account_id=adapter.account_id):
            return QuyetDinhGui(True, the="HUMAN_AGENT")
        return QuyetDinhGui(False, ly_do=(
            "Khách nhắn lần cuối đã hơn 7 ngày — Meta không cho nhắn tiếp cho "
            "tới khi khách nhắn lại. Liên hệ khách qua kênh khác."))

    return QuyetDinhGui(False, ly_do=(
        "Ngoài cửa sổ nhắn tin của kênh này (tính từ tin cuối của khách) — "
        "nền tảng sẽ từ chối tin. Chờ khách nhắn lại hoặc liên hệ qua kênh khác."))
