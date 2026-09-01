"""
Khách xin ĐỔI hoặc TRẢ hàng sau khi đã nhận.

Đã có `xin_huy_don` cho giai đoạn TRƯỚC giao. Sau giao thì trước đây không
có gì: kho tài liệu mô tả chính sách đổi trả rất kỹ nên agent NÓI về nó rất
tốt, nhưng không chỗ nào GHI NHẬN yêu cầu — mọi ca rơi vào một dòng lý do
văn xuôi, không đếm được và không hiện lên màn hình Đơn hàng.

Với đổi trả, hậu quả cụ thể hơn xin huỷ: chính sách có hạn số ngày. Yêu cầu
nằm im ba hôm rồi mới có người đọc là khách mất quyền vì lý do không phải
của họ.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core import tools  # noqa: E402


@pytest.fixture
def csdl_gia(monkeypatch):
    """Bắt lại lời gọi CSDL — không cần Postgres để chạy test này."""
    da_goi: dict = {"update": [], "log": []}

    async def _fetchrow(sql, *args):
        da_goi["update"].append((sql, args))
        return {"ma_don": args[0]} if da_goi.get("_tim_thay", True) else None

    async def _log(kind, **chi_tiet):
        da_goi["log"].append((kind, chi_tiet))

    monkeypatch.setattr(tools.db, "fetchrow", _fetchrow)
    monkeypatch.setattr(tools.db, "log_event", _log)
    return da_goi


def _chay(**args) -> dict:
    return asyncio.run(tools.run_tool("xin_doi_tra", args, "conv-1"))


# =====================================================================
#  Khai báo công cụ
# =====================================================================

def test_cong_cu_co_trong_danh_sach_va_bat_buoc_khai_loai():
    tool = next(t for t in tools.TOOLS if t["name"] == "xin_doi_tra")
    assert set(tool["input_schema"]["required"]) == {"ma_don", "loai"}
    assert tool["input_schema"]["properties"]["loai"]["enum"] == ["doi", "tra"]


def test_mo_ta_cam_noi_da_duyet():
    """
    Cùng bài học với `xin_huy_don`: nói "đã huỷ" khi đơn chưa huỷ là hệ
    thống nói dối thay mặt doanh nghiệp. Đổi trả cũng vậy.
    """
    tool = next(t for t in tools.TOOLS if t["name"] == "xin_doi_tra")
    mo_ta = tool["description"]
    assert "KHÔNG DUYỆT" in mo_ta
    assert "đã hoàn tiền" in mo_ta
    assert "chuyen_nhan_vien" in mo_ta   # ca kích ứng da đi đường y tế


# =====================================================================
#  Ghi nhận
# =====================================================================

def test_ghi_nhan_len_don_va_khong_dung_toi_trang_thai(csdl_gia):
    kq = _chay(ma_don="DH-1", loai="doi", ly_do="size chật")

    sql = csdl_gia["update"][0][0]
    assert "yeu_cau_doi_tra_loai" in sql
    # Duyệt đổi trả là việc của người — trộn vào `trang_thai` là sớm muộn
    # có người sửa nhầm thành "đã xong".
    assert "SET trang_thai" not in sql
    assert kq["da_ghi_nhan"] is True
    assert kq["da_duyet"] is False


def test_chan_theo_hoi_thoai_vi_ma_don_doan_duoc(csdl_gia):
    """Không chặn thì bất kỳ ai cũng gắn cờ lên đơn của người lạ."""
    _chay(ma_don="DH-1", loai="tra")

    sql, args = csdl_gia["update"][0]
    assert "conversation_id = $2" in sql
    assert args[1] == "conv-1"


def test_khong_dung_co_tren_don_da_huy(csdl_gia):
    _chay(ma_don="DH-1", loai="tra")
    assert "trang_thai <> 'da_huy'" in csdl_gia["update"][0][0]


def test_ghi_nhat_ky_de_dem_duoc(csdl_gia):
    """
    Không ghi nhật ký thì không thống kê được tỉ lệ đổi trả — và đó là chỉ
    số nói lên chất lượng tư vấn size lẫn chất lượng hàng.
    """
    _chay(ma_don="DH-1", loai="doi", ly_do="không hợp da")

    kind, chi_tiet = csdl_gia["log"][0]
    assert kind == "order.xin_doi_tra"
    assert chi_tiet["loai"] == "doi"
    assert chi_tiet["ma_don"] == "DH-1"


# =====================================================================
#  Không đoán thay khách
# =====================================================================

@pytest.mark.parametrize("loai", ["", "Đổi", "hoan_tien", "doi_tra", None])
def test_loai_khong_ro_thi_hoi_lai_chu_khong_doan(loai, csdl_gia):
    """
    Đoán sai giữa ĐỔI và TRẢ là gửi người xử lý đi làm nhầm việc: một bên
    cần kiểm tồn kho, một bên cần duyệt hoàn tiền.
    """
    kq = _chay(ma_don="DH-1", loai=loai)

    assert kq["da_ghi_nhan"] is False
    assert csdl_gia["update"] == []       # không đụng CSDL
    assert "Hỏi khách" in kq["ghi_chu"]


def test_khong_tim_thay_don_thi_van_chuyen_nguoi(csdl_gia):
    """
    Khách vẫn đang muốn đổi trả một cái gì đó. Im lặng bỏ qua là bỏ rơi họ
    ở đúng lúc đã không hài lòng sẵn.
    """
    csdl_gia["_tim_thay"] = False

    kq = _chay(ma_don="KHONG-CO", loai="tra")

    assert kq["da_ghi_nhan"] is False
    assert kq["can_chuyen_nhan_vien"] is True
    assert "không hứa gì về đổi trả" in kq["ghi_chu"]


def test_ghi_chu_cam_ket_luan_don_du_dieu_kien(csdl_gia):
    kq = _chay(ma_don="DH-1", loai="tra", ly_do="không ưng")

    assert "KHÔNG nói với khách là 'đã được đổi'" in kq["ghi_chu"]
    assert "không được kết luận" in kq["ghi_chu"]


# =====================================================================
#  Migration
# =====================================================================

def test_migration_rang_hai_gia_tri_hop_le():
    """
    Cột tự do thì sáu tháng nữa nó chứa 'doi', 'Đổi', 'DOI', 'đổi hàng' —
    và mọi truy vấn thống kê đều sai mà không ai biết.
    """
    sql = (ROOT / "agent" / "migrations" / "versions"
           / "0009_yeu_cau_doi_tra.sql").read_text(encoding="utf-8")
    assert "IN ('doi', 'tra')" in sql
    assert "idx_order_xin_doi_tra" in sql
