"""
Quan sát khi host: /metrics đóng mặc định, Sentry không mang bí mật ra ngoài.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent import quan_sat


@pytest.fixture
def app(monkeypatch):
    async def fetch(sql, *a):
        if "outbox_jobs" in sql:
            return [{"status": "dead", "n": 3}, {"status": "pending", "n": 1}]
        return [{"worker_name": 'outbox"x', "t": 12.4}]

    async def fetchrow(sql, *a):
        if "messages" in sql and "vao" in sql:
            return {"vao": 7, "ra": 5}
        if "cost_usd" in sql:
            return {"c": 0.0123}
        return {"n": 2}

    monkeypatch.setattr(quan_sat.db, "fetch", fetch)
    monkeypatch.setattr(quan_sat.db, "fetchrow", fetchrow)
    a = FastAPI()
    a.include_router(quan_sat.router)
    return a


def test_metrics_dong_khi_chua_cau_hinh(app, monkeypatch):
    monkeypatch.setattr(quan_sat.settings, "metrics_token", "")
    assert TestClient(app).get("/metrics").status_code == 404


def test_metrics_doi_token(app, monkeypatch):
    monkeypatch.setattr(quan_sat.settings, "metrics_token", "bi-mat-dai-du")
    k = TestClient(app)
    assert k.get("/metrics").status_code == 401
    assert k.get("/metrics", headers={"Authorization": "Bearer sai"}).status_code == 401
    r = k.get("/metrics", headers={"Authorization": "Bearer bi-mat-dai-du"})
    assert r.status_code == 200
    t = r.text
    assert "cskh_len 1" in t
    assert 'cskh_outbox_jobs{status="dead"} 3' in t
    assert 'cskh_tin_5_phut{huong="vao"} 7' in t
    assert "cskh_hoi_thoai_cho_nguoi 2" in t
    # Nhãn có dấu nháy phải được thoát, không phá định dạng Prometheus.
    assert 'vong="outbox\\"x"' in t


def test_csdl_hong_van_tra_so_do_len_0(app, monkeypatch):
    monkeypatch.setattr(quan_sat.settings, "metrics_token", "k")

    async def hong(*a, **k):
        raise ConnectionError("db down")
    monkeypatch.setattr(quan_sat.db, "fetch", hong)
    r = TestClient(app).get("/metrics", headers={"Authorization": "Bearer k"})
    assert r.status_code == 200 and "cskh_len 0" in r.text


def test_sentry_tat_khi_khong_co_dsn(monkeypatch):
    monkeypatch.setattr(quan_sat.settings, "sentry_dsn", "")
    assert quan_sat.bat_sentry() is False


def test_sentry_khong_gui_pii_va_che_bi_mat(monkeypatch):
    import sentry_sdk
    goi = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: goi.update(kw))
    monkeypatch.setattr(quan_sat.settings, "sentry_dsn", "https://k@glitchtip.vi-du.vn/1")
    assert quan_sat.bat_sentry() is True
    assert goi["send_default_pii"] is False and goi["include_local_variables"] is False
    su_kien = {"exception": {"values": [{"value": "gọi https://x/?access_token=EAAbimat123 hỏng"}]}}
    ra = goi["before_send"](su_kien, {})
    assert "EAAbimat123" not in ra["exception"]["values"][0]["value"]
