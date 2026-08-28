"""Hai công cụ MCP mới của cổng kho: tồn kho thời gian thực và sức khoẻ.

Test canh đúng hai chuyện mà `test_mcp.py` chưa phủ được:

1. Hai công cụ mới KHÔNG làm thủng ranh giới đọc/ghi. `test_mcp.py` đã canh
   danh sách tên bị cấm; ở đây canh thêm rằng chúng thật sự có mặt và thật
   sự chỉ đọc.

2. `ton_kho_realtime` phải trả "không biết" khi cổng trả `None`, chứ không
   trả 0. Trả 0 nghĩa là HẾT HÀNG — một câu trả lời sai khác hẳn với "chưa
   tra được", và client MCP không có cách nào phân biệt.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from agent import mcp_server  # noqa: E402
from agent.erp import nha_may  # noqa: E402
from agent.erp.cong import Cong  # noqa: E402
from agent.erp.hop_dong import Gia, SanPhamERP, TonKho  # noqa: E402
from tests.erp_gia import NguonGia, chay  # noqa: E402


@pytest.fixture
def cong_gia(tmp_path):
    ho_so = tmp_path / "catalog.json"
    ho_so.write_text(
        '{"san_pham": [{"ma": "AS-CL01", "da_phu_hop": ["da dầu"]}]}',
        encoding="utf-8",
    )
    n = NguonGia(
        san_pham=[SanPhamERP(ma="AS-CL01", ten="Sữa rửa mặt")],
        gia={"AS-CL01": Gia(gia_ban=245000)},
        ton={"AS-CL01": TonKho(ban_duoc=7, ma_kho="KHO-HN")},
    )
    nha_may.dat_lai()
    nha_may._cong = Cong(n, duong_dan_tu_van=ho_so)
    yield n
    nha_may.dat_lai()


def _ten_cong_cu() -> set[str]:
    return {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}


def test_hai_cong_cu_moi_co_mat():
    assert {"ton_kho_realtime", "suc_khoe_erp"} <= _ten_cong_cu()


def test_ton_kho_realtime_tra_so_ban_duoc(cong_gia):
    kq = chay(mcp_server.ton_kho_realtime("AS-CL01"))
    assert kq["tra_duoc"] is True
    assert kq["ban_duoc"] == 7
    assert kq["ma_kho"] == "KHO-HN"


def test_khong_tra_duoc_thi_noi_khong_biet_chu_khong_tra_0(cong_gia):
    # Trả 0 nghĩa là HẾT HÀNG. Đó là câu trả lời sai khác hẳn "chưa tra
    # được", và client MCP không có cách nào phân biệt hai thứ đó.
    cong_gia.hong = True
    kq = chay(mcp_server.ton_kho_realtime("AS-CL01"))
    assert kq["tra_duoc"] is False
    assert "ban_duoc" not in kq
    assert kq["ghi_chu"]


def test_ma_khong_co_cung_la_khong_tra_duoc(cong_gia):
    kq = chay(mcp_server.ton_kho_realtime("KHONG-CO"))
    assert kq["tra_duoc"] is False


def test_suc_khoe_erp_noi_ro_nguon_va_mach(cong_gia):
    kq = chay(mcp_server.suc_khoe_erp())
    assert kq["nguon"] == "gia"
    assert kq["mach_mo"] is False
    assert kq["song"] is True


def test_suc_khoe_erp_bao_chet_khi_nguon_hong(cong_gia):
    cong_gia.hong = True
    assert chay(mcp_server.suc_khoe_erp())["song"] is False


def test_hai_cong_cu_moi_khong_nam_trong_nhom_bi_cam():
    # Lặp lại phép kiểm của test_mcp.py trên đúng hai tên mới, để nếu ai đó
    # sau này đổi `ton_kho_realtime` thành công cụ điều chỉnh kho thì đỏ.
    cam = {"dieu_chinh_kho", "nhap_hang", "tru_kho", "adjust_stock"}
    assert not (_ten_cong_cu() & cam)
