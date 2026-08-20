"""
Lớp gọi model — trung lập với nhà cung cấp.

Hỗ trợ 3 đường, đổi bằng LLM_PROVIDER trong .env:
  gemini    - Gemini trên Vertex AI (MẶC ĐỊNH). Cùng project, cùng ADC với
              embedding của RAG. Hạn mức Gemini tách biệt với hạn mức Claude.
  vertex    - Claude trên Vertex AI. Cần project ĐƯỢC CẤP QUOTA Claude;
              project mới mặc định quota = 0 và mọi lời gọi trả 429.
  anthropic - Claude qua API trực tiếp, chỉ cần API key.

ĐỊNH DẠNG TRUNG LẬP
-------------------
Phần trên (agent.py) không được biết mình đang nói chuyện với nhà cung cấp
nào. Nó dựng danh sách `messages` theo dạng dưới đây, lớp này dịch sang
định dạng riêng của từng bên:

    {"role": "user",      "content": "..."}
    {"role": "assistant", "content": "...", "tool_calls": [{id,name,input}]}
    {"role": "tool",      "results": [{id, name, output: dict}]}

`content` của vai "user" nhận thêm dạng DANH SÁCH KHỐI, để gửi kèm ảnh:

    {"role": "user", "content": [
        {"type": "text",  "text": "..."},
        {"type": "image", "media_type": "image/jpeg", "data": "<base64>"},
    ]}

Dạng chuỗi thuần vẫn chạy y như cũ — mọi lời gọi hiện có không phải sửa.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import httpx

from agent.config import settings

# Giá niêm yết USD / 1 triệu token (input, output).
# Claude: giá chính thức. Gemini: xấp xỉ — kiểm tra lại trên bảng giá GCP.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
}
MAX_RETRIES = 4          # cho 429/503 tam thoi cua Vertex
CACHE_READ_RATE = 0.10
CACHE_WRITE_RATE = 1.25


@dataclass(slots=True)
class LLMResult:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    tool_calls: list[dict] = field(default_factory=list)
    stop_reason: str = ""


def provider() -> str:
    return (settings.llm_provider or "gemini").strip().lower()


def price(model: str, t_in: int, t_out: int, c_read: int = 0, c_write: int = 0) -> float:
    p_in, p_out = PRICING.get(model, (1.0, 5.0))
    return (
        t_in * p_in
        + c_read * p_in * CACHE_READ_RATE
        + c_write * p_in * CACHE_WRITE_RATE
        + t_out * p_out
    ) / 1_000_000


def parse_json(text: str) -> dict | None:
    """
    Gỡ JSON ra khỏi câu trả lời của model.

    Model đôi khi bọc JSON trong khối mã dù đã dặn không, hoặc kèm một câu
    dẫn. Thử lần lượt: nguyên văn -> bỏ rào khối mã -> bốc cặp ngoặc ngoài
    cùng. Không ra thì trả None để người gọi tự quyết, không ném lỗi.
    """
    import re

    cleaned = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def cached_system(stable: str, volatile: str = "") -> dict:
    """
    Gói system prompt. Phần ỔN ĐỊNH tách khỏi phần BIẾN ĐỘNG để lớp dưới
    đặt điểm cache đúng chỗ — đặt ngược lại là mọi request đều ghi cache mới
    và không bao giờ đọc lại được.
    """
    return {"stable": stable, "volatile": volatile}


# ===============================================================
#  Gemini trên Vertex AI
# ===============================================================

_creds = None


def _vertex_token() -> str:
    """Token ADC, tự làm mới khi hết hạn. ĐỒNG BỘ — xem _token() bên dưới."""
    global _creds
    import google.auth
    import google.auth.transport.requests

    if _creds is None:
        _creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    if not _creds.valid:
        _creds.refresh(google.auth.transport.requests.Request())
    return _creds.token


async def _token() -> str:
    """
    Lấy token ADC mà KHÔNG chặn vòng lặp sự kiện.

    `_creds.refresh()` của google-auth là lời gọi mạng ĐỒNG BỘ. Gọi thẳng
    nó trong coroutine thì trong lúc chờ, toàn bộ tiến trình đứng im: poller
    ngừng lấy tin Zalo, API dashboard ngừng trả lời, hàng đợi bài đăng ngừng
    chạy. Token hết hạn mỗi giờ nên chuyện này xảy ra đều đặn, và khi mạng
    tới GCP chậm thì cả hệ thống treo theo mà không có dấu vết gì trong log.

    `to_thread` đẩy nó sang luồng khác; `wait_for` đặt trần thời gian để một
    lần làm mới hỏng không kéo dài vô hạn.
    """
    try:
        return await asyncio.wait_for(asyncio.to_thread(_vertex_token), timeout=30)
    except asyncio.TimeoutError as exc:
        raise RuntimeError(
            "Quá 30 giây không lấy được token Vertex. Kiểm tra mạng tới GCP "
            "hoặc chạy lại: gcloud auth application-default login"
        ) from exc


def _gemini_url(model: str) -> str:
    region = settings.gemini_region or "us-central1"
    host = (
        "aiplatform.googleapis.com"
        if region == "global"
        else f"{region}-aiplatform.googleapis.com"
    )
    return (
        f"https://{host}/v1/projects/{settings.gcp_project_id}"
        f"/locations/{region}/publishers/google/models/{model}:generateContent"
    )


def _gemini_parts(content) -> list[dict]:
    """Nội dung vai user -> `parts` của Gemini. Chuỗi thuần hoặc danh sách khối."""
    if isinstance(content, str):
        return [{"text": content}]
    parts: list[dict] = []
    for blk in content or []:
        if blk.get("type") == "image":
            parts.append(
                {
                    "inlineData": {
                        "mimeType": blk.get("media_type", "image/jpeg"),
                        "data": blk["data"],
                    }
                }
            )
        elif blk.get("text"):
            parts.append({"text": blk["text"]})
    return parts or [{"text": ""}]


def _anthropic_content(content):
    """Nội dung vai user -> khối của Anthropic. Chuỗi thuần đi thẳng."""
    if isinstance(content, str):
        return content
    blocks: list[dict] = []
    for blk in content or []:
        if blk.get("type") == "image":
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": blk.get("media_type", "image/jpeg"),
                        "data": blk["data"],
                    },
                }
            )
        elif blk.get("text"):
            blocks.append({"type": "text", "text": blk["text"]})
    return blocks or ""


def _to_gemini(messages: list[dict], tools: list[dict] | None) -> tuple[list, list]:
    """Dịch định dạng trung lập -> `contents` + `tools` của Gemini."""
    contents: list[dict] = []
    for m in messages:
        role = m.get("role")

        if role == "user":
            contents.append({"role": "user", "parts": _gemini_parts(m["content"])})

        elif role == "assistant":
            parts: list[dict] = []
            if m.get("content"):
                parts.append({"text": m["content"]})
            for call in m.get("tool_calls") or []:
                parts.append(
                    {"functionCall": {"name": call["name"], "args": call["input"]}}
                )
            if parts:
                contents.append({"role": "model", "parts": parts})

        elif role == "tool":
            # Gemini khớp kết quả theo TÊN hàm, không theo id như Anthropic.
            parts = [
                {
                    "functionResponse": {
                        "name": r["name"],
                        "response": r["output"] if isinstance(r["output"], dict)
                        else {"result": r["output"]},
                    }
                }
                for r in m.get("results") or []
            ]
            if parts:
                contents.append({"role": "user", "parts": parts})

    gem_tools = []
    if tools:
        gem_tools = [
            {
                "functionDeclarations": [
                    {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    }
                    for t in tools
                ]
            }
        ]
    return contents, gem_tools


# Ngân sách token SUY NGHĨ của Gemini 2.5, theo mức effort.
#
# Đây là cái bẫy: token suy nghĩ ĐẾM VÀO `maxOutputTokens` nhưng KHÔNG hiện
# trong `candidatesTokenCount`. Nên một lời gọi có thể dừng vì MAX_TOKENS
# trong khi báo cáo chỉ 465 token ra — nhìn như model tự ý cắt ngang. Đúng
# lỗi đó đã làm hỏng bước viết kịch bản video.
#
# Trước đây `effort` chỉ có tác dụng với Claude; Gemini bỏ qua hoàn toàn dù
# nó là nhà cung cấp MẶC ĐỊNH của hệ thống này.
THINKING_BUDGET = {"low": 0, "medium": 1024, "high": 8192, "max": 24576}


async def _complete_gemini(
    *, system: dict, messages: list[dict], model: str, max_tokens: int,
    tools: list[dict] | None, effort: str = "medium",
) -> LLMResult:
    if not settings.gcp_project_id or settings.gcp_project_id.startswith("your-"):
        raise RuntimeError("Chưa đặt GCP_PROJECT_ID trong .env")

    contents, gem_tools = _to_gemini(messages, tools)
    sys_text = "\n\n".join(x for x in (system.get("stable"), system.get("volatile")) if x)

    ngan_sach = THINKING_BUDGET.get(effort, 1024)
    body: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.3,
            # Chặn trần phần suy nghĩ để nó không nuốt hết chỗ dành cho câu
            # trả lời. Không đặt thì Gemini 2.5 tự quyết, và với việc trả JSON
            # dài nó hay tiêu gần hết ngân sách vào suy nghĩ rồi bị cắt ngang.
            "thinkingConfig": {"thinkingBudget": ngan_sach},
        },
    }
    if sys_text:
        body["systemInstruction"] = {"parts": [{"text": sys_text}]}
    if gem_tools:
        body["tools"] = gem_tools

    started = time.perf_counter()
    # 429/503 trên Vertex là giới hạn tốc độ tạm thời, không phải hết hạn mức.
    # Thử lại có giãn cách thay vì để cả lượt trả lời của khách thất bại.
    delay = 2.0
    last = ""
    async with httpx.AsyncClient(timeout=120.0) as client:
        for attempt in range(MAX_RETRIES):
            r = await client.post(
                _gemini_url(model),
                headers={
                    "Authorization": f"Bearer {await _token()}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if r.status_code < 400:
                break
            last = f"Gemini {r.status_code}: {r.text[:300]}"
            if r.status_code not in (429, 503) or attempt == MAX_RETRIES - 1:
                raise RuntimeError(last)
            await asyncio.sleep(delay)
            delay *= 2
        else:  # pragma: no cover
            raise RuntimeError(last)

    data = r.json()
    candidates = data.get("candidates") or []
    text_parts, tool_calls = [], []
    if candidates:
        for part in candidates[0].get("content", {}).get("parts", []) or []:
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(
                    {
                        # Gemini không cấp id; tự sinh để phần trên dùng thống nhất.
                        "id": f"call_{len(tool_calls)}_{fc.get('name')}",
                        "name": fc.get("name"),
                        "input": fc.get("args") or {},
                    }
                )

    u = data.get("usageMetadata") or {}
    t_in = int(u.get("promptTokenCount") or 0)
    t_out = int(u.get("candidatesTokenCount") or 0)
    c_read = int(u.get("cachedContentTokenCount") or 0)

    return LLMResult(
        text="".join(text_parts).strip(),
        model=model,
        tokens_in=max(0, t_in - c_read),
        tokens_out=t_out,
        cache_read=c_read,
        cost_usd=price(model, max(0, t_in - c_read), t_out, c_read),
        latency_ms=int((time.perf_counter() - started) * 1000),
        tool_calls=tool_calls,
        stop_reason=(candidates[0].get("finishReason") if candidates else "") or "",
    )


# ===============================================================
#  Claude (Vertex hoặc API trực tiếp)
# ===============================================================

@lru_cache
def _anthropic_client():
    if provider() == "anthropic":
        from anthropic import Anthropic

        if not settings.anthropic_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=anthropic nhưng thiếu ANTHROPIC_API_KEY trong .env"
            )
        return Anthropic(api_key=settings.anthropic_api_key)

    from anthropic import AnthropicVertex

    if not settings.gcp_project_id or settings.gcp_project_id.startswith("your-"):
        raise RuntimeError("Chưa đặt GCP_PROJECT_ID trong .env")
    return AnthropicVertex(
        project_id=settings.gcp_project_id, region=settings.gcp_region
    )


def _to_anthropic(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        role = m.get("role")
        if role == "user":
            out.append({"role": "user", "content": _anthropic_content(m["content"])})
        elif role == "assistant":
            blocks: list[dict] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for call in m.get("tool_calls") or []:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call["id"],
                        "name": call["name"],
                        "input": call["input"],
                    }
                )
            if blocks:
                out.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            out.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": r["id"],
                            "content": json.dumps(r["output"], ensure_ascii=False),
                        }
                        for r in m.get("results") or []
                    ],
                }
            )
    return out


async def _complete_claude(
    *, system: dict, messages: list[dict], model: str, max_tokens: int,
    tools: list[dict] | None, effort: str,
) -> LLMResult:
    # Vertex KHÔNG có automatic prompt caching -> đặt cache_control thủ công
    # lên khối ổn định; ngữ cảnh RAG biến động nằm SAU điểm cache.
    blocks: list[dict] = [
        {
            "type": "text",
            "text": system.get("stable", ""),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if system.get("volatile"):
        blocks.append({"type": "text", "text": system["volatile"]})

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": blocks,
        "messages": _to_anthropic(messages),
        "output_config": {"effort": effort},
    }
    if tools:
        kwargs["tools"] = tools

    started = time.perf_counter()
    resp = _anthropic_client().messages.create(**kwargs)

    text_parts, tool_calls = [], []
    for block in resp.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(
                {"id": block.id, "name": block.name, "input": block.input}
            )

    u = resp.usage
    t_in = getattr(u, "input_tokens", 0) or 0
    t_out = getattr(u, "output_tokens", 0) or 0
    c_read = getattr(u, "cache_read_input_tokens", 0) or 0
    c_write = getattr(u, "cache_creation_input_tokens", 0) or 0

    return LLMResult(
        text="".join(text_parts).strip(),
        model=model,
        tokens_in=t_in,
        tokens_out=t_out,
        cache_read=c_read,
        cache_write=c_write,
        cost_usd=price(model, t_in, t_out, c_read, c_write),
        latency_ms=int((time.perf_counter() - started) * 1000),
        tool_calls=tool_calls,
        stop_reason=resp.stop_reason or "",
    )


# ===============================================================
#  Cửa vào duy nhất
# ===============================================================

async def complete(
    *,
    system: dict,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 4096,
    tools: list[dict] | None = None,
    effort: str = "medium",
) -> LLMResult:
    p = provider()
    model = model or settings.model_chat

    if p == "gemini":
        return await _complete_gemini(
            system=system, messages=messages, model=model,
            max_tokens=max_tokens, tools=tools, effort=effort,
        )
    if p in ("vertex", "anthropic"):
        return await _complete_claude(
            system=system, messages=messages, model=model,
            max_tokens=max_tokens, tools=tools, effort=effort,
        )
    raise RuntimeError(
        f"LLM_PROVIDER không hợp lệ: {p!r}. Nhận: gemini | vertex | anthropic."
    )
