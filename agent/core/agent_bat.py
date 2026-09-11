"""
Agent có được trả lời hội thoại này không — và nếu không thì VÌ SAO.

VÌ SAO TRẢ VỀ CẢ LÝ DO
-----------------------
Một hàm trả `True`/`False` là đủ để chặn, nhưng không đủ để ai đó trả lời
câu "vì sao kênh này agent không nói gì". Và câu ấy LUÔN được hỏi — thường
là vào lúc khách đã chờ hai tiếng.

Lý do đi kèm sẽ vào nhật ký ở chỗ chặn, nên dashboard và nhật ký kiểm toán
nói cùng một chuyện.

BA NẤC, THEO ĐÚNG THỨ TỰ NÀY
-----------------------------
    công tắc toàn cục   `runtime.enabled` — cắt tất cả
    theo tài khoản kênh `channel_accounts.agent_bat` — nấc thật sự hay dùng
    theo hội thoại      `conversations.mode = 'human'` — người đã tiếp quản

Thứ tự quan trọng: kiểm toàn cục trước thì khi người vận hành bấm ngắt
khẩn cấp, không cần hỏi CSDL thêm lần nào.

VÀ ĐIỀU QUAN TRỌNG NHẤT: TẮT KHÔNG PHẢI LÀ IM
----------------------------------------------
Hàm này chỉ nói agent có được trả lời không. Nó KHÔNG nói tin nhắn được
phép biến mất. Nơi gọi có nghĩa vụ chuyển hội thoại sang người và sinh một
công việc — xem `agent/main.py`.

Bỏ vế ấy thì "agent là tuỳ chọn" biến thành "kênh chết im lặng": tin vào,
không ai trả lời, và dashboard vẫn xanh vì không có gì hỏng cả.
"""
from __future__ import annotations

from typing import Any, NamedTuple

from agent import db, runtime


class KetQua(NamedTuple):
    duoc: bool
    ly_do: str = ""


async def agent_duoc_tra_loi(
    account_id: Any, conv: dict | None = None,
) -> KetQua:
    """
    Agent có được tự trả lời hội thoại này không.

    `conv` là dòng hội thoại đã đọc sẵn (để không phải truy vấn lại). Truyền
    None thì chỉ kiểm hai nấc đầu.
    """
    if not runtime.enabled():
        return KetQua(False, "Công tắc ngắt toàn hệ thống đang bật")

    if conv is not None:
        if conv.get("status") == "escalated" or conv.get("mode") == "human":
            return KetQua(False, "Hội thoại này đã do người tiếp quản")

    if account_id is not None:
        dong = await db.fetchrow(
            "SELECT agent_bat, display_name, agent_tat_ly_do "
            "FROM channel_accounts WHERE id = $1", account_id)
        # Tài khoản không tìm thấy: KHÔNG cho agent trả lời.
        #
        # Cho qua là mở đường cho một hội thoại trỏ vào tài khoản đã xoá
        # được agent trả lời nhân danh một kênh không còn tồn tại.
        if dong is None:
            return KetQua(False, "Không tìm thấy tài khoản kênh")
        if not dong["agent_bat"]:
            ly_do = dong["agent_tat_ly_do"] or "không ghi lý do"
            return KetQua(
                False,
                f"Agent đang TẮT cho kênh “{dong['display_name']}” ({ly_do})")

    return KetQua(True)
