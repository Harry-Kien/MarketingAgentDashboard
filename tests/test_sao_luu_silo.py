"""
Sao lưu trên VPS (mô hình silo) phải NÓI THẬT — ở cả ba nơi đọc nó.

Rà soát 16.11.2026 tìm ra ba kiểu hỏng, cả ba đều im lặng:

1. `suc_khoe._kiem_sao_luu` tìm `data/backup` — trong container KHÔNG BAO
   GIỜ có, nên mục Sao lưu đỏ vĩnh viễn; canh gác chỉ báo khi trạng thái
   tổng ĐỔI nên sau lần đầu im mãi, kể cả khi model chết sau đó.
2. `cua_hang sao_luu` ghi `pg_dump` RÕ cùng máy, dấu mốc lại tên
   `.sao_luu_ngoai` — "ngoài" mà không ra ngoài; `san_sang` bỏ hẳn mục
   "Mã hoá + ngoài máy" trong silo → ĐỦ giả.
3. "Báo khi máy tắt" chỉ xét có URL; URL đi theo gói chuyển nhà, người ping
   duy nhất là task Windows của máy cũ.

Không cần Docker: mọi lệnh ra ngoài đi qua runner giả.
"""
from __future__ import annotations

import asyncio
import io
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import canh_gac, suc_khoe  # noqa: E402
from scripts import chuyen_nha, goi_ma_hoa  # noqa: E402
from scripts import cua_hang as ch  # noqa: E402
from scripts import san_sang as ss  # noqa: E402


def _luc(gio_truoc: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=gio_truoc)).isoformat()


# ================================================================ 1. sức khoẻ

def _ghi(tmp_path: Path, ten: str, d: dict) -> None:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / ten).write_text(json.dumps(d), encoding="utf-8")


@pytest.fixture
def silo(monkeypatch, tmp_path):
    monkeypatch.setenv("CSKH_SILO", "1")
    monkeypatch.setattr(suc_khoe, "ROOT", tmp_path)
    return tmp_path


def test_suc_khoe_silo_khong_tim_data_backup(silo):
    """Trong container KHÔNG có data/backup — chỉ dấu mốc của máy chủ là thật."""
    assert asyncio.run(suc_khoe._kiem_sao_luu())["trang_thai"] == suc_khoe.HONG
    _ghi(silo, ".sao_luu_may_chu", {"luc": _luc(3), "ma_hoa": True})
    _ghi(silo, ".sao_luu_ra_ngoai_may", {"luc": _luc(3), "ok": True})
    _ghi(silo, ".thu_phuc_hoi", {"luc": _luc(48)})
    m = asyncio.run(suc_khoe._kiem_sao_luu())
    assert m["trang_thai"] == suc_khoe.TOT, m


def test_suc_khoe_silo_dau_moc_cu_khong_xanh(silo):
    """Tên cũ `.sao_luu_ngoai` = bản rõ cùng máy: có bản, nhưng KHÔNG xanh."""
    _ghi(silo, ".sao_luu_ngoai", {"luc": _luc(3)})
    _ghi(silo, ".thu_phuc_hoi", {"luc": _luc(48)})
    m = asyncio.run(suc_khoe._kiem_sao_luu())
    assert m["trang_thai"] == suc_khoe.CANH_BAO and "CHƯA mã hoá" in m["ghi_chu"]


def test_suc_khoe_silo_chua_ra_ngoai_may_la_canh_bao_khong_phai_hong(silo):
    _ghi(silo, ".sao_luu_may_chu", {"luc": _luc(3), "ma_hoa": True})
    m = asyncio.run(suc_khoe._kiem_sao_luu())
    assert m["trang_thai"] == suc_khoe.CANH_BAO and "NGOÀI" in m["ghi_chu"]
    _ghi(silo, ".sao_luu_ra_ngoai_may", {"luc": _luc(3), "ok": False})
    assert asyncio.run(suc_khoe._kiem_sao_luu())["trang_thai"] == suc_khoe.CANH_BAO


def test_suc_khoe_silo_dau_moc_hong_khong_thanh_xanh(silo):
    (silo / "data").mkdir()
    (silo / "data" / ".sao_luu_may_chu").write_text("rác", encoding="utf-8")
    assert asyncio.run(suc_khoe._kiem_sao_luu())["trang_thai"] == suc_khoe.HONG


