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


# =====================================================================
#  Kéo trạng thái giao hàng từ ERP về
# =====================================================================

from agent.erp.vong_dong_bo import keo_trang_thai_giao  # noqa: E402


def _keo(don, erp, ):
    ghi_lai, nhat_ky = [], []

    async def hoi(ma):
        v = erp(ma) if callable(erp) else erp.get(ma)
        if isinstance(v, Exception):
            raise v
        return v

    async def ghi(id_don, tt):
        ghi_lai.append((id_don, tt))

    async def nk(loai, **ct):
        nhat_ky.append((loai, ct))

    return chay(keo_trang_thai_giao(don, hoi, ghi, nk)), ghi_lai, nhat_ky


def test_trang_thai_moi_thi_ghi_va_keu():
    tk, ghi, nk = _keo(
        [{"id": 1, "ma_don": "AS1", "erp_ma_don": "SO-1",
          "trang_thai_giao": None}],
        {"SO-1": "delivering"},
    )
    assert ghi == [(1, "delivering")]
    assert tk["cap_nhat"] == 1
    assert nk[0][0] == "erp.trang_thai_giao_moi"


def test_khong_doi_thi_khong_ghi_lai():
    # Ghi lại một giá trị không đổi là một lượt UPDATE vô ích mỗi phút, và
    # một dòng nhật ký giả làm loãng những dòng thật.
    tk, ghi, _ = _keo(
        [{"id": 1, "erp_ma_don": "SO-1", "trang_thai_giao": "delivering"}],
        {"SO-1": "delivering"},
    )
    assert ghi == []
    assert tk["cap_nhat"] == 0


def test_chua_biet_thi_KHONG_ghi_de():
    # `None` nghĩa là chưa có phiếu giao, hoặc ERP trả trạng thái lạ. Ghi đè
    # trạng thái đang đúng bằng "chưa biết" là xoá mất thông tin thật.
    tk, ghi, _ = _keo(
        [{"id": 1, "erp_ma_don": "SO-1", "trang_thai_giao": "delivering"}],
        {"SO-1": None},
    )
    assert ghi == []
    assert tk["chua_biet"] == 1


def test_mot_don_hong_khong_lam_dung_ca_luot():
    tk, ghi, _ = _keo(
        [{"id": 1, "erp_ma_don": "A", "trang_thai_giao": None},
         {"id": 2, "erp_ma_don": "B", "trang_thai_giao": None},
         {"id": 3, "erp_ma_don": "C", "trang_thai_giao": None}],
        {"A": RuntimeError("đứt"), "B": "delivered", "C": "returned"},
    )
    assert tk["da_xet"] == 3
    assert tk["hong"] == 1
    assert [i for i, _ in ghi] == [2, 3]


def test_keo_danh_sach_rong_thi_khong_lam_gi():
    tk, ghi, nk = _keo([], {})
    assert ghi == [] and nk == []
    assert tk["da_xet"] == 0


# =====================================================================
#  Không được có việc nào viết ra rồi quên nối
# =====================================================================

def test_moi_viec_cua_vong_nen_deu_duoc_vong_nen_goi():
    """Mọi hàm việc trong module này phải được `vong_dong_bo_loop` gọi.

    ĐÃ XẢY RA THẬT: `keo_trang_thai_giao` được viết, được test, được commit
    — và không nối vào vòng nền. Không ai gọi nó. Test vẫn xanh vì test gọi
    thẳng hàm.

    Đó là mã chết đội lốt tính năng: nhìn vào repo thì thấy có, nhìn vào hệ
    thống đang chạy thì không. Và không có gì báo, vì mã chết không nổ.
    """
    import inspect
    import re

    from agent.erp import vong_dong_bo as v

    than_loop = inspect.getsource(v.vong_dong_bo_loop)

    # Hàm VIỆC = coroutine công khai, trừ chính vòng lặp và các tiện ích.
    MIEN = {"vong_dong_bo_loop"}
    viec = {
        ten for ten, o in vars(v).items()
        if inspect.iscoroutinefunction(o) and not ten.startswith("_")
        and ten not in MIEN and o.__module__ == v.__name__
    }
    assert viec, "không tìm thấy hàm việc nào — phép kiểm có thể đã mục"

    chua_noi = sorted(t for t in viec if not re.search(rf"\b{t}\(", than_loop))
    assert not chua_noi, (
        f"Hàm {chua_noi} có trong module nhưng vòng nền KHÔNG gọi. "
        "Mã chết đội lốt tính năng: repo thì có, hệ thống chạy thì không."
    )


