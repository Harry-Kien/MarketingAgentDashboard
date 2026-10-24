"""
Mặt phẳng điều khiển SaaS (`scripts/cua_hang.py`) — không cần Docker.

Mọi lệnh ra ngoài đi qua một runner giả ghi lại từng lệnh. Canh:
- mã/tên miền sai bị chặn TRƯỚC khi chạm CSDL (mã đi vào tên role/CSDL);
- bí mật không bao giờ nằm trên dòng lệnh (danh sách tiến trình đọc được);
- mỗi cửa hàng bí mật riêng, không trùng nhau;
- compose ĐÚNG MỘT bản app;
- xoá chỉ chạy sau khi sao lưu thành công.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from scripts import cua_hang as ch


class _Runner:
    def __init__(self, danh_sach=None, pg_dump=b"PGDMP-gia", health="healthy"):
        self.lenh: list[tuple[list[str], str | None]] = []
        self.danh_sach = danh_sach or []
        self.pg_dump = pg_dump
        self.health = health

    def __call__(self, lenh, *, dau_vao=None, cwd=None, nhi_phan=False):
        self.lenh.append((list(lenh), dau_vao))
        out: object = ""
        if "pg_dump" in lenh:
            out = self.pg_dump
        elif "inspect" in lenh:
            out = self.health + "\n"
        elif dau_vao and "json_agg" in dau_vao:
            out = json.dumps(self.danh_sach)
        return subprocess.CompletedProcess(lenh, 0 if out is not None else 1, out, "")


@pytest.fixture
def mp(tmp_path, monkeypatch):
    monkeypatch.setattr(ch.time, "sleep", lambda s: None)
    r = _Runner()
    return ch.MatPhang(chay=r, goc=tmp_path), r


@pytest.mark.parametrize("ma", ["ab", "Shop1", "shop-1", "a" * 21, "x;drop", "", "shop 1"])
def test_ma_sai_bi_chan(ma):
    with pytest.raises(ch.LoiCuaHang):
        ch.kiem_ma(ma)


@pytest.mark.parametrize("tm", ["localhost", "shop", "-a.vn", "a..vn", "http://a.vn", "a.vn/x"])
def test_ten_mien_sai_bi_chan(tm):
    with pytest.raises(ch.LoiCuaHang):
        ch.kiem_ten_mien(tm)


def test_bi_mat_rieng_moi_cua_hang():
    a, b = ch.sinh_bi_mat(), ch.sinh_bi_mat()
    assert all(a[k] != b[k] for k in a)
    import base64
    assert len(base64.b64decode(a["KHOA_VAULT"])) == 32


def test_tep_sinh_ra_day_du_va_mot_ban_app():
    tep = ch.sinh_tep("shopa", "shopa.vi-du.vn", ch.sinh_bi_mat())
    assert "«" not in tep[".env"] and "«" not in tep["compose.yml"]
    assert "DATABASE_URL=postgresql://ch_shopa:" in tep[".env"]
    assert "PUBLIC_BASE_URL=https://shopa.vi-du.vn" in tep[".env"]
    assert "SAO_LUU_MOI_NGAY=false" in tep[".env"]
    assert tep["compose.yml"].count("replicas: 1") == 2
    from agent.security.credential_vault import parse_master_keys
    khoa = next(d for d in tep[".env"].splitlines() if d.startswith("CREDENTIAL_MASTER_KEYS="))
    assert parse_master_keys(khoa.split("=", 1)[1])          # app đọc được khoá


def test_dien_thieu_gia_tri_thi_no():
    with pytest.raises(ch.LoiCuaHang):
        ch.dien("A=«THIEU»", {})


def test_tao_khong_dua_bi_mat_len_dong_lenh(mp, tmp_path):
    m, r = mp
    tep = m.tao("shopa", "Shop A", "shopa.vi-du.vn")
    env = (tmp_path / "cua_hang" / "shopa" / ".env").read_text(encoding="utf-8")
    bi_mat = [d.split("=", 1)[1] for d in env.splitlines()
              if d.startswith(("CREDENTIAL_MASTER_KEYS=", "WEBHOOK_SECRET="))]
    mk_db = env.split("ch_shopa:", 1)[1].split("@", 1)[0]
    mk_qt = tep.read_text(encoding="utf-8").split("Mật khẩu: ", 1)[1].split()[0]
    for lenh, _ in r.lenh:
        dong = " ".join(lenh)
        for b in (*bi_mat, mk_db, mk_qt):
            assert b not in dong, f"bí mật lộ trên dòng lệnh: {lenh[:4]}"
    # Mật khẩu CSDL đi qua stdin của psql; mật khẩu quản trị qua stdin của app.
    assert any(dv and mk_db in dv for _, dv in r.lenh)
    assert any(dv and mk_qt in dv for _, dv in r.lenh)
    # Caddyfile có tên miền mới và được nạp lại.
    assert any("reload" in lenh for lenh, _ in r.lenh)


def test_tao_role_khong_phai_superuser(mp):
    sql = " ".join(s for _, s in ch.sql_tao_csdl("shopa", "x"))
    assert "NOSUPERUSER" in sql and "NOCREATEDB" in sql and "REVOKE ALL ON DATABASE ch_shopa" in sql
    # Đo 23.10.2026: thiếu dòng này thì role cửa hàng kết nối được CSDL khác.
    assert "REVOKE CONNECT ON DATABASE postgres, saas_dieu_khien FROM PUBLIC" in sql


def test_trung_ma_hoac_ten_mien_bi_chan(tmp_path, monkeypatch):
    r = _Runner(danh_sach=[{"ma": "shopa", "ten_mien": "a.vi-du.vn", "trang_thai": "chay"}])
    m = ch.MatPhang(chay=r, goc=tmp_path)
    with pytest.raises(ch.LoiCuaHang):
        m.tao("shopa", "X", "khac.vi-du.vn")
    with pytest.raises(ch.LoiCuaHang):
        m.tao("shopb", "X", "a.vi-du.vn")
    assert not any("CREATE ROLE" in (dv or "") for _, dv in r.lenh)


def test_xoa_sao_luu_truoc_va_doi_xac_nhan(tmp_path):
    r = _Runner()
    m = ch.MatPhang(chay=r, goc=tmp_path)
    (tmp_path / "cua_hang" / "shopa").mkdir(parents=True)
    with pytest.raises(ch.LoiCuaHang):
        m.xoa("shopa", "shopb")
    assert r.lenh == []
    ban = m.xoa("shopa", "shopa")
    assert ban.exists() and ban.read_bytes() == b"PGDMP-gia"
    thu_tu = [" ".join(lenh) for lenh, dv in r.lenh] + [dv or "" for _, dv in r.lenh]
    i_dump = next(i for i, (lenh, _) in enumerate(r.lenh) if "pg_dump" in lenh)
    i_drop = next(i for i, (_, dv) in enumerate(r.lenh) if dv and "DROP DATABASE" in dv)
    assert i_dump < i_drop
    assert thu_tu


def test_sao_luu_rong_thi_khong_xoa(tmp_path):
    r = _Runner(pg_dump=b"")
    m = ch.MatPhang(chay=r, goc=tmp_path)
    (tmp_path / "cua_hang" / "shopa").mkdir(parents=True)
    with pytest.raises(ch.LoiCuaHang):
        m.xoa("shopa", "shopa")
    assert not any(dv and "DROP" in dv for _, dv in r.lenh)


def test_caddy_co_header_bao_mat_va_gioi_han_body():
    c = ch.sinh_caddy([("shopa", "shopa.vi-du.vn")], "ops@vi-du.vn")
    assert "email ops@vi-du.vn" in c
    assert "reverse_proxy cskh-shopa-app:8000" in c
    assert "Strict-Transport-Security" in c and "max_size 20MB" in c


def test_khoi_tao_khong_ghi_de(tmp_path):
    assert ch.khoi_tao(tmp_path)
    cu = (tmp_path / ".env.nen").read_text(encoding="utf-8")
    assert ch.khoi_tao(tmp_path) == []
    assert (tmp_path / ".env.nen").read_text(encoding="utf-8") == cu


def test_bi_mat_trien_khai_bi_gitignore():
    from pathlib import Path
    gi = (Path(ch.GOC) / ".gitignore").read_text(encoding="utf-8")
    for mau in ("trien_khai/cua_hang/", "trien_khai/.env.nen", "trien_khai/sao_luu/",
                "trien_khai/caddy/Caddyfile"):
        assert mau in gi, mau


def test_doc_duong_sao_luu_bench_that():
    """Bản in THẬT của ERPNext 15.120 (24.10.2026): đường dẫn tương đối với sites/."""
    ra = ("Backup Summary for localhost at 2026-10-24 22:36:12.852182\n"
          "Config  : ./localhost/private/backups/20261024_223609-localhost-site_config_backup.json 161.0B\n"
          "Database: ./localhost/private/backups/20261024_223609-localhost-database.sql.gz         847.2KiB\n"
          "Public  : ./localhost/private/backups/20261024_223609-localhost-files.tar               10.0KiB\n"
          "Private : ./localhost/private/backups/20261024_223609-localhost-private-files.tar       10.0KiB\n")
    d = ch.duong_sao_luu_bench(ra)
    assert len(d) == 4
    assert all(x.startswith("/home/frappe/frappe-bench/sites/localhost/private/backups/") for x in d)
    assert any(x.endswith("-database.sql.gz") for x in d)
