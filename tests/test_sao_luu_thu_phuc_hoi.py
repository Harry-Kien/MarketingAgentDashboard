"""`python -m scripts.sao_luu --thu-phuc-hoi` — chỉ ghi dấu mốc khi ĐẠT."""
from __future__ import annotations

import gzip
import json
import subprocess

from scripts import sao_luu as sl


class _Docker:
    def __init__(self, phuc_hoi_hong=False, so_bang="61", so_that="61"):
        self.phuc_hoi_hong, self.so_bang, self.so_that = phuc_hoi_hong, so_bang, so_that
        self.lenh: list[list[str]] = []

    def __call__(self, lenh, input=None, **kw):
        self.lenh.append(lenh)
        sql = lenh[lenh.index("-c") + 1] if "-c" in lenh else ""
        csdl = lenh[lenh.index("-d") + 1]
        if input is not None:
            return subprocess.CompletedProcess(lenh, 1 if self.phuc_hoi_hong else 0, b"",
                                               b"ERROR: hong" if self.phuc_hoi_hong else b"")
        if "information_schema" in sql:
            ra = self.so_bang if csdl.startswith("thu_phuc_hoi_") else self.so_that
            return subprocess.CompletedProcess(lenh, 0, ra.encode(), b"")
        if "messages" in sql:
            return subprocess.CompletedProcess(lenh, 0, b"198", b"")
        return subprocess.CompletedProcess(lenh, 0, b"", b"")


def _chuan_bi(tmp_path, monkeypatch, docker):
    kho = tmp_path / "backup"
    kho.mkdir()
    with gzip.open(kho / "db-20261026-010000.sql.gz", "wb") as f:
        f.write(b"-- dump\n")
    monkeypatch.setattr(sl, "KHO", kho)
    monkeypatch.setattr(sl, "DAU_MOC_PHUC_HOI", tmp_path / ".thu_phuc_hoi")
    monkeypatch.setattr(sl, "_container", lambda: "marketing-agent-db-1")
    monkeypatch.setattr(sl.subprocess, "run", docker)


def test_dat_thi_ghi_dau_moc_va_luon_xoa_csdl_tam(tmp_path, monkeypatch):
    d = _Docker()
    _chuan_bi(tmp_path, monkeypatch, d)
    ok, ghi = sl.thu_phuc_hoi()
    assert ok, ghi
    moc = json.loads((tmp_path / ".thu_phuc_hoi").read_text(encoding="utf-8"))
    assert moc["so_bang"] == 61 and moc["so_tin"] == 198
    assert any("DROP DATABASE IF EXISTS thu_phuc_hoi_" in " ".join(lenh) for lenh in d.lenh)


def test_phuc_hoi_hong_thi_khong_ghi_dau_moc_nhung_van_xoa_csdl_tam(tmp_path, monkeypatch):
    d = _Docker(phuc_hoi_hong=True)
    _chuan_bi(tmp_path, monkeypatch, d)
    ok, _ = sl.thu_phuc_hoi()
    assert not ok and not (tmp_path / ".thu_phuc_hoi").exists()
    assert any("DROP DATABASE" in " ".join(lenh) for lenh in d.lenh)


def test_thieu_bang_so_voi_csdl_that_thi_hong(tmp_path, monkeypatch):
    _chuan_bi(tmp_path, monkeypatch, _Docker(so_bang="40", so_that="61"))
    ok, ghi = sl.thu_phuc_hoi()
    assert not ok and "thiếu" in ghi and not (tmp_path / ".thu_phuc_hoi").exists()