def test_kho_don_co_du_phuong_thuc_cho_moi_viec():
    # Nối vào vòng nền mà thiếu phương thức đọc/ghi thì nó nổ lúc chạy thật,
    # ở một vòng nền không ai nhìn.
    from agent.erp.vong_dong_bo import PostgresKhoDon

    for ten in ("don_cho_dong_bo", "danh_dau_da_day", "danh_dau_that_bai",
                "danh_dau_bo_cuoc", "don_da_day", "ghi_trang_thai_giao"):
        assert hasattr(PostgresKhoDon, ten), f"PostgresKhoDon thiếu {ten}()"


def test_khong_dung_cot_da_bi_xoa():
    """`trang_thai_giao` đã bị migration 0007 xoá, thay bằng
    `trang_thai_giao_hang`.

    ĐÃ XẢY RA THẬT: bản đầu của `don_da_day()` đọc tên cột cũ. Câu SQL đó
    chỉ nổ lúc CHẠY, trong một vòng nền không ai nhìn — không test nào bắt
    được vì test không chạm CSDL.
    """
    import re
    from pathlib import Path

    ma = (Path(__file__).resolve().parent.parent / "agent" / "erp"
          / "vong_dong_bo.py").read_text(encoding="utf-8")

    # Chỉ soi DÒNG SQL. Chữ `trang_thai_giao` trong docstring và trong khoá
    # dict (`don.get("trang_thai_giao")` — bí danh SELECT trả về) đều hợp lệ.
    # Bản đầu của test này đếm trên cả file nên đỏ khi mã đã đúng.
    SQL = re.compile(r"\b(SELECT|UPDATE|WHERE|FROM|SET|AND|OR|IN)\b")
    xau = []
    for dong in ma.splitlines():
        if not SQL.search(dong):
            continue
        # Bỏ `AS trang_thai_giao` — đó là bí danh, không phải tên cột.
        con_lai = re.sub(r"AS\s+trang_thai_giao\b", "", dong)
        if re.search(r"\btrang_thai_giao\b(?!_hang)", con_lai):
            xau.append(dong.strip()[:80])

    assert not xau, (
        "Câu SQL đang dùng cột `trang_thai_giao` — cột này KHÔNG còn tồn "
        "tại. Migration 0007 đổi sang `trang_thai_giao_hang`.\n"
        + "\n".join(xau)
    )


def test_chi_dung_gia_tri_thuoc_bo_trang_thai_noi_bo():
    # Migration 0007 cũng đổi từ vựng: tiếng Việt -> giá trị
    # InternalShippingStatus. Lọc bằng từ cũ là lọc trượt mọi đơn.
    from pathlib import Path

    from agent.shipping.models import InternalShippingStatus

    ma = (Path(__file__).resolve().parent.parent / "agent" / "erp"
          / "vong_dong_bo.py").read_text(encoding="utf-8")
    for tu_cu in ("'da_giao'", "'hoan_ve'", "'dang_giao'", "'giao_that_bai'"):
        assert tu_cu not in ma, (
            f"{tu_cu} là từ vựng CŨ trước migration 0007. Bộ hiện tại là "
            f"{[s.value for s in InternalShippingStatus]}"
        )
