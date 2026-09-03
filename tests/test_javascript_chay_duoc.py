"""
JavaScript của dashboard phải PARSE ĐƯỢC.

LỖI THẬT, ĐÃ ĐẨY LÊN main (03.09.2026)

Một lần nối thêm mã vào `app.js` qua heredoc biến `\\n` thành xuống dòng
THẬT bên trong một chuỗi JS:

    confirm(
      "Xác nhận bảng giá đang dùng ĐÚNG là giá bán lẻ?
                                                       <- xuống dòng thật
    " +

`SyntaxError: Invalid or unexpected token`. Toàn bộ `app.js` chết — không
một dòng nào chạy.

HẬU QUẢ ĐO ĐƯỢC

  · KHÔNG ĐĂNG NHẬP ĐƯỢC. Form mất handler nên trình duyệt submit kiểu GET
    gốc, và URL thành `/?ten_dang_nhap=admin&mat_khau=admin123` — mật khẩu
    vào lịch sử trình duyệt và log máy chủ.
  · Mọi màn hình chết theo. Trang vẫn tải, vẫn đẹp, chỉ là không làm gì.

VÌ SAO 1898 TEST KHÔNG BẮT ĐƯỢC

Không ca nào parse JavaScript. Test đọc `app.js` như VĂN BẢN — tìm chuỗi,
đếm endpoint, kiểm selector — nên một tệp hỏng cú pháp vẫn qua hết. Xanh
giả, và nó đã lên tới nhánh main.

Python có `ruff` canh cú pháp từ đầu. JavaScript thì tới hôm nay mới có.

VÌ SAO KHÔNG TỰ VIẾT BỘ KIỂM BẰNG PYTHON

Bản đầu của tệp này có một phép đếm dấu nháy làm đường lui khi máy thiếu
node. Nó báo động giả ngay trên `app.js` thật: một regex `/[&<>"']/`, một
bảng escape HTML, và một template literal trải nhiều dòng.

Một ca kiểm báo đỏ oan sẽ bị gỡ trong lần dọn dẹp kế tiếp, và lúc đó ràng
buộc biến mất hoàn toàn. Thà dựa vào `node --check` — nó là bộ phân tích
thật — và nói thẳng khi không có node, còn hơn giữ một phép đoán.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
JS = sorted((ROOT / "dashboard").glob("*.js"))

_NODE = shutil.which("node")
# GitHub Actions đặt CI=true. Runner ubuntu-latest có sẵn node.
_TRONG_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes")


def _kiem(tep: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_NODE, "--check", str(tep)],
        capture_output=True,
        # Máy Windows tiếng Việt mặc định cp1258; không ép utf-8 thì chính
        # ca kiểm này nổ UnicodeDecodeError khi node in ra tên tệp có dấu.
        encoding="utf-8", errors="replace",
        timeout=60,
    )


def test_co_tim_thay_tep_js():
    """Đổi tên thư mục mà quên sửa đây thì mọi ca dưới xanh vì không có gì để kiểm."""
    assert JS, "không thấy tệp .js nào trong dashboard/"
    assert any(p.name == "app.js" for p in JS)


def test_ci_phai_co_node():
    """
    Trên máy cá nhân thiếu node thì bỏ qua được. Trong CI thì KHÔNG.

    Một ca kiểm luôn bị skip là một ca kiểm không tồn tại — và lần sau lỗi
    cú pháp lại lên tới main y như lần này.
    """
    if not _TRONG_CI:
        pytest.skip("không chạy trong CI")
    assert _NODE, (
        "CI không có node — bộ canh cú pháp JavaScript sẽ bị bỏ qua hoàn "
        "toàn. Thêm actions/setup-node vào .github/workflows/kiem-thu.yml."
    )


@pytest.mark.skipif(_NODE is None, reason="Máy này không có node")
@pytest.mark.parametrize("tep", JS, ids=lambda p: p.name)
def test_parse_duoc_bang_node(tep):
    r = _kiem(tep)
    assert r.returncode == 0, (
        f"{tep.name} KHÔNG parse được — cả tệp sẽ không chạy dòng nào, và "
        f"dashboard chết hoàn toàn:\n{(r.stderr or '')[:600]}"
    )


@pytest.mark.skipif(_NODE is None, reason="Máy này không có node")
def test_ca_kiem_tren_that_su_bat_duoc_loi(tmp_path):
    """
    Canh chính bộ canh. Gọi `node --check` sai cách thì nó luôn trả 0 và ca
    trên xanh vĩnh viễn — xanh giả, đúng thứ vừa để lọt một lỗi lên main.

    Dựng lại ĐÚNG kiểu hỏng đã gặp: xuống dòng thật trong chuỗi.
    """
    hong = tmp_path / "hong.js"
    hong.write_text('const a = "chuoi mo ra\nma khong dong";\n', encoding="utf-8")
    assert _kiem(hong).returncode != 0, (
        "node --check không bắt được lỗi cú pháp rõ ràng — bộ canh vô dụng"
    )


@pytest.mark.skipif(_NODE is None, reason="Máy này không có node")
def test_tep_hop_le_thi_khong_bao_dong_gia(tmp_path):
    """
    Chiều ngược lại. Báo đỏ oan thì ca kiểm sẽ bị gỡ trong lần dọn dẹp kế
    tiếp, và lúc đó ràng buộc biến mất hoàn toàn.

    Dùng đúng những cấu trúc mà bản đầu (đếm dấu nháy) từng bắt nhầm.
    """
    tot = tmp_path / "tot.js"
    tot.write_text(
        'const esc = (s) => String(s ?? "").replace(/[&<>"\']/g, (c) =>\n'
        '  ({ "&": "&amp;", \'"\': "&quot;", "\'": "&#39;" }[c]));\n'
        'const html = `<div class="${a === "x" ? "y" : "z"}">\n'
        '  nhieu dong\n'
        '</div>`;\n',
        encoding="utf-8",
    )
    r = _kiem(tot)
    assert r.returncode == 0, f"báo đỏ oan trên mã hợp lệ:\n{(r.stderr or '')[:400]}"
