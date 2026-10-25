"""
Khai webhook của APP Meta bằng Graph API (agent/channels/webhook_app_meta.py).

25.10.2026: Meta gọi một tên miền tunnel cũ đã chết, và app thiếu trường
`feed` nên bình luận không bao giờ tới. Canh: khai đúng địa chỉ, giữ trường
cũ + thêm trường cần, ĐỌC LẠI để xác nhận, và không làm lộ khoá.
"""
from __future__ import annotations

import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from agent.channels import webhook_app_meta as w


@pytest.fixture(autouse=True)
def _app(monkeypatch):
    monkeypatch.setattr(w.settings, "meta_app_id", "111")
    monkeypatch.setattr(w.settings, "meta_app_secret", "BI-MAT-APP")


class _Meta:
    """Graph giả: giữ một bản đăng ký, POST thay nó (tuỳ chọn: từ chối / lờ đi)."""

    def __init__(self, callback="https://cu.trycloudflare.com/webhook/native/meta",
                 fields=("messages", "messaging_handovers"), tu_choi=False, lo_di=False):
        self.dk = {"callback_url": callback, "fields": list(fields)}
        self.tu_choi, self.lo_di = tu_choi, lo_di
        self.post: list[dict] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            return httpx.Response(200, json={"data": [{
                "object": "page", "active": True, "callback_url": self.dk["callback_url"],
                "fields": [{"name": f} for f in self.dk["fields"]]}]})
        body = {k: v[0] for k, v in parse_qs(req.content.decode()).items()}
        self.post.append(body)
        if self.tu_choi:
            return httpx.Response(400, json={"error": {"message": "callback verification failed"}})
        if not self.lo_di:
            self.dk = {"callback_url": body["callback_url"], "fields": body["fields"].split(",")}
        return httpx.Response(200, json={"success": True})


def _chay(meta: _Meta, url: str, token: str = "vt-chung"):
    async def f():
        async with httpx.AsyncClient(transport=httpx.MockTransport(meta)) as c:
            return await w.khai_callback(c, url, token)
    return asyncio.run(f())


def test_khai_dia_chi_moi_giu_truong_cu_them_feed():
    meta = _Meta()
    ok, mo_ta = _chay(meta, "https://moi.trycloudflare.com/webhook/native/meta")
    assert ok, mo_ta
    gui = meta.post[0]
    assert gui["object"] == "page" and gui["verify_token"] == "vt-chung"
    assert gui["callback_url"] == "https://moi.trycloudflare.com/webhook/native/meta"
    truong = gui["fields"].split(",")
    assert {"messages", "messaging_handovers", "feed", "messaging_postbacks"} <= set(truong)


def test_mo_ta_khong_lo_khoa_hay_verify_token():
    ok, mo_ta = _chay(_Meta(), "https://moi.trycloudflare.com/webhook/native/meta",
                      token="VERIFY-BI-MAT")
    assert ok
    assert "BI-MAT-APP" not in mo_ta and "VERIFY-BI-MAT" not in mo_ta


def test_meta_tu_choi_thi_bao_ly_do():
    ok, mo_ta = _chay(_Meta(tu_choi=True), "https://moi.trycloudflare.com/webhook/native/meta")
    assert not ok and "verification failed" in mo_ta


def test_bao_thanh_cong_nhung_doc_lai_khac_thi_khong_tin():
    """Xanh giả nguy hiểm hơn đỏ giả: đọc lại mới tính là xong."""
    ok, mo_ta = _chay(_Meta(lo_di=True), "https://moi.trycloudflare.com/webhook/native/meta")
    assert not ok and "đọc lại" in mo_ta


@pytest.mark.parametrize("url,token", [("http://moi/webhook/native/meta", "vt"),
                                       ("https://moi/webhook/native/meta", "")])
def test_khong_https_hoac_khong_token_thi_khong_goi_meta(url, token):
    meta = _Meta()
    ok, _ = _chay(meta, url, token)
    assert not ok and meta.post == []


def test_thieu_khoa_app_thi_no(monkeypatch):
    monkeypatch.setattr(w.settings, "meta_app_secret", "")
    with pytest.raises(ValueError):
        w.khoa_app()
