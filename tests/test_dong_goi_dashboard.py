"""
`dashboard/app.js` là tệp SINH RA từ `dashboard/src/*.js` — xem
`scripts/dong_goi_dashboard.py` cho lý do nối tệp thay vì ES module.

Canh hai chiều hỏng im lặng:
  · sửa `src/` mà quên đóng gói -> trình duyệt chạy mã CŨ, sửa như không;
  · sửa thẳng `app.js` -> lần đóng gói sau xoá mất, không ai báo.
"""
from __future__ import annotations

from pathlib import Path

from scripts import dong_goi_dashboard as dg

ROOT = Path(__file__).resolve().parent.parent


def test_app_js_khop_voi_src():
    assert (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8") == dg.dong_goi(), (
        "dashboard/app.js lệch với dashboard/src/ — sửa ở src/ rồi chạy "
        "python -m scripts.dong_goi_dashboard (đừng sửa thẳng app.js)")


def test_app_js_mang_dong_canh_bao_sinh_ra():
    dau = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")[:200]
    assert "ĐỪNG SỬA TAY" in dau and "dashboard/src" in dau


def test_tep_nguon_du_nho_de_doc():
    """Mục đích của việc tách: không tệp nào quay lại thành một khối nghìn dòng."""
    tep = dg.cac_tep()
    assert len(tep) >= 10
    dai = {p.name: len(p.read_text(encoding="utf-8").splitlines()) for p in tep}
    qua = {k: v for k, v in dai.items() if v > 1000}
    assert not qua, f"tệp nguồn quá 1000 dòng, tách tiếp: {qua}"


def test_che_do_kiem_bao_do_khi_lech(tmp_path, monkeypatch):
    """Canh chính bộ canh: `--kiem` phải trả 1 khi app.js cũ."""
    gia = tmp_path / "app.js"
    gia.write_text("// cũ\n", encoding="utf-8")
    monkeypatch.setattr(dg, "DICH", gia)
    assert dg.main(["--kiem"]) == 1
    gia.write_text(dg.dong_goi(), encoding="utf-8")
    assert dg.main(["--kiem"]) == 0
