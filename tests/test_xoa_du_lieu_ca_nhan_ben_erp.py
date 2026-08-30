"""Xoá dữ liệu cá nhân phải với tới cả ERP.

VÌ SAO
------
Từ khi có cổng ghi đơn, tên — số điện thoại — địa chỉ khách được tạo thành
`Customer` (ERPNext) hoặc `res.partner` (Odoo) và nằm đó VĨNH VIỄN. Luồng
xoá trong `du_lieu_ca_nhan.xoa()` không biết ERP tồn tại.

Nghĩa là: khách yêu cầu xoá, hệ thống báo "đã xoá", nhật ký ghi
`pdpd.xoa_du_lieu` làm bằng chứng tuân thủ — mà dữ liệu vẫn còn nguyên ở
ERP. Đó không phải một thiếu sót tính năng; đó là một bản ghi nhật ký SAI SỰ
THẬT về nghĩa vụ pháp lý.

ẨN DANH, KHÔNG XOÁ HẲN
----------------------
Cùng lý do đơn hàng nội bộ được ẩn danh chứ không xoá: ERP không cho xoá bản
ghi đã có chứng từ, và nghĩa vụ lưu sổ sách kế toán vẫn còn. Ẩn danh giữ
được chứng từ mà không giữ người.

HỎNG PHẢI NÓI RA
----------------
ERP không với tới được thì KHÔNG được báo "đã xoá xong". Người vận hành phải
biết còn việc chưa làm, vì thời hạn đáp ứng yêu cầu xoá là do luật đặt, không
phải do hệ thống đặt.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agent.config import settings
from agent.core import du_lieu_ca_nhan
from agent.erp import nha_may
from tests.erp_gia import chay

ROOT = Path(__file__).resolve().parent.parent


class NguonGhiGia:
    ten = "gia_ghi"

    def __init__(self, so_ban_ghi: int = 1, nem: Exception | None = None):
        self.so_ban_ghi = so_ban_ghi
        self.nem = nem
        self.da_goi: list[str] = []

    async def tim_don(self, khoa):
        return None

    async def bao_dam_khach(self, ten, sdt, dia_chi):
        return "KH-1"

    async def tao_don(self, khoa, khach_id, dong, ghi_chu=""):
        raise AssertionError("xoá dữ liệu không được tạo đơn")

    async def trang_thai_giao(self, erp_ma_don: str) -> str | None:
        return None

    async def an_danh_khach(self, sdt: str) -> int:
        self.da_goi.append(sdt)
        if self.nem:
            raise self.nem
        return self.so_ban_ghi


def _bat_erp(monkeypatch, nguon):
    monkeypatch.setattr(settings, "erp_loai", "erpnext")
    monkeypatch.setattr(settings, "erp_ghi_don", True)
    nha_may.dat_lai()
    monkeypatch.setattr(nha_may, "tao_nguon", lambda: nguon)


# --- Hợp đồng --------------------------------------------------------

def test_hop_dong_ghi_co_an_danh_khach():
    from agent.erp.hop_dong import NguonGhiERP

    assert hasattr(NguonGhiERP, "an_danh_khach"), (
        "NguonGhiERP thiếu an_danh_khach — không có đường xoá dữ liệu cá "
        "nhân khỏi ERP"
    )


def test_ca_hai_adapter_deu_an_danh_duoc():
    from agent.erp.erpnext import NguonErpNext
    from agent.erp.odoo import NguonOdoo

    for lop in (NguonErpNext, NguonOdoo):
        assert hasattr(lop, "an_danh_khach"), f"{lop.__name__} thiếu an_danh_khach"


# --- Luồng xoá gọi tới ERP -------------------------------------------

def test_xoa_goi_toi_erp(monkeypatch):
    n = NguonGhiGia()
    _bat_erp(monkeypatch, n)
    kq = chay(du_lieu_ca_nhan.an_danh_ben_erp("0901234567"))
    nha_may.dat_lai()
    assert n.da_goi == ["0901234567"]
    assert kq["da_lam"] is True
    assert kq["so_ban_ghi"] == 1


def test_erp_tat_thi_noi_ro_la_khong_ap_dung(monkeypatch):
    # Chưa bật ghi đơn thì ERP chưa từng nhận dữ liệu khách nào. Báo "hỏng"
    # ở đây là báo động giả.
    monkeypatch.setattr(settings, "erp_ghi_don", False)
    nha_may.dat_lai()
    kq = chay(du_lieu_ca_nhan.an_danh_ben_erp("0901234567"))
    assert kq["da_lam"] is False
    assert kq["ap_dung"] is False
    assert "chưa" in kq["ghi_chu"].lower()


def test_erp_hong_thi_BAO_CHUA_XONG_chu_khong_im(monkeypatch):
    # Đây là ràng buộc quan trọng nhất của cả module. Báo "đã xoá" khi ERP
    # còn nguyên dữ liệu là ghi một bản nhật ký SAI SỰ THẬT về nghĩa vụ
    # pháp lý.
    n = NguonGhiGia(nem=RuntimeError("ERP không trả lời"))
    _bat_erp(monkeypatch, n)
    kq = chay(du_lieu_ca_nhan.an_danh_ben_erp("0901234567"))
    nha_may.dat_lai()
    assert kq["da_lam"] is False
    assert kq["ap_dung"] is True
    assert "ERP không trả lời" in kq["ly_do"]


def test_nguon_khong_ghi_duoc_thi_khong_ap_dung(monkeypatch):
    # Nguồn `tep` chưa bao giờ nhận dữ liệu khách.
    monkeypatch.setattr(settings, "erp_loai", "tep")
    monkeypatch.setattr(settings, "erp_ghi_don", True)
    nha_may.dat_lai()
    kq = chay(du_lieu_ca_nhan.an_danh_ben_erp("0901234567"))
    nha_may.dat_lai()
    assert kq["ap_dung"] is False


# --- Kết quả xoá phải phản ánh sự thật -------------------------------

def test_ket_qua_xoa_co_muc_erp():
    ma = (ROOT / "agent" / "core" / "du_lieu_ca_nhan.py").read_text(encoding="utf-8")
    assert "an_danh_ben_erp" in ma, "xoa() chưa gọi tới ERP"
    assert '"erp"' in ma, "kết quả xoá phải có mục erp để người vận hành thấy"


def test_nhat_ky_ghi_ca_ket_qua_erp():
    # Nhật ký `pdpd.xoa_du_lieu` là BẰNG CHỨNG tuân thủ. Nó phải nói cả phần
    # chưa làm được, nếu không nó là bằng chứng cho một việc chưa xong.
    ma = (ROOT / "agent" / "core" / "du_lieu_ca_nhan.py").read_text(encoding="utf-8")
    i = ma.index("pdpd.xoa_du_lieu")
    khoi = ma[i:i + 700]
    assert "erp" in khoi.lower(), (
        "log_event('pdpd.xoa_du_lieu') chưa ghi kết quả bên ERP"
    )


def test_tai_lieu_phap_ly_nhac_toi_erp():
    # docs/du-lieu-ca-nhan.md liệt kê nơi lưu dữ liệu. Thiếu ERP là tài liệu
    # nói dối về phạm vi.
    tl = ROOT / "docs" / "du-lieu-ca-nhan.md"
    if not tl.exists():
        pytest.skip("chưa có tài liệu này")
    assert "ERP" in tl.read_text(encoding="utf-8"), (
        "docs/du-lieu-ca-nhan.md chưa nhắc ERP là nơi lưu thứ ba"
    )
