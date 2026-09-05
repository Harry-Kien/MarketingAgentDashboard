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
    ho = [(3210, "Zalo sidecar"), (5678, "n8n"), (5433, "PostgreSQL"), (8000, "Dashboard")]
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
            # CỜ CHUNG, không dò tên thương hiệu.
            #
            # Bản cũ tìm chuỗi "aurora". Nó đúng đúng một lần — với đúng bộ
            # dữ liệu mẫu ban đầu. Ai dựng dữ liệu mẫu mang tên thương hiệu
            # THẬT của mình (chuyện rất hay làm khi tập dùng hệ thống) là
            # phép kiểm báo XANH cho một danh mục vẫn hoàn toàn bịa.
            #
            # Xanh giả nguy hiểm hơn đỏ giả: đỏ giả thì người ta đi kiểm,
            # xanh giả thì không ai kiểm. Nên dấu hiệu phải do người TẠO dữ
            # liệu tự khai, không phải do người kiểm đoán từ cái tên.
            if d.get("du_lieu_mau") is True:
                thieu.append("catalog.json vẫn là DỮ LIỆU MẪU "
                             "(có cờ du_lieu_mau: true)")
            elif "aurora" in str(d.get("thuong_hieu", "")).lower():
                # Giữ lại cho các file cũ chưa có cờ.
                thieu.append("catalog.json vẫn là thương hiệu mẫu cũ")
        except ValueError:
            thieu.append("catalog.json không đọc được")

    tri_thuc = ROOT / "data" / "knowledge"
    if not tri_thuc.exists() or not any(tri_thuc.glob("*.md")):
        thieu.append("chưa có tài liệu thật trong data/knowledge/")
    else:
        # ĐẾM TỆP LÀ CHƯA ĐỦ — PHẢI XEM NÓ NÓI VỀ THƯƠNG HIỆU NÀO.
        #
        # Bản trước chỉ kiểm thư mục có tệp `.md` hay không, nên nó báo
        # XANH cho một kho tri thức toàn tài liệu của thương hiệu MẪU. Đo
        # được thật: sau khi nạp danh mục BLANICA, 12/19 tài liệu vẫn nói
        # về Aurora — và chúng chứa con số cụ thể như "miễn phí vận chuyển
        # từ 500.000đ".
        #
        # Agent trích dẫn nguyên văn những con số đó, KÈM TÊN TÀI LIỆU, và
        # nói với khách rằng đó là chính sách của cửa hàng. Không có gì nổ:
        # tài liệu có thật, trích dẫn đúng, chỉ là của một cửa hàng không
        # tồn tại.
        #
        # Xanh giả ngay trong phép kiểm gác cửa đi vào chạy thật.
        thuong_hieu_that = ""
        if cat.exists():
            try:
                thuong_hieu_that = str(
                    json.loads(cat.read_text(encoding="utf-8"))
                    .get("thuong_hieu", "")
                ).strip()
            except ValueError:
                pass
        if thuong_hieu_that and "aurora" not in thuong_hieu_that.lower():
            con_mau = [
                p.name for p in sorted(tri_thuc.glob("*.md"))
                if "aurora" in p.read_text(
                    encoding="utf-8", errors="replace").lower()
            ]
            if con_mau:
                thieu.append(
                    f"{len(con_mau)}/{len(list(tri_thuc.glob('*.md')))} tài "
                    f"liệu tri thức vẫn nói về thương hiệu MẪU (Aurora) "
                    f"trong khi danh mục là {thuong_hieu_that} — "
                    f"ví dụ: {', '.join(con_mau[:3])}"
                )

    manifest = ROOT / "data" / "products" / "manifest.json"
    if manifest.exists() and "KHÔNG phải ảnh chụp" in manifest.read_text(
            encoding="utf-8", errors="replace"):
        thieu.append("ảnh sản phẩm vẫn là ảnh model sinh, không phải hàng thật")

    if thieu:
        # Gợi ý phải khớp thứ đang thiếu.
        #
        # Bản trước luôn in câu về ẢNH, kể cả khi thứ thiếu là tài liệu tri
        # thức. Người đọc đi sửa ảnh trong khi lỗi nằm ở chỗ khác — một lời
        # khuyên sai chỗ tệ hơn không có lời khuyên nào.
        if any("tri thức" in t for t in thieu):
            sua = (
                "Agent TRÍCH DẪN NGUYÊN VĂN các tài liệu này kèm tên nguồn, "
                "nên chính sách của thương hiệu mẫu sẽ được nói với khách "
                "như chính sách của bạn. Dựng khung: python -m "
                "scripts.sinh_kho_tri_thuc --nganh my_pham · "
                "điền xong: python -m scripts.ingest data/knowledge"
            )
        else:
            sua = ("Bán hàng bằng ảnh không phải sản phẩm mình bán là quảng "
                   "cáo sai sự thật. Sửa xong chạy: python -m scripts.ingest")
        return _muc("Dữ liệu doanh nghiệp", CHAN, " · ".join(thieu), sua)
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


