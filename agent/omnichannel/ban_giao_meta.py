"""
Đồng bộ quyền hội thoại phía Meta (Handover Protocol) về trạng thái bên mình.

MỘT bản, hai lối gọi: webhook Messenger cũ (`agent/main.py`) và webhook
Meta native (`agent/api/native_webhooks.py`).

VÌ SAO GỘP
----------
Đường cũ từng xử lý sự kiện bàn giao còn đường native thì KHÔNG — Trang nối
bằng đường native mà nhân viên bấm "Xong" trong Page Inbox thì Meta trả quyền
về, không ai nghe, hội thoại nằm `human` vĩnh viễn. Hai bản sao của cùng một
việc thì bản ít người đọc sẽ mục (xem `bao_khach_dang_chuyen_nguoi`).

VÌ SAO NHẬN LẠI PHẢI ĐẶT CẢ `mode`
----------------------------------
Bản cũ chỉ `SET status='auto'` và giữ `mode='human'`. Nhưng agent đọc
`mode` để biết người đã tiếp quản chưa (`agent_bat.agent_duoc_tra_loi`,
`ly_do_loi_thoi`): mode còn `human` là agent tiếp tục đứng ngoài — trong khi
nhân viên tưởng đã trả việc. Cả hai bên đều tin bên kia đang lo, khách bị
bỏ rơi mà không ai sai. Test cũ chỉ soi chuỗi `'auto'` trong mã nên xanh giả.
"""
from __future__ import annotations

from typing import Any

from agent import db


async def ap_dung_ban_giao(bg: dict[str, Any], account_id, *, boi: str) -> str | None:
    """
    Áp một sự kiện bàn giao (`MessengerAdapter.doc_ban_giao`) lên hội thoại.

    Trả "nhan_lai" / "trao_di", hoặc None khi không có hội thoại tương ứng.
    """
    conv = await db.fetchrow(
        "SELECT id FROM conversations WHERE account_id = $1 AND external_id = $2",
        account_id, bg["khach"])
    if conv is None:
        return None
    if bg["ve_tay_ta"]:
        await db.execute(
            "UPDATE conversations SET status = 'auto', mode = 'auto', "
            "version = version + 1, updated_at = now() WHERE id = $1", conv["id"])
        await db.log_event("banGiao.nhan_lai", ref_id=conv["id"], boi=boi)
        return "nhan_lai"
    await db.execute(
        "UPDATE conversations SET status = 'escalated', mode = 'human', "
        "version = version + 1, updated_at = now() WHERE id = $1", conv["id"])
    await db.log_event("banGiao.trao_di", ref_id=conv["id"], loai=bg["loai"], boi=boi)
    return "trao_di"
