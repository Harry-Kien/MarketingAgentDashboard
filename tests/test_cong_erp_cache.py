"""Cache theo tuổi, và quy tắc trung tâm: KHÔNG BAO GIỜ trả số cũ.

Đồng hồ tiêm vào thay cho `asyncio.sleep` — bộ test không được phép ngủ.
"""
from agent.erp.cong import Cong
from agent.erp.hop_dong import Gia, TonKho
from tests.erp_gia import NguonGia, chay


class DongHo:
    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def tien(self, giay: float) -> None:
        self.t += giay


def _nguon():
    return NguonGia(
        gia={"AS-CL01": Gia(gia_ban=245000, nguon="thử")},
        ton={"AS-CL01": TonKho(ban_duoc=84)},
    )


def test_trong_han_thi_khong_goi_erp_lan_hai():
    n, dh = _nguon(), DongHo()
    c = Cong(n, ttl_ton=60.0, dong_ho=dh)
    assert chay(c.ton_kho("AS-CL01")).ban_duoc == 84
    dh.tien(59)
    assert chay(c.ton_kho("AS-CL01")).ban_duoc == 84
    assert n.so_lan_goi["ton_kho"] == 1


def test_qua_han_thi_goi_lai():
    n, dh = _nguon(), DongHo()
    c = Cong(n, ttl_ton=60.0, dong_ho=dh)
    chay(c.ton_kho("AS-CL01"))
    dh.tien(61)
    chay(c.ton_kho("AS-CL01"))
    assert n.so_lan_goi["ton_kho"] == 2


def test_qua_han_ma_erp_hong_thi_tra_none_khong_tra_so_cu():
    # ĐÂY LÀ RÀNG BUỘC TRUNG TÂM CỦA CẢ CỔNG.
    # Trả số cũ là báo giá sai / báo còn hàng cho món đã hết, một cách tự
    # tin, và không ai biết. Thà im một phút.
    n, dh = _nguon(), DongHo()
    c = Cong(n, ttl_ton=60.0, dong_ho=dh)
    assert chay(c.ton_kho("AS-CL01")).ban_duoc == 84

    dh.tien(61)
    n.hong = True
    assert chay(c.ton_kho("AS-CL01")) is None


def test_gia_cung_khong_bao_gio_tra_so_cu():
    n, dh = _nguon(), DongHo()
    c = Cong(n, ttl_gia=900.0, dong_ho=dh)
    assert chay(c.gia("AS-CL01")).gia_ban == 245000

    dh.tien(901)
    n.hong = True
    assert chay(c.gia("AS-CL01")) is None


def test_bo_qua_cache_thi_luon_goi_erp():
    # Chốt đơn phải đọc tồn SỐNG. Đọc cache 60 giây ở đúng khoảnh khắc chốt
    # là để khách xác nhận xong mới báo hết hàng.
    n, dh = _nguon(), DongHo()
    c = Cong(n, ttl_ton=60.0, dong_ho=dh)
    chay(c.ton_kho("AS-CL01"))
    chay(c.ton_kho("AS-CL01", bo_qua_cache=True))
    assert n.so_lan_goi["ton_kho"] == 2


def test_bo_qua_cache_ma_erp_hong_thi_tra_none():
    n, dh = _nguon(), DongHo()
    c = Cong(n, dong_ho=dh)
    chay(c.ton_kho("AS-CL01"))
    n.hong = True
    assert chay(c.ton_kho("AS-CL01", bo_qua_cache=True)) is None


def test_ma_khong_ton_tai_tra_none_khong_nem():
    c = Cong(_nguon(), dong_ho=DongHo())
    assert chay(c.gia("KHONG-CO")) is None
    assert chay(c.ton_kho("KHONG-CO")) is None


def test_cache_tach_theo_ma():
    n = NguonGia(ton={"A": TonKho(ban_duoc=1), "B": TonKho(ban_duoc=2)})
    c = Cong(n, dong_ho=DongHo())
    assert chay(c.ton_kho("A")).ban_duoc == 1
    assert chay(c.ton_kho("B")).ban_duoc == 2