async def kiem_kho_bi_mat_tai_khoan() -> dict:
    """Mọi key version đang dùng phải còn khả năng giải mã sau khi restart."""
    from agent import db
    from agent.security.credential_vault import (
        CredentialVault,
        InvalidMasterKeyConfiguration,
        parse_master_keys,
    )

    try:
        await db.init_db()
        rows = await db.fetch(
            "SELECT DISTINCT key_version FROM credential_secrets ORDER BY key_version"
        )
    except Exception as exc:  # noqa: BLE001
        return _muc(
            "Kho bí mật tài khoản",
            CANH_BAO,
            f"không hỏi được CSDL ({type(exc).__name__})",
            "Khởi động PostgreSQL và chạy lại readiness",
        )

    required = {int(row["key_version"]) for row in rows}
    try:
        keys = parse_master_keys(settings.credential_master_keys)
        CredentialVault(
            keys,
            active_version=settings.credential_active_key_version,
        )
    except InvalidMasterKeyConfiguration:
        if required:
            return _muc(
                "Kho bí mật tài khoản",
                CHAN,
                "thiếu master key version đang dùng: "
                + ", ".join(str(version) for version in sorted(required)),
                "Khôi phục đúng key version từ kho bí mật; không tạo key mới đè lên",
            )
        return _muc(
            "Kho bí mật tài khoản",
            CANH_BAO,
            "chưa cấu hình master key; hiện chưa có credential đã lưu",
            "Sinh key AES-256 theo hướng dẫn trong .env.example trước khi nối kênh",
        )

    missing = required - set(keys)
    if missing:
        return _muc(
            "Kho bí mật tài khoản",
            CHAN,
            "thiếu master key version đang dùng: "
            + ", ".join(str(version) for version in sorted(missing)),
            "Khôi phục đúng key version từ backup kho bí mật",
        )
    return _muc(
        "Kho bí mật tài khoản",
        DU,
        f"đọc được {len(required)} key version đang dùng",
    )


def doc_tham_do_sidecar(loi: str | None, co_tai_khoan: bool) -> dict:
    """
    Phần thuần: `loi` là chi tiết lỗi khi hỏi `status` sidecar bằng bí mật
    trong `.env`, None nếu sidecar trả lời được.

    Không bao giờ in bí mật — chỉ in kết luận.
    """
    ten = "Bí mật sidecar Zalo"
    if loi is None:
        return _muc(ten, DU, "sidecar nhận chữ ký ký bằng .env hiện tại")
    if "chữ ký" in loi.lower():
        return _muc(
            ten, CHAN,
            "sidecar ĐANG CHẠY nhưng với ZALO_SIDECAR_SECRET khác .env",
            "Mọi lời gọi hai chiều bị 401, tin khách rơi im lặng và nút Quét QR "
            "báo sai là 'sidecar chưa chạy'. Khởi động lại sidecar để nó đọc "
            ".env hiện tại: python -m scripts.chay_sidecar_zalo",
        )
    if not co_tai_khoan:
        return _muc(ten, DU, "chưa có tài khoản Zalo cá nhân, sidecar không cần chạy")
    return _muc(
        ten, CANH_BAO, f"sidecar không trả lời ({loi[:80]})",
        "python -m scripts.chay_sidecar_zalo — kênh Zalo cá nhân đang đứt",
    )


