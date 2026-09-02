"""
Agent phải tra được ĐƠN THẬT nó vừa tạo — và chỉ đơn của khách đang nhắn.

LỖI ĐÃ CÓ THẬT
--------------
`tao_don_hang` ghi vào bảng `orders`, sinh mã dạng `AS260826143012`.
`tra_cuu_don_hang` lại đọc mảng `don_hang` trong `data/catalog.json` — ba
đơn mẫu bịa.

Hai đường không gặp nhau. Hậu quả trên hội thoại thật:

    Agent: "Em đã lên đơn cho chị, mã AS260826143012 ạ."
    (năm phút sau)
    Khách: "Cho chị hỏi đơn AS260826143012 tới đâu rồi?"
    Agent: "Không có mã đơn này trong hệ thống ạ."

Không có lỗi nào bị ném, không có dòng nhật ký nào, không ai biết. Đúng loại
hỏng mà `CLAUDE.md` xếp là nghiêm trọng nhất.

VÌ SAO PHẢI CHẶN THEO HỘI THOẠI
-------------------------------
Mã đơn ngắn và đoán được. Không chặn thì bất kỳ ai nhắn vào Trang cũng đọc
được tên, số điện thoại, địa chỉ của khách khác chỉ bằng cách đọc mã lên.
Đó là rò rỉ dữ liệu cá nhân, không phải bất tiện.

Không tìm thấy trong hội thoại này thì KHÔNG được nói "không có đơn đó" —
câu đó cũng đã là tiết lộ (nó phân biệt mã tồn tại với mã không tồn tại).
Phải đòi xác minh.
"""
from __future__ import annotations

import asyncio
import uuid


def _chay(name, args, conversation_id=None):
    from agent.core import tools
    return asyncio.run(tools.run_tool(name, args, conversation_id=conversation_id))


def test_tra_duoc_don_that_trong_dung_hoi_thoai(monkeypatch):
    from agent.core import tools

    hoi_thoai = uuid.uuid4()

    async def gia_lap(ma_don, conv_id):
        assert conv_id == hoi_thoai, "phải chặn theo hội thoại"
        if ma_don == "AS260826143012":
            return {"cua_hoi_thoai_nay": True, "ma_don": ma_don,
                    "trang_thai": "da_chot", "tong_tien": 450000,
                    "items": [{"ma": "AS-SP01", "sl": 1}]}
        return None

    monkeypatch.setattr(tools, "_doc_don_trong_csdl", gia_lap)
    ra = _chay("tra_cuu_don_hang", {"ma_don": "AS260826143012"}, hoi_thoai)

    assert ra["tim_thay"] is True
    assert ra["ma_don"] == "AS260826143012"


def test_don_cua_nguoi_khac_KHONG_lo_thong_tin(monkeypatch):
    """Mã tồn tại nhưng của hội thoại khác: đòi xác minh, không trả chi tiết."""
    from agent.core import tools

    async def gia_lap(ma_don, conv_id):
        return {"cua_hoi_thoai_nay": False, "ma_don": ma_don,
                "khach_ten": "Người Khác", "khach_sdt": "0900000000",
                "khach_dia_chi": "123 Đường Nào Đó"}

    monkeypatch.setattr(tools, "_doc_don_trong_csdl", gia_lap)
    ra = _chay("tra_cuu_don_hang", {"ma_don": "AS111"}, uuid.uuid4())

    assert ra.get("tim_thay") is not True
    assert ra.get("can_xac_minh") is True
    van_ban = str(ra)
    for ro_ri in ("Người Khác", "0900000000", "123 Đường Nào Đó"):
        assert ro_ri not in van_ban, f"lộ {ro_ri} của khách khác"


def test_khong_co_hoi_thoai_thi_khong_tra_don_that(monkeypatch):
    """
    Gọi ngoài ngữ cảnh hội thoại (eval, test tay) không được mở toang kho đơn.

    Không có `conversation_id` thì không có gì để chặn theo.
    """
    from agent.core import tools

    async def khong_duoc_goi(ma_don, conv_id):  # pragma: no cover
        raise AssertionError("không được đụng CSDL khi thiếu conversation_id")

    monkeypatch.setattr(tools, "_doc_don_trong_csdl", khong_duoc_goi)
    ra = _chay("tra_cuu_don_hang", {"ma_don": "AS260826143012"}, None)
    assert ra.get("tim_thay") is not True


def test_don_mau_chi_dung_khi_catalog_van_la_du_lieu_mau(monkeypatch):
    """
    Đơn mẫu trong catalog giữ cho bản demo chạy được.

    Nhưng nó phải TỰ TẮT khi shop thay bằng dữ liệu thật — cờ `du_lieu_mau`
    mất đi là đường lui này đóng lại. Để nó sống sót sang dữ liệu thật là
    agent trả lời khách bằng đơn bịa.
    """
    from agent.core import tools

    async def khong_thay(ma_don, conv_id):
        return None

    monkeypatch.setattr(tools, "_doc_don_trong_csdl", khong_thay)
    monkeypatch.setattr(tools, "_catalog", lambda: {
        "du_lieu_mau": False,
        "don_hang": [{"ma": "AS20260818", "trang_thai": "Đang giao"}],
    })
    ra = _chay("tra_cuu_don_hang", {"ma_don": "AS20260818"}, uuid.uuid4())
    assert ra.get("tim_thay") is not True, "đơn bịa lọt vào dữ liệu thật"


def test_don_mau_van_chay_trong_ban_demo(monkeypatch):
    from agent.core import tools

    async def khong_thay(ma_don, conv_id):
        return None

    monkeypatch.setattr(tools, "_doc_don_trong_csdl", khong_thay)
    monkeypatch.setattr(tools, "_catalog", lambda: {
        "du_lieu_mau": True,
        "don_hang": [{"ma": "AS20260818", "trang_thai": "Đang giao"}],
    })
    ra = _chay("tra_cuu_don_hang", {"ma_don": "AS20260818"}, uuid.uuid4())
    assert ra["tim_thay"] is True


def test_cau_lenh_sql_co_chan_theo_conversation():
    """
    Canh chính câu SQL: đây là chỗ một lần sửa ẩu là rò rỉ dữ liệu khách.

    Test trên đều tiêm hàm giả, nên không cái nào chạm tới SQL thật.
    """
    import inspect

    from agent.core import tools

    nguon = inspect.getsource(tools._doc_don_trong_csdl)
    assert "conversation_id" in nguon, "SQL không chặn theo hội thoại"
