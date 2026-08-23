"""
Hệ thống đã sẵn sàng chạy với khách THẬT chưa — kiểm bằng máy, không bằng trí nhớ.

    python -m scripts.san_sang

VÌ SAO CẦN LỆNH NÀY
-------------------
`docs/dua-vao-doanh-nghiep.md` liệt kê bảy việc bắt buộc trước khi chạy
thật. Nó là văn xuôi, và văn xuôi thì người ta đọc một lần rồi tin là mình
đã làm.

Đúng chuyện đó đã xảy ra trong chính dự án này: tài liệu ghi "sao lưu:
scripts/sao_luu.py" ở cột ĐÃ ĐỦ, trong khi không có lịch nào gọi nó. Và
`CANH_GAC_WEBHOOK` để trống suốt nhiều ngày, nghĩa là toàn bộ hệ thống báo
động ghi vào hư không mà không ai biết.

Một danh sách kiểm mà máy tự chạy được thì không nói dối.

BA MỨC, KHÔNG PHẢI HAI
----------------------
  CHẶN     chạy thật là gây hại: bí mật mặc định, dữ liệu hư cấu
  CẢNH BÁO chạy được nhưng sẽ đau: chưa sao lưu, báo động không tới ai
  ĐỦ       xong

Gộp "chưa lý tưởng" chung với "nguy hiểm" thì danh sách đỏ rực và người ta
bỏ qua cả hai.
"""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.config import settings  # noqa: E402

CHAN, CANH_BAO, DU = "CHẶN", "cảnh báo", "đủ"

# Bí mật mặc định trong tài liệu công khai không phải bí mật.
MAU_MAC_DINH = ("doi-chuoi", "thay-doi", "changeme", "password", "secret",
                "thu-nghiem", "admin123", "123456")


def _muc(ten: str, muc: str, ghi: str, sua: str = "") -> dict:
    return {"ten": ten, "muc": muc, "ghi": ghi, "sua": sua}


def _cong_mo_ra_ngoai(cong: int) -> bool:
    """
    Cổng có nghe trên mọi giao diện mạng không (0.0.0.0), hay chỉ localhost.

    Thử nối từ địa chỉ LAN của chính máy này: nối được nghĩa là máy khác
    trong cùng mạng cũng nối được.
    """
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        return False
    if ip.startswith("127."):
        return False
    s = socket.socket()
    s.settimeout(0.8)
    try:
        s.connect((ip, cong))
        return True
    except OSError:
        return False
    finally:
        s.close()


def kiem_bi_mat() -> dict:
    """Việc 1 — đổi mọi bí mật mặc định."""
    env = ROOT / ".env"
    if not env.exists():
        return _muc("Bí mật", CHAN, "chưa có file .env", "cp .env.example .env")
    xau = []
    for dong in env.read_text(encoding="utf-8", errors="replace").splitlines():
        d = dong.strip()
        if not d or d.startswith("#") or "=" not in d:
            continue
        khoa, gia = d.split("=", 1)
        gia = gia.strip().strip('"').strip("'").lower()
        if gia and any(m in gia for m in MAU_MAC_DINH):
            xau.append(khoa)      # CHỈ tên khoá, không bao giờ in giá trị
    if xau:
        return _muc("Bí mật", CHAN,
                    f"{len(xau)} khoá còn giá trị mặc định/thử nghiệm: "
                    + ", ".join(xau),
                    "đặt giá trị thật, sinh bằng: python -c "
                    '"import secrets; print(secrets.token_urlsafe(32))"')
    return _muc("Bí mật", DU, "không thấy giá trị mặc định nào")


def kiem_cookie() -> dict:
    """Việc 2 — cookie chỉ đi qua HTTPS."""
    if settings.cookie_bao_mat:
        return _muc("Cookie qua HTTPS", DU, "COOKIE_BAO_MAT=true")
    return _muc(
        "Cookie qua HTTPS", CANH_BAO,
        "COOKIE_BAO_MAT=false — cookie phiên đi ở dạng thường",
        "Chỉ bật SAU khi đã có HTTPS thật. Bật khi còn http://localhost thì "
        "trình duyệt không gửi cookie và không ai đăng nhập được.")


