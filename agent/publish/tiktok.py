"""
TikTok Content Posting API.

TRẠNG THÁI: mã viết đủ, TẮT cho tới khi app qua audit.

Điều quan trọng phải biết trước khi hứa với ai: app CHƯA qua audit thì
TikTok ép mọi bài đăng về SELF_ONLY (chỉ mình xem). Nghĩa là đăng thành
công về mặt kỹ thuật nhưng không ai thấy — tệ hơn là báo lỗi, vì dễ tưởng
đang chạy tốt. Vì vậy adapter tự dán nhãn cảnh báo vào kết quả.

Luồng: init upload -> PUT file theo chunk -> hỏi trạng thái.
"""
from __future__ import annotations

import httpx

from ..config import settings
from .base import PublishAdapter, PublishResult, PublishTarget

API = "https://open.tiktokapis.com/v2"


class TikTokPublisher(PublishAdapter):
    name = "tiktok"

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=180.0)

    async def san_sang(self) -> tuple[bool, str]:
        if not settings.tiktok_access_token:
            return False, (
                "Chưa có TikTok access token. Content Posting API phải qua "
                "audit; chưa audit thì bài chỉ ở chế độ riêng tư."
            )
        return True, ""

    async def publish(self, t: PublishTarget) -> PublishResult:
        ok, ly_do = await self.san_sang()
        if not ok:
            return PublishResult(ok=False, kenh=t.kenh, detail=ly_do)
        if not t.video_path or not t.video_path.exists():
            return PublishResult(ok=False, kenh=t.kenh,
                                 detail="TikTok bắt buộc phải có video")

        data = t.video_path.read_bytes()
        head = {"Authorization": f"Bearer {settings.tiktok_access_token}"}
        try:
            init = await self._http.post(
                f"{API}/post/publish/video/init/",
                headers=head,
                json={
                    "post_info": {
                        "title": t.caption()[:2200],
                        "privacy_level": settings.tiktok_privacy,
                        "disable_comment": False,
                    },
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": len(data),
                        "chunk_size": len(data),
                        "total_chunk_count": 1,
                    },
                },
            )
            init.raise_for_status()
            d = init.json()["data"]
            up = await self._http.put(
                d["upload_url"],
                content=data,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Range": f"bytes 0-{len(data) - 1}/{len(data)}",
                },
            )
            up.raise_for_status()
        except (httpx.HTTPError, KeyError) as exc:
            return PublishResult(ok=False, kenh=t.kenh, detail=str(exc)[:300])

        canh_bao = ""
        if settings.tiktok_privacy == "SELF_ONLY":
            canh_bao = " — CHẾ ĐỘ RIÊNG TƯ (app chưa qua audit), người khác không thấy"
        return PublishResult(
            ok=True, kenh=t.kenh, da_nhan_chua_dang=True,
            detail=f"TikTok đang xử lý video{canh_bao}",
        )

    async def aclose(self) -> None:
        await self._http.aclose()
