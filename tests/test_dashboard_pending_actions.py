"""DEV-10: Dashboard phải dùng luồng xác nhận Pending Action có đối soát."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "dashboard" / "src" / "08-tai-khoan.js").read_text(
    encoding="utf-8"
)
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
API = (ROOT / "agent" / "api" / "cong_viec.py").read_text(encoding="utf-8")


def test_tc01_tc02_tc03_danh_sach_va_chi_tiet_co_du_truong_xu_ly_don():
    for field in (
        "loai_xu_ly_don",
        "ma_don",
        "ket_qua_xu_ly_don",
        "erp_trang_thai",
        "erp_sua_luc",
        "xu_ly_boi_ten",
    ):
        assert field in API
        assert field in SRC
    for element_id in (
        "congCvKetQua",
        "cvkChiTiet",
        "cvkKetQua",
        "cvkLyDo",
        "cvkBangChung",
        "cvkGui",
    ):
        assert f'id="{element_id}"' in HTML


def test_tc04_tc05_tc10_goi_dung_api_va_ve_lai_tu_ket_qua_backend():
    assert "/action-evidence?cong_viec_id=" in SRC
    assert "/confirm-action-result" in SRC
    assert "trang_thai_cong_viec" in SRC
    assert 'ket_qua === "cho_doi_soat"' in SRC
    assert "await loadCongViec()" in SRC


def test_tc06_hien_loi_theo_http_status():
    for status in (403, 404, 409, 422):
        assert f"{status}:" in SRC
    assert "err.ma" in SRC


def test_tc07_khoa_nut_va_co_chot_chong_gui_trung():
    assert "cvKetQuaDangGui" in SRC
    assert "if (cvKetQuaDangGui) return" in SRC
    assert "cvkGui.disabled = true" in SRC


def test_dong_modal_van_giu_ban_nhap_theo_tung_cong_viec():
    assert "banNhap: {}" in SRC
    assert "function cvLuuBanNhap" in SRC
    assert "congViec.banNhap[id]" in SRC


def test_tc08_chi_hien_xac_nhan_khi_co_du_hai_quyen():
    assert 'state.toiQuyen.has("don.sua")' in SRC
    assert 'state.toiQuyen.has("cong_viec.sua")' in SRC


def test_tc09_timeout_khong_tu_danh_dau_hoan_tat():
    assert "AbortController" in SRC
    assert "AbortError" in SRC
    assert "không đổi trạng thái công việc" in SRC


def test_tc11_khong_tu_dong_resolve():
    doan = SRC[SRC.index("async function cvGuiKetQua"):]
    doan = doan[: doan.index("/* GIAO VIỆC")]
    assert "/resolve" not in doan
    assert "/giai-quyet" not in doan


def test_tc12_sua_thanh_cong_chi_gui_modified_doc_tu_backend():
    assert 'd.ket_qua === "thanh_cong"' in SRC
    assert "cvKetQuaBangChung.modified" in SRC
    assert "erp_modified_at: bangChungSua" in SRC
    assert 'name="erp_modified_at"' not in HTML
    assert "chưa có phiên bản ERPNext đã xác minh" in SRC

