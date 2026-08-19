"""
Đo thời lượng âm thanh — mảnh ghép làm nên "video khớp đúng nội dung".

Nguyên tắc: TIMELINE SUY RA TỪ ÂM THANH, không bao giờ ngược lại.
Để model tự đoán "cảnh này chắc 5 giây" là nguyên nhân kinh điển khiến
video AI bị lệch lời — hình chuyển trước khi nói xong, hoặc treo im lặng.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from agent.config import settings

# Tốc độ đọc tiếng Việt tự nhiên, dùng khi CHƯA có TTS.
SYLLABLES_PER_SECOND = 4.6
MIN_SCENE_S = 2.0
PAUSE_AFTER_SCENE_S = 0.35


async def probe_duration(path: str | Path) -> float | None:
    """Đo thời lượng thật của file audio/video bằng ffprobe."""
    proc = await asyncio.create_subprocess_exec(
        settings.ffprobe_bin,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        return None
    try:
        return round(float(out.decode().strip()), 3)
    except ValueError:
        return None


def estimate_duration(text: str) -> float:
    """
    Ước lượng dự phòng khi không có TTS.

    Tiếng Việt là ngôn ngữ đơn âm tiết — đếm âm tiết chính là đếm từ, nên
    ước lượng khá sát. Vẫn kém đo thật, chỉ dùng để MVP không bị chặn.
    """
    syllables = len(re.findall(r"\S+", text))
    return round(max(MIN_SCENE_S, syllables / SYLLABLES_PER_SECOND + 0.5), 3)


async def measure_scenes(scenes: list[dict], audio_paths: list[Path | None]) -> float:
    """
    Gắn `duration` thật cho từng cảnh, tại chỗ. Trả về tổng thời lượng.

    Ưu tiên số đo từ ffprobe; chỉ rơi về ước lượng khi cảnh đó không có audio.
    """
    total = 0.0
    for scene, audio in zip(scenes, audio_paths):
        measured = await probe_duration(audio) if audio else None
        if measured:
            scene["duration"] = round(measured + PAUSE_AFTER_SCENE_S, 3)
            scene["timing_source"] = "ffprobe"
        else:
            scene["duration"] = estimate_duration(scene.get("loi_thoai", ""))
            scene["timing_source"] = "estimate"
        scene["start"] = round(total, 3)
        total = round(total + scene["duration"], 3)
    return total