async def kiem_bi_mat_sidecar() -> dict:
    """
    Sidecar đang chạy có nhận chữ ký ký bằng `.env` hiện tại không.

    Hỏi THẲNG sidecar chứ không so với vault: từ 04.09.2026 app không còn tin
    bí mật trong vault nữa (xem bi_mat_may_chu.py), nên lệch chỉ còn một
    cách xảy ra — sidecar được bật với `.env` cũ. Đo được đúng cảnh đó: tám
    ngày không tin khách, mọi đèn xanh, nút Quét QR báo "chưa chạy".
    """
    from uuid import uuid4

    from agent.channels.zalo_personal import ZaloPersonalAdapter

    co_tai_khoan = False
    try:
        from agent import db
        await db.init_db()
        co_tai_khoan = bool(await db.fetch(
            "SELECT 1 FROM channel_accounts "
            "WHERE channel = 'zalo_personal' AND status <> 'disabled' LIMIT 1"
        ))
    except Exception:  # noqa: BLE001 — không có CSDL vẫn thăm dò được sidecar
        pass

    if not settings.zalo_sidecar_secret:
        return _muc("Bí mật sidecar Zalo", CANH_BAO if not co_tai_khoan else CHAN,
                    "ZALO_SIDECAR_SECRET trống trong .env",
                    "python -m scripts.sinh_token ZALO_SIDECAR_SECRET rồi bật sidecar")
    adapter = ZaloPersonalAdapter(
        account_id=uuid4(),
        credentials={
            "sidecar_secret": settings.zalo_sidecar_secret,
            "sidecar_url": settings.zalo_sidecar_url,
        },
    )
    try:
        # Chữ ký được kiểm TRƯỚC khi tra tài khoản, nên id ngẫu nhiên vẫn
        # phân biệt được "sai chữ ký" với "không phản hồi".
        await adapter.status()
        loi = None
    except RuntimeError as exc:
        loi = str(exc)
    finally:
        await adapter.aclose()
    return doc_tham_do_sidecar(loi, co_tai_khoan)


def doc_khoa_api(provider: str, nguon_khoa: str, co_khoa: bool, giai_ma_hong: int) -> dict:
    ten = "Khoá API"
    if giai_ma_hong:
        return _muc(
            ten, CHAN, f"{giai_ma_hong} khoá trong CSDL không giải mã được",
            "khoá chủ vault đã đổi. Nhập lại khoá ở dashboard → Cấu hình → Cài đặt API, "
            "hoặc khôi phục CREDENTIAL_MASTER_KEYS cũ",
        )
    can_khoa = provider in ("gemini_api", "anthropic")
    if can_khoa and not co_khoa:
        return _muc(
            ten, CHAN, f"provider {provider} cần API key mà không có ở đâu cả",
            "Nhập ở dashboard → Cấu hình → Cài đặt API (hoặc .env). Không có thì agent "
            "không trả lời được một tin nào",
        )
    nguon = {"csdl": "khoá từ dashboard", "env": "khoá từ .env", "trong": "không cần khoá"}[nguon_khoa]
    return _muc(ten, DU, f"provider {provider} · {nguon}")


