"""
Kiểm thử bộ làm-tự-nhiên. Không gọi API.

Mỗi ca ở đây là một dấu hiệu lộ bot có thật, quan sát được từ chính các
lần chạy trước của hệ thống này.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core.tu_nhien import (  # noqa: E402
    DAI_TOI_DA,
    SO_TIN_TOI_DA,
    cham_diem,
    lam_tu_nhien,
    nhip_go,
)


# =====================================================================
#  Phát hiện dấu hiệu lộ bot
# =====================================================================

def test_chao_lai_o_tin_thu_hai_la_dau_hieu():
    t = "Dạ em chào chị, serum này giá 690.000đ ạ."
    assert "chào lại lần nữa" in cham_diem(t, lan_dau=False)
    # Chào ở tin ĐẦU là đúng, không được tính là lỗi.
    assert "chào lại lần nữa" not in cham_diem(t, lan_dau=True)


def test_gach_dau_dong_la_dau_hieu():
    t = "Routine buổi tối:\n- Tẩy trang\n- Sữa rửa mặt\n- Toner"
    assert "gạch đầu dòng" in cham_diem(t, lan_dau=True)


def test_markdown_la_dau_hieu():
    assert "chữ đậm markdown" in cham_diem("Giá **690.000đ** ạ", lan_dau=True)
    assert "tiêu đề markdown" in cham_diem("# Sản phẩm\nGiá 690k", lan_dau=True)


def test_cau_ket_sao_rong_la_dau_hieu():
    t = "Dạ serum giá 690.000đ ạ. Anh chị cần hỗ trợ gì thêm không ạ?"
    assert "câu kết sáo rỗng" in cham_diem(t, lan_dau=True)


def test_cau_mo_sao_rong_la_dau_hieu():
    t = "Cảm ơn chị đã quan tâm đến sản phẩm bên em ạ. Serum giá 690.000đ."
    assert "câu mở sáo rỗng" in cham_diem(t, lan_dau=True)


def test_tin_qua_dai_la_dau_hieu():
    t = "Dạ. " + "Sản phẩm này hỗ trợ cấp ẩm cho da rất tốt ạ. " * 12
    assert any("quá dài" in d for d in cham_diem(t, lan_dau=True))


@pytest.mark.parametrize("t", [
    "Dạ serum phục hồi giá 690.000đ ạ.",
    "Da dầu thì mình dùng gel rửa mặt kiềm dầu sẽ hợp hơn nha.",
    "Combo này còn hàng ạ, mình lấy mấy bộ để em lên đơn?",
])
def test_cau_tra_loi_tu_nhien_khong_bi_bao_dong(t):
    assert cham_diem(t, lan_dau=False) == []


# =====================================================================
#  Sửa
# =====================================================================

def test_bo_gach_dau_dong_giu_noi_dung():
    t = "Routine tối nha:\n- Tẩy trang\n- Sữa rửa mặt\n- Toner"
    ra = " ".join(lam_tu_nhien(t, lan_dau=True))
    assert "-" not in ra.replace("690.000-", "")
    for tu in ("Tẩy trang", "Sữa rửa mặt", "Toner"):
        assert tu in ra, f"mất nội dung: {tu}"


def test_bo_chao_lai_giu_noi_dung():
    t = "Dạ em chào chị, serum phục hồi giá 690.000đ ạ."
    ra = " ".join(lam_tu_nhien(t, lan_dau=False))
    assert "chào chị" not in ra.lower()
    assert "690.000đ" in ra


def test_giu_chao_o_tin_dau_tien():
    t = "Dạ em chào chị, serum phục hồi giá 690.000đ ạ."
    assert "chào" in " ".join(lam_tu_nhien(t, lan_dau=True)).lower()


def test_chao_la_toan_bo_noi_dung_thi_khong_xoa_sach():
    """Thà chào thừa còn hơn gửi tin rỗng cho khách."""
    assert lam_tu_nhien("Dạ em chào chị ạ.", lan_dau=False)


def test_bo_cau_ket_sao_rong():
    t = "Dạ serum giá 690.000đ ạ. Anh chị cần hỗ trợ gì thêm không ạ?"
    ra = " ".join(lam_tu_nhien(t, lan_dau=False))
    assert "690.000đ" in ra
    assert "hỗ trợ gì thêm" not in ra


def test_tach_khoi_dai_thanh_nhieu_tin():
    t = ("Da dầu mùa hè thì mình nên ưu tiên làm sạch nhẹ nhàng trước đã ạ. "
         "Gel rửa mặt kiềm dầu Aurora Clear Foam có BHA 0.5% giúp thông thoáng lỗ chân lông. "
         "Sau đó mình dùng thêm toner cân bằng để da không bị khô căng nha. "
         "Combo hai món này bên em đang có giá 690.000đ ạ.")
    tin = lam_tu_nhien(t, lan_dau=False)
    assert 2 <= len(tin) <= SO_TIN_TOI_DA
    assert all(len(x) <= DAI_TOI_DA for x in tin)
    assert "690.000đ" in " ".join(tin)


def test_tin_ngan_khong_bi_tach():
    t = "Dạ combo này còn hàng ạ."
    assert lam_tu_nhien(t, lan_dau=False) == [t]


def test_khong_bao_gio_tra_ve_rong_khi_co_noi_dung():
    for t in ["Dạ.", "690.000đ", "- Toner", "**Giá**: 690k"]:
        assert lam_tu_nhien(t, lan_dau=False), f"nuốt mất nội dung: {t!r}"


def test_dau_vao_rong_thi_tra_ve_rong():
    assert lam_tu_nhien("", lan_dau=True) == []
    assert lam_tu_nhien("   \n ", lan_dau=True) == []


def test_ket_qua_sau_khi_sua_thi_sach_dau_hieu():
    """Vòng khép kín: sửa xong thì chấm điểm phải sạch."""
    t = ("Dạ em chào chị. Routine tối nha:\n- Tẩy trang\n- Sữa rửa mặt\n"
         "- Toner cân bằng\nAnh chị cần hỗ trợ gì thêm không ạ?")
    for tin in lam_tu_nhien(t, lan_dau=False):
        assert cham_diem(tin, lan_dau=False) == [], f"còn dấu hiệu trong: {tin!r}"


# =====================================================================
#  Nhịp gửi
# =====================================================================

def test_tin_dai_hon_thi_go_lau_hon():
    assert nhip_go("Dạ vâng ạ.") < nhip_go("Dạ da dầu thì mình nên dùng gel "
                                           "rửa mặt kiềm dầu sẽ hợp hơn nha ạ.")


def test_nhip_go_co_tran():
    """Không được bắt khách chờ chỉ vì câu trả lời dài."""
    assert nhip_go("từ " * 500) <= 4.0


def test_nhip_go_luon_duong():
    assert nhip_go("Dạ") > 0


def test_khong_bao_gio_tao_ra_tin_dai_hon_nguong():
    """
    Từng hỏng thật: vòng gộp đuôi tạo ra tin 884 ký tự, gấp 5 lần ngưỡng —
    đúng thứ mà cả module này sinh ra để tránh.
    """
    dai = " ".join(
        f"Câu số {i} nói về một bước chăm sóc da buổi tối cho da hỗn hợp thiên dầu."
        for i in range(1, 16)
    )
    for tin in lam_tu_nhien(dai, lan_dau=False):
        assert len(tin) <= DAI_TOI_DA, f"tin {len(tin)} ký tự, vượt {DAI_TOI_DA}"


def test_khong_mat_noi_dung_khi_tach_khoi_rat_dai():
    dai = " ".join(f"Bước {i}: rửa mặt thật kỹ nhé bạn ơi." for i in range(1, 12))
    ghep = " ".join(lam_tu_nhien(dai, lan_dau=False))
    for i in range(1, 12):
        assert f"Bước {i}:" in ghep, f"mất Bước {i}"
