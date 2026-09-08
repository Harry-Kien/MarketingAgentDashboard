"""
`bo_dau` phải đổi "đ" thành "d", như hai hàm chuẩn hoá còn lại.

LỖI THẬT, tìm ra khi viết câu thử cho plugin tra bảng.

BA HÀM CHUẨN HOÁ, MỘT HÀM LỆCH
------------------------------
    agent/core/tools.py            `_norm`   "Đà Nẵng" → "da nang"
    agent/core/cham_mot_luot.py    `fold`    "Đà Nẵng" → "da nang"
    agent/ky_nang/ban_mo_ta.py     `bo_dau`  "Đà Nẵng" → "đa nang"   ← lệch

`bo_dau` bỏ dấu thanh nhưng giữ nguyên chữ "đ".

HỎNG THẾ NÀO
------------
Khách Việt gõ không dấu rất nhiều — chính `_norm` đã ghi lý do ấy trong
chú thích của nó. Khách hỏi "ship ve da nang bao nhieu", bảng có dòng
"Đà Nẵng": `_tra_bang` so "đa nang" với "...da nang...", không khớp, agent
nói chưa có thông tin. Dòng CÓ trong bảng mà khách không lấy được.

Và vòng cải thiện của đợt trước gãy ngay tại đây: cột `khong_khop` ghi
bằng `_norm` nên bảng xếp hạng hiện "da nang"; người vận hành bấm thêm
đúng khoá ấy; khách gõ "Đà Nẵng" có dấu thì `bo_dau` cho "đa nang" và lại
trượt. Hai đầu của cùng một vòng dùng hai thước đo khác nhau.

VÌ SAO SỬA `bo_dau` CHỨ KHÔNG SỬA HAI HÀM KIA
---------------------------------------------
Hai hàm kia đã đúng và đang được dùng ở đường tin khách. Sửa chúng theo
`bo_dau` là làm hỏng chỗ đang chạy tốt để khớp chỗ đang sai.

Luật chống khoá nuốt nhau cũng dùng `bo_dau`, nên nó chặt hơn sau thay
đổi này: một bảng có cả "Đà Nẵng" lẫn "da nang" nay bị từ chối lúc LƯU —
đúng, vì hai dòng ấy vốn không phân biệt được lúc tra.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core.cham_mot_luot import fold  # noqa: E402
from agent.core.tools import _norm  # noqa: E402
from agent.ky_nang.ban_mo_ta import (  # noqa: E402
    LoiBanMoTa,
    bo_dau,
    doc_ban_mo_ta,
)
from agent.ky_nang.chay import chay_plugin  # noqa: E402


@pytest.mark.parametrize("chu", ["Đà Nẵng", "đi làm", "Đồng Nai", "ĐỎ", "đđ"])
def test_ba_ham_chuan_hoa_cho_cung_ket_qua(chu):
    """
    Ba hàm phải đồng ý với nhau. Lệch nhau là phép kiểm lúc lưu nói một
    đằng, phép so khớp lúc chạy làm một nẻo — không lỗi, không nhật ký.
    """
    assert bo_dau(chu) == _norm(chu) == fold(chu)


def _bm(bang: dict):
    return doc_ban_mo_ta({
        "ten": "tra_phi_ship",
        "loai": "tra_bang",
        "mo_ta": "Tra phí giao hàng theo tỉnh thành. Không dùng cho câu hỏi tình trạng đơn.",
        "tham_so": [{"ten": "khoa", "mo_ta": "Tỉnh khách ở"}],
        "cau_hinh": {"bang": bang},
    })


def test_khach_go_khong_dau_van_lay_duoc_dong_co_chu_d():
    """Ca hỏng thật: dòng CÓ trong bảng mà khách gõ không dấu không lấy được."""
    import asyncio

    bm = _bm({"Đà Nẵng": "Phí 28.000đ"})
    kq = asyncio.run(chay_plugin(bm, {"khoa": "ship ve da nang bao nhieu"}))
    assert kq["tim_thay"] is True
    assert kq["gia_tri"] == "Phí 28.000đ"


def test_hai_dong_chi_khac_chu_d_bi_chan_luc_luu():
    """
    Hệ quả đúng của thay đổi: "Đà Nẵng" và "da nang" không phân biệt được
    lúc tra, nên để cả hai trong một bảng là mời một câu trả lời sai.
    """
    with pytest.raises(LoiBanMoTa):
        _bm({"Đà Nẵng": "A", "da nang": "B"})
