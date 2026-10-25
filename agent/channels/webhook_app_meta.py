"""
Khai địa chỉ webhook CỦA APP với Meta bằng Graph API — không dán tay.

VÌ SAO CẦN
----------
`dang_ky_webhook_meta.py` đăng ký từng TRANG vào app (`subscribed_apps`).
Nhưng địa chỉ Meta gọi tới là của APP, khai ở App Dashboard → Webhooks, và
tới 25.10.2026 vẫn phải dán tay. Đo ngày ấy: Meta đang gọi một tên miền
tunnel CŨ (`excerpt-…trycloudflare.com`), khác cả tên miền trong `.env`, cả
hai đã chết — Facebook không nhận được tin khách nào mà không gì báo đỏ ở
phía Meta. Mỗi lần tunnel đổi tên miền là một lần kênh chết im lặng.

`POST /{app-id}/subscriptions` (khoá app = `app_id|app_secret`) làm đúng việc
nút "Xác minh và lưu": Meta gọi GET vào địa chỉ mới với verify token, địa
chỉ phải trả lời đúng thì mới lưu. Nên gọi hàm này chỉ khi tunnel đã thông
và app đã chạy.

TRƯỜNG ĐĂNG KÝ
--------------
Đo cùng ngày: app đăng ký sáu trường messaging nhưng THIẾU `feed` — bình
luận dưới bài (agent/channels/binh_luan_meta.py, có test) không bao giờ tới.
Trang đăng ký `feed` ở `subscribed_apps` là chưa đủ: app cũng phải đăng ký.
Giữ nguyên các trường app đang có (messaging_handovers dùng cho bàn giao
Page Inbox) và thêm những trường bộ đọc cần.
"""
from __future__ import annotations

from typing import Any

import httpx

from agent.config import settings

TRUONG_CAN = ("messages", "messaging_postbacks", "messaging_handovers", "feed")


def khoa_app() -> str:
    if not (settings.meta_app_id and settings.meta_app_secret):
        raise ValueError("thiếu META_APP_ID / META_APP_SECRET trong .env")
    return f"{settings.meta_app_id}|{settings.meta_app_secret}"


def doc_dang_ky(du_lieu: dict[str, Any]) -> dict[str, Any] | None:
    """Mục `object=page` trong phản hồi GET /{app}/subscriptions, hoặc None."""
    for muc in du_lieu.get("data") or []:
        if muc.get("object") == "page":
            return {"callback_url": muc.get("callback_url", ""),
                    "active": bool(muc.get("active")),
                    "fields": sorted(f.get("name", "") for f in muc.get("fields") or [])}
    return None


def truong_se_dang_ky(hien_co: list[str]) -> list[str]:
    return sorted(set(hien_co) | set(TRUONG_CAN))


async def doc_hien_tai(client: httpx.AsyncClient) -> dict[str, Any] | None:
    r = await client.get(f"{settings.graph_base}/{settings.meta_app_id}/subscriptions",
                         params={"access_token": khoa_app()})
    r.raise_for_status()
    return doc_dang_ky(r.json())


async def khai_callback(client: httpx.AsyncClient, callback_url: str,
                        verify_token: str) -> tuple[bool, str]:
    """
    Khai `callback_url` cho object page. Trả (được không, mô tả).

    Không in, không ghi verify token hay khoá app — mô tả chỉ có tên miền.
    """
    if not callback_url.startswith("https://"):
        return False, "Meta chỉ nhận callback HTTPS"
    if not verify_token:
        return False, "chưa có verify token Meta nào trong kho bí mật (nối Trang trước)"
    cu = await doc_hien_tai(client)
    truong = truong_se_dang_ky(cu["fields"] if cu else [])
    r = await client.post(
        f"{settings.graph_base}/{settings.meta_app_id}/subscriptions",
        data={"object": "page", "callback_url": callback_url, "verify_token": verify_token,
              "fields": ",".join(truong), "include_values": "true",
              "access_token": khoa_app()})
    if r.status_code != 200 or not (r.json() or {}).get("success"):
        try:
            loi = r.json().get("error", {}).get("message", "")
        except ValueError:
            loi = r.text
        return False, f"Meta từ chối ({r.status_code}): {str(loi)[:200]}"
    moi = await doc_hien_tai(client)
    if not moi or moi["callback_url"] != callback_url:
        return False, "Meta báo thành công nhưng đọc lại vẫn là địa chỉ khác — kiểm App Dashboard"
    if "feed" not in moi["fields"]:
        return False, "đã khai địa chỉ nhưng app chưa nhận trường feed (bình luận)"
    return True, f"Meta gọi {callback_url.split('/webhook', 1)[0]} · trường: {', '.join(moi['fields'])}"


async def dang_ky_cho_he_thong(public_base_url: str) -> tuple[bool, str]:
    """Dùng trong tiến trình có CSDL + kho bí mật: lấy verify token rồi khai."""
    from agent.api.native_webhooks import _dispatcher

    tokens = sorted(await _dispatcher().verify_tokens_dang_dung())
    if len(tokens) > 1:
        # Meta chỉ có MỘT ô verify token cho cả app — các Trang phải dùng chung.
        return False, f"{len(tokens)} verify token khác nhau giữa các Trang — Meta chỉ nhận một"
    url = public_base_url.rstrip("/") + "/webhook/native/meta"
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await khai_callback(client, url, tokens[0] if tokens else "")
