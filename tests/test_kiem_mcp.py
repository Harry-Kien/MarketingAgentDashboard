"""
`scripts/kiem_mcp.py` — chỉ phần THUẦN: so thiếu/thừa, chọn công cụ thử,
diễn giải dict thành Muc, mã thoát. Không mạng, không CSDL — dict giả vào
thẳng hàm, xem `tests/test_kho_mcp.py` cho phần chạm CSDL/mạng thật (giả).
"""
from __future__ import annotations

from scripts.kiem_mcp import (
    BO_QUA,
    DAT,
    HONG,
    Muc,
    chon_cong_cu_thu,
    dien_giai,
    ma_thoat,
    thieu_thua,
)


def _cong_cu(cong_cu_goc="tra_ton", *, bat=True, ghi=False, required=None, ten_model=None):
    return {
        "ten_model": ten_model or f"mcp_kho_{cong_cu_goc}",
        "cong_cu_goc": cong_cu_goc,
        "bat": bat,
        "ghi": ghi,
        "required": required or [],
    }


def _kq(
    *,
    loi_dia_chi=None,
    dia_chi_host="127.0.0.1:8765",
    noi_duoc=True,
    loi_ket_noi=None,
    cong_cu_may_chu=None,
    cong_cu_da_luu=None,
    bo=None,
):
    return {
        "dia_chi_host": dia_chi_host,
        "loi_dia_chi": loi_dia_chi,
        "noi_duoc": noi_duoc,
        "loi_ket_noi": loi_ket_noi,
        "cong_cu_may_chu": cong_cu_may_chu if cong_cu_may_chu is not None else ["tra_ton"],
        "cong_cu_da_luu": cong_cu_da_luu if cong_cu_da_luu is not None else [_cong_cu()],
        "bo_dong_bo_gan_nhat": bo or [],
    }


# ---------------------------------------------------------------------
#  thieu_thua
# ---------------------------------------------------------------------

def test_thieu_thua_khop_nguyen():
    thieu, thua = thieu_thua(["tra_ton", "ghi_don"], [_cong_cu("tra_ton"), _cong_cu("ghi_don")])
    assert thieu == [] and thua == []


def test_thieu_thua_may_chu_co_them_cong_cu_moi():
    # Máy chủ thêm "huy_don" mà chưa Đồng bộ lại — thiếu, không phải thừa.
    thieu, thua = thieu_thua(["tra_ton", "huy_don"], [_cong_cu("tra_ton")])
    assert thieu == ["huy_don"] and thua == []


def test_thieu_thua_da_luu_con_may_chu_da_bo():
    # Đã lưu "cu" nhưng máy chủ không còn khai nó nữa — thừa, sẽ tự dọn ở
    # lần Đồng bộ kế tiếp.
    thieu, thua = thieu_thua(["tra_ton"], [_cong_cu("tra_ton"), _cong_cu("cu")])
    assert thieu == [] and thua == ["cu"]


def test_thieu_thua_sap_xep_on_dinh():
    thieu, thua = thieu_thua(["b", "a"], [_cong_cu("y"), _cong_cu("x")])
    assert thieu == ["a", "b"] and thua == ["x", "y"]


# ---------------------------------------------------------------------
#  chon_cong_cu_thu
# ---------------------------------------------------------------------

def test_chon_cong_cu_thu_uu_tien_doc_dang_bat_khong_tham_so_bat_buoc():
    da_luu = [
        _cong_cu("ghi_don", ghi=True),  # bỏ: GHI
        _cong_cu("tat", bat=False),  # bỏ: đang tắt
        _cong_cu("can_tham_so", required=["ma"]),  # bỏ: có tham số bắt buộc
        _cong_cu("tra_ton"),  # đủ điều kiện
    ]
    chon = chon_cong_cu_thu(da_luu)
    assert chon is not None and chon["cong_cu_goc"] == "tra_ton"


def test_chon_cong_cu_thu_khong_co_ung_vien_tra_none():
    da_luu = [_cong_cu("ghi_don", ghi=True), _cong_cu("tat", bat=False)]
    assert chon_cong_cu_thu(da_luu) is None


def test_chon_cong_cu_thu_danh_sach_rong():
    assert chon_cong_cu_thu([]) is None


