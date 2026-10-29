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

MÃ HOÁ VÀ BẢN NGOÀI MÁY
-----------------------
Bản sao lưu chứa số điện thoại, địa chỉ và ảnh da của khách — dữ liệu nhạy
cảm theo Luật BVDLCN 91/2025. Đặt `SAO_LUU_MAT_KHAU` thì bản CSDL được mã hoá
(AES-256-GCM, cùng định dạng gói chuyển nhà) ngay trong bộ nhớ: bản thường
không bao giờ chạm đĩa. Đặt `SAO_LUU_THU_MUC_NGOAI` thì bản đã mã hoá được
chép thêm ra đó — một bản cùng máy không cứu được khi chính cái máy hỏng.
Bản chưa mã hoá KHÔNG bao giờ được chép ra ngoài.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import shutil
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
DUOI_MA_HOA = ".cskh"
# Dấu mốc lần chép ra ngoài máy gần nhất (thành công HAY hỏng) — san_sang
# đọc để biết bản ngoài máy còn tươi không. Tên khác `.sao_luu_ngoai` của
# chế độ silo (scripts/cua_hang.py) để hai nghĩa không lẫn vào nhau.
DAU_MOC_NGOAI = ROOT / "data" / ".sao_luu_ra_ngoai_may"
_MAU_DB = ("db-*.sql.gz", "db-*.sql.gz" + DUOI_MA_HOA)


def ban_db(kho: Path | None = None) -> list[Path]:
    """Mọi bản sao lưu CSDL — thường và đã mã hoá — cũ trước, mới sau."""
    kho = kho or KHO
    if not kho.exists():
        return []
    return sorted({p for m in _MAU_DB for p in kho.glob(m)}, key=lambda p: p.name)


def doc_ban_db(tep: Path, mat_khau: str | None = None) -> bytes:
    """Bản sao lưu → SQL thô. Bản `.cskh` cần đúng mật khẩu (sai thì nổ to)."""
    from scripts import goi_ma_hoa

    if tep.name.endswith(DUOI_MA_HOA):
        mk = mat_khau if mat_khau is not None else settings.sao_luu_mat_khau
        if not mk:
            raise goi_ma_hoa.LoiGoi("bản sao lưu đã mã hoá nhưng SAO_LUU_MAT_KHAU đang trống")
        buf = io.BytesIO()
        with tep.open("rb") as f:
            goi_ma_hoa.giai_ma(f, buf, mk)
        return gzip.decompress(buf.getvalue())
    with gzip.open(tep, "rb") as f:
        return f.read()


def ban_moi_con_tuoi(gio: float = 20.0) -> bool:
    """
    Bản CSDL mới nhất chưa tới `gio` giờ tuổi. `backup_loop` dùng để không sao
    lưu ở MỖI lần app khởi động: người canh dựng lại app vài lần một ngày là
    14 bản giữ lại đều cùng một ngày, mất hết các mốc phục hồi cũ — đúng thứ
    cần khi hỏng dữ liệu phát hiện chậm (rà soát 28.10.2026).
    """
    import time

    ban = ban_db()
    return bool(ban) and (time.time() - max(p.stat().st_mtime for p in ban)) < gio * 3600


def ma_hoa_ban_cu() -> int:
    """
    Đã có mật khẩu thì mã hoá lại các bản CSDL cũ còn ở dạng thường — giữ
    nguyên mốc phục hồi, bỏ bản thường. Không làm thì bật mật khẩu xong, dữ
    liệu khách vẫn nằm dạng thường thêm 14 vòng sao lưu.
    """
    from scripts import goi_ma_hoa

    if not settings.sao_luu_mat_khau:
        return 0
    da = 0
    for cu in ban_db():
        if cu.name.endswith(DUOI_MA_HOA):
            continue
        dich = cu.with_name(cu.name + DUOI_MA_HOA)
        tam = dich.with_name(dich.name + ".dang-ghi")
        with cu.open("rb") as vao, tam.open("wb") as ra:
            goi_ma_hoa.ma_hoa(vao, ra, settings.sao_luu_mat_khau)
        tam.replace(dich)
        # Giữ dấu thời gian của bản cũ: thứ tự mốc phục hồi đọc theo mtime.
        import os
        st = cu.stat()
        os.utime(dich, (st.st_atime, st.st_mtime))
        cu.unlink()
        da += 1
    return da


