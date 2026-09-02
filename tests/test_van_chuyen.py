"""
Công cụ tra vận chuyển của agent, và bậc tụt khi hãng không trả lời.

Phần ánh xạ trạng thái và các lỗi của kết nối GHN nằm ở
`tests/test_van_chuyen_ghn.py`.

VÌ SAO FILE NÀY TỪNG KIỂM MỘT API KHÁC
--------------------------------------
Bản đầu có `ShippingAdapter` + `ShippingGia` do dự án tự dựng. Khi ghép phần
kết nối GHN của cộng sự vào, hai lớp trừu tượng cùng mô tả một thứ — nên giữ
lại `BaseShippingProvider` (đầy đủ hơn: có webhook, có lộ trình) và bỏ lớp
cũ, chứ không để hai hợp đồng song song. Hai hợp đồng cho cùng một việc là
hai chỗ để lệch nhau.

Lưới canh "mã lạ không bị nuốt im lặng" của bản cũ thì GIỮ NGUYÊN — nó bắt
đúng một lỗi có thật trong bản của cộng sự.
"""
from __future__ import annotations

import asyncio


# ---------------------------------------------------------------
#  Bậc tụt: hãng chết thì việc rơi về người, không đứt dây chuyền
# ---------------------------------------------------------------

def test_adapter_mock_chay_duoc_hoan_toan_ngoai_tuyen():
    """
    Không có adapter giả thì mỗi lần chạy test là một lần gọi API hãng —
    tốn tiền, chậm, và người ta sẽ ngại chạy test.
    """
    from agent.shipping.mock import MockShippingProvider
    from agent.shipping.models import CreateWaybillRequest, ShippingItem

    nha_xe = MockShippingProvider()
    kq = asyncio.run(nha_xe.tao_van_don(CreateWaybillRequest(
        ma_don="DH-001", khach_ten="Chị Lan", khach_sdt="0900000000",
        khach_dia_chi="1 Nguyen Hue, Quan 1, TP Ho Chi Minh",
        items=[ShippingItem(ma="AS-CL01", ten="Sữa rửa mặt", so_luong=1)],
        tong_tien=245000,
    )))

    assert kq.ok is True
    assert kq.ma_van_don, "phải trả mã vận đơn để còn tra được"


def test_mac_dinh_he_thong_dung_mock():
    """
    Đổi sang `ghn` là hành động tốn tiền thật và tạo vận đơn thật.

    Mặc định phải là thứ không gây hậu quả — người vận hành chủ động bật.
    """
    from agent.config import Settings

    assert Settings().shipping_provider == "mock"


# ---------------------------------------------------------------
#  Công cụ cho agent
# ---------------------------------------------------------------

def test_tool_tra_cuu_van_chuyen_duoc_khai_bao():
    from agent.core.tools import TOOLS

    assert "tra_cuu_van_chuyen" in [t["name"] for t in TOOLS], (
        "agent phải có công cụ tra vận chuyển"
    )


def test_mo_ta_tool_noi_ro_GIOI_HAN_cua_no():
    """
    Agent phải biết nó tra được gì và KHÔNG tra được gì.

    Hệ thống đọc sổ của cửa hàng, không đọc vị trí kiện hàng theo thời gian
    thực. Mô tả không nói rõ thì agent sẽ hứa "mai hàng tới ạ" — một lời hứa
    nó không có cơ sở nào để đưa ra.
    """
    from agent.core.tools import TOOLS

    mo_ta = next(t for t in TOOLS if t["name"] == "tra_cuu_van_chuyen")["description"]
    thap = mo_ta.lower()
    assert "không" in thap, "mô tả phải nêu giới hạn"
    assert "đoán" in thap or "dự đoán" in thap or "hứa" in thap


def test_don_chua_ban_giao_thi_noi_that_chu_khong_doan():
    from agent.core.tools import run_tool

    kq = asyncio.run(run_tool("tra_cuu_van_chuyen", {"ma_don": "KHONG-CO-THAT"}))
    assert kq.get("tim_thay") is False
    assert kq.get("ghi_chu")


def test_loi_goi_y_phu_het_bon_trang_thai_noi_bo():
    """
    Thiếu một trạng thái thì agent nhận chuỗi rỗng và tự nghĩ ra lời của mình
    — đúng chỗ nó hay nói quá.
    """
    from agent.core.tools import _LOI_TRANG_THAI_GIAO
    from agent.shipping.models import InternalShippingStatus

    for trang_thai in InternalShippingStatus:
        assert _LOI_TRANG_THAI_GIAO.get(trang_thai.value), (
            f"thiếu lời gợi ý cho trạng thái {trang_thai.value}"
        )
