"""
`can_quyen()` — dependency khai quyền ngay cạnh endpoint.

Không dùng `pytest-asyncio` (repo không cài): dựng app FastAPI nhỏ và gọi
qua `TestClient`, đúng khuôn các test API khác.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.api import routes  # noqa: E402
from agent.core import xac_thuc  # noqa: E402


def _app_thu(*quyen: str) -> FastAPI:
    app = FastAPI()

    @app.get("/thu")
    async def thu(nguoi: dict = Depends(routes.can_quyen(*quyen))):
        return {"ai": nguoi["ten_dang_nhap"]}

    return app


@pytest.fixture
def gia_phien(monkeypatch):
    """Thay `doc_phien` bằng một người có tập quyền cho trước."""
    def dat(*quyen: str):
        async def gia(token: str):
            if not token:
                return None
            return {"id": "u1", "ten_dang_nhap": "kt", "ho_ten": "Kiểm thử",
                    "vai_tro": "nhan_vien", "khoa": False,
                    "quyen": frozenset(quyen)}
        monkeypatch.setattr(xac_thuc, "doc_phien", gia)
    return dat


def test_nem_ngay_luc_goi_neu_quyen_khong_co_trong_danh_muc():
    """
    Kiểm ở THÂN factory, không trong hàm con.

    Thân factory chạy lúc import module, nên gõ sai tên quyền làm máy chủ
    KHÔNG KHỞI ĐỘNG ĐƯỢC — thay vì một 403 bí ẩn vào lúc có người thật sự
    cần dùng endpoint ấy.
    """
    with pytest.raises(KeyError):
        routes.can_quyen("khong.ton_tai")


def test_dependency_mang_nhan_quyen_yeu_cau():
    """Chốt lúc khởi động nhận ra endpoint đã khai quyền nhờ nhãn này."""
    d = routes.can_quyen("khach.doc", "khach.sua")
    assert d.quyen_yeu_cau == ("khach.doc", "khach.sua")


def test_co_du_quyen_thi_qua(gia_phien):
    gia_phien("khach.doc")
    khach = TestClient(_app_thu("khach.doc"))
    khach.cookies.set(routes.TEN_COOKIE, "token-gia")
    r = khach.get("/thu")
    assert r.status_code == 200
    assert r.json() == {"ai": "kt"}


def test_thieu_quyen_thi_403_va_noi_ro_thieu_gi(gia_phien):
    """
    Thông báo phải NÓI TÊN quyền còn thiếu.

    "Không có quyền" chung chung buộc quản trị đoán, và họ sẽ đoán bằng cách
    cấp cả cụm quyền cho chắc — tức là nới quyền chỉ vì thông báo lỗi kém.
    """
    gia_phien("khach.doc")
    khach = TestClient(_app_thu("khach.xoa"))
    khach.cookies.set(routes.TEN_COOKIE, "token-gia")
    r = khach.get("/thu")
    assert r.status_code == 403
    assert "khach.xoa" in r.json()["detail"]


def test_nhieu_quyen_la_phai_co_du_khong_phai_mot_trong_so(gia_phien):
    """
    `can_quyen("a", "b")` đòi CẢ HAI.

    Hiểu nhầm thành "một trong hai" là nới quyền ở mọi chỗ dùng nhiều quyền
    — và nới thì không ai phát hiện, vì không có gì hỏng.
    """
    gia_phien("khach.doc")
    khach = TestClient(_app_thu("khach.doc", "khach.sua"))
    khach.cookies.set(routes.TEN_COOKIE, "token-gia")
    assert khach.get("/thu").status_code == 403

    gia_phien("khach.doc", "khach.sua")
    khach2 = TestClient(_app_thu("khach.doc", "khach.sua"))
    khach2.cookies.set(routes.TEN_COOKIE, "token-gia")
    assert khach2.get("/thu").status_code == 200


def test_chua_dang_nhap_thi_401_chu_khong_403(gia_phien):
    """
    401 và 403 nói hai chuyện khác nhau: "anh là ai" và "anh không được
    phép". Trả 403 cho người chưa đăng nhập là đẩy họ đi xin quyền thay vì
    đi đăng nhập.
    """
    gia_phien("khach.doc")
    khach = TestClient(_app_thu("khach.doc"))     # không đặt cookie
    assert khach.get("/thu").status_code == 401


def test_dung_lai_nguoi_middleware_da_doc(gia_phien, monkeypatch):
    """
    Middleware ở `main.py` đã đọc phiên và gắn vào `request.state.nguoi`.
    Đọc lại là gọi CSDL hai lần cho mỗi request — và truy vấn phiên giờ có
    thêm ba LEFT JOIN, nên nó không còn rẻ như trước.
    """
    dem = {"n": 0}

    async def dem_phien(token: str):
        dem["n"] += 1
        return {"id": "u1", "ten_dang_nhap": "kt", "khoa": False,
                "quyen": frozenset({"khach.doc"})}

    monkeypatch.setattr(xac_thuc, "doc_phien", dem_phien)

    app = _app_thu("khach.doc")

    @app.middleware("http")
    async def gan_nguoi(request, call_next):
        request.state.nguoi = await xac_thuc.doc_phien("token-gia")
        return await call_next(request)

    khach = TestClient(app)
    khach.cookies.set(routes.TEN_COOKIE, "token-gia")
    assert khach.get("/thu").status_code == 200
    assert dem["n"] == 1, "đọc phiên hai lần trong cùng một request"
