"""
Nhận và chuẩn hoá ảnh sản phẩm.

Ba việc bắt buộc làm TRƯỚC khi ghi xuống đĩa:

  1. Kiểm định dạng THẬT bằng magic bytes. Đuôi file do người gửi đặt, không
     tin được — `.jpg` có thể là bất cứ thứ gì.
  2. Xoay theo EXIF Orientation rồi XOÁ SẠCH EXIF. Ảnh chụp bằng điện thoại
     mang theo toạ độ GPS kho hàng hoặc nhà riêng, mà ảnh này sẽ nằm trong
     video đăng công khai. Đây là chỗ dễ quên nhất và hậu quả không thu hồi.
  3. Hạ cạnh dài xuống 2048px — dư cho khung 1920, giữ token vision thấp.

Module này không biết gì về video hay model. Nó chỉ biến bytes thô thành file
ảnh sạch trên đĩa.
"""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from PIL import Image, ImageOps

MAX_IMAGES = 8
MAX_BYTES = 10 * 1024 * 1024
MAX_EDGE = 2048
JPEG_QUALITY = 88

# Tên định dạng theo cách Pillow gọi, không theo đuôi file.
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class AssetError(ValueError):
    """Ảnh không dùng được. Thông điệp viết cho người dùng cuối đọc."""


def _normalize_one(raw: bytes, dest: Path) -> tuple[int, int]:
    """
    Chuẩn hoá một ảnh, ghi ra `dest` dạng JPEG. Trả về (rộng, cao) sau xử lý.

    Chạy đồng bộ và tốn CPU — người gọi phải đẩy sang thread.
    """
    if len(raw) > MAX_BYTES:
        raise AssetError(f"Ảnh nặng quá {MAX_BYTES // 1024 // 1024}MB")
    if not raw:
        raise AssetError("File rỗng")

    import io

    # verify() đóng file object nên phải mở hai lần: một lần để kiểm, một
    # lần để dùng. Đây là cách Pillow yêu cầu, không phải thừa.
    try:
        probe = Image.open(io.BytesIO(raw))
        probe.verify()
        fmt = probe.format
    except Exception as exc:  # noqa: BLE001 — mọi lỗi Pillow đều là "ảnh hỏng"
        raise AssetError(f"Không đọc được ảnh: {type(exc).__name__}") from exc

    if fmt not in ALLOWED_FORMATS:
        raise AssetError(f"Định dạng {fmt or 'lạ'} không nhận; chỉ jpg/png/webp")

    img = Image.open(io.BytesIO(raw))

    # Xoay theo EXIF. Ảnh điện thoại thường nằm ngang trong dữ liệu và chỉ
    # đứng lên nhờ cờ Orientation — bỏ qua bước này là ảnh vào video bị nằm.
    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGBA", "LA", "P"):
        # Nền trong suốt phải được dán lên nền trắng, không thì JPEG cho ra
        # mảng đen loang lổ.
        img = img.convert("RGBA")
        flat = Image.new("RGB", img.size, (255, 255, 255))
        flat.paste(img, mask=img.split()[-1])
        img = flat
    elif img.mode != "RGB":
        img = img.convert("RGB")

    if max(img.size) > MAX_EDGE:
        img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Không truyền `exif=` — mọi siêu dữ liệu bị bỏ lại ở đây, có chủ đích.
    img.save(dest, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return img.size


async def save_uploads(
    dest_dir: Path, files: list[tuple[str, bytes]]
) -> tuple[list[dict], list[str]]:
    """
    Chuẩn hoá cả lô ảnh vào `dest_dir`.

    Trả về (danh sách ảnh dùng được, danh sách lời cảnh báo). Một ảnh hỏng
    KHÔNG làm hỏng cả lô — nó chỉ biến thành một dòng cảnh báo.
    """
    saved: list[dict] = []
    warnings: list[str] = []

    for name, raw in files[:MAX_IMAGES]:
        ord_ = len(saved)
        dest = dest_dir / f"img_{ord_:02d}.jpg"
        try:
            width, height = await asyncio.to_thread(_normalize_one, raw, dest)
        except AssetError as exc:
            warnings.append(f"{name}: {exc}")
            continue
        saved.append(
            {
                "ord": ord_,
                "file_path": str(dest),
                "width": width,
                "height": height,
            }
        )

    if len(files) > MAX_IMAGES:
        warnings.append(
            f"Chỉ nhận {MAX_IMAGES} ảnh đầu, bỏ qua {len(files) - MAX_IMAGES} ảnh"
        )
    return saved, warnings


def to_data_block(path: str | Path) -> dict:
    """Đọc ảnh trên đĩa thành khối `image` cho tầng LLM."""
    data = Path(path).read_bytes()
    return {
        "type": "image",
        "media_type": "image/jpeg",
        "data": base64.b64encode(data).decode("ascii"),
    }
