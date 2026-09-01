"""
Sổ đăng ký khung ngành.

Thêm ngành mới là thêm một module ở đây rồi khai vào `KHUNG_THEO_MA`. Cố ý
KHÔNG quét thư mục tự động: một khung ngành là thứ phải được người thêm vào
có ý thức, không phải thứ xuất hiện vì ai đó thả nhầm tệp vào thư mục.
"""
from __future__ import annotations

from agent.tri_thuc.hop_dong import KhungNganh
from agent.tri_thuc.nganh import my_pham, the_thao

KHUNG_THEO_MA: dict[str, KhungNganh] = {
    my_pham.KHUNG.ma: my_pham.KHUNG,
    the_thao.KHUNG.ma: the_thao.KHUNG,
}


def lay(ma: str) -> KhungNganh:
    """
    Lấy khung theo mã. Mã lạ thì NÉM, không rơi về mặc định.

    Rơi về mỹ phẩm khi người dùng gõ nhầm `--nganh the_thaoo` là sinh ra cả
    một kho tri thức sai ngành mà trông như đúng — hỏng im lặng, đúng khuôn
    `agent/erp/nha_may.py` đã cố ý tránh.
    """
    try:
        return KHUNG_THEO_MA[ma.strip().lower()]
    except KeyError:
        raise ValueError(
            f"Không có khung ngành {ma!r}. Hợp lệ: "
            + ", ".join(sorted(KHUNG_THEO_MA))
        ) from None
