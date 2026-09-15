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


def doc_ten_trong_prompt(prompt: str, ten_danh_muc: str) -> dict:
    """
    Phần thuần: agent có tự giới thiệu ĐÚNG TÊN cửa hàng không.

    LỖI ĐÃ XẢY RA THẬT (14.09.2026)
    -------------------------------
    `agent/prompts/system.md` viết "nhân viên tư vấn của Aurora Skin" —
    thương hiệu MẪU của repo — trong khi danh mục thật là BLANICA. Agent
    chào khách thật bằng tên một cửa hàng không tồn tại, mỗi lần chào, suốt
    nhiều tuần.

    Không có gì nổ: câu chữ trôi chảy, `docs`, test, eval đều xanh. Mục
    "Dữ liệu doanh nghiệp" ở trên cũng xanh — nó kiểm danh mục, kho tri
    thức và ảnh, còn prompt thì không ai nghĩ tới. Đúng loại xanh giả mà
    CLAUDE.md cảnh báo, và nó nằm ở câu ĐẦU TIÊN khách đọc.

    Giờ prompt mang placeholder `{THUONG_HIEU}`, thay bằng tên từ danh mục
    lúc nạp. Phép kiểm này canh hai chiều: placeholder còn đó, và danh mục
    có tên để điền vào.
    """
    ten = "Tên cửa hàng agent nói"
    if "{THUONG_HIEU}" not in prompt:
        return _muc(
            ten, CHAN,
            "prompt hệ thống GÕ CỨNG tên thương hiệu — agent sẽ nói tên ấy "
            "với mọi khách, kể cả khi danh mục là thương hiệu khác",
            "Đặt lại {THUONG_HIEU} trong agent/prompts/system.md; tên thật "
            "lấy từ trường thuong_hieu của data/catalog.json",
        )
    if not ten_danh_muc or ten_danh_muc == tools_mac_dinh():
        return _muc(
            ten, CANH_BAO,
            f"danh mục chưa khai `thuong_hieu` — agent tự xưng là "
            f"“{tools_mac_dinh()}”",
            "Thêm trường thuong_hieu vào data/catalog.json để agent giới "
            "thiệu đúng tên cửa hàng",
        )
    return _muc(ten, DU, f"agent tự xưng là “{ten_danh_muc}”")


def tools_mac_dinh() -> str:
    from agent.core import tools

    return tools.TEN_THUONG_HIEU_MAC_DINH


def kiem_ten_trong_prompt() -> dict:
    from agent.core import tools

    prompt = (ROOT / "agent" / "prompts" / "system.md").read_text(encoding="utf-8")
    return doc_ten_trong_prompt(prompt, tools.ten_thuong_hieu())


def doc_nguoi_canh(tuoi_phut: float | None) -> dict:
    """
    Phần thuần: `tuoi_phut` là tuổi của file trạng thái người canh bên ngoài
    (`data/.canh_gac_ngoai`), None nếu chưa từng có.

    Người canh chạy mỗi 5 phút và ghi file ấy MỖI lần chạy, kể cả khi mọi
    thứ tốt. File cũ hơn 15 phút nghĩa là chính người canh đã ngừng — task
    bị gỡ, máy vừa đăng nhập lại mà task chưa chạy, hay .bat hỏng. Đó là
    lúc "app chết thì ai dựng lại" không còn ai trả lời, và không gì trên
    dashboard nói ra: dashboard chỉ biết về chính nó.

    Đo được 14.09.2026: máy tắt lúc 09:50, người canh không chạy được khi
    máy tắt (đương nhiên), nhưng sau khi đăng nhập lại cũng không có gì cho
    biết nó đã chạy lại chưa và đã làm gì.
    """
    ten = "Người canh bên ngoài"
    sua = ("Đăng ký task 5 phút một lần: xem đầu scripts/canh_gac_ngoai.py "
           "(schtasks trên Windows, cron trên Linux). Không có nó, app chết "
           "lúc 2 giờ sáng là chết tới sáng")
    if tuoi_phut is None:
        return _muc(ten, CANH_BAO, "chưa từng chạy — không ai dựng lại app khi nó chết", sua)
    if tuoi_phut > 15:
        return _muc(ten, CANH_BAO,
                    f"lần chạy cuối cách đây {int(tuoi_phut)} phút — task đã ngừng?",
                    sua)
    return _muc(ten, DU, f"chạy cách đây {int(tuoi_phut)} phút")


