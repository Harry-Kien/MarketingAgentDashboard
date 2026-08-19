"""
Bậc 3 — ffmpeg. Lưới an toàn, luôn chạy được.

Phân vai với `layout.py`: Pillow đã vẽ xong hai lớp ảnh tĩnh cho mỗi cảnh,
ffmpeg chỉ còn ba việc — cho lớp nền chuyển động, chồng lớp chữ lên, và mã
hoá. Không có `drawtext` nào ở đây, nên không có lỗi tràn chữ nào ở đây.

HAI QUYẾT ĐỊNH ĐÁNG GHI LẠI
---------------------------
1. KHÔNG dùng `xfade` để chuyển cảnh. Chồng mờ 0,4s làm tổng thời lượng ngắn
   đi (số cảnh - 1) x 0,4 giây, tức là video trôi lệch khỏi giọng đọc — đúng
   cái bệnh mà cả hệ thống này sinh ra để tránh. Dùng fade-in trong từng cảnh
   thay thế: mượt tương đương, thời lượng chính xác tuyệt đối.

2. KHÔNG dùng `-shortest`. File giọng đọc luôn NGẮN HƠN thời lượng cảnh, vì
   `timing.py` cộng thêm 0,35 giây nghỉ sau mỗi câu. `-shortest` cắt cảnh
   xuống bằng độ dài audio, ăn mất khoảng nghỉ đó và làm hình lệch dần khỏi
   tiếng. Thay bằng `apad` để chèn im lặng cho đủ, `-t` giữ đúng thời lượng.
   Lỗi này chưa lộ ra vì TTS chưa chạy — không có audio thì không có gì để
   cắt ngắn.
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from agent.video.renderers import layout, subtitles
from agent.video.renderers.base import RenderContext

FPS = 30
FADE_IN = 0.3
ZOOM_RANGE = 0.10          # phóng 10% suốt cảnh — đủ thấy, chưa thấy méo

# Cảnh rời là file TẠM, sẽ bị mã hoá lại lần nữa khi ghép. Nén chặt ở bước
# này là tự chồng nhiễu lên nhiễu, nên để chất lượng gần như không mất
# (crf 16) rồi mới nén thật ở bước cuối.
CRF_SEGMENT = 16
CRF_FINAL = 19
PRESET_FINAL = "medium"    # chậm hơn veryfast nhưng đây là bản giao đi

# Chuẩn âm lượng của các nền tảng xã hội: -16 LUFS, đỉnh thật -1.5 dBTP.
# Không chuẩn hoá thì mỗi video một mức to nhỏ khác nhau, người xem phải
# chỉnh loa liên tục — lỗi nghiệp dư dễ thấy nhất ở video doanh nghiệp.
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


async def _run(*args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    out, _ = await proc.communicate()
    return proc.returncode or 0, out.decode(errors="replace")


def _kenburns(frames: int, zoom_in: bool) -> str:
    """
    Biểu thức Ken Burns cho `zoompan`.

    Hướng phóng đổi luân phiên theo cảnh chẵn lẻ. Cùng một hướng suốt video
    trông như lỗi kỹ thuật hơn là dụng ý.
    """
    frames = max(1, frames)
    if zoom_in:
        z = f"1+{ZOOM_RANGE}*on/{frames}"
    else:
        z = f"{1 + ZOOM_RANGE}-{ZOOM_RANGE}*on/{frames}"
    return (
        f"zoompan=z='{z}'"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={layout.WIDTH}x{layout.HEIGHT}:fps={FPS}"
    )


async def _segment(
    ctx: RenderContext, scene: dict, index: int, work: Path
) -> tuple[bool, str, Path]:
    """Dựng một cảnh thành file mp4 riêng."""
    dur = max(0.5, float(scene.get("duration", 3.0)))
    frames = int(round(dur * FPS))
    seg = work / f"seg_{index:02d}.mp4"

    base_png, over_png = layout.write_scene(scene, ctx.asset_for(scene), work, index)
    audio = ctx.audio_dir / f"scene_{index:02d}.wav"
    has_audio = audio.exists()

    cmd = [
        _ffmpeg(), "-y",
        "-loop", "1", "-t", f"{dur:.3f}", "-i", str(base_png),
        "-loop", "1", "-t", f"{dur:.3f}", "-i", str(over_png),
    ]
    if has_audio:
        cmd += ["-i", str(audio)]
    else:
        cmd += [
            "-f", "lavfi", "-t", f"{dur:.3f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        ]

    chain = (
        f"[0:v]{_kenburns(frames, index % 2 == 0)},setsar=1[bg];"
        f"[bg][1:v]overlay=0:0:format=auto[ov];"
        f"[ov]fade=t=in:st=0:d={FADE_IN}[v]"
    )

    cmd += [
        "-filter_complex", chain,
        "-map", "[v]",
        "-map", "2:a",
        # apad + -t: audio ngắn hơn cảnh thì chèn im lặng, không cắt hình.
        "-af", "apad",
        "-t", f"{dur:.3f}",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CRF_SEGMENT),
        "-pix_fmt", "yuv420p",
        # ÉP CỨNG stereo 48kHz cho MỌI cảnh. Cảnh có giọng đọc lấy layout từ
        # file wav (viet-tts trả mono), cảnh không có thì anullsrc sinh
        # stereo. Ghép hai loại lại thì `concat` lấy thông số của cảnh ĐẦU
        # TIÊN làm chuẩn — nghĩa là định dạng audio của cả video đổi theo
        # việc cảnh mở đầu có lời thoại hay không. Đầu ra không được phép
        # phụ thuộc vào nội dung như vậy.
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k",
        str(seg),
    ]

    code, log = await _run(*cmd)
    if code != 0:
        return False, f"cảnh {index}: {log[-400:]}", seg
    return True, "", seg


async def render(ctx: RenderContext) -> tuple[bool, str]:
    """Dựng trọn video. Trả (thành công, ghi chú hoặc lý do hỏng)."""
    if not ctx.scenes:
        return False, "không có cảnh nào để dựng"

    work = Path(tempfile.mkdtemp(prefix="mkt_render_"))
    try:
        parts: list[Path] = []
        for i, scene in enumerate(ctx.scenes):
            ok, err, seg = await _segment(ctx, scene, i, work)
            if not ok:
                return False, err
            parts.append(seg)

        listing = work / "parts.txt"
        listing.write_text(
            "\n".join("file '" + p.as_posix() + "'" for p in parts), encoding="utf-8"
        )

        ctx.out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            _ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
        ]

        note = "ffmpeg"
        if ctx.subtitles:
            ass = subtitles.build(
                ctx.scenes, work / "phude.ass",
                font=Path(layout.font_path() or "Segoe UI").stem or "Segoe UI",
            )
            if ass is not None:
                cmd += ["-vf", f"ass='{subtitles.filter_arg(ass)}'"]
                note = "ffmpeg + phụ đề"

        cmd += [
            "-af", LOUDNORM,
            "-c:v", "libx264", "-preset", PRESET_FINAL, "-crf", str(CRF_FINAL),
            "-profile:v", "high", "-level", "4.1",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
            # Đưa chỉ mục lên đầu file: không có cờ này thì trình duyệt và
            # ứng dụng phải tải hết file mới phát được, video 20MB trên 4G
            # là đứng im mấy giây rồi mới chạy.
            "-movflags", "+faststart",
            str(ctx.out_path),
        ]

        code, log = await _run(*cmd)
        if code != 0:
            return False, f"ghép: {log[-400:]}"
        return True, note
    finally:
        shutil.rmtree(work, ignore_errors=True)
