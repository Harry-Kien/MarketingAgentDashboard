"""
`scripts.kiem_goi`: kiểm một gói đã cài mà KHÔNG gọi model sinh văn bản.

VÌ SAO CẦN SCRIPT NÀY
---------------------
Cài gói xong, ba mảnh của nó nằm ở ba chỗ khác nhau: hướng dẫn kích hoạt
theo từ khoá, công cụ trong bảng plugin, tài liệu trong kho tri thức. Mảnh
nào hỏng cũng KHÔNG nổ — agent chỉ lặng lẽ trả lời như chưa từng có gói.
Đúng kiểu hỏng im lặng mà repo này sợ nhất.

VÌ SAO CÁC PHÉP KIỂM Ở ĐÂY ĐỀU CÓ THỂ ĐỎ
----------------------------------------
Bản nháp đầu có hai phép kiểm nghe hợp lý mà KHÔNG BAO GIỜ đỏ được:

  * "mỗi từ khoá phải kích hoạt chính gói của nó" — `chon_goi` so
    `fold(k) in fold(cau_hoi)`, mà câu hỏi ở đây CHÍNH LÀ từ khoá, nên
    `fold(k) in fold(k)` luôn đúng.
  * "mỗi khoá bảng tra lại phải ra chính nó" — `_tra_bang` so bằng
    `bo_dau`, và khoá lồng nhau đã bị chặn từ lúc lưu.

Cả hai luôn xanh, tức là xanh giả: chúng thưởng cho mọi gói, kể cả gói
hỏng. Bỏ đi, thay bằng những phép có ca đỏ thật — mỗi test dưới đây dựng
đúng một gói hỏng và đòi script bắt được.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.ky_nang import goi as g  # noqa: E402
from scripts import kiem_goi as k  # noqa: E402


def _goi(**doi) -> g.Goi:
    d = {
        "ten": "tu-van-chong-nang",
        "phien_ban": "1.0.0",
        "mo_ta": "Tư vấn chọn và dùng kem chống nắng theo hoàn cảnh của khách.",
        "tu_khoa": ["chống nắng", "spf"],
        "huong_dan": "Khi khách hỏi về kem chống nắng, hỏi hoàn cảnh dùng trước "
                     "rồi mới gợi ý. Không nhận xét về tình trạng da của khách.",
        "cong_cu": [],
        "tai_lieu": [],
    }
    d.update(doi)
    return g.doc_goi(d)


def _bang(bang: dict[str, str]) -> dict:
    return {
        "ten": "tra_cach_dung",
        "loai": "tra_bang",
        "mo_ta": "Tra cách dùng kem chống nắng theo hoàn cảnh. Không dùng cho câu hỏi về giá.",
        "tham_so": [{"ten": "khoa", "mo_ta": "Hoàn cảnh khách sẽ dùng"}],
        "cau_hinh": {"bang": bang},
    }


def _do(mucs: list[k.Muc]) -> list[k.Muc]:
    return [m for m in mucs if m.trang_thai == k.HONG]


def _canh_bao(mucs: list[k.Muc]) -> list[k.Muc]:
    return [m for m in mucs if m.trang_thai == k.CANH_BAO]


# --- Từ khoá quá rộng ------------------------------------------------

def test_tu_khoa_chiem_cau_nghiep_vu_thi_canh_bao():
    """
    Gói lấy từ khoá "đơn" sẽ kích hoạt cả khi khách hỏi tình trạng đơn
    hàng. Hướng dẫn tư vấn chống nắng chen vào một lượt tra đơn là prompt
    thừa: tốn tiền mỗi lượt và kéo agent lạc đề.
    """
    mucs = k.kiem_tu_khoa(_goi(tu_khoa=["đơn"]), [])
    assert _canh_bao(mucs), "từ khoá 'đơn' chiếm câu hỏi đơn hàng mà không ai báo"
    assert any("đơn" in m.chi_tiet for m in _canh_bao(mucs))


def test_tu_khoa_hep_thi_khong_canh_bao():
    assert not _canh_bao(k.kiem_tu_khoa(_goi(), []))


# --- Bị gói khác chiếm chỗ -------------------------------------------

def test_bi_day_khoi_hai_suat_thi_do():
    """
    Mỗi lượt chỉ nạp hướng dẫn của GOI_MOI_LUOT_TOI_DA gói. Ba gói cùng
    khớp một từ khoá thì gói xếp sau rớt — nó vẫn "đang bật" trên
    dashboard, vẫn không bao giờ tới lượt, và không có gì báo.
    """
    ta = _goi(ten="tu-van-chong-nang", tu_khoa=["spf"])
    khac = [_goi(ten=t, tu_khoa=["spf"]) for t in ("aaa-goi-mot", "bbb-goi-hai")]
    mucs = k.kiem_tu_khoa(ta, khac)
    assert _do(mucs), "gói bị đẩy khỏi hai suất mỗi lượt mà không ai báo"
    assert any("spf" in m.chi_tiet for m in _do(mucs))


def test_mot_goi_khac_cung_khop_thi_van_qua():
    ta = _goi(tu_khoa=["spf"])
    assert not _do(k.kiem_tu_khoa(ta, [_goi(ten="aaa-goi-mot", tu_khoa=["spf"])]))


# --- Từ khoá thừa ----------------------------------------------------

def test_tu_khoa_long_nhau_thi_canh_bao():
    """"chống nắng" đã trùm "chống nắng cho da dầu" — cụm dài không bao giờ
    ăn thêm lượt nào, chỉ làm người đọc tưởng gói phủ rộng hơn thực tế."""
    mucs = k.kiem_tu_khoa(_goi(tu_khoa=["chống nắng", "chống nắng cho da dầu"]), [])
    assert _canh_bao(mucs)


# --- Bảng tra --------------------------------------------------------

def test_kiem_bang_goi_duoc_tu_trong_event_loop():
    """
    LỖI THẬT, gặp ngay lần chạy đầu.

    `kiem_bang` từng gọi `asyncio.run(chay_plugin(...))`, chạy ngon khi
    test gọi thẳng nó, và nổ `RuntimeError: asyncio.run() cannot be called
    from a running event loop` khi `chay()` gọi nó — vì `chay()` đã ở
    trong một vòng lặp. Bộ test cũ xanh trong khi script không chạy nổi
    một lần: test đi một đường, script đi đường khác.

    Test này đi ĐÚNG đường script đi.
    """
    async def nhu_trong_chay():
        return await k.kiem_bang(_bang({"đi làm": "Bôi hai đốt ngón tay."}))

    assert not _do(asyncio.run(nhu_trong_chay()))


def test_tu_dau_chung_giua_cac_khoa_thi_canh_bao():
    """
    Hai khoá mở đầu bằng cùng một từ: model điền tham số cụt thành "đi" thì
    `_tra_bang` khớp hai dòng và agent hỏi lại thay vì trả lời.

    Không kiểm "mỗi khoá tra lại ra chính nó": `_tra_bang` so bằng trước,
    và khoá lồng nhau đã bị `doc_ban_mo_ta` chặn từ lúc lưu — phép đó
    không bao giờ đỏ được với một bảng hợp lệ.
    """
    mucs = asyncio.run(k.kiem_bang(_bang({"đi làm": "Bôi hai đốt ngón tay.",
                              "đi biển": "Chọn loại kháng nước."})))
    assert _canh_bao(mucs), "hai khoá cùng mở đầu bằng 'đi' mà không ai báo"
    assert not _do(mucs), "khớp mập mờ là cảnh báo, không phải hỏng"


def test_khoa_rieng_hin_thi_khong_canh_bao():
    mucs = asyncio.run(k.kiem_bang(_bang({"đi làm": "Bôi hai đốt ngón tay.",
                              "bãi biển": "Chọn loại kháng nước."})))
    assert not _do(mucs) and not _canh_bao(mucs)


def test_gia_tri_rong_thi_do():
    mucs = asyncio.run(k.kiem_bang(_bang({"đi làm": "Bôi hai đốt ngón tay.", "đi biển": "   "})))
    assert _do(mucs)


# --- Truy vấn dùng để thử tra tài liệu --------------------------------

def test_tra_tai_lieu_bang_noi_dung_khong_bang_tieu_de():
    """
    ĐỎ GIẢ THẬT, gặp ngay lần chạy đầu trên gói tu-van-chong-nang.

    Bản đầu tra kho tri thức bằng chính TIÊU ĐỀ tài liệu và báo HỎNG khi
    tiêu đề không lọt top 5. Nhưng `retrieve` xếp theo ngữ nghĩa của NỘI
    DUNG: tiêu đề "Cách đọc nhãn kem chống nắng" thua ba tài liệu cũ, dù
    hỏi "SPF 50 chặn bao nhiêu phần trăm" thì chính nó đứng đầu với 0.842.

    Script khi ấy bảo người vận hành cài lại một gói đang chạy tốt. Đỏ giả
    làm người ta đi kiểm rồi mất niềm tin vào bảng — nhẹ hơn xanh giả,
    nhưng vẫn phải sửa.

    Truy vấn phải lấy từ nội dung, thứ thật sự nằm trong đoạn được nhúng.
    """
    t = {"tieu_de": "Cách đọc nhãn kem chống nắng",
         "noi_dung": "SPF là mức bảo vệ trước tia UVB, con số càng cao thì "
                     "thời gian bảo vệ càng dài. PA là mức bảo vệ trước UVA."}
    q = k.truy_van_tra(t)
    assert t["tieu_de"] not in q, "vẫn tra bằng tiêu đề — đúng lỗi đỏ giả cũ"
    assert q in t["noi_dung"], "truy vấn phải là một mẩu có thật trong nội dung"
    assert len(q) >= 20, "mẩu quá ngắn thì tra ra gì cũng được"


def test_truy_van_tra_khong_no_voi_noi_dung_mot_dong():
    t = {"tieu_de": "X", "noi_dung": "A" * 60}
    assert k.truy_van_tra(t) in t["noi_dung"]


# --- Mã thoát --------------------------------------------------------

@pytest.mark.parametrize("trang_thai, mong", [
    ([k.TOT, k.TOT], 0),
    ([k.TOT, k.CANH_BAO], 0),
    ([k.TOT, k.HONG], 1),
])
def test_ma_thoat_do_thi_khac_khong(trang_thai, mong):
    """
    Cảnh báo KHÔNG làm đỏ mã thoát. Một bảng lúc nào cũng đỏ là bảng người
    ta thôi đọc — cùng lý do `san_sang` tách cảnh báo khỏi hỏng.
    """
    mucs = [k.Muc("x", t, "") for t in trang_thai]
    assert k.ma_thoat(mucs) == mong
