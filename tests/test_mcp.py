"""
Kiểm thử máy chủ MCP. Không gọi API model, không cần CSDL.

Hai thứ được canh ở đây:

1. RANH GIỚI AN TOÀN — MCP client là một model khác, chạy ngoài tầm kiểm
   soát của hệ thống này: không qua chốt tuân thủ, không có trần chi phí,
   không có lưới an toàn chuyển người. Nó tuyệt đối không được có công cụ
   đăng bài, chốt đơn hay nhắn tin cho khách.

2. TÊN THAM SỐ — lớp bọc MCP gọi lại `tools.run_tool` bằng dict. Đặt sai
   tên khoá thì bộ lọc bỏ qua trong IM LẶNG: không lỗi, không cảnh báo,
   chỉ có kết quả sai. Đã xảy ra thật (`van_de` thay vì `nhu_cau`,
   `ngan_sach` thay vì `gia_toi_da`) và chỉ lộ ra khi chạy thử tay.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import mcp_server  # noqa: E402
from agent.core.tools import TOOLS  # noqa: E402


def _ten_cong_cu() -> set[str]:
    import asyncio
    return {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}


# =====================================================================
#  Ranh giới an toàn
# =====================================================================

def test_mcp_khong_co_quyen_dang_bai_hay_nhan_khach():
    cam = {
        "dang_bai", "duyet_bai", "publish_post", "approve_post",
        "gui_tin_nhan", "send_message", "tra_loi_khach",
        "tao_don_hang", "chot_don", "create_order",
        "chuyen_nhan_vien", "tao_video",
    }
    lo = _ten_cong_cu() & cam
    assert not lo, (
        f"MCP đang lộ công cụ có hậu quả ra ngoài: {sorted(lo)}. "
        "Client MCP không đi qua chốt tuân thủ nào của hệ thống này."
    )


def test_bai_soan_qua_mcp_luon_dung_o_cho_duyet():
    src = inspect.getsource(mcp_server.dua_bai_vao_hang_doi)
    assert 'tao_boi="mcp"' in src
    # tao_bai() luôn đặt trang_thai='cho_duyet'; ở đây canh không ai lén
    # truyền trạng thái khác vào.
    assert "trang_thai" not in src, (
        "Không được cho phép đặt trạng thái bài từ MCP — mọi bài phải chờ duyệt."
    )


# =====================================================================
#  Tên tham số phải khớp với tools.run_tool
# =====================================================================

def _khoa_schema(ten: str) -> set[str]:
    for t in TOOLS:
        if t["name"] == ten:
            return set(t["input_schema"].get("properties", {}))
    raise AssertionError(f"Không có công cụ {ten} trong TOOLS")


def test_ten_tham_so_goi_y_san_pham_khop():
    ky = set(inspect.signature(mcp_server.goi_y_san_pham).parameters)
    assert ky <= _khoa_schema("goi_y_san_pham"), (
        f"Tham số MCP không có trong công cụ thật: "
        f"{sorted(ky - _khoa_schema('goi_y_san_pham'))}"
    )


def test_ten_tham_so_tra_cuu_san_pham_khop():
    ky = set(inspect.signature(mcp_server.tra_cuu_san_pham).parameters)
    assert ky <= _khoa_schema("tra_cuu_san_pham")


def test_ten_tham_so_tra_cuu_don_hang_khop():
    ky = set(inspect.signature(mcp_server.tra_cuu_don_hang).parameters)
    assert ky <= _khoa_schema("tra_cuu_don_hang")


def test_moi_khoa_truyen_vao_run_tool_deu_hop_le():
    """
    Soi thẳng mã: mọi khoá dict truyền vào run_tool phải nằm trong schema.

    Bắt được đúng lỗi đã xảy ra — `"van_de": van_de` gửi một khoá mà công
    cụ thật không đọc, nên bộ lọc im lặng bỏ qua.
    """
    import re
    for ten_ham, ten_tool in [
        ("goi_y_san_pham", "goi_y_san_pham"),
        ("tra_cuu_san_pham", "tra_cuu_san_pham"),
        ("tra_cuu_don_hang", "tra_cuu_don_hang"),
    ]:
        src = inspect.getsource(getattr(mcp_server, ten_ham))
        goi = src.split("run_tool(", 1)[1]
        khoa = set(re.findall(r'"(\w+)":', goi))
        thua = khoa - _khoa_schema(ten_tool)
        assert not thua, (
            f"{ten_ham} gửi khoá không tồn tại: {sorted(thua)} — "
            f"bộ lọc sẽ bỏ qua trong im lặng"
        )


# =====================================================================
#  Mô tả công cụ
# =====================================================================

def test_moi_cong_cu_deu_co_mo_ta():
    import asyncio
    for t in asyncio.run(mcp_server.mcp.list_tools()):
        assert t.description and len(t.description.strip()) > 30, (
            f"{t.name} thiếu mô tả — client MCP chọn công cụ dựa vào mô tả này"
        )


def test_khong_con_nhac_ten_nhom_hang_bi_cam():
    """
    "Đặc trị" là cách nói bị cấm theo Thông tư 06/2011/TT-BYT. Nó từng là
    TÊN NHÓM trong danh mục nên model đọc được và nhắc lại trong lời tư vấn
    gửi cho khách thật — nguồn rò rỉ nằm ở dữ liệu, không ở prompt.
    """
    import json

    # Đọc qua `_catalog()` chứ KHÔNG mở thẳng `data/catalog.json`: file đó
    # nằm trong .gitignore nên máy vừa clone repo về không có nó, và test
    # hỏng bằng FileNotFoundError. Hàm kia tự rơi về `catalog.example.json`
    # đi kèm repo — nhờ vậy phép kiểm tuân thủ này chạy được ở CI và trên
    # máy người mới, đúng những chỗ cần nó nhất.
    from agent.core.tools import _catalog

    catalog = _catalog()
    loai = {p.get("loai", "") for p in catalog.get("san_pham", [])}
    assert "Đặc trị" not in loai, "Tên nhóm hàng vi phạm quảng cáo mỹ phẩm"

    for t in TOOLS:
        assert "Đặc trị" not in json.dumps(t, ensure_ascii=False), (
            f"Mô tả công cụ {t['name']} còn nhắc nhóm hàng cũ"
        )


# =====================================================================
#  MCP trên chính cổng 8000
# =====================================================================
# Trước đây MCP qua HTTP là một tiến trình RIÊNG ở cổng 8765, không có xác
# thực nào, chỉ an toàn nhờ nghe 127.0.0.1 — tức là an toàn cho tới đúng
# ngày ai đó đổi host. Nay nó mount vào app chính và đi qua đúng lớp bảo vệ
# của dashboard.

import inspect as _inspect  # noqa: E402

from agent import main as _app_main  # noqa: E402
from agent.config import settings as _settings  # noqa: E402


def test_khong_co_token_thi_mcp_tat_han():
    """
    Fail-closed có chủ đích. Máy chủ MCP mở ra toàn bộ danh mục, đơn hàng và
    kho tri thức cho bất kỳ client nào gọi được — một tính năng như vậy
    không được bật theo mặc định chỉ vì nó tiện.
    """
    src = _inspect.getsource(_app_main.chan_neu_chua_dang_nhap)
    assert "if not khoa:" in src
    assert "404" in src.split("if not khoa:")[1][:120]


def test_mac_dinh_la_tat():
    """
    Máy vừa clone về không được tự phơi MCP ra.

    Kiểm giá trị mặc định TRONG MÃ, không dựng  — dựng thì
    pydantic đọc  của máy đang chạy, và test hoá ra chỉ đo cấu hình
    cá nhân của người chạy nó.
    """
    assert _settings.__class__.model_fields["mcp_token"].default == ""


def test_nhan_ca_token_lan_phien_dashboard():
    """
    Client MCP là ứng dụng khác (Claude Desktop), không đăng nhập bằng form
    được — nên phải có đường token. Nhưng người đang mở dashboard thì cũng
    phải gọi thử được mà không cần dán token.
    """
    src = _inspect.getsource(_app_main.chan_neu_chua_dang_nhap)
    assert "Bearer" in src
    assert "doc_phien" in src.split('duong.startswith("/mcp")')[1][:600]


def test_chan_khi_khong_co_gi():
    src = _inspect.getsource(_app_main.chan_neu_chua_dang_nhap)
    assert "401" in src.split('duong.startswith("/mcp")')[1][:700]


def test_mcp_khong_nam_trong_danh_sach_mo():
    assert not any("mcp" in d for d in _app_main._MO)


def test_thieu_gach_cheo_van_chay():
    """
    Mount ASGI chỉ nhận đúng đường có gạch chéo cuối; POST vào `/mcp` trả
    405. Người cấu hình Claude Desktop gõ thiếu một ký tự sẽ nhận đúng lỗi
    đó, và 405 không gợi ra được là thiếu gạch chéo.
    """
    duong = {getattr(r, "path", "") for r in _app_main.app.routes}
    assert "/mcp" in duong


def test_chuyen_huong_307_giu_nguyen_method():
    """
    302 biến POST thành GET và mọi lời gọi công cụ mất sạch tham số. Chỉ
    307 mới giữ nguyên method lẫn thân request.
    """
    src = _inspect.getsource(_app_main._mcp_them_gach_cheo)
    assert "307" in src


def test_vong_doi_mcp_chay_trong_vong_doi_app():
    """
    Mount KHÔNG tự chạy lifespan của app con. Bỏ bước này thì request đầu
    tiên ném "Task group is not initialized" — và lỗi đó chỉ hiện khi có
    client thật gọi tới, tức hỏng im lặng cho tới đúng lúc cần dùng.
    """
    src = _inspect.getsource(_app_main.lifespan)
    assert "lifespan_context" in src
    assert "__aexit__" in src
