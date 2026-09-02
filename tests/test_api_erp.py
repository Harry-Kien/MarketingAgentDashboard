"""Vỏ REST của cổng kho/ERP.

Hai điều test canh, ngoài chuyện đọc được dữ liệu:

1. **Chỉ ĐỌC.** Không có endpoint nào tạo đơn, trừ kho, hay sửa gì bên ERP.
   Cùng lý do đã ghi trong docstring của `agent/mcp_server.py`: thứ gọi vào
   đây không đi qua sáu lớp lưới tuân thủ trong `agent/core/agent.py`.

2. **Không biết thì trả 503, không trả số cũ.** Đây là quy tắc trung tâm của
   cổng, và nó phải sống sót qua tầng HTTP chứ không dừng ở tầng Python.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.erp import router
from agent.api.routes import bat_buoc_dang_nhap
from agent.erp import nha_may
from agent.erp.cong import Cong
from agent.erp.hop_dong import Gia, SanPhamERP, TonKho
from tests.erp_gia import NguonGia


def _nguon(hong: bool = False) -> NguonGia:
    return NguonGia(
        san_pham=[SanPhamERP(ma="AS-CL01", ten="Sữa rửa mặt", loai="Làm sạch")],
        gia={"AS-CL01": Gia(gia_ban=245000, nguon="Bảng giá bán lẻ")},
        ton={"AS-CL01": TonKho(ban_duoc=7, ma_kho="KHO-HN")},
        hong=hong,
    )


def _client(nguon: NguonGia, tmp_path) -> TestClient:
    ho_so = tmp_path / "catalog.json"
    ho_so.write_text(
        '{"san_pham": [{"ma": "AS-CL01", "da_phu_hop": ["da dầu"]}]}',
        encoding="utf-8",
    )
    cong = Cong(nguon, duong_dan_tu_van=ho_so)
    nha_may.dat_lai()
    nha_may._cong = cong

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[bat_buoc_dang_nhap] = lambda: {
        "ten_dang_nhap": "thu", "vai_tro": "nhan_vien"
    }
    return TestClient(app)


def test_danh_sach_san_pham(tmp_path):
    r = _client(_nguon(), tmp_path).get("/api/erp/san-pham")
    assert r.status_code == 200
    ds = r.json()["san_pham"]
    assert len(ds) == 1
    assert ds[0]["ma"] == "AS-CL01"
    assert ds[0]["gia"] == 245000
    assert ds[0]["ton_kho"] == 7
    nha_may.dat_lai()


def test_mot_san_pham(tmp_path):
    r = _client(_nguon(), tmp_path).get("/api/erp/san-pham/AS-CL01")
    assert r.status_code == 200
    assert r.json()["ten"] == "Sữa rửa mặt"
    assert r.json()["da_phu_hop"] == ["da dầu"]
    nha_may.dat_lai()


def test_ma_khong_co_thi_404(tmp_path):
    r = _client(_nguon(), tmp_path).get("/api/erp/san-pham/KHONG-CO")
    assert r.status_code == 404
    nha_may.dat_lai()


def test_ton_kho_tra_hang_ban_duoc(tmp_path):
    r = _client(_nguon(), tmp_path).get("/api/erp/ton-kho/AS-CL01")
    assert r.status_code == 200
    assert r.json()["ban_duoc"] == 7
    assert r.json()["ma_kho"] == "KHO-HN"
    nha_may.dat_lai()


def test_ton_kho_khong_tra_duoc_thi_503_khong_phai_200_voi_so_cu(tmp_path):
    # QUY TẮC TRUNG TÂM, kiểm ở tầng HTTP.
    # Trả 200 kèm số cũ là để client tin tưởng một con số đã chết. 503 nói
    # đúng sự thật: dịch vụ chưa trả lời được, đừng dùng số nào cả.
    r = _client(_nguon(hong=True), tmp_path).get("/api/erp/ton-kho/AS-CL01")
    assert r.status_code == 503
    nha_may.dat_lai()


def test_suc_khoe_noi_ro_nguon_va_trang_thai_mach(tmp_path):
    r = _client(_nguon(), tmp_path).get("/api/erp/suc-khoe")
    assert r.status_code == 200
    d = r.json()
    assert d["nguon"] == "gia"
    assert d["mach_mo"] is False
    assert d["song"] is True
    nha_may.dat_lai()


def test_suc_khoe_bao_chet_khi_erp_hong(tmp_path):
    r = _client(_nguon(hong=True), tmp_path).get("/api/erp/suc-khoe")
    # Sức khoẻ luôn trả 200 — nó là bộ đo, không phải bộ phục vụ dữ liệu.
    # Trả 503 ở đây thì bộ giám sát ngoài không phân biệt được "ERP chết"
    # với "chính API này chết".
    assert r.status_code == 200
    assert r.json()["song"] is False
    nha_may.dat_lai()


def test_phai_dang_nhap(tmp_path):
    ho_so = tmp_path / "catalog.json"
    ho_so.write_text('{"san_pham": []}', encoding="utf-8")
    nha_may.dat_lai()
    nha_may._cong = Cong(_nguon(), duong_dan_tu_van=ho_so)
    app = FastAPI()
    app.include_router(router)
    # KHÔNG ghi đè dependency: request không có cookie phiên phải bị chặn.
    r = TestClient(app).get("/api/erp/san-pham")
    assert r.status_code == 401
    nha_may.dat_lai()


def test_vo_rest_khong_co_duong_nao_ghi_vao_erp():
    """Không endpoint nào tạo đơn, trừ kho, hay sửa gì bên ERP.

    Client gọi vào đây là một hệ khác: không đi qua sáu lớp lưới tuân thủ
    trong `agent/core/agent.py`, không có trần chi phí, không có lưới chuyển
    người. Cho nó quyền tạo đơn là giao chìa khoá cho một người lạ.

    VÌ SAO KHÔNG CÒN LÀ "CHỈ GET"
    -----------------------------
    Bản đầu của test này khẳng định router chỉ có GET/HEAD/OPTIONS. Đúng
    tinh thần nhưng sai phép đo: `/kiem-ket-noi` là POST mà vẫn chỉ đọc —
    nó là POST để trình duyệt và bộ nhớ đệm không tự kích hoạt sáu lượt gọi
    ERP.

    Nên phép kiểm đúng là NGƯỠNG GHI VÀO ERP, không phải động từ HTTP. Mọi
    POST phải nằm trong danh sách trắng, và mã nguồn không được chứa lời gọi
    ghi nào.
    """
    from pathlib import Path

    POST_DUOC_PHEP = {"/api/erp/kiem-ket-noi"}
    la = {
        r.path for r in router.routes
        if getattr(r, "methods", set()) - {"GET", "HEAD", "OPTIONS"}
    } - POST_DUOC_PHEP
    assert not la, f"Endpoint ghi không nằm trong danh sách trắng: {sorted(la)}"

    ma = (Path(__file__).resolve().parent.parent / "agent" / "api" / "erp.py"
          ).read_text(encoding="utf-8")
    for cam in ("tao_don", "bao_dam_khach", "day_don"):
        assert cam not in ma, f"vỏ REST không được ghi vào ERP, thấy: {cam}"


# =====================================================================
#  Kiểm kết nối từ dashboard
# =====================================================================

def test_kiem_ket_noi_tra_bao_cao(tmp_path):
    r = _client(_nguon(), tmp_path).post("/api/erp/kiem-ket-noi")
    assert r.status_code == 200
    d = r.json()
    assert "muc" in d and "san_sang" in d and "trang_thai" in d
    nha_may.dat_lai()


def test_kiem_ket_noi_khong_bao_gio_500(tmp_path):
    # Người vận hành phải nhận BÁO CÁO nói mình thiếu gì, không phải một
    # trang lỗi 500 không nói gì cả.
    r = _client(_nguon(hong=True), tmp_path).post("/api/erp/kiem-ket-noi")
    assert r.status_code == 200
    assert r.json()["san_sang"] is False
    nha_may.dat_lai()


def test_kiem_ket_noi_phai_dang_nhap(tmp_path):
    ho_so = tmp_path / "catalog.json"
    ho_so.write_text('{"san_pham": []}', encoding="utf-8")
    nha_may.dat_lai()
    nha_may._cong = Cong(_nguon(), duong_dan_tu_van=ho_so)
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app).post("/api/erp/kiem-ket-noi").status_code == 401
    nha_may.dat_lai()


def test_kiem_ket_noi_khong_lo_bi_mat(tmp_path, monkeypatch):
    from agent.config import settings

    monkeypatch.setattr(settings, "erpnext_api_key", "khoa-bi-mat-xyz")
    monkeypatch.setattr(settings, "erpnext_api_secret", "secret-bi-mat-xyz")
    r = _client(_nguon(), tmp_path).post("/api/erp/kiem-ket-noi")
    assert "khoa-bi-mat-xyz" not in r.text
    assert "secret-bi-mat-xyz" not in r.text
    nha_may.dat_lai()


def test_kiem_ket_noi_la_POST_chu_khong_phai_GET(tmp_path):
    # Nó GỌI THẬT ra ERP. Để là GET thì trình duyệt, trình quét link và bộ
    # nhớ đệm đều có thể tự kích hoạt — đốt hạn mức gọi ERP của cửa hàng.
    c = _client(_nguon(), tmp_path)
    assert c.get("/api/erp/kiem-ket-noi").status_code == 405
    nha_may.dat_lai()


def test_dashboard_co_panel_ket_noi_erp():
    """Màn Kho phải có panel kết nối ERP, và app.js phải nối vào nó.

    Endpoint không có ai gọi thì cũng như không có. Đã xảy ra một lần: cổng
    ERP ghi log_event đầy đủ mà không màn hình nào đọc bảng `events`.
    """
    from pathlib import Path

    goc = Path(__file__).resolve().parent.parent
    html = (goc / "dashboard" / "index.html").read_text(encoding="utf-8")
    js = (goc / "dashboard" / "app.js").read_text(encoding="utf-8")

    for pt in ("erpthu", "erpcauhinh", "erpketqua"):
        assert f'id="{pt}"' in html, f"index.html thiếu #{pt}"
        assert f"#{pt}" in js, f"app.js không dùng #{pt}"

    assert "/erp/kiem-ket-noi" in js, "app.js chưa gọi endpoint kiểm kết nối"
    assert '"POST"' in js or "'POST'" in js, (
        "phải gọi bằng POST — GET thì trình duyệt và bộ nhớ đệm tự kích "
        "hoạt sáu lượt gọi ERP"
    )