def _dang_chay(cong: int) -> bool:
    s = socket.socket()
    s.settimeout(0.8)
    try:
        s.connect(("127.0.0.1", cong))
        return True
    except OSError:
        return False
    finally:
        s.close()


def kiem_cong() -> dict:
    """
    Việc 3 — đóng cổng không cần mở ra ngoài.

    DỊCH VỤ ĐANG TẮT THÌ KHÔNG KẾT LUẬN LÀ AN TOÀN.
    Bản đầu của hàm này trả "đủ — không cổng nào mở ra LAN" trong khi
    Docker đang tắt. Không có gì để nối thì tất nhiên không nối được, và
    một dấu xanh vì lý do đó tệ hơn không kiểm: nó khiến người ta bật dịch
    vụ lên rồi tưởng đã kiểm rồi.
    """
    ho = [(3080, "ZaloCRM"), (5678, "n8n"), (9000, "MinIO"), (8000, "Dashboard")]
    chay = [(c, t) for c, t in ho if _dang_chay(c)]
    if not chay:
        return _muc("Cổng ra mạng LAN", CANH_BAO,
                    "chưa kiểm được — không dịch vụ nào đang chạy",
                    "docker compose up -d rồi chạy lại lệnh này")

    mo = [f"{t} :{c}" for c, t in chay if _cong_mo_ra_ngoai(c)]
    tat = [t for c, t in ho if not _dang_chay(c)]
    ghi_them = f" (chưa kiểm: {', '.join(tat)})" if tat else ""
    if mo:
        return _muc("Cổng ra mạng LAN", CANH_BAO,
                    "cả mạng LAN vào được: " + " · ".join(mo) + ghi_them,
                    "Chỉ cổng của lớp proxy được ra ngoài; còn lại buộc về "
                    "127.0.0.1 trong docker-compose.")
    return _muc("Cổng ra mạng LAN", DU,
                f"{len(chay)} dịch vụ đang chạy, không cổng nào ra LAN" + ghi_them)


async def kiem_tai_khoan() -> dict:
    """Việc 4 — mỗi người một tài khoản."""
    from agent import db
    try:
        await db.init_db()
        r = await db.fetch("SELECT ten_dang_nhap, vai_tro FROM nguoi_dung "
                           "WHERE NOT khoa")
    except Exception as exc:  # noqa: BLE001
        return _muc("Tài khoản", CANH_BAO,
                    f"không hỏi được CSDL ({type(exc).__name__})",
                    "docker compose up -d")
    if not r:
        return _muc("Tài khoản", CHAN, "chưa có tài khoản nào",
                    'python -m scripts.tao_tai_khoan admin "mật khẩu" --quan-tri')
    qt = sum(1 for x in r if x["vai_tro"] == "quan_tri")
    if len(r) == 1:
        return _muc("Tài khoản", CANH_BAO,
                    "chỉ có 1 tài khoản — dùng chung thì nhật ký kiểm toán "
                    "thành vô nghĩa",
                    'python -m scripts.tao_tai_khoan <tên> "mật khẩu"')
    return _muc("Tài khoản", DU, f"{len(r)} tài khoản ({qt} quản trị)")


def kiem_sao_luu() -> dict:
    """Việc 5 — sao lưu tự động, và đã thử phục hồi."""
    thu_muc = ROOT / "data" / "backup"
    if not thu_muc.exists() or not any(thu_muc.iterdir()):
        return _muc("Sao lưu", CHAN, "chưa có bản sao lưu nào",
                    "python -m scripts.sao_luu — rồi đặt Task Scheduler chạy "
                    "hằng ngày, và THỬ PHỤC HỒI một lần")
    ban = sorted(thu_muc.glob("*"), key=lambda p: p.stat().st_mtime)
    from datetime import datetime, timezone
    moi = datetime.fromtimestamp(ban[-1].stat().st_mtime, timezone.utc)
    ngay = (datetime.now(timezone.utc) - moi).days
    if ngay > 2:
        return _muc("Sao lưu", CANH_BAO, f"bản mới nhất đã {ngay} ngày",
                    "đặt lịch chạy hằng ngày")
    return _muc("Sao lưu", CANH_BAO,
                f"{len(ban)} bản, mới nhất {ngay} ngày trước",
                "Bản sao lưu CHƯA TỪNG phục hồi thử thì chưa phải bản sao "
                "lưu — máy không kiểm hộ việc này được.")


