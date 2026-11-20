"""
Đường dẫn tệp trong `data/` lưu vào CSDL: TƯƠNG ĐỐI, không tuyệt đối.

VÌ SAO
------
Đo 20.11.2026: mọi `attachments.storage_key` và payload gửi tệp trong outbox
mang đường dẫn kiểu `D:\\Marketing Dasbhboard CSKH\\data\\products\\...`. Chuyển
cửa hàng lên VPS Linux (`scripts.chuyen_nha`) là mọi ảnh sản phẩm đã gửi và
mọi tệp nhân viên gửi thành "Tệp không còn trên máy chủ" — không lỗi lúc
chuyển, chỉ vỡ khi có người bấm xem.

Lưu `data/<đường dẫn con>` thì cùng một dòng CSDL mở được trên mọi máy. Dòng
CŨ (tuyệt đối, có thể của máy khác, có thể dấu `\\`) vẫn đọc được: lấy phần
sau đoạn `data` cuối cùng rồi đặt dưới thư mục `data/` của máy đang chạy.
"""
from __future__ import annotations

import re
from pathlib import Path

GOC_DU_LIEU = (Path(__file__).resolve().parents[1] / "data").resolve()


def khoa_luu(duong: str | Path) -> str:
    """Khoá để LƯU: `data/...` (dấu `/`) nếu tệp nằm trong `data/`, nguyên văn nếu không."""
    p = Path(duong)
    try:
        con = p.resolve().relative_to(GOC_DU_LIEU)
    except (ValueError, OSError):
        return str(duong)
    return "data/" + con.as_posix()


def mo_khoa(khoa: str | None) -> Path | None:
    """Đường dẫn THẬT trên máy đang chạy cho một khoá đã lưu (mới hoặc cũ)."""
    if not khoa:
        return None
    s = str(khoa).strip()
    phan = [x for x in re.split(r"[\\/]+", s) if x]
    if phan and phan[0] == "data" and not Path(s).is_absolute():
        return GOC_DU_LIEU.joinpath(*phan[1:])
    # Dòng cũ: đường dẫn tuyệt đối, có khi của máy khác (Windows trên Linux).
    vi_tri = [i for i, x in enumerate(phan) if x.lower() == "data"]
    if vi_tri:
        sau = phan[vi_tri[-1] + 1:]
        if sau:
            return GOC_DU_LIEU.joinpath(*sau)
    return Path(s)