def test_ten_dau_moc_khop_ba_noi():
    """Ghi một tên, đọc một tên khác là hỏng câm — đúng kiểu lỗi đang sửa."""
    assert suc_khoe.DAU_MOC_SAO_LUU == ch.DAU_MOC_SAO_LUU == ss.DAU_MOC_SAO_LUU
    assert suc_khoe.DAU_MOC_NGOAI_MAY == ch.DAU_MOC_NGOAI_MAY == ss.DAU_MOC_NGOAI_MAY
    assert suc_khoe.DAU_MOC_THU_PHUC_HOI == ch.DAU_MOC_THU_PHUC_HOI
    assert ch.DAU_MOC_PING == ss.DAU_MOC_PING


# ================================================================ 1b. canh gác

def _kq(*hong: str) -> dict:
    muc = [{"ten": t, "trang_thai": "hong", "ghi_chu": ""} for t in hong]
    muc.append({"ten": "CSDL", "trang_thai": "tot", "ghi_chu": ""})
    return {"trang_thai": "hong" if hong else "tot", "muc": muc}


def _chay(monkeypatch, chuoi: list[dict]) -> list[tuple[str, str]]:
    da_bao: list[tuple[str, str]] = []

    async def bao_gia(muc_do, tieu_de, chi_tiet, kq):
        da_bao.append((muc_do, tieu_de))

    it = iter(chuoi)

    async def tong_kiem_gia():
        return next(it)

    monkeypatch.setattr(canh_gac, "_bao", bao_gia)
    monkeypatch.setattr(canh_gac.suc_khoe, "tong_kiem", tong_kiem_gia)
    monkeypatch.setattr(canh_gac, "_truoc", None)
    monkeypatch.setattr(canh_gac, "_cho_truoc", False)
    monkeypatch.setattr(canh_gac, "_tap_hong_truoc", frozenset())

    async def het():
        for _ in chuoi:
            await canh_gac.kiem_mot_lan()
    asyncio.run(het())
    return da_bao


def test_muc_hong_moi_van_duoc_bao_khi_tong_da_hong(monkeypatch):
    """Sao lưu đỏ sẵn, rồi model chết: model chết PHẢI được báo."""
    bao = _chay(monkeypatch, [_kq("Sao lưu"), _kq("Sao lưu"), _kq("Sao lưu", "Model ngôn ngữ")])
    assert [m for m, _ in bao] == ["hong", "hong"]
    assert "Model ngôn ngữ" in bao[1][1]


def test_cung_tap_hong_thi_khong_spam(monkeypatch):
    bao = _chay(monkeypatch, [_kq("Sao lưu", "Model ngôn ngữ")] * 4)
    assert [m for m, _ in bao] == ["hong"]


def test_bot_mot_muc_hong_thi_im_het_hong_thi_bao_phuc_hoi(monkeypatch):
    bao = _chay(monkeypatch, [_kq("A", "B"), _kq("A"), _kq()])
    assert [m for m, _ in bao] == ["hong", "phuc_hoi"]


# ================================================================ 2. cua_hang sao_luu

class _Runner:
    """Runner giả: pg_dump/tar trả byte, ghi lại dấu mốc gửi vào container."""

    def __init__(self, pg_dump=b"PGDMP-du-lieu-khach-0909123456", tar=b"TAR-anh-da",
                 lenh_ngoai_ma=0):
        self.lenh: list[tuple[list[str], object]] = []
        self.pg_dump, self.tar, self.lenh_ngoai_ma = pg_dump, tar, lenh_ngoai_ma
        self.dau_moc: dict[str, dict] = {}
        self.restore_vao: bytes | None = None

    def __call__(self, lenh, *, dau_vao=None, cwd=None, nhi_phan=False):
        lenh = list(lenh)
        self.lenh.append((lenh, dau_vao))
        if "pg_dump" in lenh:
            return subprocess.CompletedProcess(lenh, 0, self.pg_dump, b"")
        if "tar" in lenh and "run" in lenh:
            return subprocess.CompletedProcess(lenh, 0, self.tar, b"")
        if lenh[:1] == ["rclone"]:
            return subprocess.CompletedProcess(lenh, self.lenh_ngoai_ma, "", "lỗi mạng")
        if "pg_restore" in lenh:
            self.restore_vao = dau_vao
            return subprocess.CompletedProcess(lenh, 0, b"", b"")
        if lenh[-2:-1] == ["-c"] and lenh[-1].startswith("cat > /app/data/"):
            self.dau_moc[lenh[-1].rsplit("/", 1)[-1]] = json.loads(dau_vao)
            return subprocess.CompletedProcess(lenh, 0, "", "")
        if dau_vao and "count(*)" in str(dau_vao):
            return subprocess.CompletedProcess(lenh, 0, "61\n", "")
        if dau_vao and "json_agg" in str(dau_vao):
            return subprocess.CompletedProcess(lenh, 0, json.dumps(
                [{"ma": "shopa", "trang_thai": "chay", "ten_mien": "a.vn"}]), "")
        if "inspect" in lenh:
            return subprocess.CompletedProcess(lenh, 0, "running healthy\n", "")
        return subprocess.CompletedProcess(lenh, 0, "", "")


