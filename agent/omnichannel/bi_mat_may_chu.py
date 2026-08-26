"""
Bí mật thuộc về MÁY CHỦ thì máy chủ tự điền, không hỏi người dùng.

RANH GIỚI
---------
Credential của một tài khoản kênh chia làm hai loại, và trộn lẫn hai loại là
gốc của phần lớn rắc rối khi nối kênh:

  CỦA NGƯỜI DÙNG   Page access token, App secret của Meta, Refresh token của
                   Zalo OA. Mỗi tài khoản một giá trị khác nhau. Chỉ chủ tài
                   khoản mới lấy được. Bắt buộc phải hỏi.

  CỦA MÁY CHỦ      `sidecar_secret`, `sidecar_url`. MỌI tài khoản Zalo cá
                   nhân dùng chung đúng một giá trị, nằm sẵn trong `.env`
                   của người vận hành.

Hỏi loại thứ hai là sai ba lần cùng lúc: người dùng không có `.env` để mở
(nhất là khi hệ thống chạy trên tên miền cho nhiều người), chép tay chuỗi 32
ký tự là mời gọi sai một byte, và bí mật máy chủ đi vòng qua trình duyệt mà
không đổi lại được gì.

VÌ SAO ĐÈ LÊN GIÁ TRỊ CLIENT GỬI, KHÔNG PHẢI "ĐIỀN NẾU THIẾU"
--------------------------------------------------------------
Chỉ có ĐÚNG MỘT giá trị đúng và máy chủ đang giữ nó. Tôn trọng thứ client
gửi lên nghĩa là một giá trị sai vẫn đi được vào vault, rồi hỏng ở tận bước
quét QR — cách chỗ gây lỗi hàng chục thao tác, không còn ai nhớ đã dán gì.

Đè lên còn tự chữa những tài khoản cũ đã lỡ lưu sai: chỉ cần bấm lưu lại.

VÌ SAO NÉM KHI MÁY CHỦ CHƯA CẤU HÌNH
------------------------------------
Điền chuỗi rỗng thì tài khoản trông y hệt tài khoản tốt trên dashboard —
trạng thái xanh, có credential — chỉ có QR là không bao giờ quét được, và
không có dòng lỗi nào ở đâu cả. Đúng kiểu hỏng mà repo này sợ nhất.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent.omnichannel.accounts import Channel


class ThieuBiMatMayChu(RuntimeError):
    """Máy chủ chưa cấu hình bí mật mà kênh này bắt buộc phải có."""


def bo_sung_bi_mat_may_chu(
    channel: Channel,
    credentials: Mapping[str, Any] | None,
    *,
    secret: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """
    Trả về bản credential ĐÃ có đủ phần của máy chủ.

    `secret` / `url` để tiêm giá trị trong test. Bỏ trống thì đọc từ cấu hình
    thật — nhờ vậy chỗ gọi không phải biết tên biến môi trường.
    """
    ra = dict(credentials or {})
    if channel is not Channel.ZALO_PERSONAL:
        return ra

    if secret is None or url is None:
        # Nhập ở đây chứ không ở đầu file: `settings` đọc `.env` lúc khởi
        # tạo, và test tiêm giá trị thì không nên kéo theo cấu hình thật.
        from agent.config import settings

        if secret is None:
            secret = settings.zalo_sidecar_secret
        if url is None:
            url = settings.zalo_sidecar_url

    secret = str(secret or "").strip()
    url = str(url or "").strip()
    if not secret:
        raise ThieuBiMatMayChu(
            "Máy chủ chưa cấu hình ZALO_SIDECAR_SECRET. "
            "Sinh bằng: python -m scripts.sinh_token ZALO_SIDECAR_SECRET"
        )
    if not url:
        raise ThieuBiMatMayChu("Máy chủ chưa cấu hình ZALO_SIDECAR_URL")

    ra["sidecar_secret"] = secret
    ra["sidecar_url"] = url
    return ra