def doc_ghi_don(ghi_don: bool, submit_don: bool) -> dict:
    """
    Phần thuần: đơn chốt xong có sang ERP không, và có giữ chỗ hàng không.

    HAI CÔNG TẮC, BA TRẠNG THÁI, và trạng thái giữa là chỗ dễ tưởng đã
    xong nhất.

    Tắt ghi đơn: ERP không biết gì về đơn nào. Kho nội bộ trừ, kho ERP
    không, và hai bên lệch dần theo từng đơn cho tới lần kiểm kê.

    Bật ghi đơn nhưng chưa submit: đơn sang ERP ở dạng NHÁP. Nhìn thấy
    được trong danh sách, nên mọi dấu hiệu nói đã xong — nhưng ERPNext chỉ
    giữ chỗ hàng khi đơn được submit, nên hai khách vẫn mua được cùng một
    món cuối. Đo được 15.09.2026: đơn SAL-ORD-2026-00001 sang tới nơi mà
    `reserved_qty` vẫn bằng 0.
    """
    ten = "Ghi đơn sang ERP"
    if not ghi_don:
        return _muc(
            ten, CANH_BAO,
            "ERP_GHI_DON đang TẮT — đơn chốt xong không sang ERP",
            "Kho nội bộ trừ, kho ERP không, hai bên lệch dần theo từng đơn. "
            "Đặt ERP_GHI_DON=true rồi mở ERP xem tận mắt đơn ĐẦU TIÊN",
        )
    if not submit_don:
        return _muc(
            ten, CANH_BAO,
            "đơn sang ERP ở dạng NHÁP — ERPNext CHƯA giữ chỗ tồn kho",
            "Đơn nhìn thấy được trong ERP nên trông như đã xong, nhưng hai "
            "khách vẫn mua được cùng một món cuối. Đặt ERP_SUBMIT_DON=true "
            "để đơn thành chứng từ chính thức và kho được giữ chỗ ngay",
        )
    return _muc(ten, DU, "đơn sang ERP dạng chính thức, kho được giữ chỗ ngay")


def kiem_ghi_don() -> dict:
    return doc_ghi_don(
        ghi_don=bool(settings.erp_ghi_don),
        submit_don=bool(settings.erp_submit_don),
    )


def doc_van_chuyen(provider: str, co_token: bool, co_shop_id: bool,
                   url: str) -> dict:
    """
    Phần thuần: vận chuyển đang nối thật, hay đang chạy bằng hàng giả.

    LỖI THẬT, ĐO ĐƯỢC 15.09.2026. `SHIPPING_PROVIDER=mock` với token và
    shop id đều rỗng, và không mục nào ở đâu nói ra — bảng xanh hết.

    `MockShippingProvider.tao_van_don()` trả về một mã vận đơn trông như
    thật. Nhân viên bấm tạo vận đơn, nhận mã, nhắn cho khách, và hãng vận
    chuyển chưa bao giờ nghe nói tới đơn này. Khách tra mã thì không thấy
    gì. Đúng khuôn `ERP_LOAI=tep`: rất hữu ích lúc dựng, rất nguy hiểm khi
    không ai nhớ nó đang bật.

    CẢNH BÁO CHỨ KHÔNG CHẶN. Cửa hàng tự đi gửi hàng, không dùng hãng nào,
    là cách vận hành hợp lệ; chặn ở đó là bắt họ cấu hình thứ họ không
    dùng.

    THIẾU KHOÁ THÌ HỎNG, không phải cảnh báo: bật một hãng thật mà thiếu
    khoá là cấu hình mâu thuẫn, và MỌI lần tạo vận đơn đều hỏng.
    """
    ten = "Vận chuyển"
    p = (provider or "").strip().lower()

    if p in ("", "khong", "khong_dung", "none"):
        return _muc(ten, DU, "không nối hãng nào — cửa hàng tự gửi")

    if p == "mock":
        return _muc(
            ten, CANH_BAO,
            "đang dùng hãng GIẢ (mock) — mã vận đơn phát ra KHÔNG tra được "
            "ở đâu cả",
            "Đặt SHIPPING_PROVIDER=ghn kèm GHN_TOKEN và GHN_SHOP_ID. Để "
            "nguyên thì nhân viên sẽ nhắn cho khách một mã vận đơn không "
            "tồn tại, và chỉ vỡ ra khi khách hỏi lại",
        )

    thieu = [t for t, co in (("GHN_TOKEN", co_token),
                             ("GHN_SHOP_ID", co_shop_id)) if not co]
    if thieu:
        return _muc(
            ten, CHAN,
            f"bật {p!r} nhưng thiếu {', '.join(thieu)} — mọi lần tạo vận đơn sẽ hỏng",
            f"Điền {', '.join(thieu)} trong .env, hoặc quay về "
            "SHIPPING_PROVIDER=mock nếu chưa tới lúc nối thật",
        )

    if "dev-" in (url or "") or "sandbox" in (url or "").lower():
        return _muc(
            ten, CANH_BAO,
            f"{p} đang trỏ vào môi trường THỬ ({url[:48]}…)",
            "Sandbox trả mã vận đơn thật-như-thật nhưng KHÔNG có kiện hàng "
            "nào được lấy — xanh hoàn toàn và sai hoàn toàn. Đổi sang địa "
            "chỉ production khi chạy thật",
        )

    return _muc(ten, DU, f"{p} đã đủ khoá, trỏ vào địa chỉ thật")


