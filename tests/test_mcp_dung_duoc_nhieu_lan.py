"""
Vòng đời app phải chạy được NHIỀU LẦN trong cùng một tiến trình.

ĐO ĐƯỢC 22.09.2026 — trên mã chưa sửa, chạy
`pytest tests/test_thanh_vien_kenh.py` với Postgres thật cho
`9 passed, 4 errors`, mọi lỗi đều là:

    RuntimeError: StreamableHTTPSessionManager .run() can only be called
    once per instance.

Nguyên nhân: app MCP được dựng MỘT lần lúc import, còn
`StreamableHTTPSessionManager.run()` chỉ chạy được đúng một lần cho mỗi thể
hiện. Sản xuất không thấy vì lifespan chỉ chạy một lần rồi tiến trình sống
mãi; bộ test thì dựng app nhiều lần trong cùng tiến trình, nên từ app thứ
hai trở đi mọi test dùng lifespan đều ERROR. Đo trên worktree sạch ở `HEAD`
để chắc đây là lỗi sẵn có chứ không phải mới sinh.

Vì sao nó ẩn lâu: đúng nhóm test ấy bị bỏ qua ở máy phát triển do thiếu
`TEST_DATABASE_URL` (xem `test_postgres_chay_o_may_local.py`). Một lỗi làm
hỏng hàng chục test nằm im sau một dòng `skipped`.

CÁCH TEST NÀY ĐO — và vì sao không chạy vòng đời app đầy đủ:
bản đầu tiên của file này gọi `app.router.lifespan_context(app)` hai lần.
Nó bắt đúng lỗi, nhưng vòng đời app cần Postgres, nên khi Docker tắt thì
hai test ĐỎ vì `ConnectionRefusedError` — đỏ vì hạ tầng, không phải vì
ràng buộc bị vi phạm. Một test đỏ sai chỗ dạy người ta bỏ qua màu đỏ.

Nên ở đây đo THẲNG cơ chế đã hỏng: dựng hai app MCP và chạy vòng đời của
CHÍNH CHÚNG. Không chạm CSDL, mà vẫn đỏ nếu ai đó quay lại dùng chung một
thể hiện.
"""
from __future__ import annotations

import asyncio

import pytest

from agent.main import app


def _tao() -> callable:
    tao = getattr(app.state, "tao_mcp_app", None)
    if tao is None:
        pytest.skip("MCP tắt (thiếu MCP_TOKEN) — không có gì để kiểm")
    return tao


def test_mount_mcp_tro_toi_ban_hien_hanh():
    """
    Mount phải đi qua lớp chuyển tiếp, không giữ cứng một đối tượng.

    Mount thẳng app MCP thì việc dựng bản mới ở lifespan trở nên vô nghĩa —
    mount vẫn phục vụ bản cũ, và lỗi quay lại y như trước trong khi test
    dưới vẫn xanh.
    """
    # `/mcp` có HAI route trùng đường: một APIRoute chuyển hướng cho đường
    # thiếu gạch chéo, và Mount thật. Lọc theo đường thôi sẽ bắt nhầm cái
    # đầu — và test khi ấy đỏ vì lý do chẳng liên quan.
    mount = [
        r for r in app.routes
        if type(r).__name__ == "Mount" and getattr(r, "path", "") == "/mcp"
    ]
    if not mount:
        pytest.skip("MCP tắt (thiếu MCP_TOKEN) — không có gì để kiểm")
    ten_lop = type(mount[0].app).__name__
    assert ten_lop == "_McpChuyenTiep", (
        f"/mcp đang mount thẳng `{ten_lop}`. Phải mount lớp chuyển tiếp đọc "
        "`app.state.mcp_app` lúc có request, nếu không bản dựng lại ở "
        "lifespan không bao giờ được dùng."
    )


def test_moi_lan_goi_cho_mot_the_hien_khac():
    """Dùng lại một thể hiện là nguyên nhân gốc, nên chốt thẳng vào đó."""
    tao = _tao()
    a, b = tao(), tao()
    assert a is not b, (
        "tao_mcp_app() trả về cùng một đối tượng — session manager sẽ bị "
        "`run()` lần thứ hai và ném ngay"
    )


def test_chay_vong_doi_mcp_hai_lan_khong_nem():
    """
    Chốt chính, và KHÔNG chạm CSDL: chạy vòng đời của chính hai app MCP.

    Đây đúng là thao tác đã ném trên mã cũ. Nếu ai gộp lại thành một thể
    hiện dùng chung, lần thứ hai ở đây đỏ ngay.
    """
    tao = _tao()

    async def chay() -> None:
        for lan in (1, 2):
            m = tao()
            try:
                async with m.router.lifespan_context(m):
                    pass
            except RuntimeError as e:
                if "once per instance" in str(e):
                    pytest.fail(
                        f"lần {lan}: app MCP bị dùng lại thay vì dựng mới — "
                        "xem tao_mcp_app() trong agent/main.py"
                    )
                raise

    asyncio.run(chay())


def test_lifespan_app_dat_roi_go_tham_chieu():
    """
    Vòng đời app phải ĐẶT `app.state.mcp_app` lúc vào và GỠ lúc ra.

    Gỡ để request tới `/mcp` sau khi tắt nổ rõ ràng, thay vì chạy trên một
    session manager đã đóng — kiểu hỏng khó lần ra hơn nhiều.

    Đọc mã nguồn chứ không chạy vòng đời app: chạy nó cần Postgres, và một
    test hạ tầng-phụ-thuộc ở đây chỉ tạo đỏ sai chỗ.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "agent" / "main.py").read_text(
        encoding="utf-8"
    )
    i_dat = src.find("app.state.mcp_app = _m")
    i_yield = src.find("\n    yield\n", i_dat if i_dat > 0 else 0)
    i_go = src.find("app.state.mcp_app = None", i_yield if i_yield > 0 else 0)
    assert i_dat != -1, "lifespan không còn đặt app.state.mcp_app"
    assert i_yield != -1, "không tìm thấy `yield` của lifespan"
    assert i_go != -1 and i_go > i_yield, (
        "lifespan không gỡ `app.state.mcp_app` SAU `yield` — tắt app rồi mà "
        "/mcp vẫn trỏ tới session manager đã đóng"
    )
