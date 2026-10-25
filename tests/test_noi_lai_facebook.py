"""
Phép kiểm nhanh "Internet có tới được địa chỉ công khai không" của người canh.

Resolver nhà mạng từng mù tên miền tunnel vừa cấp: kết luận "chết" từ đó là
dựng lại một tunnel đang khoẻ — đổi tên miền vô cớ, Meta gọi vào chỗ cũ.
"""
from __future__ import annotations

import socket
import urllib.error

from scripts import chay_tunnel as ct
from scripts import noi_lai_facebook as nl


def _dns_hong(*_a, **_k):
    raise urllib.error.URLError(socket.gaierror(11001, "getaddrinfo failed"))


def test_khong_phai_https_thi_khong_song():
    assert nl.cong_khai_song_nhanh("http://host.docker.internal:8000") is False


def test_dns_may_mu_nhung_doh_va_goi_ip_duoc_thi_song(monkeypatch):
    monkeypatch.setattr(nl.urllib.request, "urlopen", _dns_hong)
    monkeypatch.setattr(ct, "_ip_qua_doh", lambda host: ["104.16.0.1"])
    monkeypatch.setattr(ct, "_goi_qua_ip", lambda host, ip, **k: True)
    assert nl.cong_khai_song_nhanh("https://moi.trycloudflare.com") is True


def test_ten_mien_khong_con_ton_tai_thi_chet(monkeypatch):
    monkeypatch.setattr(nl.urllib.request, "urlopen", _dns_hong)
    monkeypatch.setattr(ct, "_ip_qua_doh", lambda host: [])
    assert nl.cong_khai_song_nhanh("https://da-chet.trycloudflare.com") is False


def test_loi_khong_phai_dns_thi_khong_hoi_doh(monkeypatch):
    hoi: list[str] = []

    def _tu_choi(*_a, **_k):
        raise urllib.error.URLError(ConnectionRefusedError())

    monkeypatch.setattr(nl.urllib.request, "urlopen", _tu_choi)
    monkeypatch.setattr(ct, "_ip_qua_doh", lambda host: hoi.append(host) or [])
    assert nl.cong_khai_song_nhanh("https://x.trycloudflare.com") is False
    assert hoi == []
