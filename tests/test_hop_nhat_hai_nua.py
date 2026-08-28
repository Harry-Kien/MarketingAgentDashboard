"""Hợp nhất nửa thương mại (ERP) với nửa tư vấn (kho nội bộ).

ERP biết bán cái gì giá bao nhiêu. Nó KHÔNG biết serum này hợp da dầu hay
da khô. Chín trên mười bốn trường của bản ghi sản phẩm không tồn tại trong
Odoo hay ERPNext — và chín trường đó chính là toàn bộ chất tư vấn.
"""
import json

import pytest

from agent.erp.anh_xa import AnhXa
from agent.erp.cong import Cong
from agent.erp.hop_dong import Gia, LoiERP, SanPhamERP, TonKho
from tests.erp_gia import NguonGia, chay


@pytest.fixture
def nua_tu_van(tmp_path):
    p = tmp_path / "catalog.json"
    p.write_text(
        json.dumps(
            {
                "san_pham": [
                    {
                        "ma": "AS-CL01",
                        "ten": "Tên cũ trong file",
                        "gia": 999,
                        "ton_kho": 999,
                        "da_phu_hop": ["da dầu"],
                        "thanh_phan_chinh": ["Cica"],
                        "so_cong_bo": "12345/22/CBMP-HN",
                    }
                ],
                "don_hang": [{"ma": "AS001"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return p


def _nguon():
    return NguonGia(
        san_pham=[SanPhamERP(ma="AS-CL01", ten="Tên thật từ ERP", loai="Làm sạch")],
        gia={"AS-CL01": Gia(gia_ban=245000)},
        ton={"AS-CL01": TonKho(ban_duoc=7)},
    )


def test_giu_dung_hinh_dang_ma_tools_dang_cho(nua_tu_van):
    d = chay(Cong(_nguon(), duong_dan_tu_van=nua_tu_van).danh_muc())
    assert set(d) >= {"san_pham", "don_hang"}
    assert isinstance(d["san_pham"], list)


def test_erp_thang_o_nua_thuong_mai(nua_tu_van):
    d = chay(Cong(_nguon(), duong_dan_tu_van=nua_tu_van).danh_muc())
    sp = d["san_pham"][0]
    assert sp["ten"] == "Tên thật từ ERP"
    assert sp["gia"] == 245000
    assert sp["ton_kho"] == 7


def test_kho_noi_bo_thang_o_nua_tu_van(nua_tu_van):
    d = chay(Cong(_nguon(), duong_dan_tu_van=nua_tu_van).danh_muc())
    sp = d["san_pham"][0]
    assert sp["da_phu_hop"] == ["da dầu"]
    assert sp["thanh_phan_chinh"] == ["Cica"]
    assert sp["so_cong_bo"] == "12345/22/CBMP-HN"


def test_thieu_ho_so_tu_van_thi_khong_duoc_gioi_thieu(nua_tu_van):
    # ERP thêm 50 SKU mới, không ai viết hồ sơ tư vấn cho chúng. Không có cờ
    # này thì agent tư vấn chúng bằng tưởng tượng và không ai biết.
    n = _nguon()
    n.san_pham.append(SanPhamERP(ma="AS-MOI", ten="SKU mới toanh"))
    n.bang_gia["AS-MOI"] = Gia(gia_ban=100000)
    n.bang_ton["AS-MOI"] = TonKho(ban_duoc=3)

    d = chay(Cong(n, duong_dan_tu_van=nua_tu_van).danh_muc())
    moi = [sp for sp in d["san_pham"] if sp["ma"] == "AS-MOI"][0]
    cu = [sp for sp in d["san_pham"] if sp["ma"] == "AS-CL01"][0]
    assert moi["duoc_gioi_thieu"] is False
    assert cu["duoc_gioi_thieu"] is True


def test_erp_hong_hoan_toan_thi_nem_chu_khong_tra_rong(nua_tu_van):
    n = _nguon()
    n.hong = True
    with pytest.raises(LoiERP):
        chay(Cong(n, duong_dan_tu_van=nua_tu_van).danh_muc())


def test_dung_anh_xa_ma(tmp_path):
    p = tmp_path / "catalog.json"
    p.write_text(
        json.dumps(
            {"san_pham": [{"ma": "AS-CL01", "da_phu_hop": ["da khô"]}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    n = NguonGia(
        san_pham=[SanPhamERP(ma="ITEM-1", ten="Từ ERP")],
        gia={"ITEM-1": Gia(gia_ban=1000)},
        ton={"ITEM-1": TonKho(ban_duoc=1)},
    )
    c = Cong(n, duong_dan_tu_van=p, anh_xa=AnhXa({"AS-CL01": "ITEM-1"}))
    sp = chay(c.danh_muc())["san_pham"][0]
    assert sp["ma"] == "AS-CL01"
    assert sp["da_phu_hop"] == ["da khô"]
    assert sp["duoc_gioi_thieu"] is True


def test_gia_khong_tra_duoc_thi_bo_qua_san_pham_do(nua_tu_van):
    # Sản phẩm không có giá thì agent không được nói về nó — nói mà không
    # kèm giá là mời khách hỏi giá rồi trả lời bằng số bịa.
    n = _nguon()
    n.bang_gia.clear()
    d = chay(Cong(n, duong_dan_tu_van=nua_tu_van).danh_muc())
    assert d["san_pham"] == []
