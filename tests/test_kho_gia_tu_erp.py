"""
Màn Kho phải hỏi GIÁ từ ERP, không chỉ từ file danh mục.

LỖI THẬT, ĐO ĐƯỢC 14.09.2026
---------------------------
`/api/kho` ghép mỗi dòng tồn kho với `_catalog()` — file `data/catalog.json`
trên đĩa. Mã nào không nằm trong file ấy thì `gia = 0`, và dòng hiện
"(không có trong danh mục)".

Trên hệ thống thật: `catalog.json` có 13 mã, bảng `ton_kho` có 35 dòng, và
22 mã còn lại là HÀNG THẬT đã ngừng bán nhưng CÒN TỒN 1.088 đơn vị, với giá
đầy đủ trong ERPNext (AS-CB01 giá 1.150.000đ, AS-CL01 giá 245.000đ…).

Hậu quả: ô "Giá trị tồn" trên dashboard bỏ sót toàn bộ số hàng ấy — riêng
một mã đã 28 triệu. Người vận hành đọc một con số thấp hơn thực tế và không
có gì nói cho họ biết. Không lỗi, không nhật ký.

VÌ SAO KHÔNG ĐƠN GIẢN LÀ "NẠP LẠI catalog.json"
-----------------------------------------------
`catalog.json` cố ý chỉ chứa hàng ĐANG BÁN: đó là thứ agent được phép tư
vấn. Nhồi hàng ngừng bán vào đó là agent bắt đầu chào bán chúng. Hai câu
hỏi khác nhau — "bán được gì" và "trong kho còn gì đáng bao nhiêu" — phải
có hai nguồn, và màn Kho hỏi câu thứ hai.

GIÁ KHÔNG BIẾT KHÁC GIÁ BẰNG KHÔNG
----------------------------------
ERP không trả giá thì `gia` là None, không phải 0. Gộp hai thứ là nói dối
một cách tự tin: "giá trị tồn" cộng thêm 0 trông y hệt như món ấy không
đáng gì, trong khi sự thật là chưa tra được.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.api import routes  # noqa: E402
from agent.erp.hop_dong import Gia  # noqa: E402


@pytest.fixture
def kho_gia(monkeypatch):
    """Một dòng trong danh mục, một dòng chỉ có ở ERP, một dòng không ai biết."""
    ton = [
        {"ma": "BLA-1", "so_luong": 2, "cap_nhat_luc": _luc()},
        {"ma": "AS-1", "so_luong": 25, "cap_nhat_luc": _luc()},
        {"ma": "AS-2", "so_luong": 10, "cap_nhat_luc": _luc()},
    ]
    gia_erp = {"AS-1": 1_150_000}

    async def fetch(sql, *a):
        return ton if "ton_kho" in sql else []

    def catalog():
        return {"san_pham": [{"ma": "BLA-1", "ten": "Serum BLANICA",
                              "loai": "Tinh chất", "gia": 300_000}]}

    class _Cong:
        async def gia(self, ma, bo_qua_cache=False):
            g = gia_erp.get(ma)
            return Gia(gia_ban=g, nguon="erpnext") if g else None

    monkeypatch.setattr(routes.db, "fetch", fetch)
    monkeypatch.setattr("agent.core.tools._catalog", catalog)
    monkeypatch.setattr("agent.core.tools._anh_san_pham", lambda ma: None)
    monkeypatch.setattr("agent.erp.nha_may.cong", lambda: _Cong())
    return ton


def _luc():
    from datetime import datetime, timezone
    return datetime(2026, 9, 14, tzinfo=timezone.utc)


def _dong(ra: dict, ma: str) -> dict:
    return next(x for x in ra["san_pham"] if x["ma"] == ma)


def _goi() -> dict:
    return asyncio.run(routes.kho_tong_quan(_quyen={}))


# --- Giá lấy được từ ERP ---------------------------------------------

def test_ma_ngoai_danh_muc_van_co_gia_tu_erp(kho_gia):
    ra = _goi()
    assert _dong(ra, "AS-1")["gia"] == 1_150_000, \
        "hàng thật đã ngừng bán mà hiện giá 0 — giá trị tồn bỏ sót nó"


def test_gia_tri_ton_cong_ca_hang_ngoai_danh_muc(kho_gia):
    ra = _goi()
    assert ra["gia_tri_ton"] == 2 * 300_000 + 25 * 1_150_000


def test_danh_muc_van_la_nguon_uu_tien(kho_gia):
    """Hàng đang bán lấy giá từ danh mục — đó là giá agent báo cho khách,
    và hai con số phải là một."""
    ra = _goi()
    assert _dong(ra, "BLA-1")["gia"] == 300_000


# --- Không biết khác bằng không ---------------------------------------

def test_erp_khong_tra_gia_thi_la_none_khong_phai_0(kho_gia):
    d = _dong(_goi(), "AS-2")
    assert d["gia"] is None, "gộp 'chưa tra được' vào 'giá 0' là nói dối tự tin"


def test_dong_chua_biet_gia_khong_lam_hong_tong(kho_gia):
    ra = _goi()
    assert isinstance(ra["gia_tri_ton"], int)
    assert ra["so_ma_chua_biet_gia"] == 1, \
        "không đếm ra thì người đọc tưởng tổng đã đủ"


# --- ERP hỏng thì bảng vẫn phải vẽ ------------------------------------

def test_erp_hong_thi_van_tra_bang(monkeypatch, kho_gia):
    class _Hong:
        async def gia(self, ma, bo_qua_cache=False):
            raise RuntimeError("ERP sập")

    monkeypatch.setattr("agent.erp.nha_may.cong", lambda: _Hong())
    ra = _goi()
    assert len(ra["san_pham"]) == 3, "ERP sập mà mất luôn bảng tồn kho"
    assert _dong(ra, "BLA-1")["gia"] == 300_000, "giá từ danh mục vẫn phải còn"


def test_ten_van_noi_ro_ma_ngoai_danh_muc(kho_gia):
    """Có giá rồi vẫn phải nói nó không nằm trong danh mục bán: đó là lý do
    agent không chào nó cho khách."""
    assert "danh mục" in _dong(_goi(), "AS-1")["ten"].lower()
