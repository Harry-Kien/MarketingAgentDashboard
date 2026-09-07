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
        self.plugin: dict[str, dict] = {}    # bảng ky_nang_cai_dat giả
        self.su_kien: list[str] = []
        self.events: list[dict] = []         # dòng giả cho SELECT ... FROM events

    async def execute(self, sql, *a):
        s = " ".join(sql.split()); self.sql.append((s, a))
        # VÌ SAO KHÔNG json.dumps THAM SỐ Ở TEST: đây chính là điều đang
        # được canh — nếu goi.py/kho_ky_nang.py lỡ mã hoá hai lần thì `a[2]`
        # (hay `a[-1]` ở plugin) tới đây đã là str, và bất kỳ test nào đọc
        # lại field bên trong nó (vd `noi_dung["mo_ta"]`) sẽ nổ ngay ở CSDL
        # giả này thay vì im lặng lọt qua tới CSDL thật.
        if s.startswith("INSERT INTO goi_ky_nang ("):
            self.goi[a[0]] = {"ten": a[0], "phien_ban": a[1], "bat": True, "noi_dung": a[2], "tao_boi": a[3]}
        elif s.startswith("INSERT INTO goi_ky_nang_lich_su"):
            self.lich_su.append({"id": len(self.lich_su) + 1, "ten": a[0], "phien_ban": a[1], "noi_dung": a[2], "thay_boi": a[3]})
        elif s.startswith("UPDATE goi_ky_nang SET bat"):
            self.goi[a[1]]["bat"] = a[0]
        elif s.startswith("DELETE FROM goi_ky_nang WHERE ten"):
            self.goi.pop(a[0], None)
        elif s.startswith("INSERT INTO ky_nang_cai_dat"):
            # Chỉ nơi duy nhất gọi câu này trong các test ở tệp này là
            # `_ghi_plugin` (goi.py), luôn 5 tham số (ten, bat, ban_mo_ta,
            # tao_boi, goi) — "goi" luôn là tham số CUỐI.
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
        if "FROM goi_ky_nang WHERE bat" in s:
            # Câu SQL thật lọc bằng WHERE, "bat" thậm chí không nằm trong
            # SELECT — CSDL giả phải mô phỏng đúng việc lọc NÀY, không phải
            # trả nguyên bảng rồi để mã ứng dụng tự lọc lại (đó chính là
            # dòng chết `.get("bat", True)` đã gỡ khỏi _cac_goi_dang_bat).
            return [r for r in self.goi.values() if r["bat"]]
        if "FROM goi_ky_nang" in s:
            return list(self.goi.values())
        if "FROM ky_nang_cai_dat" in s:
            if "ban_mo_ta IS NOT NULL AND bat" in s:
                # Câu đếm trần plugin: mọi plugin ĐANG BẬT không thuộc gói
                # đang cài. Mô phỏng đúng bộ lọc của SQL, không trả cả bảng
                # rồi để mã ứng dụng tự lọc lại.
                return [dict(v) for v in self.plugin.values()
                        if v.get("bat") and v["goi"] != a[0]]
            ten_can = a[0] if a else []
            return [dict(v) for v in self.plugin.values() if v["ten"] in ten_can]
        if "FROM events" in s:
            return self.events
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
    nap, xoa_nguon, dem_xoa_dem_kho = [], [], []

    async def ingest(title, source, text):
        nap.append((title, source)); return 1

    async def xoa(prefix):
        xoa_nguon.append(prefix); return 0

    xoa_dem_kho_that = kho_ky_nang.xoa_dem  # bản gốc — bắt trước khi ghi đè

    def xoa_dem_kho():
        # Đếm THẬT SỰ gọi bản gốc (dọn `kho_ky_nang._DEM`), không phải
        # no-op: test hỏng-đường-nạp-tài-liệu (mục 5b) phải thấy được là
        # `kho_ky_nang.xoa_dem()` VẪN chạy ngay cả khi `bat_tat()` ném lỗi
        # — một no-op không phân biệt được "đã gọi" với "chưa từng gọi",
        # và bỏ luôn bản gốc thì bộ nhớ đệm của MODULE KHÁC rò rỉ giữa các
        # test (module-global, không tự dọn theo từng test).
        dem_xoa_dem_kho.append(1)
        xoa_dem_kho_that()

    monkeypatch.setattr(g, "db", csdl)
    # kho_ky_nang._doc() tự đọc bảng ky_nang_cai_dat — trỏ nó vào cùng CSDL
    # giả để câu SQL đó không rơi vào db.pool() thật (chưa init_db() trong
    # test) và không lệch trạng thái với những gì goi.py vừa ghi.
    monkeypatch.setattr(kho_ky_nang, "db", csdl)
    monkeypatch.setattr(rag, "ingest", ingest)
    monkeypatch.setattr(rag, "xoa_nguon", xoa)
    monkeypatch.setattr(kho_ky_nang, "xoa_dem", xoa_dem_kho)
    g.xoa_dem(); kho_ky_nang.xoa_dem()
    csdl.nap, csdl.xoa_nguon, csdl.dem_xoa_dem_kho = nap, xoa_nguon, dem_xoa_dem_kho
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
    # Lọc THẬT phải nằm ở câu SQL (WHERE bat), không phải ở một điều kiện
    # Python đọc cột "bat" không hề có trong SELECT — đó là dòng chết đã gỡ
    # khỏi _cac_goi_dang_bat(), và đây là phép kiểm canh nó không quay lại.
    assert any(s.startswith("SELECT ten, noi_dung FROM goi_ky_nang WHERE bat") for s, _ in kho.sql)
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


