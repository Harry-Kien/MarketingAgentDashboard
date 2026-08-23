"""
Sao lưu cơ sở dữ liệu và tài liệu công ty.

    python -m scripts.sao_luu              # sao lưu ngay
    python -m scripts.sao_luu --liet-ke    # xem các bản đã có
    python -m scripts.sao_luu --giu 30     # giữ 30 bản gần nhất

VÌ SAO CẦN
----------
Toàn bộ đơn hàng, hội thoại, video và bài đăng nằm trong MỘT container
Postgres. Không có bản sao nào. Volume hỏng, hoặc ai đó gõ nhầm
`docker compose down -v`, là mất sạch — và đây là loại mất mát KHÔNG SỬA
ĐƯỢC SAU. Mọi lỗi khác trong hệ thống này đều còn cứu vãn; lỗi này thì không.

CÁCH LÀM
--------
Gọi `pg_dump` BÊN TRONG container nên máy chủ không phải cài postgres client,
và phiên bản pg_dump luôn khớp phiên bản server — lệch phiên bản là nguyên
nhân kinh điển khiến bản sao lưu không phục hồi được.

Kèm luôn `data/knowledge/` vì đó là tài liệu công ty, không nằm trong git.
"""
from __future__ import annotations

import argparse
import gzip
import subprocess
import sys
import tarfile
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import ROOT, settings      # noqa: E402

KHO = ROOT / "data" / "backup"
GIU_MAC_DINH = 14

# Dòng cuối của một bản pg_dump hoàn chỉnh. Thiếu nó nghĩa là dump bị cắt
# giữa chừng — và một bản sao lưu hỏng còn nguy hiểm hơn không có bản nào,
# vì nó cho cảm giác an toàn giả.
DAU_KET_THUC = b"-- PostgreSQL database dump complete"


def _container() -> str | None:
    """Tìm container Postgres của dự án. Không đoán tên, hỏi docker."""
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    ten = [n for n in out.split() if "marketing" in n and "db" in n and "langfuse" not in n]
    return ten[0] if ten else None


def _thong_tin_db() -> tuple[str, str]:
    """(user, tên db) tách từ DATABASE_URL."""
    phan = settings.database_url.rsplit("/", 1)
    ten_db = phan[-1].split("?")[0] if len(phan) > 1 else "marketing_agent"
    user = "agent"
    if "://" in settings.database_url:
        giua = settings.database_url.split("://", 1)[1]
        if "@" in giua:
            user = giua.split("@")[0].split(":")[0]
    return user, ten_db


def sao_luu_db(dich: Path) -> tuple[bool, str]:
    """Chạy pg_dump trong container, nén gzip. Trả (thành công, ghi chú)."""
    ct = _container()
    if not ct:
        return False, "không thấy container Postgres đang chạy (docker compose up -d?)"

    user, ten_db = _thong_tin_db()
    try:
        kq = subprocess.run(
            ["docker", "exec", ct, "pg_dump", "-U", user, "-d", ten_db],
            capture_output=True, timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"

    if kq.returncode != 0:
        return False, kq.stderr.decode(errors="replace")[-300:]

    if DAU_KET_THUC not in kq.stdout:
        # Không ghi ra đĩa. Bản sao lưu hỏng mà vẫn nằm trong thư mục backup
        # là cái bẫy: đến lúc cần phục hồi mới biết nó vô dụng.
        return False, "pg_dump kết thúc bất thường, bản sao không hoàn chỉnh"

    dich.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(dich, "wb") as f:
        f.write(kq.stdout)
    return True, f"{dich.stat().st_size / 1_048_576:.2f} MB"


def sao_luu_tai_lieu(dich: Path) -> tuple[bool, str]:
    """Đóng gói data/knowledge — tài liệu công ty, không nằm trong git."""
    nguon = ROOT / "data" / "knowledge"
    if not nguon.exists() or not any(nguon.iterdir()):
        return False, "chưa có tài liệu nào trong data/knowledge"
    dich.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dich, "w:gz") as tar:
        tar.add(nguon, arcname="knowledge")
    return True, f"{dich.stat().st_size / 1024:.0f} KB"


def don_ban_cu(giu: int) -> int:
    """Xoá bản cũ, giữ lại `giu` bản gần nhất của mỗi loại."""
    da_xoa = 0
    for mau in ("db-*.sql.gz", "knowledge-*.tar.gz"):
        ban = sorted(KHO.glob(mau), reverse=True)
        for cu in ban[giu:]:
            cu.unlink(missing_ok=True)
            da_xoa += 1
    return da_xoa


def liet_ke() -> None:
    if not KHO.exists() or not any(KHO.iterdir()):
        print(f"Chưa có bản sao lưu nào trong {KHO}")
        print("Tạo bản đầu tiên:  python -m scripts.sao_luu")
        return
    tong = 0
    for f in sorted(KHO.iterdir(), reverse=True):
        mb = f.stat().st_size / 1_048_576
        tong += mb
        thoi = datetime.fromtimestamp(f.stat().st_mtime)
        print(f"  {f.name:34s} {mb:7.2f} MB  {thoi:%Y-%m-%d %H:%M}")
    print(f"\n  Tổng {tong:.1f} MB tại {KHO}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--liet-ke", action="store_true")
    ap.add_argument("--giu", type=int, default=GIU_MAC_DINH)
    args = ap.parse_args()

    if args.liet_ke:
        liet_ke()
        return 0

    dau = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    print(f"Sao lưu lúc {dau} (UTC)\n")

    ok_db, ghi_chu = sao_luu_db(KHO / f"db-{dau}.sql.gz")
    print(f"  cơ sở dữ liệu : {'OK  ' + ghi_chu if ok_db else 'HỎNG — ' + ghi_chu}")

    ok_tl, tl = sao_luu_tai_lieu(KHO / f"knowledge-{dau}.tar.gz")
    print(f"  tài liệu      : {'OK  ' + tl if ok_tl else 'bỏ qua — ' + tl}")

    xoa = don_ban_cu(args.giu)
    if xoa:
        print(f"  dọn bản cũ    : xoá {xoa} file, giữ {args.giu} bản gần nhất")

    if not ok_db:
        print("\nSAO LƯU THẤT BẠI. Đừng bỏ qua dòng này.")
        return 1

    print(f"\nXong. Bản sao nằm ở {KHO}")
    print("\nPhục hồi khi cần:")
    print("  gunzip -c data/backup/db-<mốc>.sql.gz | \\")
    print(f"    docker exec -i {_container() or '<container>'} psql -U agent -d marketing_agent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
