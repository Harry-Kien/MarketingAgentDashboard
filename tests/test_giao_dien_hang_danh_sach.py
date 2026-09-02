"""
Dòng danh sách: ô đầu tiên phải vừa với thứ đặt vào nó.

LỖI ĐÃ CÓ THẬT — CHỮ BỊ ĐÈ
--------------------------
`.row` là lưới ba cột dùng chung cho hội thoại, đơn hàng và khách hàng:

    grid-template-columns: 3px minmax(0, 1fr) auto;

Cột đầu rộng **3px** vì nó sinh ra cho `.row__flag` — thanh màu trạng thái
mảnh chạy dọc mép trái.

Nhưng danh sách Khách hàng đặt `.avatar` vào đúng cột đó, và avatar rộng
**32px** kèm `flex: 0 0 auto` nên nó KHÔNG co lại. Nó tràn khỏi ô 3px và
nằm chồng lên tên khách — đọc được trên ảnh chụp màn hình người dùng gửi.

Không có lỗi nào bị ném. CSS không bao giờ báo lỗi; nó chỉ vẽ sai.

VÌ SAO SỬA BẰNG BIẾN THỂ CHỨ KHÔNG SỬA `.row`
----------------------------------------------
Nới cột đầu của `.row` thành `auto` sẽ làm thanh trạng thái 3px ở màn hình
Hội thoại và Đơn hàng co về 0 và biến mất — sửa một chỗ, hỏng hai chỗ.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def test_row_mac_dinh_van_giu_cot_3px_cho_thanh_trang_thai():
    """Thanh màu trạng thái là tín hiệu quét mắt nhanh nhất trên màn hình."""
    khoi = CSS.split(".row {", 1)[1].split("}", 1)[0]
    assert "3px" in khoi, "cột thanh trạng thái đã bị nới — nó sẽ biến mất"


def test_co_bien_the_rieng_cho_dong_co_avatar():
    assert ".row--avatar" in CSS, "chưa có biến thể cho dòng có avatar"


def test_bien_the_avatar_KHONG_dung_cot_3px():
    khoi = CSS.split(".row--avatar", 1)[1].split("}", 1)[0]
    assert "grid-template-columns" in khoi, "biến thể chưa đổi lưới cột"
    assert "3px" not in khoi, "vẫn nhét avatar 32px vào ô 3px"


def test_danh_sach_khach_hang_dung_bien_the_do():
    """
    Có CSS mà không gắn class là mã chết — đã xảy ra hai lần trong dự án này
    hôm nay (lưới chặn mã lạ, và hàm nạp tồn kho).
    """
    khoi = JS.split("#contactlist", 1)[1][:900]
    assert "row--avatar" in khoi, "danh sách khách hàng chưa dùng biến thể"


def test_moi_dong_dung_avatar_deu_phai_khai_bien_the():
    """
    Canh chung, không canh riêng một màn hình.

    Thêm avatar vào một danh sách khác mà quên class là lỗi đè chữ quay lại
    ở chỗ mới, và lần sau sẽ lại phải nhìn ảnh chụp màn hình mới biết.
    """
    for khoi in re.findall(r'class="row [^"]*"[^>]*>\s*<span class="avatar"', JS):
        assert "row--avatar" in khoi, (
            "một dòng đặt avatar vào cột 3px mà không khai biến thể"
        )


def test_avatar_khong_bi_co_lai_khi_ten_dai():
    """
    `flex: 0 0 auto` giữ avatar tròn khi tên dài.

    Bỏ nó đi thì avatar bị bóp thành hình bầu dục — sửa lỗi đè chữ mà đẻ ra
    lỗi méo hình.
    """
    khoi = CSS.split(".avatar {", 1)[1].split("}", 1)[0]
    assert "flex: 0 0 auto" in khoi
