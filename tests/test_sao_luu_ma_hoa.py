"""
Sao lưu mã hoá + bản ngoài máy.

Bản sao lưu chứa SĐT, địa chỉ, ảnh da của khách (dữ liệu nhạy cảm — Luật
BVDLCN 91/2025). Ba ràng buộc:
  1. có mật khẩu thì KHÔNG còn bản thường nào trên đĩa;
  2. bản chưa mã hoá KHÔNG BAO GIỜ được chép ra ngoài máy;
  3. mã hoá không được làm hỏng phép thử phục hồi — phục hồi phải đọc được.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import goi_ma_hoa
from scripts import sao_luu as sl

SQL = b"CREATE TABLE t (id int);\nINSERT INTO t VALUES (1);\n" + sl.DAU_KET_THUC + b"\n"


@pytest.fixture
def kho(tmp_path, monkeypatch):
    k = tmp_path / "backup"
    monkeypatch.setattr(sl, "KHO", k)
    monkeypatch.setattr(sl, "DAU_MOC_NGOAI", tmp_path / ".sao_luu_ra_ngoai_may")
    monkeypatch.setattr(sl, "_container", lambda: "marketing-agent-db-1")
    monkeypatch.setattr(sl.subprocess, "run",
                        lambda *a, **kw: subprocess.CompletedProcess(a, 0, stdout=SQL, stderr=b""))
    monkeypatch.setattr(sl.settings, "sao_luu_mat_khau", "")
    monkeypatch.setattr(sl.settings, "sao_luu_thu_muc_ngoai", "")
    return k


def test_co_mat_khau_thi_khong_con_ban_thuong(kho, monkeypatch):
    monkeypatch.setattr(sl.settings, "sao_luu_mat_khau", "mk-thu-nghiem-dai")
    ok, ghi = sl.sao_luu_db(kho / "db-20261028-010000.sql.gz")
    assert ok and "đã mã hoá" in ghi
    assert [p.name for p in kho.iterdir()] == ["db-20261028-010000.sql.gz.cskh"]
    tep = kho / "db-20261028-010000.sql.gz.cskh"
    assert SQL not in tep.read_bytes() and b"INSERT INTO" not in tep.read_bytes()
    assert sl.doc_ban_db(tep) == SQL
    with pytest.raises(goi_ma_hoa.LoiGoi):
        sl.doc_ban_db(tep, mat_khau="sai")


def test_khong_mat_khau_thi_noi_ro_la_chua_ma_hoa(kho):
    ok, ghi = sl.sao_luu_db(kho / "db-1.sql.gz")
    assert ok and "CHƯA MÃ HOÁ" in ghi
    assert sl.doc_ban_db(kho / "db-1.sql.gz") == SQL


def test_ban_ma_hoa_ma_mat_mat_khau_thi_no_to(kho, monkeypatch):
    monkeypatch.setattr(sl.settings, "sao_luu_mat_khau", "mk")
    sl.sao_luu_db(kho / "db-1.sql.gz")
    monkeypatch.setattr(sl.settings, "sao_luu_mat_khau", "")
    with pytest.raises(goi_ma_hoa.LoiGoi, match="SAO_LUU_MAT_KHAU"):
        sl.doc_ban_db(kho / "db-1.sql.gz.cskh")


def test_chep_ra_ngoai_chi_ban_ma_hoa(kho, tmp_path, monkeypatch):
    ngoai = tmp_path / "OneDrive" / "SaoLuu"
    monkeypatch.setattr(sl.settings, "sao_luu_mat_khau", "mk")
    monkeypatch.setattr(sl.settings, "sao_luu_thu_muc_ngoai", str(ngoai))
    ok, ghi = sl.sao_luu_db(kho / "db-1.sql.gz")
    assert ok and "đã chép ra" in ghi
    assert [p.name for p in ngoai.iterdir()] == ["db-1.sql.gz.cskh"]     # không có tệp ".dang-chep"
    moc = json.loads(sl.DAU_MOC_NGOAI.read_text(encoding="utf-8"))
    assert moc["ok"] is True

    # Bản thường: TỪ CHỐI chép.
    (kho / "db-0.sql.gz").write_bytes(b"x")
    ok, ghi = sl.chep_ra_ngoai(kho / "db-0.sql.gz", str(ngoai))
    assert not ok and "KHÔNG chép bản chưa mã hoá" in ghi
    assert not (ngoai / "db-0.sql.gz").exists()


def test_chep_hong_thi_ghi_dau_moc_hong(kho, tmp_path, monkeypatch):
    la_tep = tmp_path / "khong-phai-thu-muc"
    la_tep.write_text("x")
    monkeypatch.setattr(sl.settings, "sao_luu_mat_khau", "mk")
    monkeypatch.setattr(sl.settings, "sao_luu_thu_muc_ngoai", str(la_tep))
    ok, ghi = sl.sao_luu_db(kho / "db-1.sql.gz")
    assert ok, "bản trong máy vẫn tốt — hỏng chép ra ngoài không được làm hỏng cả lượt"
    assert "KHÔNG chép ra ngoài được" in ghi
    assert json.loads(sl.DAU_MOC_NGOAI.read_text(encoding="utf-8"))["ok"] is False


def test_giu_n_ban_tinh_chung_hai_loai(kho, monkeypatch):
    kho.mkdir()
    for i in range(1, 6):
        (kho / f"db-2026102{i}-000000.sql.gz").write_bytes(b"x")
    for i in range(6, 9):
        (kho / f"db-2026102{i}-000000.sql.gz.cskh").write_bytes(b"x")
    sl.don_ban_cu(3)
    assert [p.name for p in sl.ban_db()] == [
        "db-20261026-000000.sql.gz.cskh", "db-20261027-000000.sql.gz.cskh",
        "db-20261028-000000.sql.gz.cskh"]


def test_moi_noi_doc_sao_luu_deu_hieu_ban_ma_hoa():
    """Bật mã hoá mà một chỗ chỉ tìm *.sql.gz là chỗ đó báo 'chưa có bản sao nào' — đỏ giả."""
    goc = Path(__file__).resolve().parent.parent
    assert ".cskh" in (goc / "agent" / "suc_khoe.py").read_text(encoding="utf-8")
    src = (goc / "scripts" / "sao_luu.py").read_text(encoding="utf-8")
    i = src.index("def thu_phuc_hoi(")
    assert "ban_db()" in src[i:i + 2000] and "doc_ban_db(" in src[i:i + 2500]


# ------------------------------------------------------------------ san_sang

def test_san_sang_ma_hoa_sao_luu():
    from datetime import datetime, timedelta, timezone

    from scripts.san_sang import CANH_BAO, DU, doc_ma_hoa_sao_luu as doc

    moi = {"luc": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(), "ok": True}
    cu = {"luc": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(), "ok": True}
    assert doc(False, False, False, None)["muc"] == CANH_BAO
    assert doc(True, False, True, moi)["muc"] == CANH_BAO          # mật khẩu có, bản mới vẫn thường
    assert doc(True, True, False, None)["muc"] == CANH_BAO          # chỉ một bản cùng máy
    assert doc(True, True, True, cu)["muc"] == CANH_BAO             # bản ngoài máy cũ
    assert doc(True, True, True, {**moi, "ok": False, "ghi": "USB rút"})["muc"] == CANH_BAO
    assert doc(True, True, True, moi)["muc"] == DU


def test_ho_so_bvdlcn_khai_dung_cau_hinh(monkeypatch):
    from scripts import sinh_ho_so_bvdlcn as h

    monkeypatch.setattr(h.settings, "sao_luu_mat_khau", "")
    assert "chưa mã hoá" in h.sinh() and "mã hoá AES-256-GCM" not in h.sinh()
    monkeypatch.setattr(h.settings, "sao_luu_mat_khau", "mk")
    monkeypatch.setattr(h.settings, "sao_luu_thu_muc_ngoai", "")
    assert "mã hoá AES-256-GCM" in h.sinh() and "Chưa có bản ngoài máy" in h.sinh()
