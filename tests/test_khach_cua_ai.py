"""
Nhân viên đăng nhập vào phải biết NGAY khách nào là của mình.

VÌ SAO
------
Chủ dự án hỏi đúng câu này: "đăng nhập vào thì sao biết đâu là khách hàng
của mình, đâu là của người khác". Màn hình vốn đã hiện tên người phụ trách
trên mỗi dòng — nhưng khi người ấy là CHÍNH MÌNH thì nó cũng chỉ là một cái
tên, phải đọc rồi tự đối chiếu. Ở danh sách trăm khách thì không ai làm.

Ba trạng thái, ba màu, đọc được bằng cách liếc:

    của mình        xanh · "Bạn phụ trách"
    của người khác  xám  · tên người ấy
    chưa giao       vàng · "chưa có chủ" — của chung, ai cũng trả lời được

Và số ngay trên chip lọc: "Khách của tôi" rỗng trông hệt như bộ lọc hỏng.

Lưu ý ranh giới: đây là lớp NHÌN THẤY. Lớp chặn thật nằm ở máy chủ —
`account_memberships` (kênh) và mức tầm nhìn trong `agent/core/pham_vi.py`.
Bộ lọc chip chỉ thu hẹp thứ máy chủ đã cho phép thấy.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")


def test_khach_cua_minh_khac_mau_khong_chi_khac_ten():
    doan = JS[JS.index("function chuKhach"):JS.index("function chuKhach") + 1400]
    assert "contact.owner_user_id === state.toiId" in doan
    assert "pill--toi" in doan and "Bạn phụ trách" in doan
    # Thứ tự quan trọng: nhánh "của mình" phải đứng TRƯỚC nhánh hiện tên,
    # không thì khách của mình rơi vào nhánh chung và mất màu.
    assert doan.index("pill--toi") < doan.index("if (contact.owner_ho_ten")
    assert ".pill--toi {" in CSS


def test_ba_trang_thai_deu_co_nhan_rieng():
    doan = JS[JS.index("function chuKhach"):JS.index("function chuKhach") + 1400]
    assert "pill--warn" in doan and "chưa có chủ" in doan


def test_chip_loc_hien_so_luong():
    for loc in ("tat_ca", "cua_toi", "vo_chu"):
        assert f'data-chuloc="{loc}"' in HTML
    assert HTML.count('<b class="chip__dem"></b>') == 3
    assert ".chip__dem:empty { display: none; }" in CSS
    doan = JS[JS.index("async function loadContacts"):]
    doan = doan[:doan.index("\n}\n")]
    assert "demToi" in doan and "demVoChu" in doan


def test_loc_khach_cua_toi_so_voi_id_that():
    """`state.toiId` lấy từ /api/toi lúc đăng nhập; thiếu nó bộ lọc luôn rỗng."""
    assert "state.toiId = nguoi.id;" in JS
    doan = JS[JS.index("async function loadContacts"):]
    assert 'loc === "cua_toi" ? c.owner_user_id && c.owner_user_id === state.toiId' in doan[:900]


def test_man_hinh_noi_ro_loc_rong_nghia_la_gi():
    """Rỗng mà không có chữ thì người dùng tưởng hệ thống hỏng."""
    doan = JS[JS.index("async function loadContacts"):]
    doan = doan[:doan.index("\n}\n")]
    assert "Chưa có khách nào được giao cho bạn." in doan
    assert "Mọi khách trong phạm vi của bạn đều đã có người phụ trách." in doan
