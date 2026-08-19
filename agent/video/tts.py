"""
Giọng đọc tiếng Việt qua viet-tts (API tương thích chuẩn OpenAI TTS).

Thiếu dịch vụ này hệ thống vẫn chạy — video sẽ không lời và timeline dùng
ước lượng âm tiết. Nhưng đó là chế độ suy giảm, không phải kiến trúc đúng.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from agent.config import settings


async def available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(settings.tts_base_url.rstrip("/").rsplit("/v1", 1)[0] + "/")
        return r.status_code < 500
    except httpx.HTTPError:
        return False


async def synthesize(text: str, out_path: Path) -> Path | None:
    """Đọc `text` thành file wav. Trả None nếu dịch vụ không sẵn sàng."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": "tts-1",
        "input": text,
        "voice": settings.tts_voice,
        "response_format": "wav",
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.post(
                settings.tts_base_url.rstrip("/") + "/audio/speech", json=payload
            )
        if r.status_code >= 400 or not r.content:
            return None
        out_path.write_bytes(r.content)
        return out_path
    except httpx.HTTPError:
        return None
