"""
Giao khách hàng loạt từ danh sách — chốt màn hình.

Hành vi máy chủ kiểm ở kịch bản nghiệm thu 12. Ở đây chỉ canh: màn hình có
ô tick, có thanh giao, gọi đúng endpoint một-giao-dịch, và tick không mất
qua vòng làm mới.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def test_co_o_tick_va_thanh_giao():
    assert 'id="chonbar"' in HTML and 'id="chonGiao"' in HTML
    assert 'data-chon="${contact.id}"' in JS


def test_goi_endpoint_mot_giao_dich_khong_lap_endpoint_don():
    doan = JS[JS.index('$("#chonGiao")'):]
    # Cắt tới đầu handler kế tiếp: khối này kết thúc bằng `});` ở cột 0.
    doan = doan[:doan.index(chr(10) + '});' + chr(10))]
    assert '"/contacts/chu-so-huu/hang-loat"' in doan
    assert 'for (const id of ids)' not in doan and 'ids.map((id) => api(' not in doan


def test_tick_song_qua_vong_lam_moi():
    """Tick mười khách rồi thấy mất sạch sau 6 giây là thứ người ta bỏ luôn."""
    assert "state.khachDaChon" in JS
    assert 'state.khachDaChon.has(contact.id) ? " checked"' in JS


def test_o_tick_nam_ngoai_nut_hang():
    """<button> không được chứa điều khiển khác — tick phải là anh em của nút."""
    i = JS.index('<label class="chonkhach"')
    j = JS.index('<button type="button" class="row row--avatar', i)
    assert "</label>" in JS[i:j]


def test_khong_co_quyen_giao_thi_khong_thay_o_tick():
    assert 'giaoDuoc ? `<label class="chonkhach"' in JS
