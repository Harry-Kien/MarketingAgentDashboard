"""
Câu thử lưu KÈM kỹ năng, chạy lại sau mỗi lần sửa.

VÌ SAO
------
Sửa một dòng trong bảng dài có thể làm hỏng dòng khác, và không gì bắt
được. Thêm "Sài Gòn" vào dòng Hồ Chí Minh là dòng "Sa Đéc" bỗng khớp mập
mờ; đổi một khoá là câu khách hỏi hôm qua hôm nay trượt. Không lỗi, không
nhật ký — chỉ là agent trả lời kém đi ở đúng chỗ nó vốn trả lời tốt.

Câu thử là bộ nhớ của những gì ĐÃ từng đúng. Người vận hành gõ vài câu
khách hay hỏi kèm chữ phải có trong câu trả lời; mỗi lần lưu, hệ thống
chạy lại toàn bộ và nói ngay câu nào trượt.

VÌ SAO CHỈ CHO `tra_bang`
-------------------------
Câu thử phải chạy được ở MỌI lần lưu, tức là phải rẻ và tất định.
`_tra_bang` là hàm thuần: không mạng, không model, không tiền. Bốn loại
kia đều ra ngoài — `tra_tai_lieu` gọi embedding, `goi_api_doc` và `mcp`
gọi máy chủ khác, và `chuyen_chuyen_biet` thì không có gì để đối chiếu.
Chạy chúng ở mỗi lần lưu là biến một cú bấm Lưu thành một lần gọi mạng.

VÌ SAO BÁO CHỨ KHÔNG CHẶN
-------------------------
Người vận hành có thể đang sửa dở: đổi khoá trước, sửa câu thử sau. Chặn
lưu ở đó là bắt họ sửa hai chỗ đúng thứ tự, và cách họ sẽ chọn là xoá câu
thử đi cho xong. Báo to thì họ thấy và tự quyết.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.ky_nang.ban_mo_ta import LoiBanMoTa, doc_ban_mo_ta  # noqa: E402
from agent.ky_nang.cau_thu import chay_cau_thu  # noqa: E402

BANG = {
    "đi làm | công sở": "Bôi hai đốt ngón tay trước khi ra khỏi nhà.",
    "bãi biển": "Chọn loại kháng nước, bôi lại sau mỗi lần lên bờ.",
}


def _tho(**ghi_de) -> dict:
    d = {
        "ten": "tra_cach_dung",
        "loai": "tra_bang",
        "mo_ta": "Tra cách dùng kem chống nắng theo hoàn cảnh. Không dùng cho câu hỏi về giá.",
        "tham_so": [{"ten": "khoa", "mo_ta": "Hoàn cảnh khách sẽ dùng"}],
        "cau_hinh": {"bang": BANG},
        "cau_thu": [
            {"hoi": "đi làm", "mong_doi": "hai đốt ngón tay"},
            {"hoi": "công sở", "mong_doi": "hai đốt ngón tay"},
        ],
    }
    d.update(ghi_de)
    return d


def chay(coro):
    return asyncio.run(coro)


# --- Bộ kiểm ----------------------------------------------------------

def test_cau_thu_di_qua_bo_kiem_va_giu_lai():
    bm = doc_ban_mo_ta(_tho())
    assert len(bm.cau_thu) == 2
    assert bm.cau_thu[0].hoi == "đi làm"
    assert bm.cau_thu[0].mong_doi == "hai đốt ngón tay"


def test_khong_co_cau_thu_van_hop_le():
    """Mọi plugin đã lưu đều chưa có ô này. Chúng phải nạp lại được y như cũ."""
    tho = _tho()
    del tho["cau_thu"]
    assert doc_ban_mo_ta(tho).cau_thu == ()


def test_chi_tra_bang_moi_co_cau_thu():
    """
    Bốn loại kia đều ra mạng. Cho khai câu thử ở đó là hứa một thứ chỉ chạy
    được khi có mạng, mà nó lại chạy ở mỗi lần bấm Lưu.
    """
    with pytest.raises(LoiBanMoTa) as e:
        doc_ban_mo_ta(_tho(
            loai="chuyen_chuyen_biet",
            tham_so=[],
            cau_hinh={"ly_do": "Khách hỏi hợp tác bán buôn"},
        ))
    assert "tra_bang" in str(e.value)


def test_qua_nam_cau_thu_bi_tu_choi():
    with pytest.raises(LoiBanMoTa):
        doc_ban_mo_ta(_tho(cau_thu=[{"hoi": f"h{i}", "mong_doi": "x"} for i in range(6)]))


def test_cau_thu_thieu_hoi_bi_tu_choi():
    with pytest.raises(LoiBanMoTa):
        doc_ban_mo_ta(_tho(cau_thu=[{"mong_doi": "x"}]))


def test_hoi_qua_dai_bi_cat_bo():
    with pytest.raises(LoiBanMoTa):
        doc_ban_mo_ta(_tho(cau_thu=[{"hoi": "x" * 300, "mong_doi": "y"}]))


# --- Chạy -------------------------------------------------------------

def test_moi_cau_dung_thi_khong_truot():
    ra = chay(chay_cau_thu(doc_ban_mo_ta(_tho())))
    assert [x["dat"] for x in ra] == [True, True]


def test_cau_sai_thi_noi_ro_no_nhan_duoc_gi():
    """
    Chỉ nói "trượt" thì người vận hành phải tự đi tra. Nói luôn agent trả
    về gì mới sửa được ngay tại chỗ.
    """
    bm = doc_ban_mo_ta(_tho(cau_thu=[{"hoi": "đi làm", "mong_doi": "kháng nước"}]))
    ra = chay(chay_cau_thu(bm))
    assert ra[0]["dat"] is False
    assert "hai đốt ngón tay" in ra[0]["nhan_duoc"]


def test_mong_doi_bo_trong_nghia_la_phai_KHONG_khop():
    """
    Ca quan trọng nhất của một bảng tra: khoá lạ phải trượt, để agent nói
    chưa có thông tin thay vì đoán. Không có cách khai ca ấy thì câu thử
    chỉ canh được nửa hành vi.
    """
    bm = doc_ban_mo_ta(_tho(cau_thu=[{"hoi": "Đà Nẵng", "mong_doi": ""}]))
    assert chay(chay_cau_thu(bm))[0]["dat"] is True

    bm2 = doc_ban_mo_ta(_tho(cau_thu=[{"hoi": "đi làm", "mong_doi": ""}]))
    assert chay(chay_cau_thu(bm2))[0]["dat"] is False


def test_khop_khong_phan_biet_hoa_thuong_va_dau():
    bm = doc_ban_mo_ta(_tho(cau_thu=[{"hoi": "DI LAM", "mong_doi": "HAI ĐỐT"}]))
    assert chay(chay_cau_thu(bm))[0]["dat"] is True


def test_bi_danh_cung_duoc_thu():
    """Bí danh là khoá thật với `_tra_bang`; câu thử phải với tới được."""
    bm = doc_ban_mo_ta(_tho(cau_thu=[{"hoi": "công sở", "mong_doi": "hai đốt"}]))
    assert chay(chay_cau_thu(bm))[0]["dat"] is True


def test_khong_co_cau_thu_thi_tra_rong():
    tho = _tho()
    del tho["cau_thu"]
    assert chay(chay_cau_thu(doc_ban_mo_ta(tho))) == []


def test_chay_cau_thu_khong_ra_mang():
    """
    Chạy ở MỌI lần lưu, nên nó phải thuần. Canh bằng AST như ràng buộc
    chỉ-đọc của `chay.py`: một lời gọi mạng lọt vào đây là mỗi cú bấm Lưu
    thành một lần ra ngoài.
    """
    import ast

    nguon = (ROOT / "agent" / "ky_nang" / "cau_thu.py").read_text(encoding="utf-8")
    cam = {"retrieve", "lay", "execute", "fetch", "fetchrow", "log_event", "complete"}
    pham = [
        n.func.attr for n in ast.walk(ast.parse(nguon))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr in cam
    ]
    assert not pham, f"câu thử gọi {pham} — nó chạy ở mỗi lần lưu"
