"""
Canh một kiểu chết im lặng: adapter dài hạn cầm refresh token đã bị xoay.

BỐI CẢNH ĐO ĐƯỢC (14.09.2026, trên OA thật)
-------------------------------------------
Zalo **giết refresh token cũ ngay** khi nó được dùng một lần — lần thứ hai
trả `error=-14014 Invalid refresh token`.

Trong khi đó hệ thống có HAI đường cùng cầm khoá của một OA:

  · `channels.get_for_account()` CACHE một adapter dài hạn — outbox worker
    và đường nhân viên trả lời dùng cái này, sống suốt đời tiến trình.
  · Nút “Xác minh provider” trên dashboard dựng một adapter RIÊNG
    (`NativeVerificationAdapterFactory`), làm mới token rồi ghi vào vault.

Bấm nút xác minh là xoay khoá. Adapter đang cache vẫn giữ khoá cũ trong bộ
nhớ, và `_doc_refresh_da_luu()` — khi credential đến từ vault — trả lại
CHÍNH bản trong bộ nhớ, không bao giờ đọc lại kho. Nên khi access token của
nó hết hạn (khoảng một giờ sau), nó làm mới bằng một khoá đã chết, và chết
luôn cho tới khi khởi động lại tiến trình.

Tái hiện được, và đây là kiểu hỏng tệ nhất theo CLAUDE.md: dashboard xanh
(vừa xác minh thành công xong!), tin nằm trong outbox thử tám lần rồi vào
dead-letter, khách chờ mãi không ai trả lời.

Lưới chặn: adapter phải ĐỌC LẠI kho khi khoá trong tay bị từ chối.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import pytest  # noqa: E402

from agent.channels.zalo_oa import ZaloOAAdapter  # noqa: E402

SONG = "refresh-con-song"
CHET = "refresh-da-chet"


def _client(chap_nhan: set[str], nhat_ky: list[str]) -> httpx.AsyncClient:
    """
    Máy chủ Zalo giả, bắt chước đúng hành vi đo được: chỉ chấp nhận refresh
    token nằm trong `chap_nhan`, và trả HTTP 200 kèm thân lỗi cho phần còn
    lại — Zalo không dùng mã HTTP để báo lỗi này.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/access_token"):
            than = request.content.decode()
            token = [p.split("=", 1)[1] for p in than.split("&")
                     if p.startswith("refresh_token=")][0]
            nhat_ky.append(token)
            if token not in chap_nhan:
                return httpx.Response(200, json={
                    "error": -14014, "error_name": "Invalid refresh token."})
            return httpx.Response(200, json={
                "access_token": "at-moi", "refresh_token": "refresh-ke-tiep",
                "expires_in": 3600})
        return httpx.Response(200, json={"error": 0, "data": {}})

    return httpx.AsyncClient(base_url="https://openapi.example/v3.0/oa",
                             transport=httpx.MockTransport(handler))


def _adapter(client, *, refresh, doc_lai=None, ghi=None) -> ZaloOAAdapter:
    return ZaloOAAdapter(
        account_id=uuid4(),
        credentials={"app_id": "app", "secret_key": "secret",
                     "refresh_token": refresh},
        client=client,
        on_credentials_rotated=ghi,
        on_credentials_reload=doc_lai,
    )


def test_khoa_bi_xoay_o_noi_khac_thi_doc_lai_kho_va_gui_duoc():
    """
    Đúng kịch bản đã tái hiện: worker cầm khoá cũ, dashboard vừa xoay khoá.

    Worker phải tự đọc lại kho và chạy tiếp — KHÔNG được chết tới lúc
    khởi động lại.
    """
    nhat_ky: list[str] = []
    client = _client({SONG}, nhat_ky)

    async def doc_lai():
        return {"app_id": "app", "secret_key": "secret", "refresh_token": SONG}

    adapter = _adapter(client, refresh=CHET, doc_lai=doc_lai)
    token = asyncio.run(adapter._lay_token())

    assert token == "at-moi"
    # Thử khoá trong tay trước, thất bại rồi mới đọc lại kho — không phải
    # cứ gọi là đọc kho, vì đọc kho mỗi lượt là bỏ phí bộ nhớ đệm.
    assert nhat_ky == [CHET, SONG]
    asyncio.run(adapter.aclose())


def test_kho_cung_giu_khoa_chet_thi_bao_loi_chu_khong_lap_vo_han():
    """Đọc lại kho ĐÚNG MỘT LẦN. Kho cũng sai thì phải nổ, không quay vòng."""
    nhat_ky: list[str] = []
    client = _client(set(), nhat_ky)

    async def doc_lai():
        return {"app_id": "app", "secret_key": "secret", "refresh_token": SONG}

    adapter = _adapter(client, refresh=CHET, doc_lai=doc_lai)
    with pytest.raises(RuntimeError):
        asyncio.run(adapter._lay_token())

    assert nhat_ky == [CHET, SONG]
    asyncio.run(adapter.aclose())