def kiem_van_chuyen() -> dict:
    return doc_van_chuyen(
        provider=getattr(settings, "shipping_provider", "") or "",
        co_token=bool((getattr(settings, "ghn_token", "") or "").strip()),
        co_shop_id=bool(str(getattr(settings, "ghn_shop_id", "") or "").strip()),
        url=getattr(settings, "ghn_api_url", "") or "",
    )


def kiem_nguoi_canh() -> dict:
    """Người canh bên ngoài (`scripts/canh_gac_ngoai.py`) còn chạy không."""
    from datetime import datetime, timezone

    f = ROOT / "data" / ".canh_gac_ngoai"
    if not f.exists():
        return doc_nguoi_canh(None)
    moi = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc)
    return doc_nguoi_canh((datetime.now(timezone.utc) - moi).total_seconds() / 60)


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
    except Exception as exc:  # noqa: BLE001 — không có CSDL thì vẫn đọc được .env
        # Nói ra là không đếm được, chứ không lặng lẽ coi như bằng 0: nuốt ở
        # đây nghĩa là khoá chủ vault đổi mà mục này vẫn báo "đủ".
        print(f"[cảnh báo] không đếm được sự kiện giải mã hỏng ({type(exc).__name__})")
        giai_ma_hong = 0
    provider = (cau_hinh_dong.lay("LLM_PROVIDER") or "gemini").lower()
    khoa = "GEMINI_API_KEY" if provider == "gemini_api" else "ANTHROPIC_API_KEY"
    if provider in ("gemini_api", "anthropic"):
        return doc_khoa_api(provider, cau_hinh_dong.nguon(khoa), bool(cau_hinh_dong.lay(khoa)), giai_ma_hong)
    return doc_khoa_api(provider, "trong", False, giai_ma_hong)


def doc_embedding(da_nap: str | None, hien_hanh: str) -> dict:
    """
    Phần thuần: `da_nap` là model ghi trong `embed_model_dang_dung` (None khi
    chưa có dòng nào), `hien_hanh` là model provider hiện hành sẽ dùng.

    Hai model cho hai không gian vector khác nhau. Kho nạp bằng A mà hỏi bằng
    B thì `<=>` vẫn trả về đủ số kết quả, xếp hạng vẫn có vẻ hợp lý, và
    không một lỗi nào được ghi — agent chỉ trích dẫn nhầm đoạn tài liệu.
    Đổi provider trên dashboard là lúc chuyện này xảy ra.

    VẮNG DÒNG KHÔNG PHẢI LÀ AN TOÀN: bookkeeping mới có gần đây, nên kho nạp
    trước đó không để lại dấu vết nào — và mọi kho như vậy dùng `EMBED_MODEL`
    mặc định. Coi None là `EMBED_MODEL` thì đúng cảnh "đổi sang gemini_api
    xong chưa nạp lại" được báo, thay vì xanh giả.
    """
    from agent.core import rag

    ten = "Embedding"
    thuc = da_nap or rag.EMBED_MODEL
    if thuc == hien_hanh:
        ghi = hien_hanh + ("" if da_nap else " (chưa ghi nhận lần nạp nào)")
        return _muc(ten, DU, ghi)
    if da_nap:
        ghi = f"kho nạp bằng {da_nap}, đang hỏi bằng {hien_hanh}"
    else:
        ghi = (f"chưa ghi nhận lần nạp nào, đang hỏi bằng {hien_hanh} — kho có "
               f"thể được nạp bằng {rag.EMBED_MODEL} trước khi đổi provider")
    return _muc(
        ten, CANH_BAO,
        ghi + " — tìm kiếm trả kết quả sai mà không một lỗi nào",
        "Nạp lại kho tri thức (Tri thức → Nạp lại), hoặc: python -m "
        "scripts.ingest data/knowledge",
    )


