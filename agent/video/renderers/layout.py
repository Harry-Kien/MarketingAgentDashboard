"""
Vẽ khung hình tĩnh bằng Pillow.

VÌ SAO KHÔNG DÙNG `drawtext` CỦA FFMPEG
---------------------------------------
`drawtext` không cho biết chuỗi sẽ rộng bao nhiêu pixel trước khi vẽ. Với
tiếng Việt có dấu, đoán bằng số ký tự luôn sai. Hệ quả đã thấy trong video
thật: dòng "Giá: 4.290.000đ. Bảo hành 24 tháng. Đặt ngay!" tràn khỏi khung
1080px và bị cắt cụt cả hai đầu.

Pillow ĐO ĐƯỢC hộp chữ trước khi vẽ. Nên chữ được xuống dòng theo bề rộng
thật, và cỡ chữ tự hạ khi vẫn không vừa. Cùng một tinh thần với `timing.py`:
đo trước, dựng sau.

Phân vai: Pillow lo bố cục và chữ, ffmpeg lo chuyển động và mã hoá.

Mỗi cảnh sinh ra HAI ảnh:
  base — ảnh sản phẩm, cỡ gấp đôi khung, sẽ được ffmpeg zoom (Ken Burns)
  over — lớp phủ trong suốt chứa dải tối và chữ, ĐỨNG YÊN đè lên trên

Tách hai lớp vì chữ mà zoom theo ảnh thì vừa chóng mặt vừa mờ chữ.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 1080, 1920
SCALE = 2                       # dư địa cho Ken Burns phóng to
BG = (20, 24, 28)
BG_ACCENT = (18, 63, 53)
FG = (242, 243, 240)

# Dải đáy dành riêng cho phụ đề — chữ tiêu đề không được lấn vào.
BOTTOM_RESERVED = 300
MARGIN_X = 90

_REGULAR = [
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_BOLD = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

# Dải tối càng đậm khi ảnh càng sáng — bảo đảm chữ trắng luôn đọc được, thay
# vì phải đoán đúng màu chữ cho từng ảnh rồi cầu may.
SCRIM_ALPHA = {"toi": 150, "trung_binh": 185, "sang": 215}

ACCENT_DEFAULT = (31, 111, 92)


def font_path(bold: bool = False) -> str | None:
    for p in (_BOLD if bold else _REGULAR):
        if Path(p).exists():
            return p
    return None


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = font_path(bold)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    start_size: int,
    bold: bool = True,
):
    """
    Tìm cỡ chữ và cách ngắt dòng để chữ NẰM TRỌN trong hộp cho trước.

    Hạ dần cỡ chữ tới khi vừa cả bề ngang lẫn bề dọc, đo bằng số đo thật chứ
    không đếm ký tự. Đây là hàm diệt lỗi tràn chữ.

    Trả về (các dòng, font, chiều cao mỗi dòng).
    """
    size = start_size
    while size >= 28:
        font = _font(size, bold)
        approx = max(6, int(max_width / (size * 0.52)))
        lines = textwrap.wrap(text, width=approx) or [""]
        line_h = int(size * 1.16)
        widest = max(_text_width(draw, ln, font) for ln in lines)
        if widest <= max_width and len(lines) * line_h <= max_height:
            return lines, font, line_h
        size -= 4

    # Chữ dài bất thường: cắt bớt dòng còn hơn để tràn ra ngoài khung.
    font = _font(28, bold)
    lines = textwrap.wrap(text, width=max(8, int(max_width / 15))) or [""]
    keep = max(1, max_height // 33)
    return lines[:keep], font, 33


def text_box(vung_trong: str):
    """
    Hộp đặt chữ, chọn theo vùng trống mà bước nhìn ảnh chỉ ra.

    Đây là chỗ hướng B trả công: chữ tránh sản phẩm thay vì luôn nằm giữa
    khung. Mọi hộp đều nằm phía trên dải phụ đề.
    """
    usable_bottom = HEIGHT - BOTTOM_RESERVED
    if vung_trong == "tren":
        return MARGIN_X, 200, WIDTH - MARGIN_X, 780
    if vung_trong == "trai":
        return MARGIN_X, 620, int(WIDTH * 0.62), 1240
    if vung_trong == "phai":
        return int(WIDTH * 0.38), 620, WIDTH - MARGIN_X, 1240
    return MARGIN_X, usable_bottom - 460, WIDTH - MARGIN_X, usable_bottom - 40


def _cover(src: Image.Image, size) -> Image.Image:
    """Phóng ảnh phủ kín khung rồi cắt phần thừa, giữ nguyên tỷ lệ."""
    scale = max(size[0] / src.width, size[1] / src.height)
    resized = src.resize(
        (max(1, int(src.width * scale)), max(1, int(src.height * scale))),
        Image.LANCZOS,
    )
    left = (resized.width - size[0]) // 2
    top = (resized.height - size[1]) // 2
    return resized.crop((left, top, left + size[0], top + size[1]))


def base_frame(image_path=None, accent: bool = False) -> Image.Image:
    """
    Lớp nền: ảnh sản phẩm phủ kín khung dọc, cỡ gấp đôi để còn chỗ zoom.

    Ảnh ngang không bị viền đen: nền là chính ảnh đó phóng to và làm mờ, ảnh
    gốc đặt nguyên tỷ lệ ở giữa. Giữ được trọn sản phẩm mà vẫn lấp đầy khung.
    """
    size = (WIDTH * SCALE, HEIGHT * SCALE)
    if image_path is None or not Path(image_path).exists():
        return Image.new("RGB", size, BG_ACCENT if accent else BG)

    try:
        src = Image.open(image_path).convert("RGB")
    except OSError:
        return Image.new("RGB", size, BG_ACCENT if accent else BG)

    target_ratio = size[0] / size[1]
    src_ratio = src.width / src.height

    if abs(src_ratio - target_ratio) < 0.12:
        return _cover(src, size)

    bg = _cover(src, size).filter(ImageFilter.GaussianBlur(radius=60))
    bg = Image.blend(bg, Image.new("RGB", size, BG), 0.35)

    # KHÔNG dùng `thumbnail()`: nó chỉ thu nhỏ, không bao giờ phóng to. Ảnh
    # ngang 1920px hẹp hơn khung 2160px sẽ nằm lọt thỏm giữa màn hình, viền
    # mờ bao quanh bốn phía — trông như lỗi chứ không như dụng ý.
    scale = min(size[0] / src.width, size[1] / src.height)
    fg = src.resize(
        (max(1, int(src.width * scale)), max(1, int(src.height * scale))),
        Image.LANCZOS,
    )
    bg.paste(fg, ((size[0] - fg.width) // 2, (size[1] - fg.height) // 2))
    return bg


def _scrim(box, alpha: int, vung_trong: str) -> Image.Image:
    """
    Dải tối chuyển dần, nằm sau chữ.

    Hướng chuyển màu phải CHẠY RA MÉP KHUNG, không được đậm ở giữa rồi nhạt
    về hai đầu — kiểu đó tạo một vệt mờ ngang giữa ảnh, trông như lỗi nén chứ
    không như dụng ý. Chữ ở dưới thì tối dần xuống đáy, chữ ở trên thì tối
    dần lên đỉnh, tương tự cho trái phải.

    Dựng bằng một hàng (hoặc cột) pixel rồi kéo giãn — rẻ và mượt.
    """
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    dark = Image.new("RGBA", (WIDTH, HEIGHT), (8, 10, 12, 255))
    ramp = 260          # quãng tan dần, tính từ mép vùng chữ ra ngoài
    pad = 60            # nới vùng đặc ra ngoài hộp chữ một chút

    def profile(pos: int, solid_from: int, solid_to: int, toward_high: bool) -> int:
        """Đặc kín trong [solid_from, solid_to], tan dần ra phía ngoài."""
        if solid_from <= pos <= solid_to:
            return alpha
        dist = (pos - solid_to) if toward_high else (solid_from - pos)
        if dist <= 0:
            return alpha
        t = min(1.0, dist / ramp)
        return int(alpha * ((1.0 - t) ** 1.6))

    if vung_trong in ("trai", "phai"):
        strip = Image.new("L", (WIDTH, 1))
        px = strip.load()
        for x in range(WIDTH):
            if vung_trong == "trai":
                px[x, 0] = profile(x, 0, x1 + pad, toward_high=True)
            else:
                px[x, 0] = profile(x, x0 - pad, WIDTH, toward_high=False)
    else:
        strip = Image.new("L", (1, HEIGHT))
        px = strip.load()
        for y in range(HEIGHT):
            if vung_trong == "tren":
                px[0, y] = profile(y, 0, y1 + pad, toward_high=True)
            else:
                # Đặc từ mép trên hộp chữ xuống hết đáy — dải phụ đề cũng cần
                # nền tối, nên không dừng ở đáy hộp.
                px[0, y] = profile(y, y0 - pad, HEIGHT, toward_high=False)

    layer.paste(dark, (0, 0), strip.resize((WIDTH, HEIGHT), Image.BILINEAR))
    return layer


def _hex(value: str):
    value = (value or "").lstrip("#")
    if len(value) != 6:
        return ACCENT_DEFAULT
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return ACCENT_DEFAULT


def overlay_frame(
    scene: dict, analysis: dict, index: int, accent_hex: str = "#1F6F5C"
) -> Image.Image:
    """Lớp phủ đứng yên: dải tối + số cảnh + tiêu đề + gạch nhấn."""
    analysis = analysis or {}
    vung = analysis.get("vung_trong", "duoi")
    box = text_box(vung)
    layer = _scrim(box, SCRIM_ALPHA.get(analysis.get("do_sang", "trung_binh"), 185), vung)
    draw = ImageDraw.Draw(layer)
    accent = _hex(accent_hex)

    x0, y0, x1, y1 = box
    max_w, max_h = x1 - x0, y1 - y0

    draw.text((x0, y0), f"{index + 1:02d}", font=_font(30, bold=True),
              fill=(accent[0], accent[1], accent[2], 255))

    title = str(scene.get("text_man_hinh") or scene.get("loi_thoai") or "").strip()
    if title:
        start = 104 if scene.get("nhan_manh") else 88
        lines, font, line_h = fit_text(draw, title, max_w, max_h - 70, start)
        y = y0 + 54
        for line in lines:
            draw.text((x0, y), line, font=font, fill=(FG[0], FG[1], FG[2], 255))
            y += line_h

    rule_y = min(y1 + 26, HEIGHT - BOTTOM_RESERVED - 14)
    draw.rectangle([x0, rule_y, x0 + 160, rule_y + 5],
                   fill=(accent[0], accent[1], accent[2], 255))
    return layer


def write_scene(scene: dict, asset, work: Path, index: int):
    """Ghi cặp ảnh base/over cho một cảnh. Trả (đường dẫn base, đường dẫn over)."""
    asset = asset or {}
    analysis = asset.get("analysis") or {}
    accent = analysis.get("mau_chu_dao") or "#1F6F5C"

    base = base_frame(asset.get("file_path"), accent=bool(scene.get("nhan_manh")))
    over = overlay_frame(scene, analysis, index, accent)

    base_path = work / f"base_{index:02d}.jpg"
    over_path = work / f"over_{index:02d}.png"
    base.save(base_path, format="JPEG", quality=92)
    over.save(over_path, format="PNG")
    return base_path, over_path
