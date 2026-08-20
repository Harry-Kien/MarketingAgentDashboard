"""
Đăng bài qua n8n — đường đi DUY NHẤT chạy được ngay hôm nay.

n8n đã có sẵn node cho Facebook Graph, Instagram, TikTok, YouTube, X.
Xác thực nằm trong n8n (OAuth wizard sẵn có), không nằm trong mã này —
nên hệ thống không phải giữ token dài hạn của mạng xã hội, và khi
Facebook đổi phiên bản Graph API thì sửa trong n8n, không sửa ở đây.

Hợp đồng: POST tới webhook n8n, nhận lại {ok, url} hoặc chỉ 200.
n8n workflow chạy bất đồng bộ -> đánh dấu da_nhan_chua_dang, chờ n8n
gọi ngược về /api/posts/{id}/callback báo kết quả thật.
"""
from __future__ import annotations

import httpx

from ..config import settings
from .base import PublishAdapter, PublishResult, PublishTarget


class N8nPublisher(PublishAdapter):
    name = "n8n"

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=30.0)

    async def san_sang(self) -> tuple[bool, str]:
        if not settings.n8n_webhook_url:
            return False, "Chưa cấu hình N8N_WEBHOOK_URL trong .env"
        return True, ""

    async def publish(self, target: PublishTarget) -> PublishResult:
        ok, ly_do = await self.san_sang()
        if not ok:
            return PublishResult(ok=False, kenh=target.kenh, detail=ly_do)

        body = {
            "post_id": target.post_id,
            "kenh": target.kenh,
            "tieu_de": target.tieu_de,
            "caption": target.caption(),
            "hashtags": target.hashtags,
            # n8n chạy trong Docker: đường dẫn file phải là đường n8n thấy
            # được. Gửi cả đường tuyệt đối lẫn URL tải qua HTTP để workflow
            # chọn cách nào tiện.
            "video_path": str(target.video_path) if target.video_path else None,
            "video_url": (
                f"{settings.public_base_url}/media/videos/{target.video_path.name}"
                if target.video_path else None
            ),
            "callback_url": f"{settings.public_base_url}/api/posts/{target.post_id}/callback",
        }
        headers = {}
        if settings.n8n_auth_header:
            headers["Authorization"] = settings.n8n_auth_header

        try:
            r = await self._http.post(
                settings.n8n_webhook_url, json=body, headers=headers
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            return PublishResult(
                ok=False, kenh=target.kenh, detail=f"n8n không nhận: {exc}"[:300]
            )

        data = {}
        try:
            data = r.json() if r.content else {}
        except ValueError:
            pass
        if isinstance(data, list) and data:
            data = data[0]
        if not isinstance(data, dict):
            data = {}

        # n8n trả url ngay -> đăng xong luôn. Không trả -> đang chạy nền.
        url = str(data.get("url") or data.get("post_url") or "")
        if url:
            return PublishResult(ok=True, kenh=target.kenh, url=url,
                                 detail="n8n đăng xong")
        return PublishResult(
            ok=True, kenh=target.kenh, da_nhan_chua_dang=True,
            detail="n8n đã nhận, đang xử lý nền",
        )

    async def aclose(self) -> None:
        await self._http.aclose()