# ---------------------------------------------------------------
#  Mã hoá JSONB đúng MỘT lần (mục 1 review Task 3)
# ---------------------------------------------------------------

def test_cai_ghi_jsonb_bang_dict_khong_ma_hoa_hai_lan(kho):
    """
    Codec ở agent/db.py (agent/db.py dòng ~25) đã tự mã hoá khi thấy
    `$n::jsonb`. Truyền thêm `json.dumps()` là mã hoá HAI LẦN: cột chứa
    một CHUỖI JSON, không phải object — `noi_dung->>'mo_ta'` trả NULL và
    tiếng Việt hoá thành \\uXXXX. Test canh trực tiếp KIỂU tham số đưa vào
    `execute()`, vì CSDL giả (không phải Postgres thật) không tự phân biệt
    được str JSON hợp lệ với dict — chỉ nhìn hành vi bên ngoài thì lọt.
    """
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="qt"))

    goi_sql = [a for s, a in kho.sql if s.startswith("INSERT INTO goi_ky_nang (")]
    assert goi_sql and isinstance(goi_sql[0][2], dict)
    assert goi_sql[0][2]["mo_ta"] == _goi()["mo_ta"]

    plugin_sql = [a for s, a in kho.sql if s.startswith("INSERT INTO ky_nang_cai_dat")]
    assert plugin_sql and isinstance(plugin_sql[0][2], dict)

    chay(g.cai(_goi(phien_ban="1.1.0"), boi="qt"))
    lich_su_sql = [a for s, a in kho.sql if s.startswith("INSERT INTO goi_ky_nang_lich_su")]
    assert lich_su_sql and isinstance(lich_su_sql[0][2], dict)


# ---------------------------------------------------------------
#  Đường hỏng khi nạp tài liệu (mục 3, 4, 5a, 5b review Task 3)
# ---------------------------------------------------------------

def test_cai_nap_tai_lieu_hong_thi_goi_va_plugin_tat_va_xoa_nguon(kho, monkeypatch):
    from agent.core import rag
    from agent.ky_nang import goi as g

    async def ingest_hong(title, source, text):
        raise RuntimeError("API nhúng sập")
    monkeypatch.setattr(rag, "ingest", ingest_hong)

    with pytest.raises(RuntimeError, match="TẮT"):
        chay(g.cai(_goi(), boi="qt"))

    assert kho.goi["tu-van-da-nhay-cam"]["bat"] is False
    assert kho.plugin["bang_thanh_phan_ne"]["bat"] is False
    # gỡ bản dở sau khi hỏng — tài liệu nạp một phần của gói đã TẮT không
    # được nằm lại trong kho tri thức
    assert kho.xoa_nguon[-1] == "goi:tu-van-da-nhay-cam:"
    assert "ky_nang.goi_tai_lieu_hong" in kho.su_kien


