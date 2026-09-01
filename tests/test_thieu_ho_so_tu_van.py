"""
SKU có bên ERP mà chưa ai viết nửa tư vấn thì KHÔNG được đem ra khuyên.

`agent/erp/cong.py:193` gắn cờ `duoc_gioi_thieu=False` cho đúng trường hợp
này và ghi `erp.thieu_ho_so`. Nhưng suốt một thời gian dài không mã nào đọc
cờ đó — tìm khắp repo chỉ thấy nơi ĐẶT cờ, tài liệu, và test của cổng.

Cảnh báo có, chặn thì không. Hậu quả đúng như `docs/van-hanh.md` mô tả:
"agent giới thiệu một sản phẩm nghe rất chung chung" — nó biết tên và giá,
không biết hợp loại da nào, và vẫn đem ra khuyên.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core import tools  # noqa: E402


def _hang(ma: str, ten: str, *, du_ho_so: bool, **them) -> dict:
    sp = {
        "ma": ma,
        "ten": ten,
        "loai": "Dưỡng ẩm",
        "gia": 250_000,
        "dung_tich": "50ml",
        "ton_kho": 10,
        "duoc_gioi_thieu": du_ho_so,
    }
    if du_ho_so:
        sp["da_phu_hop"] = ["da dầu", "da hỗn hợp"]
        sp["van_de_ho_tro"] = ["cấp ẩm"]
        sp["thanh_phan_chinh"] = ["hyaluronic acid"]
    sp.update(them)
    return sp


@pytest.fixture
def danh_muc_gia(monkeypatch):
    """Thay danh mục sống bằng danh mục dựng sẵn — không chạm ERP, không CSDL."""
    def dat(san_pham: list[dict]):
        async def _gia():
            return {"san_pham": san_pham}
        monkeypatch.setattr(tools, "_catalog_song", _gia)
    return dat


def _goi_y(**args) -> dict:
    return asyncio.run(tools.run_tool("goi_y_san_pham", args, None))


def _tra_cuu(ten: str) -> dict:
    return asyncio.run(tools.run_tool("tra_cuu_san_pham", {"ten_san_pham": ten}, None))


# =====================================================================
#  Gợi ý
# =====================================================================

def test_khong_goi_y_hang_chua_co_ho_so_tu_van(danh_muc_gia):
    danh_muc_gia([
        _hang("A-01", "Kem dưỡng có hồ sơ", du_ho_so=True),
        _hang("B-02", "Hàng ERP chưa ai viết tư vấn", du_ho_so=False,
              da_phu_hop=["da dầu"], van_de_ho_tro=["cấp ẩm"]),
    ])

    kq = _goi_y(loai_da="da dầu")

    ten_goi_y = [s["ten"] for s in kq["san_pham"]]
    assert "Kem dưỡng có hồ sơ" in ten_goi_y
    assert "Hàng ERP chưa ai viết tư vấn" not in ten_goi_y
    assert kq["so_luong"] == 1


def test_bao_cho_agent_biet_co_hang_bi_loai_va_cam_nhac_ten(danh_muc_gia):
    """
    Agent phải BIẾT là có hàng bị loại — nếu không nó tưởng cửa hàng không
    có gì và nói sai. Nhưng KHÔNG được nhắc tên với khách, vì nhắc tên một
    món rồi không tư vấn được gì về nó là tệ hơn không nhắc.
    """
    danh_muc_gia([
        _hang("A-01", "Có hồ sơ", du_ho_so=True),
        _hang("B-02", "Chưa có hồ sơ", du_ho_so=False,
              da_phu_hop=["da dầu"], van_de_ho_tro=["cấp ẩm"]),
    ])

    kq = _goi_y(loai_da="da dầu")

    assert kq["thieu_ho_so_tu_van"] == ["Chưa có hồ sơ"]
    assert "KHÔNG nhắc tên" in kq["ghi_chu"]


def test_tat_ca_deu_thieu_ho_so_thi_chuyen_nguoi_chu_khong_khuyen_bua(danh_muc_gia):
    """
    Đây là ca nguy hiểm nhất: nối ERP mà chưa nạp nửa tư vấn nào.

    Trả danh sách rỗng kèm lời dặn chuyển người là đúng; trả sản phẩm kèm
    một câu chung chung là phát ngôn không có căn cứ.
    """
    danh_muc_gia([
        _hang("B-02", "Chưa có hồ sơ", du_ho_so=False,
              da_phu_hop=["da dầu"], van_de_ho_tro=["cấp ẩm"]),
    ])

    kq = _goi_y(loai_da="da dầu")

    assert kq["so_luong"] == 0
    assert "san_pham" not in kq
    assert kq["thieu_ho_so_tu_van"] == ["Chưa có hồ sơ"]
    assert "chuyen_nhan_vien" in kq["ghi_chu"]


def test_co_ho_so_thi_khong_kem_canh_bao_thua(danh_muc_gia):
    """Cảnh báo nổ khi không có gì để cảnh báo là cách nhanh nhất bị bỏ qua."""
    danh_muc_gia([_hang("A-01", "Có hồ sơ", du_ho_so=True)])

    kq = _goi_y(loai_da="da dầu")

    assert "thieu_ho_so_tu_van" not in kq
    assert "ghi_chu" not in kq


def test_nguon_tep_khong_gan_co_thi_van_goi_y_binh_thuong(danh_muc_gia):
    """
    Nguồn `tep` KHÔNG gắn `duoc_gioi_thieu`. Mặc định chặn khi cờ vắng mặt
    sẽ làm câm toàn bộ gợi ý trên bản chạy file — tức là làm hỏng đường đi
    mặc định của repo để vá một đường ít dùng hơn.
    """
    sp = _hang("A-01", "Hàng từ file", du_ho_so=True)
    del sp["duoc_gioi_thieu"]
    danh_muc_gia([sp])

    kq = _goi_y(loai_da="da dầu")

    assert kq["so_luong"] == 1
    assert "thieu_ho_so_tu_van" not in kq


# =====================================================================
#  Tra cứu đích danh
# =====================================================================

def test_tra_cuu_dich_danh_van_tra_gia_nhung_kem_canh_bao(danh_muc_gia):
    """
    Khách hỏi đúng tên thì vẫn phải trả giá và tồn — hai số ấy CÓ THẬT, đến
    từ ERP. Nhưng phải nói rõ là không có nửa tư vấn, nếu không model lấp
    chỗ trống bằng suy đoán từ tên hàng.
    """
    danh_muc_gia([
        _hang("B-02", "Serum chưa có hồ sơ", du_ho_so=False),
    ])

    kq = _tra_cuu("Serum chưa có hồ sơ")

    assert kq["tim_thay"] is True
    assert kq["gia"] == 250_000
    assert kq["con_hang"] is True
    assert "CHƯA có hồ sơ tư vấn" in kq["ghi_chu"]
    assert "chuyen_nhan_vien" in kq["ghi_chu"]


def test_tra_cuu_hang_du_ho_so_khong_kem_canh_bao(danh_muc_gia):
    danh_muc_gia([_hang("A-01", "Kem dưỡng đủ hồ sơ", du_ho_so=True)])

    kq = _tra_cuu("Kem dưỡng đủ hồ sơ")

    assert kq["tim_thay"] is True
    assert "ghi_chu" not in kq
