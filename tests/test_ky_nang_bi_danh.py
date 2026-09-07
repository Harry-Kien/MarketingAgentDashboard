"""
Một dòng bảng nhận nhiều cách gọi: "Hồ Chí Minh | Sài Gòn | HCM | TPHCM".

VÌ SAO
------
`_tra_bang` so khớp theo chuỗi sau khi bỏ dấu. "Hồ Chí Minh" thì trúng,
"Sài Gòn" và "HCM" thì trượt — mỗi cách gọi khác là một lần agent nói
"chưa có thông tin" cho một dòng ĐÃ CÓ trong bảng. Cách chữa cũ là chép
dòng ấy ra bốn lần với bốn khoá, và bốn lần sửa mỗi khi giá đổi.

VÌ SAO DÙNG GẠCH ĐỨNG, KHÔNG PHẢI DẤU PHẨY
------------------------------------------
Dấu phẩy nằm sẵn trong tên thật ("Quận 1, TP.HCM"). Gạch đứng thì không,
và người dán từ Excel đã quen nó là dấu tách cột — cùng ký tự `docBangDan`
đang dùng.

LUẬT CHỐNG KHOÁ NUỐT NHAU VẪN GIỮ NGUYÊN, ÁP CHO TỪNG BÍ DANH
-------------------------------------------------------------
Bí danh là khoá thật với `_tra_bang`, nên "sg" và "sgn" lồng nhau vẫn
nguy hiểm y như hai dòng lồng nhau — cùng một cách hỏng, chỉ khác chỗ gõ.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.ky_nang.ban_mo_ta import LoiBanMoTa, doc_ban_mo_ta  # noqa: E402
from agent.ky_nang.chay import chay_plugin  # noqa: E402


def _bm(bang: dict[str, str]):
    return doc_ban_mo_ta({
        "ten": "tra_phi_ship",
        "loai": "tra_bang",
        "mo_ta": "Tra phí giao hàng theo tỉnh thành. Không dùng cho câu hỏi tình trạng đơn.",
        "tham_so": [{"ten": "khoa", "mo_ta": "Tỉnh hoặc thành phố khách ở"}],
        "cau_hinh": {"bang": bang},
    })


def _tra(bm, khoa):
    return asyncio.run(chay_plugin(bm, {"khoa": khoa}))


BANG = {
    "Hồ Chí Minh | Sài Gòn | TPHCM": "Phí 25.000đ, giao 1-2 ngày",
    "Hà Nội | Thủ đô": "Phí 35.000đ, giao 2-3 ngày",
}


# --- Tra bằng bí danh -------------------------------------------------

@pytest.mark.parametrize("hoi", ["Hồ Chí Minh", "Sài Gòn", "sai gon", "TPHCM", "tphcm"])
def test_moi_cach_goi_deu_ra_dung_dong(hoi):
    kq = _tra(_bm(BANG), hoi)
    assert kq["tim_thay"] is True
    assert kq["gia_tri"] == "Phí 25.000đ, giao 1-2 ngày"


def test_dong_khac_khong_bi_anh_huong():
    kq = _tra(_bm(BANG), "Thủ đô")
    assert kq["gia_tri"] == "Phí 35.000đ, giao 2-3 ngày"


def test_khong_khop_van_la_khong_khop():
    kq = _tra(_bm(BANG), "Đà Nẵng")
    assert kq["tim_thay"] is False


def test_khoa_tra_ve_la_ten_chinh_khong_phai_bi_danh():
    """
    Agent đọc `khoa` để nhắc lại cho khách. Trả về "tphcm" thì câu trả lời
    thành "dạ TPHCM thì phí 25.000đ" — đúng nghĩa nhưng đọc như máy. Tên
    chính là cái người vận hành viết ra để hiện.
    """
    kq = _tra(_bm(BANG), "tphcm")
    assert kq["khoa"] == "Hồ Chí Minh"


def test_ca_cau_dai_van_khop():
    """
    HỒI QUY THẬT nếu bí danh chỉ "chạy nhờ" nhánh khớp-chứa.

    `_tra_bang` so hai chiều: `khoa in cau` hoặc `cau in khoa`. Model hay
    điền cả cụm khách nói. Với khoá một tên, "ho chi minh" nằm trong "minh
    o ho chi minh" nên khớp. Nếu bí danh chỉ là chuỗi dài "ho chi minh |
    sai gon | tphcm" thì KHÔNG chiều nào đúng, và một dòng đang chạy tốt
    bỗng trượt ngay sau khi người vận hành thêm cách gọi thứ hai — họ vừa
    làm bảng tốt lên và nhận về một bảng tệ đi.
    """
    bm = _bm({"Hồ Chí Minh | Sài Gòn": "Phí 25.000đ"})
    assert _tra(bm, "mình ở Hồ Chí Minh")["gia_tri"] == "Phí 25.000đ"
    assert _tra(bm, "em ở Sài Gòn nha")["gia_tri"] == "Phí 25.000đ"


def test_bi_danh_khong_bi_dinh_lien_nhau():
    """Chuỗi thô "a | b" chứa cả "a | b"; tách rồi thì không bí danh nào là
    "hồ chí minh | sài" cả."""
    bm = _bm({"Hồ Chí Minh | Sài Gòn": "A"})
    assert _tra(bm, "Minh | Sài")["tim_thay"] is False


# --- Luật cũ vẫn giữ --------------------------------------------------

def test_bi_danh_long_nhau_bi_chan():
    """"sg" nằm trong "sgn": câu chứa "sg" nhận câu trả lời của dòng ấy một
    cách chắc nịch, đúng cách hỏng mà luật cũ sinh ra để chặn."""
    with pytest.raises(LoiBanMoTa) as e:
        _bm({"Sài Gòn | sg": "A", "Cần Thơ | sgn": "B"})
    assert "sg" in str(e.value)


def test_bi_danh_trung_giua_hai_dong_bi_chan():
    with pytest.raises(LoiBanMoTa):
        _bm({"Hồ Chí Minh | HCM": "A", "Hà Nội | HCM": "B"})


def test_bi_danh_rong_bi_bo_qua():
    """"Hà Nội ||  | Thủ đô" là gõ nhầm, không phải một bí danh rỗng."""
    bm = _bm({"Hà Nội ||  | Thủ đô": "Phí 35.000đ"})
    assert bm.cau_hinh["bang"]["Hà Nội ||  | Thủ đô"] == "Phí 35.000đ"


# --- Bảng cũ không đổi nghĩa ------------------------------------------

def test_bang_khong_co_gach_dung_chay_y_nhu_cu():
    """Mọi bảng đã lưu đều không có gạch đứng — chúng phải xử sự y hệt."""
    bm = _bm({"đi làm": "Bôi hai đốt ngón tay.", "bãi biển": "Chọn loại kháng nước."})
    assert (_tra(bm, "đi làm"))["gia_tri"] == "Bôi hai đốt ngón tay."
    assert (_tra(bm, "khong co"))["tim_thay"] is False


def test_khop_nhieu_dong_van_hoi_lai():
    bm = _bm({"đi làm | công sở": "A", "đi biển | bãi tắm": "B"})
    kq = _tra(bm, "đi")
    assert kq["tim_thay"] is False and len(kq["nhieu_ket_qua"]) == 2