async def kiem_khoa_api() -> dict:
    """Provider hiện hành có khoá không, và khoá lấy từ đâu."""
    from agent import cau_hinh_dong, db

    try:
        await db.init_db()
        await cau_hinh_dong.nap()
        hong = await db.fetchrow(
            "SELECT count(*) AS n FROM events WHERE kind = 'cau_hinh_api.giai_ma_hong' "
            "AND created_at > now() - interval '10 minutes'"
        )
        giai_ma_hong = int(hong["n"]) if hong else 0
    except Exception:  # noqa: BLE001 — không có CSDL thì vẫn đọc được .env
        giai_ma_hong = 0
    provider = (cau_hinh_dong.lay("LLM_PROVIDER") or "gemini").lower()
    khoa = "GEMINI_API_KEY" if provider == "gemini_api" else "ANTHROPIC_API_KEY"
    if provider in ("gemini_api", "anthropic"):
        return doc_khoa_api(provider, cau_hinh_dong.nguon(khoa), bool(cau_hinh_dong.lay(khoa)), giai_ma_hong)
    return doc_khoa_api(provider, "trong", False, giai_ma_hong)


async def kiem_outbox() -> dict:
    """Outbox có thoát hàng hay đang chất tin mà worker đã chết."""
    from datetime import datetime, timedelta, timezone
    from agent import db

    try:
        await db.init_db()
        row = await db.fetchrow(
            """
            SELECT
                count(*) FILTER (
                    WHERE status IN ('pending','retry','processing')
                ) AS pending,
                count(*) FILTER (WHERE status = 'dead') AS dead,
                (SELECT last_seen_at FROM worker_heartbeats
                 WHERE worker_name = 'outbox') AS last_seen_at
            FROM outbox_jobs
            """
        )
    except Exception as exc:  # noqa: BLE001
        return _muc(
            "Outbox gửi tin",
            CANH_BAO,
            f"không hỏi được CSDL ({type(exc).__name__})",
            "Khởi động PostgreSQL và ứng dụng rồi chạy lại readiness",
        )

    pending = int((row or {}).get("pending") or 0)
    dead = int((row or {}).get("dead") or 0)
    heartbeat = (row or {}).get("last_seen_at")
    stale = heartbeat is None
    if heartbeat is not None:
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=timezone.utc)
        stale = datetime.now(timezone.utc) - heartbeat > timedelta(minutes=2)

    if pending and stale:
        return _muc(
            "Outbox gửi tin",
            CHAN,
            f"{pending} job đang chờ nhưng worker không có heartbeat mới",
            "Khởi động lại FastAPI worker và kiểm tra /api/outbox/jobs",
        )
    if dead:
        return _muc(
            "Outbox gửi tin",
            CANH_BAO,
            f"có {dead} dead-letter cần xử lý",
            "Quản trị xem lỗi rồi retry/cancel qua API outbox",
        )
    if stale:
        return _muc(
            "Outbox gửi tin",
            CANH_BAO,
            "worker chưa có heartbeat; hiện không có job tồn",
            "Khởi động ứng dụng và chạy lại readiness",
        )
    return _muc("Outbox gửi tin", DU, "worker sống, không có dead-letter")


async def kiem_kenh() -> dict:
    """Chỉ coi account native đã có provider health xanh là kênh thật."""
    from agent import db
    try:
        await db.init_db()
        rows = await db.fetch(
            """
            SELECT account.channel, count(*) AS total
            FROM channel_accounts account
            WHERE NOT account.is_legacy
              AND account.status = 'active'
              AND EXISTS (
                  SELECT 1 FROM account_health_events health
                  WHERE health.account_id = account.id
                    AND health.status = 'active'
              )
            GROUP BY account.channel ORDER BY account.channel
            """
        )
    except Exception as exc:  # noqa: BLE001
        return _muc(
            "Kênh nhận tin", CHAN,
            f"không kiểm được account native ({type(exc).__name__})",
            "Khởi động PostgreSQL, tạo account trong màn Kết nối và bấm Xác minh provider",
        )
    if not rows:
        return _muc(
            "Kênh nhận tin", CHAN, "chưa có account native được provider xác minh",
            "Mở Kết nối, đăng nhập/cấp quyền rồi chạy Xác minh provider cho ít nhất một account",
        )
    labels = {
        "zalo_personal": "Zalo cá nhân", "zalo_oa": "Zalo OA",
        "facebook": "Facebook", "instagram": "Instagram",
        "whatsapp": "WhatsApp", "webchat": "Web chat",
    }
    enabled = [f"{labels.get(row['channel'], row['channel'])} ({row['total']})" for row in rows]
    return _muc("Kênh nhận tin", DU, "provider đã xác minh: " + ", ".join(enabled))


