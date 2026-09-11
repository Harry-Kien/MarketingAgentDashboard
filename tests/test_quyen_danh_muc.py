"""
Danh mục quyền, và chốt bắt route chưa khai quyền.

Chốt này là lý do khối A tồn tại: nó bắt endpoint ra đời mà không ai canh.
Đó là loại hỏng im lặng nguy hiểm nhất ở đây — không nổ, không ghi nhật ký,
và chỉ lộ ra vào đúng ngày có người dùng sai quyền.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.core import quyen  # noqa: E402


def test_ma_quyen_dung_dinh_dang():
    """`nhom.hanh_dong`, chữ thường, không dấu — để nhóm được trên dashboard."""
    for ma in quyen.QUYEN:
        assert ma == ma.lower(), ma
        assert ma.count(".") == 1, ma
        nhom, hanh_dong = ma.split(".")
        assert nhom and hanh_dong, ma
        assert ma.replace(".", "_").isidentifier(), ma


def test_moi_quyen_co_nhan_tieng_viet():
    """Nhãn hiện trên màn cấp quyền. Thiếu nhãn là một ô tick không ai hiểu."""
    for ma, nhan in quyen.QUYEN.items():
        assert nhan.strip(), ma
        assert nhan[0].isupper(), f"{ma}: nhãn nên bắt đầu bằng chữ hoa"


def test_duyet_route_phai_di_de_quy():
    """
    ĐÂY LÀ TEST QUAN TRỌNG NHẤT FILE NÀY.

    FastAPI bản đang dùng gói mỗi router đã `include_router` vào một
    `_IncludedRouter`; route thật nằm trong `.original_router`. Duyệt phẳng
    `app.routes` cho 7 route thay vì 166 — và chốt ở dưới sẽ báo "mọi route
    đã khai quyền" trong khi 159 route chưa khai.

    Xanh giả. Không ai đi kiểm lại một dấu xanh.
    """
    from agent.main import app

    assert len(list(quyen.moi_route(app.routes))) >= 160


def test_mien_tru_khong_tro_vao_route_da_chet():
    """
    Miễn trừ trỏ vào đường dẫn không còn tồn tại là rác vô hại HÔM NAY.
    Ngày mai có người thêm lại đúng đường dẫn ấy và nó ra đời không được
    canh — im lặng.
    """
    from agent.main import app

    that = {
        (pt, getattr(r, "path", ""))
        for r in quyen.moi_route(app.routes)
        for pt in (getattr(r, "methods", None) or set())
    }
    chet = {mt for mt in quyen.MIEN_TRU if mt not in that}
    assert not chet, f"Miễn trừ trỏ vào route đã chết: {sorted(chet)}"


def test_danh_sach_hoan_khong_giao_voi_mien_tru():
    """Một route hoặc được miễn trừ, hoặc đang chờ khai quyền — không cả hai."""
    assert not (quyen.DANH_SACH_HOAN & quyen.MIEN_TRU)


def test_danh_sach_hoan_khong_tro_vao_route_da_chet():
    """
    Cùng lý do với miễn trừ, và gắt hơn: một cặp hoãn trỏ vào route đã chết
    sẽ không bao giờ bị xoá khỏi danh sách, nên danh sách không bao giờ rỗng
    được — và Việc 10 sẽ bế tắc mà không hiểu vì sao.
    """
    from agent.main import app

    that = {
        (pt, getattr(r, "path", ""))
        for r in quyen.moi_route(app.routes)
        for pt in (getattr(r, "methods", None) or set())
    }
    chet = {mt for mt in quyen.DANH_SACH_HOAN if mt not in that}
    assert not chet, f"Danh sách hoãn trỏ vào route đã chết: {sorted(chet)}"


def test_moi_route_da_khai_quyen_hoac_duoc_hoan():
    """Chốt chính. Khi `DANH_SACH_HOAN` rỗng, đây là chốt thật sự."""
    from agent.main import app

    quyen.kiem_moi_route_co_quyen(app)
