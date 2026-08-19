"""
Thang ba bậc dựng hình, tự tụt xuống bậc dưới khi bậc trên chưa sẵn sàng.

    veo  ->  hyperframes  ->  ffmpeg

Bậc dưới cùng KHÔNG có điều kiện gì ngoài ffmpeg trong PATH, nên dây chuyền
không bao giờ đứng vì thiếu hạ tầng. Đây là mở rộng của cơ chế hai bậc vốn
có, không phải kiến trúc mới.

Lý do từng bậc bị bỏ qua được gom lại và ghi vào thẻ video — để khi bạn tưởng
đang dùng Veo mà thật ra đang dùng ffmpeg thì nhìn là biết ngay, thay vì phải
đoán.
"""
from __future__ import annotations

from pathlib import Path

from agent.video.renderers import ffmpeg, hyperframes, layout, subtitles, veo
from agent.video.renderers.base import RenderContext, RenderResult

__all__ = [
    "RenderContext",
    "RenderResult",
    "render",
    "render_legacy",
    "layout",
    "subtitles",
]

LADDER = (
    ("veo", veo.render),
    ("hyperframes", hyperframes.render),
    ("ffmpeg", ffmpeg.render),
)


async def render(ctx: RenderContext) -> RenderResult:
    """Chạy lần lượt từ bậc cao xuống bậc thấp, dừng ở bậc đầu tiên thành công."""
    skipped: list[str] = []

    for name, fn in LADDER:
        try:
            ok, detail = await fn(ctx)
        except Exception as exc:  # noqa: BLE001 — một bậc hỏng không được chặn bậc sau
            skipped.append(f"{name}: {type(exc).__name__}: {exc}"[:180])
            continue

        if ok:
            note = detail
            if skipped:
                note = f"{detail} (bỏ qua: {'; '.join(skipped)})"
            return RenderResult(ok=True, backend=name, detail=note[:600])

        skipped.append(f"{name}: {detail}"[:180])

    return RenderResult(ok=False, backend="none", detail=" | ".join(skipped)[:900])


async def render_legacy(
    title: str, scenes: list[dict], audio_dir: Path, out_path: Path
):
    """Chữ ký cũ (không ảnh), giữ cho mã gọi cũ khỏi gãy."""
    result = await render(
        RenderContext(
            title=title, scenes=scenes, audio_dir=audio_dir, out_path=out_path
        )
    )
    return result.ok, result.backend, result.detail