# ---------------------------------------------------------------------
#  dien_giai — diễn giải dict thuần thành Muc
# ---------------------------------------------------------------------

def test_dien_giai_dia_chi_bi_rao_thi_moi_muc_sau_bo_qua():
    kq = _kq(loi_dia_chi="host ngoài danh sách", noi_duoc=False, dia_chi_host=None)
    mucs = dien_giai(kq, None)
    theo_ten = {m.ten: m for m in mucs}
    assert theo_ten["Địa chỉ qua rào"].trang_thai == HONG
    assert theo_ten["Nối được máy chủ"].trang_thai == BO_QUA
    assert theo_ten["Công cụ: máy chủ so với đã lưu"].trang_thai == BO_QUA


def test_dien_giai_khong_noi_duoc_thi_cong_cu_bo_qua():
    kq = _kq(noi_duoc=False, loi_ket_noi="Máy chủ không trả lời trong 10s.")
    mucs = dien_giai(kq, None)
    theo_ten = {m.ten: m for m in mucs}
    assert theo_ten["Nối được máy chủ"].trang_thai == HONG
    assert "10s" in theo_ten["Nối được máy chủ"].chi_tiet
    assert theo_ten["Công cụ: máy chủ so với đã lưu"].trang_thai == BO_QUA


def test_dien_giai_thieu_thua_thi_hong_va_neu_ten():
    kq = _kq(cong_cu_may_chu=["tra_ton", "moi"], cong_cu_da_luu=[_cong_cu("tra_ton"), _cong_cu("cu")])
    mucs = dien_giai(kq, None)
    m = next(x for x in mucs if x.ten == "Công cụ: máy chủ so với đã lưu")
    assert m.trang_thai == HONG
    assert "moi" in m.chi_tiet and "cu" in m.chi_tiet


def test_dien_giai_khop_nguyen_thi_dat():
    kq = _kq()
    mucs = dien_giai(kq, None)
    m = next(x for x in mucs if x.ten == "Công cụ: máy chủ so với đã lưu")
    assert m.trang_thai == DAT


def test_dien_giai_bo_dong_bo_gan_nhat_hien_ly_do():
    kq = _kq(bo=[{"ten": "xau", "ly_do": "mô tả có câu ra lệnh"}])
    mucs = dien_giai(kq, None)
    m = next(x for x in mucs if x.ten == "Công cụ bị bỏ ở lần Đồng bộ gần nhất")
    assert m.trang_thai == HONG and "xau" in m.chi_tiet and "câu ra lệnh" in m.chi_tiet


def test_dien_giai_khong_co_ung_vien_thi_bo_qua():
    kq = _kq(cong_cu_da_luu=[_cong_cu("ghi_don", ghi=True)])
    mucs = dien_giai(kq, None)
    m = next(x for x in mucs if x.ten == "Gọi thử một công cụ ĐỌC")
    assert m.trang_thai == BO_QUA


def test_dien_giai_goi_thanh_cong_thi_dat():
    kq = _kq()
    mucs = dien_giai(kq, {"ket_qua": "ok", "du_lieu": None, "ghi_chu": "x"})
    m = next(x for x in mucs if x.ten.startswith("Gọi thử"))
    assert m.trang_thai == DAT


def test_dien_giai_goi_loi_thi_hong():
    kq = _kq()
    mucs = dien_giai(kq, {"loi": "Máy chủ báo lỗi: hết hàng", "can_chuyen_nhan_vien": True})
    m = next(x for x in mucs if x.ten.startswith("Gọi thử"))
    assert m.trang_thai == HONG and "hết hàng" in m.chi_tiet


# ---------------------------------------------------------------------
#  ma_thoat
# ---------------------------------------------------------------------

def test_ma_thoat_khong_hong_thi_0():
    mucs = [Muc("a", DAT, ""), Muc("b", BO_QUA, "")]
    assert ma_thoat(mucs) == 0


def test_ma_thoat_co_hong_thi_1():
    mucs = [Muc("a", DAT, ""), Muc("b", HONG, "")]
    assert ma_thoat(mucs) == 1


def test_ma_thoat_danh_sach_rong_thi_0():
    assert ma_thoat([]) == 0
