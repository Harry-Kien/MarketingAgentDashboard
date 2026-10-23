"""
App và sidecar phải bật TÁCH RỜI khỏi tiến trình bật chúng.

23.10.2026: production chết theo chu kỳ hơn hai tiếng — người canh bật lại
app, Task Scheduler dừng lượt chạy quá 3 phút và giết luôn app vừa bật. Xem
scripts/tach_roi.py.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts import tach_roi

ROOT = Path(__file__).resolve().parent.parent


class _PopenGia:
    def __init__(self, loi_lan_dau: bool = False):
        self.goi: list[dict] = []
        self.loi_lan_dau = loi_lan_dau

    def __call__(self, lenh, **kw):
        self.goi.append(kw)
        if self.loi_lan_dau and len(self.goi) == 1:
            raise OSError(5, "Access is denied")
        return object()


@pytest.mark.skipif(os.name != "nt", reason="cờ tách job chỉ có trên Windows")
def test_windows_tach_khoi_job_va_console(monkeypatch, tmp_path):
    gia = _PopenGia()
    monkeypatch.setattr(tach_roi.subprocess, "Popen", gia)
    mo_ta = tach_roi.bat(["x"], cwd=tmp_path, nhat_ky=tmp_path / "a.log")
    co = gia.goi[0]["creationflags"]
    assert co & subprocess.CREATE_BREAKAWAY_FROM_JOB
    assert co & subprocess.DETACHED_PROCESS and co & subprocess.CREATE_NEW_PROCESS_GROUP
    assert gia.goi[0]["stdin"] is subprocess.DEVNULL
    assert mo_ta.startswith("tách rời")


@pytest.mark.skipif(os.name != "nt", reason="cờ tách job chỉ có trên Windows")
def test_job_cam_tach_thi_van_bat_va_NOI_RA(monkeypatch, tmp_path):
    """App chết theo còn hơn không có app — nhưng nhật ký phải nói lý do."""
    gia = _PopenGia(loi_lan_dau=True)
    monkeypatch.setattr(tach_roi.subprocess, "Popen", gia)
    mo_ta = tach_roi.bat(["x"], cwd=tmp_path, nhat_ky=tmp_path / "a.log")
    assert len(gia.goi) == 2
    assert not gia.goi[1]["creationflags"] & subprocess.CREATE_BREAKAWAY_FROM_JOB
    assert mo_ta.startswith("KHÔNG tách được")


def test_bat_that_va_ghi_duoc_nhat_ky(tmp_path):
    """Cờ đúng trên hệ điều hành này: tiến trình thật chạy và ghi được log."""
    log = tmp_path / "con.log"
    tach_roi.bat([sys.executable, "-c", "print('song')"], cwd=tmp_path, nhat_ky=log)
    for _ in range(100):
        if log.exists() and "song" in log.read_text(encoding="utf-8", errors="replace"):
            break
        time.sleep(0.1)
    assert "song" in log.read_text(encoding="utf-8", errors="replace")


def _goi_popen_trong(tep: str, ham: str | None = None) -> list[int]:
    cay = ast.parse((ROOT / tep).read_text(encoding="utf-8"))
    goc = cay if ham is None else next(
        n for n in ast.walk(cay) if isinstance(n, ast.FunctionDef) and n.name == ham)
    return [n.lineno for n in ast.walk(goc)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "Popen"]


def test_app_va_sidecar_di_qua_tach_roi():
    """Bật app/sidecar bằng Popen trần là quay lại đúng lỗi 23.10.2026."""
    assert _goi_popen_trong("scripts/khoi_dong.py", "_bat_app") == []
    assert "tach_roi.bat(" in (ROOT / "scripts/khoi_dong.py").read_text(encoding="utf-8")
    assert _goi_popen_trong("scripts/chay_sidecar_zalo.py", "main") == []
    assert "tach_roi.bat(" in (ROOT / "scripts/chay_sidecar_zalo.py").read_text(encoding="utf-8")


def test_nguoi_canh_chay_python_khong_dem_dau_ra():
    """Lượt bị dừng giữa chừng mà dầu ra còn trong bộ đệm là mất sạch nhật ký."""
    bat = (ROOT / "scripts" / "canh_gac_ngoai.bat").read_text(encoding="ascii")
    assert "python.exe\" -u -m scripts.canh_gac_ngoai" in bat


def test_python_that_doc_home_trong_pyvenv_cfg(tmp_path, monkeypatch):
    """Bộ khởi chạy venv chết khi bật tách rời — phải bật thẳng trình gốc."""
    goc = tmp_path / "Python312"
    goc.mkdir()
    (goc / "python.exe").write_text("", encoding="utf-8")
    venv = tmp_path / ".venv"
    (venv / "Scripts").mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text(f"home = {goc}\nversion = 3.12.5\n", encoding="utf-8")
    stub = venv / "Scripts" / "python.exe"
    monkeypatch.setattr(tach_roi.os, "name", "nt")
    exe, env = tach_roi.python_that(stub)
    assert exe == str(goc / "python.exe")
    assert env == {"__PYVENV_LAUNCHER__": str(stub)}


def test_python_that_khong_phai_venv_thi_giu_nguyen(tmp_path):
    exe = tmp_path / "python.exe"
    assert tach_roi.python_that(exe) == (str(exe), {})


@pytest.mark.skipif(os.name != "nt", reason="bộ khởi chạy venv chỉ có trên Windows")
def test_trinh_that_nap_dung_thu_vien_cua_venv(tmp_path):
    """Đo thật: trình gốc + __PYVENV_LAUNCHER__ thấy sys.prefix là venv và import được uvicorn."""
    stub = ROOT / ".venv" / "Scripts" / "python.exe"
    if not stub.exists():
        stub = Path(sys.prefix) / "Scripts" / "python.exe"
    if not (stub.parent.parent / "pyvenv.cfg").exists():
        pytest.skip("không chạy trong venv")
    exe, them = tach_roi.python_that(stub)
    r = subprocess.run([exe, "-c", "import sys, uvicorn; print(sys.prefix)"],
                       env={**os.environ, **them}, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-400:]
    assert Path(r.stdout.strip()).resolve() == stub.parent.parent.resolve()


def test_app_bat_bang_trinh_that_khong_qua_bo_khoi_chay():
    nguon = (ROOT / "scripts" / "khoi_dong.py").read_text(encoding="utf-8")
    than = nguon[nguon.index("def _bat_app"):nguon.index("def _tat_app")]
    assert "python_that(" in than
