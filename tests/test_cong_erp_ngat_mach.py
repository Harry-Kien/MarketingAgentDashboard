"""Ngắt mạch: ERP chậm không được kéo cả contact center chậm theo.

Ở contact center, mỗi lời gọi treo là hàng chục khách chờ cùng lúc.
"""
from agent.erp.cong import Cong
from agent.erp.hop_dong import TonKho
from tests.erp_gia import NguonGia, chay


class DongHo:
    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def tien(self, giay: float) -> None:
        self.t += giay


def _bo(dh):
    """Nguồn luôn hỏng, TTL = 0 nên lần nào cũng phải gọi ERP thật."""
    n = NguonGia(ton={"A": TonKho(ban_duoc=5)}, hong=True)
    return n, Cong(
        n, ttl_ton=0.0, ngat_mach_so_lan=3, ngat_mach_giay=30.0, dong_ho=dh
    )


def test_mach_dong_luc_dau():
    _, c = _bo(DongHo())
    assert c.trang_thai()["mach_mo"] is False


def test_du_so_lan_hong_thi_mo_mach():
    _, c = _bo(DongHo())
    for _ in range(3):
        assert chay(c.ton_kho("A")) is None
    assert c.trang_thai()["mach_mo"] is True
    assert c.trang_thai()["hong_lien_tiep"] == 3


def test_mach_mo_thi_khong_goi_erp_nua():
    n, c = _bo(DongHo())
    for _ in range(3):
        chay(c.ton_kho("A"))
    truoc = n.so_lan_goi["ton_kho"]
    for _ in range(10):
        assert chay(c.ton_kho("A")) is None
    assert n.so_lan_goi["ton_kho"] == truoc


def test_het_thoi_gian_mo_mach_thi_thu_lai():
    dh = DongHo()
    n, c = _bo(dh)
    for _ in range(3):
        chay(c.ton_kho("A"))
    truoc = n.so_lan_goi["ton_kho"]
    dh.tien(31)
    chay(c.ton_kho("A"))
    assert n.so_lan_goi["ton_kho"] == truoc + 1


def test_goi_thanh_cong_thi_dat_lai_bo_dem():
    n, c = _bo(DongHo())
    chay(c.ton_kho("A"))
    chay(c.ton_kho("A"))
    assert c.trang_thai()["hong_lien_tiep"] == 2
    n.hong = False
    assert chay(c.ton_kho("A")).ban_duoc == 5
    assert c.trang_thai()["hong_lien_tiep"] == 0
    assert c.trang_thai()["mach_mo"] is False


def test_trang_thai_noi_ro_nguon_nao():
    _, c = _bo(DongHo())
    assert c.trang_thai()["nguon"] == "gia"