def test_bat_lai_nap_tai_lieu_hong_thi_tat_va_van_xoa_dem(kho, monkeypatch):
    from agent.core import rag
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="qt"))
    chay(g.bat_tat("tu-van-da-nhay-cam", False, boi="qt"))
    dem_truoc = len(kho.dem_xoa_dem_kho)

    async def ingest_hong(title, source, text):
        raise RuntimeError("API nhúng sập")
    monkeypatch.setattr(rag, "ingest", ingest_hong)

    with pytest.raises(RuntimeError, match="TẮT"):
        chay(g.bat_tat("tu-van-da-nhay-cam", True, boi="qt"))

    assert kho.goi["tu-van-da-nhay-cam"]["bat"] is False
    assert kho.plugin["bang_thanh_phan_ne"]["bat"] is False
    assert "ky_nang.goi_tai_lieu_hong" in kho.su_kien
    # xoa_dem() của kho_ky_nang phải chạy dù nhánh hỏng — ở finally, không
    # phải chỉ trên đường thành công.
    assert len(kho.dem_xoa_dem_kho) > dem_truoc


# ---------------------------------------------------------------
#  Đếm lượt gọi 7 ngày (mục 6, 7 review Task 3)
# ---------------------------------------------------------------

def test_dem_goi_7_ngay_sql_va_gop_dung_theo_ten(kho):
    from agent.ky_nang import goi as g

    kho.events = [
        {"ten": "bang_thanh_phan_ne", "goi": "tu-van-da-nhay-cam", "so_lan": 3, "so_loi": 1},
    ]
    dem = chay(g.dem_goi_7_ngay())
    assert dem == {"bang_thanh_phan_ne": {"so_lan": 3, "so_loi": 1, "goi": "tu-van-da-nhay-cam"}}
    sql = next(s for s, _ in kho.sql if "FROM events" in s)
    assert "thu_nghiem" in sql and "cong_cu.goi" in sql


def test_liet_ke_cong_so_lan_theo_cong_cu_cua_goi(kho):
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="qt"))
    kho.events = [
        {"ten": "bang_thanh_phan_ne", "goi": "tu-van-da-nhay-cam", "so_lan": 5, "so_loi": 2},
    ]
    ra = chay(g.liet_ke())
    assert len(ra) == 1
    r = ra[0]
    assert set(r) == {
        "ten", "phien_ban", "bat", "mo_ta", "tu_khoa",
        "so_cong_cu", "so_tai_lieu", "so_lan_7_ngay", "so_loi_7_ngay", "sua_luc",
    }
    assert r["so_lan_7_ngay"] == 5 and r["so_loi_7_ngay"] == 2


def test_liet_ke_dem_7_ngay_hong_thi_van_tra_danh_sach(kho, monkeypatch, caplog):
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="qt"))

    async def hong():
        raise RuntimeError("đo hỏng")
    monkeypatch.setattr(g, "dem_goi_7_ngay", hong)

    with caplog.at_level("WARNING", logger="agent.ky_nang.goi"):
        ra = chay(g.liet_ke())
    assert len(ra) == 1
    assert ra[0]["so_lan_7_ngay"] == 0 and ra[0]["so_loi_7_ngay"] == 0
    assert any("đo hỏng" in r.message for r in caplog.records)


# ---------------------------------------------------------------
#  lich_su() và gói hỏng trong CSDL (mục 5f, 5g review Task 3)
# ---------------------------------------------------------------

def test_lich_su_tra_ve_danh_sach(kho):
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="qt"))
    chay(g.cai(_goi(phien_ban="1.1.0"), boi="qt"))
    ls = chay(g.lich_su("tu-van-da-nhay-cam"))
    assert len(ls) == 1
    assert ls[0]["phien_ban"] == "1.0.0" and ls[0]["thay_boi"] == "qt"


def test_cac_goi_dang_bat_bo_qua_goi_hong(kho, caplog):
    from agent.ky_nang import goi as g

    kho.goi["goi-hong"] = {
        "ten": "goi-hong", "phien_ban": "1.0.0", "bat": True,
        "noi_dung": {
            "ten": "goi-hong", "phien_ban": "1.0.0",
            "mo_ta": "Mô tả đủ dài cho gói này, ít nhất hai mươi ký tự thật.",
            "tu_khoa": ["tu khoa mau"],
            # THIẾU "huong_dan" — đây chính là điều test canh.
        },
        "tao_boi": "x",
    }
    g.xoa_dem()
    with caplog.at_level("WARNING", logger="agent.ky_nang.goi"):
        ra = chay(g._cac_goi_dang_bat())
    assert ra == ()
    assert any("goi-hong" in r.message for r in caplog.records)


