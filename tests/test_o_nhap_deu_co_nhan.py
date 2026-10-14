"""
Mọi ô nhập trên dashboard phải có tên đọc được.

Một ô nhập không nhãn vẫn dùng được bằng chuột — người ta nhìn dòng chữ
bên trên và hiểu. Bằng trình đọc màn hình thì nó đọc ra "edit, blank": ô
làm gì, bắt buộc hay không, điền kiểu gì — không có gì cả. Hỏng im lặng với
đúng nhóm người không có cách nào tự biết mình đang thiếu thông tin.

ĐO ĐƯỢC 22.09.2026: `index.html` dùng `<label class="field">` ở 81 chỗ và
`<div class="field">` ở 5 chỗ. Ba trong năm chỗ lệch ấy chứa ô nhập, nên
nhãn nhìn thấy được (`<span>`) KHÔNG gắn với ô nhập nào.

Dùng bộ phân tích HTML thật chứ không regex: bản nháp viết bằng regex báo
17 chỗ sai ở `app.js`, mà phần lớn là nút có chữ dạng `${...}` bị chính
biểu thức lọc ăn mất. Một bộ đo báo nhầm tệ hơn không có bộ đo — nó chỉ sai
chỗ, và người ta đi sửa phần đang đúng.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "dashboard" / "index.html"
APP_JS = ROOT / "dashboard" / "app.js"

# Không cần nhãn riêng: giá trị do mã đặt, hoặc đã có nhãn nhìn thấy kề bên
# theo đúng ngữ nghĩa của chính thẻ.
KHONG_CAN = {"hidden", "submit", "button", "reset", "image"}


class _Soi(HTMLParser):
    """Theo dõi độ sâu `<label>` để biết ô nhập có ĐƯỢC BỌC hay không."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sau_label = 0
        self.thieu: list[str] = []
        self.for_da_dung: set[str] = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "label":
            self.sau_label += 1
            if a.get("for"):
                self.for_da_dung.add(a["for"])
            return
        if tag not in ("input", "select", "textarea"):
            return
        if tag == "input" and (a.get("type") or "text").lower() in KHONG_CAN:
            return
        # Ô tick/radio hầu như luôn nằm cạnh chữ của chính nó; bỏ qua để
        # không đẻ ra tiếng ồn che mất lỗi thật.
        if tag == "input" and (a.get("type") or "").lower() in ("checkbox", "radio"):
            return

        co = (
            self.sau_label > 0
            or a.get("aria-label")
            or a.get("aria-labelledby")
            or a.get("placeholder")
            or a.get("title")
        )
        if not co:
            dong = self.getpos()[0]
            self.thieu.append(f"index.html:{dong} <{tag} {a.get('name') or a.get('id') or '?'}>")

    def handle_endtag(self, tag):
        if tag == "label" and self.sau_label:
            self.sau_label -= 1


def test_moi_o_nhap_trong_index_deu_co_ten_doc_duoc():
    soi = _Soi()
    soi.feed(INDEX.read_text(encoding="utf-8"))
    assert not soi.thieu, (
        "Ô nhập không có tên đọc được:\n  " + "\n  ".join(soi.thieu)
        + "\nSửa bằng MỘT trong ba cách: bọc trong <label class=\"field\"> "
        "(khối một ô), thêm aria-label (khối nhiều ô), hoặc <label for=…>."
        "\nĐừng đổi <span> thành <label>: `.field > span` đang mang style, "
        "đổi thẻ là vỡ giao diện."
    )


def test_hai_select_trong_customer360_co_nhan():
    """
    Hai ô này nằm trong panel Customer 360 do `app.js` dựng, nên bộ soi
    HTML ở trên không thấy. Chốt riêng vì chúng là ô người trực dùng hằng
    ngày: ghi consent và chọn ai đọc được ghi chú bàn giao.
    """
    js = APP_JS.read_text(encoding="utf-8")
    for ten in ('name="status"', 'name="visibility"'):
        i = js.find(f"<select {ten}")
        assert i != -1, f"không còn <select {ten}> — đọc lại test này"
        the = js[i: js.find(">", i)]
        assert "aria-label" in the, (
            f"<select {ten}> thiếu aria-label; trình đọc màn hình chỉ đọc "
            f"được các lựa chọn chứ không biết ô này hỏi gì"
        )


def test_vung_bam_cam_ung_du_to_va_dat_dung_cho():
    """
    Ô tick trên màn cảm ứng phải ≥24px (WCAG 2.2 AA · 2.5.8 Target Size).

    ĐO ĐƯỢC 22.09.2026 ở khung 375px: 13–16px trên ba màn. Nặng nhất là ô
    tick chọn khách — nó dùng để GIAO KHÁCH HÀNG LOẠT và chỉ xác nhận một
    lần cho cả lô, nên bấm trượt là giao nhầm khách cho người khác.

    Chốt cả THỨ TỰ, vì đó là chỗ bản vá đầu tiên hụt: đặt khối `pointer:
    coarse` gần đầu file thì `.chonkhach input { width: 16px }` ở phần sau
    THẮNG (cùng độ ưu tiên, luật sau ăn). Đo lại lúc ấy: màn Đăng bài lên
    24px còn màn Khách hàng vẫn 16px — sửa một nửa, và nửa hỏng là nửa
    nguy hiểm hơn.
    """
    css = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")

    i_coarse = css.find("@media (pointer: coarse)")
    assert i_coarse != -1, (
        "mất khối @media (pointer: coarse) — ô tick trở lại 13–16px trên "
        "điện thoại, và không có gì báo"
    )
    khoi = css[i_coarse: css.find("\n}", css.find(".chonkhach input", i_coarse)) + 2]
    assert "24px" in khoi, "khối cảm ứng không còn đặt 24px"

    i_chonkhach = css.rfind(".chonkhach input", 0, i_coarse)
    assert i_chonkhach == -1 or i_chonkhach < i_coarse, "logic tìm kiếm sai"
    # Luật 16px gốc phải đứng TRƯỚC khối cảm ứng, nếu không nó đè lại.
    for m in re.finditer(r"\.chonkhach input\s*\{[^}]*\}", css):
        if "16px" in m.group(0):
            assert m.start() < i_coarse, (
                "`.chonkhach input { …16px }` đang đứng SAU khối "
                "@media (pointer: coarse) nên đè mất nó. Giữ khối cảm ứng ở "
                "CUỐI file."
            )


def test_van_giu_cac_moc_tiep_can_toan_cuc():
    """
    Bốn thứ này đang CÓ và rất dễ mất trong một lần dọn CSS hay đổi khung.
    Chốt lại để mất là biết ngay, thay vì phát hiện qua một lời phàn nàn.
    """
    html = INDEX.read_text(encoding="utf-8")
    css = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")

    assert 'lang="vi"' in html, "<html> mất lang -> trình đọc đọc tiếng Việt bằng giọng Anh"
    assert "<main" in html or 'role="main"' in html, "mất mốc <main> để nhảy thẳng vào nội dung"
    assert "aria-live" in html or "aria-live" in js, (
        "toast không còn aria-live -> thông báo thành công/thất bại không "
        "được đọc lên, người dùng không biết thao tác đã ăn hay chưa"
    )
    assert ":focus-visible" in css, (
        "mất :focus-visible -> đi bằng phím Tab không thấy mình đang ở đâu"
    )
    assert "prefers-reduced-motion" in css, (
        "mất prefers-reduced-motion -> người đặt giảm chuyển động vẫn bị "
        "hiệu ứng, và với một số người đó là chóng mặt thật"
    )
