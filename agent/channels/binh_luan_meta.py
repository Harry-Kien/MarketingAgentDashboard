"""
Bình luận Facebook: đọc webhook `feed`, nhận ra số điện thoại, ẩn bình luận.

VÌ SAO MỖI BÌNH LUẬN MỘT HỘI THOẠI (`cmt:<comment_id>`)
------------------------------------------------------
Meta cho Trang trả lời RIÊNG (private reply) đúng MỘT lần cho mỗi bình
luận, trong 7 ngày, và tin ấy gửi tới `recipient.comment_id` — không phải
PSID. Khách trả lời lại thì thành tin nhắn Messenger thường, về hội thoại
PSID như mọi tin khác. Gộp bình luận vào hội thoại PSID là mất chỗ để biết
"bình luận nào đã được trả lời riêng chưa", và tin thứ hai gửi đi sẽ bị
Meta từ chối rồi chết trong outbox. Xem `cua_so_gui.py`.

VÌ SAO AGENT KHÔNG TỰ TRẢ LỜI BÌNH LUẬN
--------------------------------------
Agent hay tách câu trả lời thành 2–3 tin cho tự nhiên. Với bình luận, chỉ
tin đầu đi được; phần còn lại bị từ chối. Nên bình luận vào inbox ở trạng
thái chờ người, như tin `standby` — xem `agent/main.py::handle_inbound`.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from agent.channels.base import InboundMessage

# Số di động VN: 0 hoặc +84/84, rồi đầu 3/5/7/8/9, rồi 8 số. Ghép dấu cách,
# chấm, gạch giữa các chữ số trước khi soi — khách cố tình viết "0912 345
# 678" chính là để lách bộ lọc kiểu ngây thơ.
_SDT = re.compile(r"(?<!\d)(?:\+?84|0)[35789]\d{8}(?!\d)")
_NOI = re.compile(r"(?<=\d)[\s.\-]+(?=\d)")


def co_so_dien_thoai(text: str) -> bool:
    return bool(_SDT.search(_NOI.sub("", text or "")))


def _thoi_diem(giay) -> datetime:
    try:
        return datetime.fromtimestamp(int(giay), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc)


def doc_binh_luan(payload: dict, adapter) -> list[InboundMessage]:
    """Bình luận MỚI của khách trong một lô webhook `feed`."""
    if payload.get("object") != "page":
        return []
    ra: list[InboundMessage] = []
    for entry in payload.get("entry") or []:
        if not isinstance(entry, dict):
            continue
        trang = str(entry.get("id") or "")
        for thay_doi in entry.get("changes") or []:
            if not isinstance(thay_doi, dict) or thay_doi.get("field") != "feed":
                continue
            v = thay_doi.get("value") or {}
            # Chỉ bình luận MỚI: sửa/xoá không phải câu hỏi mới, và cảm xúc
            # (reaction) thì không có gì để trả lời.
            if v.get("item") != "comment" or v.get("verb") != "add":
                continue
            tu = v.get("from") or {}
            nguoi = str(tu.get("id") or "")
            # Trang tự trả lời công khai cũng về qua `feed`. Không chặn ở
            # đây thì mỗi câu trả lời của shop lại thành một "tin khách".
            if not nguoi or nguoi == trang:
                continue
            loi = str(v.get("message") or "").strip()
            cmt = str(v.get("comment_id") or "")
            if not loi or not cmt:
                continue
            ra.append(InboundMessage(
                account_id=adapter.account_id,
                channel=adapter.name,
                conversation_ref=f"cmt:{cmt}",
                customer_ref=nguoi,
                customer_name=str(tu.get("name") or "Khách bình luận"),
                text=loi,
                dedupe_key=f"{adapter.name}:cmt:{cmt}",
                received_at=_thoi_diem(v.get("created_time")),
                attachments=[],
                meta={"loai": "binh_luan", "comment_id": cmt,
                      "post_id": str(v.get("post_id") or ""),
                      "co_sdt": co_so_dien_thoai(loi),
                      "nen_tang_goc": "facebook_comment"},
            ))
    return ra
