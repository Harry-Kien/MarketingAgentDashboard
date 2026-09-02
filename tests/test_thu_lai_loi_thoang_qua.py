"""
Lỗi thoáng qua của nhà cung cấp phải được THỬ LẠI, không đẩy thẳng sang người.

LỖI DO CHÍNH BỘ 56 CÂU VÀNG BẮT ĐƯỢC
------------------------------------
Lượt chạy đầy đủ gặp một `Gemini 502` từ frontend của Google. Bản trước chỉ
thử lại 429 và 503, nên 502 ném thẳng — và ở luồng thật, `main.py` bắt lỗi
đó rồi chuyển hội thoại sang chế độ human.

Nghĩa là một sự cố hạ tầng kéo dài hai giây làm một khách bị đẩy vào hàng
chờ người, giữa đêm, cho một câu hỏi giá bình thường.

502/500/504 cùng một loại với 503: lỗi phía máy chủ, thoáng qua, và lần thử
sau thường thành công.

VÌ SAO KHÔNG THỬ LẠI MỌI MÃ LỖI
-------------------------------
400 là body sai. 401/403 là hỏng xác thực. 404 là sai tên model. Thử lại
những mã đó chỉ làm khách chờ lâu gấp ba rồi vẫn hỏng — và giấu mất nguyên
nhân thật khỏi nhật ký.
"""
from __future__ import annotations

import inspect

import pytest

from agent.core.llm import MA_THU_LAI


@pytest.mark.parametrize("ma", [429, 500, 502, 503, 504])
def test_ma_thoang_qua_duoc_thu_lai(ma):
    assert ma in MA_THU_LAI


@pytest.mark.parametrize("ma", [400, 401, 403, 404, 422])
def test_ma_do_MINH_sai_thi_khong_thu_lai(ma):
    """Thử lại một request sai định dạng là chờ lâu gấp ba rồi vẫn hỏng."""
    assert ma not in MA_THU_LAI


def test_502_nam_trong_danh_sach():
    """
    Canh riêng 502 vì nó là mã ĐÃ gây lỗi thật, và là mã dễ bị bỏ sót nhất:
    người ta nhớ 429 và 503, ít ai nhớ 502.
    """
    assert 502 in MA_THU_LAI


def test_danh_sach_duoc_GAN_vao_vong_thu_lai():
    """Có hằng mà vòng lặp vẫn so cứng là hằng chết."""
    from agent.core import llm

    nguon = inspect.getsource(llm)
    assert "MA_THU_LAI" in nguon.split("MA_THU_LAI = ", 1)[1], (
        "khai hằng nhưng không dùng"
    )
    assert "(429, 503)" not in nguon, "vẫn còn danh sách cứng cũ"


def test_co_gian_cach_tang_dan():
    """
    Thử lại ngay lập tức ba lần là ba lần cùng gặp đúng sự cố đó, và với 429
    thì còn làm giới hạn tốc độ tệ hơn.
    """
    from agent.core import llm

    nguon = inspect.getsource(llm)
    assert "delay *= 2" in nguon


def test_het_luot_thu_thi_NEM_chu_khong_im():
    """
    Hỏng thật phải nổi lên: `main.py` bắt lỗi này để chuyển hội thoại sang
    người và ghi nhật ký. Nuốt im là khách ngồi chờ một câu trả lời không
    bao giờ tới.
    """
    from agent.core import llm

    nguon = inspect.getsource(llm)
    assert "raise RuntimeError(last)" in nguon
