"""
Màn Công việc phải dùng được HẾT những gì API cho phép.

LỖ HỔNG ĐÃ ĐO (15.09.2026)
--------------------------
`agent/api/cong_viec.py` cho: giao việc cho người khác (quyền
`cong_viec.giao`), đổi mức ưu tiên, đặt/xoá hạn, huỷ việc. Màn hình chỉ có
ba nút: Xong · Mở lại · Nhận.

Hệ quả: quyền `cong_viec.giao` nằm trong danh mục, cấp được cho vai trò,
nhưng KHÔNG cách nào dùng. Người trực chỉ tự nhận việc về mình được, không
đẩy sang đồng nghiệp được; trưởng ca muốn phân việc thì phải gọi điện bảo
nhau, và màn Công việc thành danh sách chỉ để đọc.

Đây là cùng một lớp lỗi với `manager` kênh ở màn Nhân sự, và với ba tính
năng "có endpoint mà không có màn hình" tìm ra trước đó: quyền có, cửa
không. Không có gì đỏ để ai nhận ra — mọi mảnh xét riêng đều đúng.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
API = (ROOT / "agent" / "api" / "cong_viec.py").read_text(encoding="utf-8")
SUA = JS[JS.index("async function cvMoSua"):JS.index("async function loadCongViec")]


def test_co_nut_sua_tren_tung_dong_viec():
    assert 'data-cvsua="${esc(v.id)}"' in JS
    assert 'e.target.closest("[data-cvsua]")' in JS


def test_sua_duoc_ca_bon_thu_API_cho_phep():
    for truong in ("uu_tien", "han", "trang_thai"):
        assert f'name: "{truong}"' in SUA, truong
    assert 'name: "nguoi_nhan"' in SUA


def test_o_chon_nguoi_chi_hien_khi_co_quyen_giao():
    """
    Hiện ô cho người không có quyền là dựng một cú bấm chắc chắn 403 — và
    dạy người dùng rằng thông báo lỗi là chuyện bình thường.
    """
    assert 'state.toiQuyen.has("cong_viec.giao")' in SUA
    assert 'state.toiQuyen.has("nguoi_dung.doc")' in SUA
    assert "if (nguoiChon)" in SUA


def test_xoa_han_va_thu_hoi_nguoi_nhan_gui_dung_co():
    """
    `SuaIn` phân biệt "không gửi" với "gửi rỗng" bằng hai cờ riêng. Gửi
    thiếu cờ thì để trống ô hạn không xoá được hạn, và người dùng tưởng
    màn hình hỏng.
    """
    assert "xoa_han = true" in SUA and "xoa_nguoi_nhan = true" in SUA
    assert "xoa_han: bool = False" in API and "xoa_nguoi_nhan: bool = False" in API


def test_han_tinh_theo_gio_may_nguoi_dung():
    """Hạn "ngày X" là hết ngày X, không phải 0h UTC (7h sáng giờ VN)."""
    assert 'new Date(d.han + "T23:59:59")' in SUA


def test_danh_sach_viec_duoc_giu_lai_de_mo_sua():
    """Không giữ thì nút Sửa phải gọi lại API chỉ để đọc một dòng đã có."""
    doan = JS[JS.index("async function loadCongViec"):]
    assert "congViec.ds = d.cong_viec;" in doan[:600]


def test_huy_viec_lam_duoc_tu_man_hinh():
    """`huy` là một trong bốn trạng thái; trước đây không nút nào đặt được nó."""
    from agent.core.cong_viec import TRANG_THAI

    assert "huy" in TRANG_THAI
    # Ô chọn trạng thái dựng từ danh mục máy chủ trả về, nên có đủ bốn mức.
    assert "congViec.trangThai.map" in SUA
