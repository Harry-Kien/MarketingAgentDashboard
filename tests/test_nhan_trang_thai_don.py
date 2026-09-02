"""Dashboard phải biết TÊN mọi trạng thái đơn mà backend có thể ghi ra.

VÌ SAO TEST NÀY TỒN TẠI
-----------------------
`dashboard/app.js` tra nhãn bằng `ORDER_LABEL[trang_thai] || trang_thai`.
Cái `||` đó là một đường lui IM LẶNG: thiếu nhãn thì dòng đơn hiện ra chữ
kỹ thuật trần — `cho_dong_bo` — với thẻ màu xám trung tính, và người trực
không hiểu mình đang nhìn cái gì.

Đã xảy ra thật: thêm trạng thái `cho_dong_bo` ở backend mà quên dashboard.
Đơn đó là đơn khách ĐÃ ĐƯỢC HỨA sẽ có người gọi, nhưng nó hiện ra như một
dòng bình thường, cờ xanh, lẫn vào đám đơn đã xong.

Không có test này thì lần thêm trạng thái sau cũng vậy, và cũng không ai
biết cho tới khi một khách bị bỏ quên.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from agent.core.tools import TRANG_THAI_DON

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "dashboard" / "app.js"


def _khoa(ten_bien: str) -> set[str]:
    """Các khoá của một object literal trong app.js."""
    ma = APP_JS.read_text(encoding="utf-8")
    m = re.search(rf"const {ten_bien}\s*=\s*\{{(.*?)\}};", ma, re.S)
    assert m, f"Không tìm thấy {ten_bien} trong dashboard/app.js"
    return set(re.findall(r"(\w+)\s*:", m.group(1)))


def test_moi_trang_thai_deu_co_nhan_tren_dashboard():
    thieu = sorted(set(TRANG_THAI_DON) - _khoa("ORDER_LABEL"))
    assert not thieu, (
        f"Trạng thái {thieu} có ở backend nhưng ORDER_LABEL trong "
        "dashboard/app.js chưa biết. Dòng đơn sẽ hiện chữ kỹ thuật trần."
    )


def test_moi_trang_thai_deu_co_mau_tren_dashboard():
    thieu = sorted(set(TRANG_THAI_DON) - _khoa("ORDER_TONE"))
    assert not thieu, (
        f"Trạng thái {thieu} chưa có màu trong ORDER_TONE — thẻ sẽ ra màu "
        "xám trung tính, không phân biệt được với trạng thái bình thường."
    )


def test_dashboard_khong_khai_trang_thai_ma_backend_khong_co():
    # Chiều ngược lại cũng đáng canh: nhãn cho một trạng thái đã bị xoá là
    # mã chết, và nó làm người đọc tưởng trạng thái đó còn tồn tại.
    thua = sorted(_khoa("ORDER_LABEL") - set(TRANG_THAI_DON))
    assert not thua, f"ORDER_LABEL khai trạng thái backend không còn: {thua}"


def test_cho_dong_bo_duoc_hien_nhu_viec_can_chu_y():
    # Không đủ nếu chỉ có nhãn. Đơn `cho_dong_bo` là đơn khách đã được hứa
    # sẽ có người gọi — nó phải nổi lên, không được mang cờ "auto" như đơn
    # đã xong.
    ma = APP_JS.read_text(encoding="utf-8")
    assert "cho_dong_bo" in ma
    assert re.search(r"cho_duyet \|\| cho_dong_bo", ma), (
        "Đơn cho_dong_bo phải mang cờ 'assist' như đơn chờ duyệt"
    )
    assert "Chưa vào được kho/ERP" in ma, (
        "Phải nói lý do ngay trên dòng đơn — người trực làm việc ở màn hình "
        "này, không đọc nhật ký"
    )


def test_trang_thai_don_khop_voi_thu_backend_that_su_ghi():
    """Quét các câu `UPDATE orders SET trang_thai='...'` trong mã.

    Chỉ bảng `orders`. Bản đầu của test này quét mọi cột tên `trang_thai`
    và đỏ vì bắt luôn trạng thái của bảng `posts` (`da_dang`, `da_len_lich`)
    và của giao hàng (`da_giao`) — ba bộ trạng thái khác nhau, tình cờ trùng
    tên cột.
    """
    ma = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (ROOT / "agent").rglob("*.py")
    )
    thay: set[str] = set()
    for cau in re.findall(r"UPDATE orders SET(.{0,400}?)WHERE", ma, re.S):
        thay |= set(re.findall(r"trang_thai\s*=\s*'(\w+)'", cau))
        thay |= set(re.findall(r'trang_thai\s*=\s*"(\w+)"', cau))

    assert thay, "Không quét được câu UPDATE orders nào — regex có thể đã mục"
    la = sorted(thay - set(TRANG_THAI_DON))
    assert not la, (
        f"Mã đang ghi trạng thái đơn {la} mà TRANG_THAI_DON không khai. "
        "Dashboard sẽ không có nhãn cho chúng."
    )


def test_json_doc_duoc_app_js_khong_co_loi_cu_phap_object():
    # Phép kiểm rẻ: hai object literal phải parse được sau khi thêm khoá.
    for ten in ("ORDER_LABEL", "ORDER_TONE"):
        assert _khoa(ten), f"{ten} rỗng — có thể vừa hỏng cú pháp"
    assert json.dumps(sorted(TRANG_THAI_DON))


# =====================================================================
#  Thanh lọc đơn phải lọc được mọi trạng thái
# =====================================================================

def test_moi_trang_thai_deu_loc_duoc_tren_dashboard():
    """Thanh chip lọc đơn phải có đủ mọi trạng thái.

    Thiếu một chip thì người trực KHÔNG CÓ CÁCH NÀO xem riêng nhóm đơn đó.
    Đã xảy ra với `cho_dong_bo` — đúng nhóm cần chú ý nhất, vì khách đã được
    hứa sẽ có người gọi.

    `all` không tính: nó lọc tất cả, không phải một trạng thái.
    """
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    co = set(re.findall(r'data-ostatus="(\w+)"', html)) - {"all"}
    thieu = sorted(set(TRANG_THAI_DON) - co)
    assert not thieu, (
        f"Thanh lọc đơn thiếu chip cho {thieu}. Người trực không xem riêng "
        "được nhóm đơn đó."
    )


def test_khong_co_chip_loc_cho_trang_thai_khong_ton_tai():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    co = set(re.findall(r'data-ostatus="(\w+)"', html)) - {"all"}
    thua = sorted(co - set(TRANG_THAI_DON))
    assert not thua, f"Chip lọc cho trạng thái backend không có: {thua}"
