"""
Đóng gói cửa hàng đang chạy trên MÁY NÀY để chuyển lên VPS.

    python -m scripts.chuyen_nha dong_goi                 gói nóng (máy này vẫn chạy)
    python -m scripts.chuyen_nha dong_goi --dung-may-nay  DỪNG máy này rồi mới gói
    python -m scripts.chuyen_nha xem <goi> <tep-mat-khau> xem gói có gì, không giải nén

Ra hai tệp trong `chuyen_nha/` (bị .gitignore chặn):
    goi-<thời điểm>.cskh          gói ĐÃ MÃ HOÁ (scripts/goi_ma_hoa.py)
    goi-<thời điểm>.mat-khau.txt  mật khẩu — chép lên VPS bằng đường KHÁC gói

Trên VPS: `python3 -m scripts.cua_hang nhap <ma> --goi ... --mat-khau-tep ...`.

GÓI CÓ GÌ
---------
  csdl.dump       pg_dump CSDL `marketing_agent` — hội thoại, khách, đơn,
                  kho bí mật tài khoản kênh (token Facebook/Zalo đã mã hoá)
  du_lieu.tar     data/: danh mục thật, tài liệu tri thức, ảnh, tệp khách gửi
  cau_hinh.json   giá trị .env cần mang theo — QUAN TRỌNG NHẤT là
                  CREDENTIAL_MASTER_KEYS: thiếu nó thì mọi token kênh trong
                  CSDL thành rác, phải nối lại từng kênh bằng tay
  erp/            bản sao lưu ERPNext (CSDL + tệp + site_config có khoá mã
                  hoá của ERPNext) khi ERP_LOAI=erpnext
  manifest.json   số đếm để VPS tự kiểm "đã nhận đủ chưa"

VÌ SAO CÓ --dung-may-nay
------------------------
Hai bản cùng chạy là tin trả lời ĐÔI cho khách, và hai sidecar cùng một
phiên Zalo thì Zalo đá văng một bên. Gói nóng dùng để DIỄN TẬP; lần chuyển
thật thì dừng máy này trước (và mọi tin vào sau lúc gói sẽ không có trên VPS).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import tarfile
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GOC = Path(__file__).resolve().parent.parent
PHIEN_BAN = 1

# Khoá .env KHÔNG mang theo: thuộc về máy (địa chỉ, cổng, đường dẫn, vai
# tiến trình) — VPS sinh giá trị của riêng nó. Mọi khoá khác đều mang, để
# không cấu hình nghiệp vụ nào (giờ làm việc, ngưỡng, token kênh, ERP...)
# lặng lẽ rơi mất giữa đường.
KHONG_MANG = frozenset({
    "DATABASE_URL", "PUBLIC_BASE_URL", "WEBHOOK_PUBLIC_URL", "COOKIE_BAO_MAT",
    "VAI_TRO_TIEN_TRINH", "LEGACY_POLLING_BAT", "SAO_LUU_MOI_NGAY", "CSKH_SILO",
    "ZALO_SIDECAR_SECRET", "ZALO_SIDECAR_URL", "ZALO_CONTROL_PLANE_URL",
    "ERPNEXT_URL", "VIDEO_STUDIO_DIR", "VIDEO_OUTPUT_DIR", "FFPROBE_BIN",
    "HYPERFRAMES_BAT", "TTS_BASE_URL", "LANGFUSE_HOST", "N8N_WEBHOOK_URL",
    "N8N_AUTH_HEADER", "ZALOCRM_BASE_URL", "ZALOCRM_API_KEY", "CHATWOOT_BASE_URL",
    "CHATWOOT_API_TOKEN", "CHATWOOT_ACCOUNT_ID", "CHATWOOT_WEBHOOK_SECRET",
    "GOOGLE_APPLICATION_CREDENTIALS",
})

# Trong data/: thứ của MÁY (nhật ký, sao lưu cục bộ, kết quả đo), không
# phải của cửa hàng. Sao lưu cũ đặc biệt không được mang: nó nhân đôi kích
# thước gói và chứa dữ liệu khách đã có trong csdl.dump.
_BO_DU_LIEU = re.compile(
    r"^(backup|backups|sao_luu)(/|$)|\.log(\.|$)|\.err$|\.bak$|^\.canh_gac_ngoai$"
    r"|^\.sao_luu_ngoai$|^\.thu_phuc_hoi$|^eval/(ket-qua|nhieu-luot)-|^eval/golden\.jsonl$")


class LoiChuyen(Exception):
    pass


def doc_env(tep: Path) -> dict[str, str]:
    ra: dict[str, str] = {}
    for dong in tep.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Z][A-Z0-9_]*)=(.*)$", dong)
        if m:
            ra[m.group(1)] = m.group(2).strip()
    return ra


def cau_hinh_mang_theo(env: dict[str, str]) -> dict[str, str]:
    if not env.get("CREDENTIAL_MASTER_KEYS"):
        raise LoiChuyen("`.env` không có CREDENTIAL_MASTER_KEYS — không có nó thì token "
                        "kênh trong CSDL không giải mã được trên VPS.")
    return {k: v for k, v in env.items() if k not in KHONG_MANG}


def tep_du_lieu(thu_muc: Path) -> list[Path]:
    ra = []
    for p in sorted(thu_muc.rglob("*")):
        if not p.is_file():
            continue
        tuong_doi = p.relative_to(thu_muc).as_posix()
        if _BO_DU_LIEU.search(tuong_doi):
            continue
        ra.append(p)
    return ra


def _chay(lenh: list[str], *, nhi_phan: bool = False, cwd: Path | None = None):
    kq = subprocess.run(lenh, capture_output=True, cwd=cwd, check=False)
    if kq.returncode != 0:
        loi = (kq.stderr or b"").decode("utf-8", "replace").strip()[:400]
        raise LoiChuyen(f"{' '.join(lenh[:4])} hỏng: {loi}")
    return kq.stdout if nhi_phan else kq.stdout.decode("utf-8", "replace")


def _psql(goc: Path, sql: str) -> str:
    return _chay(["docker", "compose", "exec", "-T", "db", "psql", "-U", "agent", "-d",
                  "marketing_agent", "-At", "-c", sql], cwd=goc).strip()


from scripts.cua_hang import duong_sao_luu_bench  # noqa: E402


def _sao_luu_erp(tam: Path) -> list[str]:
    """`bench backup --with-files` trong container ERPNext máy này, chép ra `tam/erp`."""
    trang = _chay(["docker", "inspect", "-f", "{{.State.Running}}", "erpnext-web"]).strip()
    if trang != "true":
        raise LoiChuyen("ERPNext máy này đang TẮT — bật trước: docker compose -f "
                        "docker-compose.erpnext.yml up -d (chờ ~1 phút) rồi chạy lại. "
                        "Hoặc thêm --khong-erp nếu VPS không cần dữ liệu ERP cũ.")
    ra = _chay(["docker", "exec", "erpnext-web", "bench", "--site", "localhost", "backup",
                "--with-files"])
    duong = duong_sao_luu_bench(ra)
    if not any(d.endswith("-database.sql.gz") for d in duong):
        raise LoiChuyen("bench backup không báo tệp CSDL nào — xem docker logs erpnext-web")
    (tam / "erp").mkdir()
    ten = []
    for d in duong:
        dich = tam / "erp" / Path(d).name
        dich.write_bytes(_chay(["docker", "exec", "erpnext-web", "cat", d], nhi_phan=True))
        ten.append(dich.name)
    return ten


def dung_may_nay() -> list[str]:
    """Tắt người canh (để nó không dựng lại) rồi dừng app + sidecar. Trả các bước đã làm."""
    from scripts import khoi_dong as k

    viec = []
    if sys.platform == "win32":
        r = subprocess.run(["schtasks", "/change", "/tn", "CanhGacMarketingAgent", "/disable"],
                           capture_output=True, text=True)
        viec.append("tắt task CanhGacMarketingAgent" if r.returncode == 0
                    else "KHÔNG tắt được task người canh — tắt tay trong Task Scheduler")
    k._tat_app()
    viec.append("dừng app")
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | Where-Object "
                    "{ $_.CommandLine -like '*server.mjs*' } | ForEach-Object { Stop-Process "
                    "-Id $_.ProcessId -Force }"] if sys.platform == "win32"
                   else ["pkill", "-f", "node src/server.mjs"], capture_output=True)
    viec.append("dừng sidecar Zalo")
    return viec


def dong_goi(goc: Path, ra_thu_muc: Path, *, co_erp: bool | None = None,
             dung_truoc: bool = False) -> tuple[Path, Path, dict]:
    from scripts import goi_ma_hoa

    env = doc_env(goc / ".env")
    cau_hinh = cau_hinh_mang_theo(env)
    if co_erp is None:
        co_erp = env.get("ERP_LOAI", "tep").lower() == "erpnext"
    viec_dung = dung_may_nay() if dung_truoc else []

    import tempfile

    with tempfile.TemporaryDirectory() as t:
        tam = Path(t)
        dump = _chay(["docker", "compose", "exec", "-T", "db", "pg_dump", "-U", "agent", "-Fc",
                      "marketing_agent"], nhi_phan=True, cwd=goc)
        if len(dump) < 1024:
            raise LoiChuyen("pg_dump ra gần như rỗng — CSDL máy này có đang chạy?")
        (tam / "csdl.dump").write_bytes(dump)
        tep = tep_du_lieu(goc / "data")
        with tarfile.open(tam / "du_lieu.tar", "w") as tar:
            for p in tep:
                tar.add(p, arcname=p.relative_to(goc / "data").as_posix())
        erp = _sao_luu_erp(tam) if co_erp else []
        manifest = {
            "phien_ban": PHIEN_BAN, "luc": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "nong": not dung_truoc, "viec_dung_may": viec_dung,
            "so_tin": int(_psql(goc, "SELECT count(*) FROM messages")),
            "so_hoi_thoai": int(_psql(goc, "SELECT count(*) FROM conversations")),
            "so_khach": int(_psql(goc, "SELECT count(*) FROM contacts")),
            "migration_cuoi": _psql(goc, "SELECT max(version) FROM schema_migrations"),
            "so_tep_du_lieu": len(tep), "erp": erp, "erp_site": "localhost" if erp else None,
        }
        (tam / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
        (tam / "cau_hinh.json").write_text(json.dumps(cau_hinh, ensure_ascii=False),
                                           encoding="utf-8")

        ra_thu_muc.mkdir(parents=True, exist_ok=True)
        ten = time.strftime("goi-%Y%m%d-%H%M")
        goi, tep_mk = ra_thu_muc / f"{ten}.cskh", ra_thu_muc / f"{ten}.mat-khau.txt"
        mat_khau = goi_ma_hoa.sinh_mat_khau()
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for p in sorted(tam.rglob("*")):
                if p.is_file():
                    tar.add(p, arcname=p.relative_to(tam).as_posix())
        buf.seek(0)
        with open(goi, "wb") as f:
            goi_ma_hoa.ma_hoa(buf, f, mat_khau)
        tep_mk.write_text(mat_khau + "\n", encoding="utf-8")
    return goi, tep_mk, manifest


def mo_goi(goi: Path, mat_khau: str, dich: Path) -> dict:
    """Giải mã + giải nén vào `dich` (thư mục rỗng). Trả manifest."""
    from scripts import goi_ma_hoa

    buf = io.BytesIO()
    with open(goi, "rb") as f:
        goi_ma_hoa.giai_ma(f, buf, mat_khau)
    buf.seek(0)
    with tarfile.open(fileobj=buf, mode="r") as tar:
        # filter="data": chặn đường dẫn tuyệt đối, "..", symlink ra ngoài —
        # gói là dữ liệu từ ngoài vào máy chủ.
        tar.extractall(dich, filter="data")
    manifest = json.loads((dich / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("phien_ban") != PHIEN_BAN:
        raise LoiChuyen(f"gói phiên bản {manifest.get('phien_ban')}, mã này đọc {PHIEN_BAN}")
    for can in ("csdl.dump", "du_lieu.tar", "cau_hinh.json"):
        if not (dich / can).exists():
            raise LoiChuyen(f"gói thiếu {can}")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m scripts.chuyen_nha")
    sub = ap.add_subparsers(dest="lenh", required=True)
    d = sub.add_parser("dong_goi")
    d.add_argument("--dung-may-nay", action="store_true")
    d.add_argument("--khong-erp", action="store_true")
    d.add_argument("--goc", default=str(GOC), help="thư mục dự án đang chạy (có .env, data/)")
    d.add_argument("--ra", default="", help="thư mục ghi gói (mặc định <goc>/chuyen_nha)")
    x = sub.add_parser("xem")
    x.add_argument("goi")
    x.add_argument("mat_khau_tep")
    ts = ap.parse_args(argv)
    try:
        if ts.lenh == "dong_goi":
            goc = Path(ts.goc).resolve()
            goi, tep_mk, m = dong_goi(goc, Path(ts.ra) if ts.ra else goc / "chuyen_nha",
                                      co_erp=False if ts.khong_erp else None,
                                      dung_truoc=ts.dung_may_nay)
            print(f"Gói: {goi} ({goi.stat().st_size // 1024} KB, đã mã hoá)")
            print(f"Mật khẩu: {tep_mk} — KHÔNG in ra đây; chép lên VPS bằng đường khác gói.")
            print(f"Có: {m['so_hoi_thoai']} hội thoại, {m['so_tin']} tin, {m['so_khach']} khách, "
                  f"{m['so_tep_du_lieu']} tệp dữ liệu, ERP: {'có' if m['erp'] else 'không'}")
            if m["nong"]:
                print("Gói NÓNG (máy này vẫn chạy) — dùng để diễn tập. Lần chuyển thật: "
                      "thêm --dung-may-nay.")
        else:
            import tempfile

            mk = Path(ts.mat_khau_tep).read_text(encoding="utf-8").strip()
            with tempfile.TemporaryDirectory() as t:
                print(json.dumps(mo_goi(Path(ts.goi), mk, Path(t)), ensure_ascii=False, indent=2))
    except (LoiChuyen, OSError) as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 — LoiGoi và lỗi giải nén: nói rõ, không traceback
        print(f"LỖI: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