def chep_ra_ngoai(tep: Path, thu_muc: str | None = None) -> tuple[bool, str]:
    """
    Chép một bản ĐÃ MÃ HOÁ ra thư mục ngoài máy. Ghi dấu mốc cả khi hỏng:
    hỏng mà không ghi gì là bản ngoài máy cũ dần trong im lặng.
    """
    noi = (thu_muc if thu_muc is not None else settings.sao_luu_thu_muc_ngoai).strip()
    if not noi:
        return False, "chưa đặt SAO_LUU_THU_MUC_NGOAI"
    if not tep.name.endswith(DUOI_MA_HOA):
        return False, "KHÔNG chép bản chưa mã hoá ra ngoài máy — đặt SAO_LUU_MAT_KHAU trước"
    try:
        dich = Path(noi)
        dich.mkdir(parents=True, exist_ok=True)
        tam = dich / (tep.name + ".dang-chep")
        shutil.copyfile(tep, tam)
        # Đổi tên sau khi chép xong: thư mục đồng bộ đám mây không được
        # thấy (và tải lên) một tệp chép dở như thể nó là bản hoàn chỉnh.
        tam.replace(dich / tep.name)
        ok, ghi = True, f"đã chép ra {dich}"
    except OSError as exc:
        ok, ghi = False, f"KHÔNG chép ra ngoài được: {type(exc).__name__}: {exc}"[:200]
    try:
        DAU_MOC_NGOAI.write_text(json.dumps({
            "luc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ok": ok, "tep": tep.name, "ghi": ghi}), encoding="utf-8")
    except OSError:
        pass
    return ok, ghi

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
    nen = gzip.compress(kq.stdout)
    if not settings.sao_luu_mat_khau:
        dich.write_bytes(nen)
        return True, f"{dich.stat().st_size / 1_048_576:.2f} MB · CHƯA MÃ HOÁ (đặt SAO_LUU_MAT_KHAU)"
    from scripts import goi_ma_hoa

    dich = dich.with_name(dich.name + DUOI_MA_HOA)
    tam = dich.with_name(dich.name + ".dang-ghi")
    with tam.open("wb") as f:
        goi_ma_hoa.ma_hoa(io.BytesIO(nen), f, settings.sao_luu_mat_khau)
    tam.replace(dich)
    ghi = f"{dich.stat().st_size / 1_048_576:.2f} MB · đã mã hoá"
    so_cu = ma_hoa_ban_cu()
    if so_cu:
        ghi += f" · mã hoá lại {so_cu} bản cũ"
    if settings.sao_luu_thu_muc_ngoai.strip():
        _ok, ngoai = chep_ra_ngoai(dich)
        ghi += " · " + ngoai
    return True, ghi


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
    # Bản CSDL thường và mã hoá đếm CHUNG một hàng: giữ 14 bản gần nhất là
    # 14 bản, không phải 14 bản mỗi loại.
    for ban in (ban_db(), sorted(KHO.glob("knowledge-*.tar.gz"), key=lambda p: p.name)):
        for cu in (ban[:-giu] if giu > 0 else ban):
            cu.unlink(missing_ok=True)
            da_xoa += 1
    noi = settings.sao_luu_thu_muc_ngoai.strip()
    if noi and giu > 0 and Path(noi).is_dir():
        for cu in ban_db(Path(noi))[:-giu]:
            try:
                cu.unlink(missing_ok=True)
                da_xoa += 1
            except OSError:
                pass
    return da_xoa


DAU_MOC_PHUC_HOI = ROOT / "data" / ".thu_phuc_hoi"
_DEM_BANG = "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"


