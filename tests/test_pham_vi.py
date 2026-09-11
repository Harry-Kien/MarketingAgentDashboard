"""
Lớp phạm vi: "nhân viên này được thấy khách nào".

ĐÂY LÀ RÀNG BUỘC TRUNG TÂM CỦA CẢ KHỐI A, và nó sống trong một mệnh đề
WHERE. Sai theo hướng lỏng thì nhân viên thấy khách không phải của mình —
và không có gì hỏng để ai nhận ra. Sai theo hướng chặt thì họ mất sạch
khách, và triệu chứng là "dashboard trống", không phải một lỗi.

Hai tầng test, cố ý chồng nhau:
  ĐƠN VỊ (file này, luôn chạy)  — khẳng định trên chuỗi SQL sinh ra
  TÍCH HỢP (test_pham_vi_that)  — chạy thật trên Postgres

Tầng đơn vị bắt lỗi soạn mệnh đề. Tầng tích hợp bắt thứ chỉ Postgres mới
biết. Bỏ tầng nào cũng để lọt một loại lỗi.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.core import pham_vi  # noqa: E402

NV_ID = "11111111-1111-1111-1111-111111111111"
NV = {"id": NV_ID, "quyen": frozenset({"khach.doc"})}
SEP = {"id": "22222222-2222-2222-2222-222222222222",
       "quyen": frozenset({"khach.doc", "khach.xem_tat_ca"})}


def test_bon_muc_va_dung_bon():
    """
    Thêm mức thứ năm mà quên xử lý nó ở `dieu_kien_khach` là mức ấy rơi vào
    nhánh mặc định — và nhánh mặc định của một hàm lọc quyền phải là nhánh
    CHẶT nhất, không phải nhánh tiện nhất.
    """
    assert pham_vi.MUC_TAM_NHIN == ("tat", "an_noi_dung", "chi_doc", "an")


def test_muc_mac_dinh_la_tat():
    """
    Bật một tính năng phân quyền mà đổi ngay quyền của mọi người đang làm
    việc là cách tạo sự cố: sáng hôm sau nhân viên mở dashboard thấy trống
    và không ai hiểu vì sao. Quản trị bật khi đã giao khách xong.
    """
    assert pham_vi.MUC_MAC_DINH == "tat"


def test_muc_tat_khong_them_dieu_kien_nao():
    sql, ts = pham_vi.dieu_kien_khach(nguoi=NV, muc="tat", so_tham_so=0)
    assert sql.strip() == "TRUE"
    assert ts == []


@pytest.mark.parametrize("muc", ["an_noi_dung", "chi_doc"])
def test_hai_muc_giua_khong_loc_danh_sach(muc):
    """
    `an_noi_dung` và `chi_doc` vẫn cho THẤY khách của người khác — chúng chỉ
    đổi hai cờ (đọc được nội dung không, trả lời được không).

    Lọc luôn danh sách ở hai mức này là biến chúng thành `an`, và ba lựa
    chọn trên màn Cấu hình thành hai — người quản trị chọn một thứ rồi nhận
    một thứ khác.
    """
    sql, ts = pham_vi.dieu_kien_khach(nguoi=NV, muc=muc, so_tham_so=0)
    assert sql.strip() == "TRUE"
    assert ts == []


def test_muc_an_loc_theo_chu_va_van_cho_khach_vo_chu():
    """
    Khách chưa giao là CỦA CHUNG — chủ dự án đã chọn vậy.

    Bỏ vế `owner_user_id IS NULL` là khách mới nhắn tới thành vô hình với
    tất cả mọi người: không lỗi, không nhật ký, khách ngồi chờ tới khi có
    người tình cờ mở đúng hội thoại.
    """
    sql, ts = pham_vi.dieu_kien_khach(nguoi=NV, muc="an", so_tham_so=2)
    assert "owner_user_id IS NULL" in sql
    assert "$3" in sql, "phải tiếp đúng sau số tham số đã dùng"
    assert ts == [NV_ID]


def test_bi_danh_bang_doi_theo_truy_van_goi_toi():
    """
    Truy vấn sẵn có đặt tên bảng khác nhau (`contact` ở `list_visible`).
    Gắn cứng `contacts.` là mệnh đề ném `missing FROM-clause entry` — may
    là nổ to. Nhưng truy vấn nào tình cờ có CẢ bảng `contacts` lẫn một bí
    danh khác thì nó lọc nhầm bảng, và cái đó không nổ.
    """
    sql, _ = pham_vi.dieu_kien_khach(
        nguoi=NV, muc="an", so_tham_so=0, bi_danh="contact")
    assert "contact.owner_user_id" in sql
    assert "contacts.owner_user_id" not in sql


def test_tham_so_danh_so_tiep_dung_cho():
    """
    Truy vấn gọi tới đã dùng sẵn vài tham số. Đánh số lại từ `$1` là ghi đè
    tham số của người gọi — và Postgres không báo gì, nó chỉ so nhầm cột.
    """
    for da_dung in (0, 1, 5):
        sql, _ = pham_vi.dieu_kien_khach(nguoi=NV, muc="an", so_tham_so=da_dung)
        assert f"${da_dung + 1}" in sql


def test_nguoi_co_xem_tat_ca_thi_khong_muc_nao_loc():
    for muc in pham_vi.MUC_TAM_NHIN:
        sql, ts = pham_vi.dieu_kien_khach(nguoi=SEP, muc=muc, so_tham_so=0)
        assert sql.strip() == "TRUE", muc
        assert ts == []


def test_muc_la_thi_nem_chu_khong_tra_TRUE():
    """
    Mức lạ trả `TRUE` là mở toang danh bạ vì một lỗi gõ trong cấu hình — và
    mở toang thì không có gì hỏng để ai đi kiểm.
    """
    with pytest.raises(ValueError):
        pham_vi.dieu_kien_khach(nguoi=NV, muc="khong_co_that", so_tham_so=0)


# --- hai cờ ---------------------------------------------------------

def test_duoc_tra_loi_theo_tung_muc():
    cua_toi = {"owner_user_id": NV_ID}
    cua_nguoi_khac = {"owner_user_id": "99999999-9999-9999-9999-999999999999"}
    vo_chu = {"owner_user_id": None}

    assert pham_vi.duoc_tra_loi(NV, cua_nguoi_khac, muc="tat")
    assert not pham_vi.duoc_tra_loi(NV, cua_nguoi_khac, muc="chi_doc")
    assert not pham_vi.duoc_tra_loi(NV, cua_nguoi_khac, muc="an_noi_dung")

    for muc in pham_vi.MUC_TAM_NHIN:
        assert pham_vi.duoc_tra_loi(NV, cua_toi, muc=muc), muc
        assert pham_vi.duoc_tra_loi(NV, vo_chu, muc=muc), muc


def test_duoc_xem_noi_dung_chi_bi_chan_o_muc_an_noi_dung():
    cua_nguoi_khac = {"owner_user_id": "99999999-9999-9999-9999-999999999999"}
    assert pham_vi.duoc_xem_noi_dung(NV, cua_nguoi_khac, muc="tat")
    assert pham_vi.duoc_xem_noi_dung(NV, cua_nguoi_khac, muc="chi_doc")
    assert not pham_vi.duoc_xem_noi_dung(NV, cua_nguoi_khac, muc="an_noi_dung")


def test_hai_co_cung_nem_khi_muc_la():
    khach = {"owner_user_id": None}
    for ham in (pham_vi.duoc_tra_loi, pham_vi.duoc_xem_noi_dung):
        with pytest.raises(ValueError):
            ham(NV, khach, muc="khong_co_that")