# ---------------------------------------------------------------
#  kho_ky_nang.liet_ke() với số 7 ngày (mục 5h review Task 3)
# ---------------------------------------------------------------

def test_kho_ky_nang_liet_ke_co_so_lan_7_ngay(kho, monkeypatch):
    from agent.ky_nang import goi as g, kho_ky_nang

    async def dem_gia():
        return {"tao_don_hang": {"so_lan": 4, "so_loi": 1, "goi": None}}
    monkeypatch.setattr(g, "dem_goi_7_ngay", dem_gia)
    kho_ky_nang.xoa_dem()

    ra = chay(kho_ky_nang.liet_ke())
    cc = next(x for x in ra["co_san"] if x["ten"] == "tao_don_hang")
    assert cc["so_lan_7_ngay"] == 4 and cc["so_loi_7_ngay"] == 1


def test_kho_ky_nang_liet_ke_dem_hong_thi_van_tra_bang(kho, monkeypatch):
    from agent.ky_nang import goi as g, kho_ky_nang

    async def hong():
        raise RuntimeError("đo hỏng")
    monkeypatch.setattr(g, "dem_goi_7_ngay", hong)
    kho_ky_nang.xoa_dem()

    ra = chay(kho_ky_nang.liet_ke())
    assert ra["co_san"]
    assert all(k["so_lan_7_ngay"] == 0 for k in ra["co_san"])


# ---------------------------------------------------------------
#  Chiếm plugin rời (mục 9 review Task 3)
# ---------------------------------------------------------------

def test_cai_tu_choi_neu_cong_cu_trung_plugin_roi(kho):
    """
    `bang_thanh_phan_ne` đã có sẵn như một plugin RỜI (goi=None, ai đó
    thêm tay qua dashboard) — gói cố cài công cụ cùng tên phải bị từ chối,
    và KHÔNG được ghi gì (không gói, không lịch sử, không sự kiện): sai
    thì không ghi gì, đúng bất biến đầu docstring của `cai()`.
    """
    from agent.ky_nang import goi as g

    kho.plugin["bang_thanh_phan_ne"] = {"ten": "bang_thanh_phan_ne", "bat": True, "goi": None}

    with pytest.raises(g.LoiGoi, match="bang_thanh_phan_ne"):
        chay(g.cai(_goi(), boi="qt"))

    assert kho.goi == {} and kho.lich_su == [] and kho.su_kien == []


def test_cai_tu_choi_neu_cong_cu_trung_goi_khac(kho):
    """Cùng chốt, nhưng cái đang chiếm là công cụ của MỘT GÓI KHÁC."""
    from agent.ky_nang import goi as g

    kho.plugin["bang_thanh_phan_ne"] = {"ten": "bang_thanh_phan_ne", "bat": True, "goi": "goi-khac"}

    with pytest.raises(g.LoiGoi, match="goi-khac"):
        chay(g.cai(_goi(), boi="qt"))

    assert kho.goi == {}


def test_cai_lai_gia_ban_than_khong_bi_chan(kho):
    """Cài lại (nâng phiên bản) gói của CHÍNH MÌNH không phải là chiếm."""
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="qt"))
    x = chay(g.cai(_goi(phien_ban="1.1.0"), boi="qt"))
    assert x.phien_ban == "1.1.0"


# ---------------------------------------------------------------
#  Trần plugin khi cài gói (mục 1 review cuối)
# ---------------------------------------------------------------

def test_cai_goi_vuot_tran_plugin_thi_tu_choi(kho):
    """
    `luu_plugin` chặn được đường thêm plugin RỜI, nhưng cài gói là đường
    thứ hai vào cùng bảng — không chặn thì hai gói năm công cụ là vượt trần
    mà không ai báo, và mọi lời gọi model mang thêm lược đồ vượt trần.
    """
    from agent.ky_nang import goi as g
    from agent.ky_nang import kho_ky_nang

    for i in range(kho_ky_nang.PLUGIN_TOI_DA):
        kho.plugin[f"roi_{i}"] = {"ten": f"roi_{i}", "bat": True, "goi": None}

    with pytest.raises(g.KhoDay) as e:
        chay(g.cai(_goi(), boi="qt"))
    # Câu báo phải NÊU SỐ: "quá trần" mà không nói bao nhiêu thì người vận
    # hành không biết phải tắt mấy cái.
    assert str(kho_ky_nang.PLUGIN_TOI_DA) in str(e.value)
    assert kho.goi == {} and kho.lich_su == [] and kho.su_kien == []


