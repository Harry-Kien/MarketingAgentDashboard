"""
Nạp ảnh khách gửi thành khối cho mô hình nhìn được.

VÌ SAO CẦN
----------
Trước file này, mã nói thẳng với agent: "[khách gửi kèm N ảnh — bạn KHÔNG
xem được nội dung ảnh]". Trung thực, và đúng: agent không bịa ra thứ nó
không thấy.

Nhưng với shop mỹ phẩm thì đó là khoảng trống lớn. Khách gửi ảnh sản phẩm
muốn mua, ảnh hàng nhận được bị vỡ, ảnh hoá đơn, ảnh màn hình chuyển khoản.
Không nhìn được nghĩa là mọi ca đó đều phải chuyển người.

BỐN GIỚI HẠN, MỖI CÁI CHẶN MỘT KIỂU HỎNG KHÁC NHAU
--------------------------------------------------
  số ảnh    -> khách gửi một loạt 20 ảnh không làm nổ chi phí một lượt
  dung lượng-> ảnh 12MB từ điện thoại không làm treo đường trả lời khách
  định dạng -> chỉ nhận thứ mô hình đọc được; PDF hay video đi vào là lỗi
               khó hiểu ở tận tầng nhà cung cấp
  thời gian -> CDN của hãng chậm thì bỏ ảnh, KHÔNG để khách chờ mãi

KHÔNG BAO GIỜ NÉM LỖI
---------------------
Tải ảnh hỏng thì bỏ ảnh đó và trả lời bằng phần chữ. Tin nhắn của khách mới
là việc chính; để một CDN chậm làm đứt cả lượt trả lời là đánh đổi sai —
cùng nguyên tắc với việc lấy tên khách từ Graph.
"""
from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

# Định dạng mô hình đọc được. Danh sách CHO PHÉP chứ không phải danh sách
# cấm: thứ lạ lọt vào sẽ hỏng ở tầng nhà cung cấp với thông báo khó hiểu.
MIME_CHO_PHEP = frozenset({
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif",
})

# Khách gửi cả album thì cũng chỉ đọc mấy tấm đầu. Mỗi ảnh là một khối token
# đáng kể, và ảnh thứ mười hiếm khi nói thêm điều gì.
TOI_DA_ANH = 3

# Ảnh chụp từ điện thoại đời mới thường 3–8MB. Trên ngưỡng này thì gần như
# chắc chắn là video hoặc file gửi nhầm.
TOI_DA_BYTE = 8 * 1024 * 1024

# Lời gọi này nằm TRÊN đường trả lời khách: chờ lâu hơn ngần này thì thà trả
# lời bằng phần chữ còn hơn để khách nhìn màn hình im lặng.
HAN_GIAY = 12.0


def _mime_tu(attachment: Mapping[str, Any]) -> str:
    """Đoán kiểu tệp từ metadata rồi tới đuôi tên."""
    mime = str(attachment.get("mime_type") or "").split(";")[0].strip().lower()
    if mime:
        return mime
    duong = str(attachment.get("url") or attachment.get("goc") or "").lower()
    for duoi, m in (
        (".png", "image/png"), (".webp", "image/webp"), (".gif", "image/gif"),
        (".jpeg", "image/jpeg"), (".jpg", "image/jpeg"),
    ):
        if duoi in duong:
            return m
    return ""


def loc_anh(attachments: Sequence[Mapping[str, Any]] | None) -> list[dict]:
    """
    Những đính kèm ĐÁNG tải về. Không chạm mạng.

    Tách khỏi phần tải để test được phép lọc mà không cần dựng máy chủ giả.
    """
    ra: list[dict] = []
    for item in attachments or []:
        if not isinstance(item, Mapping):
            continue
        url = str(item.get("url") or item.get("goc") or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            continue
        mime = _mime_tu(item)
        # Bộ đọc webhook đặt `loai: "image"`; tin cả hai nguồn, nhưng phải có
        # ít nhất một nguồn nói đây là ảnh.
        la_anh = mime in MIME_CHO_PHEP or str(item.get("loai") or "") == "image"
        if not la_anh:
            continue
        ra.append({"url": url, "mime": mime or "image/jpeg"})
        if len(ra) >= TOI_DA_ANH:
            break
    return ra


async def lay_khoi_anh(
    attachments: Sequence[Mapping[str, Any]] | None,
    *,
    client: httpx.AsyncClient | None = None,
    ghi_loi=None,
) -> list[dict]:
    """
    Tải ảnh về và đóng thành khối `{"type": "image", ...}` cho `llm`.

    Trả danh sách rỗng khi không có ảnh nào dùng được — chỗ gọi cứ trả lời
    bằng phần chữ như trước.
    """
    can_tai = loc_anh(attachments)
    if not can_tai:
        return []

    tu_mo = client is None
    client = client or httpx.AsyncClient(timeout=HAN_GIAY, follow_redirects=True)
    khoi: list[dict] = []
    try:
        for anh in can_tai:
            try:
                r = await client.get(anh["url"])
                if getattr(r, "status_code", 200) >= 400:
                    raise ValueError(f"HTTP {r.status_code}")

                du_lieu = r.content or b""
                if not du_lieu:
                    raise ValueError("tệp rỗng")
                if len(du_lieu) > TOI_DA_BYTE:
                    raise ValueError(f"{len(du_lieu)} byte, quá lớn")

                # Kiểu do máy chủ khai đáng tin hơn phần đoán từ tên tệp.
                mime = str(
                    (getattr(r, "headers", {}) or {}).get("content-type") or ""
                ).split(";")[0].strip().lower() or anh["mime"]
                if mime == "image/jpg":
                    mime = "image/jpeg"
                if mime not in MIME_CHO_PHEP:
                    raise ValueError(f"kiểu không đọc được: {mime or 'không rõ'}")

                khoi.append({
                    "type": "image",
                    "media_type": mime,
                    "data": base64.b64encode(du_lieu).decode("ascii"),
                })
            except Exception as exc:  # noqa: BLE001 — xem docstring đầu file
                if ghi_loi is not None:
                    await ghi_loi(f"{type(exc).__name__}: {exc}"[:200])
    finally:
        if tu_mo:
            await client.aclose()
    return khoi
