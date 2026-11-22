"""
`docs/yeu-cau-chuc-nang.md` phải khớp bộ sinh, và mọi thứ nó nêu tên phải có thật.

Bảng này là phụ lục khoá luận: người đọc tin dòng "Đạt — test X canh". Nếu X
đã bị đổi tên, bảng vẫn in "Đạt" — xanh giả. Bộ sinh kiểm từng tham chiếu và
NỔ khi thiếu; các test dưới đây canh (1) tài liệu không cũ, (2) bộ kiểm thật
sự bắt được tham chiếu chết, (3) trạng thái mục không gõ tay được.

Không cần CSDL, không gọi model.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import sinh_bang_yeu_cau as sb  # noqa: E402


def test_tai_lieu_khop_ban_sinh():
    """Đổi test, route, tab hay quyền mà quên sinh lại là bảng bắt đầu nói dối."""
    assert sb.TEP_DOC.exists(), "chưa có: python -m scripts.sinh_bang_yeu_cau --ghi"
    assert sb.TEP_DOC.read_text(encoding="utf-8") == sb.dung_tai_lieu(), (
        "docs/yeu-cau-chuc-nang.md đã cũ — chạy lại: python -m scripts.sinh_bang_yeu_cau --ghi")


def test_moi_tham_chieu_ton_tai():
    loi = (sb.kiem_muc(sb.MUC) + sb.kiem_phi_chuc_nang(sb.PHI_CHUC_NANG)
           + sb.kiem_han_che(sb.HAN_CHE))
    assert not loi, "\n".join(loi)


def test_khong_co_route_bi_cam():
    """Bảng ghi "không xoá nhân viên, chỉ khoá" — route xoá xuất hiện là bảng sai."""
    assert not sb.kiem_khong_co_route(sb.ROUTE_CAM)
    # Phép kiểm phải bắt được route có thật — không thì nó xanh với mọi thứ.
    assert sb.kiem_khong_co_route((("DELETE", "/api/vai-tro"),))


def test_bo_kiem_bat_duoc_tham_chieu_chet():
    """Bộ kiểm luôn trả rỗng là bộ kiểm vô dụng — đúng kiểu xanh giả."""
    hong = sb.Muc(
        99, "giả", (
            sb.YeuCau("đạt mà không có test", sb.DAT),
            sb.YeuCau("test không có", sb.DAT, ("tests/test_cay_menu.py::test_khong_he_co",)),
            sb.YeuCau("tệp không có", sb.DAT, ("tests/test_khong_he_co.py::test_a",)),
            sb.YeuCau("trạng thái lạ", "xong"),
        ),
        ma=("agent/khong_he_co.py",),
        api=("GET /api/khong-he-co",),
        giao_dien=("tab:khong-he-co", "nut:sai-loai"),
        nghiem_thu=("test_99_khong_he_co",),
    )
    loi = "\n".join(sb.kiem_muc([hong]))
    for mau in ("không nêu test canh", "test_khong_he_co", "test_khong_he_co.py",
                "trạng thái lạ", "agent/khong_he_co.py", "/api/khong-he-co",
                "khong-he-co", "nut:sai-loai", "test_99_khong_he_co"):
        assert mau in loi, f"bộ kiểm không bắt: {mau}"
    with pytest.raises(sb.LoiThamChieu):
        sb.dung_tai_lieu(cac_muc=(hong,))
    pcn = sb.kiem_phi_chuc_nang([sb.PhiChucNang("x", "y", "z", sb.DAT)])
    assert pcn and "không nêu test canh" in pcn[0]
    assert sb.kiem_han_che([sb.HanChe("x", "y", ("docs/khong-he-co.md",))])
    # Hạn chế đã được sửa trong mã mà bảng vẫn kể là bảng chê oan.
    assert sb.kiem_han_che([sb.HanChe("x", "y", con_dung=lambda: False)])
    assert not sb.kiem_han_che([sb.HanChe("x", "y", con_dung=lambda: True)])


def test_trang_thai_muc_suy_tu_yeu_cau_con():
    t = "tests/test_cay_menu.py::test_nut_quay_lai_hai_buoc"

    def muc(*tt):
        return sb.Muc(1, "x", tuple(sb.YeuCau(str(i), s, (t,)) for i, s in enumerate(tt)))

    assert sb.trang_thai_muc(muc(sb.DAT, sb.DAT)) == sb.DAT
    assert sb.trang_thai_muc(muc(sb.DAT, sb.NGOAI)) == sb.DAT, "ngoài phạm vi không kéo mục xuống"
    assert sb.trang_thai_muc(muc(sb.DAT, sb.MOT_PHAN)) == sb.MOT_PHAN
    assert sb.trang_thai_muc(muc(sb.DAT, sb.CHUA)) == sb.MOT_PHAN
    assert sb.trang_thai_muc(muc(sb.CHUA, sb.CHUA)) == sb.CHUA
    assert sb.trang_thai_muc(muc(sb.NGOAI)) == sb.NGOAI


def test_nghiem_thu_khong_dat_thi_muc_khong_dat(monkeypatch):
    t = "tests/test_cay_menu.py::test_nut_quay_lai_hai_buoc"
    m = sb.Muc(1, "x", (sb.YeuCau("a", sb.DAT, (t,)),), nghiem_thu=("test_01_x",))
    monkeypatch.setattr(sb, "ket_qua_nghiem_thu", lambda: {"test_01_x": (1, "x", "KHÔNG ĐẠT")})
    assert sb.trang_thai_muc(m) == sb.MOT_PHAN
    monkeypatch.setattr(sb, "ket_qua_nghiem_thu", lambda: {"test_01_x": (1, "x", "đạt")})
    assert sb.trang_thai_muc(m) == sb.DAT


def test_bang_phu_du_moi_muc_cua_phieu_viec():
    """Bảng có mục 1–21, không có mục 11 — thiếu một mục là phụ lục sót việc."""
    assert [m.so for m in sb.MUC] == [*range(1, 11), *range(12, 22)]


def test_doc_nghiem_thu_that():
    """Bộ đọc `docs/nghiem-thu.md` là regex — đổi khuôn bảng thì nó trả rỗng IM LẶNG."""
    khai = re.findall(r"^def (test_\d+_\w+)\(",
                      (ROOT / sb.TEP_TEST_NGHIEM_THU).read_text(encoding="utf-8"), re.M)
    assert khai and set(sb.ket_qua_nghiem_thu()) == set(khai)


def test_dem_test_doc_ca_async_va_lop():
    ten = sb.ham_test("tests/test_bang_yeu_cau.py")
    assert "test_tai_lieu_khop_ban_sinh" in ten
    assert sb.ham_test("tests/khong_he_co.py") == frozenset()
