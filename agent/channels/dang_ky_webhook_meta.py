"""
Đăng ký một Trang vào webhook của app — bước KHÔNG có thì không nhận được tin.

VÌ SAO CẦN MỘT BƯỚC RIÊNG
-------------------------
OAuth cho ta Page access token. Có token là GỬI được tin đi ngay. Nhưng NHẬN
tin cần một thứ khác hẳn: Trang phải được đăng ký vào webhook của app, bằng
`POST /{page-id}/subscribed_apps`.

Trước khi có file này, hệ thống làm xong OAuth rồi dừng. Mọi dấu hiệu đều
nói đã xong — Trang hiện trên dashboard, trạng thái xanh, xác minh kết nối
PASS, gửi tin chủ động PASS — chỉ có tin khách nhắn vào là không bao giờ
tới. Người vận hành phải tự mò vào Meta App Dashboard bấm tay, mà không có
gì trên màn hình nói cho họ biết điều đó.

CHỈ ĐĂNG KÝ `messages`
----------------------
Đúng thứ bộ đọc `MessengerAdapter.parse` xử lý được, không hơn.

  - `messaging_postbacks` -> parse trả None, đăng ký chỉ tốn lưu lượng
  - `message_echoes`      -> Meta đẩy lại CHÍNH tin Trang vừa gửi. Agent đọc
                             câu trả lời của mình rồi trả lời tiếp. Vòng lặp
                             vọng này đã xảy ra thật ở kênh Zalo trong dự án
                             này và phải chặn ở hai lớp mới dứt.

Thêm trường thì thêm ở đây, SAU khi bộ đọc xử lý được nó.

KHÔNG NÉM LỖI
-------------
Một Trang hỏng không được chặn 25 Trang còn lại. Trả `(False, lý do)` để chỗ
gọi ghi nhật ký và ĐẾM RIÊNG — chứ không phải nuốt im.
"""
from __future__ import annotations

from typing import Any

import httpx

from agent.config import settings

GRAPH_VERSION = settings.graph_version
GRAPH_BASE = settings.graph_base

# Xem docstring: chỉ những trường bộ đọc thật sự xử lý được.
TRUONG_THEO_DOI = ("messages",)


def _ly_do_tu_phan_hoi(phan_hoi: Any) -> str:
    """Moi câu lỗi của Graph ra. Graph gói lỗi trong `error.message`."""
    try:
        du_lieu = phan_hoi.json() or {}
    except Exception:  # noqa: BLE001 — lỗi không phải JSON thì dùng status
        return f"HTTP {getattr(phan_hoi, 'status_code', '?')}"
    loi = du_lieu.get("error") or {}
    if isinstance(loi, dict) and loi.get("message"):
        return str(loi["message"])[:200]
    return f"HTTP {getattr(phan_hoi, 'status_code', '?')}: {str(du_lieu)[:150]}"


async def dang_ky_webhook_trang(
    *,
    page_id: str,
    page_token: str,
    client: httpx.AsyncClient | None = None,
) -> tuple[bool, str]:
    """
    Đăng ký Trang vào webhook. Trả `(thành công, lý do khi hỏng)`.
    """
    if not page_id or not page_token:
        return False, "thiếu page_id hoặc page access token"

    tu_mo = client is None
    client = client or httpx.AsyncClient(base_url=GRAPH_BASE, timeout=20)
    try:
        phan_hoi = await client.post(
            f"/{page_id}/subscribed_apps",
            params={
                "subscribed_fields": ",".join(TRUONG_THEO_DOI),
                "access_token": page_token,
            },
        )
        if getattr(phan_hoi, "status_code", 200) >= 400:
            return False, _ly_do_tu_phan_hoi(phan_hoi)

        # HTTP 200 kèm `success: false` là đúng kiểu xanh giả: mã trạng thái
        # nói ổn còn thân phản hồi nói không. Tin thân phản hồi.
        try:
            du_lieu = phan_hoi.json() or {}
        except Exception:  # noqa: BLE001
            du_lieu = {}
        if du_lieu.get("success") is False:
            return False, _ly_do_tu_phan_hoi(phan_hoi)
        return True, ""
    except Exception as exc:  # noqa: BLE001 — xem docstring: không chặn Trang khác
        return False, f"{type(exc).__name__}: {exc}"[:200]
    finally:
        if tu_mo:
            await client.aclose()
