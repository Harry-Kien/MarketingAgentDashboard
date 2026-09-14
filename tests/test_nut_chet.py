"""
Không có NÚT CHẾT trên dashboard.

Một điều khiển vẽ ra mà không mã nào bắt sự kiện thì bấm vào không có gì
xảy ra — không lỗi, không toast, không log. Người dùng kết luận "tính năng
này hỏng" và thôi dùng. Đã xảy ra: ảnh sản phẩm trong Kho mang
`data-xemanh` từ lâu mà không có gì bắt, bấm vào im lặng.

Hai chiều canh, cùng tinh thần với `test_dashboard_goi_dung_duong.py`:

  - mọi `data-<x>="…"` mà app.js/index.html vẽ ra phải có chỗ đọc nó:
    selector `[data-x]` / `[data-x=`, hoặc `dataset.<camelX>`
  - mọi `id` của button/form/select/input trong index.html phải được app.js
    nhắc tới, hoặc có `name` để FormData đọc

Danh sách THUỘC TÍNH DỮ LIỆU (không phải hành động) khai tường minh dưới
đây; thêm một thuộc tính chỉ-để-đọc mới thì thêm vào đó, kèm lý do.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")

# Thuộc tính mang DỮ LIỆU cho một handler khác đọc, không phải nút.
CHI_DE_DOC = {
    "view",       # tab thanh bên: handler chung đọc dataset.view
    "tokenslot",  # ô nhận kết quả sức khoẻ kênh
    "bat", "dangkhoa", "chu",   # trạng thái kèm theo nút cạnh nó
    "vtbang",     # bảng tick vai trò, xoá theo id người
    "contact",    # id khách trên dòng — nút hàng là chính dòng
    "nguoi",      # id nhân viên trên dòng — nút nằm trong dòng
    "chuloc", "kieu", "ma", "truong", "so",
}


def _camel(d: str) -> str:
    p = d.split("-")
    return p[0] + "".join(x.title() for x in p[1:])


def test_moi_data_hanh_dong_deu_co_handler():
    sinh = set(re.findall(r'data-([a-z][a-z0-9-]*)="\$\{', JS))
    sinh |= set(re.findall(r'data-([a-z][a-z0-9-]*)="', HTML))
    chet = []
    for d in sorted(sinh - CHI_DE_DOC):
        co = (re.search(r"\[data-" + re.escape(d) + r"[\]=]", JS)
              or ("dataset." + _camel(d)) in JS)
        if not co:
            chet.append("data-" + d)
    assert not chet, f"vẽ ra mà không gì bắt sự kiện: {chet}"
    assert len(sinh) > 60, "bộ đọc quét được quá ít — hỏng rồi vẫn xanh"


def test_moi_dieu_khien_co_id_deu_duoc_nhac_toi():
    ids = set(re.findall(
        r'<(?:button|form|select|input|textarea)\b[^>]*\bid="([^"]+)"', HTML))
    thieu = []
    for i in sorted(ids):
        nhac = f"#{i}" in JS or f'getElementById("{i}")' in JS
        # Ô trong form đọc qua FormData theo `name` — không cần id trong JS.
        co_name = re.search(rf'<(?:select|input|textarea)\b[^>]*\bid="{re.escape(i)}"[^>]*\bname=', HTML) \
            or re.search(rf'<(?:select|input|textarea)\b[^>]*\bname="[^"]+"[^>]*\bid="{re.escape(i)}"', HTML)
        if not nhac and not co_name:
            thieu.append(i)
    assert not thieu, f"điều khiển có id mà app.js không nhắc tới: {thieu}"
