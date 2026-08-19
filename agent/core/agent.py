"""
Bộ điều phối agent — nơi một tin nhắn của khách trở thành một câu trả lời.

Luồng:
    tin nhắn -> RAG lấy ngữ cảnh -> Claude (vòng lặp tool) -> quyết định gửi

Ba cơ chế an toàn nằm ở đây, không nằm trong prompt:
    1. Trần chi phí mỗi hội thoại -> vượt thì chuyển người.
    2. Chế độ assist -> agent soạn, người bấm gửi.
    3. Cờ escalate từ tool -> khoá hội thoại lại cho người xử lý.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from agent import db
from agent.config import ROOT, settings
from agent.core import llm, rag, tools

SYSTEM = (ROOT / "agent" / "prompts" / "system.md").read_text(encoding="utf-8")
MAX_TOOL_ROUNDS = 4


@dataclass(slots=True)
class Reply:
    text: str
    escalate: bool = False
    escalate_reason: str = ""
    grounded: bool = False
    confidence: float = 0.0
    sources: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    latency_ms: int = 0
    model: str = ""
    video_id: str | None = None



# ---------------------------------------------------------------
#  Chốt chặn CỨNG cho luật tuân thủ
# ---------------------------------------------------------------
# Với quy định về quảng cáo mỹ phẩm và ranh giới tư vấn y tế, KHÔNG được
# phó mặc cho model tự nhớ gọi tool. Nếu câu hỏi của khách chạm vào các
# tình huống dưới đây thì buộc chuyển người, bất kể model làm gì.
_BUOC_CHUYEN = (
    # thai kỳ và cho con bú
    "mang thai", "bầu", "có bầu", "cho con bú", "đang bú",
    # đang điều trị y tế
    "bác sĩ", "bac si", "theo toa", "đơn thuốc", "bôi thuốc", "uống thuốc",
    "đang điều trị", "da liễu",
    # bệnh lý da
    "viêm da", "mụn viêm", "mụn bọc", "mụn mủ", "nám", "chàm", "vẩy nến",
    "dị ứng", "kích ứng nặng",
    # da đang phản ứng
    "đỏ rát", "ngứa rát", "nổi sẩn", "sưng đỏ", "bong tróc", "phồng rộp",
)


def _bat_buoc_chuyen(question: str) -> str | None:
    low = (question or "").lower()
    for key in _BUOC_CHUYEN:
        if key in low:
            return f"Câu hỏi chạm vào tình huống bắt buộc chuyển người: '{key}'"
    return None


# Câu chữ cho thấy agent đang hứa chuyển hội thoại cho người thật.
_HANDOFF_HINTS = (
    "chuyển thông tin",
    "chuyển cho nhân viên",
    "chuyển anh",
    "chuyển chị",
    "chuyển mình",
    "chuyển qua cho",
    "chuyên môn tư vấn",
    "nhân viên bên em sẽ",
    "bạn phụ trách",
    "liên hệ lại với",
    "hỏi ý kiến bác sĩ",
    "trao đổi với bác sĩ",
)


def _promises_handoff(text: str) -> bool:
    low = (text or "").lower()
    return any(hint in low for hint in _HANDOFF_HINTS)


def _confidence(passages: list[rag.Passage], used_tool: bool) -> float:
    """
    Ước lượng độ tin cậy thô: điểm khớp RAG cao nhất, cộng thưởng nếu
    câu trả lời dựa trên dữ liệu hệ thống (tool) thay vì tài liệu.
    """
    base = max((p.score for p in passages), default=0.0)
    if used_tool:
        base = max(base, 0.8)
    return round(min(base, 0.99), 3)


async def respond(
    *, conversation_id: uuid.UUID, history: list[dict], question: str
) -> Reply:
    """Sinh câu trả lời cho một lượt. `history` là các lượt trước đã chuẩn hoá."""
    conv = await db.fetchrow(
        "SELECT cost_usd FROM conversations WHERE id = $1", conversation_id
    )
    spent = float(conv["cost_usd"]) if conv else 0.0
    if spent >= settings.max_cost_per_conversation:
        return Reply(
            text="Để em chuyển anh/chị sang nhân viên hỗ trợ trực tiếp nhé.",
            escalate=True,
            escalate_reason=f"Vượt trần chi phí hội thoại ({spent:.4f} USD)",
        )

    passages = await rag.retrieve(question, k=5)
    context = rag.as_context(passages)

    messages = [*history, {"role": "user", "content": question}]
    total_cost = 0.0
    tok_in = tok_out = cache_read = latency = 0
    used_tool = False
    escalate = False
    escalate_reason = ""
    video_id: str | None = None
    final_text = ""

    for _ in range(MAX_TOOL_ROUNDS):
        result = await llm.complete(
            # Phần ổn định mang cache_control; ngữ cảnh RAG biến động nằm SAU.
            system=llm.cached_system(SYSTEM, context),
            messages=messages,
            model=settings.model_chat,
            tools=tools.TOOLS,
            max_tokens=1500,
            effort="medium",
        )
        total_cost += result.cost_usd
        tok_in += result.tokens_in
        tok_out += result.tokens_out
        cache_read += result.cache_read
        latency += result.latency_ms

        if not result.tool_calls:
            final_text = result.text
            break

        used_tool = True
        # Định dạng TRUNG LẬP — lớp llm dịch sang Gemini hay Claude tuỳ provider.
        messages.append(
            {
                "role": "assistant",
                "content": result.text or "",
                "tool_calls": result.tool_calls,
            }
        )

        tool_results: list[dict] = []
        for call in result.tool_calls:
            out = await tools.run_tool(call["name"], call["input"], conversation_id)

            if call["name"] == "chuyen_nhan_vien":
                escalate = True
                escalate_reason = call["input"].get("ly_do", "")

            if call["name"] == "tao_video" and out.get("da_nhan"):
                from agent.video import pipeline

                video_id = await pipeline.request_video(
                    title=call["input"].get("tieu_de", "Video"),
                    brief=call["input"].get("yeu_cau", ""),
                    kind=call["input"].get("loai", "explainer"),
                    conversation_id=conversation_id,
                )
                out["video_id"] = video_id

            tool_results.append(
                {"id": call["id"], "name": call["name"], "output": out}
            )
        messages.append({"role": "tool", "results": tool_results})
        final_text = result.text or final_text
    else:
        final_text = final_text or "Em cần kiểm tra thêm, chuyển anh/chị cho nhân viên nhé."
        escalate = True
        escalate_reason = "Vượt số vòng gọi công cụ cho phép"

    confidence = _confidence(passages, used_tool)
    if confidence < settings.confidence_floor and not used_tool:
        escalate = True
        escalate_reason = escalate_reason or f"Độ tin cậy thấp ({confidence:.2f})"

    # Chốt chặn cứng: luật tuân thủ không được phụ thuộc vào việc model
    # có nhớ gọi tool hay không.
    if not escalate:
        buoc = _bat_buoc_chuyen(question)
        if buoc:
            escalate = True
            escalate_reason = buoc

    # LƯỚI AN TOÀN: model đôi khi VIẾT rằng sẽ chuyển người nhưng KHÔNG gọi
    # tool. Khách đọc thấy lời hứa, còn hội thoại thì không bao giờ tới tay
    # nhân viên. Không được để lời hứa với khách rơi vào khoảng không.
    if not escalate and _promises_handoff(final_text):
        escalate = True
        escalate_reason = "Agent nói sẽ chuyển người nhưng không gọi công cụ"

    return Reply(
        text=final_text.strip() or "Em chưa rõ ý anh/chị, anh/chị nói thêm giúp em nhé.",
        escalate=escalate,
        escalate_reason=escalate_reason,
        grounded=bool(passages) or used_tool,
        confidence=confidence,
        sources=[p.doc_title for p in passages],
        cost_usd=total_cost,
        tokens_in=tok_in,
        tokens_out=tok_out,
        cache_read=cache_read,
        latency_ms=latency,
        model=settings.model_chat,
        video_id=video_id,
    )
