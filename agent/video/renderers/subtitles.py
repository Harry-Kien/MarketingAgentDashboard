"""
Sinh phụ đề `.ass` từ kịch bản đã có thời lượng đo thật.

Vì sao `.ass` chứ không `.srt`: cần định vị chính xác, viền chữ, và cỡ chữ
theo khung 1080×1920. `.srt` không mang được thông tin nào trong số đó, trình
phát tự quyết — mà video này sẽ được burn cứng vào hình nên phải tự quyết.

Phụ đề là mảnh quan trọng hơn vẻ ngoài của nó: phần lớn người xem Zalo và
TikTok xem trong trạng thái tắt tiếng. Khi TTS chưa chạy, đây là thứ DUY NHẤT
truyền được lời thoại.
"""
from __future__ import annotations

from pathlib import Path

# Chừa sẵn dải đáy cho phụ đề. Khâu vẽ chữ tiêu đề không được lấn vào đây.
BOTTOM_RESERVED = 300

_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},52,&H00F2F3F0,&H000000FF,&H00101418,&H90000000,0,0,0,0,100,100,0,0,1,4,1,2,90,90,110,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _stamp(seconds: float) -> str:
    """Giây -> H:MM:SS.cc theo đúng cách ASS đọc."""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    """ASS coi `{` `}` là mã lệnh và xuống dòng thật là hết dòng sự kiện."""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\r\n", " ")
        .replace("\n", " ")
        .strip()
    )


def build(scenes: list[dict], out_path: Path, font: str = "Segoe UI") -> Path | None:
    """
    Viết file `.ass`. Trả None nếu không cảnh nào có lời thoại.

    Mốc thời gian lấy thẳng từ `start`/`duration` của cảnh — tức là lấy từ số
    đo ffprobe khi có giọng đọc. Phụ đề không tự tính giờ riêng, nên nó không
    thể lệch khỏi hình.
    """
    lines = []
    for scene in scenes:
        text = _escape(scene.get("loi_thoai", ""))
        if not text:
            continue
        start = float(scene.get("start", 0.0))
        dur = float(scene.get("duration", 0.0))
        if dur <= 0:
            continue
        # Cắt sớm 0,12s để chữ không dính sang cảnh sau.
        end = start + max(0.4, dur - 0.12)
        lines.append(
            f"Dialogue: 0,{_stamp(start)},{_stamp(end)},Default,,0,0,0,,{text}"
        )

    if not lines:
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        _HEAD.format(font=font) + "\n".join(lines) + "\n", encoding="utf-8"
    )
    return out_path


def filter_arg(path: Path) -> str:
    r"""
    Đường dẫn cho filter `ass=` của ffmpeg.

    Windows: dấu hai chấm của ổ đĩa phải được thoát bằng dấu chéo ngược, vì
    filtergraph hiểu dấu hai chấm là ký tự ngăn tham số. Bỏ qua bước này thì
    ffmpeg báo "không mở được file" trong khi file nằm sờ sờ ở đó — chỗ hỏng
    kinh điển và im lặng. Dấu chéo ngược của Windows cũng đổi thành chéo xuôi.
    """
    return str(path).replace("\\", "/").replace(":", "\\:")
