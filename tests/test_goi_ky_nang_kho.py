"""
Kho gói kỹ năng: cài, bật tắt, xoá, khôi phục — CSDL giả ghi lại SQL.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def chay(coro):
    return asyncio.run(coro)


def test_migration_0014_tao_du_bang_va_cot():
    sql = (ROOT / "agent" / "migrations" / "versions" / "0014_goi_ky_nang.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS goi_ky_nang" in sql
    assert "CREATE TABLE IF NOT EXISTS goi_ky_nang_lich_su" in sql
    assert re.search(r"ALTER TABLE ky_nang_cai_dat ADD COLUMN IF NOT EXISTS goi TEXT", sql)


def test_rag_xoa_nguon_theo_tien_to(monkeypatch):
    from agent.core import rag

    sql_da_chay = []

    async def execute(sql, *a):
        sql_da_chay.append((" ".join(sql.split()), a))
        return "DELETE 3"

    monkeypatch.setattr(rag.db, "execute", execute)
    n = chay(rag.xoa_nguon("goi:abc:"))
    assert n == 3
    assert "DELETE FROM documents WHERE source LIKE $1" in sql_da_chay[0][0]
    assert sql_da_chay[0][1] == ("goi:abc:%",)


def test_reply_co_goi_ky_nang_mac_dinh_rong():
    from agent.core.agent import Reply

    assert Reply(text="x").goi_ky_nang == []


class _CSDL:
    """CSDL giả: ghi lại SQL, trả dữ liệu theo kịch bản."""

    def __init__(self):
        self.sql: list[tuple[str, tuple]] = []
        self.goi: dict[str, dict] = {}       # bảng goi_ky_nang giả
        self.lich_su: list[dict] = []
        self.plugin: dict[str, dict] = {}
        self.su_kien: list[str] = []

    async def execute(self, sql, *a):
        s = " ".join(sql.split()); self.sql.append((s, a))
        if s.startswith("INSERT INTO goi_ky_nang ("):
            self.goi[a[0]] = {"ten": a[0], "phien_ban": a[1], "bat": True, "noi_dung": a[2], "tao_boi": a[3]}
        elif s.startswith("INSERT INTO goi_ky_nang_lich_su"):
            self.lich_su.append({"id": len(self.lich_su) + 1, "ten": a[0], "phien_ban": a[1], "noi_dung": a[2], "thay_boi": a[3]})
        elif s.startswith("UPDATE goi_ky_nang SET bat"):
            self.goi[a[1]]["bat"] = a[0]
        elif s.startswith("DELETE FROM goi_ky_nang WHERE ten"):
            self.goi.pop(a[0], None)
        elif s.startswith("INSERT INTO ky_nang_cai_dat"):
            self.plugin[a[0]] = {"ten": a[0], "bat": True, "goi": a[-1]}
        elif s.startswith("DELETE FROM ky_nang_cai_dat WHERE goi"):
            for k in [k for k, v in self.plugin.items() if v["goi"] == a[0]]:
                self.plugin.pop(k)
        elif s.startswith("UPDATE ky_nang_cai_dat SET bat"):
            for v in self.plugin.values():
                if v["goi"] == a[1]:
                    v["bat"] = a[0]
        return "OK 1"

    async def fetch(self, sql, *a):
        s = " ".join(sql.split()); self.sql.append((s, a))
        if "FROM goi_ky_nang_lich_su" in s:
            return [r for r in self.lich_su if r["ten"] == a[0]]
        if "FROM goi_ky_nang" in s:
            return list(self.goi.values())
        if "FROM events" in s:
            return []
        return []

    async def fetchrow(self, sql, *a):
        s = " ".join(sql.split()); self.sql.append((s, a))
        if "FROM goi_ky_nang_lich_su" in s:
            return next((r for r in self.lich_su if r["id"] == a[0] and r["ten"] == a[1]), None)
        if "FROM goi_ky_nang" in s:
            return self.goi.get(a[0])
        return None

    async def log_event(self, kind, **kw):
        self.su_kien.append(kind)


@pytest.fixture
def kho(monkeypatch):
    from agent.core import rag
    from agent.ky_nang import goi as g, kho_ky_nang

    csdl = _CSDL()
    nap, xoa_nguon = [], []

    async def ingest(title, source, text):
        nap.append((title, source)); return 1

    async def xoa(prefix):
        xoa_nguon.append(prefix); return 0

    monkeypatch.setattr(g, "db", csdl)
    monkeypatch.setattr(rag, "ingest", ingest)
    monkeypatch.setattr(rag, "xoa_nguon", xoa)
    monkeypatch.setattr(kho_ky_nang, "xoa_dem", lambda: None)
    g.xoa_dem()
    csdl.nap, csdl.xoa_nguon = nap, xoa_nguon
    return csdl


def _goi(**doi):
    d = {"ten": "tu-van-da-nhay-cam", "phien_ban": "1.0.0",
         "mo_ta": "Tư vấn cho khách da nhạy cảm, hỏi tiền sử kích ứng trước.",
         "tu_khoa": ["da nhạy cảm"],
         "huong_dan": "Khi khách nói da nhạy cảm: hỏi đã từng kích ứng với gì, ưu tiên sản phẩm không hương liệu.",
         "cong_cu": [{"ten": "bang_thanh_phan_ne", "loai": "tra_bang",
                      "mo_ta": "Tra thành phần khách da nhạy cảm nên tránh, theo tên thành phần.",
                      "tham_so": [{"ten": "thanh_phan", "mo_ta": "Tên thành phần khách hỏi", "bat_buoc": True}],
                      "cau_hinh": {"bang": {"Hương liệu": "nên tránh"}}}],
         "tai_lieu": [{"tieu_de": "Thành phần nên tránh", "noi_dung": "Hương liệu, cồn khô, tinh dầu đậm đặc. " * 5}]}
    d.update(doi); return d


def test_cai_ghi_goi_plugin_tai_lieu(kho):
    from agent.ky_nang import goi as g

    x = chay(g.cai(_goi(), boi="qt"))
    assert x.ten in kho.goi and kho.plugin["bang_thanh_phan_ne"]["goi"] == x.ten
    assert kho.nap == [("[tu-van-da-nhay-cam] Thành phần nên tránh", "goi:tu-van-da-nhay-cam:00")]
    assert kho.xoa_nguon == ["goi:tu-van-da-nhay-cam:"]   # gỡ bản cũ trước khi nạp
    assert "ky_nang.goi_cai" in kho.su_kien and kho.lich_su == []


def test_cai_phien_ban_moi_thi_ban_cu_vao_lich_su(kho):
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="qt"))
    chay(g.cai(_goi(phien_ban="1.1.0"), boi="qt"))
    assert [h["phien_ban"] for h in kho.lich_su] == ["1.0.0"]
    assert kho.goi["tu-van-da-nhay-cam"]["phien_ban"] == "1.1.0"


def test_cai_cung_phien_ban_khong_ghi_lich_su(kho):
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="qt")); chay(g.cai(_goi(), boi="qt"))
    assert kho.lich_su == []


def test_qua_20_goi_thi_tu_choi(kho):
    from agent.ky_nang import goi as g

    for i in range(g.GOI_TOI_DA):
        kho.goi[f"goi-{i}"] = {"ten": f"goi-{i}", "phien_ban": "1.0.0", "bat": True, "noi_dung": "{}", "tao_boi": "x"}
    with pytest.raises(g.KhoDay):
        chay(g.cai(_goi(ten="goi-moi"), boi="qt"))


def test_tat_goi_thi_tat_plugin_va_go_tai_lieu(kho):
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="qt"))
    chay(g.bat_tat("tu-van-da-nhay-cam", False, boi="qt"))
    assert kho.goi["tu-van-da-nhay-cam"]["bat"] is False
    assert kho.plugin["bang_thanh_phan_ne"]["bat"] is False
    assert kho.xoa_nguon[-1] == "goi:tu-van-da-nhay-cam:"
    chay(g.bat_tat("tu-van-da-nhay-cam", True, boi="qt"))
    assert kho.plugin["bang_thanh_phan_ne"]["bat"] is True and len(kho.nap) == 2


def test_xoa_giu_lich_su(kho):
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="qt")); chay(g.cai(_goi(phien_ban="1.1.0"), boi="qt"))
    assert chay(g.xoa("tu-van-da-nhay-cam", boi="qt")) is True
    assert "tu-van-da-nhay-cam" not in kho.goi and not kho.plugin and len(kho.lich_su) == 1
    with pytest.raises(g.GoiKhongTonTai):
        chay(g.xoa("tu-van-da-nhay-cam", boi="qt"))


def test_khoi_phuc_ban_cu(kho):
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="qt")); chay(g.cai(_goi(phien_ban="1.1.0"), boi="qt"))
    x = chay(g.khoi_phuc("tu-van-da-nhay-cam", 1, boi="qt"))
    assert x.phien_ban == "1.0.0" and kho.goi["tu-van-da-nhay-cam"]["phien_ban"] == "1.0.0"
    assert [h["phien_ban"] for h in kho.lich_su] == ["1.0.0", "1.1.0"]


def test_huong_dan_cho_luot_chi_goi_dang_bat(kho):
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="qt"))
    assert chay(g.huong_dan_cho_luot("da nhạy cảm của em lắm"))[0][0] == "tu-van-da-nhay-cam"
    chay(g.bat_tat("tu-van-da-nhay-cam", False, boi="qt"))
    g.xoa_dem()
    assert chay(g.huong_dan_cho_luot("da nhạy cảm của em lắm")) == []


def test_huong_dan_cho_luot_csdl_hong_thi_rong(monkeypatch, caplog):
    from agent.ky_nang import goi as g

    class _Hong:
        async def fetch(self, *a): raise RuntimeError("CSDL sập")

    monkeypatch.setattr(g, "db", _Hong()); g.xoa_dem()
    with caplog.at_level("WARNING", logger="agent.ky_nang.goi"):
        assert chay(g.huong_dan_cho_luot("da nhạy cảm")) == []
    assert any("CSDL sập" in r.message for r in caplog.records)


def test_xuat_tra_dung_dinh_dang_nap_lai_duoc(kho):
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="qt"))
    d = chay(g.xuat("tu-van-da-nhay-cam"))
    assert g.doc_goi(d).ten == "tu-van-da-nhay-cam"
    assert chay(g.xuat("khong-co")) is None