def test_cai_lai_khong_dem_cong_cu_cua_chinh_goi_do(kho):
    """
    Công cụ CỦA GÓI ĐANG CÀI không được đếm hai lần: cài lại một gói đã có
    mà bị từ chối vì chính công cụ của nó là không nâng cấp được gói nào nữa.
    """
    from agent.ky_nang import goi as g
    from agent.ky_nang import kho_ky_nang

    for i in range(kho_ky_nang.PLUGIN_TOI_DA - 1):
        kho.plugin[f"roi_{i}"] = {"ten": f"roi_{i}", "bat": True, "goi": None}
    chay(g.cai(_goi(), boi="qt"))          # vừa đủ trần
    x = chay(g.cai(_goi(phien_ban="1.1.0"), boi="qt"))
    assert x.phien_ban == "1.1.0"


def test_plugin_dang_tat_khong_chiem_cho_trong_tran(kho):
    """Trần đếm plugin ĐANG BẬT — cái đã tắt không tốn lược đồ nào."""
    from agent.ky_nang import goi as g
    from agent.ky_nang import kho_ky_nang

    for i in range(kho_ky_nang.PLUGIN_TOI_DA):
        kho.plugin[f"roi_{i}"] = {"ten": f"roi_{i}", "bat": False, "goi": None}
    assert chay(g.cai(_goi(), boi="qt")).ten == "tu-van-da-nhay-cam"


def test_bat_lai_goi_vuot_tran_plugin_thi_tu_choi_va_van_tat(kho):
    """
    `bat_tat(ten, True)` là đường THỨ BA vào bảng `ky_nang_cai_dat` (sau cài
    gói và lưu plugin rời) — chỉ `UPDATE ... SET bat`, không tự đi qua chốt
    trần nào. Thiếu kiểm ở đây thì bật lại một gói cũ khi trần đã đầy vẫn
    qua được: gói vừa cài xong, xong tắt, giờ đầy plugin rời rồi bật lại
    vẫn phải bị chặn, và gói phải NGUYÊN TRẠNG THÁI TẮT sau khi bị chặn.
    """
    from agent.ky_nang import goi as g
    from agent.ky_nang import kho_ky_nang

    chay(g.cai(_goi(), boi="qt"))
    chay(g.bat_tat("tu-van-da-nhay-cam", False, boi="qt"))
    assert kho.goi["tu-van-da-nhay-cam"]["bat"] is False
    assert kho.plugin["bang_thanh_phan_ne"]["bat"] is False

    for i in range(kho_ky_nang.PLUGIN_TOI_DA):
        kho.plugin[f"roi_{i}"] = {"ten": f"roi_{i}", "bat": True, "goi": None}

    with pytest.raises(g.KhoDay) as e:
        chay(g.bat_tat("tu-van-da-nhay-cam", True, boi="qt"))
    assert str(kho_ky_nang.PLUGIN_TOI_DA) in str(e.value)
    assert kho.goi["tu-van-da-nhay-cam"]["bat"] is False
    assert kho.plugin["bang_thanh_phan_ne"]["bat"] is False


# ---------------------------------------------------------------
#  tao_boi của plugin trong gói là NGƯỜI cài (mục 10 review cuối)
# ---------------------------------------------------------------

def test_plugin_cua_goi_ghi_dung_nguoi_cai(kho):
    from agent.ky_nang import goi as g

    chay(g.cai(_goi(), boi="chi-lan"))
    them = [a for s, a in kho.sql if s.startswith("INSERT INTO ky_nang_cai_dat")]
    # (ten, bat, ban_mo_ta, tao_boi, goi) — hằng "goi" ở ô tao_boi làm nhật ký
    # kiểm toán mất đúng cái nó sinh ra để giữ: ai đã cài.
    assert them and them[0][3] == "chi-lan"


# ---------------------------------------------------------------
#  kho_ky_nang.luu_plugin — cùng lỗi mã hoá JSONB hai lần, đường khác
#  (plugin rời qua dashboard, không đi qua goi.py._ghi_plugin)
# ---------------------------------------------------------------

