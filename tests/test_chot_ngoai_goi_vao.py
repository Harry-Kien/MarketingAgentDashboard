"""
Canh những đường mà HỆ THỐNG NGOÀI gọi vào: OAuth callback, callback n8n.

VÌ SAO NHÓM TEST NÀY TỒN TẠI
-----------------------------
Có HAI chốt độc lập trên cùng một đường `/api`:

    agent/main.py::_MO          chốt ĐĂNG NHẬP (middleware)
    agent/core/quyen.py::MIEN_TRU chốt PHÂN QUYỀN (kiểm lúc khởi động)

Khai miễn trừ ở một chốt mà quên chốt kia thì đường vẫn chết, và chết ở
401 — trông hệt như "bên ngoài gọi sai".

Việc này ĐÃ XẢY RA: `/api/connect/zalo-oa/callback` được khai vào
`MIEN_TRU` mà quên `_MO`, nên luồng nối Zalo OA không bao giờ chạy được.
Test của khối ấy vẫn xanh vì nó dựng một `FastAPI()` trần chỉ gắn router —
không có middleware, nên không có chốt nào để mà vướng.

Nên mọi test ở đây chạy trên `agent.main.app` THẬT. Đó là điểm chính.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.core.quyen import MIEN_TRU  # noqa: E402
from agent.main import _MO, app  # noqa: E402


@pytest.fixture(scope="module")
def khach():
    # `raise_server_exceptions=False`: vài endpoint ở đây sẽ chạm CSDL và
    # ném. Ta chỉ quan tâm nó có bị 401 CHẶN TRƯỚC hay không.
    return TestClient(app, raise_server_exceptions=False)


# Đường + cách gọi của từng hệ thống ngoài. Thêm một luồng OAuth mới thì
# thêm một dòng ở đây — và nếu quên khai miễn trừ, dòng ấy đỏ ngay.
NGOAI_GOI = [
    ("GET", "/api/connect/meta/callback", {"error": "x"}),
    ("GET", "/api/connect/zalo-oa/callback", {"error": "x"}),
]


@pytest.mark.parametrize("pt,duong,tham_so", NGOAI_GOI)
def test_he_thong_ngoai_khong_bi_chot_dang_nhap_chan(khach, pt, duong, tham_so):
    """
    401 ở đây nghĩa là luồng CHẾT HOÀN TOÀN: bên ngoài không có cookie
    phiên và không bao giờ có được.
    """
    tra = khach.request(pt, duong, params=tham_so)
    assert tra.status_code != 401, (
        f"{pt} {duong} bị chốt đăng nhập chặn — thêm nó vào `_MO` "
        "trong agent/main.py")


def test_callback_n8n_khong_bi_chot_dang_nhap_chan(khach):
    """
    Đường này có tham số trong path nên `_MO` (so bằng ==) không phủ được;
    nó đi qua `_MO_MAU`. Sai regex là im lặng quay về 401.
    """
    tra = khach.post(
        "/api/posts/11111111-2222-3333-4444-555555555555/callback",
        json={"kenh": "facebook", "ok": True})
    assert tra.status_code != 401 or "Vé" in tra.text, (
        "callback n8n bị chốt đăng nhập chặn — kiểm `_MO_MAU`")


def test_ve_thieu_tra_401_va_KHONG_cham_csdl(khach):
    """
    Không vé thì từ chối ngay, không hỏi CSDL.

    Hai lý do. 404 nói cho người dò biết bài nào có thật, nên phải là 401.
    Và đường này mở cho cả internet: mỗi lần gọi không vé mà vẫn truy vấn
    là biến nó thành một cần gạt đơn giản để làm mệt CSDL.

    Test này chạy KHÔNG có pool — chạm CSDL là 500, nên 401 ở đây chính là
    bằng chứng nó không chạm.
    """
    tra = khach.post(
        "/api/posts/11111111-2222-3333-4444-555555555555/callback",
        json={"kenh": "facebook", "ok": True})
    assert tra.status_code == 401

    tra = khach.post(
        "/api/posts/11111111-2222-3333-4444-555555555555/callback",
        json={"kenh": "facebook", "ok": True}, params={"token": ""})
    assert tra.status_code == 401


# ---------------- bất biến giữa hai chốt ----------------

def test_mo_dang_nhap_thi_phai_mo_ca_phan_quyen():
    """
    BẤT BIẾN: `_MO` ⊆ `MIEN_TRU`.

    Đường được miễn đăng nhập nghĩa là không có người dùng nào gắn vào
    request. `can_quyen(...)` khi ấy không có gì để kiểm và sẽ từ chối —
    401 đổi thành 403, vẫn là chết.
    """
    duong_mien_tru = {d for _, d in MIEN_TRU}
    thieu = sorted(set(_MO) - duong_mien_tru)
    assert not thieu, (
        "Những đường này miễn đăng nhập nhưng chưa miễn phân quyền, nên "
        f"chúng trả 403 thay vì chạy: {thieu}")


def test_mau_mo_cung_phai_co_trong_mien_tru():
    """Cùng bất biến trên, cho các đường khai bằng regex."""
    duong_mien_tru = {d for _, d in MIEN_TRU}
    assert "/api/posts/{post_id}/callback" in duong_mien_tru


def test_start_cua_moi_luong_oauth_van_doi_dang_nhap(khach):
    """
    Chỉ CALLBACK được mở. Mở luôn `/start` là cho bất kỳ ai ngoài internet
    sinh `state` hợp lệ, và chốt của callback rỗng ruột.
    """
    for duong in ("/api/connect/meta/start", "/api/connect/zalo-oa/start"):
        assert khach.get(duong).status_code == 401, f"{duong} đang mở toang"


# KHÔNG đếm lại số đường trong `_MO` ở đây.
#
# `tests/test_xac_thuc.py` đã canh việc ấy, và canh KỸ HƠN: nó bắt mỗi
# đường mở phải có tên trong một bảng kèm LÝ DO và kèm chốt thay thế. Chép
# lại một phép đếm yếu hơn bên cạnh một phép kiểm mạnh hơn chỉ tạo ra hai
# chỗ phải sửa khi thêm đường, và người sửa sẽ sửa chỗ dễ.
