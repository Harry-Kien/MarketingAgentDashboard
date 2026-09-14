"""
Phòng thử: phiên chết KHÔNG được thành ngõ cụt.

LỖI ĐÃ XẢY RA THẬT (14.09.2026)
--------------------------------
Phiên thử sống trong RAM TIẾN TRÌNH (`agent/core/phong_thu_phien.py`), nên
nó biến mất mỗi lần máy chủ khởi động lại, và tự hết sau 2 giờ không dùng.
Tab đang mở vẫn giữ id cũ trong biến JS.

Nhật ký máy chủ ngay sau một lần bật lại:

    POST /api/phong-thu/phien/fYNFnjVgDAo/hoi -> 404 Not Found
    POST /api/phong-thu/phien/fYNFnjVgDAo/hoi -> 404 Not Found

Hai lần liên tiếp, cùng một tab: người dùng bấm Gửi, thấy toast "Phiên thử
không tồn tại hoặc đã hết hạn", bấm lại, vẫn thế. Không có gì trên màn hình
nói phải bấm "Phiên mới" hay tải lại trang — với họ, Phòng thử chỉ đơn giản
là hỏng.

BA RÀNG BUỘC CANH Ở ĐÂY
  * 404 -> tự mở phiên mới rồi gửi lại ĐÚNG MỘT LẦN (lặp vô hạn thì mỗi
    vòng là một lượt gọi model có thể tốn tiền);
  * mở phiên mới thì PHẢI xoá lượt cũ trên màn hình và nói ra — máy chủ
    không còn `history` ấy, màn hình giữ lại là màn hình nói dối;
  * nút Gửi khoá trong lúc chờ model: một lượt mất 3–7 giây, có ca 100
    giây, và mỗi cú bấm thừa là một lượt gọi model THẬT.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _khoi(dau: str, cuoi: str) -> str:
    return JS[JS.index(dau):JS.index(cuoi)]


HOI = _khoi("async function hoiPhongThu", '$("#phongthu-form")')
FORM = _khoi('$("#phongthu-form")?.addEventListener', "async function xoaPhienPhongThuTrenMayChu")


def test_404_thi_tu_mo_phien_moi_va_gui_lai():
    assert "e.ma !== 404" in HOI and "throw e" in HOI
    assert "await loadPhongThu();" in HOI
    # Gửi lại sau khi mở phiên mới — hai lời gọi `gui()` trong cùng một khối.
    assert HOI.count("await gui()") == 2


def test_chi_thu_lai_MOT_lan():
    """
    Vòng lặp `while` ở đây là vòng lặp gọi model — mỗi vòng có thể tốn tiền
    thật. Thử lại đúng một lần, và lần hai hỏng thì để lỗi nổ ra.
    """
    assert "while" not in HOI
    assert "if (!state.phongThu.phien) throw e;" in HOI


def test_mo_phien_moi_thi_xoa_luot_cu_va_noi_ra():
    assert "state.phongThu = { phien: null, luot: [] };" in HOI
    assert "veChatPhongThu();" in HOI
    assert "KHÔNG nhớ các lượt trước" in HOI


def test_khong_gui_khi_chua_co_phien():
    """`/phien/null/hoi` trả 404 vì một lý do khác hẳn — người đọc log đi tìm nhầm chỗ."""
    assert 'toast("Chưa mở được phiên thử' in HOI


def test_nut_gui_khoa_trong_luc_cho_model():
    assert "nut.disabled = true" in FORM and "o.disabled = true" in FORM
    assert 'nut.textContent = "Đang hỏi…"' in FORM
    # `finally`: model lỗi thì nút vẫn phải mở lại, không thì màn hình chết cứng.
    assert "finally" in FORM and "nut.disabled = false" in FORM


def test_xoa_phien_khong_bao_do_khi_404():
    doan = _khoi("async function xoaPhienPhongThuTrenMayChu", '$("#phongthu-moi")')
    assert "if (e.ma !== 404) toast(e.message, true);" in doan
