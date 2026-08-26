"""
Luồng realtime phải phản hồi trong khoảng người dùng không kịp thấy là chậm.

VÌ SAO CÓ TEST NÀY
------------------
`event_stream` hỏi CSDL theo nhịp rồi mới đẩy sự kiện. Nhịp đó là toàn bộ
độ trễ mà người trực cảm nhận: tin khách đã nằm trong CSDL từ lâu, nhưng
dashboard chưa biết cho tới lượt hỏi kế tiếp.

Nhịp 1 giây khiến giao diện có cảm giác "chậm hơn Zalo" dù mọi thứ phía sau
đã xong. Đây là con số dễ bị nâng lên khi ai đó tối ưu tải CSDL mà quên mất
nó đánh đổi bằng trải nghiệm — nên phải có ngưỡng canh.

Truy vấn đằng sau là một lần quét chỉ mục trên `inbox_events.sequence_id`,
rất rẻ; nhịp nhanh không phải vấn đề ở quy mô một cửa hàng.
"""
from __future__ import annotations

import inspect

from agent.api.inbox import event_stream
from agent.config import settings

NGUONG_GIAY = 0.3


def test_nhip_hoi_mac_dinh_du_nhanh():
    mac_dinh = inspect.signature(event_stream).parameters["poll_seconds"].default
    assert mac_dinh <= NGUONG_GIAY, (
        f"nhịp hỏi SSE {mac_dinh}s làm dashboard trễ hơn mức người dùng chấp nhận"
    )


def test_nhip_hoi_doi_duoc_bang_cau_hinh():
    """Vận hành nhiều người trực thì phải nới được, không phải sửa mã."""
    assert hasattr(settings, "sse_poll_seconds")
    assert 0 < settings.sse_poll_seconds <= NGUONG_GIAY


def test_route_dung_cau_hinh_chu_khong_dung_so_go_cung():
    """Đổi cấu hình mà route vẫn dùng mặc định trong hàm thì cấu hình vô nghĩa."""
    from agent.api import inbox

    nguon = inspect.getsource(inbox.inbox_events)
    assert "poll_seconds=" in nguon, "route phải truyền nhịp hỏi xuống event_stream"