def kiem_du_lieu_that() -> dict:
    """Việc 6 và 7 — danh mục, tài liệu và ảnh phải là của doanh nghiệp bạn."""
    thieu = []
    cat = ROOT / "data" / "catalog.json"
    if not cat.exists():
        thieu.append("chưa có data/catalog.json (đang dùng danh mục mẫu)")
    else:
        try:
            d = json.loads(cat.read_text(encoding="utf-8"))
            if "aurora" in str(d.get("thuong_hieu", "")).lower():
                thieu.append("catalog.json vẫn là thương hiệu hư cấu Aurora Skin")
        except ValueError:
            thieu.append("catalog.json không đọc được")

    tri_thuc = ROOT / "data" / "knowledge"
    if not tri_thuc.exists() or not any(tri_thuc.glob("*.md")):
        thieu.append("chưa có tài liệu thật trong data/knowledge/")

    manifest = ROOT / "data" / "products" / "manifest.json"
    if manifest.exists() and "KHÔNG phải ảnh chụp" in manifest.read_text(
            encoding="utf-8", errors="replace"):
        thieu.append("ảnh sản phẩm vẫn là ảnh model sinh, không phải hàng thật")

    if thieu:
        return _muc("Dữ liệu doanh nghiệp", CHAN, " · ".join(thieu),
                    "Bán hàng bằng ảnh không phải sản phẩm mình bán là quảng "
                    "cáo sai sự thật. Sửa xong chạy: python -m scripts.ingest")
    return _muc("Dữ liệu doanh nghiệp", DU, "danh mục, tài liệu và ảnh đều là thật")


def kiem_bao_dong() -> dict:
    """Không nằm trong bảy việc, nhưng phát hiện được khi chạy thật."""
    if settings.canh_gac_webhook:
        return _muc("Báo động tới người", DU, "đã có CANH_GAC_WEBHOOK")
    return _muc("Báo động tới người", CANH_BAO,
                "CANH_GAC_WEBHOOK trống — canh gác chỉ ghi nhật ký, "
                "KHÔNG ai nhận được tin",
                "Trỏ vào một webhook n8n để định tuyến ra Zalo/Telegram. "
                "Agent chết lúc 2 giờ sáng thì tới sáng mới biết.")


def kiem_kenh() -> dict:
    """Có kênh nào thật sự nhận được tin của khách không."""
    from agent.channels import registry
    bat = registry.dang_bat()
    if not bat:
        return _muc("Kênh nhận tin", CHAN, "chưa cấu hình kênh nào",
                    "Điền ZALOCRM_API_KEY hoặc CHATWOOT_* trong .env")
    return _muc("Kênh nhận tin", DU, "đang bật: " + ", ".join(bat))


async def chay() -> int:
    muc = [
        kiem_bi_mat(), kiem_du_lieu_that(), kiem_kenh(),
        await kiem_tai_khoan(), kiem_sao_luu(), kiem_bao_dong(),
        kiem_cookie(), kiem_cong(),
    ]

    dau = {CHAN: "[CHẶN]", CANH_BAO: "[cảnh báo]", DU: "[đủ]"}
    print("\nSẴN SÀNG CHẠY VỚI KHÁCH THẬT?\n" + "─" * 62)
    for m in muc:
        print(f"{dau[m['muc']]:<12} {m['ten']:<22} {m['ghi']}")
        if m["sua"] and m["muc"] != DU:
            for dong in m["sua"].split(". "):
                if dong.strip():
                    print(f"{'':<12} └─ {dong.strip()}")

    chan = [m for m in muc if m["muc"] == CHAN]
    canh = [m for m in muc if m["muc"] == CANH_BAO]
    print("─" * 62)
    if chan:
        print(f"CHƯA CHẠY ĐƯỢC: còn {len(chan)} việc CHẶN"
              + (f", {len(canh)} cảnh báo" if canh else ""))
        return 1
    if canh:
        print(f"Chạy được, nhưng còn {len(canh)} cảnh báo sẽ gây đau về sau.")
        return 0
    print("Đủ điều kiện chạy với khách thật.")
    return 0


def main() -> int:
    import asyncio
    return asyncio.run(chay())


if __name__ == "__main__":
    raise SystemExit(main())
