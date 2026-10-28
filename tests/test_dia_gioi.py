"""
Danh mục hành chính sau sáp nhập 2025 — chỉ chặn khi CHẮC CHẮN sai.

Đỏ giả ở đây tệ hơn xanh giả thường lệ: chặn nhầm là khách thật đang đặt
hàng bị hỏi lại vô cớ. Nên phần lớn test dưới đây canh chiều KHÔNG chặn.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from agent.core import dia_gioi as d


def test_du_lieu_di_theo_repo_va_du():
    """Đọc được trên mọi máy, kể cả bản clone sạch — không phụ thuộc data/."""
    raw = json.loads(d.TEP.read_text(encoding="utf-8"))
    assert len(raw["tinh"]) == 34
    assert sum(len(t["phuong"]) for t in raw["tinh"]) > 3000
    assert raw["giay_phep"] == "MIT"
    assert (d.TEP.parent / "dia_gioi_vn.LICENSE").read_text(encoding="utf-8").count("MIT License") == 1


@pytest.mark.parametrize("chu,ten", [
    ("TP Hồ Chí Minh", "Thành phố Hồ Chí Minh"), ("TP.HCM", "Thành phố Hồ Chí Minh"),
    ("Sài Gòn", "Thành phố Hồ Chí Minh"), ("hcm", "Thành phố Hồ Chí Minh"),
    ("Hà Nội", "Thành phố Hà Nội"), ("HN", "Thành phố Hà Nội"),
    ("tỉnh an giang", "Tỉnh An Giang"), ("Thanh Hóa", "Tỉnh Thanh Hoá"),
])
def test_tim_tinh(chu, ten):
    t = d.tim_tinh(chu)
    assert t and t["ten"] == ten


def test_tinh_cu_da_sap_nhap_khong_nhan_ra():
    assert d.tim_tinh("Quảng Nam") is None and d.tim_tinh("Bình Dương") is None


def test_bat_mau_thuan_chac_chan():
    msg = d.mau_thuan("12 Lê Lợi, Phường Ba Đình, TP Hồ Chí Minh")
    assert msg and "Ba Đình" in msg and "Hỏi lại khách" in msg


@pytest.mark.parametrize("dia_chi", [
    "12 Lê Lợi, Phường Ba Đình, Thành phố Hà Nội",            # đúng
    "5 Nguyễn Huệ, Phường Sài Gòn, TP.HCM",                   # đúng
    "5 Nguyễn Huệ, Phường Bến Nghé, Quận 1, TP HCM",          # địa chỉ cũ ba cấp
    "Số 3, Phường 1, Vĩnh Long",                              # phường đánh số
    "Tổ 2, Phường Ba Đình, Quảng Nam",                        # tỉnh cũ: không chắc
    "1 A, Xã Không Có Thật, Hà Nội",                          # không nhận ra: không chắc
    "12 Lê Lợi, Ba Đình, TP Hồ Chí Minh",                     # thiếu tiền tố phường
    "giao ở cổng chợ", "",
])
def test_khong_chac_thi_khong_chan(dia_chi):
    assert d.mau_thuan(dia_chi) is None


def test_cong_cu_len_don_dung_lai_khi_dia_chi_mau_thuan():
    from agent.core import tools

    kq = asyncio.run(tools._tao_don_hang({
        "items": [{"ten_san_pham": "x", "so_luong": 1}], "khach_ten": "Chị Lan",
        "khach_sdt": "0912345678", "khach_dia_chi": "12 Lê Lợi, Phường Ba Đình, TP Hồ Chí Minh",
        "khach_da_xac_nhan": True}, products=[], conversation_id=None))
    assert kq["tao_duoc"] is False and "Ba Đình" in kq["ly_do"]
