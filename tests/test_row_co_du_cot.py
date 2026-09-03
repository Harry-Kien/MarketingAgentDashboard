"""
Mọi `.row` phải có `.row__flag` — thiếu là nội dung biến mất hoàn toàn.

LỖI THẬT, NGƯỜI DÙNG BÁO BẰNG ẢNH CHỤP MÀN HÌNH (03.09.2026)

`.row` là lưới ba cột:

    grid-template-columns: 3px minmax(0, 1fr) auto;
                           ^^^ dải màu trạng thái

Cột đầu rộng ĐÚNG 3px và dành cho `.row__flag`. Bỏ nó đi thì `.row__body`
tụt lên cột 3px, và toàn bộ chữ bị `overflow: hidden` cắt sạch — trên màn
hình chỉ còn đúng MỘT ký tự ở mép trái.

Hai panel của màn Cấu hình mắc đúng lỗi này: "Ai đổi gì, lúc nào" và
"Không chỉnh được ở đây". Người dùng nhìn thấy một danh sách toàn dòng
trống, chỉ có mốc thời gian bên phải.

VÌ SAO KHÔNG CÓ TEST NÀO BẮT ĐƯỢC

Không lỗi JS, không lỗi HTTP, HTML hợp lệ, `node --check` xanh. Nó chỉ sai
về BỐ CỤC — và bố cục thì chỉ lộ ra khi mở lên nhìn.

Ca kiểm này biến "phải nhìn mới thấy" thành "chạy test là biết".
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")

sys.path.insert(0, str(ROOT))

# `<div class="row">` mở ra rồi tới thẻ con ĐẦU TIÊN.
_MO_ROW = re.compile(
    r'<div class="row(?:\s[^"]*)?">\s*(?:<!--.*?-->\s*)?<(\w+)([^>]*)>',
    re.S,
)


def _cot_dau_khong_phai_flag(van_ban: str) -> list[str]:
    xau = []
    for m in _MO_ROW.finditer(van_ban):
        thuoc_tinh = m.group(2)
        if "row__flag" in thuoc_tinh:
            continue
        dong = van_ban[: m.start()].count("\n") + 1
        xau.append(f"dòng {dong}: <{m.group(1)}{thuoc_tinh[:60]}>")
    return xau


def test_row_grid_van_co_cot_flag_3px():
    """
    Nếu ai đó bỏ cột 3px khỏi `.row` thì cả ca kiểm dưới thành vô nghĩa —
    và bố cục đổi trên toàn dashboard, không chỉ hai panel này.
    """
    khoi = re.search(r"\.row\s*\{([^}]*)\}", CSS)
    assert khoi, "không tìm thấy luật .row"
    than = " ".join(khoi.group(1).split())
    assert "grid-template-columns: 3px" in than, (
        f".row không còn bắt đầu bằng cột 3px: {than[:120]}"
    )


def test_row_trong_html_deu_co_flag():
    xau = _cot_dau_khong_phai_flag(HTML)
    assert not xau, (
        "index.html có .row thiếu .row__flag — nội dung sẽ tụt vào cột 3px "
        "và biến mất:\n" + "\n".join(xau[:8])
    )


def test_row_trong_js_deu_co_flag():
    xau = _cot_dau_khong_phai_flag(JS)
    assert not xau, (
        "app.js dựng .row thiếu .row__flag — nội dung sẽ tụt vào cột 3px "
        "và biến mất:\n" + "\n".join(xau[:8])
    )


def test_ca_kiem_that_su_bat_duoc_loi():
    """
    Canh chính bộ canh. Regex viết hỏng thì nó không khớp gì cả và hai ca
    trên xanh vĩnh viễn — xanh giả, đúng thứ vừa để lọt lỗi này tới tay
    người dùng.
    """
    hong = '<div class="row"><span class="row__body">chu</span></div>'
    assert _cot_dau_khong_phai_flag(hong), "regex không bắt được .row thiếu flag"

    lanh = ('<div class="row"><span class="row__flag"></span>'
            '<span class="row__body">chu</span></div>')
    assert not _cot_dau_khong_phai_flag(lanh), "báo đỏ oan trên .row hợp lệ"


def test_bat_duoc_ca_khi_flag_co_bien_the_mau():
    """`row__flag row__flag--auto` vẫn là flag, không được báo nhầm."""
    lanh = ('<div class="row"><span class="row__flag row__flag--halt"></span>'
            '<span class="row__body">x</span></div>')
    assert not _cot_dau_khong_phai_flag(lanh)


@pytest.mark.parametrize(
    "vung",
    ["#cauhinh-ds", "#kynang-cosan", "#kynang-plugin", "#tichhop-ds",
     "#cauhinh-lichsu"],
)
def test_chu_giai_thich_van_duoc_xuong_dong(vung):
    """
    Kèm luôn phần đã sửa lượt trước, cộng `#cauhinh-lichsu` bị bỏ sót lúc
    đó. Cả năm vùng đều là chữ giải thích, không phải nhãn xem trước.
    """
    khoi = re.search(
        re.escape(vung) + r"[^{}]*\.row__sub[^{}]*\{([^}]*)\}", CSS
    )
    assert khoi, f"{vung} .row__sub chưa có luật cho xuống dòng"
    assert "white-space: normal" in " ".join(khoi.group(1).split())


def test_nhat_ky_khong_do_JSON_tho_ra_man_hinh():
    """
    `{"mode":"auto","enabled":"True","zalo_account_id":null,...}` là thứ lập
    trình viên đọc được, không phải người trực ca. Nó dài 200 ký tự và chôn
    mất thứ duy nhất đáng nhìn: cái gì vừa đổi.
    """
    assert "doiThayCauHinh" in JS, "lịch sử cấu hình vẫn đổ JSON thô"
    assert "JSON.stringify(x.chi_tiet)" not in JS