@pytest.fixture
def mp(tmp_path):
    r = _Runner()
    m = ch.MatPhang(chay=r, goc=tmp_path, ping=lambda url, song: True)
    (tmp_path / "cua_hang" / "shopa").mkdir(parents=True)
    (tmp_path / "cua_hang" / "shopa" / "compose.yml").write_text(
        "services:\n  app:\n    image: cskh-app:latest\n", encoding="utf-8")
    return m, r


def _giai(tep: Path, mk: str) -> bytes:
    ra = io.BytesIO()
    with tep.open("rb") as f:
        goi_ma_hoa.giai_ma(f, ra, mk)
    return ra.getvalue()


def test_sao_luu_ma_hoa_ban_ro_khong_cham_dia(mp, tmp_path):
    m, r = mp
    kq = m.sao_luu_day_du("shopa")
    tep = kq["tep"]
    assert tep.name.endswith(".dump.cskh")
    tho = tep.read_bytes()
    assert b"PGDMP" not in tho and b"0909123456" not in tho, "bản rõ nằm trên đĩa"
    # Không còn tệp nào chứa bản rõ trong thư mục sao lưu.
    for p in (tmp_path / "sao_luu" / "shopa").iterdir():
        assert b"0909123456" not in p.read_bytes(), p.name
    mk = m.mat_khau_sao_luu(sinh_neu_thieu=False)
    assert mk, "mật khẩu phải được sinh và ghi vào .env.nen"
    assert _giai(tep, mk) == r.pg_dump
    # Mật khẩu không đi trên dòng lệnh nào.
    assert not any(mk in " ".join(lenh) for lenh, _ in r.lenh)


def test_sao_luu_kem_volume_du_lieu_ma_hoa(mp):
    m, r = mp
    kq = m.sao_luu_day_du("shopa")
    assert kq["du_lieu"] is True
    tep_dl = next(kq["tep"].parent.glob("*-du-lieu.tar.cskh"))
    assert _giai(tep_dl, m.mat_khau_sao_luu()) == r.tar
    lenh_tar = next(lenh for lenh, _ in r.lenh if "tar" in lenh)
    assert "cskh-shopa-du-lieu:/app/data:ro" in lenh_tar, "phải mount CHỈ ĐỌC"
    assert r.dau_moc[".sao_luu_may_chu"]["ma_hoa"] is True
    assert r.dau_moc[".sao_luu_may_chu"]["du_lieu"] is True


def test_volume_hong_van_co_ban_csdl_nhung_dau_moc_noi_ra(tmp_path):
    r = _Runner(tar=b"")
    m = ch.MatPhang(chay=r, goc=tmp_path, ping=lambda u, s: True)
    kq = m.sao_luu_day_du("shopa")        # không có compose.yml
    assert kq["tep"].exists() and kq["du_lieu"] is False
    assert r.dau_moc[".sao_luu_may_chu"]["du_lieu"] is False


def test_chua_cau_hinh_ngoai_may_thi_KHONG_ghi_dau_moc_ngoai(mp):
    m, r = mp
    kq = m.sao_luu_day_du("shopa")
    assert kq["ngoai"] is None
    assert ".sao_luu_ra_ngoai_may" not in r.dau_moc
    assert ".sao_luu_ngoai" not in r.dau_moc, "tên cũ nói 'ngoài' mà không ra ngoài"


def test_thu_muc_ngoai_cung_dia_bi_tu_choi(mp, tmp_path):
    m, r = mp
    ngoai = tmp_path / "ngoai"
    ngoai.mkdir()
    m.mat_khau_sao_luu()
    with (tmp_path / ".env.nen").open("a", encoding="utf-8") as f:
        f.write(f"SAO_LUU_THU_MUC_NGOAI={ngoai}\n")
    kq = m.sao_luu_day_du("shopa")         # tmp_path: cùng đĩa
    assert kq["ngoai"] is False and "CÙNG đĩa" in kq["ngoai_ghi"]
    assert ".sao_luu_ra_ngoai_may" not in r.dau_moc


