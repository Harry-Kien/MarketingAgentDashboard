"""
Panel Cài đặt API: ô bí mật không bao giờ mang giá trị, có Kiểm tra và Lưu.
Kiểm bằng đọc mã (regex), cùng cách với tests/test_dashboard_khong_nhap_nhay.py.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _than_ham(ten: str) -> str:
    m = re.search(rf"(?:async )?function {ten}\(.*?\n\}}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}"
    return m.group(0)


def test_panel_nam_trong_man_cau_hinh():
    assert 'id="api-panel"' in HTML
    assert HTML.index('id="api-panel"') > HTML.index('data-view="cauhinh"')
    assert HTML.index('id="api-panel"') < HTML.index('id="cauhinh-ds"')


def test_o_bi_mat_la_password_va_khong_co_value():
    than = _than_ham("oNhapApi")
    the_password = re.search(r'<input type="password"[^>]*>', than, re.S)
    assert the_password, "ô bí mật phải là input type=password"
    # Không dựng thuộc tính value cho ô bí mật: giá trị không có ở client để mà dựng.
    assert "value=" not in the_password.group(0)
    assert 'autocomplete="off"' in the_password.group(0)


def test_co_nut_kiem_tra_va_luu_theo_nhom():
    than = _than_ham("loadCaiDatApi")
    assert "data-api-kiem" in than and "data-api-luu" in than


def test_kiem_tra_gui_gia_tri_dang_go_chua_luu():
    # Kiểm phải gửi thứ đang gõ (giaTriApiDangGo), không gửi cấu hình đã lưu.
    assert re.search(r"/cai-dat-api/kiem-tra[\s\S]{0,300}giaTriApiDangGo\(", JS)


def _nhanh_view(ten: str) -> str:
    """
    Thân của nhánh `if (state.view === "<ten>") { ... }` trong vòng làm mới.

    Trước đây test dưới đo KHOẢNG CÁCH 120 ký tự giữa `state.view` và lời
    gọi. Nó đỏ ngay khi có người thêm một loader khác vào cùng nhánh — một
    thay đổi hoàn toàn đúng — và người sửa sẽ nới con số ấy chứ không đọc
    lại ý định. Đọc đúng thân nhánh thì không có con số nào để nới.
    """
    i = JS.index(f'state.view === "{ten}"')
    j = JS.index("{", i)
    sau, k = 0, j
    while k < len(JS):
        if JS[k] == "{":
            sau += 1
        elif JS[k] == "}":
            sau -= 1
            if sau == 0:
                break
        k += 1
    return JS[j:k + 1]


def test_loader_goi_khi_mo_man_cau_hinh():
    assert "loadCaiDatApi()" in _nhanh_view("cauhinh")


def test_bo_doc_nhanh_view_khong_om_ca_file():
    """
    Canh chính bộ đọc trên: ôm quá tay thì mọi `assert ... in` đều đúng, và
    test kia xanh vĩnh viễn dù nhánh đã mất lời gọi.
    """
    than = _nhanh_view("cauhinh")
    assert than.startswith("{") and than.endswith("}")
    assert len(than) < 600, "đọc lố sang phần khác của vòng làm mới"
    assert "loadCongViec()" not in than, "ôm nhầm cả nhánh của màn khác"


def test_khong_tu_kiem_khi_mo_trang():
    """Mỗi lần kiểm là một lượt gọi tốn tiền; chỉ chạy khi người bấm."""
    than = _than_ham("loadCaiDatApi")
    assert "kiem-tra" not in than


def test_chi_hien_o_khoa_cua_provider_dang_chon():
    """
    Hiện cả hai ô khoá là mời người ta dán khoá Anthropic trong khi provider
    là gemini_api: khoá lưu đúng, Kiểm tra báo đúng, agent vẫn câm — không
    có gì nổ và người dùng không biết nhìn đâu.
    """
    than = _than_ham("hienODungProvider")
    # Ẩn bằng thuộc tính `hidden` trên chính dòng, không xoá khỏi DOM: dựng
    # lại DOM mỗi lần đổi ô chọn là mất thứ người ta đang gõ dở.
    assert "data-api-row" in than and ".hidden" in than
    assert re.search(r"API_KHOA_THEO_PROVIDER\s*=\s*\{[^}]*gemini_api:\s*\"GEMINI_API_KEY\"", JS)
    assert re.search(r"API_KHOA_THEO_PROVIDER\s*=\s*\{[^}]*anthropic:\s*\"ANTHROPIC_API_KEY\"", JS)
    # gemini/vertex xác thực qua gcloud: không ô nào được hiện.
    assert not re.search(r"API_KHOA_THEO_PROVIDER\s*=\s*\{[^}]*\bvertex:", JS)
    # Áp dụng cả lúc dựng lần đầu, không chỉ khi người đổi ô chọn.
    assert "hienODungProvider()" in _than_ham("loadCaiDatApi")
    assert re.search(r'addEventListener\("change"[\s\S]{0,200}hienODungProvider\(\)', JS)
    # Dòng phải MANG khoá để mà ẩn được.
    assert 'data-api-row="${esc(m.khoa)}"' in _than_ham("loadCaiDatApi")


def test_moi_chuoi_tu_may_chu_deu_qua_esc():
    """kiem_ket_qua là chữ do nhà cung cấp trả về — không esc là XSS từ chính lỗi của họ."""
    src = _than_ham("oNhapApi") + _than_ham("trangThaiApi") + _than_ham("loadCaiDatApi")
    for ten in ["m.nhan", "m.y_nghia", "m.hien", "m.kiem_ket_qua"]:
        # Mọi lần chèn phải đi qua esc(...) — chuỗi "${<tên>" trần (không có
        # "esc(" đứng trước) nghĩa là có chỗ lọt HTML thô từ máy chủ ra DOM.
        assert ("${" + ten) not in src, f"{ten} bị chèn thẳng, không qua esc()"
        assert ("esc(" + ten) in src, f"{ten} chưa từng được esc() ở đâu cả"
    assert "${esc(c)}" in src
    assert "${c}" not in src


def test_o_da_an_khong_duoc_gui_va_bi_xoa_gia_tri():
    """Đổi provider sau khi gõ khoá: ô ẩn phải bị bỏ qua lúc gom và xoá giá trị lúc ẩn."""
    gom = _than_ham("giaTriApiDangGo")
    assert "data-api-row" in gom and "hidden" in gom, \
        "giaTriApiDangGo phải kiểm closest('[data-api-row]')?.hidden"
    an = _than_ham("hienODungProvider")
    assert 'input[type="password"]' in an and ".value" in an, \
        "hienODungProvider phải xoá giá trị password khi ẩn dòng"
