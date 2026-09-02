"""Hợp đồng dữ liệu của cổng ERP.

Test canh hai điều dễ trượt nhất: `Gia` phải là một VẬT chứ không phải một
số nguyên (vì giá thật phụ thuộc bảng giá, và ta cần truy vết nguồn), và
`TonKho.ban_duoc` phải là hàng BÁN ĐƯỢC chứ không phải hàng có trong kho.
"""
import dataclasses

import pytest

from agent.erp.hop_dong import Gia, KetQuaDon, LoiERP, NguonERP, SanPhamERP, TonKho


def test_gia_la_vat_khong_phai_so():
    # Giá thật phụ thuộc bảng giá; trả về int trần là mất đường truy vết
    # khi khách thắc mắc "sao báo giá này".
    g = Gia(gia_ban=245_000, nguon="Bảng giá bán lẻ")
    assert g.gia_ban == 245_000
    assert g.don_vi == "VND"
    assert g.nguon == "Bảng giá bán lẻ"
    assert g.hieu_luc_den is None


def test_gia_bat_bien():
    # Bất biến để không ai lỡ tay sửa giá sau khi cổng đã trả ra.
    g = Gia(gia_ban=100)
    with pytest.raises(dataclasses.FrozenInstanceError):
        g.gia_ban = 1


def test_ton_kho_la_hang_ban_duoc():
    t = TonKho(ban_duoc=7, ma_kho="KHO-HN")
    assert t.ban_duoc == 7
    assert t.ma_kho == "KHO-HN"


def test_san_pham_mac_dinh_duoc_phep_ban():
    sp = SanPhamERP(ma="AS-CL01", ten="Sữa rửa mặt")
    assert sp.ban_duoc_phep is True


def test_ket_qua_don_that_bai_phai_co_ly_do():
    kq = KetQuaDon(thanh_cong=False, ly_do="ERP từ chối: hết hàng")
    assert kq.thanh_cong is False
    assert kq.erp_ma_don == ""
    assert "hết hàng" in kq.ly_do


def test_loi_erp_la_runtime_error():
    assert issubclass(LoiERP, RuntimeError)


class _NguonToiThieu:
    ten = "toi_thieu"

    async def danh_sach_san_pham(self, chi_ban_duoc: bool = True):
        return []

    async def gia(self, ma: str):
        return None

    async def ton_kho(self, ma: str):
        return None

    async def suc_khoe(self) -> bool:
        return True


def test_protocol_nhan_dien_duoc_nguon_hop_le():
    # runtime_checkable để `san_sang.py` kiểm được adapter nạp từ .env có đủ
    # bốn phương thức hay không, TRƯỚC khi khách nhắn tin đầu tiên.
    assert isinstance(_NguonToiThieu(), NguonERP)


def test_protocol_tu_choi_nguon_thieu_phuong_thuc():
    class _Thieu:
        ten = "thieu"

        async def gia(self, ma: str):
            return None

    assert not isinstance(_Thieu(), NguonERP)
