"""
Hiện TÊN THẬT của khách, không phải chữ "Khách" chung chung.

VÌ SAO ĐÁNG LÀM
---------------
Người trực nhìn danh sách hội thoại và thấy bốn dòng "Khách" thì không biết
ai là ai — phải mở từng cái ra đọc. Mọi công cụ chăm sóc khách hàng chuyên
nghiệp đều hiện tên, vì đó là thứ đầu tiên mắt tìm.

Nó cũng đổi chất lượng cuộc trò chuyện: gọi đúng tên khách là khác biệt
giữa một quầy dịch vụ và một cái máy.

VÌ SAO CHƯA CÓ
--------------
Webhook Meta CHỈ gửi mã người dùng (PSID), không gửi tên. Muốn có tên phải
gọi Graph API riêng — mã cũ đã ghi chú đúng điều này rồi nhưng chưa làm.

CHỈ GỌI KHI CẦN
---------------
Gọi Graph mỗi tin là thêm một lượt mạng vào đường trả lời khách, và đốt hạn
mức API. Chỉ gọi khi tên còn là giá trị mặc định.
"""
from __future__ import annotations

import pytest

from agent.channels.ten_khach import can_lay_ten, ghep_ten


@pytest.mark.parametrize("mac_dinh", ["Khách", "Khách Instagram", "Khách WhatsApp", ""])
def test_ten_mac_dinh_thi_can_lay(mac_dinh):
    assert can_lay_ten(mac_dinh) is True


def test_da_co_ten_that_thi_khong_goi_lai():
    """Gọi Graph mỗi tin là thêm một lượt mạng vào đường trả lời khách."""
    assert can_lay_ten("Trần Trung Kiên") is False


def test_ghep_ho_va_ten_theo_thu_tu_viet_nam():
    """
    Meta trả `first_name`/`last_name` theo lối phương Tây. Người Việt đọc
    họ trước — ghép sai thứ tự là gọi khách bằng tên lót.
    """
    assert ghep_ten({"first_name": "Kiên", "last_name": "Trần Trung"}) == "Trần Trung Kiên"


def test_thieu_mot_nua_van_dung_duoc():
    assert ghep_ten({"first_name": "Kiên"}) == "Kiên"
    assert ghep_ten({"last_name": "Trần"}) == "Trần"


def test_khong_co_gi_thi_tra_rong_de_giu_ten_cu():
    """
    Trả rỗng chứ KHÔNG trả "Khách": chỗ gọi sẽ giữ nguyên tên đang có.

    Trả một giá trị mặc định ở đây là ghi đè mất tên thật mà lần trước đã
    lấy được — Graph hỏng một lần là khách mất tên vĩnh viễn.
    """
    assert ghep_ten({}) == ""
    assert ghep_ten({"first_name": "  ", "last_name": ""}) == ""


def test_bo_khoang_trang_thua():
    assert ghep_ten({"first_name": " Kiên ", "last_name": " Trần "}) == "Trần Kiên"


# ---------------------------------------------------------------
#  Adapter gọi Graph API
# ---------------------------------------------------------------

def test_adapter_messenger_co_ham_lay_ten():
    from agent.channels.messenger import MessengerAdapter

    assert hasattr(MessengerAdapter, "lay_ten_khach")


def test_lay_ten_goi_dung_duong_graph():
    """Gọi `/{psid}` xin đúng ba trường tên — không xin ảnh, giới tính, múi giờ."""
    import asyncio
    from uuid import uuid4

    class _R:
        status_code = 200

        @staticmethod
        def json():
            return {"name": "Trần Trung Kiên",
                    "first_name": "Kiên", "last_name": "Trần Trung"}

    class _Client:
        def __init__(self):
            self.calls = []

        async def get(self, duong, params=None):
            self.calls.append((duong, params or {}))
            return _R()

        async def aclose(self):
            return None

    from agent.channels.messenger import MessengerAdapter

    client = _Client()
    ad = MessengerAdapter(
        account_id=uuid4(),
        credentials={"access_token": "T", "app_secret": "S"},
        client=client,
    )
    ten = asyncio.run(ad.lay_ten_khach("PSID-1"))

    assert ten == "Trần Trung Kiên"
    duong, params = client.calls[0]
    assert "PSID-1" in duong
    assert params.get("fields") == "name,first_name,last_name"
    for du in ("profile_pic", "gender", "timezone", "locale"):
        assert du not in params.get("fields", ""), f"xin dư trường {du}"


def test_graph_hong_thi_tra_rong_chu_khong_nem_loi():
    """
    Không lấy được tên KHÔNG được làm hỏng việc nhận tin.

    Tên chỉ là thứ hiển thị cho đẹp; tin nhắn của khách mới là việc chính.
    Ném lỗi ở đây là đánh đổi sai hoàn toàn.
    """
    import asyncio
    from uuid import uuid4

    class _Client:
        async def get(self, duong, params=None):
            raise RuntimeError("Graph tu choi")

        async def aclose(self):
            return None

    from agent.channels.messenger import MessengerAdapter

    ad = MessengerAdapter(
        account_id=uuid4(),
        credentials={"access_token": "T", "app_secret": "S"},
        client=_Client(),
    )
    assert asyncio.run(ad.lay_ten_khach("PSID-1")) == ""


def test_dispatch_lam_giau_ten_truoc_khi_tra_ve():
    """
    Bộ điều phối phải hỏi tên NGAY sau khi phân tích, trước khi tin đi tiếp.

    Làm sau đó thì hội thoại đã được tạo với tên "Khách" rồi, và sửa lại là
    một đường ghi nữa — phức tạp hơn mà kết quả kém hơn.

    Chỉ gọi khi tên còn mặc định: `can_lay_ten` canh việc đó.
    """
    import inspect

    from agent.api import native_webhooks

    nguon = inspect.getsource(native_webhooks)
    assert "can_lay_ten" in nguon, "chưa lọc theo tên mặc định"
    assert "lay_ten_khach" in nguon, "chưa gọi Graph lấy tên"


def test_uu_tien_truong_name_cua_facebook():
    """
    `name` là tên Facebook hiển thị — đã đúng thứ tự theo ngôn ngữ của khách.

    Tự ghép từ first/last là ta ĐOÁN quy ước đặt tên. Người Việt đọc họ
    trước, người Mỹ đọc tên trước, và có người để cả biệt danh trong
    `first_name`. Facebook đã xử lý chuyện đó rồi — dùng lại kết quả của họ
    chính xác hơn mọi quy tắc ta tự viết.

    Vẫn giữ đường ghép làm dự phòng: một số tài khoản không trả `name`.
    """
    from agent.channels.ten_khach import ghep_ten

    assert ghep_ten({"name": "Trần Trung Kiên",
                     "first_name": "Kiên",
                     "last_name": "Trần Trung"}) == "Trần Trung Kiên"


def test_khong_co_name_thi_ghep_nhu_cu():
    from agent.channels.ten_khach import ghep_ten

    assert ghep_ten({"first_name": "Kiên", "last_name": "Trần Trung"}) == "Trần Trung Kiên"


def test_name_rong_khong_lam_mat_duong_du_phong():
    from agent.channels.ten_khach import ghep_ten

    assert ghep_ten({"name": "   ", "first_name": "Kiên"}) == "Kiên"


def test_xin_ca_ba_truong_khi_goi_graph():
    """Xin `name` mà quên khai trong `fields` thì Graph không trả về."""
    import inspect

    from agent.channels.messenger import MessengerAdapter

    nguon = inspect.getsource(MessengerAdapter.lay_ten_khach)
    assert "name,first_name,last_name" in nguon
