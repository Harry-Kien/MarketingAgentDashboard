"""
Mỗi tin khách vào KHÔNG được để lại một kết nối HTTP mở.

`zalo_oa_webhook()` dựng một adapter mới cho từng webhook, và
`ZaloOAAdapter.__init__` tạo luôn một `httpx.AsyncClient` kèm pool kết nối.
Không đóng thì mỗi tin khách rò một client — hỏng theo kiểu chậm và im
lặng: chạy ngon cả tuần, rồi hết file descriptor vào đúng đợt đông khách,
và dấu vết để lại chẳng liên quan gì tới Zalo.

Kênh này chưa có tin thật nào đi qua (đo 14.09.2026: `listrecentchat` rỗng)
nên rò rỉ chưa cắn. Đó là lý do phải canh bằng test chứ không đợi thấy đau.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
import pathlib
import sys
from uuid import uuid4

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from agent.api import zalo_oa_webhook as mod  # noqa: E402
from agent.channels.base import InboundMessage  # noqa: E402

APP_ID = "2109757420003470723"
SECRET = "s" * 32
TS = "1725350400000"
AID = uuid4()


class _AdapterGian_diep:
    """Adapter giả, ghi lại xem có bị đóng không."""

    def __init__(self, tin: list[InboundMessage]):
        self._tin = tin
        self.da_dong = False

    def parse_nhieu(self, payload):
        return list(self._tin)

    async def aclose(self):
        self.da_dong = True


def _dung_moi_truong(monkeypatch, tin):
    from agent.omnichannel.accounts import (AccountStatus, Channel,
                                            ChannelAccount)

    account = ChannelAccount(
        id=AID, channel=Channel.ZALO_OA, display_name="OA thử",
        external_account_id="oa-1", status=AccountStatus.ACTIVE,
        capabilities={}, metadata={}, is_legacy=False,
    )

    class _Repo:
        async def get(self, account_id):
            return account if account_id == AID else None

    class _Loader:
        async def load(self, account_id):
            return {"app_id": APP_ID, "secret_key": SECRET,
                    "refresh_token": "r"}

    gian_diep = _AdapterGian_diep(tin)

    class _Factory:
        def __init__(self, *a, **k):
            pass

        async def create(self, account_id):
            return gian_diep

    monkeypatch.setattr(mod, "_kho", lambda: (_Repo(), _Loader()))
    monkeypatch.setattr(mod, "AccountAdapterFactory", _Factory)

    import agent.main as m

    async def _khong_lam_gi(_msg):
        return None

    monkeypatch.setattr(m, "handle_inbound", _khong_lam_gi)

    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app), gian_diep


def _goi(client, than: bytes):
    mac = hashlib.sha256(
        (APP_ID + than.decode() + TS + SECRET).encode()).hexdigest()
    return client.post(
        f"/webhook/native/zalo-oa/{AID}", content=than,
        headers={"Content-Type": "application/json",
                 "X-ZEvent-Signature": f"mac={mac}",
                 "X-ZEvent-Timestamp": TS})


def _tin_that() -> InboundMessage:
    return InboundMessage(
        account_id=AID, channel="zalo_oa", conversation_ref="u1",
        customer_ref="u1", customer_name="Khách", text="giá bao nhiêu",
        dedupe_key="zalo_oa:m1",
        received_at=datetime.now(timezone.utc),
    )


@pytest.mark.parametrize("tin,mong_doi_queued", [
    ([], False),
    ([_tin_that()], True),
])
def test_adapter_luon_duoc_dong_sau_moi_webhook(monkeypatch, tin,
                                                mong_doi_queued):
    """Có tin hay không có tin, kết nối đều phải đóng."""
    client, gian_diep = _dung_moi_truong(monkeypatch, tin)
    than = json.dumps({"app_id": APP_ID, "event_name": "user_send_text",
                       "timestamp": TS}).encode()

    r = _goi(client, than)

    assert r.status_code == 200, r.text
    assert ("queued" in r.json()) is mong_doi_queued
    assert gian_diep.da_dong is True, "webhook rò một httpx.AsyncClient mỗi tin"
