"""
URL callback hiện trên dashboard phải là địa chỉ CÔNG KHAI, không phải localhost.

LỖI ĐÃ XẢY RA
-------------
`connectionCallback()` dựng URL bằng `location.origin` — địa chỉ TRÌNH DUYỆT.
Người vận hành mở dashboard ở `http://127.0.0.1:8000`, nên thẻ tài khoản hiện

    http://127.0.0.1:8000/webhook/native/meta/<id>

Đó là địa chỉ Meta KHÔNG BAO GIỜ gọi vào được. Người dùng copy nguyên dòng
đó dán vào Meta, Meta báo lỗi xác minh, và không có gì nói ra rằng vấn đề
nằm ở `127.0.0.1`.

Chỉ MÁY CHỦ biết địa chỉ công khai (`PUBLIC_BASE_URL`); trình duyệt không.
Nên máy chủ phải nói cho dashboard biết.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _than_goc_cong_khai() -> str:
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    ham = re.search(r"function goc_cong_khai\(.*?\n}", js, re.S)
    assert ham, "không tìm thấy hàm dựng gốc địa chỉ công khai"
    return ham.group(0)


def test_overview_tra_ve_dia_chi_cong_khai():
    """Dashboard đã tải overview sẵn — gửi kèm ở đó, không cần thêm lượt gọi."""
    src = (ROOT / "agent" / "api" / "routes.py").read_text(encoding="utf-8")
    assert '"public_base_url"' in src, "overview phải trả về địa chỉ công khai"


def test_js_uu_tien_dia_chi_cong_khai_hon_location_origin():
    than = _than_goc_cong_khai()
    assert "PUBLIC_BASE" in than, "vẫn dựng URL thuần từ location.origin"
    # Thứ tự quan trọng: địa chỉ công khai phải đứng TRƯỚC trong biểu thức,
    # nếu không thì location.origin luôn thắng và bản vá thành vô nghĩa.
    assert than.index("PUBLIC_BASE") < than.index("location.origin")


def test_van_co_duong_lui_khi_chua_cau_hinh():
    """
    Chưa dựng tunnel thì `PUBLIC_BASE_URL` còn là localhost — lúc đó hiện
    `location.origin` vẫn đúng và vẫn dùng được để thử tại chỗ.
    """
    assert "location.origin" in _than_goc_cong_khai(), "cần đường lui"


def test_dashboard_co_nhan_gia_tri_tu_overview():
    """Máy chủ gửi rồi mà dashboard không đọc thì vẫn hiện localhost."""
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert "o.public_base_url" in js, "dashboard chưa đọc giá trị từ overview"


def test_callback_dung_ham_goc_chu_khong_dung_thang_location():
    """
    Sửa một chỗ mà bỏ sót chỗ kia thì vẫn hiện localhost ở nửa số thẻ.

    URL callback giờ dựng ở `callbackTheoKenh` — Meta chỉ nhận MỘT callback
    cho mỗi app, nên nó thuộc về KÊNH chứ không thuộc từng tài khoản.
    `connectionCallback` chỉ còn là lớp mỏng gọi vào đó.

    Canh cả hai hàm: ràng buộc chuyển chỗ thì test phải theo, nhưng không
    được nới lỏng.
    """
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")

    dung_goc = False
    for ten in ("callbackTheoKenh", "connectionCallback"):
        ham = re.search(r"function " + ten + r"\(.*?\n}", js, re.S)
        assert ham, f"không tìm thấy {ten}"
        than = ham.group(0)
        assert "location.origin" not in than, (
            f"{ten} vẫn dùng thẳng location.origin"
        )
        dung_goc = dung_goc or "goc_cong_khai()" in than

    assert dung_goc, "không hàm nào dựng URL từ goc_cong_khai()"
