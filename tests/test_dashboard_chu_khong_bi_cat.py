"""
Chữ giải thích hậu quả không được cắt cụt.

LỖI THẬT, THẤY KHI MỞ DASHBOARD LÊN NHÌN (03.09.2026)

`.row__sub` mang `white-space: nowrap` + `text-overflow: ellipsis`. Đúng cho
danh sách hội thoại — mỗi dòng là một bản xem trước, cắt cụt là bình thường.

Nhưng màn Cấu hình và màn Kỹ năng dùng đúng lớp ấy cho câu "tắt cái này thì
mất gì", và cả hai màn được thiết kế QUANH việc người vận hành đọc câu đó
trước khi bấm. Trên màn hình hẹp nó ra thế này:

    Lưu ý: Nâng lên: an toàn hơn, nhưng chuyển người …

Người vận hành đọc được nửa câu rồi bấm. Nửa còn lại — "nên ca trực nặng
hơn" — là nửa đáng cân nhắc nhất.

Không nổ, không lỗi, và trông vẫn gọn gàng. Đúng kiểu hỏng im lặng, chỉ là
lần này nó hỏng ở phía con người chứ không phải phía máy.

Có một ca kiểm CSS ở đây thay vì chỉ nhìn bằng mắt, vì lần dọn dẹp CSS sau
sẽ không ai nhớ vì sao bốn selector kia tồn tại.
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")

# Vùng mà `.row__sub` LÀ nội dung, không phải nhãn phụ.
VUNG_PHAI_XUONG_DONG = (
    "#cauhinh-ds",
    "#kynang-cosan",
    "#kynang-plugin",
    "#tichhop-ds",
)


def _khoi_css(selector: str) -> str:
    """Thân của khối CSS chứa selector này, hoặc chuỗi rỗng."""
    for m in re.finditer(r"([^{}]+)\{([^}]*)\}", CSS):
        if selector in m.group(1):
            return m.group(2)
    return ""


@pytest.mark.parametrize("vung", VUNG_PHAI_XUONG_DONG)
def test_chu_giai_thich_duoc_xuong_dong(vung):
    than = _khoi_css(f"{vung} .row__sub")
    assert than, (
        f"{vung} .row__sub không có luật riêng — nó sẽ thừa kế "
        "`white-space: nowrap` của .row__sub và bị cắt cụt giữa câu"
    )
    assert "white-space: normal" in than, f"{vung}: thiếu white-space: normal"


def test_luat_chung_van_giu_nowrap():
    """
    Không được sửa `.row__sub` chung. Danh sách hội thoại CẦN cắt cụt: mỗi
    dòng là một bản xem trước, và cho nó xuống dòng thì danh sách 40 hội
    thoại dài gấp ba, người trực phải cuộn nhiều hơn để làm cùng một việc.
    """
    than = _khoi_css(".row__sub")
    assert "nowrap" in than, (
        "luật .row__sub chung đã mất nowrap — danh sách hội thoại sẽ dài ra"
    )


@pytest.mark.parametrize("vung", VUNG_PHAI_XUONG_DONG)
def test_vung_do_that_su_ton_tai_trong_html(vung):
    """
    Selector CSS trỏ vào một id không có trong HTML là mã chết: nó không
    làm gì, không ai biết, và lần dọn dẹp sau sẽ xoá nhầm luật đang dùng.
    """
    assert f'id="{vung.lstrip("#")}"' in HTML, (
        f"{vung} có luật CSS nhưng không có phần tử nào mang id đó"
    )


def test_man_cau_hinh_va_ky_nang_deu_dung_row_sub():
    """
    Canh chiều ngược lại: nếu hai màn ấy đổi sang lớp khác thì luật ở trên
    thành vô dụng, và chữ lại bị cắt — im lặng như cũ.
    """
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    for ham in ("loadCauHinh", "loadKyNang"):
        i = js.find(f"function {ham}")
        assert i != -1, f"không tìm thấy {ham} trong app.js"
        than = js[i:i + 2600]
        assert "row__sub" in than, (
            f"{ham} không còn dùng .row__sub — luật cho chữ xuống dòng thành "
            "vô dụng và chữ giải thích lại bị cắt"
        )
