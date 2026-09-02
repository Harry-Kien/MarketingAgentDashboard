"""
Nối Trang xong phải TỰ đăng ký webhook — nếu không thì tin khách không tới.

VÌ SAO ĐÂY LÀ HỎNG IM LẶNG ĐIỂN HÌNH
------------------------------------
OAuth cho ta Page access token. Có token là GỬI được tin đi. Nhưng NHẬN tin
thì cần một bước nữa hoàn toàn khác: đăng ký Trang vào webhook của app, tức
`POST /{page-id}/subscribed_apps`.

Thiếu bước đó thì mọi thứ trông như đã xong:

  - Trang hiện trên dashboard, trạng thái xanh
  - Xác minh kết nối PASS (vì token thật và gọi Graph được)
  - Gửi tin chủ động PASS

...chỉ có tin khách nhắn vào là không bao giờ tới, và không có dòng lỗi nào
ở đâu cả. Người vận hành sẽ tưởng khách không nhắn.

VÌ SAO BÁO SỐ RIÊNG, KHÔNG GỘP VÀO "ĐÃ NỐI N TRANG"
----------------------------------------------------
"Đã nối 26 Trang" trong khi 4 Trang không đăng ký được là một câu XANH GIẢ.
Repo này có nguyên tắc: xanh giả nguy hiểm hơn đỏ giả, vì đỏ giả thì người
ta đi kiểm còn xanh giả thì không ai kiểm.
"""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class _R:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data if data is not None else {"success": True}

    def json(self):
        return self._data


class _Client:
    def __init__(self, tra=None, no=None):
        self.calls = []
        self._tra = tra or _R()
        self._no = no

    async def post(self, duong, params=None, **kw):
        self.calls.append((duong, params or {}))
        if self._no:
            raise self._no
        return self._tra


def test_goi_dung_endpoint_subscribed_apps():
    from agent.channels.dang_ky_webhook_meta import dang_ky_webhook_trang

    client = _Client()
    ok, _ly_do = asyncio.run(
        dang_ky_webhook_trang(page_id="123", page_token="T", client=client))

    assert ok is True
    duong, params = client.calls[0]
    assert duong == "/123/subscribed_apps"
    assert params["access_token"] == "T"


def test_dang_ky_truong_messages():
    """Không có `messages` thì tin khách không về — đó là toàn bộ mục đích."""
    from agent.channels.dang_ky_webhook_meta import dang_ky_webhook_trang

    client = _Client()
    asyncio.run(dang_ky_webhook_trang(page_id="1", page_token="T", client=client))
    assert "messages" in client.calls[0][1]["subscribed_fields"]


def test_khong_dang_ky_message_echoes():
    """
    `message_echoes` đẩy lại chính tin Trang vừa gửi.

    Đăng ký nó là agent đọc câu trả lời của chính mình rồi trả lời tiếp —
    vòng lặp vọng đã xảy ra thật ở kênh Zalo trong dự án này.
    """
    from agent.channels.dang_ky_webhook_meta import dang_ky_webhook_trang

    client = _Client()
    asyncio.run(dang_ky_webhook_trang(page_id="1", page_token="T", client=client))
    assert "echo" not in client.calls[0][1]["subscribed_fields"]


def test_graph_tu_choi_thi_bao_THAT_BAI_kem_ly_do():
    from agent.channels.dang_ky_webhook_meta import dang_ky_webhook_trang

    client = _Client(tra=_R(403, {"error": {"message": "thieu quyen"}}))
    ok, ly_do = asyncio.run(
        dang_ky_webhook_trang(page_id="1", page_token="T", client=client))

    assert ok is False
    assert "thieu quyen" in ly_do


def test_graph_tra_success_false_van_la_that_bai():
    """HTTP 200 mà `success: false` là đúng kiểu xanh giả."""
    from agent.channels.dang_ky_webhook_meta import dang_ky_webhook_trang

    client = _Client(tra=_R(200, {"success": False}))
    ok, _ = asyncio.run(
        dang_ky_webhook_trang(page_id="1", page_token="T", client=client))
    assert ok is False


def test_mang_hong_thi_bao_that_bai_chu_khong_nem():
    """Một Trang hỏng không được chặn 25 Trang còn lại."""
    from agent.channels.dang_ky_webhook_meta import dang_ky_webhook_trang

    client = _Client(no=RuntimeError("mat mang"))
    ok, ly_do = asyncio.run(
        dang_ky_webhook_trang(page_id="1", page_token="T", client=client))
    assert ok is False
    assert "mat mang" in ly_do


def test_thieu_token_thi_khong_goi_mang():
    from agent.channels.dang_ky_webhook_meta import dang_ky_webhook_trang

    client = _Client()
    ok, _ = asyncio.run(
        dang_ky_webhook_trang(page_id="1", page_token="", client=client))
    assert ok is False
    assert client.calls == []


# --- Ràng buộc phải nằm trên ĐƯỜNG CHẠY của OAuth ---

def test_oauth_co_goi_dang_ky_sau_khi_tao_tai_khoan():
    from agent.api import oauth_meta

    nguon = inspect.getsource(oauth_meta._tao_tai_khoan_tu_danh_sach)
    assert "dang_ky_webhook_trang" in nguon


def test_oauth_bao_rieng_so_trang_dang_ky_duoc():
    """Gộp vào 'đã nối N Trang' là xanh giả — xem docstring đầu file."""
    from agent.api import oauth_meta

    nguon = inspect.getsource(oauth_meta)
    assert "chua_dang_ky" in nguon, "phải tách được Trang chưa đăng ký webhook"


# --- Trang ĐÃ nối từ trước cũng phải đăng ký được, không phải làm lại OAuth ---

def test_co_endpoint_dang_ky_lai_cho_trang_da_noi():
    """
    26 Trang nối trước khi có tính năng này vẫn đang KHÔNG nhận được tin.

    Sửa mà chỉ giúp lần nối sau thì người đang có Trang treo vẫn treo. Bắt
    họ gỡ ra nối lại là mất luôn lịch sử hội thoại của những Trang đó.
    """
    from agent.api.channel_accounts import router

    duong = {getattr(r, "path", "") for r in router.routes}
    assert "/api/channel-accounts/{account_id}/dang-ky-webhook" in duong


def test_endpoint_doi_quyen_quan_tri():
    from agent.api import channel_accounts

    nguon = inspect.getsource(channel_accounts.dang_ky_webhook)
    assert "bat_buoc_quan_tri" in nguon


def test_endpoint_khong_tra_token_ra_ngoai():
    """Response phải dựng từ kết quả, không phải từ dict credential."""
    from agent.api import channel_accounts

    nguon = inspect.getsource(channel_accounts.dang_ky_webhook)
    than = "\n".join(
        d for d in nguon.splitlines()
        if not d.strip().startswith("#") and '"""' not in d
    )
    assert "return creds" not in than
    assert '"access_token":' not in than


def test_dashboard_co_nut_dang_ky_webhook():
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert "dang-ky-webhook" in js, "dashboard chưa gọi endpoint đăng ký lại"
