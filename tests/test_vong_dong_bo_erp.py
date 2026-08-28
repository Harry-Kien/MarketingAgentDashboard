"""Vòng nền thử lại đơn kẹt `cho_dong_bo`.

Không có vòng này thì `cho_dong_bo` là NGÕ CỤT: đơn nằm đó mãi, khách chờ,
và biểu hiện duy nhất ra ngoài là một dòng trạng thái không ai xem.

Bốn điều được canh:

1. Backoff — ERP đang bảo trì mà quét mỗi 30 giây là đập vào hệ thống đang ốm.
2. Bỏ cuộc CÓ TIẾNG — thử mãi mãi là giấu một đơn hỏng sau vòng lặp bận rộn.
3. Từ chối thì dừng ngay, không thử lại. Đó là câu trả lời.
4. Một đơn hỏng KHÔNG được làm dừng cả lượt quét.
"""
from __future__ import annotations

from agent.erp.day_don import KetQuaDay
from agent.erp.vong_dong_bo import (SO_LAN_TOI_DA, quet_mot_luot,
                                    tre_lan_sau)
from tests.erp_gia import chay


class KhoDonGia:
    def __init__(self, don: list[dict]):
        self.don = don
        self.da_day: list[tuple] = []
        self.that_bai: list[tuple] = []
        self.bo_cuoc: list[tuple] = []

    async def don_cho_dong_bo(self, gioi_han: int = 20):
        return self.don

    async def danh_dau_da_day(self, id_don, erp_ma_don):
        self.da_day.append((id_don, erp_ma_don))

    async def danh_dau_that_bai(self, id_don, ly_do):
        self.that_bai.append((id_don, ly_do))

    async def danh_dau_bo_cuoc(self, id_don, ly_do):
        self.bo_cuoc.append((id_don, ly_do))


def _don(**kw) -> dict:
    return {
        "id": kw.pop("id", 1),
        "ma_don": kw.pop("ma_don", "AS001"),
        "erp_so_lan_thu": kw.pop("so_lan", 0),
        # Đủ lâu để tới lượt, trừ khi test cố ý đặt khác.
        "_giay_tu_lan_thu_cuoi": kw.pop("giay", 10_000),
        **kw,
    }


def _quet(don, ket_cuc="xong", **kw):
    kho = KhoDonGia(don)
    nhat_ky: list = []

    async def ghi(loai, **ct):
        nhat_ky.append((loai, ct))

    async def day(_d):
        if callable(ket_cuc):
            return ket_cuc(_d)
        return KetQuaDay(ket_cuc=ket_cuc, **kw)

    tk = chay(quet_mot_luot(kho, day, ghi))
    return kho, tk, nhat_ky


# --- Đường suôn ------------------------------------------------------

def test_day_lai_thanh_cong_thi_danh_dau_xong():
    kho, tk, nhat_ky = _quet([_don()], "xong", erp_ma_don="SO-9")
    assert kho.da_day == [(1, "SO-9")]
    assert tk["xong"] == 1
    assert any(l == "erp.don_dong_bo_muon" for l, _ in nhat_ky)


def test_van_con_hong_thi_dem_them_mot_lan():
    kho, tk, _ = _quet([_don(so_lan=2)], "cho_lai", ly_do="vẫn đứt")
    assert kho.that_bai == [(1, "vẫn đứt")]
    assert tk["con_cho"] == 1
    assert kho.bo_cuoc == []


# --- 1. Backoff ------------------------------------------------------

def test_tre_gian_dan_va_co_tran():
    assert tre_lan_sau(0) == 60
    assert tre_lan_sau(1) == 120
    assert tre_lan_sau(2) == 240
    assert tre_lan_sau(99) == 1800     # chặn ở 30 phút


def test_chua_toi_luot_thi_khong_goi_erp():
    # ERP đang bảo trì mà quét mỗi 30 giây là đập vào hệ thống đang ốm.
    goi: list = []

    def day(d):
        goi.append(d)
        return KetQuaDay(ket_cuc="xong")

    kho, tk, _ = _quet([_don(so_lan=3, giay=10)], day)
    assert goi == []
    assert tk["hoan"] == 1
    assert kho.da_day == []


def test_toi_luot_thi_goi():
    kho, tk, _ = _quet([_don(so_lan=1, giay=200)], "xong", erp_ma_don="SO-1")
    assert tk["xong"] == 1


# --- 2. Bỏ cuộc có tiếng ---------------------------------------------

def test_qua_so_lan_toi_da_thi_dung_va_KEU():
    # Thử mãi mãi là giấu một đơn hỏng sau một vòng lặp bận rộn — nhìn từ
    # ngoài không phân biệt được với đang chạy bình thường.
    kho, tk, nhat_ky = _quet([_don(so_lan=SO_LAN_TOI_DA)], "xong")
    assert tk["bo_cuoc"] == 1
    assert kho.da_day == []
    assert any(l == "erp.don_bo_cuoc" for l, _ in nhat_ky)


def test_bo_cuoc_khong_goi_erp_nua():
    goi: list = []

    def day(d):
        goi.append(d)
        return KetQuaDay(ket_cuc="xong")

    _quet([_don(so_lan=SO_LAN_TOI_DA + 5)], day)
    assert goi == []


