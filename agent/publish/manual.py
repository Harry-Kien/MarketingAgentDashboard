"""
Hàng đợi thủ công — lưới an toàn cuối cùng, luôn dùng được.

Không gọi API nào. Chỉ đánh dấu bài "sẵn sàng để người đăng"; dashboard
hiện nút tải video và nút chép caption. Đây là chế độ mặc định khi chưa
cấu hình n8n và chưa được nền tảng duyệt quyền.

Vẫn phải đi qua PublishAdapter chứ không phải một nhánh if riêng, để khi
n8n hoặc Graph API bật lên thì phần trên không đổi một dòng nào.
"""
from __future__ import annotations

from .base import PublishAdapter, PublishResult, PublishTarget


class ManualPublisher(PublishAdapter):
    name = "manual"

    async def publish(self, target: PublishTarget) -> PublishResult:
        return PublishResult(
            ok=True,
            kenh=target.kenh,
            da_nhan_chua_dang=True,
            detail="Đã vào hàng đợi — tải video và đăng thủ công",
        )
