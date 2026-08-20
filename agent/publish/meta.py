"""
Facebook Page / Instagram Business qua Graph API.

TRẠNG THÁI: mã viết đủ, TẮT cho tới khi app được duyệt.

Muốn bật cần:
  1. Meta Business Account + Business Verification (giấy phép kinh doanh)
  2. App Review cho: pages_manage_posts, pages_read_engagement
     và instagram_content_publish nếu đăng Instagram
  3. Page Access Token dài hạn (60 ngày, phải gia hạn)

Chưa có 3 thứ đó thì Graph API trả lỗi 200/10 "Requires permission".
san_sang() nói thẳng điều này ra dashboard thay vì để nó thất bại lúc đăng.

Instagram Reels đi hai bước, không phải một: tạo container rồi publish.
Container cần thời gian Meta xử lý video nên phải hỏi trạng thái vòng lặp.
"""
from __future__ import annotations

import asyncio

import httpx

from ..config import settings
from .base import PublishAdapter, PublishResult, PublishTarget

GRAPH = "https://graph.facebook.com/v21.0"


class MetaPublisher(PublishAdapter):
    name = "meta"

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=120.0)

    async def san_sang(self) -> tuple[bool, str]:
        if not settings.fb_page_token:
            return False, (
                "Chưa có Page Access Token. Cần Business Verification + "
                "App Review quyền pages_manage_posts (1-4 tuần)."
            )
        return True, ""

    async def publish(self, target: PublishTarget) -> PublishResult:
        ok, ly_do = await self.san_sang()
        if not ok:
            return PublishResult(ok=False, kenh=target.kenh, detail=ly_do)
        if target.kenh == "instagram":
            return await self._instagram(target)
        return await self._facebook(target)

    async def _facebook(self, t: PublishTarget) -> PublishResult:
        page = settings.fb_page_id
        try:
            if t.video_path and t.video_path.exists():
                with t.video_path.open("rb") as fh:
                    r = await self._http.post(
                        f"{GRAPH}/{page}/videos",
                        data={"description": t.caption(),
                              "access_token": settings.fb_page_token},
                        files={"source": (t.video_path.name, fh, "video/mp4")},
                    )
            else:
                r = await self._http.post(
                    f"{GRAPH}/{page}/feed",
                    data={"message": t.caption(),
                          "access_token": settings.fb_page_token},
                )
            r.raise_for_status()
            pid = r.json().get("id", "")
        except httpx.HTTPError as exc:
            return PublishResult(ok=False, kenh=t.kenh, detail=str(exc)[:300])
        return PublishResult(ok=True, kenh=t.kenh,
                             url=f"https://facebook.com/{pid}" if pid else "")

    async def _instagram(self, t: PublishTarget) -> PublishResult:
        ig = settings.ig_user_id
        if not ig:
            return PublishResult(ok=False, kenh=t.kenh,
                                 detail="Chưa cấu hình IG_USER_ID")
        if not t.video_path:
            return PublishResult(ok=False, kenh=t.kenh,
                                 detail="Instagram bắt buộc phải có video hoặc ảnh")
        # Instagram chỉ nhận URL công khai, không nhận upload trực tiếp.
        video_url = f"{settings.public_base_url}/media/videos/{t.video_path.name}"
        try:
            r = await self._http.post(
                f"{GRAPH}/{ig}/media",
                data={"media_type": "REELS", "video_url": video_url,
                      "caption": t.caption(),
                      "access_token": settings.fb_page_token},
            )
            r.raise_for_status()
            cid = r.json()["id"]

            # Meta cần thời gian tải và mã hoá video -> hỏi vòng lặp.
            for _ in range(30):
                await asyncio.sleep(4)
                s = await self._http.get(
                    f"{GRAPH}/{cid}",
                    params={"fields": "status_code",
                            "access_token": settings.fb_page_token},
                )
                if s.json().get("status_code") == "FINISHED":
                    break
            else:
                return PublishResult(ok=False, kenh=t.kenh,
                                     detail="Instagram xử lý video quá lâu")

            p = await self._http.post(
                f"{GRAPH}/{ig}/media_publish",
                data={"creation_id": cid, "access_token": settings.fb_page_token},
            )
            p.raise_for_status()
            mid = p.json().get("id", "")
        except httpx.HTTPError as exc:
            return PublishResult(ok=False, kenh=t.kenh, detail=str(exc)[:300])
        return PublishResult(ok=True, kenh=t.kenh,
                             url=f"https://instagram.com/p/{mid}" if mid else "")

    async def aclose(self) -> None:
        await self._http.aclose()
