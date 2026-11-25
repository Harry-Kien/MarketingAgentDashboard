"""Regression BUG-19-01: thuộc tính hidden phải thắng display component."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "dashboard/app.css").read_text(encoding="utf-8")
JS = (ROOT / "dashboard/src/19-thong-bao.js").read_text(encoding="utf-8")


def test_hidden_la_quy_tac_nen_toan_dashboard():
    compact = " ".join(CSS.split())
    assert "[hidden] { display: none !important; }" in compact


def test_hidden_thang_btn_inline_flex():
    compact = " ".join(CSS.split())
    assert compact.index("[hidden] { display: none !important; }") < compact.index(
        ".btn { display: inline-flex;"
    )


def test_nut_xem_them_doc_con_nua_tu_backend():
    assert 'chuong.conNua = d.con_nua;' in JS
    assert '$("#chuongThem").hidden = !chuong.conNua;' in JS


def test_danh_sach_rong_khong_tu_bat_nut_xem_them():
    """Danh sách rỗng chỉ vẽ empty-state; quyền hiện nút vẫn do con_nua."""
    assert "chuong.ds.length" in JS
    assert "chuong.conNua" in JS
    assert "chuong.ds.length ||" not in JS


def test_cac_component_hidden_khac_van_duoc_bao_ve():
    """Lưới hồi quy cho form, tab, rail và popup ngoài nút thông báo."""
    html = (ROOT / "dashboard/index.html").read_text(encoding="utf-8")
    for marker in (
        'id="loginMa" hidden',
        'id="railCaiDatCon" hidden',
        'class="tabpanel" id="cv-ca-truc" data-gan="cv-ca-truc" role="tabpanel" hidden',
        'id="chuongKhung" role="dialog" aria-label="Thông báo" hidden',
    ):
        assert marker in html
