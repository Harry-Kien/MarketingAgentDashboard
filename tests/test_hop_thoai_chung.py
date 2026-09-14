"""
Dashboard không còn hộp prompt()/alert() của trình duyệt; mọi chỗ hỏi
người dùng đi qua MỘT hộp thoại chung (`hoiHop`).

VÌ SAO
------
prompt() có đúng một ô chữ: không nhãn, không ô số, không ô ngày, không
kiểm gì. Hỏi hai thứ là hai hộp nối nhau — bấm Huỷ ở hộp sau là mất hộp
trước. Đo trên hệ thống thật 14.09.2026: Tạo việc bắt gõ ngày dạng
YYYY-MM-DD vào ô chữ; Nhập kho, Kiểm kê, Gộp khách, Đo bài đăng, Tắt agent
đều là chuỗi prompt. Một hộp chung, dựng ô theo mô tả, dùng lại lớp phủ
`.cong` của màn đăng nhập — cả app chỉ có một kiểu hộp thoại.

Cùng đợt: những lỗi giao diện đo được bằng DOM trên 17 màn ở 1366px và
375px — dải nút gợi ý Phòng thử tràn tới 3.312px, Nhật ký hiện JSON thô
bị cắt, ô cấu hình không có nhãn, nhãn trạng thái tràn mép ở khổ điện
thoại, 74 nút cao 26px không bấm được bằng ngón tay.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")


def _khoi(dau: str, dai: int = 1400) -> str:
    i = JS.index(dau)
    return JS[i:i + dai]


# ---------------- không còn hộp của trình duyệt ----------------

def _bo_chu_thich(js: str) -> str:
    """
    Xoá chú thích nhưng GIỮ số dòng (thay bằng dòng trống), để dòng báo
    lỗi trỏ đúng chỗ. Chú thích của chính bản vá nhắc tới "prompt()" — quét
    cả chú thích là chốt đỏ vì lời giải thích của nó.
    """
    js = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), js, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", js)


def test_khong_con_prompt_hay_alert_nao():
    """Chốt tổng: thêm một prompt() mới ở bất kỳ đâu là đỏ ngay."""
    ma = _bo_chu_thich(JS)
    con = [m.start() for m in re.finditer(r"(?<![\w.])(prompt|alert)\(", ma)]
    dong = sorted({ma.count("\n", 0, i) + 1 for i in con})
    assert not dong, f"còn prompt()/alert() ở dòng: {dong}"


def test_bo_chu_thich_van_bat_duoc_prompt_that():
    """
    Canh chính bộ lọc trên: lọc quá tay là chốt tổng xanh với mọi thứ.

    Chỉ bỏ `//` ĐẦU DÒNG, cố ý: bỏ `//` giữa dòng là cắt luôn `https://`
    trong chuỗi, và mã sau đó thành thứ không còn là mã.
    """
    assert "prompt(" not in _bo_chu_thich("/* prompt() */ x = 1;\n  // prompt(\n")
    assert "prompt(" in _bo_chu_thich("/* ok */ const a = prompt('x'); // ghi chú\n")
    assert "https://x" in _bo_chu_thich('u = "https://x"; // web\n')


def test_hop_thoai_chung_ton_tai_va_dong_duoc_bang_esc():
    assert 'id="congHoi"' in HTML and 'id="hoiform"' in HTML
    assert "function hoiHop(" in JS and "function hoiDong(" in JS
    assert 'e.key === "Escape" && hoiDangMo' in JS
    # Hộp mới thay hộp cũ, không chồng hai Promise treo mãi.
    assert "if (hoiDangMo) hoiDong(null);" in JS


def test_tam_cho_hoi_deu_di_qua_hop_chung():
    for dau in ('$("#cv-them")', '$$("[data-knhap]")', '$$("[data-kkiemke]")',
                '$("#gopLam")', "async function rtYeuCauDem", '$$("[data-pmetric]")',
                'box.querySelector("[data-posted]")', "$$('[data-agentbat]')"):
        assert "hoiHop(" in _khoi(dau), f"{dau} chưa dùng hoiHop"


def test_tao_viec_co_o_ngay_that():
    """Gõ YYYY-MM-DD vào ô chữ là gõ sai một nửa số lần; ô ngày thì không."""
    khoi = _khoi('$("#cv-them")')
    assert 'type: "date"' in khoi
    # Hạn "ngày X" = hết ngày X giờ máy người dùng, không phải 0h UTC.
    assert 'new Date(d.han + "T23:59:59")' in khoi


def test_nhap_kho_kiem_ke_co_o_so():
    assert 'type: "number"' in _khoi('$$("[data-knhap]")')
    khoi = _khoi('$$("[data-kkiemke]")')
    assert 'type: "number"' in khoi and "required: true" in khoi


# ---------------- lỗi giao diện đo được ----------------

def test_nhat_ky_khong_hien_json_tho():
    khoi = _khoi("async function loadEvents")
    assert "moTaChiTiet(e.detail)" in khoi
    assert 'title="${esc(JSON.stringify(e.detail))}"' in khoi   # JSON đủ vẫn còn khi rê chuột
    assert "function moTaChiTiet" in JS


def test_goi_y_phong_thu_xuong_dong():
    khoi = _khoi("async function loadPhongThu")
    assert 'class="row__sub row__sub--truot"' in khoi
    assert "veChatPhongThu();" in khoi     # khung chat không trống trơn lúc mới mở


def test_o_cau_hinh_co_nhan_cho_bo_doc_man_hinh():
    khoi = _khoi("function oNhapCauHinh")
    assert khoi.count('aria-label="${esc(m.nhan)}"') == 3
    assert 'aria-label="Hồ sơ agent cho' in JS
    assert 'data-api-khoa="${m.khoa}" aria-label=' in JS


def test_kho_dien_thoai_nut_du_cao_va_nhan_khong_tran():
    mobile = CSS[CSS.index("@media (max-width: 560px)"):]
    mobile = mobile[:mobile.index("\n}\n")]
    assert ".btn--sm, .chip { padding: 7px 12px; min-height: 34px; }" in mobile
    assert ".row__side { max-width: 46%; flex-wrap: wrap; }" in mobile
    assert ".tag, .src, .pill { white-space: normal;" in mobile
    # Nhãn nằm trong tiêu đề một dòng: tiêu đề phải xuống dòng ở khổ hẹp.
    assert ".row__title { white-space: normal;" in mobile


def test_khong_con_chu_PII_trong_danh_sach_khach():
    """Chủ shop không biết PII là gì; họ biết SĐT và email."""
    assert "Chưa có PII xác minh" not in JS
