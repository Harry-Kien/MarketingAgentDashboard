"""
Sổ đăng ký kỹ năng (skill) của agent, và cơ chế thêm kỹ năng KHÔNG cần sửa mã.

Ba phần:

  so_dang_ky.py   khai báo 11 công cụ có sẵn: nhóm, mức rủi ro, tắt được không
  ban_mo_ta.py    kiểm bản mô tả plugin do người vận hành viết
  chay.py         thi hành plugin — bốn loại, tất cả CHỈ ĐỌC

Vì sao có lớp này: `TOOLS` trong `agent/core/tools.py` là một danh sách
phẳng, mô tả cho MODEL đọc. Nó không nói cho NGƯỜI biết công cụ nào nguy
hiểm, công cụ nào cần ERP, công cụ nào không được phép tắt. Người vận hành
cần biết những điều đó mới bật/tắt có trách nhiệm được.
"""
from __future__ import annotations

from agent.ky_nang.ban_mo_ta import (
    LOAI_PLUGIN,
    LoiBanMoTa,
    BanMoTa,
    doc_ban_mo_ta,
    thanh_cong_cu,
)
from agent.ky_nang.so_dang_ky import (
    KHONG_TAT_DUOC,
    SO_DANG_KY,
    KyNang,
    khai_bao,
    ten_ky_nang_co_san,
)

__all__ = [
    "BanMoTa",
    "KHONG_TAT_DUOC",
    "KyNang",
    "LOAI_PLUGIN",
    "LoiBanMoTa",
    "SO_DANG_KY",
    "doc_ban_mo_ta",
    "khai_bao",
    "ten_ky_nang_co_san",
    "thanh_cong_cu",
]
