"""
Kiểm thử bảo vệ dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP).

Phần này XOÁ DỮ LIỆU THẬT và không hoàn tác được, nên nó cần lưới an toàn
chặt hơn mọi phần khác. Ba thứ được canh:

  1. Chuẩn hoá số điện thoại — không chuẩn hoá thì yêu cầu xoá TRƯỢT và dữ
     liệu vẫn nằm nguyên đó, trong khi hệ thống báo "đã xoá".
  2. Đơn hàng phải ẨN DANH chứ không xoá — Luật Kế toán 2015 Điều 41 buộc
     lưu chứng từ tối thiểu 10 năm. Xoá thẳng là vi phạm một luật khác.
  3. Nhật ký không được chứa số điện thoại thật — ghi lại thứ vừa hứa xoá
     thì việc xoá thành vô nghĩa.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core import du_lieu_ca_nhan as pdpd  # noqa: E402


# =====================================================================
#  Chuẩn hoá số điện thoại
# =====================================================================

@pytest.mark.parametrize("vao, ra", [
    ("0967627336", "0967627336"),
    ("0967 627 336", "0967627336"),
    ("0967.627.336", "0967627336"),
    ("+84967627336", "0967627336"),
    ("84967627336", "0967627336"),
    ("(096) 762-7336", "0967627336"),
    (" 0967627336 ", "0967627336"),
])
def test_moi_cach_viet_deu_ve_mot_so(vao, ra):
    assert pdpd.chuan_hoa_sdt(vao) == ra


def test_so_rong_khong_lam_sap():
    assert pdpd.chuan_hoa_sdt("") == ""
    assert pdpd.chuan_hoa_sdt(None) == ""


def test_so_qua_ngan_bi_tu_choi():
    import asyncio
    for ham in (pdpd.tra_cuu, pdpd.xoa):
        with pytest.raises(ValueError, match="không hợp lệ"):
            asyncio.run(ham("12345"))


# =====================================================================
#  Đơn hàng ẩn danh, hội thoại xoá hẳn
# =====================================================================

def test_don_hang_duoc_an_danh_chu_khong_xoa():
    """
    Xoá thẳng bản ghi đơn là vi phạm Luật Kế toán 2015 Điều 41. Phải giữ
    mã đơn, số tiền, ngày — chỉ thay tên, số điện thoại, địa chỉ.
    """
    src = inspect.getsource(pdpd.xoa)
    assert "UPDATE orders SET khach_ten" in src, "đơn hàng phải được ẩn danh"
    assert "DELETE FROM orders" not in src, (
        "không được xoá đơn hàng — chứng từ kế toán phải lưu tối thiểu 10 năm"
    )


def test_khong_an_danh_nham_cot_so_sach():
    """Mã đơn, tổng tiền, ngày tạo phải nguyên vẹn cho sổ sách."""
    src = inspect.getsource(pdpd.xoa)
    for cot in ("ma_don", "tong_tien", "items", "created_at"):
        assert f"{cot} = $" not in src, f"không được đụng vào {cot}"


def test_hoi_thoai_bi_xoa_han():
    """Nội dung chat chứa PII và không có nghĩa vụ lưu giữ nào."""
    src = inspect.getsource(pdpd.xoa)
    assert "DELETE FROM conversations" in src


# =====================================================================
#  Nhật ký không được giữ lại thứ vừa hứa xoá
# =====================================================================

def test_nhat_ky_chi_ghi_dau_van_tay_khong_ghi_so_that():
    src = inspect.getsource(pdpd.xoa)
    assert "_dau_van_tay(so)" in src, "phải băm số trước khi ghi nhật ký"
    # Tìm khối log_event và soi xem có truyền số thật vào không.
    khoi = src.split("log_event(", 1)[1].split(")", 1)[0]
    assert "sdt" not in khoi and "so=" not in khoi, (
        "nhật ký đang giữ số điện thoại thật — việc xoá thành vô nghĩa"
    )


def test_dau_van_tay_on_dinh_va_khong_lo_so():
    a = pdpd._dau_van_tay("0967627336")
    b = pdpd._dau_van_tay("0967627336")
    c = pdpd._dau_van_tay("0912345678")
    assert a == b, "cùng một số phải ra cùng dấu vân tay"
    assert a != c
    assert "0967627336" not in a


def test_moi_thao_tac_deu_duoc_ghi_lai():
    """Phải chứng minh được đã thực hiện yêu cầu, kèm căn cứ pháp lý."""
    for ham in (pdpd.xoa, pdpd.don_theo_thoi_han):
        src = inspect.getsource(ham)
        assert "log_event" in src
        assert "Nghị định 13/2023" in src, "nhật ký phải nêu căn cứ pháp lý"


# =====================================================================
#  Thời hạn lưu trữ
# =====================================================================

def test_don_theo_han_khong_dung_toi_don_hang():
    src = inspect.getsource(pdpd.don_theo_thoi_han)
    assert "orders" not in src, (
        "thời hạn 180 ngày chỉ áp cho hội thoại — chứng từ kế toán có thời "
        "hạn riêng dài hơn nhiều"
    )


def test_xem_truoc_duoc_truoc_khi_xoa():
    """Người vận hành phải nhìn được sẽ mất gì trước khi một vòng lặp nền xoá."""
    ky = inspect.signature(pdpd.don_theo_thoi_han).parameters
    assert "chi_dem" in ky


def test_xoa_luon_tra_ve_so_ban_ghi_bi_tac_dong():
    """Báo 'đã xoá' mà không nói xoá bao nhiêu thì không kiểm chứng được."""
    src = inspect.getsource(pdpd.xoa)
    for khoa in ("don_hang_an_danh", "hoi_thoai_da_xoa", "ghi_chu"):
        assert khoa in src