async def kiem_embedding() -> dict:
    """Kho tri thức có được nạp bằng đúng model embedding đang hỏi không."""
    from agent import db
    from agent.core import rag

    hien = rag.embed_model_hien_hanh()
    try:
        await db.init_db()
        row = await db.fetchrow(
            "SELECT gia_tri FROM cau_hinh_agent WHERE khoa = 'embed_model_dang_dung'"
        )
    except Exception as exc:  # noqa: BLE001
        return _muc("Embedding", CANH_BAO,
                    f"không hỏi được CSDL ({type(exc).__name__})",
                    "Khởi động PostgreSQL rồi chạy lại")
    return doc_embedding(str(row["gia_tri"]) if row else None, hien)


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


def doc_webhook_zalo_oa(tai_khoan: list[dict], public_base_url: str) -> dict:
    """
    Địa chỉ webhook đã khai ở Zalo Console còn trỏ đúng chỗ không.

    VÌ SAO MỤC “Callback provider” KHÔNG THAY ĐƯỢC MỤC NÀY
    ------------------------------------------------------
    Mục kia hỏi "PUBLIC_BASE_URL có phải https không" — câu đó gần như luôn
    đúng, kể cả khi Zalo đang gọi vào một tên miền `trycloudflare` đã chết
    từ lần khởi động trước. Một mục luôn xanh không nói gì về việc tin khách
    có vào được hay không.

    Mục này đọc tên miền Zalo THẬT SỰ đã gọi vào — ghi lại mỗi lần một
    webhook qua được chữ ký — rồi so với tên miền hiện tại.

    Kết luận lấy theo mục TỆ NHẤT: một OA chết vẫn là một OA chết, dù ba OA
    khác đang chạy tốt.
    """
    from agent.omnichannel.webhook_da_toi import (TRANG_CHUA_RO, TRANG_LECH,
                                                  so_dia_chi)

    if not tai_khoan:
        return _muc("Webhook Zalo OA", DU, "chưa nối OA nào")

    lech, chua_ro = [], []
    for tk in tai_khoan:
        trang, ly_do = so_dia_chi(tk.get("metadata"), public_base_url)
        ten = str(tk.get("display_name") or "OA")
        if trang == TRANG_LECH:
            lech.append(f"{ten}: {ly_do}")
        elif trang == TRANG_CHUA_RO:
            chua_ro.append(ten)

    goc = (public_base_url or "").rstrip("/")
    if lech:
        return _muc(
            "Webhook Zalo OA", CHAN, "; ".join(lech),
            "Vào Zalo Developers → OA → Webhook, dán lại "
            f"{goc}/webhook/native/zalo-oa/<account_id>. "
            "Lấy đúng địa chỉ ở dashboard → Kết nối",
        )
    if chua_ro:
        return _muc(
            "Webhook Zalo OA", CANH_BAO,
            f"chưa có webhook nào của Zalo tới được ({', '.join(chua_ro)})",
            "Chưa chứng minh được địa chỉ trong Zalo Console là đúng — "
            "nhắn thử một tin vào OA rồi chạy lại lệnh này. "
            f"Địa chỉ cần khai: {goc}/webhook/native/zalo-oa/<account_id>",
        )
    return _muc("Webhook Zalo OA", DU,
                f"Zalo gọi đúng vào {_host_goc(public_base_url)}")


def _host_goc(url: str) -> str:
    from agent.omnichannel.webhook_da_toi import doc_host
    return doc_host(url) or url


async def kiem_webhook_zalo_oa() -> dict:
    from agent import db

    dong = await db.fetch(
        "SELECT display_name, metadata FROM channel_accounts "
        "WHERE channel = 'zalo_oa' AND status IN ('active', 'degraded')")
    return doc_webhook_zalo_oa([dict(d) for d in dong],
                               settings.public_base_url or "")


