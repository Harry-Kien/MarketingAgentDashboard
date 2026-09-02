"""
MỌI vai tin nhắn phải có kiểu hiển thị — thiếu một vai là đọc ngược hội thoại.

LỖI NGƯỜI DÙNG BÁO
------------------
Tin báo mã vận đơn do HỆ THỐNG gửi cho khách, nhưng nó hiện BÊN TRÁI với nền
trắng — đúng chỗ và đúng kiểu của tin KHÁCH GỬI VÀO.

Người trực nhìn vào tưởng khách vừa nhắn cho mình một đoạn về mã vận đơn.

NGUYÊN NHÂN
-----------
Bốn vai có thật trong CSDL — customer, staff, agent, system — nhưng CSS chỉ
tạo kiểu cho ba:

    .msg--customer          { align-self: flex-start; }
    .msg--agent, .msg--staff { align-self: flex-end; }

`.msg--system` không có dòng nào, nên nó rơi về mặc định: canh trái, không
màu nền.

Vai `system` mới chỉ xuất hiện hôm nay, khi tin báo vận đơn được chuyển sang
đi qua outbox. Trước đó nó gọi thẳng adapter nên KHÔNG vào bảng `messages` —
và không vào bảng thì không ai thấy nó hiển thị sai.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")

# Bốn vai hệ thống thật sự sinh ra. `customer` từ webhook; ba vai còn lại
# `OutboundService` cho phép — xem `_ensure_role_allowed`.
VAI = ("customer", "agent", "staff", "system")


def test_moi_vai_deu_co_kieu_rieng():
    for vai in VAI:
        assert f".msg--{vai}" in CSS, (
            f"vai `{vai}` không có kiểu — nó sẽ rơi về mặc định canh trái"
        )


def test_ba_vai_di_RA_deu_canh_phai():
    """
    `agent`, `staff`, `system` đều là tin shop gửi cho khách. Chỉ `customer`
    là tin đi vào.
    """
    khoi = CSS.split("align-self: flex-end", 1)[0][-400:]
    for vai in ("agent", "staff", "system"):
        assert f".msg--{vai}" in khoi, f"`{vai}` không nằm trong nhóm canh phải"


def test_customer_canh_trai():
    khoi = CSS.split(".msg--customer {", 1)[1].split("}", 1)[0]
    assert "flex-start" in khoi


def test_ba_vai_di_ra_phan_biet_duoc_voi_nhau():
    """
    Người trực quét mắt cần phân biệt ba thứ: AI soạn (cần để mắt), người gõ
    (đã có người lo), máy báo (không cần ai làm gì). Cùng một màu cho cả ba
    là mất thông tin đó.
    """
    kieu = {}
    for vai in ("agent", "staff", "system"):
        moc = f".msg--{vai} .msg__bubble"
        assert moc in CSS, f"`{vai}` chưa có kiểu bong bóng riêng"
        kieu[vai] = CSS.split(moc, 1)[1].split("}", 1)[0]
    assert len(set(kieu.values())) == 3, "ba vai đi ra đang trông giống hệt nhau"


def test_anh_cua_vai_di_ra_cung_bo_goc_nhu_bong_bong():
    khoi = CSS.split(".msg__anh img", 1)[1]
    for vai in ("agent", "staff", "system"):
        assert f".msg--{vai} .msg__anh img" in khoi


def test_nhan_hien_thi_phu_du_bon_vai():
    """Thiếu nhãn thì khung chat hiện thẳng chuỗi thô `system`."""
    khoi = JS.split("const who =", 1)[1].split("}", 1)[0]
    for vai in VAI:
        assert vai in khoi, f"thiếu nhãn tiếng Việt cho vai `{vai}`"
