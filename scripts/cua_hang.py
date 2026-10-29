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

# Gói cước: (số kênh, số nhân viên đang hoạt động, hội thoại AI mỗi tháng).
# 0 = không giới hạn. App tự chặn khi vượt — agent/goi_cuoc.py.
GOI: dict[str, tuple[int, int, int]] = {
    "dung_thu": (2, 3, 200),
    "co_ban": (3, 5, 1500),
    "chuyen_nghiep": (10, 20, 8000),
    "khong_gioi_han": (0, 0, 0),
}

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


UID_APP = 10001       # người dùng `cskh` trong Dockerfile


def doc_khoa_gcp(tep: Path) -> dict[str, str]:
    """
    Kiểm tệp khoá service account của Google Cloud (Vertex AI). Trả
    project_id và client_email — KHÔNG BAO GIỜ trả hay in private_key.

    Kiểm ngay lúc tạo cửa hàng chứ không để app tự phát hiện: khoá sai thì
    app vẫn lên khoẻ, healthz xanh, và agent chuyển người MỌI tin vì không
    gọi được mô hình — hỏng im lặng.
    """
    try:
        d = json.loads(Path(tep).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LoiCuaHang(f"không đọc được tệp khoá GCP ({type(exc).__name__})") from None
    if d.get("type") != "service_account":
        raise LoiCuaHang("tệp khoá GCP phải là khoá SERVICE ACCOUNT (type=service_account), "
                         "không phải OAuth client hay thông tin gcloud của người dùng.")
    thieu = [k for k in ("project_id", "client_email", "private_key") if not d.get(k)]
    if thieu:
        raise LoiCuaHang(f"tệp khoá GCP thiếu {', '.join(thieu)}")
    return {"project_id": str(d["project_id"]), "client_email": str(d["client_email"])}


def khoi_mo_hinh(gcp: dict[str, str] | None) -> tuple[str, str]:
    """(khối .env cho mô hình, dòng mount khoá vào compose)."""
    if not gcp:
        return ("# --- Mô hình: cửa hàng tự nhập khoá ở dashboard (Cấu hình → Model) ---\n"
                "LLM_PROVIDER=gemini_api\nGEMINI_API_KEY=", "")
    return ("# --- Mô hình: Vertex AI qua service account (tệp gcp.json cạnh .env, chỉ đọc) ---\n"
            f"# Tài khoản: {gcp['client_email']}\n"
            "LLM_PROVIDER=gemini\n"
            f"GCP_PROJECT_ID={gcp['project_id']}\n"
            "GCP_REGION=global\n"
            "GEMINI_REGION=us-central1\n"
            "GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp.json",
            "      - ./gcp.json:/run/secrets/gcp.json:ro\n")


def sinh_tep(ma: str, ten_mien: str, bi_mat: dict[str, str], *,
             image_app: str = IMAGE_APP, image_sidecar: str = IMAGE_SIDECAR,
             gcp: dict[str, str] | None = None) -> dict[str, str]:
    k, nv, ai = GOI["dung_thu"]
    mo_hinh, gcp_mount = khoi_mo_hinh(gcp)
    gia_tri = {"MA": ma, "TEN_MIEN": ten_mien, "IMAGE_APP": image_app,
               "IMAGE_SIDECAR": image_sidecar, "GIOI_HAN_KENH": str(k),
               "GIOI_HAN_NHAN_VIEN": str(nv), "GIOI_HAN_AI": str(ai),
               "MO_HINH": mo_hinh, "GCP_MOUNT": gcp_mount, **bi_mat}
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


def sinh_caddy_erp(ten_mien: str) -> str:
    """ERPNext qua Caddy: TLS, header bảo mật; nhận tệp tới 50 MB như nginx của ERPNext."""
    return f"""{kiem_ten_mien(ten_mien)} {{
\tencode gzip
\trequest_body {{
\t\tmax_size 50MB
\t}}
\theader {{
\t\tStrict-Transport-Security "max-age=31536000"
\t\tX-Content-Type-Options nosniff
\t\t-Server
\t}}
\treverse_proxy cskh-erp-frontend:8080
}}
"""


def gop_env(env: str, them: dict[str, str]) -> str:
    """
    Gộp giá trị mang từ máy cũ vào .env vừa sinh: khoá đã có thì thay giá
    trị TẠI CHỖ, khoá chưa có thì thêm vào một khối riêng ở cuối — để người
    đọc .env thấy ngay dòng nào đến từ máy cũ.
    """
    dong = env.splitlines()
    con = dict(them)
    for i, d in enumerate(dong):
        m = re.match(r"^([A-Z][A-Z0-9_]*)=", d)
        if m and m.group(1) in con:
            dong[i] = f"{m.group(1)}={con.pop(m.group(1))}"
    if con:
        dong += ["", "# --- Mang từ máy cũ (scripts.chuyen_nha) ---"]
        dong += [f"{k}={v}" for k, v in sorted(con.items())]
    return "\n".join(dong) + "\n"


# Khi có --gcp-khoa, các khoá này lấy từ tệp khoá/mẫu, KHÔNG từ máy cũ:
# project_id của khoá mới là sự thật, giá trị cũ có thể là dự án khác.
_KHOA_MO_HINH = ("LLM_PROVIDER", "GCP_PROJECT_ID", "GCP_REGION", "GEMINI_REGION")

# Diễn tập trên một máy có cửa hàng THẬT đang chạy: không vòng nền nào (không
# outbox gửi tin, không giữ phiên Zalo — hai sidecar một phiên là Zalo đá
# văng bản thật), không báo động ra ngoài.
_DIEN_TAP = {"VAI_TRO_TIEN_TRINH": "api", "CANH_GAC_WEBHOOK": "", "CANH_GAC_BAT": "false",
             "BAO_NHAN_VIEN_WEBHOOK": "", "BAO_NHAN_VIEN_CHUYEN_NGUOI": "false"}


def cau_hinh_nhap(cau_hinh: dict[str, str], *, co_gcp: bool, co_erp_vps: bool,
                  dien_tap: bool) -> dict[str, str]:
    """Phần thuần của `nhap`: từ cấu hình máy cũ ra giá trị ghi vào .env mới."""
    ra = dict(cau_hinh)
    provider = ra.get("LLM_PROVIDER", "gemini_api").strip().lower()
    if co_gcp:
        for k in _KHOA_MO_HINH:
            ra.pop(k, None)
    elif provider in ("gemini", "vertex"):
        raise LoiCuaHang(f"máy cũ dùng LLM_PROVIDER={provider} (Vertex AI qua gcloud) — trên VPS "
                         "cần tệp khoá service account: thêm --gcp-khoa <tệp.json>")
    if ra.get("ERP_LOAI", "tep").strip().lower() == "erpnext":
        if not co_erp_vps:
            raise LoiCuaHang("máy cũ dùng ERPNext nhưng VPS chưa có: chạy `cua_hang erp khoi_tao` "
                             "+ `erp chay` trước, hoặc thêm --khong-erp để chuyển sang danh mục tệp")
        ra["ERPNEXT_URL"] = ERP_URL_NOI_BO
    if dien_tap:
        ra.update(_DIEN_TAP)
    return ra


def dat_goi_env(env: str, goi: str) -> str:
    """Thay (hoặc thêm) các dòng gói cước trong nội dung .env — giữ nguyên phần còn lại."""
    if goi not in GOI:
        raise LoiCuaHang(f"Không có gói {goi!r}. Có: {', '.join(GOI)}")
    k, nv, ai = GOI[goi]
    moi = {"GOI_CUOC": goi, "GIOI_HAN_KENH": str(k), "GIOI_HAN_NHAN_VIEN": str(nv),
           "GIOI_HAN_HOI_THOAI_AI_THANG": str(ai)}
    dong = env.splitlines()
    for khoa, gia_tri in moi.items():
        vi_tri = [i for i, d in enumerate(dong) if d.startswith(f"{khoa}=")]
        if vi_tri:
            dong[vi_tri[0]] = f"{khoa}={gia_tri}"
        else:
            dong.append(f"{khoa}={gia_tri}")
    return "\n".join(dong) + "\n"


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
        # Postgres mặc định cho PUBLIC quyền CONNECT vào MỌI CSDL. Đo được
        # 23.10.2026: role cửa hàng mới kết nối được vào CSDL khác (không đọc
        # được bảng — nhưng một lớp phòng thủ thiếu là một lớp). Thu ở CSDL hệ
        # thống mỗi lần tạo: chạy lại vô hại, và không phụ thuộc ai nhớ làm.
        ("postgres", f"REVOKE CONNECT ON DATABASE postgres, {CSDL_DIEU_KHIEN} FROM PUBLIC;"),
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
        # dau_vao dạng bytes: đẩy bản sao lưu vào pg_restore qua stdin.
        return subprocess.run(lenh, cwd=cwd, input=dau_vao, capture_output=True, check=False)
    return _chay_that(lenh, dau_vao=dau_vao, cwd=cwd)


def _bay_gio() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
        noi_dung = sinh_caddy(ds, email)
        env_erp = self.goc / "erp" / ".env.erp"
        if env_erp.exists():
            m = re.search(r"^ERP_TEN_MIEN=(.+)$", env_erp.read_text(encoding="utf-8"), re.M)
            if m and m.group(1).strip():
                noi_dung += "\n" + sinh_caddy_erp(m.group(1).strip())
        tep.write_text(noi_dung, encoding="utf-8", newline="\n")
        # Caddy đọc lại cấu hình KHÔNG làm rơi kết nối đang mở.
        self.docker("exec", "cskh-caddy", "caddy", "reload", "--config", "/etc/caddy/Caddyfile")

    # --- lệnh ---
    def _chuan_bi(self, ma: str, ten_mien: str, gcp_khoa: Path | None,
                  them_env: dict[str, str] | None = None) -> Path:
        """CSDL + role + thư mục cấu hình của một cửa hàng MỚI. Chưa bật container."""
        kiem_ma(ma)
        if any(c["ma"] == ma or c["ten_mien"] == ten_mien for c in self.danh_sach()):
            raise LoiCuaHang(f"Mã {ma} hoặc tên miền {ten_mien} đã có cửa hàng dùng.")
        gcp = doc_khoa_gcp(gcp_khoa) if gcp_khoa else None
        bi_mat = sinh_bi_mat()
        for csdl, lenh in sql_tao_csdl(ma, bi_mat["MAT_KHAU_DB"]):
            self.sql(csdl, lenh)

        noi = self.thu_muc / ma
        noi.mkdir(parents=True, exist_ok=False)
        for ten_tep, noi_dung in sinh_tep(ma, ten_mien, bi_mat, gcp=gcp).items():
            if ten_tep == ".env" and them_env:
                noi_dung = gop_env(noi_dung, them_env)
            (noi / ten_tep).write_text(noi_dung, encoding="utf-8", newline="\n")
        _chi_chu_doc(noi / ".env")
        if gcp_khoa:
            dich = noi / "gcp.json"
            dich.write_bytes(Path(gcp_khoa).read_bytes())
            _chi_chu_doc(dich)
            # Container chạy bằng uid 10001: tệp 0600 của root thì app không đọc
            # được khoá, Vertex báo lỗi xác thực, agent chuyển người MỌI tin.
            try:
                os.chown(dich, UID_APP, UID_APP)
            except (AttributeError, PermissionError, OSError):
                pass
        return noi

    def _dang_ky(self, ma: str, ten: str, ten_mien: str) -> None:
        """
        Ghi cửa hàng vào bảng điều khiển. Dòng `da_xoa` cũ cùng mã/tên miền
        được dọn trước: `xoa` giữ lại dòng ấy làm dấu vết, nên không dọn thì
        mã của một cửa hàng đã xoá không bao giờ dùng lại được (đo 24.10.2026).
        """
        self.sql(CSDL_DIEU_KHIEN,
                 f"DELETE FROM cua_hang WHERE trang_thai = 'da_xoa' AND "
                 f"(ma = {_q(ma)} OR ten_mien = {_q(ten_mien)}); "
                 f"INSERT INTO cua_hang (ma, ten, ten_mien) VALUES "
                 f"({_q(ma)}, {_q(ten)}, {_q(ten_mien)});")

    def tao(self, ma: str, ten: str, ten_mien: str, gcp_khoa: Path | None = None) -> Path:
        ten_mien = kiem_ten_mien(ten_mien)
        noi = self._chuan_bi(ma, ten_mien, gcp_khoa)

        self._dang_ky(ma, ten, ten_mien)
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

    def nhap(self, ma: str, ten: str, ten_mien: str, goi: Path, mat_khau: str, *,
             gcp_khoa: Path | None = None, khong_erp: bool = False,
             dien_tap: bool = False) -> dict:
        """
        Dựng cửa hàng TỪ GÓI CHUYỂN NHÀ của máy cũ (scripts/chuyen_nha.py):
        CSDL, tệp dữ liệu, cấu hình, khoá kho bí mật, và ERPNext nếu có.

        Không tạo quản trị viên: tài khoản cũ đi theo CSDL. Cuối cùng so số
        tin nhắn với manifest — "khôi phục xong" mà thiếu dữ liệu là thứ
        chỉ lộ ra khi khách hỏi lại chuyện tuần trước.
        """
        import tempfile

        from scripts import chuyen_nha

        ten_mien = kiem_ten_mien(ten_mien)
        kiem_ma(ma)
        if any(c["ma"] == ma or c["ten_mien"] == ten_mien for c in self.danh_sach()):
            raise LoiCuaHang(f"Mã {ma} hoặc tên miền {ten_mien} đã có cửa hàng dùng.")
        if gcp_khoa:
            doc_khoa_gcp(gcp_khoa)          # khoá sai thì dừng NGAY, trước mọi bước chậm
        erp = ERP(self)
        with tempfile.TemporaryDirectory() as t:
            tam = Path(t)
            manifest = chuyen_nha.mo_goi(Path(goi), mat_khau, tam)
            cau_hinh = json.loads((tam / "cau_hinh.json").read_text(encoding="utf-8"))
            if khong_erp:
                cau_hinh["ERP_LOAI"] = "tep"
            them = cau_hinh_nhap(cau_hinh, co_gcp=bool(gcp_khoa),
                                 co_erp_vps=erp.env.exists(), dien_tap=dien_tap)
            # ERP TRƯỚC cửa hàng: hỏng ở đây thì chưa có gì của cửa hàng để dọn.
            if manifest.get("erp") and not khong_erp:
                erp.nhap(tam / "erp")
            noi = self._chuan_bi(ma, ten_mien, gcp_khoa, them_env=them)
            try:
                return self._nhap_csdl_va_bat(ma, ten, ten_mien, noi, tam, manifest, dien_tap)
            except BaseException:
                # Nhập dở là tệ hơn không nhập: CSDL nửa vời, mã cửa hàng bị
                # chiếm, lần thử lại báo "đã có". Dọn sạch rồi mới ném tiếp.
                self._don_nhap_do(ma)
                raise

    def _don_nhap_do(self, ma: str) -> None:
        noi = self.thu_muc / ma
        if noi.exists():
            self.chay(["docker", "compose", "-p", f"cskh-{ma}", "down", "-v"], cwd=noi)
            for tep in noi.glob("*"):
                tep.unlink()
            noi.rmdir()
        for csdl, lenh in (("postgres", f"DROP DATABASE IF EXISTS ch_{ma} WITH (FORCE);"),
                           ("postgres", f"DROP ROLE IF EXISTS ch_{ma};"),
                           (CSDL_DIEU_KHIEN, f"DELETE FROM cua_hang WHERE ma = {_q(ma)};")):
            try:
                self.sql(csdl, lenh)
            except LoiCuaHang:
                pass

    def _nhap_csdl_va_bat(self, ma: str, ten: str, ten_mien: str, noi: Path, tam: Path,
                          manifest: dict, dien_tap: bool) -> dict:
        kq = self.chay(["docker", "exec", "-i", PG, "pg_restore", "-U", PG_QUAN_TRI,
                        "-d", f"ch_{ma}", "--no-owner", f"--role=ch_{ma}", "--no-comments",
                        "--exit-on-error"],
                       dau_vao=(tam / "csdl.dump").read_bytes(), nhi_phan=True)
        if kq.returncode != 0:
            loi = (kq.stderr or b"").decode("utf-8", "replace").strip()[:500]
            raise LoiCuaHang(f"khôi phục CSDL hỏng: {loi}")
        so_tin = int(self.sql(f"ch_{ma}", "SELECT count(*) FROM messages;",
                              mot_dong=True).strip() or 0)
        if so_tin != manifest["so_tin"]:
            raise LoiCuaHang(f"CSDL khôi phục có {so_tin} tin, gói ghi {manifest['so_tin']} — "
                             "thiếu dữ liệu, KHÔNG bật cửa hàng.")

        self._dang_ky(ma, ten, ten_mien)
        # Tạo container + volume nhưng CHƯA chạy: tệp dữ liệu phải nằm sẵn
        # trong volume trước lần khởi động đầu, không thì app nạp danh mục
        # mẫu và ghi đè dấu "đã nạp" của tri thức.
        self.docker("compose", "-p", f"cskh-{ma}", "up", "--no-start", cwd=noi)
        m = re.search(r"^\s*image:\s*(\S+)", (noi / "compose.yml").read_text(encoding="utf-8"),
                      re.M)
        if m is None:
            raise LoiCuaHang("compose.yml của cửa hàng không có dòng image")
        kq = self.chay(["docker", "run", "--rm", "-i", "--user", str(UID_APP), "-v",
                        f"cskh-{ma}-du-lieu:/app/data", "--entrypoint", "tar", m.group(1),
                        "-xf", "-", "-C", "/app/data"],
                       dau_vao=(tam / "du_lieu.tar").read_bytes(), nhi_phan=True)
        if kq.returncode != 0:
            raise LoiCuaHang("chép tệp dữ liệu vào volume hỏng: "
                             + (kq.stderr or b"").decode("utf-8", "replace")[:300])
        self.docker("compose", "-p", f"cskh-{ma}", "up", "-d", cwd=noi)
        self._cho_khoe(ma, giay=300)
        self._ghi_caddy()
        return {**manifest, "so_tin_da_nhap": so_tin, "dien_tap": dien_tap}

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

    def doi_goi(self, ma: str, goi: str) -> None:
        kiem_ma(ma)
        tep = self.thu_muc / ma / ".env"
        tep.write_text(dat_goi_env(tep.read_text(encoding="utf-8"), goi),
                       encoding="utf-8", newline="\n")
        self.sql(CSDL_DIEU_KHIEN, f"UPDATE cua_hang SET goi = {_q(goi)}, "
                                  f"cap_nhat_luc = now() WHERE ma = {_q(ma)};")
        # Hạn mức đọc từ .env lúc khởi động — phải dựng lại container để áp.
        self.docker("compose", "-p", f"cskh-{ma}", "up", "-d", "--force-recreate", "app",
                    cwd=self.thu_muc / ma)

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
        # Dấu mốc cho `san_sang` trong container — CHỈ ghi khi thành công, nên
        # lịch sao lưu ngừng thì dấu mốc cũ dần và mục Sao lưu tự đỏ.
        self._ghi_dau_moc(ma, ".sao_luu_ngoai",
                          {"luc": _bay_gio(), "tep": tep.name, "byte": len(kq.stdout)})
        return tep

    def _ghi_dau_moc(self, ma: str, ten: str, noi_dung: dict) -> bool:
        """Ghi một tệp JSON nhỏ vào volume dữ liệu của cửa hàng (qua container app)."""
        kq = self.chay(["docker", "exec", "-i", f"cskh-{ma}-app", "sh", "-c",
                        f"cat > /app/data/{ten}"], dau_vao=json.dumps(noi_dung))
        return kq.returncode == 0

    def thu_phuc_hoi(self, ma: str) -> dict:
        """
        Phục hồi bản sao lưu MỚI NHẤT vào một CSDL tạm, đếm bảng, so với CSDL
        thật, rồi xoá CSDL tạm. Không đụng CSDL đang chạy.

        Bản sao lưu chưa từng phục hồi thử thì chưa phải bản sao lưu: tệp có
        thể rỗng một nửa, thiếu extension, hay hỏng định dạng — và chỉ biết
        vào đúng ngày cần nó.
        """
        kiem_ma(ma)
        ds = sorted((self.goc / "sao_luu" / ma).glob(f"ch_{ma}-*.dump"))
        if not ds:
            raise LoiCuaHang(f"chưa có bản sao lưu nào của {ma} — chạy sao_luu {ma} trước.")
        tep = ds[-1]
        tam = f"thu_{ma}_{time.strftime('%Y%m%d%H%M%S')}"
        self.sql("postgres", f"CREATE DATABASE {tam};")
        try:
            self.sql(tam, 'CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS '
                          'unaccent; CREATE EXTENSION IF NOT EXISTS pg_trgm; CREATE EXTENSION IF '
                          'NOT EXISTS "uuid-ossp"; CREATE EXTENSION IF NOT EXISTS pgcrypto;')
            kq = self.chay(["docker", "exec", "-i", PG, "pg_restore", "-U", PG_QUAN_TRI,
                            "-d", tam, "--no-owner", "--exit-on-error"],
                           dau_vao=tep.read_bytes(), nhi_phan=True)
            if kq.returncode != 0:
                loi = (kq.stderr or b"").decode("utf-8", "replace").strip()[:400]
                raise LoiCuaHang(f"phục hồi {tep.name} HỎNG: {loi}")
            dem = ("SELECT count(*) FROM information_schema.tables "
                   "WHERE table_schema = 'public';")
            so_bang = int(self.sql(tam, dem, mot_dong=True).strip() or 0)
            so_that = int(self.sql(f"ch_{ma}", dem, mot_dong=True).strip() or 0)
            so_tin = int(self.sql(tam, "SELECT count(*) FROM messages;", mot_dong=True).strip() or 0)
            if so_bang == 0 or so_bang < so_that:
                raise LoiCuaHang(f"bản phục hồi có {so_bang} bảng, CSDL thật có {so_that} — thiếu.")
        finally:
            self.sql("postgres", f"DROP DATABASE IF EXISTS {tam} WITH (FORCE);")
        kq_moc = {"luc": _bay_gio(), "tep": tep.name, "so_bang": so_bang, "so_tin": so_tin}
        self._ghi_dau_moc(ma, ".thu_phuc_hoi", kq_moc)
        return kq_moc

    def sua_hong(self) -> list[tuple[str, str]]:
        """
        Người canh trên VPS (cron 5 phút): container app/sidecar nào không
        chạy hoặc `unhealthy` thì khởi động lại; MỌI lượt ghi nhịp đập vào
        volume để `san_sang` biết người canh còn sống.

        `restart: unless-stopped` chỉ lo container THOÁT. Container còn sống
        mà treo (healthcheck đỏ) thì Docker không tự khởi động lại — đúng
        kiểu chết mà vẫn "Up".
        """
        viec: list[tuple[str, str]] = []
        for c in self.danh_sach():
            if c["trang_thai"] != "chay":
                continue
            ma = c["ma"]
            for vai in ("app", "sidecar"):
                ten = f"cskh-{ma}-{vai}"
                kq = self.chay(["docker", "inspect", "-f",
                                "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}",
                                ten])
                trang = (kq.stdout or "").strip() if kq.returncode == 0 else "không có"
                if trang.startswith("running") and "unhealthy" not in trang:
                    continue
                r = self.chay(["docker", "start" if not trang.startswith("running") else "restart",
                               ten])
                viec.append((ten, f"{trang or '?'} -> " + ("đã bật lại" if r.returncode == 0
                                                        else f"BẬT LẠI HỎNG: {(r.stderr or '')[:120]}")))
            self._ghi_dau_moc(ma, ".canh_gac_ngoai", {"luc": _bay_gio()})
        return viec

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


def duong_sao_luu_bench(ra: str) -> list[str]:
    """
    Đường dẫn tệp trong bản in của `bench backup`. Bench in TƯƠNG ĐỐI với
    thư mục sites (`./localhost/private/backups/...`) — bản đầu chỉ bắt
    đường tuyệt đối nên không thấy tệp nào (đo 24.10.2026, ERPNext 15.120).
    """
    ra_duong = []
    for d in re.findall(r"((?:\./|/home/frappe/)\S+?\.(?:sql\.gz|tar|json))(?=\s|$)", ra):
        if d.startswith("./"):
            d = "/home/frappe/frappe-bench/sites/" + d[2:]
        if d not in ra_duong:
            ra_duong.append(d)
    return ra_duong


ERP_COMPOSE = "docker-compose.erpnext.yml"
ERP_SITE = "localhost"
ERP_BACKEND = "cskh-erp-backend"
ERP_URL_NOI_BO = "http://cskh-erp-frontend:8080"


class ERP:
    """
    ERPNext DÙNG CHUNG trên VPS (`trien_khai/docker-compose.erpnext.yml`).

    Một site tên `localhost` — đúng tên site trên máy cũ, để bản sao lưu
    khôi phục nguyên vẹn (tên site nằm trong đường dẫn tệp và cấu hình).
    """

    def __init__(self, mp: MatPhang):
        self.mp = mp
        self.thu_muc = mp.goc / "erp"
        self.env = self.thu_muc / ".env.erp"

    def _env(self) -> dict[str, str]:
        if not self.env.exists():
            raise LoiCuaHang("chưa có trien_khai/erp/.env.erp — chạy: cua_hang erp khoi_tao")
        return dict(re.findall(r"^([A-Z_]+)=(.*)$", self.env.read_text(encoding="utf-8"), re.M))

    def khoi_tao(self, ten_mien: str = "") -> list[str]:
        if self.env.exists():
            return ["đã có trien_khai/erp/.env.erp, không đổi gì"]
        if ten_mien:
            ten_mien = kiem_ten_mien(ten_mien)
        self.thu_muc.mkdir(parents=True, exist_ok=True)
        self.env.write_text(f"ERP_DB_MAT_KHAU={secrets.token_urlsafe(24)}\n"
                            f"ERP_ADMIN_MAT_KHAU={secrets.token_urlsafe(16)}\n"
                            f"ERP_TEN_MIEN={ten_mien}\n", encoding="utf-8", newline="\n")
        _chi_chu_doc(self.env)
        return ["đã sinh trien_khai/erp/.env.erp (mật khẩu CSDL + Administrator ERPNext)"]

    def chay(self) -> None:
        self.mp.docker("compose", "-f", str(self.mp.goc / ERP_COMPOSE), "--env-file",
                       str(self.env), "up", "-d")

    def _bench(self, *args: str, dau_vao: bytes | None = None) -> str:
        kq = self.mp.chay(["docker", "exec", "-i", ERP_BACKEND, "bench", *args],
                          dau_vao=dau_vao, nhi_phan=True)
        ra = (kq.stdout or b"").decode("utf-8", "replace")
        if kq.returncode != 0:
            loi = (kq.stderr or b"").decode("utf-8", "replace") + ra
            # bench có thể nhắc lại mật khẩu trong thông báo — che trước khi in.
            for gt in self._env().values():
                if len(gt) >= 12:
                    loi = loi.replace(gt, "***")
            raise LoiCuaHang(f"bench {' '.join(args[:2])} hỏng: {loi.strip()[-400:]}")
        return ra

    def co_site(self) -> bool:
        kq = self.mp.chay(["docker", "exec", ERP_BACKEND, "test", "-f",
                           f"sites/{ERP_SITE}/site_config.json"])
        return kq.returncode == 0

    def tao_site(self) -> None:
        e = self._env()
        if self.co_site():
            return
        self._bench("new-site", ERP_SITE, "--mariadb-root-password", e["ERP_DB_MAT_KHAU"],
                    "--admin-password", e["ERP_ADMIN_MAT_KHAU"], "--install-app", "erpnext",
                    "--mariadb-user-host-login-scope", "%")
        self._sau_site(e)

    def _sau_site(self, e: dict[str, str]) -> None:
        if e.get("ERP_TEN_MIEN"):
            self._bench("--site", ERP_SITE, "set-config", "host_name", f"https://{e['ERP_TEN_MIEN']}")
        self._bench("--site", ERP_SITE, "enable-scheduler")

    def nhap(self, thu_muc_sao_luu: Path) -> dict:
        """
        Khôi phục bản `bench backup --with-files` của máy cũ vào site mới.

        Ba thứ dễ quên, mỗi thứ là một kiểu hỏng im lặng:
          · khoá mã hoá (`encryption_key` trong site_config_backup.json):
            thiếu nó thì mật khẩu/API secret lưu trong ERPNext giải mã ra
            rác — khoá API của agent "đúng" mà ERPNext từ chối;
          · tệp đính kèm (public + private): thiếu thì ảnh sản phẩm, chứng
            từ đính kèm trả 404;
          · mật khẩu Administrator: bản sao lưu mang mật khẩu của máy cũ
            (có thể là `admin`) — đặt lại ngay.
        """
        e = self._env()
        tep = {p.name: p for p in thu_muc_sao_luu.glob("*")}
        db = next((p for n, p in tep.items() if n.endswith("-database.sql.gz")), None)
        if db is None:
            raise LoiCuaHang(f"{thu_muc_sao_luu} không có *-database.sql.gz")
        cfg = next((p for n, p in tep.items() if n.endswith("site_config_backup.json")), None)
        khoa = json.loads(cfg.read_text(encoding="utf-8")).get("encryption_key") if cfg else None
        if not khoa:
            raise LoiCuaHang("bản sao lưu ERP thiếu site_config_backup.json/encryption_key — "
                             "khôi phục không có khoá thì mọi API secret trong ERPNext thành rác")
        if not self.co_site():
            self.tao_site()
        # NGOÀI thư mục site: `restore` dọn private/backups của site giữa chừng,
        # tệp đặt ở đó biến mất trước bước giải nén tệp đính kèm ("Invalid
        # path" — đo 24.10.2026).
        dich = "/home/frappe/frappe-bench/nhap_erp"
        self.mp.chay(["docker", "exec", ERP_BACKEND, "mkdir", "-p", dich])
        for p in tep.values():
            self.mp.chay(["docker", "exec", "-i", ERP_BACKEND, "sh", "-c", f"cat > {dich}/{p.name}"],
                         dau_vao=p.read_bytes(), nhi_phan=True)
        # KHÔNG truyền --encryption-key cho `restore`: tham số ấy là khoá của
        # bản sao lưu ĐÃ MÃ HOÁ, không phải khoá của site. Truyền vào là
        # frappe đem tệp tar thường đi "giải mã" rồi báo "Invalid path"
        # (đo 24.10.2026). Khoá site đặt ngay sau bằng set-config.
        args = ["--site", ERP_SITE, "restore", "--force", f"{dich}/{db.name}",
                "--mariadb-root-password", e["ERP_DB_MAT_KHAU"]]
        for duoi, co in (("-files.tar", "--with-public-files"),
                         ("-private-files.tar", "--with-private-files")):
            p = next((p for n, p in tep.items() if n.endswith(duoi)), None)
            if p is not None:
                args += [co, f"{dich}/{p.name}"]
        self._bench(*args)
        self._bench("--site", ERP_SITE, "set-config", "encryption_key", khoa)
        self._bench("--site", ERP_SITE, "migrate")
        self._bench("--site", ERP_SITE, "set-admin-password", e["ERP_ADMIN_MAT_KHAU"])
        self._sau_site(e)
        self.mp.chay(["docker", "exec", ERP_BACKEND, "rm", "-rf", dich])
        return {"tep": sorted(tep)}

    def ping(self) -> bool:
        kq = self.mp.chay(["docker", "exec", ERP_BACKEND, "curl", "-s", "-m", "8",
                           "http://frontend:8080/api/method/ping"])
        return kq.returncode == 0 and "pong" in (kq.stdout or "")

    def sao_luu(self) -> Path:
        ra = self._bench("--site", ERP_SITE, "backup", "--with-files")
        duong = duong_sao_luu_bench(ra)
        if not any(d.endswith("-database.sql.gz") for d in duong):
            raise LoiCuaHang("bench backup không báo tệp CSDL nào — KHÔNG có bản sao lưu ERP")
        dich = self.thu_muc / "sao_luu" / time.strftime("%Y%m%d-%H%M%S")
        dich.mkdir(parents=True)
        for d in duong:
            kq = self.mp.chay(["docker", "exec", ERP_BACKEND, "cat", d], nhi_phan=True)
            (dich / Path(d).name).write_bytes(kq.stdout or b"")
        return dich


def _chi_chu_doc(tep: Path) -> None:
    try:
        os.chmod(tep, 0o600)
    except OSError:
        pass                    # Windows: quyền theo ACL, không theo chmod


def bao_nguoi_van_hanh(noi_dung: str, goc: Path = TRIEN_KHAI) -> bool:
    """
    Gửi một dòng tới webhook của NGƯỜI VẬN HÀNH (`CANH_GAC_WEBHOOK` trong
    .env.nen — khác webhook của từng cửa hàng). Không có thì chỉ in: cron
    gửi đầu ra qua thư nếu máy có cấu hình mail, còn không thì nằm trong
    /var/log/cskh-canh.log do scripts/cai_vps.sh đặt.
    """
    tep = goc / ".env.nen"
    m = re.search(r"^CANH_GAC_WEBHOOK=(.+)$", tep.read_text(encoding="utf-8"), re.M) \
        if tep.exists() else None
    if not m or not m.group(1).strip():
        return False
    import urllib.request

    try:
        req = urllib.request.Request(
            m.group(1).strip(), data=json.dumps({"text": noi_dung}).encode("utf-8"),
            headers={"content-type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10):
            return True
    except OSError as exc:
        print(f"Không gửi được báo động: {type(exc).__name__}", file=sys.stderr)
        return False


def khoi_tao(goc: Path = TRIEN_KHAI, email: str = "") -> list[str]:
    """Sinh .env.nen (mật khẩu superuser Postgres) và Caddyfile rỗng nếu chưa có."""
    viec = []
    env = goc / ".env.nen"
    if not env.exists():
        env.write_text(f"POSTGRES_MAT_KHAU={secrets.token_urlsafe(32)}\nTLS_EMAIL={email}\n"
                       "# Webhook nhận báo động của người vận hành (n8n/Telegram/Slack...).\n"
                       "CANH_GAC_WEBHOOK=\n",
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
    t.add_argument("--gcp-khoa", help="tệp khoá service account Google Cloud (Vertex AI)")
    n = sub.add_parser("nhap", help="dựng cửa hàng từ gói chuyển nhà của máy cũ")
    n.add_argument("ma")
    n.add_argument("--ten", required=True)
    n.add_argument("--ten-mien", required=True)
    n.add_argument("--goi", required=True)
    n.add_argument("--mat-khau-tep", required=True)
    n.add_argument("--gcp-khoa")
    n.add_argument("--khong-erp", action="store_true")
    n.add_argument("--dien-tap", action="store_true",
                   help="không vòng nền, không gửi tin, không giữ phiên Zalo — để thử khi máy cũ còn chạy")
    e = sub.add_parser("erp", help="ERPNext dùng chung trên VPS")
    e.add_argument("viec", choices=["khoi_tao", "chay", "tao_site", "nhap", "sao_luu", "ping"])
    e.add_argument("--ten-mien", default="")
    e.add_argument("--tu", help="thư mục bản sao lưu bench (cho `erp nhap`)")
    sub.add_parser("liet_ke")
    kk = sub.add_parser("kiem")
    kk.add_argument("--sua", action="store_true",
                    help="bật lại container chết/treo và ghi nhịp đập người canh (cron)")
    tp = sub.add_parser("thu_phuc_hoi")
    tp.add_argument("ma", nargs="?")
    tp.add_argument("--tat-ca", action="store_true")
    for ten in ("tam_dung", "chay", "khoi_dong_lai"):
        sub.add_parser(ten).add_argument("ma")
    g = sub.add_parser("goi")
    g.add_argument("ma")
    g.add_argument("ten_goi", choices=sorted(GOI))
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
        elif ts.lenh == "nhap":
            mk = Path(ts.mat_khau_tep).read_text(encoding="utf-8").strip()
            kq = mp.nhap(ts.ma, ts.ten, ts.ten_mien, Path(ts.goi), mk,
                         gcp_khoa=Path(ts.gcp_khoa) if ts.gcp_khoa else None,
                         khong_erp=ts.khong_erp, dien_tap=ts.dien_tap)
            print(f"Đã nhập cửa hàng {ts.ma}: {kq['so_hoi_thoai']} hội thoại, "
                  f"{kq['so_tin_da_nhap']}/{kq['so_tin']} tin, {kq['so_khach']} khách, "
                  f"ERP: {'có' if kq.get('erp') and not ts.khong_erp else 'không'}"
                  + (" — CHẾ ĐỘ DIỄN TẬP (không vòng nền)" if kq["dien_tap"] else ""))
            print(f"Tiếp: trỏ DNS {ts.ten_mien} về máy này, rồi khai lại webhook Meta/Zalo OA "
                  f"theo https://{ts.ten_mien} (xem docs/len-vps.md, bước 6).")
        elif ts.lenh == "erp":
            erp = ERP(mp)
            if ts.viec == "khoi_tao":
                for v in erp.khoi_tao(ts.ten_mien):
                    print(v)
            elif ts.viec == "chay":
                erp.chay()
                print("ERPNext đang khởi động (lần đầu mất 1–2 phút).")
            elif ts.viec == "tao_site":
                erp.tao_site()
                print("Đã tạo site ERPNext mới. Mật khẩu Administrator: trien_khai/erp/.env.erp")
            elif ts.viec == "nhap":
                if not ts.tu:
                    raise LoiCuaHang("thiếu --tu <thư mục bản sao lưu>")
                print(f"Đã khôi phục ERPNext: {erp.nhap(Path(ts.tu))['tep']}")
            elif ts.viec == "sao_luu":
                print(f"Sao lưu ERPNext: {erp.sao_luu()}")
            else:
                ok = erp.ping()
                print("ERPNext trả lời" if ok else "ERPNext KHÔNG trả lời")
                return 0 if ok else 1
            if ts.viec in ("khoi_tao", "nhap", "tao_site"):
                mp._ghi_caddy()
        elif ts.lenh == "tao":
            tep = mp.tao(ts.ma, ts.ten, ts.ten_mien,
                         gcp_khoa=Path(ts.gcp_khoa) if ts.gcp_khoa else None)
            print(f"Đã dựng cửa hàng {ts.ma}. Thông tin đăng nhập đầu tiên: {tep} "
                  "(không in ra đây).")
            print("Nhớ trỏ DNS tên miền về máy này, rồi khai URL webhook Meta/Zalo theo tên miền ấy.")
        elif ts.lenh == "liet_ke":
            for c in mp.danh_sach():
                print(f"{c['ma']:20} {c['trang_thai']:9} {c['goi']:10} {c['ten_mien']}  — {c['ten']}")
        elif ts.lenh == "kiem":
            if ts.sua:
                viec = mp.sua_hong()
                for ten, mo_ta in viec:
                    print(f"SỬA {ten}: {mo_ta}")
                if viec:
                    bao_nguoi_van_hanh("Người canh VPS đã phải bật lại: "
                                       + "; ".join(f"{t} ({m})" for t, m in viec))
            hong = 0
            for ma, ok, trang in mp.kiem():
                print(f"{'ỔN ' if ok else 'HỎNG'} {ma:20} {trang}")
                hong += not ok
            return 1 if hong else 0
        elif ts.lenh == "thu_phuc_hoi":
            ds = [c["ma"] for c in mp.danh_sach()] if ts.tat_ca else [ts.ma]
            if not ds or ds == [None]:
                raise LoiCuaHang("Chỉ rõ mã cửa hàng hoặc --tat-ca.")
            hong = []
            for ma in ds:
                try:
                    kq = mp.thu_phuc_hoi(ma)
                    print(f"{ma}: phục hồi {kq['tep']} được {kq['so_bang']} bảng, "
                          f"{kq['so_tin']} tin nhắn — CSDL tạm đã xoá.")
                except LoiCuaHang as exc:
                    print(f"{ma}: HỎNG — {exc}", file=sys.stderr)
                    hong.append(ma)
            if hong:
                bao_nguoi_van_hanh(f"Thử phục hồi sao lưu HỎNG: {', '.join(hong)}")
                return 1
        elif ts.lenh in ("tam_dung", "chay", "khoi_dong_lai"):
            mp.doi_trang_thai(ts.ma, ts.lenh)
            print(f"{ts.lenh}: {ts.ma} xong")
        elif ts.lenh == "goi":
            mp.doi_goi(ts.ma, ts.ten_goi)
            k, nv, ai = GOI[ts.ten_goi]
            print(f"{ts.ma}: gói {ts.ten_goi} — {k or '∞'} kênh, {nv or '∞'} nhân viên, "
                  f"{ai or '∞'} hội thoại AI/tháng. Đã dựng lại app.")
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
