"""
Màn Cấu hình: form thật thay cho chuỗi prompt(), và hàng form không bị cắt.

Hai lỗi đo được bằng mắt trên hệ thống thật trước bản này:

  - Ô chọn ở "Luật chia việc" và "SLA" hiện "Ca", "mọ", "tl", "10(": hàng
    `.form__row` nằm trong lưới hai cột `.form` nên chỉ được nửa panel, bốn
    ô co về cỡ chữ ngắn nhất.
  - Hồ sơ agent là NĂM hộp prompt() nối nhau, trường khách là bốn; bấm Huỷ ở
    hộp cuối là mất sạch, và hướng dẫn 4000 ký tự phải gõ trong một dòng.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")


def _doan(dau: str, cuoi: str) -> str:
    return JS[JS.index(dau):JS.index(cuoi)]


def test_hang_form_trai_het_hai_cot_va_o_gian_deu():
    assert ".form > .form__row" in CSS and "grid-column: 1 / -1" in CSS
    assert ".form__row > .field { flex: 1 1" in CSS


def test_ho_so_agent_la_form_khong_phai_prompt():
    assert 'id="hsaForm"' in HTML
    khoi = HTML[HTML.index('id="hsaForm"'):]
    khoi = khoi[:khoi.index("</form>")]
    assert '<textarea name="huong_dan"' in khoi          # 4000 ký tự cần ô nhiều dòng
    # `form.id` là thuộc tính id của form — ô nhập tên "id" bị che mất.
    assert 'name="ho_so_id"' in khoi and '<input type="hidden" name="id"' not in khoi
    doan = _doan("function hsaMoForm", "/* ---------------- trường thông tin khách")
    assert "prompt(" not in doan
    assert '"/ho-so-agent"' in doan and "`/ho-so-agent/${f.ho_so_id.value}`" in doan


def test_truong_khach_la_form_kieu_la_o_chon():
    assert 'id="truongForm"' in HTML and 'id="truongKieu"' in HTML
    doan = _doan("function truongMoForm", "/* ---------------- nhân sự: vai trò và quyền")
    assert 'prompt("' not in doan
    # confirm() còn lại duy nhất là hộp xoá kèm SỐ hồ sơ sắp mất giá trị
    # (máy chủ trả 409) — đó là câu hỏi mang thông tin, giữ lại có chủ ý.
    assert doan.count("confirm(") == 1 and "err.message" in doan[doan.index("confirm("):][:60]
    # Khi sửa: mã và kiểu khoá đúng như máy chủ từ chối đổi.
    assert "f.ma.disabled = !!t" in doan and "f.kieu.disabled = !!t" in doan
    # Tạo mới gửi cả `ma` và `kieu`; sửa thì không.
    assert "ma: f.ma.value.trim(), kieu" in doan


def test_form_la_phan_tu_tinh_khong_bi_vong_lam_moi_dung_lai():
    """`#hsa-ds`/`#truong-ds` dựng lại mỗi 6 giây; form nằm NGOÀI hai div ấy."""
    for form, ds in (("hsaForm", "hsa-ds"), ("truongForm", "truong-ds")):
        assert HTML.index(f'id="{form}"') < HTML.index(f'id="{ds}"')
