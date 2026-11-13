"""Readiness phải báo CHẶN khi mất DB, không crash và không báo xanh."""
import asyncio

import pytest

from agent import db
from scripts import san_sang as ss


def test_webhook_tu_mo_csdl_truoc_khi_doc(monkeypatch):
    da_mo = False

    async def mo():
        nonlocal da_mo
        da_mo = True

    async def doc(*args):
        assert da_mo, "đọc trước khi init_db()"
        return []

    monkeypatch.setattr(db, "init_db", mo)
    monkeypatch.setattr(db, "fetch", doc)
    assert asyncio.run(ss.kiem_webhook_zalo_oa())["muc"] == ss.DU


@pytest.mark.parametrize("hong_o", ["mo", "doc"])
def test_webhook_mat_csdl_bao_chan_khong_lo_bi_mat(monkeypatch, hong_o):
    async def mo():
        if hong_o == "mo":
            raise ConnectionRefusedError("postgresql://user:BI_MAT@db")

    async def doc(*args):
        raise TimeoutError("postgresql://user:BI_MAT@db")

    monkeypatch.setattr(db, "init_db", mo)
    monkeypatch.setattr(db, "fetch", doc)
    kq = asyncio.run(ss.kiem_webhook_zalo_oa())
    assert kq["muc"] == ss.CHAN
    assert "CSDL" in kq["ghi"]
    assert "BI_MAT" not in str(kq)


def test_bang_day_du_mat_csdl_van_in_den_cuoi(monkeypatch, capsys):
    """Đường mạng được thay ở biên; mọi phép kiểm DB chạy mã thật."""
    async def mat(*a, **k):
        raise ConnectionRefusedError("BI_MAT")

    async def callback():
        return ss._muc("Callback provider", ss.CHAN, "ngoại tuyến")

    async def erp():
        return ss._muc("ERP trả lời", ss.CHAN, "ngoại tuyến")

    monkeypatch.setattr(db, "init_db", mat)
    monkeypatch.setattr(ss, "kiem_callback_cong_khai", callback)
    monkeypatch.setattr(ss, "kiem_erp_song", erp)
    monkeypatch.setattr(ss, "kiem_cong", lambda: ss._muc("Cổng ra mạng LAN", ss.DU, "nội bộ"))
    assert asyncio.run(ss.chay()) == 1
    ra = capsys.readouterr().out
    assert "Webhook Zalo OA" in ra and "Cổng ra mạng LAN" in ra
    assert "CHƯA CHẠY ĐƯỢC" in ra and "BI_MAT" not in ra