def doc_callback_cong_khai(url: str, ma_http: int | None, loi: str | None, la_app_nay: bool) -> dict:
    """
    Phán quyết tách khỏi phần gọi mạng, để test lái được mọi nhánh.

    VÌ SAO KHÔNG CÒN CHỈ KIỂM CHUỖI
    -------------------------------
    Bản trước của hàm này chỉ hỏi `url.startswith("https://")` rồi báo ĐỦ.
    Nghĩa là tên miền tunnel chết ba tiếng trước, tin Zalo OA và Facebook
    rơi vào hư không suốt ba tiếng, mà mục này vẫn xanh — vì chuỗi trong
    `.env` vẫn còn nguyên chữ `https`.

    Tên miền `trycloudflare` ĐỔI MỖI LẦN CHẠY. Đó không phải rủi ro hiếm,
    đó là mặc định: mỗi lần khởi động lại máy là một tên miền mới, và nếu
    quên dán lại URL webhook ở Meta/Zalo thì kênh chết im lặng. CLAUDE.md
    đã ghi đúng câu ấy; phép kiểm thì lại không canh nó.

    Zalo cá nhân KHÔNG đi qua tunnel (sidecar gọi thẳng 127.0.0.1), nên
    tunnel chết vẫn còn một kênh sống — và đó chính là điều khiến nó khó
    thấy: dashboard vẫn có tin mới, chỉ thiếu hẳn hai kênh kia.

    VÀ "GỌI TỚI ĐƯỢC BÂY GIỜ" VẪN CHƯA PHẢI ĐỦ
    ------------------------------------------
    Một tên miền `trycloudflare` đang sống vẫn là tên miền sẽ chết ở lần
    cloudflared chạy lại tiếp theo — đo được bốn lần đổi trong 24 giờ, một
    lần lúc 0h20 dù máy vẫn chạy bình thường. Nên URL tạm mà gọi được thì
    là CẢNH BÁO, không phải ĐỦ: nó nói "hôm nay chạy", không nói "dán một
    lần là xong".
    """
    ten = "Callback provider"
    if not url.startswith("https://"):
        return _muc(
            ten, CANH_BAO,
            "chưa có HTTPS công khai cho webhook",
            "Tạo hostname/tunnel HTTPS trỏ về cổng 8000 rồi cấu hình callback riêng của từng account",
        )
    if loi is not None:
        return _muc(
            ten, CHAN,
            f"URL công khai không gọi tới được ({loi})",
            "Tunnel đã chết hoặc đổi tên miền. Chạy python -m scripts.khoi_dong rồi DÁN LẠI "
            "URL webhook ở Meta và Zalo OA. Bỏ bước dán lại là hai kênh ấy chết im lặng",
        )
    if not la_app_nay:
        return _muc(
            ten, CANH_BAO,
            f"URL công khai trả {ma_http} nhưng không nhận ra ứng dụng này",
            "Tên miền có thể đã được cấp cho tunnel của người khác, hoặc proxy biên chặn "
            "/healthz. Mở thẳng URL trong trình duyệt để xem đang trỏ về đâu",
        )
    if "trycloudflare.com" in url:
        return _muc(
            ten, CANH_BAO,
            "gọi tới được, nhưng là tunnel TẠM — tên miền đổi mỗi lần "
            "cloudflared chạy lại",
            "Webhook đã dán vào Zalo/Meta sẽ chết ở lần đổi tiếp theo mà không "
            "có gì báo. Bật tunnel CỐ ĐỊNH: bốn bước ở đầu scripts/chay_tunnel.py "
            "(cần một tên miền và tài khoản Cloudflare miễn phí)",
        )
    return _muc(ten, DU, "URL công khai gọi tới được và trả đúng ứng dụng này")


async def kiem_callback_cong_khai() -> dict:
    """Gọi THẬT vào URL công khai, không chỉ đọc chuỗi trong `.env`."""
    from urllib.parse import urlsplit

    import httpx

    url = settings.webhook_public_url or ""
    if not url.startswith("https://"):
        return doc_callback_cong_khai(url, None, None, False)

    p = urlsplit(url)
    ma_http: int | None = None
    la_app_nay = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as khach:
            r = await khach.get(f"{p.scheme}://{p.netloc}/healthz")
        ma_http = r.status_code
        # `/healthz` của app trả {"ok": true, "runtime": {...}}. Một tunnel
        # lạ chiếm tên miền cũ sẽ trả 404 hoặc JSON hình dạng khác, nên đây
        # phân biệt được "tới được" với "tới đúng app của mình".
        than = r.json() if r.status_code == 200 else {}
        la_app_nay = bool(than.get("ok")) and "runtime" in than
        loi = None
    except Exception as exc:  # noqa: BLE001 — mọi kiểu hỏng mạng đều là "không tới được"
        loi = type(exc).__name__
    return doc_callback_cong_khai(url, ma_http, loi, la_app_nay)


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
        kiem_bi_mat(), await kiem_khoa_api(), await kiem_embedding(),
        kiem_du_lieu_that(), kiem_ten_trong_prompt(),
        await kiem_kenh(), await kiem_callback_cong_khai(),
        await kiem_webhook_zalo_oa(),
        await kiem_tai_khoan(), await kiem_kho_bi_mat_tai_khoan(),
        await kiem_bi_mat_sidecar(),
        await kiem_outbox(), await kiem_ton_kho(),
        kiem_ghi_don(), kiem_van_chuyen(),
        kiem_sao_luu(), kiem_bao_dong(), kiem_nguoi_canh(),
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