def test_khong_co_duong_doc_lai_thi_van_no_to():
    """Thiếu lưới không được biến thành im lặng: vẫn phải báo lỗi."""
    nhat_ky: list[str] = []
    adapter = _adapter(_client(set(), nhat_ky), refresh=CHET)
    with pytest.raises(RuntimeError):
        asyncio.run(adapter._lay_token())
    assert nhat_ky == [CHET]
    asyncio.run(adapter.aclose())


def test_khoa_doc_lai_trung_khoa_dang_cam_thi_khong_goi_zalo_lan_hai():
    """
    Kho trả đúng khoá vừa hỏng thì gọi lại Zalo là vô ích — và tốn một lượt
    trong hạn mức của endpoint OAuth.
    """
    nhat_ky: list[str] = []

    async def doc_lai():
        return {"app_id": "app", "secret_key": "secret", "refresh_token": CHET}

    adapter = _adapter(_client(set(), nhat_ky), refresh=CHET, doc_lai=doc_lai)
    with pytest.raises(RuntimeError):
        asyncio.run(adapter._lay_token())
    assert nhat_ky == [CHET]
    asyncio.run(adapter.aclose())


def test_doc_lai_thanh_cong_thi_khoa_moi_duoc_ghi_lai():
    """Khoá Zalo trả về ở lượt cứu phải được cất, không thì lần sau chết lại."""
    nhat_ky: list[str] = []
    da_ghi: list[dict] = []

    async def doc_lai():
        return {"app_id": "app", "secret_key": "secret", "refresh_token": SONG}

    async def ghi(payload):
        da_ghi.append(dict(payload))

    adapter = _adapter(_client({SONG}, nhat_ky), refresh=CHET,
                       doc_lai=doc_lai, ghi=ghi)
    asyncio.run(adapter._lay_token())

    assert da_ghi and da_ghi[-1]["refresh_token"] == "refresh-ke-tiep"
    asyncio.run(adapter.aclose())


# =====================================================================
#  Đường đọc lại phải được NỐI SẴN, không chỉ tồn tại
# =====================================================================
#
# Một lưới có mà không ai mắc vào thì bằng không có. Hai nơi dựng adapter
# Zalo OA từ vault, và cả hai đều phải đưa đường đọc lại vào.

def _tai_khoan_gia():
    from agent.omnichannel.accounts import (AccountStatus, Channel,
                                            ChannelAccount)
    return ChannelAccount(
        id=uuid4(), channel=Channel.ZALO_OA, display_name="OA thử",
        external_account_id="oa-1", status=AccountStatus.ACTIVE,
        capabilities={"send_text": True}, metadata={}, is_legacy=False,
    )


class _KhoGia:
    """Kho credential giả, đếm số lần bị đọc lại."""

    def __init__(self, account):
        self.account = account
        self.so_lan_doc = 0
        self.khoa = {"app_id": "app", "secret_key": "secret",
                     "refresh_token": SONG}

    async def get(self, account_id):
        return self.account if account_id == self.account.id else None

    async def load(self, account_id):
        self.so_lan_doc += 1
        return dict(self.khoa)

    async def store_rotated(self, account_id, credentials):
        self.khoa = dict(credentials)


def test_factory_noi_san_duong_doc_lai_cho_zalo_oa():
    from agent.channels.factory import AccountAdapterFactory

    kho = _KhoGia(_tai_khoan_gia())
    adapter = asyncio.run(
        AccountAdapterFactory(kho, kho).create(kho.account.id))

    truoc = kho.so_lan_doc
    lay_lai = asyncio.run(adapter._doc_lai_khoa())

    assert lay_lai == SONG, "factory chưa nối đường đọc lại kho"
    assert kho.so_lan_doc == truoc + 1
    asyncio.run(adapter.aclose())


def test_duong_xac_minh_provider_cung_noi_duong_doc_lai():
    """
    Chính nút này gây ra sự cố. Nếu adapter của nó không đọc lại được kho
    thì bấm hai lần liên tiếp là lần sau hỏng.
    """
    from agent.omnichannel.account_verification import (
        NativeVerificationAdapterFactory)

    kho = _KhoGia(_tai_khoan_gia())
    adapter = asyncio.run(
        NativeVerificationAdapterFactory(kho)(kho.account))

    truoc = kho.so_lan_doc
    assert asyncio.run(adapter._doc_lai_khoa()) == SONG
    assert kho.so_lan_doc == truoc + 1
    asyncio.run(adapter.aclose())
