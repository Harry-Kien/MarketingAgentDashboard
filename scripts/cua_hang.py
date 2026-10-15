"""
Mặt phẳng điều khiển SaaS: dựng, dừng, sao lưu, xoá từng CỬA HÀNG.

    python -m scripts.cua_hang khoi_tao                     sinh trien_khai/.env.nen + Caddyfile
    python -m scripts.cua_hang tao <ma> --ten "Tên" --ten-mien shop.vi-du.vn
    python -m scripts.cua_hang liet_ke
    python -m scripts.cua_hang kiem                         mã thoát ≠ 0 nếu có cửa hàng hỏng
    python -m scripts.cua_hang tam_dung <ma> | chay <ma> | khoi_dong_lai <ma>
    python -m scripts.cua_hang sao_luu <ma> | --tat-ca
    python -m scripts.cua_hang xoa <ma> --xac-nhan <ma>     sao lưu TRƯỚC, rồi mới xoá

MÔ HÌNH SILO
------------
Mỗi cửa hàng: một CSDL `ch_<ma>` + role `ch_<ma>` (không phải superuser,
chỉ sở hữu CSDL của mình), một container app, một container sidecar, một
volume dữ liệu, một tên miền có TLS. Chung: máy chủ Postgres và Caddy
(`trien_khai/docker-compose.nen.yml`). Lý do chọn silo thay vì RLS:
docs/superpowers/plans/2026-10-15-giai-doan-2-nen-saas-silo.md.

KHÔNG IN BÍ MẬT
---------------
Mật khẩu CSDL, khoá vault, mật khẩu quản trị viên đầu tiên đều ghi vào tệp
trong `trien_khai/cua_hang/<ma>/` (bị .gitignore chặn). SQL chứa mật khẩu
đi qua stdin của `psql`, không qua đối số dòng lệnh — đối số nằm trong danh
sách tiến trình mà ai trên máy cũng đọc được.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GOC = Path(__file__).resolve().parent.parent
TRIEN_KHAI = GOC / "trien_khai"
THU_MUC = TRIEN_KHAI / "cua_hang"
MAU = TRIEN_KHAI / "mau"
CADDYFILE = TRIEN_KHAI / "caddy" / "Caddyfile"
ENV_NEN = TRIEN_KHAI / ".env.nen"
SAO_LUU = TRIEN_KHAI / "sao_luu"

PG = "cskh-postgres"
PG_QUAN_TRI = "quan_tri"
CSDL_DIEU_KHIEN = "saas_dieu_khien"
IMAGE_APP = os.environ.get("CSKH_IMAGE_APP", "cskh-app:latest")
IMAGE_SIDECAR = os.environ.get("CSKH_IMAGE_SIDECAR", "cskh-sidecar:latest")

# Mã đi thẳng vào TÊN role/CSDL/container — định danh SQL không tham số hoá
# được, nên chặn ở đây bằng danh sách ký tự cho phép, không bằng thoát chuỗi.
_MA = re.compile(r"^[a-z0-9]{3,20}$")
_TEN_MIEN = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class LoiCuaHang(Exception):
    """Lỗi người vận hành sửa được — in ra, mã thoát 2."""


# ---------------------------------------------------------------- thuần

def kiem_ma(ma: str) -> str:
    if not _MA.match(ma or ""):
        raise LoiCuaHang("Mã cửa hàng: 3–20 ký tự, chỉ chữ thường không dấu và số.")
    return ma


def kiem_ten_mien(ten_mien: str) -> str:
    ten_mien = (ten_mien or "").strip().lower()
    if not _TEN_MIEN.match(ten_mien):
        raise LoiCuaHang(f"Tên miền không hợp lệ: {ten_mien!r}")
    return ten_mien


def sinh_bi_mat() -> dict[str, str]:
    """Bí mật RIÊNG cho một cửa hàng. Không ký tự nào cần thoát trong URL/SQL."""
    return {
        "MAT_KHAU_DB": secrets.token_urlsafe(24),
        "KHOA_VAULT": base64.b64encode(secrets.token_bytes(32)).decode(),
        "WEBHOOK_SECRET": secrets.token_urlsafe(32),
        "SIDECAR_SECRET": secrets.token_urlsafe(32),
    }


def dien(mau: str, gia_tri: dict[str, str]) -> str:
    """Thay «KHOA». Còn «…» nào sót là nổ — tệp cấu hình thiếu một giá trị
    trông y hệt tệp đúng, và app lên với chuỗi «X» làm mật khẩu."""
    for k, v in gia_tri.items():
        mau = mau.replace(f"«{k}»", v)
    if (con := re.findall(r"«[A-Z_]+»", mau)):
        raise LoiCuaHang(f"mẫu còn chỗ chưa điền: {sorted(set(con))}")
    return mau


def sinh_tep(ma: str, ten_mien: str, bi_mat: dict[str, str], *,
             image_app: str = IMAGE_APP, image_sidecar: str = IMAGE_SIDECAR) -> dict[str, str]:
    gia_tri = {"MA": ma, "TEN_MIEN": ten_mien, "IMAGE_APP": image_app,
               "IMAGE_SIDECAR": image_sidecar, **bi_mat}
    return {
        ".env": dien((MAU / "env.cua_hang").read_text(encoding="utf-8"), gia_tri),
        "compose.yml": dien((MAU / "compose.cua_hang.yml").read_text(encoding="utf-8"), gia_tri),
    }


def sinh_caddy(cac_cua_hang: list[tuple[str, str]], email: str = "") -> str:
    dau = ("{\n" + (f"\temail {email}\n" if email else "") + "}\n\n")
    khoi = []
    for ma, ten_mien in sorted(cac_cua_hang):
        khoi.append(f"""{ten_mien} {{
\tencode gzip
\trequest_body {{
\t\tmax_size 20MB
\t}}
\theader {{
\t\tStrict-Transport-Security "max-age=31536000"
\t\tX-Content-Type-Options nosniff
\t\tReferrer-Policy strict-origin-when-cross-origin
\t\tX-Frame-Options SAMEORIGIN
\t\t-Server
\t}}
\treverse_proxy cskh-{ma}-app:8000
}}
""")
    return dau + "\n".join(khoi)


def _q(s: str) -> str:
    """Chuỗi SQL. Bí mật do `sinh_bi_mat` sinh không có dấu nháy, nhưng
    thoát vẫn bắt buộc — đây là chỗ một ngày nào đó ai đó truyền chuỗi khác."""
    return "'" + s.replace("'", "''") + "'"


def sql_tao_csdl(ma: str, mat_khau: str) -> list[tuple[str, str]]:
    """(CSDL chạy, SQL). Tách vì CREATE DATABASE không chạy trong transaction."""
    kiem_ma(ma)
    r = f"ch_{ma}"
    return [
        ("postgres", f"CREATE ROLE {r} LOGIN PASSWORD {_q(mat_khau)} "
                     "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;"),
        ("postgres", f"CREATE DATABASE {r} OWNER {r};"),
        ("postgres", f"REVOKE ALL ON DATABASE {r} FROM PUBLIC;"),
        # Extension tạo bằng superuser: role thường không tạo được `vector`.
        # App chạy schema.sql với CREATE EXTENSION IF NOT EXISTS — có sẵn rồi
        # thì lệnh ấy không đòi quyền gì.
        (r, 'CREATE EXTENSION IF NOT EXISTS vector; '
            'CREATE EXTENSION IF NOT EXISTS unaccent; '
            'CREATE EXTENSION IF NOT EXISTS pg_trgm; '
            'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; '
            'CREATE EXTENSION IF NOT EXISTS pgcrypto; '
            f'ALTER SCHEMA public OWNER TO {r};'),
    ]


SQL_DIEU_KHIEN = """
CREATE TABLE IF NOT EXISTS cua_hang (
    ma          TEXT PRIMARY KEY CHECK (ma ~ '^[a-z0-9]{3,20}$'),
    ten         TEXT NOT NULL,
    ten_mien    TEXT NOT NULL UNIQUE,
    goi         TEXT NOT NULL DEFAULT 'dung_thu',
    trang_thai  TEXT NOT NULL DEFAULT 'chay'
                CHECK (trang_thai IN ('chay', 'tam_dung', 'da_xoa')),
    tao_luc     TIMESTAMPTZ NOT NULL DEFAULT now(),
    cap_nhat_luc TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


# ---------------------------------------------------------------- tác dụng phụ

Chay = Callable[..., subprocess.CompletedProcess]


def _chay_that(lenh: list[str], *, dau_vao: str | None = None,
               cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(lenh, input=dau_vao, cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", check=False)


def _chay_nhi_phan(lenh, *, dau_vao=None, cwd=None, nhi_phan=False):
    if nhi_phan:
        return subprocess.run(lenh, cwd=cwd, capture_output=True, check=False)
    return _chay_that(lenh, dau_vao=dau_vao, cwd=cwd)


class MatPhang:
    """Mọi lệnh ra ngoài (docker, psql, HTTP) đi qua `chay` — test thay được."""

    def __init__(self, chay: Chay = _chay_nhi_phan, goc: Path = TRIEN_KHAI):
        self.chay = chay
        self.goc = goc
        self.thu_muc = goc / "cua_hang"

    # --- psql qua docker exec, SQL qua stdin ---
    def sql(self, csdl: str, lenh: str, *, mot_dong: bool = False) -> str:
        args = ["docker", "exec", "-i", PG, "psql", "-U", PG_QUAN_TRI, "-d", csdl,
                "-v", "ON_ERROR_STOP=1", "-X", "-q"]
        if mot_dong:
            args += ["-At"]
        kq = self.chay(args, dau_vao=lenh)
        if kq.returncode != 0:
            # stderr của psql có thể nhắc lại câu lệnh — che mật khẩu trước khi in.
            loi = re.sub(r"PASSWORD '[^']*'", "PASSWORD '***'", kq.stderr or "")
            raise LoiCuaHang(f"psql ({csdl}) hỏng: {loi.strip()[:400]}")
        return kq.stdout

    def docker(self, *args: str, cwd: Path | None = None) -> str:
        kq = self.chay(["docker", *args], cwd=cwd)
        if kq.returncode != 0:
            raise LoiCuaHang(f"docker {' '.join(args[:3])} hỏng: {(kq.stderr or '').strip()[:400]}")
        return kq.stdout

    def danh_sach(self) -> list[dict]:
        self.sql(CSDL_DIEU_KHIEN, SQL_DIEU_KHIEN)
        ra = self.sql(CSDL_DIEU_KHIEN,
                      "SELECT coalesce(json_agg(c ORDER BY ma), '[]') FROM cua_hang c "
                      "WHERE trang_thai <> 'da_xoa';", mot_dong=True)
        return json.loads(ra.strip() or "[]")

    def _ghi_caddy(self) -> None:
        email = ""
        if (self.goc / ".env.nen").exists():
            m = re.search(r"^TLS_EMAIL=(.*)$",
                          (self.goc / ".env.nen").read_text(encoding="utf-8"), re.M)
            email = m.group(1).strip() if m else ""
        ds = [(c["ma"], c["ten_mien"]) for c in self.danh_sach() if c["trang_thai"] == "chay"]
        tep = self.goc / "caddy" / "Caddyfile"
        tep.parent.mkdir(parents=True, exist_ok=True)
        tep.write_text(sinh_caddy(ds, email), encoding="utf-8", newline="\n")
        # Caddy đọc lại cấu hình KHÔNG làm rơi kết nối đang mở.
        self.docker("exec", "cskh-caddy", "caddy", "reload", "--config", "/etc/caddy/Caddyfile")

    # --- lệnh ---
    def tao(self, ma: str, ten: str, ten_mien: str) -> Path:
        kiem_ma(ma)
        ten_mien = kiem_ten_mien(ten_mien)
        if any(c["ma"] == ma or c["ten_mien"] == ten_mien for c in self.danh_sach()):
            raise LoiCuaHang(f"Mã {ma} hoặc tên miền {ten_mien} đã có cửa hàng dùng.")
        bi_mat = sinh_bi_mat()
        for csdl, lenh in sql_tao_csdl(ma, bi_mat["MAT_KHAU_DB"]):
            self.sql(csdl, lenh)

        noi = self.thu_muc / ma
        noi.mkdir(parents=True, exist_ok=False)
        for ten_tep, noi_dung in sinh_tep(ma, ten_mien, bi_mat).items():
            (noi / ten_tep).write_text(noi_dung, encoding="utf-8", newline="\n")
        _chi_chu_doc(noi / ".env")

        self.sql(CSDL_DIEU_KHIEN,
                 f"INSERT INTO cua_hang (ma, ten, ten_mien) VALUES "
                 f"({_q(ma)}, {_q(ten)}, {_q(ten_mien)});")
        self.docker("compose", "-p", f"cskh-{ma}", "up", "-d", cwd=noi)
        self._cho_khoe(ma)

        mat_khau = secrets.token_urlsafe(16)
        kq = self.chay(["docker", "exec", "-i", f"cskh-{ma}-app", "python", "-m",
                        "scripts.tao_tai_khoan", "quantri", "-", "--quan-tri"],
                       dau_vao=mat_khau + "\n")
        if kq.returncode != 0:
            raise LoiCuaHang(f"tạo quản trị viên hỏng: {(kq.stderr or '').strip()[:300]}")
        tep_mk = noi / "quan_tri_lan_dau.txt"
        tep_mk.write_text(f"Đăng nhập https://{ten_mien} — tài khoản: quantri\n"
                          f"Mật khẩu: {mat_khau}\nĐổi mật khẩu ngay lần đầu đăng nhập.\n",
                          encoding="utf-8")
        _chi_chu_doc(tep_mk)
        self._ghi_caddy()
        return tep_mk

    def _cho_khoe(self, ma: str, giay: int = 120) -> None:
        """Chờ container app báo healthy — migration chạy lần đầu mất vài giây."""
        het = time.monotonic() + giay
        while time.monotonic() < het:
            ra = self.docker("inspect", "-f", "{{.State.Health.Status}}", f"cskh-{ma}-app").strip()
            if ra == "healthy":
                return
            if ra == "unhealthy":
                break
            time.sleep(3)
        raise LoiCuaHang(f"cskh-{ma}-app không lên — xem: docker logs cskh-{ma}-app")

    def kiem(self) -> list[tuple[str, bool, str]]:
        ra = []
        for c in self.danh_sach():
            if c["trang_thai"] != "chay":
                continue
            try:
                trang = self.docker("inspect", "-f", "{{.State.Health.Status}}",
                                    f"cskh-{c['ma']}-app").strip()
            except LoiCuaHang as exc:
                trang = f"không có container ({exc})"
            ra.append((c["ma"], trang == "healthy", trang))
        return ra

    def doi_trang_thai(self, ma: str, lenh: str) -> None:
        kiem_ma(ma)
        noi = self.thu_muc / ma
        if lenh == "tam_dung":
            self.docker("compose", "-p", f"cskh-{ma}", "stop", cwd=noi)
            moi = "tam_dung"
        elif lenh == "chay":
            self.docker("compose", "-p", f"cskh-{ma}", "up", "-d", cwd=noi)
            moi = "chay"
        else:
            self.docker("compose", "-p", f"cskh-{ma}", "restart", cwd=noi)
            return
        self.sql(CSDL_DIEU_KHIEN, f"UPDATE cua_hang SET trang_thai = {_q(moi)}, "
                                  f"cap_nhat_luc = now() WHERE ma = {_q(ma)};")
        self._ghi_caddy()

    def sao_luu(self, ma: str) -> Path:
        kiem_ma(ma)
        dich = self.goc / "sao_luu" / ma
        dich.mkdir(parents=True, exist_ok=True)
        tep = dich / f"ch_{ma}-{time.strftime('%Y%m%d-%H%M%S')}.dump"
        kq = self.chay(["docker", "exec", PG, "pg_dump", "-U", PG_QUAN_TRI, "-Fc", f"ch_{ma}"],
                       nhi_phan=True)
        if kq.returncode != 0 or not kq.stdout:
            raise LoiCuaHang(f"pg_dump ch_{ma} hỏng hoặc rỗng — KHÔNG có bản sao lưu.")
        tep.write_bytes(kq.stdout)
        return tep

    def xoa(self, ma: str, xac_nhan: str) -> Path:
        kiem_ma(ma)
        if xac_nhan != ma:
            raise LoiCuaHang("Gõ lại đúng mã cửa hàng ở --xac-nhan để xoá.")
        ban = self.sao_luu(ma)          # sao lưu hỏng thì nổ ở đây, chưa xoá gì
        noi = self.thu_muc / ma
        self.docker("compose", "-p", f"cskh-{ma}", "down", "-v", cwd=noi)
        self.sql("postgres", f"DROP DATABASE IF EXISTS ch_{ma} WITH (FORCE);")
        self.sql("postgres", f"DROP ROLE IF EXISTS ch_{ma};")
        self.sql(CSDL_DIEU_KHIEN, f"UPDATE cua_hang SET trang_thai = 'da_xoa', "
                                  f"cap_nhat_luc = now() WHERE ma = {_q(ma)};")
        for tep in noi.glob("*"):
            tep.unlink()
        noi.rmdir()
        self._ghi_caddy()
        return ban


def _chi_chu_doc(tep: Path) -> None:
    try:
        os.chmod(tep, 0o600)
    except OSError:
        pass                    # Windows: quyền theo ACL, không theo chmod


def khoi_tao(goc: Path = TRIEN_KHAI, email: str = "") -> list[str]:
    """Sinh .env.nen (mật khẩu superuser Postgres) và Caddyfile rỗng nếu chưa có."""
    viec = []
    env = goc / ".env.nen"
    if not env.exists():
        env.write_text(f"POSTGRES_MAT_KHAU={secrets.token_urlsafe(32)}\nTLS_EMAIL={email}\n",
                       encoding="utf-8", newline="\n")
        _chi_chu_doc(env)
        viec.append(f"đã sinh {env.relative_to(goc.parent)}")
    caddy = goc / "caddy" / "Caddyfile"
    if not caddy.exists():
        caddy.parent.mkdir(parents=True, exist_ok=True)
        caddy.write_text(sinh_caddy([], email), encoding="utf-8", newline="\n")
        viec.append(f"đã sinh {caddy.relative_to(goc.parent)}")
    return viec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m scripts.cua_hang")
    sub = ap.add_subparsers(dest="lenh", required=True)
    k = sub.add_parser("khoi_tao")
    k.add_argument("--email-tls", default="")
    t = sub.add_parser("tao")
    t.add_argument("ma")
    t.add_argument("--ten", required=True)
    t.add_argument("--ten-mien", required=True)
    sub.add_parser("liet_ke")
    sub.add_parser("kiem")
    for ten in ("tam_dung", "chay", "khoi_dong_lai"):
        sub.add_parser(ten).add_argument("ma")
    s = sub.add_parser("sao_luu")
    s.add_argument("ma", nargs="?")
    s.add_argument("--tat-ca", action="store_true")
    x = sub.add_parser("xoa")
    x.add_argument("ma")
    x.add_argument("--xac-nhan", required=True)
    ts = ap.parse_args(argv)

    mp = MatPhang(chay=_chay_nhi_phan)
    try:
        if ts.lenh == "khoi_tao":
            for v in khoi_tao(email=ts.email_tls) or ["đã có sẵn, không đổi gì"]:
                print(v)
            print("Tiếp: docker compose -f trien_khai/docker-compose.nen.yml "
                  "--env-file trien_khai/.env.nen up -d")
        elif ts.lenh == "tao":
            tep = mp.tao(ts.ma, ts.ten, ts.ten_mien)
            print(f"Đã dựng cửa hàng {ts.ma}. Thông tin đăng nhập đầu tiên: {tep} "
                  "(không in ra đây).")
            print("Nhớ trỏ DNS tên miền về máy này, rồi khai URL webhook Meta/Zalo theo tên miền ấy.")
        elif ts.lenh == "liet_ke":
            for c in mp.danh_sach():
                print(f"{c['ma']:20} {c['trang_thai']:9} {c['goi']:10} {c['ten_mien']}  — {c['ten']}")
        elif ts.lenh == "kiem":
            hong = 0
            for ma, ok, trang in mp.kiem():
                print(f"{'ỔN ' if ok else 'HỎNG'} {ma:20} {trang}")
                hong += not ok
            return 1 if hong else 0
        elif ts.lenh in ("tam_dung", "chay", "khoi_dong_lai"):
            mp.doi_trang_thai(ts.ma, ts.lenh)
            print(f"{ts.lenh}: {ts.ma} xong")
        elif ts.lenh == "sao_luu":
            ds = [c["ma"] for c in mp.danh_sach()] if ts.tat_ca else [ts.ma]
            if not ds or ds == [None]:
                raise LoiCuaHang("Chỉ rõ mã cửa hàng hoặc --tat-ca.")
            for ma in ds:
                print(f"{ma}: {mp.sao_luu(ma)}")
        elif ts.lenh == "xoa":
            print(f"Đã xoá {ts.ma}. Bản sao lưu cuối: {mp.xoa(ts.ma, ts.xac_nhan)}")
    except LoiCuaHang as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
