# tests/test_phong_thu_phien.py
"""
Phiên thử sống trong RAM, hội thoại giả không được job nền nào nhặt.

Hội thoại thử phải có trong `conversations` (công cụ tra đơn cần khoá
ngoại) nhưng ở `mode='human'`, `state='closed'`, gắn tài khoản kênh đã
TẮT — auto_routing chỉ nhặt mode <> 'human', sla chỉ quét open/pending,
canh gác bỏ qua tài khoản disabled. Test đọc SQL, không cần Postgres.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from agent.core import phong_thu_phien as pp


def chay(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _sach(monkeypatch):
    pp.xoa_het()
    sql_da_chay: list[str] = []

    async def fetchrow(sql, *a):
        sql_da_chay.append(" ".join(sql.split()))
        return {"id": uuid.uuid4()}

    monkeypatch.setattr(pp.db, "fetchrow", fetchrow)
    yield sql_da_chay
    pp.xoa_het()


def test_tao_va_lay_phien(_sach):
    p = chay(pp.tao_phien())
    assert pp.lay_phien(p.id) is p and p.luot == [] and p.history == []
    assert pp.xoa_phien(p.id) and pp.lay_phien(p.id) is None


def test_hoi_thoai_thu_khong_bi_job_nen_nhat(_sach):
    chay(pp.tao_phien())
    sql = " || ".join(_sach)
    assert "status = 'disabled'" in sql or "'disabled'" in sql
    assert "external_account_id" in sql and "phong-thu" in sql
    assert "'phong_thu'" in sql and "'human'" in sql and "'closed'" in sql


def test_ghi_luot_noi_history_dung_dinh_dang():
    p = chay(pp.tao_phien())
    pp.ghi_luot(p, "giá?", {"cost_usd": 0.01, "luoi_bat": None}, "245.000đ")
    assert p.history == [{"role": "user", "content": "giá?"},
                         {"role": "assistant", "content": "245.000đ"}]
    assert p.luot[0]["khach"] == "giá?" and p.luot[0]["agent"] == "245.000đ"
    assert p.chi_phi == pytest.approx(0.01)


def test_qua_30_luot_thi_tu_choi():
    p = chay(pp.tao_phien())
    for i in range(pp.TOI_DA_LUOT):
        pp.ghi_luot(p, str(i), {"cost_usd": 0}, "ok")
    with pytest.raises(pp.PhienDayLuot):
        pp.ghi_luot(p, "x", {"cost_usd": 0}, "ok")


def test_don_phien_cu_khi_day(monkeypatch):
    gio = [1000.0]
    monkeypatch.setattr(pp, "_bay_gio", lambda: gio[0])
    cu = chay(pp.tao_phien())
    gio[0] += pp.TTL_GIAY + 1
    for _ in range(pp.TOI_DA_PHIEN):
        chay(pp.tao_phien())
    assert pp.lay_phien(cu.id) is None
    assert len(pp._PHIEN) <= pp.TOI_DA_PHIEN


def test_lay_phien_het_han_tra_none(monkeypatch):
    gio = [1000.0]
    monkeypatch.setattr(pp, "_bay_gio", lambda: gio[0])
    p = chay(pp.tao_phien())
    gio[0] += pp.TTL_GIAY + 1
    assert pp.lay_phien(p.id) is None


def test_danh_sach_va_tong_quan_loai_phong_thu():
    from pathlib import Path

    nguon = (Path(__file__).resolve().parent.parent / "agent" / "api" / "routes.py").read_text(encoding="utf-8")
    assert nguon.count("channel <> 'phong_thu'") >= 3