def test_luu_plugin_ghi_jsonb_bang_dict_khong_ma_hoa_hai_lan(monkeypatch):
    """
    `kho_ky_nang.luu_plugin` là đường RIÊNG để tạo một plugin rời từ form
    "Tạo hoặc sửa plugin" trên dashboard — khác `goi.py._ghi_plugin` (đã có
    test canh ở trên cho đường cài GÓI). Codec JSONB ở agent/db.py
    (encoder=json.dumps) tự mã hoá khi thấy `$n::jsonb`; `json.dumps()`
    thêm ở đây từng làm cột chứa một CHUỖI JSON thay vì object (mã hoá hai
    lần) — `ban_mo_ta->>'mo_ta'` trả NULL và tiếng Việt hoá thành \\uXXXX.

    Giả `db.execute`/`db.log_event` bằng monkeypatch thay vì dùng CSDL giả
    dùng chung, vì `_CSDL` ở trên được viết riêng cho các hàm trong
    `goi.py` (tham số cuối luôn là "goi") — dùng lại nó cho `luu_plugin`
    (tham số cuối là "boi") sẽ đọc nhầm cột.
    """
    from agent.ky_nang import kho_ky_nang

    kho_ky_nang.xoa_dem()  # cô lập khỏi mọi ca trước — _DEM là biến toàn cục

    goi_execute: list[tuple[str, tuple]] = []

    async def execute(sql, *a):
        goi_execute.append((" ".join(sql.split()), a))
        return "INSERT 0 1"

    async def log_event(kind, **kw):
        pass

    async def fetchrow(sql, *a):
        return None      # chưa có dòng nào mang tên này

    monkeypatch.setattr(kho_ky_nang.db, "execute", execute)
    monkeypatch.setattr(kho_ky_nang.db, "log_event", log_event)
    monkeypatch.setattr(kho_ky_nang.db, "fetchrow", fetchrow)

    tho = {
        "ten": "tra_bao_hanh", "loai": "tra_bang",
        "mo_ta": "Tra thời hạn bảo hành của một dòng sản phẩm theo tên dòng.",
        "tham_so": [{"ten": "dong_san_pham", "mo_ta": "Tên dòng sản phẩm khách hỏi", "bat_buoc": True}],
        "cau_hinh": {"bang": {"Kem Chống Nắng": "12 tháng sau khi mở nắp"}},
    }
    chay(kho_ky_nang.luu_plugin(tho, boi="qt"))

    them = [a for s, a in goi_execute if s.startswith("INSERT INTO ky_nang_cai_dat")]
    assert them, "luu_plugin không gọi INSERT INTO ky_nang_cai_dat"
    tham_so_ban_mo_ta = them[0][1]
    assert isinstance(tham_so_ban_mo_ta, dict), (
        "ban_mo_ta truyền vào db.execute() phải là dict — codec JSONB tự "
        f"json.dumps(); truyền {type(tham_so_ban_mo_ta).__name__} nghĩa là "
        "mã hoá tay lần nữa, mã hoá HAI LẦN"
    )
    assert tham_so_ban_mo_ta["mo_ta"] == tho["mo_ta"]

    kho_ky_nang.xoa_dem()  # không để bản đệm này rò sang test chạy sau


# ---------------------------------------------------------------
#  Công cụ của GÓI không sửa/xoá được bằng đường plugin rời
#  (mục 2 và 3 review cuối)
# ---------------------------------------------------------------

@pytest.fixture
def kho_plugin(monkeypatch):
    """CSDL giả tối thiểu cho hai đường plugin rời: execute + fetchrow."""
    from agent.ky_nang import kho_ky_nang

    trang_thai = {"xoa": "DELETE 0", "chu_goi": None}
    da_chay: list[tuple[str, tuple]] = []

    async def execute(sql, *a):
        s = " ".join(sql.split()); da_chay.append((s, a))
        return trang_thai["xoa"] if s.startswith("DELETE") else "INSERT 0 1"

    async def fetchrow(sql, *a):
        da_chay.append((" ".join(sql.split()), a))
        return {"goi": trang_thai["chu_goi"]} if trang_thai["chu_goi"] else None

    async def log_event(kind, **kw):
        pass

    monkeypatch.setattr(kho_ky_nang.db, "execute", execute)
    monkeypatch.setattr(kho_ky_nang.db, "fetchrow", fetchrow)
    monkeypatch.setattr(kho_ky_nang.db, "log_event", log_event)
    kho_ky_nang.xoa_dem()
    trang_thai["sql"] = da_chay
    yield trang_thai
    kho_ky_nang.xoa_dem()