def test_thu_muc_ngoai_that_thi_chep_va_ghi_dau_moc(mp, tmp_path, monkeypatch):
    m, r = mp
    ngoai = tmp_path / "ngoai"
    ngoai.mkdir()
    m.mat_khau_sao_luu()
    with (tmp_path / ".env.nen").open("a", encoding="utf-8") as f:
        f.write(f"SAO_LUU_THU_MUC_NGOAI={ngoai}\n")
    monkeypatch.setattr(m, "_cung_o_dia", lambda a, b: False)
    kq = m.sao_luu_day_du("shopa")
    assert kq["ngoai"] is True
    chep = sorted(p.name for p in (ngoai / "shopa").iterdir())
    assert len(chep) == 2 and all(p.endswith(".cskh") for p in chep)
    assert r.dau_moc[".sao_luu_ra_ngoai_may"]["ok"] is True


def test_lenh_ngoai_hong_thi_khong_ghi_dau_moc(tmp_path):
    r = _Runner(lenh_ngoai_ma=1)
    m = ch.MatPhang(chay=r, goc=tmp_path, ping=lambda u, s: True)
    m.mat_khau_sao_luu()
    with (tmp_path / ".env.nen").open("a", encoding="utf-8") as f:
        f.write("SAO_LUU_LENH_NGOAI=rclone copyto {tep} b2:cskh/{ma}/{ten}\n")
    kq = m.sao_luu_day_du("shopa")
    assert kq["ngoai"] is False
    assert ".sao_luu_ra_ngoai_may" not in r.dau_moc


def test_lenh_ngoai_chay_khong_qua_shell_va_ghi_dau_moc(tmp_path):
    r = _Runner()
    m = ch.MatPhang(chay=r, goc=tmp_path, ping=lambda u, s: True)
    m.mat_khau_sao_luu()
    with (tmp_path / ".env.nen").open("a", encoding="utf-8") as f:
        f.write("SAO_LUU_LENH_NGOAI=rclone copyto {tep} b2:cskh/{ma}/{ten}\n")
    kq = m.sao_luu_day_du("shopa")
    assert kq["ngoai"] is True and r.dau_moc[".sao_luu_ra_ngoai_may"]["ok"] is True
    lenh = next(lenh for lenh, _ in r.lenh if lenh[:1] == ["rclone"])
    assert lenh[2] == str(kq["tep"]) and lenh[3] == f"b2:cskh/shopa/{kq['tep'].name}"


def test_thu_phuc_hoi_giai_ma_truoc_khi_pg_restore(mp):
    m, r = mp
    m.sao_luu_day_du("shopa")
    kq = m.thu_phuc_hoi("shopa")
    assert r.restore_vao == r.pg_dump, "pg_restore phải nhận bản đã giải mã"
    assert kq["tep"].endswith(".dump.cskh")
    assert ".thu_phuc_hoi" in r.dau_moc


def test_khoi_tao_sinh_mat_khau_sao_luu(tmp_path):
    ch.khoi_tao(goc=tmp_path)
    nen = (tmp_path / ".env.nen").read_text(encoding="utf-8")
    assert "SAO_LUU_MAT_KHAU=" in nen and "SAO_LUU_MAT_KHAU=\n" not in nen
    assert "SAO_LUU_THU_MUC_NGOAI=" in nen and "SAO_LUU_LENH_NGOAI=" in nen


# ================================================================ 2b. san_sang silo

def test_san_sang_silo_co_muc_ma_hoa_ngoai_may():
    """Trước đây mục này bị BỎ trong silo → ĐỦ giả."""
    src = (ROOT / "scripts" / "san_sang.py").read_text(encoding="utf-8")
    assert "*([] if trong_silo() else [kiem_ma_hoa_sao_luu()])" not in src
    f = ss.doc_ma_hoa_sao_luu_silo
    assert f(None, None)["muc"] != ss.DU
    assert f({"luc": _luc(3)}, None)["muc"] == ss.CHAN, "bản rõ = chặn"
    assert f({"luc": _luc(3), "ma_hoa": True}, None)["muc"] == ss.CANH_BAO
    assert f({"luc": _luc(3), "ma_hoa": True, "du_lieu": False},
             {"luc": _luc(1), "ok": True})["muc"] == ss.CANH_BAO
    assert f({"luc": _luc(3), "ma_hoa": True}, {"luc": _luc(60), "ok": True})["muc"] == ss.CANH_BAO
    assert f({"luc": _luc(3), "ma_hoa": True}, {"luc": _luc(3), "ok": True})["muc"] == ss.DU