def thu_phuc_hoi() -> tuple[bool, str]:
    """
    Phục hồi bản `db-*.sql.gz` MỚI NHẤT vào một CSDL tạm, đếm bảng và tin
    nhắn, so với CSDL thật, rồi xoá CSDL tạm. Không đụng CSDL đang chạy.

    Bản sao lưu chưa từng phục hồi thử thì chưa phải bản sao lưu: tệp có
    thể nén hỏng, thiếu extension, hay cắt giữa chừng — và chỉ biết vào đúng
    ngày cần nó. Thành công thì ghi dấu mốc `data/.thu_phuc_hoi` để
    `scripts.san_sang` xác nhận; thất bại thì KHÔNG ghi (dấu mốc cũ dần, mục
    Sao lưu tự đỏ lại).
    """
    import json

    ct = _container()
    if not ct:
        return False, "không thấy container Postgres đang chạy"
    ban = ban_db()
    if not ban:
        return False, "chưa có bản sao lưu CSDL nào — chạy python -m scripts.sao_luu trước"
    tep = ban[-1]
    user, ten_db = _thong_tin_db()
    tam = "thu_phuc_hoi_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    def psql(csdl: str, sql: str, dau_vao: bytes | None = None) -> subprocess.CompletedProcess:
        lenh = ["docker", "exec", "-i", ct, "psql", "-U", user, "-d", csdl, "-v",
                "ON_ERROR_STOP=1", "-X", "-q", "-At"]
        if sql:
            lenh += ["-c", sql]
        return subprocess.run(lenh, input=dau_vao, capture_output=True, timeout=600)

    tao = psql(ten_db, f"CREATE DATABASE {tam};")
    if tao.returncode != 0:
        return False, "không tạo được CSDL tạm: " + tao.stderr.decode(errors="replace")[-200:]
    try:
        try:
            sql = doc_ban_db(tep)
        except Exception as exc:  # noqa: BLE001 — sai mật khẩu, tệp cắt cụt
            return False, f"không đọc được {tep.name}: {type(exc).__name__}: {exc}"[:300]
        kq = psql(tam, "", dau_vao=sql)
        if kq.returncode != 0:
            return False, f"phục hồi {tep.name} HỎNG: " + kq.stderr.decode(errors="replace")[-300:]
        so_bang = int(psql(tam, _DEM_BANG).stdout.decode().strip() or 0)
        so_that = int(psql(ten_db, _DEM_BANG).stdout.decode().strip() or 0)
        so_tin = int(psql(tam, "SELECT count(*) FROM messages;").stdout.decode().strip() or 0)
    finally:
        psql(ten_db, f"DROP DATABASE IF EXISTS {tam} WITH (FORCE);")
    if so_bang == 0 or so_bang < so_that:
        return False, f"bản phục hồi có {so_bang} bảng, CSDL thật có {so_that} — thiếu"
    DAU_MOC_PHUC_HOI.write_text(json.dumps({
        "luc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tep": tep.name, "so_bang": so_bang, "so_tin": so_tin}), encoding="utf-8")
    return True, f"{tep.name}: {so_bang} bảng, {so_tin} tin nhắn — CSDL tạm đã xoá"


def liet_ke() -> None:
    if not KHO.exists() or not any(KHO.iterdir()):
        print(f"Chưa có bản sao lưu nào trong {KHO}")
        print("Tạo bản đầu tiên:  python -m scripts.sao_luu")
        return
    tong = 0.0
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
    ap.add_argument("--thu-phuc-hoi", action="store_true",
                    help="phục hồi bản mới nhất vào CSDL tạm để chứng minh nó dùng được")
    ap.add_argument("--giai-ma", metavar="TEP",
                    help="giải mã một bản .cskh thành .sql.gz cạnh nó (để phục hồi tay)")
    args = ap.parse_args()

    if args.giai_ma:
        tep = Path(args.giai_ma)
        ra = tep.with_name(tep.name.removesuffix(DUOI_MA_HOA))
        ra.write_bytes(gzip.compress(doc_ban_db(tep)))
        print(f"Đã giải mã ra {ra} — bản này KHÔNG mã hoá: phục hồi xong thì xoá nó.")
        return 0

    if args.liet_ke:
        liet_ke()
        return 0
    if args.thu_phuc_hoi:
        ok, ghi_chu = thu_phuc_hoi()
        print(("Thử phục hồi ĐẠT: " if ok else "Thử phục hồi HỎNG: ") + ghi_chu)
        return 0 if ok else 1

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
    print("\nPhục hồi khi cần (bản .cskh: giải mã trước bằng --giai-ma <tệp>):")
    print("  gunzip -c data/backup/db-<mốc>.sql.gz | \\")
    print(f"    docker exec -i {_container() or '<container>'} psql -U agent -d marketing_agent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
