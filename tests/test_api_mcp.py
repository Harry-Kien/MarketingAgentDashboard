"""API máy chủ MCP — chỉ quản trị. Bí mật không bao giờ ra khỏi GET."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import nguoi_thu, toan_quyen

from agent.api import mcp_may_chu as api
from agent.api import routes
from agent.ky_nang import kho_mcp as km


def _app(quan_tri=True):
    app = FastAPI(); app.include_router(api.router)
    app.dependency_overrides[routes.nguoi_da_dang_nhap] = (
        (lambda: toan_quyen()) if quan_tri else (lambda: nguoi_thu()))
    return app


@pytest.fixture
def kho(monkeypatch):
    """
    CSDL giả bằng dict, y như `tests/test_api_goi_ky_nang.py`. `them()` gọi
    THẬT `km._kiem_ten` để bản gõ tên sai vẫn ra đúng `LoiMayChu` mà `_loi()`
    phải dịch — không giả lập luật đặt tên riêng ở đây, kẻo test xanh dù
    router quên bọc lỗi.
    """
    goi_kiem: list[tuple] = []
    may_chu: dict[str, dict] = {}

    async def kiem_ket_noi(dia_chi, headers=None):
        goi_kiem.append((dia_chi, headers))
        return {"ok": True, "so_cong_cu": 1,
                "cong_cu": [{"ten": "tra_ton", "mo_ta": "tra cứu tồn", "ghi_goi_y": False}],
                "loi": None}

    async def them(ten, nhan, dia_chi, headers, *, boi):
        ten = km._kiem_ten(ten)  # ném LoiMayChu nếu tên sai dạng — như hàm thật
        if ten in may_chu:
            raise km.KhoDay(f"Đã có máy chủ tên {ten!r}.")
        if len(may_chu) >= km.MCP_MAY_CHU_TOI_DA:
            raise km.KhoDay(f"Đã đủ {km.MCP_MAY_CHU_TOI_DA} máy chủ MCP.")
        may_chu[ten] = {"nhan": nhan, "dia_chi": dia_chi, "headers": headers, "bat": True}
        return {"ok": True, "so_cong_cu": 1, "so_bat": 1, "so_bo": 0, "bo": [], "loi": None}

    async def dong_bo(ten, *, boi):
        if ten not in may_chu:
            raise km.MayChuKhongTonTai(ten)
        return {"ok": True, "so_cong_cu": 1, "so_bat": 1, "so_bo": 0, "bo": [], "loi": None}

    async def bat_tat(ten, bat, *, boi):
        if ten not in may_chu:
            raise km.MayChuKhongTonTai(ten)
        may_chu[ten]["bat"] = bat

    async def dat_cong_cu(ten, ten_cong_cu, *, bat=None, ghi=None, ghi_cho_phep=None, boi):
        if ten not in may_chu:
            raise km.MayChuKhongTonTai(ten)
        return {"ten": ten_cong_cu, "bat": bool(bat), "ghi": bool(ghi),
                "ghi_cho_phep": bool(ghi_cho_phep)}

    async def xoa(ten, *, boi):
        if ten not in may_chu:
            raise km.MayChuKhongTonTai(ten)
        may_chu.pop(ten)
        return True

    async def liet_ke():
        # `co_bi_mat` là TẤT CẢ những gì GET được phép nói về bí mật — không
        # có khoá `headers` trong dòng này, y như hàm thật.
        return [{"ten": t, "nhan": v["nhan"], "host": "vidu.com", "bat": v["bat"],
                 "co_bi_mat": True, "suc_khoe": {}, "tao_boi": "qt",
                 "so_cong_cu": 0, "so_bat": 0, "cong_cu": []} for t, v in may_chu.items()]

    for ten, ham in [("kiem_ket_noi", kiem_ket_noi), ("them", them), ("dong_bo", dong_bo),
                      ("bat_tat", bat_tat), ("dat_cong_cu", dat_cong_cu), ("xoa", xoa),
                      ("liet_ke", liet_ke)]:
        monkeypatch.setattr(api.kho_mcp, ten, ham)
    return {"may_chu": may_chu, "goi_kiem": goi_kiem}


def _than() -> dict:
    return {"ten": "kho_trung_tam", "nhan": "Kho trung tâm", "dia_chi": "https://vidu.com/mcp",
            "headers": {"Authorization": "Bearer x"}}


def test_nhan_vien_403():
    assert TestClient(_app(False)).get("/api/mcp").status_code in (401, 403)


def test_kiem_khong_ghi(kho, monkeypatch):
    da_goi_them = []
    monkeypatch.setattr(api.kho_mcp, "them", lambda *a, **kw: da_goi_them.append(1))
    c = TestClient(_app())
    r = c.post("/api/mcp/kiem", json={"dia_chi": "https://vidu.com/mcp"})
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["so_cong_cu"] == 1
    assert len(kho["goi_kiem"]) == 1
    assert da_goi_them == []
    assert kho["may_chu"] == {}


def test_them_201(kho):
    c = TestClient(_app())
    r = c.post("/api/mcp", json=_than())
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["ten"] == "kho_trung_tam" and d["so_cong_cu"] == 1 and d["so_bat"] == 1
    assert d["so_bo"] == 0 and d["bo"] == []
    assert d["ok"] is True and d["loi"] is None
    assert "kho_trung_tam" in kho["may_chu"]


def test_them_dong_bo_hong_van_201_nhung_noi_that(kho, monkeypatch):
    """
    Máy chủ vẫn được TẠO khi lần đồng bộ đầu hỏng — cố ý, để một lần mạng
    chập không làm mất bản ghi và bí mật vừa mã hoá. Nhưng nếu response chỉ
    có `so_cong_cu: 0` thì dashboard không phân biệt được "máy chủ thật
    không có công cụ nào" với "sai địa chỉ / sai header / DNS hỏng", và nó
    báo "Đã nối" cho cả bốn ca.
    """
    async def them_hong(ten, nhan, dia_chi, headers, *, boi):
        return {"ok": False, "so_cong_cu": 0, "so_bat": 0, "so_bo": 0, "bo": [],
                "loi": "Không nối được máy chủ MCP: ConnectError"}
    monkeypatch.setattr(api.kho_mcp, "them", them_hong)

    r = TestClient(_app()).post("/api/mcp", json=_than())
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["ok"] is False
    assert "ConnectError" in d["loi"]


def test_ten_sai_422(kho):
    c = TestClient(_app())
    r = c.post("/api/mcp", json=_than() | {"ten": "Sai Tên"})
    assert r.status_code == 422


def test_kho_day_409(kho):
    c = TestClient(_app())
    assert c.post("/api/mcp", json=_than()).status_code == 201
    r = c.post("/api/mcp", json=_than())  # trùng tên
    assert r.status_code == 409


def test_may_chu_khong_ton_tai_404(kho):
    c = TestClient(_app())
    assert c.post("/api/mcp/khong-co/bat-tat", json={"bat": False}).status_code == 404
    assert c.post("/api/mcp/khong-co/dong-bo").status_code == 404
    assert c.delete("/api/mcp/khong-co").status_code == 404


def test_vault_chua_san_sang_503(kho, monkeypatch):
    from agent.cau_hinh_dong import VaultChuaSanSang

    async def them_hong(ten, nhan, dia_chi, headers, *, boi):
        raise VaultChuaSanSang("vault chưa cấu hình")
    monkeypatch.setattr(api.kho_mcp, "them", them_hong)
    c = TestClient(_app())
    assert c.post("/api/mcp", json=_than()).status_code == 503


def test_get_khong_lo_header(kho):
    c = TestClient(_app())
    c.post("/api/mcp", json=_than())
    r = c.get("/api/mcp")
    assert r.status_code == 200
    assert "header" not in r.text.lower()
    assert r.json()["may_chu"][0]["co_bi_mat"] is True
    assert r.json()["may_chu_toi_da"] == km.MCP_MAY_CHU_TOI_DA
    assert "plugin_toi_da" in r.json()


def test_cong_cu_kho_day_409(kho, monkeypatch):
    c = TestClient(_app())
    c.post("/api/mcp", json=_than())

    async def day(ten, ten_cong_cu, *, bat=None, ghi=None, ghi_cho_phep=None, boi):
        raise km.KhoDay("đủ 12 công cụ đang bật")
    monkeypatch.setattr(api.kho_mcp, "dat_cong_cu", day)
    r = c.post("/api/mcp/kho_trung_tam/cong-cu/tra_ton", json={"bat": True})
    assert r.status_code == 409


def test_dong_bo_va_bat_tat_204(kho):
    c = TestClient(_app())
    c.post("/api/mcp", json=_than())
    assert c.post("/api/mcp/kho_trung_tam/dong-bo").status_code == 200
    assert c.post("/api/mcp/kho_trung_tam/bat-tat", json={"bat": False}).status_code == 204
    assert kho["may_chu"]["kho_trung_tam"]["bat"] is False
    assert c.post("/api/mcp/kho_trung_tam/cong-cu/tra_ton", json={"bat": True}).status_code == 204
    assert c.delete("/api/mcp/kho_trung_tam").status_code == 204
    assert "kho_trung_tam" not in kho["may_chu"]


def test_router_gan_vao_app():
    from fastapi.openapi.utils import get_openapi
    from agent import main
    assert "/api/mcp" in get_openapi(title="x", version="1", routes=main.app.routes)["paths"]