# --- 3. Từ chối là câu trả lời ---------------------------------------

def test_erp_tu_choi_thi_dung_ngay_khong_thu_lai():
    kho, tk, nhat_ky = _quet([_don()], "tu_choi", ly_do="mã hàng không tồn tại")
    assert tk["bo_cuoc"] == 1
    assert kho.bo_cuoc == [(1, "mã hàng không tồn tại")]
    assert kho.that_bai == []
    assert any(l == "erp.don_bi_tu_choi_khi_thu_lai" for l, _ in nhat_ky)


# --- 4. Một đơn hỏng không làm dừng cả lượt --------------------------

def test_mot_don_nem_thi_cac_don_sau_van_duoc_thu():
    def day(d):
        if d["id"] == 1:
            raise RuntimeError("bất ngờ")
        return KetQuaDay(ket_cuc="xong", erp_ma_don=f"SO-{d['id']}")

    kho, tk, _ = _quet([_don(id=1), _don(id=2), _don(id=3)], day)
    assert tk["da_xet"] == 3
    assert [i for i, _ in kho.da_day] == [2, 3]
    assert [i for i, _ in kho.that_bai] == [1]


def test_quet_khong_bao_gio_nem():
    def day(_d):
        raise KeyboardInterrupt  # noqa: TRY301 — cố tình chọn thứ khó nhất

    kho = KhoDonGia([_don()])

    async def ghi(*_a, **_k):
        return None

    try:
        chay(quet_mot_luot(kho, day, ghi))
    except KeyboardInterrupt:
        # BaseException KHÔNG bị nuốt, và đó là đúng: Ctrl-C phải dừng được
        # tiến trình. Chỉ `Exception` mới bị bắt.
        pass


def test_danh_sach_rong_thi_khong_lam_gi():
    kho, tk, _ = _quet([])
    assert tk == {"da_xet": 0, "xong": 0, "bo_cuoc": 0, "con_cho": 0,
                  "hoan": 0}


# =====================================================================
#  Đối soát tồn kho
# =====================================================================

from agent.erp.hop_dong import TonKho  # noqa: E402
from agent.erp.vong_dong_bo import doi_soat_ton_kho  # noqa: E402


def _soat(noi_bo, erp, **kw):
    nhat_ky: list = []

    async def ghi(loai, **ct):
        nhat_ky.append((loai, ct))

    async def hoi(ma):
        v = erp(ma) if callable(erp) else erp.get(ma)
        if isinstance(v, Exception):
            raise v
        return v

    return chay(doi_soat_ton_kho(noi_bo, hoi, ghi, **kw)), nhat_ky


def test_khop_thi_khong_keu():
    kq, nhat_ky = _soat({"A": 5}, {"A": TonKho(ban_duoc=5)})
    assert kq["lech"] == []
    assert nhat_ky == []


def test_lech_thi_keu_kem_ca_hai_con_so():
    # Chỉ báo "có lệch" mà không kèm số thì người đi chữa vẫn phải tự tra
    # lại từ đầu.
    kq, nhat_ky = _soat({"A": 5}, {"A": TonKho(ban_duoc=2)})
    assert kq["lech"] == [{"ma": "A", "noi_bo": 5, "erp": 2}]
    assert nhat_ky[0][0] == "erp.lech_ton_kho"
    assert nhat_ky[0][1]["chi_tiet"][0]["erp"] == 2


def test_KHONG_tu_sua():
    # Máy tự "chữa" một con số nó không hiểu vì sao lệch là xoá mất bằng
    # chứng của lỗi thật, và lần sau lệch lại.
    noi_bo = {"A": 5}
    _soat(noi_bo, {"A": TonKho(ban_duoc=2)})
    assert noi_bo == {"A": 5}


def test_erp_khong_tra_duoc_thi_KHONG_tinh_la_lech():
    # Coi "không biết" thành "lệch" là báo động giả hàng loạt mỗi khi ERP
    # chậm — và báo động giả nhiều thì người ta tắt báo động.
    kq, nhat_ky = _soat({"A": 5}, {"A": None})
    assert kq["lech"] == []
    assert kq["khong_tra_duoc"] == 1
    assert nhat_ky == []


def test_erp_nem_cung_khong_tinh_la_lech():
    kq, _ = _soat({"A": 5}, {"A": RuntimeError("đứt")})
    assert kq["lech"] == []
    assert kq["khong_tra_duoc"] == 1


def test_mot_ma_hong_khong_lam_dung_ca_luot():
    kq, _ = _soat(
        {"A": 5, "B": 9, "C": 1},
        {"A": RuntimeError("x"), "B": TonKho(ban_duoc=9),
         "C": TonKho(ban_duoc=4)},
    )
    assert kq["da_soat"] == 3
    assert [d["ma"] for d in kq["lech"]] == ["C"]


def test_nguong_lech_cho_phep_sai_so_nho():
    kq, _ = _soat({"A": 5}, {"A": TonKho(ban_duoc=4)}, nguong_lech=1)
    assert kq["lech"] == []
