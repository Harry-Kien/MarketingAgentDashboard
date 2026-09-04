"""
Khoá bảng lồng nhau thì TỪ CHỐI lúc lưu, đừng để nó trả lời sai lúc chạy.

LỖI THẬT, ĐO ĐƯỢC 04.09.2026

Người dùng đang tạo plugin `tra_bao_hanh` và để nguyên ô gợi ý của giao
diện: `{"bang": {"serum": "12 tháng"}}`. Cấu hình đó LƯU ĐƯỢC, và:

    'serum dưỡng tóc'  -> 'serum': '12 tháng'
    'serum khử mùi'    -> 'serum': '12 tháng'
    'kem chống nắng'   -> không thấy

Danh mục cửa hàng có BỐN sản phẩm chứa chữ "serum" — Serum Sau Tẩy Lông,
Serum Dưỡng Trắng, Serum Dưỡng Tóc, Serum Khử Mùi Hôi Nách. Một dòng trả
lời thay cho cả bốn.

VÌ SAO KHÔNG CÓ AI HỎI LẠI

`chay._tra_bang` khớp đúng trước, rồi khớp CHỨA hai chiều, và nhánh "khớp
nhiều dòng" mới hỏi lại khách. Với hai khoá lồng nhau, câu hỏi rơi vào giữa
chỉ khớp ĐÚNG MỘT dòng — dòng ngắn. Không mơ hồ, nên nhánh hỏi lại không
bao giờ chạy tới. Khách nhận một con số sai và tin nó.

Khoá KHÔNG lồng nhau thì trường hợp xấu nhất là khớp nhiều dòng, và lúc đó
đã có người hỏi lại. Hỏi lại thì không ai bị trả lời sai.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.ky_nang.ban_mo_ta import (  # noqa: E402
    LoiBanMoTa,
    bo_dau,
    doc_ban_mo_ta,
    khoa_long_nhau,
)

KY_NANG = ROOT / "agent" / "ky_nang"


def tho(bang: dict[str, str]) -> dict:
    return {
        "ten": "tra_bao_hanh",
        "loai": "tra_bang",
        "mo_ta": "Chính sách đổi trả và hạn dùng sau khi mở nắp từng dòng sản phẩm.",
        "tham_so": [{"ten": "dong_san_pham", "mo_ta": "Tên dòng sản phẩm khách hỏi."}],
        "cau_hinh": {"bang": bang},
    }


# ---------------------------------------------------------------
#  Ca trung tâm — đúng cấu hình người dùng suýt lưu
# ---------------------------------------------------------------

def test_serum_long_trong_serum_duong_toc_bi_TU_CHOI():
    with pytest.raises(LoiBanMoTa) as e:
        doc_ban_mo_ta(tho({"serum": "12 tháng", "serum dưỡng tóc": "6 tháng"}))
    assert "serum" in str(e.value)


def test_thong_diep_noi_RO_khoa_nao_nuot_khoa_nao():
    """
    "Cấu hình không hợp lệ" bắt người ta đi dò 13 dòng. Nói thẳng cặp nào
    thì sửa mất mười giây.
    """
    with pytest.raises(LoiBanMoTa) as e:
        doc_ban_mo_ta(tho({"kem": "a", "kem chống nắng": "b"}))
    thong_diep = str(e.value)
    assert "'kem'" in thong_diep and "'kem chống nắng'" in thong_diep


def test_bang_13_dong_that_cua_cua_hang_VAN_luu_duoc():
    """
    Phép chặn phải để lọt bảng đúng. Chặn quá tay thì người ta bỏ plugin,
    và mất luôn thứ nó sinh ra để làm.
    """
    doc_ban_mo_ta(tho({
        "Kem Tẩy Lông": "a", "Serum Sau Tẩy Lông": "b", "Nước Tẩy Trang": "c",
        "Sữa Rửa Mặt": "d", "Tẩy Tế Bào Chết": "e", "Nước Hoa Hồng": "f",
        "Serum Dưỡng Trắng": "g", "Kem Dưỡng Ẩm": "h", "Kem Chống Nắng": "i",
        "Serum Dưỡng Tóc": "j", "Serum Khử Mùi Hôi Nách": "k",
        "Bọt Vệ Sinh Nữ": "l", "Bọt Vệ Sinh Nam": "m",
    }))


# ---------------------------------------------------------------
#  So khớp phải BỎ DẤU và KHÔNG phân biệt hoa thường
# ---------------------------------------------------------------

@pytest.mark.parametrize("a,b", [
    ("Serum", "SERUM DƯỠNG TÓC"),      # khác hoa thường
    ("serum", "serum duong toc"),      # một bên không dấu
    ("  serum  ", "serum dưỡng tóc"),  # thừa khoảng trắng
])
def test_long_nhau_bi_bat_du_go_kieu_gi(a, b):
    """
    Lúc CHẠY, `bo_dau` bỏ dấu và hạ chữ thường rồi mới so. Phép kiểm lúc LƯU
    mà so nguyên văn thì nó bỏ lọt đúng những cặp sẽ đụng nhau lúc chạy.
    """
    assert khoa_long_nhau({a: "x", b: "y"}) is not None


def test_khoa_chi_TRUNG_MOT_PHAN_thi_KHONG_bi_chan():
    """
    "Kem Dưỡng Ẩm" và "Kem Chống Nắng" cùng bắt đầu bằng "Kem" nhưng không
    cái nào lọt trong cái kia. Câu hỏi mơ hồ ("kem") khớp cả hai, và nhánh
    hỏi lại sẽ chạy — an toàn, nên không được chặn.
    """
    assert khoa_long_nhau({"Kem Dưỡng Ẩm": "a", "Kem Chống Nắng": "b"}) is None


def test_bang_mot_dong_khong_bao_gio_long_nhau():
    assert khoa_long_nhau({"Kem Chống Nắng": "a"}) is None


def test_bat_duoc_cap_o_GIUA_bang_khong_chi_hai_dong_dau():
    """
    Duyệt thiếu thì bảng dài lọt lưới, mà bảng dài mới hay lồng nhau.

    Dữ liệu độn cố tình KHÔNG đánh số. Bản đầu của test này dùng `dong 0..19`
    và đỏ ngay — vì "dong 1" nằm lọt trong "dong 10". Phép chặn đúng, dữ liệu
    độn sai; và đó cũng là bằng chứng cái bẫy này dễ dính tới mức nào.
    """
    bang = {f"muc {chr(97 + i)}": "x" for i in range(20)}
    bang["Sữa Rửa Mặt"] = "a"
    bang["Sữa Rửa Mặt Dịu Nhẹ"] = "b"
    cap = khoa_long_nhau(bang)
    assert cap is not None and "Sữa Rửa Mặt" in cap


# ---------------------------------------------------------------
#  Một định nghĩa `bo_dau`, không phải hai
# ---------------------------------------------------------------

def test_chi_co_MOT_dinh_nghia_bo_dau():
    """
    Phép kiểm lúc LƯU và phép so khớp lúc CHẠY phải chuẩn hoá y hệt nhau.
    Hai bản sao thì lúc nào đó chúng lệch, và khi ấy phép kiểm nói một đằng
    còn bộ chạy làm một nẻo — không lỗi, không nhật ký.
    """
    dinh_nghia = []
    for tep in KY_NANG.glob("*.py"):
        for node in ast.walk(ast.parse(tep.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name.lstrip("_") == "bo_dau":
                dinh_nghia.append(f"{tep.name}:{node.name}")
    assert len(dinh_nghia) == 1, f"có {len(dinh_nghia)} bản sao: {dinh_nghia}"


def test_chay_dung_CHUNG_bo_dau_voi_ban_mo_ta():
    from agent.ky_nang import chay

    assert chay.bo_dau is bo_dau, "chay.py dùng một hàm chuẩn hoá khác"


# ---------------------------------------------------------------
#  Mẫu điền sẵn trong giao diện phải tự nó hợp lệ
# ---------------------------------------------------------------

def test_mau_trong_giao_dien_luu_duoc():
    """
    Người vận hành SỬA mẫu chứ không VIẾT lại. Mẫu mà bị chính phép kiểm từ
    chối thì ai bấm Lưu lần đầu cũng ăn lỗi — và học được rằng thông báo lỗi
    của hệ thống này là thứ nên bỏ qua.
    """
    import json
    import re

    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    m = re.search(r"tra_bang:\s*'((?:[^'\\]|\\.)*)'", js)
    assert m, "không tìm thấy mẫu tra_bang trong app.js"
    mau = json.loads(m.group(1).encode().decode("unicode_escape"))
    doc_ban_mo_ta(tho(mau["bang"]))
