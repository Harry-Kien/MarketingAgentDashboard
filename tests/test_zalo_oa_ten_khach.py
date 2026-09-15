"""
Khách Zalo OA phải có TÊN trên dashboard, không phải bốn dòng “Khách”.

Repo này đã có sẵn khuôn cho việc đó — `agent/channels/ten_khach.py`,
`lay_ten_khach()` trên adapter, và `_lam_giau_ten()` gọi nó ở đường webhook.
Facebook dùng đủ bộ. Zalo OA thì không: webhook của Zalo chỉ gửi `sender.id`,
`parse()` đặt cứng "Khách", và đường webhook OA chưa gọi lớp làm giàu tên.

Hậu quả không nổ, chỉ âm ỉ: người trực mở danh sách hội thoại thấy toàn
“Khách”, phải bấm vào từng cái mới biết ai là ai. Mà Official Account mới
là kênh chạy thật của cửa hàng — nó phải bằng hoặc hơn Facebook, không
được kém hơn.

Đường Zalo dùng: GET v3.0/oa/user/detail?data={"user_id": ...}
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
from uuid import uuid4

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from agent.channels.ten_khach import can_lay_ten  # noqa: E402
from agent.channels.zalo_oa import ZaloOAAdapter  # noqa: E402


def _adapter(handler) -> ZaloOAAdapter:
    return ZaloOAAdapter(
        account_id=uuid4(),
        credentials={"app_id": "a", "secret_key": "s", "refresh_token": "r"},
        client=httpx.AsyncClient(base_url="https://openapi.example/v3.0/oa",
                                 transport=httpx.MockTransport(handler)),
    )


def _may_chu(ho_so: dict, *, loi_http=False):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/access_token"):
            return httpx.Response(200, json={"access_token": "at",
                                             "expires_in": 3600})
        if loi_http:
            return httpx.Response(500, text="oops")
        assert request.url.path.endswith("/user/detail"), request.url
        # Zalo nhận tham số qua `data` là một chuỗi JSON, không phải query rời.
        assert json.loads(request.url.params["data"])["user_id"] == "u1"
        return httpx.Response(200, json=ho_so)

    return handler


# ---------------------------------------------------------------
#  Lấy được tên
# ---------------------------------------------------------------

def test_lay_duoc_display_name():
    ad = _adapter(_may_chu({"error": 0, "data": {"user_id": "u1",
                                                 "display_name": "Ngọc Hân"}}))
    assert asyncio.run(ad.lay_ten_khach("u1")) == "Ngọc Hân"
    asyncio.run(ad.aclose())


def test_lui_ve_ten_khac_khi_thieu_display_name():
    """Zalo có nơi trả `name`/`user_alias`; thiếu một trường không phải là bó tay."""
    for khoa in ("name", "user_alias"):
        ad = _adapter(_may_chu({"error": 0, "data": {khoa: "Ngọc Hân"}}))
        assert asyncio.run(ad.lay_ten_khach("u1")) == "Ngọc Hân", khoa
        asyncio.run(ad.aclose())


# ---------------------------------------------------------------
#  Hỏng thì trả rỗng — tên chỉ để hiển thị, tin nhắn mới là việc chính
# ---------------------------------------------------------------

def test_zalo_bao_loi_nghiep_vu_thi_tra_rong_khong_nem():
    """Zalo trả HTTP 200 kèm `error != 0`. Đọc thành tên là ghi rác vào hồ sơ."""
    ad = _adapter(_may_chu({"error": -201, "message": "user_id is not valid"}))
    assert asyncio.run(ad.lay_ten_khach("u1")) == ""
    asyncio.run(ad.aclose())


def test_loi_mang_thi_tra_rong_khong_nem():
    ad = _adapter(_may_chu({}, loi_http=True))
    assert asyncio.run(ad.lay_ten_khach("u1")) == ""
    asyncio.run(ad.aclose())


def test_thieu_user_id_thi_khong_goi_mang():
    goi: list = []

    def handler(request):
        goi.append(request.url)
        return httpx.Response(200, json={"access_token": "at", "expires_in": 1})

    ad = _adapter(handler)
    assert asyncio.run(ad.lay_ten_khach("")) == ""
    assert goi == [], "gọi mạng cho một user_id rỗng là phí một chặng"
    asyncio.run(ad.aclose())


# ---------------------------------------------------------------
#  Phải được NỐI vào đường webhook, không chỉ tồn tại
# ---------------------------------------------------------------

def test_ten_mac_dinh_cua_zalo_oa_nam_trong_danh_sach_can_lay_ten():
    """
    `parse()` đặt "Khách". Nếu giá trị ấy không nằm trong `TEN_MAC_DINH` thì
    lớp làm giàu bỏ qua, và tính năng im lặng không chạy.
    """
    assert can_lay_ten("Khách") is True


def test_duong_webhook_oa_co_goi_lop_lam_giau_ten():
    nguon = (ROOT / "agent" / "api" / "zalo_oa_webhook.py").read_text(
        encoding="utf-8")
    assert "lam_giau_ten" in nguon, "webhook OA chưa gọi lớp làm giàu tên"