def kiem_callback_cong_khai() -> dict:
    url = settings.webhook_public_url or ""
    if not url.startswith("https://"):
        return _muc(
            "Callback provider", CANH_BAO,
            "chưa có HTTPS công khai cho webhook",
            "Tạo hostname/tunnel HTTPS trỏ về cổng 8000 rồi cấu hình callback riêng của từng account",
        )
    return _muc("Callback provider", DU, "đã có HTTPS công khai")


async def kiem_ton_kho() -> dict:
    """
    Mã trong danh mục có dòng tồn kho không — nếu không thì KHÔNG LÊN ĐƠN ĐƯỢC.

    `giu_hang` từ chối mã không có dòng trong `ton_kho`, nên thiếu một mã là
    hỏng đúng những đơn chứa mã đó, thiếu hết là hỏng mọi đơn. Đã xảy ra
    thật: hàm nạp tồn kho tồn tại nhưng không ai gọi, bảng trống suốt, và
    mọi đơn agent lên đều trả "Mã X không có trong kho".

    Không có gì nổ, không có dòng nhật ký nào, và mục này lúc đó chưa tồn
    tại nên `san_sang` vẫn báo đủ. Đó là lý do phải có nó.
    """
    from agent import db
    from agent.core import tools

    ma_danh_muc = {
        str(sp.get("ma")) for sp in tools._catalog().get("san_pham", [])
        if sp.get("ma")
    }
    if not ma_danh_muc:
        return _muc("Tồn kho", CANH_BAO, "danh mục chưa có sản phẩm nào",
                    "Nạp danh mục trước: python -m scripts.ingest")

    try:
        await db.init_db()
        rows = await db.fetch("SELECT ma FROM ton_kho")
    except Exception as exc:  # noqa: BLE001
        return _muc("Tồn kho", CANH_BAO,
                    f"không hỏi được CSDL ({type(exc).__name__})",
                    "Khởi động PostgreSQL rồi chạy lại")

    thieu = ma_danh_muc - {str(r["ma"]) for r in rows}
    if not thieu:
        return _muc("Tồn kho", DU,
                    f"đủ {len(ma_danh_muc)} mã có dòng tồn kho")

    vi_du = ", ".join(sorted(thieu)[:3])
    if len(thieu) == len(ma_danh_muc):
        return _muc(
            "Tồn kho", CHAN,
            f"KHÔNG mã nào có dòng tồn kho ({len(thieu)}/{len(ma_danh_muc)})",
            "Agent sẽ báo 'không có trong kho' cho MỌI đơn. "
            "Khởi động lại ứng dụng để nạp, hoặc chạy python -m scripts.ingest",
        )
    return _muc(
        "Tồn kho", CANH_BAO,
        f"{len(thieu)}/{len(ma_danh_muc)} mã chưa có dòng tồn kho ({vi_du}...)",
        "Đơn chứa những mã này sẽ hỏng. Khởi động lại ứng dụng để nạp",
    )


async def chay() -> int:
    muc = [
        kiem_bi_mat(), await kiem_khoa_api(), kiem_du_lieu_that(), await kiem_kenh(), kiem_callback_cong_khai(),
        await kiem_tai_khoan(), await kiem_kho_bi_mat_tai_khoan(),
        await kiem_bi_mat_sidecar(),
        await kiem_outbox(), await kiem_ton_kho(),
        kiem_sao_luu(), kiem_bao_dong(),
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
