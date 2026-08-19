"""
Hợp đồng chung của ba bậc dựng hình.

Mọi backend nhận cùng một `RenderContext` và trả cùng một `RenderResult`.
Nhờ vậy `pipeline.py` không cần biết bậc nào đang chạy, và thêm bậc mới
(Veo, hay thứ gì đó sau này) không phải sửa dây chuyền.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RenderContext:
    title: str
    scenes: list[dict]
    audio_dir: Path
    out_path: Path
    # Ảnh sản phẩm đã qua bước nhìn: {ord, file_path, analysis, usable}
    assets: list[dict] = field(default_factory=list)
    subtitles: bool = True

    def asset_for(self, scene: dict) -> dict | None:
        """
        Ảnh của một cảnh, theo `anh_index` mà bước kịch bản gán.

        Không tin chỉ số model trả về: ngoài phạm vi thì quay vòng, không có
        ảnh nào thì trả None và cảnh rơi về nền màu. Model gán sai không được
        phép làm hỏng cả video.
        """
        if not self.assets:
            return None
        idx = scene.get("anh_index")
        if not isinstance(idx, int):
            return None
        return self.assets[idx % len(self.assets)]

    @property
    def has_images(self) -> bool:
        return bool(self.assets)


@dataclass
class RenderResult:
    ok: bool
    backend: str
    detail: str = ""
