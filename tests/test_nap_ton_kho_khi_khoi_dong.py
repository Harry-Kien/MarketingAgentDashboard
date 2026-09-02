"""
Tồn kho phải được nạp từ danh mục lúc khởi động — nếu không, MỌI đơn đều hỏng.

LỖI ĐÃ CÓ THẬT
--------------
`kho.dong_bo_tu_danh_muc()` tồn tại, chú thích ghi rõ "Chạy một lần khi khởi
động", và KHÔNG CÓ GÌ GỌI NÓ. Bảng `ton_kho` trống rỗng trong khi danh mục
có 22 sản phẩm.

Hậu quả đo được trên hệ thống đang chạy:

    LEN DON THU -> thanh cong = False | ly do: Mã AS-SR01 không có trong kho.

Tức là chức năng chính của cả hệ thống — agent tự lên đơn — hỏng 100%. Mà
không có lỗi nào bị ném lúc khởi động, không có dòng nhật ký nào, và
`san_sang` vẫn báo đủ. Khách nhắn mua hàng thì agent xin lỗi "hết hàng" cho
sản phẩm còn nguyên trên kệ.

VÌ SAO MỘT HÀM CHẾT LẠI SỐNG SÓT LÂU NHƯ VẬY
--------------------------------------------
Vì nó CÓ test riêng và test đó xanh. Test gọi thẳng hàm rồi kiểm kết quả —
hàm chạy đúng. Không ai kiểm xem có ai GỌI nó không.

Đó là lý do file này canh ĐƯỜNG DÂY, không canh hàm.
"""
from __future__ import annotations

import inspect


def test_lifespan_co_goi_dong_bo_ton_kho():
    from agent import main

    nguon = inspect.getsource(main.lifespan)
    assert "dong_bo_tu_danh_muc" in nguon, (
        "không ai nạp tồn kho lúc khởi động — mọi đơn sẽ hỏng"
    )


def test_nap_sau_khi_init_db():
    """Gọi trước `init_db` là chưa có kết nối nào để mà ghi."""
    from agent import main

    nguon = inspect.getsource(main.lifespan)
    assert nguon.index("init_db") < nguon.index("dong_bo_tu_danh_muc")


def test_hong_thi_KHONG_chan_khoi_dong():
    """
    Danh mục hỏng không được làm chết cả ứng dụng.

    Nhưng cũng không được nuốt im — phải có nhật ký, nếu không ta quay lại
    đúng lỗi này lần nữa.
    """
    from agent import main

    nguon = inspect.getsource(main.lifespan)
    khoi = nguon.split("dong_bo_tu_danh_muc", 1)[1][:600]
    assert "except" in khoi, "hỏng danh mục là chết app"
    assert "log_event" in khoi, "nuốt lỗi im lặng"


def test_san_sang_canh_ton_kho_trong():
    """
    Máy phải tự phát hiện được trạng thái này, không đợi người mò ra.

    `san_sang` là chỗ duy nhất người vận hành thật sự đọc trước khi mở bán.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "scripts" / "san_sang.py").read_text(
        encoding="utf-8")
    assert "ton_kho" in src, "san_sang không kiểm tồn kho"
