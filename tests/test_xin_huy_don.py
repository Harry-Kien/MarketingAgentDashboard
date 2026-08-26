"""
Khách xin huỷ: agent GHI NHẬN rồi chuyển người — không tự huỷ, và không để rơi.

VÌ SAO NGƯỜI QUYẾT, KHÔNG PHẢI AGENT
------------------------------------
Xin huỷ hầu như luôn là lúc khách đang không hài lòng. Đó là khoảnh khắc
cứu được đơn — đổi màu khác, đổi size, giải thích một hiểu lầm. Người làm
được việc đó; agent huỷ cái rụp thì mất đơn mà không ai biết vì sao mất.

VÌ SAO GHI LÊN CHÍNH ĐƠN, KHÔNG CHỈ CHUYỂN HỘI THOẠI
-----------------------------------------------------
Đây là chỗ hở của "chuyển người" thuần tuý: yêu cầu chỉ nằm trong đoạn chat.
Người đóng gói sáng hôm sau nhìn màn hình Đơn hàng, KHÔNG thấy gì bất
thường, và gói hàng gửi đi.

Kết quả: đơn khách đã xin huỷ vẫn lên đường. Khách từ chối nhận, shop chịu
phí hoàn COD, và khách thì chắc chắn không quay lại. Không có lỗi nào bị
ném ở bất kỳ đâu — chỉ là hai người nhìn hai màn hình khác nhau.

Nên yêu cầu phải nằm TRÊN ĐƠN, chỗ người đóng gói thật sự nhìn.

VÌ SAO AGENT KHÔNG ĐƯỢC NÓI "ĐÃ HUỶ"
------------------------------------
Đơn chưa huỷ. Nói đã huỷ là hứa thay người khác một việc chưa xảy ra —
đúng kiểu "hứa mà không làm" mà lưới thứ tư trong agent.py đang canh.
"""
from __future__ import annotations

import asyncio
import inspect
import uuid


def _chay(name, args, conversation_id=None):
    from agent.core import tools
    return asyncio.run(tools.run_tool(name, args, conversation_id=conversation_id))


def test_co_cong_cu_xin_huy():
    from agent.core.tools import TOOLS

    assert any(t["name"] == "xin_huy_don" for t in TOOLS)


def test_ghi_nhan_chu_KHONG_huy(monkeypatch):
    from agent.core import tools

    da_goi = {}

    async def gia_lap(ma_don, conv_id, ly_do):
        da_goi["ma"] = ma_don
        return True

    monkeypatch.setattr(tools, "_danh_dau_xin_huy", gia_lap)
    ra = _chay("xin_huy_don", {"ma_don": "AS1", "ly_do": "đổi ý"}, uuid.uuid4())

    assert da_goi["ma"] == "AS1"
    assert ra["da_ghi_nhan"] is True
    assert ra["da_huy"] is False, "agent không được tự huỷ"


def test_luon_chuyen_nguoi(monkeypatch):
    """Ghi nhận mà không chuyển người là yêu cầu nằm im mãi mãi."""
    from agent.core import tools

    async def gia_lap(ma_don, conv_id, ly_do):
        return True

    monkeypatch.setattr(tools, "_danh_dau_xin_huy", gia_lap)
    ra = _chay("xin_huy_don", {"ma_don": "AS1", "ly_do": "x"}, uuid.uuid4())
    assert ra.get("can_chuyen_nhan_vien") is True


def test_agent_bi_CAM_noi_da_huy(monkeypatch):
    """Kết quả tool phải dặn thẳng, vì model sẽ trượt sang 'đã huỷ' nếu không."""
    from agent.core import tools

    async def gia_lap(ma_don, conv_id, ly_do):
        return True

    monkeypatch.setattr(tools, "_danh_dau_xin_huy", gia_lap)
    ra = _chay("xin_huy_don", {"ma_don": "AS1", "ly_do": "x"}, uuid.uuid4())

    loi_dan = ra.get("ghi_chu", "")
    assert "đã huỷ" in loi_dan or "đã hủy" in loi_dan, "phải nói rõ điều bị cấm"


def test_don_khong_thuoc_hoi_thoai_thi_KHONG_danh_dau(monkeypatch):
    """
    Không chặn thì bất kỳ ai cũng gắn cờ xin huỷ lên đơn của người lạ.

    Đó là phá hoại được từ xa: chỉ cần đoán mã đơn.
    """
    from agent.core import tools

    async def gia_lap(ma_don, conv_id, ly_do):
        return False   # SQL không khớp hội thoại -> không có dòng nào bị sửa

    monkeypatch.setattr(tools, "_danh_dau_xin_huy", gia_lap)
    ra = _chay("xin_huy_don", {"ma_don": "AS-CUA-NGUOI-KHAC", "ly_do": "x"},
               uuid.uuid4())

    assert ra["da_ghi_nhan"] is False
    assert ra.get("can_chuyen_nhan_vien") is True, "vẫn phải có người xem"


def test_thieu_hoi_thoai_thi_khong_dung_toi_csdl(monkeypatch):
    from agent.core import tools

    async def khong_duoc_goi(ma_don, conv_id, ly_do):  # pragma: no cover
        raise AssertionError("không được đụng CSDL khi thiếu conversation_id")

    monkeypatch.setattr(tools, "_danh_dau_xin_huy", khong_duoc_goi)
    ra = _chay("xin_huy_don", {"ma_don": "AS1", "ly_do": "x"}, None)
    assert ra["da_ghi_nhan"] is False


def test_sql_chan_theo_hoi_thoai_va_khong_dong_vao_trang_thai():
    """
    Canh chính câu SQL. Hai điều phải đúng cùng lúc:

      - có `conversation_id` -> không gắn cờ lên đơn người khác
      - không GHI vào `trang_thai` -> tool này tuyệt đối không huỷ đơn

    Đọc `trang_thai` thì được (để loại đơn đã huỷ) — cấm là cấm GÁN. Bản
    đầu của test này cấm cả đọc, tức cấm luôn cái chốt chặn đang cần.
    """
    from agent.core import tools

    nguon = inspect.getsource(tools._danh_dau_xin_huy)
    assert "conversation_id" in nguon

    phan_set = nguon.split("SET", 1)[1].split("WHERE", 1)[0]
    assert "trang_thai" not in phan_set, "SQL đang GÁN trang_thai — nó sẽ huỷ đơn"


def test_don_da_giao_roi_thi_khong_gan_co_duoc():
    """Đơn đã huỷ hoặc đã giao thì gắn cờ xin huỷ là vô nghĩa và gây rối."""
    from agent.core import tools

    nguon = inspect.getsource(tools._danh_dau_xin_huy)
    assert "da_huy" in nguon, "SQL phải loại đơn đã huỷ"


def test_schema_co_cot_luu_yeu_cau():
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[1] / "agent" / "schema.sql").read_text(
        encoding="utf-8")
    assert "yeu_cau_huy_luc" in sql
    assert "yeu_cau_huy_ly_do" in sql


def test_man_hinh_don_hang_hien_co_xin_huy():
    """Ghi vào CSDL mà màn hình không hiện thì người đóng gói vẫn không thấy."""
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "dashboard" / "app.js").read_text(
        encoding="utf-8")
    assert "yeu_cau_huy_luc" in js, "màn hình Đơn hàng chưa hiện cờ xin huỷ"
