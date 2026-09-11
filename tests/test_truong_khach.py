"""
Trường khách tuỳ biến — kiểm kiểu ở MÃ.

Dashboard vẽ ô nhập theo kiểu, nên mọi thứ trông đúng cho tới khi có ai gọi
API trực tiếp, hoặc một tab cũ còn mở. Khi ấy `so` nhận một chuỗi, `chon`
nhận giá trị ngoài danh sách, và nó LƯU ĐƯỢC — không lỗi, không nhật ký.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.core import truong_khach as tk  # noqa: E402

CHU = {"ma": "ghi_chu", "nhan": "Ghi chú", "kieu": "chu"}
SO = {"ma": "tuoi", "nhan": "Tuổi", "kieu": "so"}
NGAY = {"ma": "sinh_nhat", "nhan": "Sinh nhật", "kieu": "ngay"}
BOOL = {"ma": "vip", "nhan": "Khách VIP", "kieu": "dung_sai"}
CHON = {"ma": "loai_da", "nhan": "Loại da", "kieu": "chon",
        "lua_chon": ["dầu", "khô", "hỗn hợp"]}
NHIEU = {"ma": "quan_tam", "nhan": "Quan tâm", "kieu": "nhieu_chon",
         "lua_chon": ["mụn", "nám", "lão hoá"]}


# --- mã trường -------------------------------------------------------

@pytest.mark.parametrize("ma", ["loai_da", "tuoi", "ghi_chu_2", "a"])
def test_ma_hop_le(ma):
    assert tk.kiem_ma(ma) == ma


@pytest.mark.parametrize("ma", [
    "", "Loai_Da", "loại_da", "loai da", "loai.da", "2tuoi", "_x", None,
    "a" * 41,
])
def test_ma_khong_hop_le_thi_nem(ma):
    """
    Khoá có dấu chấm làm mọi truy vấn đường dẫn JSONB trở nên mơ hồ, và
    người viết truy vấn sau này không đoán ra vì sao nó không khớp.
    """
    with pytest.raises(tk.TruongHong):
        tk.kiem_ma(ma)


# --- từng kiểu -------------------------------------------------------

def test_chu_cat_khoang_trang():
    assert tk.kiem_gia_tri(CHU, "  da nhạy cảm  ") == "da nhạy cảm"


def test_so_nhan_chuoi_so_va_dau_phay_thap_phan():
    assert tk.kiem_gia_tri(SO, "28") == 28.0
    assert tk.kiem_gia_tri(SO, "1,5") == 1.5


def test_so_tu_choi_chu():
    with pytest.raises(tk.TruongHong):
        tk.kiem_gia_tri(SO, "hai mươi tám")


def test_bool_bi_TU_CHOI_o_truong_so():
    """
    `bool` là con của `int` trong Python, nên `isinstance(True, int)` là
    True. Không loại nó ra thì `True` lặng lẽ lưu thành 1 — sai kiểu mà
    không nổ, và sáu tháng sau có một cột "Tuổi" toàn số 1 mà không ai
    truy được nguồn.

    Loại ra rồi thì nó rơi xuống nhánh ép chuỗi, `float("True")` ném, và
    người gửi nhận 422 nói rõ trường nào. Đó mới là thứ đáng có: `True`
    trong ô Tuổi là một nhầm lẫn, không phải một em bé một tuổi.
    """
    with pytest.raises(tk.TruongHong):
        tk.kiem_gia_tri(SO, True)
    assert isinstance(tk.kiem_gia_tri(SO, 28), float)


def test_ngay_phai_dung_dinh_dang():
    assert tk.kiem_gia_tri(NGAY, "1995-03-12") == "1995-03-12"
    for hong in ("12/03/1995", "1995-13-01", "hôm qua", 19950312):
        with pytest.raises(tk.TruongHong):
            tk.kiem_gia_tri(NGAY, hong)


def test_dung_sai_nhan_ca_tieng_viet():
    assert tk.kiem_gia_tri(BOOL, "có") is True
    assert tk.kiem_gia_tri(BOOL, "không") is False
    assert tk.kiem_gia_tri(BOOL, True) is True
    with pytest.raises(tk.TruongHong):
        tk.kiem_gia_tri(BOOL, "có lẽ")


def test_chon_tu_choi_gia_tri_ngoai_danh_sach():
    assert tk.kiem_gia_tri(CHON, "dầu") == "dầu"
    with pytest.raises(tk.TruongHong) as loi:
        tk.kiem_gia_tri(CHON, "da cá sấu")
    # Thông báo phải NÓI RA danh sách hợp lệ, không chỉ "giá trị sai".
    assert "dầu" in str(loi.value)


def test_nhieu_chon_bo_trung_nhung_giu_thu_tu():
    """
    `set` làm thứ tự nhảy mỗi lần tải trang, và người ta tưởng dữ liệu bị
    đổi.
    """
    assert tk.kiem_gia_tri(NHIEU, ["nám", "mụn", "nám"]) == ["nám", "mụn"]


def test_nhieu_chon_tu_choi_lua_chon_la():
    with pytest.raises(tk.TruongHong):
        tk.kiem_gia_tri(NHIEU, ["mụn", "không có thật"])


# --- rỗng và bắt buộc -------------------------------------------------

def test_rong_thi_tra_None_neu_khong_bat_buoc():
    for d in (CHU, SO, NGAY, CHON):
        assert tk.kiem_gia_tri(d, "") is None
        assert tk.kiem_gia_tri(d, None) is None


def test_bat_buoc_de_rong_thi_nem():
    d = dict(CHU, bat_buoc=True)
    with pytest.raises(tk.TruongHong):
        tk.kiem_gia_tri(d, "")


def test_khong_bao_gio_tra_None_thay_cho_gia_tri_hong():
    """
    Trả `None` khi giá trị hỏng là lưu một ô rỗng thay cho thứ người dùng
    vừa gõ — và họ thấy "đã lưu", rồi mở lại thấy trống.
    """
    with pytest.raises(tk.TruongHong):
        tk.kiem_gia_tri(SO, "abc")


# --- cả hồ sơ ---------------------------------------------------------

def test_kiem_ho_so_chuan_hoa_va_bo_o_rong():
    ra = tk.kiem_ho_so([CHU, SO, CHON],
                       {"ghi_chu": " x ", "tuoi": "30", "loai_da": ""})
    assert ra == {"ghi_chu": "x", "tuoi": 30.0}


def test_khoa_la_thi_NEM_chu_khong_bo_qua():
    """
    Bỏ qua im lặng là kịch bản tệ nhất: người vận hành vừa xoá một trường,
    tab cũ vẫn gửi khoá cũ lên, máy chủ nuốt, và họ thấy "đã lưu" trong khi
    dữ liệu vừa gõ không đi đâu cả.
    """
    with pytest.raises(tk.TruongHong) as loi:
        tk.kiem_ho_so([CHU], {"ghi_chu": "x", "truong_da_xoa": "y"})
    assert "truong_da_xoa" in str(loi.value)


def test_khong_gui_thi_khong_dong_toi():
    """Gửi một phần không được xoá các trường còn lại."""
    assert tk.kiem_ho_so([CHU, SO], {"tuoi": 1}) == {"tuoi": 1.0}


def test_moi_kieu_deu_co_nhan_tieng_viet():
    assert set(tk.NHAN_KIEU) == set(tk.KIEU)
    for nhan in tk.NHAN_KIEU.values():
        assert nhan and nhan[0].isupper()
