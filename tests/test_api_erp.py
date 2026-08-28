"""Vỏ REST của cổng kho/ERP.

Hai điều test canh, ngoài chuyện đọc được dữ liệu:

1. **Chỉ ĐỌC.** Không có endpoint nào tạo đơn, trừ kho, hay sửa gì bên ERP.
   Cùng lý do đã ghi trong docstring của `agent/mcp_server.py`: thứ gọi vào
   đây không đi qua năm lớp lưới tuân thủ trong `agent/core/agent.py`.

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


def test_vo_rest_khong_co_duong_nao_ghi():
    # Client gọi vào đây là một hệ khác, không đi qua năm lớp lưới tuân thủ
    # trong agent/core/agent.py, không có trần chi phí, không có lưới chuyển
    # người. Cho nó quyền tạo đơn là giao chìa khoá cho một người lạ.
    phuong_thuc = {
        m for r in router.routes for m in getattr(r, "methods", set())
    }
    assert phuong_thuc <= {"GET", "HEAD", "OPTIONS"}, (
        f"Vỏ REST của ERP chỉ được ĐỌC, thấy: {sorted(phuong_thuc)}"
    )
