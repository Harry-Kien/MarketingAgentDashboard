"""
Phần danh bạ của adapter ZaloCRM — gọi qua HTTP, không mạng thật.

`khach()` từng gọi `self.cau_hinh_du()`, một phương thức CHỈ có ở adapter
Chatwoot và Messenger. Mọi lời gọi đều nổ AttributeError — không test nào
chạm tới, mypy bắt được (23.10.2026). Test này canh cả hai nhánh: chưa cấu
hình thì trả None êm, đã cấu hình thì đọc đúng khách.
"""
from __future__ import annotations

import asyncio

import httpx

from agent.channels import zalocrm


def _adapter(monkeypatch, khoa: str, xu_ly=None) -> zalocrm.ZaloCRMAdapter:
    monkeypatch.setattr(zalocrm.settings, "zalocrm_api_key", khoa)
    ad = zalocrm.ZaloCRMAdapter()
    if xu_ly is not None:
        ad._client = httpx.AsyncClient(base_url="http://zalocrm.test",
                                       transport=httpx.MockTransport(xu_ly))
    return ad


def test_khach_chua_cau_hinh_thi_tra_none_khong_no(monkeypatch):
    ad = _adapter(monkeypatch, "")
    assert asyncio.run(ad.khach("c-1")) is None


def test_khach_doc_dung_khach_khi_da_cau_hinh(monkeypatch):
    goi: list[str] = []

    def xu_ly(req: httpx.Request) -> httpx.Response:
        goi.append(req.url.path)
        return httpx.Response(200, json={"contact": {"id": "c-1", "fullName": "Chị Lan"}})

    ad = _adapter(monkeypatch, "khoa-thu", xu_ly)
    assert asyncio.run(ad.khach("c-1")) == {"id": "c-1", "fullName": "Chị Lan"}
    assert goi == ["/api/public/contacts/c-1"]


def test_khach_thieu_id_thi_khong_goi_mang(monkeypatch):
    goi: list[str] = []
    ad = _adapter(monkeypatch, "khoa-thu", lambda r: goi.append(1) or httpx.Response(200))
    assert asyncio.run(ad.khach("")) is None
    assert goi == []
