"""
Lớp mỏng giữ tương thích ngược.

Bộ dựng đã tách thành package `agent.video.renderers` (ba bậc: veo,
hyperframes, ffmpeg) vì file này phình quá nhanh khi thêm ảnh sản phẩm.
Mã mới nên gọi thẳng:

    from agent.video import renderers
    result = await renderers.render(renderers.RenderContext(...))

File này chỉ còn để mã cũ gọi theo chữ ký bốn tham số khỏi gãy.
"""
from __future__ import annotations

from agent.video.renderers import layout
from agent.video.renderers import render_legacy as render

WIDTH, HEIGHT, FPS = layout.WIDTH, layout.HEIGHT, 30

__all__ = ["render", "_font", "WIDTH", "HEIGHT", "FPS"]


def _font() -> str | None:
    """Đường dẫn font đang dùng. Giữ tên cũ cho `scripts/test_render.py`."""
    return layout.font_path()
