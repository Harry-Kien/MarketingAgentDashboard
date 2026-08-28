"""Adapter đọc `catalog.json` — nguồn mặc định, giữ clone sạch chạy được."""
import json

import pytest

from agent.erp.hop_dong import LoiERP, NguonERP
from agent.erp.tep import NguonTep
from tests.erp_gia import chay


@pytest.fixture
def catalog(tmp_path):
    p = tmp_path / "catalog.json"
    p.write_text(
        json.dumps(
            {
                "san_pham": [
                    {"ma": "AS-CL01", "ten": "Sữa rửa mặt", "loai": "Làm sạch",
                     "gia": 245000, "dung_tich": "150ml", "ton_kho": 84},
                    {"ma": "AS-SR9", "ten": "Hàng ngừng bán", "loai": "Serum",
                     "gia": 500000, "ton_kho": 3, "ngung_ban": True},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return p


def test_la_nguon_erp_hop_le(catalog):
    assert isinstance(NguonTep(catalog), NguonERP)


def test_doc_duoc_san_pham(catalog):
    ds = chay(NguonTep(catalog).danh_sach_san_pham())
    assert [sp.ma for sp in ds] == ["AS-CL01"]
    assert ds[0].ten == "Sữa rửa mặt"
    assert ds[0].dung_tich == "150ml"


def test_mac_dinh_loai_hang_khong_duoc_ban(catalog):
    # ERP chứa cả hàng ngừng kinh doanh, hàng mẫu, vật tư nội bộ. Không lọc
    # thì agent nhiệt tình tư vấn lọ sample không bán.
    ds = chay(NguonTep(catalog).danh_sach_san_pham())
    assert "AS-SR9" not in [sp.ma for sp in ds]


def test_xin_ca_hang_khong_ban_thi_van_tra(catalog):
    ds = chay(NguonTep(catalog).danh_sach_san_pham(chi_ban_duoc=False))
    assert {sp.ma for sp in ds} == {"AS-CL01", "AS-SR9"}
    assert [sp.ban_duoc_phep for sp in ds if sp.ma == "AS-SR9"] == [False]


def test_gia_va_ton_kho(catalog):
    n = NguonTep(catalog)
    g = chay(n.gia("AS-CL01"))
    assert g.gia_ban == 245000
    assert g.nguon == "catalog.json"
    t = chay(n.ton_kho("AS-CL01"))
    assert t.ban_duoc == 84


def test_ma_khong_co_thi_tra_none(catalog):
    n = NguonTep(catalog)
    assert chay(n.gia("KHONG-CO")) is None
    assert chay(n.ton_kho("KHONG-CO")) is None


def test_file_that_khong_co_thi_roi_ve_ban_mau(tmp_path):
    # Đường lui bắt buộc: `catalog.json` nằm trong .gitignore nên không đi
    # theo repo. Thiếu đường lui này là máy vừa clone về chạy ra rỗng, agent
    # không nói được giá nào, và người cài tưởng hệ thống hỏng.
    ds = chay(NguonTep(tmp_path / "khong-ton-tai.json").danh_sach_san_pham())
    assert len(ds) > 0


def test_file_hong_thi_nem_loi_erp_khong_tra_rong(tmp_path):
    # Trả rỗng là hỏng IM LẶNG: agent tưởng cửa hàng không có sản phẩm nào
    # và chuyển hết cho người, không ai biết vì sao.
    xau = tmp_path / "catalog.json"
    xau.write_text("{ dữ liệu hỏng", encoding="utf-8")
    with pytest.raises(LoiERP):
        chay(NguonTep(xau).danh_sach_san_pham())


def test_suc_khoe(catalog, tmp_path):
    assert chay(NguonTep(catalog).suc_khoe()) is True
    xau = tmp_path / "hong.json"
    xau.write_text("{ hỏng", encoding="utf-8")
    assert chay(NguonTep(xau).suc_khoe()) is False
