"""Vòng làm mới 6 giây không được làm panel nhấp nháy, và không được đốt ERP.

HAI LỖI ĐƯỢC CANH Ở ĐÂY
-----------------------
1. **Nhấp nháy.** `refresh()` chạy mỗi 6 giây và gọi lại `loadHeThong()`.
   Hàm đó ghi `box.innerHTML = 'Đang hỏi từng dịch vụ…'` NGAY ĐẦU, tức là
   xoá trắng panel, rồi mới đi dò 5 dịch vụ. Người xem thấy nội dung biến
   mất rồi hiện lại, sáu giây một lần.

   Ô chờ chỉ có ý nghĩa khi NGƯỜI vừa bấm nút. Làm mới ngầm phải vẽ đè, im
   lặng.

2. **Đốt hạn mức ERP.** `loadKho()` cũng nằm trong vòng 6 giây, và nó gọi
   `loadErpCauHinh()` → `GET /erp/suc-khoe` → chạm vào ERP thật. Mở tab Kho
   rồi đi ăn trưa là 600 lượt gọi ERP mỗi giờ cho một dòng chữ gần như
   không đổi.

VÌ SAO TEST BẰNG CÁCH ĐỌC MÃ
----------------------------
Bộ test của dự án là pytest, và dựng cả trình duyệt để đếm số lần vẽ lại là
chi phí lớn hơn thứ nó canh. Đọc mã bắt được đúng hai khuôn đã gây lỗi:
gán ô chờ vô điều kiện, và gọi ERP không có phanh.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "dashboard" / "app.js"


def _ma() -> str:
    return APP_JS.read_text(encoding="utf-8")


def _than_ham(ten: str) -> str:
    """Thân của một `async function` cho tới hàm kế tiếp."""
    ma = _ma()
    i = ma.index(f"async function {ten}(")
    j = ma.find("\nasync function ", i + 1)
    k = ma.find("\nfunction ", i + 1)
    het = min(x for x in (j, k, len(ma)) if x > 0)
    return ma[i:het]


# --- 1. Không nhấp nháy ----------------------------------------------

def test_loadHeThong_khong_xoa_trang_panel_vo_dieu_kien():
    than = _than_ham("loadHeThong")
    assert "Đang hỏi từng dịch vụ" in than, "mất ô chờ — có thể vừa sửa nhầm"

    # Ô chờ phải nằm TRONG một khối điều kiện. Điều kiện thường ở dòng
    # TRƯỚC, nên soi mỗi dòng gán là soi sai chỗ — bản đầu của test này mắc
    # đúng lỗi đó và đỏ khi mã đã đúng.
    dong = than.splitlines()
    i = next(k for k, d in enumerate(dong) if "Đang hỏi từng dịch vụ" in d)
    truoc = " ".join(d.strip() for d in dong[max(0, i - 2):i + 1])
    assert "if (" in truoc, (
        "Ô chờ đang được gán vô điều kiện. Vòng làm mới 6 giây sẽ xoá trắng "
        "panel rồi vẽ lại — đó chính là nhấp nháy.\n"
        f"Ngữ cảnh: {truoc}"
    )


def test_loadHeThong_nhan_co_bao_dang_cho():
    # Người bấm nút thì thấy ô chờ (họ vừa yêu cầu, cần phản hồi ngay).
    # Vòng nền thì không.
    than = _than_ham("loadHeThong")
    assert re.search(r"async function loadHeThong\(\s*\w+", than), (
        "loadHeThong phải nhận cờ phân biệt 'người bấm' với 'vòng nền'"
    )


def test_nut_kiem_tra_van_hien_o_cho():
    ma = _ma()
    assert re.search(r'#hethongrun"\)\?\.addEventListener\("click",\s*\(\)\s*=>',
                     ma), (
        "Nút Kiểm tra phải gọi loadHeThong với cờ đang-chờ. Gán thẳng tên "
        "hàm thì tham số đầu là Event — dựa vào đó là dựa vào tình cờ."
    )


# --- 2. Không đốt hạn mức ERP ----------------------------------------

def test_loadErpCauHinh_co_phanh():
    than = _than_ham("loadErpCauHinh")
    assert "ERP_CAUHINH_MOI_MS" in than or "Date.now()" in than, (
        "loadErpCauHinh chạy trong vòng 6 giây và gọi thật vào ERP. Phải có "
        "phanh, nếu không mở tab Kho rồi đi ăn trưa là 600 lượt gọi mỗi giờ."
    )


def test_phanh_du_thua():
    ma = _ma()
    m = re.search(r"ERP_CAUHINH_MOI_MS\s*=\s*(\d+)", ma)
    assert m, "thiếu hằng số chu kỳ làm mới cấu hình ERP"
    assert int(m.group(1)) >= 30_000, (
        "Chu kỳ dưới 30 giây là vẫn đang đốt hạn mức ERP cho một dòng chữ "
        "gần như không đổi"
    )


def test_thu_ket_noi_van_lam_moi_ngay_lap_tuc():
    # Phanh không được làm người bấm "Thử kết nối" thấy dòng cấu hình cũ.
    ma = _ma()
    assert re.search(r"loadErpCauHinh\(\s*true\s*\)", ma), (
        "Sau khi Thử kết nối phải làm mới NGAY, bỏ qua phanh"
    )


# --- Cú pháp vẫn hợp lệ sau khi sửa ----------------------------------

def test_app_js_khong_hong_cu_phap():
    # Phép kiểm rẻ nhất bắt được lỗi đắt nhất: sửa JS làm hỏng cả dashboard
    # thì pytest không thấy gì, và người dùng nhận một trang trắng.
    ma = _ma()
    assert ma.count("{") == ma.count("}"), "ngoặc nhọn lệch"
    assert ma.count("(") == ma.count(")"), "ngoặc tròn lệch"
