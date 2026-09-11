"""
Công việc — lõi thuần, không cần CSDL.

Ràng buộc quan trọng nhất ở tầng này: việc đã xong thì KHÔNG quá hạn nữa.
Đếm chúng vào là con số quá hạn chỉ tăng và không bao giờ giảm — và một con
số chỉ tăng là con số người ta thôi nhìn sau tuần đầu.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.core import cong_viec as cv  # noqa: E402

BAY_GIO = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
HOM_QUA = BAY_GIO - timedelta(days=1)
NGAY_MAI = BAY_GIO + timedelta(days=1)

NV = {"id": "11111111-1111-1111-1111-111111111111",
      "quyen": frozenset({"cong_viec.doc"})}
SEP = {"id": "22222222-2222-2222-2222-222222222222",
       "quyen": frozenset({"cong_viec.doc", "cong_viec.xem_tat_ca"})}


def test_moi_trang_thai_va_uu_tien_deu_co_nhan_tieng_viet():
    assert set(cv.NHAN_TRANG_THAI) == set(cv.TRANG_THAI)
    assert set(cv.NHAN_UU_TIEN) == set(cv.UU_TIEN)


@pytest.mark.parametrize("tt", ["moi", "dang_lam", "xong", "huy"])
def test_trang_thai_hop_le(tt):
    assert cv.kiem_trang_thai(tt) == tt


def test_trang_thai_la_thi_nem():
    with pytest.raises(cv.CongViecHong) as loi:
        cv.kiem_trang_thai("dang_treo")
    assert "moi" in str(loi.value), "thông báo phải nói ra giá trị hợp lệ"


def test_uu_tien_la_thi_nem():
    with pytest.raises(cv.CongViecHong):
        cv.kiem_uu_tien("cuc_gap")


# --- quá hạn ---------------------------------------------------------

def test_qua_han_khi_chua_xong_va_han_da_qua():
    assert cv.qua_han({"han": HOM_QUA, "trang_thai": "moi"}, BAY_GIO)
    assert cv.qua_han({"han": HOM_QUA, "trang_thai": "dang_lam"}, BAY_GIO)


def test_viec_da_xong_KHONG_bao_gio_qua_han():
    """
    Con số quá hạn phải GIẢM được khi người ta làm xong việc. Không thì nó
    chỉ tăng, và một con số chỉ tăng là con số không ai nhìn nữa.
    """
    assert not cv.qua_han({"han": HOM_QUA, "trang_thai": "xong"}, BAY_GIO)
    assert not cv.qua_han({"han": HOM_QUA, "trang_thai": "huy"}, BAY_GIO)


def test_khong_han_thi_khong_qua_han():
    assert not cv.qua_han({"han": None, "trang_thai": "moi"}, BAY_GIO)


def test_han_chua_toi_thi_chua_qua():
    assert not cv.qua_han({"han": NGAY_MAI, "trang_thai": "moi"}, BAY_GIO)


def test_han_dang_chuoi_ISO_van_doc_duoc():
    """API trả hạn dạng chuỗi ISO; hàm này bị gọi cả trên bản đã tuần tự hoá."""
    assert cv.qua_han({"han": HOM_QUA.isoformat(), "trang_thai": "moi"}, BAY_GIO)


def test_han_khong_co_mui_gio_duoc_coi_la_UTC():
    """
    `datetime` ngây thơ so với `datetime` có múi giờ thì Python NÉM. Ném ở
    đây nghĩa là cả màn Công việc chết vì một dòng dữ liệu cũ.
    """
    ngay_tho = HOM_QUA.replace(tzinfo=None)
    assert cv.qua_han({"han": ngay_tho, "trang_thai": "moi"}, BAY_GIO)


# --- phạm vi ---------------------------------------------------------

def test_xem_tat_ca_thi_khong_loc():
    sql, ts = cv.dieu_kien_pham_vi(nguoi=SEP, so_tham_so=0)
    assert sql == "TRUE"
    assert ts == []


def test_nhan_vien_thay_viec_minh_nhan_minh_giao_va_viec_CHUA_GIAO():
    """
    Vế "chưa giao cho ai" là cốt lõi: việc do agent đẩy sang luôn ra đời ở
    trạng thái chưa giao. Bỏ vế ấy là cả khối này vô nghĩa — việc sinh ra
    rồi không ai thấy.
    """
    sql, ts = cv.dieu_kien_pham_vi(nguoi=NV, so_tham_so=0)
    assert "nguoi_nhan = $1" in sql
    assert "nguoi_giao = $1" in sql
    assert "nguoi_nhan IS NULL" in sql
    assert ts == [NV["id"]]


def test_tham_so_danh_so_tiep_dung_cho():
    sql, _ = cv.dieu_kien_pham_vi(nguoi=NV, so_tham_so=3)
    assert "$4" in sql
    assert "$1" not in sql


def test_bi_danh_bang_doi_theo_truy_van():
    sql, _ = cv.dieu_kien_pham_vi(nguoi=NV, so_tham_so=0, bi_danh="cv")
    assert "cv.nguoi_nhan" in sql