def test_xoa_plugin_chi_xoa_dong_khong_thuoc_goi(kho_plugin):
    """
    Câu DELETE phải mang `goi IS NULL`. Thiếu nó thì xoá được một mảnh của
    gói đang bật: agent mất công cụ, hướng dẫn vẫn dạy nó gọi, dashboard vẫn
    hiện gói "đang bật" — không nổ, không nhật ký.
    """
    from agent.ky_nang import ban_mo_ta, kho_ky_nang

    kho_plugin["chu_goi"] = "tu-van-da-nhay-cam"
    with pytest.raises(ban_mo_ta.LoiBanMoTa) as e:
        chay(kho_ky_nang.xoa_plugin("bang_thanh_phan_ne", boi="qt"))
    assert "tu-van-da-nhay-cam" in str(e.value)
    xoa_sql = next(s for s, _ in kho_plugin["sql"] if s.startswith("DELETE FROM ky_nang_cai_dat"))
    assert "goi IS NULL" in xoa_sql


def test_xoa_plugin_khong_ton_tai_van_tra_false(kho_plugin):
    """Không có dòng nào mang tên đó là chuyện KHÁC "thuộc gói" — trả False."""
    from agent.ky_nang import kho_ky_nang

    assert chay(kho_ky_nang.xoa_plugin("khong-co-tren-doi", boi="qt")) is False


def test_xoa_plugin_roi_van_xoa_duoc(kho_plugin):
    from agent.ky_nang import kho_ky_nang

    kho_plugin["xoa"] = "DELETE 1"
    assert chay(kho_ky_nang.xoa_plugin("plugin_roi", boi="qt")) is True


def test_luu_plugin_tu_choi_ten_dang_thuoc_goi(kho_plugin):
    """
    Sửa công cụ của gói qua form plugin rời là một thay đổi lặng lẽ biến
    mất ở lần cài lại gói — gói là nguồn sự thật.
    """
    from agent.ky_nang import ban_mo_ta, kho_ky_nang

    kho_plugin["chu_goi"] = "tu-van-da-nhay-cam"
    tho = {
        "ten": "bang_thanh_phan_ne", "loai": "tra_bang",
        "mo_ta": "Tra thành phần khách da nhạy cảm nên tránh, theo tên thành phần.",
        "tham_so": [{"ten": "thanh_phan", "mo_ta": "Tên thành phần khách hỏi", "bat_buoc": True}],
        "cau_hinh": {"bang": {"Hương liệu": "nên tránh"}},
    }
    with pytest.raises(ban_mo_ta.LoiBanMoTa) as e:
        chay(kho_ky_nang.luu_plugin(tho, boi="qt"))
    assert "tu-van-da-nhay-cam" in str(e.value)
    assert not [s for s, _ in kho_plugin["sql"] if s.startswith("INSERT INTO ky_nang_cai_dat")]


def test_doc_lay_cot_goi_lam_nhan_khong_lay_tu_so_do(monkeypatch):
    """
    Nhãn gói của plugin phải đọc từ cột `goi`, không từ bảng số đo 7 ngày:
    một công cụ của gói CHƯA ai gọi lần nào trong tuần từng hiện ra như
    plugin rời, và dashboard cho luôn nút Xoá.
    """
    from agent.ky_nang import goi as g, kho_ky_nang

    async def fetch(sql, *a):
        assert "goi" in sql, "SELECT phải lấy cả cột goi"
        return [{"ten": "bang_thanh_phan_ne", "bat": True, "goi": "tu-van-da-nhay-cam",
                 "ban_mo_ta": _goi()["cong_cu"][0]}]

    async def dem_rong():
        return {}

    monkeypatch.setattr(kho_ky_nang.db, "fetch", fetch)
    monkeypatch.setattr(g, "dem_an_toan", dem_rong)
    kho_ky_nang.xoa_dem()
    ra = chay(kho_ky_nang.liet_ke())
    assert ra["plugin"][0]["goi"] == "tu-van-da-nhay-cam"

    # `tools._goi_cua` dán nhãn số đo từ CHÍNH nguồn này, không từ bộ đệm gói
    # (bộ đệm gói chỉ giữ gói đọc và kiểm được, nên một gói hỏng làm nhãn sai).
    from agent.core import tools
    assert tools._goi_cua("bang_thanh_phan_ne") == "tu-van-da-nhay-cam"
    assert tools._goi_cua("tao_don_hang") is None
    kho_ky_nang.xoa_dem()
