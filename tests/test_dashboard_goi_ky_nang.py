from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _than_ham(ten):
    m = re.search(r"(?:async )?function " + ten + r"\(.*?\n\}\n", JS, re.S)
    assert m, ten
    return m.group(0)


def test_panel_va_form_co_mat():
    assert 'id="goi-ds"' in HTML and 'id="goiform"' in HTML and 'id="goi-tep"' in HTML
    assert 'id="goi-kiem"' in HTML and 'id="goi-cai"' in HTML


def test_goi_dung_api():
    src = _than_ham("loadGoiKyNang")
    assert "/goi-ky-nang" in src and "esc(" in src
    for f in ("g.ten", "g.phien_ban", "g.mo_ta"):
        assert f"${{{f}}}" not in src, f
    cai = _than_ham("caiGoiKyNang")
    assert "/goi-ky-nang/kiem" in cai and "FormData" in cai and '"/goi-ky-nang/tep"' in cai


def test_cot_so_lan_goi_o_ky_nang_viet_san():
    src = _than_ham("gopKyNang") + _than_ham("loadKyNang")
    assert "so_lan_7_ngay" in src and "loadGoiKyNang()" in src
    # loadGoiKyNang() lỗi (vd CSDL chưa migrate 0014) không được lan lên
    # refresh() 6 giây, và panel #goi-ds phải NÓI ra là không tải được —
    # "Chưa có gói nào." khi CSDL hỏng là xanh giả (hỏng im lặng).
    assert re.search(r"try\s*\{\s*await loadGoiKyNang\(\);\s*\}\s*catch", src)
    assert "Không tải được gói kỹ năng" in src


def test_nut_kiem_nhan_tep_json_va_noi_ro_ve_zip():
    """
    Bản trước, nút Kiểm bỏ qua tệp đã chọn và lặng lẽ kiểm phần còn sót
    trong ô dán — người dùng thấy "Hợp lệ" cho một gói KHÁC gói họ chọn.
    Tệp phải THẮNG ô dán, và .zip (bộ giải nén chỉ có ở máy chủ) phải được
    nói thẳng ra, không im lặng kiểm nhầm.
    """
    src = _than_ham("caiGoiKyNang")
    assert "tep.text()" in src and "JSON.parse" in src
    assert re.search(r"\.zip\$/i\.test\(tep\.name\)", src)
    assert "Kiểm chỉ nhận .json" in src
    # Nhánh gửi tệp thật (FormData) chỉ chạy khi KHÔNG phải chỉ kiểm.
    assert "if (tep && !chiKiem)" in src


def test_cong_cu_cua_goi_khong_co_nut_xoa():
    """
    Máy chủ từ chối xoá riêng công cụ của gói; một nút luôn báo lỗi là nút
    dạy người ta bỏ qua thông báo lỗi. Thay bằng nhãn tên gói.
    """
    src = _than_ham("veDongKyNang")
    # Nhãn tên gói phải có, và tên gói phải qua esc(): nó là chữ từ máy chủ.
    assert re.search(r'gói \$\{esc\(\w+\.goi', src), "mất nhãn tên gói"
    # Nút Xoá chỉ được vẽ ở nhánh dành riêng cho công cụ TỰ TẠO. Kiểm theo
    # nhánh chứ không theo thứ tự xuất hiện: thứ tự đúng một cách tình cờ
    # vẫn xanh, còn nhánh thì nói đúng ràng buộc.
    assert src.index('nguon === "tu_tao"') < src.index("data-plugin-xoa")


def test_xuat_lich_su_khoi_phuc_co_nut():
    src = _than_ham("loadGoiKyNang")
    assert "data-goi-xuat" in src and "data-goi-lichsu" in src and "data-goi-battat" in src and "data-goi-xoa" in src
    assert "data-goi-khoiphuc" in JS