def test_san_sang_silo_doc_dau_moc_that(monkeypatch, tmp_path):
    monkeypatch.setattr(ss, "ROOT", tmp_path)
    monkeypatch.setenv("CSKH_SILO", "1")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / ".sao_luu_ngoai").write_text(json.dumps({"luc": _luc(2)}), encoding="utf-8")
    assert ss.kiem_ma_hoa_sao_luu()["muc"] == ss.CHAN, "dấu mốc cũ = bản rõ"
    (tmp_path / "data" / ".sao_luu_may_chu").write_text(
        json.dumps({"luc": _luc(2), "ma_hoa": True, "du_lieu": True}), encoding="utf-8")
    (tmp_path / "data" / ".sao_luu_ra_ngoai_may").write_text(
        json.dumps({"luc": _luc(2), "ok": True}), encoding="utf-8")
    assert ss.kiem_ma_hoa_sao_luu()["muc"] == ss.DU


# ================================================================ 8. ping từ máy chủ

def test_ping_silo_doc_dau_moc_that_khong_chi_co_url():
    f = ss.doc_ping_silo
    assert f(False, None)["muc"] == ss.CANH_BAO
    assert f(True, None)["muc"] == ss.CANH_BAO, "có URL mà chưa ping lần nào = chưa có gì"
    assert f(True, {"luc": _luc(1), "ok": True})["muc"] == ss.CANH_BAO, "1 giờ = cron đã ngừng"
    assert f(True, {"luc": _luc(0.05), "ok": False})["muc"] == ss.CANH_BAO
    assert f(True, {"luc": _luc(0.05), "ok": True})["muc"] == ss.DU


def test_san_sang_silo_dung_kiem_ping_that(monkeypatch, tmp_path):
    monkeypatch.setattr(ss, "ROOT", tmp_path)
    monkeypatch.setenv("CSKH_SILO", "1")
    monkeypatch.setattr(ss.settings, "canh_gac_ping_url", "https://hc-ping.com/x")
    assert ss.kiem_ping_con_song()["muc"] == ss.CANH_BAO
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / ".ping_con_song").write_text(
        json.dumps({"luc": _luc(0.05), "ok": True}), encoding="utf-8")
    assert ss.kiem_ping_con_song()["muc"] == ss.DU


def test_kiem_sua_ping_tung_cua_hang_va_ghi_dau_moc(tmp_path):
    r = _Runner()
    da_ping: list[tuple[str, bool]] = []
    m = ch.MatPhang(chay=r, goc=tmp_path, ping=lambda u, s: da_ping.append((u, s)) or True)
    (tmp_path / "cua_hang" / "shopa").mkdir(parents=True)
    (tmp_path / "cua_hang" / "shopa" / ".env").write_text(
        "CANH_GAC_PING_URL=https://hc-ping.com/abc\n", encoding="utf-8")
    m.sua_hong()
    assert da_ping == [("https://hc-ping.com/abc", True)]
    assert r.dau_moc[".ping_con_song"]["ok"] is True
    assert ".canh_gac_ngoai" in r.dau_moc


def test_kiem_sua_khong_url_thi_khong_ping_khong_ghi(tmp_path):
    r = _Runner()
    da_ping: list = []
    m = ch.MatPhang(chay=r, goc=tmp_path, ping=lambda u, s: da_ping.append(u) or True)
    (tmp_path / "cua_hang" / "shopa").mkdir(parents=True)
    m.sua_hong()
    assert da_ping == [] and ".ping_con_song" not in r.dau_moc


def test_url_ping_khong_di_theo_goi_chuyen_nha():
    """Mang sang VPS: máy cũ chết mà VPS vẫn ping cùng check → không ai được báo."""
    assert "CANH_GAC_PING_URL" in chuyen_nha.KHONG_MANG
    for ten in (".sao_luu_may_chu", ".ping_con_song", ".sao_luu_ra_ngoai_may"):
        assert chuyen_nha._BO_DU_LIEU.search(ten), ten


def test_huong_dan_vps_noi_cat_khoa_ngoai_may():
    doc = (ROOT / "docs" / "len-vps.md").read_text(encoding="utf-8")
    for can in ("CREDENTIAL_MASTER_KEYS", "SAO_LUU_MAT_KHAU", "SAO_LUU_THU_MUC_NGOAI",
                "SAO_LUU_LENH_NGOAI", "CANH_GAC_PING_URL"):
        assert can in doc, can
