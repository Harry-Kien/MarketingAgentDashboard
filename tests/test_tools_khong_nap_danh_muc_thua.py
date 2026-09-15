"""
Công cụ không cần danh mục thì KHÔNG được nạp danh mục.

ĐO ĐƯỢC (15.09.2026, máy có ERPNext đang chạy, `ERP_LOAI=erpnext`)
------------------------------------------------------------------
`_run_tool_that` nạp danh mục ở một dòng nằm TRÊN mọi nhánh phân phối, nên
mọi công cụ đều trả giá — kể cả `xin_doi_tra`, thứ chỉ chạy một câu UPDATE.
Vết gọi thật:

    run_tool -> _run_tool_that (tools.py:849) -> _catalog_song
             -> nha_may.cong().danh_muc()   <- ra mạng, ~1.0 giây

Một giây ấy nằm NGAY TRÊN đường trả lời khách, và tiêu một lượt trong hạn
mức lẫn bộ ngắt mạch của cổng ERP — để lấy một danh sách sản phẩm mà nhánh
được gọi không bao giờ đọc tới.

Nó còn làm bộ kiểm thử xanh-đỏ thất thường: `tests/test_xin_doi_tra.py`
khẳng định sự kiện đầu tiên là `order.xin_doi_tra`, nhưng lượt gọi ERP chèn
`erp.thieu_ho_so` lên trước — nên test đỏ trên máy có ERP sống và xanh trên
máy không có. Đỏ theo môi trường là thứ người ta học cách bỏ qua.

KÊ THEO CHIỀU PHỦ ĐỊNH CÓ CHỦ Ý
-------------------------------
Danh sách là các công cụ KHÔNG cần danh mục, không phải các công cụ cần.
Quên thêm vào danh sách phủ định thì mất một chút tốc độ; quên thêm vào
danh sách khẳng định thì công cụ nhìn thấy danh mục RỖNG và bảo khách là
shop không có sản phẩm nào — sai mà không nổ.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core import tools  # noqa: E402


@pytest.fixture
def dem_nap(monkeypatch):
    """Đếm số lần danh mục bị nạp; chặn mọi lượt ra mạng."""
    dem = {"n": 0}

    async def _catalog_song_gia():
        dem["n"] += 1
        return {"san_pham": [{"ma": "SP1", "ten": "Kem chống nắng",
                              "gia": 100000, "ton_kho": 5}]}

    async def _fetchrow(_sql, *args):
        return {"ma_don": args[0] if args else "DH-1"}

    async def _log(_kind, **_ct):
        return None

    monkeypatch.setattr(tools, "_catalog_song", _catalog_song_gia)
    monkeypatch.setattr(tools.db, "fetchrow", _fetchrow)
    monkeypatch.setattr(tools.db, "log_event", _log)
    return dem


@pytest.mark.parametrize("ten,args", [
    ("xin_doi_tra", {"ma_don": "DH-1", "loai": "doi"}),
    ("xin_huy_don", {"ma_don": "DH-1"}),
    ("chuyen_nhan_vien", {"ly_do": "khách đòi gặp người"}),
])
def test_cong_cu_khong_can_danh_muc_thi_KHONG_nap(dem_nap, ten, args):
    asyncio.run(tools.run_tool(ten, args, "conv-1"))
    assert dem_nap["n"] == 0, f"{ten} nạp danh mục thừa — một vòng ERP vô ích"


@pytest.mark.parametrize("ten,args", [
    ("tra_cuu_san_pham", {"ten_san_pham": "kem chống nắng"}),
    ("goi_y_san_pham", {"loai_da": "da dầu"}),
])
def test_cong_cu_can_danh_muc_thi_VAN_nap(dem_nap, ten, args):
    """
    Vế còn lại, và nó quan trọng ngang vế trên: tối ưu tay mà cắt nhầm là
    công cụ tra cứu nhìn thấy danh mục rỗng rồi bảo khách shop không bán gì.
    """
    asyncio.run(tools.run_tool(ten, args, "conv-1"))
    assert dem_nap["n"] == 1, f"{ten} không còn nạp danh mục"


def test_cham_vao_danh_muc_chua_nap_thi_NO_TO():
    """
    Lưới cho cái giá phải trả của tối ưu này.

    Kê nhầm một công cụ CÓ dùng danh mục vào danh sách "không cần" là nó
    nhìn thấy danh sách rỗng rồi bảo khách shop không bán gì — sai mà không
    nổ, đúng kiểu hỏng tệ nhất của repo này.

    Nên chỗ của danh mục chưa nạp không phải `[]` mà là một vật NỔ KHI BỊ
    CHẠM. Sai thì lộ ra ngay ở lần chạy đầu tiên, không phải ở một khách
    thật ba tuần sau.
    """
    chua_nap = tools._DANH_MUC_CHUA_NAP
    for cham in (lambda: list(chua_nap), lambda: chua_nap[0],
                 lambda: len(chua_nap), lambda: [x for x in chua_nap]):
        with pytest.raises(RuntimeError):
            cham()


def test_danh_sach_phu_dinh_chi_chua_cong_cu_co_that():
    """Tên gõ sai nằm im trong danh sách thì nó không canh gì cả."""
    ten_that = {t["name"] for t in tools.TOOLS}
    la = tools._KHONG_CAN_DANH_MUC - ten_that
    assert not la, f"tên không có trong TOOLS: {sorted(la)}"
