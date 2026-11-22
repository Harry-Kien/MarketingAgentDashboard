"""
Agent có được trả lời hội thoại này không — và nếu không thì VÌ SAO.

VÌ SAO TRẢ VỀ CẢ LÝ DO
-----------------------
Một hàm trả `True`/`False` là đủ để chặn, nhưng không đủ để ai đó trả lời
câu "vì sao kênh này agent không nói gì". Và câu ấy LUÔN được hỏi — thường
là vào lúc khách đã chờ hai tiếng.

Lý do đi kèm sẽ vào nhật ký ở chỗ chặn, nên dashboard và nhật ký kiểm toán
nói cùng một chuyện.

BA NẤC
------
    theo hội thoại      `conversations.mode = 'human'` — người đã tiếp quản
    công tắc toàn cục   `runtime.enabled` — cắt tất cả (Cấu hình AI Agent →
                        Cấu hình cơ bản, và đèn ngắt khẩn cấp ở thanh trên)
    theo tài khoản kênh `channel_accounts.agent_bat`

Hai nấc đầu không hỏi CSDL (`conv` do nơi gọi đọc sẵn), nên khi người vận
hành bấm ngắt khẩn cấp, không cần hỏi CSDL thêm lần nào. Nấc "người tiếp
quản" đứng đầu để BẬT lại AI không bao giờ giành hội thoại nhân viên đang
cầm, và TẮT AI không bắn thông báo thừa cho hội thoại ấy.

VÀ ĐIỀU QUAN TRỌNG NHẤT: TẮT KHÔNG PHẢI LÀ IM
----------------------------------------------
Hàm này chỉ nói agent có được trả lời không. Nó KHÔNG nói tin nhắn được
phép biến mất. Nơi gọi có nghĩa vụ chuyển hội thoại sang người và báo nhân
viên (thông báo nội bộ) — xem `agent/omnichannel/xu_ly_tin_vao.py`.

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
    # Người đã tiếp quản xét TRƯỚC công tắc toàn cục. Cả hai đều không hỏi
    # CSDL (`conv` đã đọc sẵn), nên ngắt khẩn cấp vẫn không phụ thuộc CSDL.
    # Thứ tự này quyết định LÝ DO, và lý do quyết định có báo nhân viên hay
    # không (xu_ly_tin_vao chỉ im khi lý do là "người tiếp quản"): xét công
    # tắc trước thì lúc AI TẮT, mỗi tin khách vào một hội thoại nhân viên
    # đang cầm lại bắn một thông báo "AI chuyển giao" — trong khi AI chẳng
    # chuyển gì, nhân viên đang làm việc bình thường.
    if conv is not None:
        if conv.get("status") == "escalated" or conv.get("mode") == "human":
            return KetQua(False, "Hội thoại này đã do người tiếp quản")

    if not runtime.enabled():
        return KetQua(False, "Công tắc ngắt toàn hệ thống đang bật")

    if conv is not None and conv.get("id") is not None:
        from agent import goi_cuoc
        if not await goi_cuoc.con_luot_ai(conv["id"]):
            hm = goi_cuoc.han_muc()
            return KetQua(False, f"Hết lượt hội thoại AI của gói {hm.goi} trong tháng "
                                 f"({hm.hoi_thoai_ai_thang}) — nâng gói để agent nhận tiếp")

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
