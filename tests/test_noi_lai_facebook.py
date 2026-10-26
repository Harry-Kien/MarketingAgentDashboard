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


class _Tra:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_cham_mot_lan_khong_bi_coi_la_chet(monkeypatch):
    """26.10.2026: tunnel chậm quá 10 giây một lần, lần sau trả 200 — không được báo chết."""
    lan = []

    def _cham_roi_tra(*_a, **_k):
        lan.append(1)
        if len(lan) == 1:
            raise urllib.error.URLError(TimeoutError("timed out"))
        return _Tra()

    monkeypatch.setattr(nl.urllib.request, "urlopen", _cham_roi_tra)
    monkeypatch.setattr(ct, "_ip_qua_doh", lambda host: [])
    monkeypatch.setattr(nl.time, "sleep", lambda s: None)
    assert nl.cong_khai_song_nhanh("https://x.trycloudflare.com") is True
    assert len(lan) == 2


def test_qua_han_thi_cung_thu_duong_ip(monkeypatch):
    def _qua_han(*_a, **_k):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(nl.urllib.request, "urlopen", _qua_han)
    monkeypatch.setattr(ct, "_ip_qua_doh", lambda host: ["104.16.0.1"])
    monkeypatch.setattr(ct, "_goi_qua_ip", lambda host, ip, **k: True)
    assert nl.cong_khai_song_nhanh("https://x.trycloudflare.com") is True


def test_moi_duong_deu_hong_qua_moi_lan_thu_moi_la_chet(monkeypatch):
    goi = []

    def _tu_choi(*_a, **_k):
        goi.append(1)
        raise urllib.error.URLError(ConnectionRefusedError())

    monkeypatch.setattr(nl.urllib.request, "urlopen", _tu_choi)
    monkeypatch.setattr(ct, "_ip_qua_doh", lambda host: [])
    monkeypatch.setattr(nl.time, "sleep", lambda s: None)
    assert nl.cong_khai_song_nhanh("https://x.trycloudflare.com") is False
    assert len(goi) == nl.SO_LAN_THU
