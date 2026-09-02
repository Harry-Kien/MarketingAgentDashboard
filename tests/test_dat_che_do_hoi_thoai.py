"""
Phải có đường đưa hội thoại VỀ LẠI chế độ agent tự trả lời.

LỖI ĐÃ CÓ THẬT — MỘT NGÕ CỤT
----------------------------
Ba chế độ, và chú giải trên đầu dashboard hiện đủ cả ba:

    auto   -> xanh  "Agent xử lý"     — AI trả lời thẳng cho khách
    assist -> cam   "Chờ duyệt"       — AI soạn, người bấm gửi
    human  -> đỏ    "Đã chuyển người" — AI im, người trả lời

Nhưng chỉ có hai nút, và không nút nào dẫn tới `auto`:

    "Tôi tiếp quản"       -> human
    "Kết thúc tiếp quản"  -> assist

Nghĩa là hội thoại một khi đã rơi xuống `assist` hoặc `human` thì KẸT ở đó
vĩnh viễn. Người trực xử lý xong một ca khó, muốn trả lại cho agent — không
có đường. Mọi hội thoại cũ dần dồn hết vào hàng chờ duyệt, và người trực
phải bấm tay từng câu trả lời cho những khách chỉ hỏi giá.

Ô xanh trên chú giải trở thành một lời hứa hệ thống không giữ được.

VÌ SAO ĐỔI CHẾ ĐỘ PHẢI CÓ KIỂM SOÁT
------------------------------------
Chuyển sang `auto` nghĩa là AI gửi thẳng cho khách, KHÔNG ai duyệt. Đó là
một quyết định thật, nên nó cần đúng những chốt mà takeover/release đã có:
khoá hàng, kiểm phiên bản, ghi nhật ký kiểm toán.
"""
from __future__ import annotations

import inspect

import pytest

CHE_DO = ("auto", "assist")


def test_co_duong_dat_che_do():
    from agent.api.inbox import router

    duong = {getattr(r, "path", "") for r in router.routes}
    assert "/api/inbox/conversations/{conversation_id}/che-do" in duong


def test_duong_doi_dang_nhap():
    from agent.api import inbox

    assert "bat_buoc_dang_nhap" in inspect.getsource(inbox.dat_che_do_conversation)


@pytest.mark.parametrize("che_do", CHE_DO)
def test_chi_nhan_auto_va_assist(che_do):
    """
    `human` KHÔNG đi qua đường này.

    Chuyển sang `human` là GIAO VIỆC cho một người cụ thể — nó cần biết giao
    cho ai, và đã có `takeover` làm đúng việc đó. Nhét nó vào đây là hai
    đường cùng đổi một thứ theo hai luật khác nhau.
    """
    from agent.api.inbox import DatCheDoIn

    assert DatCheDoIn(che_do=che_do, expected_version=1, reason="người trực đã xử lý xong").che_do == che_do


def test_tu_choi_che_do_human_va_gia_tri_bia():
    from pydantic import ValidationError

    from agent.api.inbox import DatCheDoIn

    for xau in ("human", "tu_dong", ""):
        with pytest.raises(ValidationError):
            DatCheDoIn(che_do=xau, expected_version=1, reason="người trực đã xử lý xong")


def test_bat_buoc_co_ly_do():
    """
    Cùng luật với takeover và release.

    Nhật ký kiểm toán ghi "ai đó bật auto lúc 2 giờ sáng" mà không có lý do
    thì nó chỉ là một dòng chữ, không dùng được khi cần truy.
    """
    from pydantic import ValidationError

    from agent.api.inbox import DatCheDoIn

    with pytest.raises(ValidationError):
        DatCheDoIn(che_do="auto", expected_version=1, reason="   ")


def test_kiem_phien_ban_truoc_khi_doi():
    """
    Hai người mở cùng hội thoại, một người tiếp quản, người kia bật auto —
    không kiểm phiên bản thì cú bấm sau xoá việc của cú bấm trước.
    """
    from agent.omnichannel import routing

    nguon = inspect.getsource(routing.ConversationRoutingService.dat_che_do)
    assert "expected_version" in nguon
    assert "ConversationConflict" in nguon


def test_dang_giao_cho_nguoi_thi_phai_release_truoc():
    """
    Hội thoại `human` có người đang giữ. Bật auto sau lưng họ là AI nhắn
    chen vào giữa cuộc họ đang xử lý.
    """
    from agent.omnichannel import routing

    nguon = inspect.getsource(routing.ConversationRoutingService.dat_che_do)
    assert '"human"' in nguon


def test_co_khoa_hang_nhu_takeover():
    """Cùng fence với outbox worker — nếu không, job AI đang gửi lọt qua."""
    from agent.omnichannel import routing

    nguon = inspect.getsource(routing.ConversationRoutingService.dat_che_do)
    assert "lock_conversation" in nguon


def test_ghi_nhat_ky_kiem_toan():
    from agent.omnichannel import routing

    nguon = inspect.getsource(routing.PostgresRoutingTransaction.apply_che_do)
    assert "events" in nguon
    assert "conversation.che_do" in nguon


def test_dashboard_co_nut_tra_ve_cho_agent():
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "dashboard" / "app.js").read_text(
        encoding="utf-8")
    assert "che-do" in js, "dashboard chưa gọi đường đổi chế độ"
    assert "btn-chedo" in js, "chưa có nút đổi chế độ"
