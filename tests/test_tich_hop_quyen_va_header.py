"""
Proxy tích hợp và các đường "chỉ kiểm phiên" — rà soát 16.11.2026.

Canh hai lớp:

  HEADER  Proxy từng chuyển NGUYÊN `Cookie` (kể cả cookie phiên dashboard)
          và `X-Forwarded-*` do client đặt sang app đích. App tự thêm (hay
          một bản ZaloCRM/n8n bị chiếm) đọc được phiên dashboard trong nhật
          ký request; người dùng tự khai IP nguồn với app đích. Và địa chỉ
          link-local (169.254.169.254 — metadata đám mây) lọt qua chốt SSRF.

  QUYỀN   Ba đường chỉ hỏi "đã đăng nhập chưa", bỏ qua quyền: middleware
          bám Referer, WebSocket `/tich-hop/*` + `/cable`, và `/mcp` qua phiên.
          Người có phiên mà thiếu quyền phải bị chặn ở cả ba.

Không cần CSDL: phiên giả qua `doc_phien`.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent import main as app_main  # noqa: E402
from agent.api import tich_hop, tich_hop_kho  # noqa: E402
from agent.api.routes import TEN_COOKIE  # noqa: E402
from agent.core import xac_thuc  # noqa: E402


# ---------------------------------------------------------------- header

def test_cookie_phien_dashboard_khong_sang_app_dich():
    h = tich_hop.header_chuyen_tiep([
        ("cookie", f"_chatwoot_session=abc; {TEN_COOKIE}=BI-MAT-PHIEN; khac=1"),
        ("accept", "text/html"),
    ])
    assert "BI-MAT-PHIEN" not in h["cookie"]
    assert "_chatwoot_session=abc" in h["cookie"] and "khac=1" in h["cookie"]
    assert h["accept"] == "text/html"


def test_chi_co_cookie_phien_thi_bo_han_header_cookie():
    h = tich_hop.header_chuyen_tiep([("Cookie", f"{TEN_COOKIE}=x")])
    assert not any(k.lower() == "cookie" for k in h)


def test_bo_x_forwarded_do_client_dat():
    h = tich_hop.header_chuyen_tiep([
        ("X-Forwarded-For", "1.2.3.4"), ("x-forwarded-host", "gia.vn"),
        ("Forwarded", "for=1.2.3.4"), ("X-Real-IP", "1.2.3.4"), ("host", "localhost:8000"),
        ("user-agent", "ua"),
    ])
    assert set(k.lower() for k in h) == {"user-agent"}


def test_websocket_loc_cookie_phien():
    src = __import__("inspect").getsource(tich_hop.cau_websocket)
    assert "loc_cookie(" in src


class _HttpGia:
    """httpx.AsyncClient giả: trả câu trả lời cố định, ghi header đã gửi."""

    gui: dict = {}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def request(self, method, url, headers=None, content=None):
        import httpx

        _HttpGia.gui = dict(headers or {})
        return httpx.Response(200, headers=[
            ("content-type", "text/html"),
            ("set-cookie", f"{TEN_COOKIE}=PHIEN-CAY; Path=/"),
            ("set-cookie", "_chatwoot_session=moi; Path=/; Expires=Wed, 21 Oct 2026 07:28:00 GMT"),
        ], content=b"ok")


def test_proxy_that_khong_gui_phien_va_khong_cho_cay_phien(monkeypatch):
    """Đi trọn `chuyen_tiep`: header ra đã lọc, Set-Cookie tên phiên bị bỏ."""
    from starlette.requests import Request

    monkeypatch.setattr(tich_hop.httpx, "AsyncClient", _HttpGia)
    scope = {"type": "http", "method": "GET", "path": "/tich-hop/chatwoot/app",
             "query_string": b"", "headers": [
                 (b"cookie", f"{TEN_COOKIE}=BI-MAT; _chatwoot_session=cu".encode()),
                 (b"x-forwarded-for", b"9.9.9.9")]}

    async def nhan():
        return {"type": "http.request", "body": b"", "more_body": False}

    tra = asyncio.run(tich_hop.chuyen_tiep(Request(scope, nhan), "chatwoot", "app"))
    gui = {k.lower(): v for k, v in _HttpGia.gui.items()}
    assert "BI-MAT" not in gui.get("cookie", "") and "_chatwoot_session=cu" in gui["cookie"]
    assert "x-forwarded-for" not in gui
    cookies = [v.decode() for k, v in tra.raw_headers if k == b"set-cookie"]
    assert not any(c.startswith(TEN_COOKIE) for c in cookies), "app đích cấy được phiên"
    assert any(c.startswith("_chatwoot_session=moi") and "Expires" in c for c in cookies)


@pytest.mark.parametrize("ip", ["169.254.169.254", "169.254.0.1", "fe80::1", "fd00:ec2::254"])
def test_chan_link_local_va_metadata(monkeypatch, ip):
    import socket

    def gia(host, port, *a, **k):
        fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(fam, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(tich_hop_kho.socket, "getaddrinfo", gia)
    with pytest.raises(tich_hop_kho.LoiUngDung, match="metadata"):
        tich_hop_kho.kiem_dia_chi("http://may-chu-noi-bo:8080")


def test_dai_noi_bo_van_duoc_noi(monkeypatch):
    import socket

    monkeypatch.setattr(tich_hop_kho.socket, "getaddrinfo",
                        lambda h, p, *a, **k: [(socket.AF_INET, 1, 6, "", ("10.0.0.5", p))])
    assert tich_hop_kho.kiem_dia_chi("http://grafana:3000") == "http://grafana:3000"


# ---------------------------------------------------------------- quyền

def _phien(monkeypatch, *quyen: str):
    async def gia(token):
        if not token:
            return None
        return {"id": "00000000-0000-0000-0000-000000000001", "ten_dang_nhap": "nv",
                "vai_tro": "nhan_vien", "khoa": False, "quyen": frozenset(quyen)}
    monkeypatch.setattr(xac_thuc, "doc_phien", gia)


class _WSGia:
    def __init__(self):
        self.cookies = {TEN_COOKIE: "token"}
        self.headers = {}
        self.url = type("U", (), {"query": ""})()
        self.da_accept = False
        self.ma_dong = None

    async def accept(self):
        self.da_accept = True

    async def close(self, code=1000):
        self.ma_dong = code


def test_websocket_co_phien_thieu_tich_hop_doc_bi_chan(monkeypatch):
    _phien(monkeypatch, "hoi_thoai.doc")
    ws = _WSGia()
    asyncio.run(tich_hop.cau_websocket(ws, "chatwoot", "cable"))
    assert ws.da_accept is False and ws.ma_dong == 1008


def _client():
    from fastapi.testclient import TestClient

    # KHÔNG `with`: không chạy lifespan, không CSDL — chỉ middleware.
    return TestClient(app_main.app)


def test_duong_tuyet_doi_theo_referer_doi_quyen(monkeypatch):
    _phien(monkeypatch, "hoi_thoai.doc")

    async def la_chatwoot(_ref):
        return "chatwoot"

    async def khong_duoc_goi(*a, **k):
        raise AssertionError("đã chuyển tiếp cho người thiếu quyền")

    monkeypatch.setattr(tich_hop, "ung_dung_tu_referer", la_chatwoot)
    monkeypatch.setattr(tich_hop, "chuyen_tiep", khong_duoc_goi)
    k = _client()
    k.cookies.set(TEN_COOKIE, "token")
    r = k.get("/packs/js/app.js", headers={"Referer": "http://x/tich-hop/chatwoot/"})
    assert r.status_code == 403 and "tich_hop.doc" in r.text


def test_duong_tuyet_doi_co_quyen_thi_di_tiep(monkeypatch):
    from fastapi.responses import Response

    _phien(monkeypatch, "tich_hop.doc")

    async def la_chatwoot(_ref):
        return "chatwoot"

    async def tra(*a, **k):
        return Response("asset", status_code=200)

    monkeypatch.setattr(tich_hop, "ung_dung_tu_referer", la_chatwoot)
    monkeypatch.setattr(tich_hop, "chuyen_tiep", tra)
    k = _client()
    k.cookies.set(TEN_COOKIE, "token")
    r = k.get("/packs/js/app.js", headers={"Referer": "http://x/tich-hop/chatwoot/"})
    assert r.status_code == 200 and r.text == "asset"


def test_mcp_qua_phien_thieu_quyen_cau_hinh_bi_chan(monkeypatch):
    monkeypatch.setattr(app_main.settings, "mcp_token", "token-mcp-du-dai-cho-test-1234")
    _phien(monkeypatch, "khach.doc", "don.doc")
    k = _client()
    k.cookies.set(TEN_COOKIE, "token")
    r = k.post("/mcp/", json={})
    assert r.status_code == 403 and "cau_hinh.sua" in r.text


def test_mcp_qua_phien_co_quyen_thi_qua_chot(monkeypatch):
    monkeypatch.setattr(app_main.settings, "mcp_token", "token-mcp-du-dai-cho-test-1234")
    _phien(monkeypatch, "cau_hinh.sua")
    k = _client()
    k.cookies.set(TEN_COOKIE, "token")
    r = k.post("/mcp/", json={})
    assert r.status_code not in (401, 403)


def test_mcp_bearer_van_chay_khong_can_phien(monkeypatch):
    monkeypatch.setattr(app_main.settings, "mcp_token", "token-mcp-du-dai-cho-test-1234")
    _phien(monkeypatch)
    r = _client().post("/mcp/", json={},
                       headers={"Authorization": "Bearer token-mcp-du-dai-cho-test-1234"})
    assert r.status_code not in (401, 403)
