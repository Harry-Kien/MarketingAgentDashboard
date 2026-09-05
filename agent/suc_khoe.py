"""
Tự chẩn đoán sức khoẻ hệ thống.

VÌ SAO CẦN
----------
`/healthz` hiện chỉ trả `{"ok": true}` khi tiến trình còn sống. Nhưng tiến
trình sống KHÔNG có nghĩa là hệ thống đang phục vụ được: hết hạn mức model,
poller ngừng lấy tin Zalo, Postgres đầy đĩa, giọng đọc tắt — tất cả đều để
lại một tiến trình khoẻ mạnh mà khách thì không được trả lời.

Với doanh nghiệp, khoảng thời gian giữa "hệ thống hỏng" và "có người phát
hiện" là khoảng thời gian mất khách. Trang này rút khoảng đó về gần bằng
không.

NGUYÊN TẮC
----------
Mỗi mục đều GỌI THẬT chứ không đoán. Một dịch vụ "đã cấu hình" mà trả 403
thì vẫn là hỏng, và người vận hành cần biết trước khi khách biết.

Ba mức: `tot` (chạy), `canh_bao` (chạy nhưng suy giảm), `hong` (không phục
vụ được). Chỉ `hong` mới kéo trạng thái tổng xuống — suy giảm là chuyện bình
thường của hệ thống có nhiều bậc dự phòng.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from agent import db, runtime
from agent.core import gio_lam_viec
from agent.config import ROOT, settings

TOT, CANH_BAO, HONG = "tot", "canh_bao", "hong"


def _muc(ten: str, trang_thai: str, ghi_chu: str, **them) -> dict:
    return {"ten": ten, "trang_thai": trang_thai, "ghi_chu": ghi_chu, **them}


async def _kiem_db() -> dict:
    t0 = time.perf_counter()
    try:
        row = await db.fetchrow("SELECT count(*) AS n FROM conversations")
        ms = int((time.perf_counter() - t0) * 1000)
        return _muc("Cơ sở dữ liệu", TOT,
                    f"{row['n']} hội thoại · phản hồi {ms}ms", latency_ms=ms)
    except Exception as exc:  # noqa: BLE001
        return _muc("Cơ sở dữ liệu", HONG, f"{type(exc).__name__}: {exc}"[:150])


async def _kiem_model() -> dict:
    """
    Gọi model thật bằng một câu cực ngắn.

    Không có cách nào biết hạn mức còn hay hết mà không gọi. Chi phí một lần
    kiểm dưới 0,00001 USD — rẻ hơn nhiều so với việc phát hiện hết quota qua
    lời phàn nàn của khách.
    """
    from agent import cau_hinh_dong
    from agent.core import llm

    p = llm.provider()
    ok, chi_tiet, ms = await llm.kiem_khoa(
        provider_name=p,
        model=cau_hinh_dong.lay("MODEL_CHEAP") or settings.model_cheap,
    )
    if ok:
        return _muc("Model ngôn ngữ", TOT, f"{chi_tiet} · {p}", latency_ms=ms)
    if "HẾT HẠN MỨC" in chi_tiet:
        return _muc("Model ngôn ngữ", HONG, "HẾT HẠN MỨC — agent không trả lời được khách")
    return _muc("Model ngôn ngữ", HONG, chi_tiet[:150])


async def _kiem_embedding_khop() -> dict:
    """
    Kho tri thức có được nạp bằng đúng model embedding đang hỏi không.

    Hai model cho hai không gian vector khác nhau: kho nạp bằng A, hỏi bằng
    B thì tìm kiếm trả kết quả sai mà không một lỗi nào. Đổi provider trên
    dashboard là lúc chuyện này xảy ra.
    """
    from agent.core import rag

    hien = rag.embed_model_hien_hanh()
    row = await db.fetchrow(
        "SELECT gia_tri FROM cau_hinh_agent WHERE khoa = 'embed_model_dang_dung'"
    )
    if not row:
        return _muc("Embedding kho tri thức", TOT, f"{hien} (chưa ghi nhận lần nạp nào)")
    da = str(row["gia_tri"])
    if da != hien:
        return _muc(
            "Embedding kho tri thức", HONG,
            f"kho nạp bằng {da}, đang hỏi bằng {hien} — tìm kiếm sai mà không lỗi. "
            "Nạp lại kho tri thức (Tri thức → Nạp lại)",
        )
    return _muc("Embedding kho tri thức", TOT, hien)


async def _kiem_giong_doc() -> dict:
    from agent.video import tts

    try:
        ch = await asyncio.wait_for(tts.chan_doan(), timeout=60)
    except Exception as exc:  # noqa: BLE001
        return _muc("Giọng đọc", CANH_BAO, f"không dò được: {type(exc).__name__}")

    if ch.get("viettts"):
        return _muc("Giọng đọc", TOT, "viet-tts")
    if ch.get("google"):
        return _muc("Giọng đọc", TOT, "Google Cloud TTS")
    return _muc("Giọng đọc", CANH_BAO,
                "không có nhà cung cấp nào — video sẽ CÂM và thời lượng chỉ "
                "là ước lượng. " + (ch.get("ly_do_google") or ""))


async def _tai_khoan_active_thieu_credential() -> list[str]:
    """
    Tài khoản mang nhãn `active` mà KHÔNG nạp nổi credential.

    LỖI THẬT, ĐO ĐƯỢC 04.09.2026

    Tài khoản webchat "Web thử nghiệm" hiện `active`, `ly_do_hong` rỗng,
    `/api/suc-khoe` báo "4 kênh native" — nhưng khách bấm vào widget nhận:

        409 {"detail": "Webchat account thiếu widget secret"}

    Nó được tạo và đánh dấu `active` mà chưa từng cấu hình. Bản ghi có
    `metadata` rỗng và không một credential nào.

    Chính docstring của `_kiem_kenh` đã tiên đoán chuyện này — "nếu một ngày
    kênh native chết thật, ô này vẫn nói y hệt — nó chưa từng nhìn vào đó" —
    rồi vẫn đọc cột `status` thay vì gọi thử.

    VÌ SAO KHÔNG GỌI `verify_connection()`

    Đó mới là phép kiểm đầy đủ, nhưng nó đi ra mạng. `canh_gac` chạy mỗi 60
    giây, và `verify` của Zalo OA gọi `_lay_token()`; access token có đệm,
    nhưng đệm nằm trong INSTANCE adapter, nên mỗi lượt kiểm dựng adapter mới
    là một lượt làm mới. Refresh token của Zalo XOAY VÒNG — dùng một lần rồi
    chết. Đốt nó mỗi phút là tự tay giết kênh mình đang canh.

    Hỏi "có credential không" thì chỉ là MỘT truy vấn tồn tại — không giải
    mã, không chạm mạng, không chạm khoá. Nó bắt đúng lớp lỗi "được đánh dấu
    sống nhưng không phục vụ nổi", cho MỌI kênh, kể cả kênh chưa tồn tại lúc
    viết dòng này.

    Sống-hay-chết ở đầu kia đã có vòng giữ phiên Zalo và vòng kiểm token
    Meta lo; chúng ghi kết quả vào `status`, thứ mà `_kiem_kenh` vẫn đọc.
    """
    try:
        r = await db.fetch(
            """
            SELECT a.channel, a.display_name
            FROM channel_accounts a
            WHERE a.status = 'active'
              AND NOT EXISTS (SELECT 1 FROM credential_secrets s
                              WHERE s.account_id = a.id)
            ORDER BY a.channel, a.display_name
            """
        )
        return [f"{x['channel']} · {x['display_name']}" for x in r]
    except Exception:  # noqa: BLE001
        # CSDL sập thì IM LẶNG, và có chủ ý.
        #
        # `_kiem_kenh` vốn bọc truy vấn của nó đúng như vậy, vì "Cơ sở dữ
        # liệu" đã là một mục riêng: hỏng ở đó thì trang sức khoẻ đã đỏ sẵn,
        # nói thêm lần nữa chỉ là nhiễu.
        #
        # Quan trọng hơn: ném ra ở đây là giết cả mục "Kênh nhận tin", tức
        # đổi MỘT ô đỏ lấy một ô biến mất. Test cũ
        # `test_csdl_hong_thi_khong_lam_sap_phep_kiem` bắt đúng chỗ này khi
        # bản đầu của hàm không có khối `try` — nó có từ trước, và nó đúng.
        return []


async def _kiem_kenh() -> dict:
    """
    Kênh nhận tin. Chưa cấu hình thì là lựa chọn, không phải hỏng.

    ĐẾM CẢ TÀI KHOẢN NATIVE, KHÔNG CHỈ HAI KÊNH DI SẢN
    --------------------------------------------------
    Bản trước chỉ nhìn `ZALOCRM_API_KEY` và `CHATWOOT_BASE_URL` — hai đường
    nạp tin CŨ. Từ khi có connector native, khách vào qua `channel_accounts`
    (Zalo cá nhân, Zalo OA, Facebook, Instagram, WhatsApp, web chat), và
    phép kiểm này mù hoàn toàn với chúng.

    Hậu quả đo được: hệ thống có 3 tài khoản `active` và đã nhận 100 tin
    nhắn thật, mà màn hình sức khoẻ vẫn báo "chưa nối kênh nào — hệ thống
    chạy nhưng không có khách vào".

    Báo sai kiểu này không làm ai mất dữ liệu, nhưng nó dạy người vận hành
    bỏ qua đúng cái ô mà họ mở ra để tin. Và nếu một ngày kênh native chết
    thật, ô này vẫn nói y hệt — nó chưa từng nhìn vào đó.
    """
    from agent.channels import registry as channels

    native = ""
    try:
        r = await db.fetch(
            "SELECT channel, status, count(*) n FROM channel_accounts "
            "GROUP BY 1, 2"
        )
        song = {x["channel"] for x in r if x["status"] == "active"}
        hong = sum(x["n"] for x in r
                   if x["status"] in ("degraded", "reauth_required"))
        if song:
            native = f"{len(song)} kênh native: {', '.join(sorted(song))}"
            if hong:
                native += f" · {hong} tài khoản cần xử lý"
    except Exception:  # noqa: BLE001 — CSDL hỏng đã có mục riêng báo
        native = ""

    thieu = await _tai_khoan_active_thieu_credential()
    if thieu:
        # Đặt TRƯỚC mọi nhánh trả `tot` bên dưới. Một tài khoản `active` mà
        # không phục vụ được là hỏng, dù các tài khoản khác có khoẻ đến đâu.
        return _muc(
            "Kênh nhận tin", HONG,
            f"{len(thieu)} kênh hiện 'active' nhưng CHƯA CÓ CREDENTIAL — "
            f"khách vào sẽ bị từ chối: {', '.join(thieu)}",
        )

    bat = []
    if settings.zalocrm_api_key:
        bat.append("zalocrm")
    if settings.chatwoot_base_url and settings.chatwoot_api_token:
        bat.append("chatwoot")

    if not bat:
        if native:
            # Có kênh native là ĐỦ. Hai kênh di sản tắt là chuyện bình
            # thường, không phải thiếu sót.
            return _muc("Kênh nhận tin", TOT, native)
        return _muc("Kênh nhận tin", CANH_BAO,
                    "chưa nối kênh nào — hệ thống chạy nhưng không có khách vào")

    them = f" · {native}" if native else ""
    try:
        tin = await asyncio.wait_for(channels.keo_tin_moi(), timeout=20)
        return _muc("Kênh nhận tin", TOT,
                    f"{', '.join(bat)} · {len(tin)} tin chờ{them}")
    except Exception as exc:  # noqa: BLE001
        return _muc("Kênh nhận tin", HONG,
                    f"{', '.join(bat)}: {type(exc).__name__}: {exc}"[:140])


async def _kiem_hang_doi_video() -> dict:
    try:
        row = await db.fetchrow(
            "SELECT count(*) FILTER (WHERE status = 'queued')                AS cho, "
            "       count(*) FILTER (WHERE status IN "
            "         ('claimed','looking','scripting','voicing','rendering')) AS dang, "
            "       count(*) FILTER (WHERE status = 'failed' "
            "         AND updated_at > now() - interval '24 hours')            AS hong "
            "FROM videos"
        ) or {}
    except Exception as exc:  # noqa: BLE001
        return _muc("Hàng đợi video", HONG, f"{type(exc).__name__}"[:100])

    cho, dang, hong = int(row.get("cho") or 0), int(row.get("dang") or 0), int(row.get("hong") or 0)
    ghi = f"{cho} chờ · {dang} đang dựng · {hong} lỗi trong 24h"
    # Nhiều video xếp hàng mà không cái nào đang chạy = thợ nền đã chết.
    if cho > 3 and dang == 0:
        return _muc("Hàng đợi video", CANH_BAO, ghi + " — hàng đợi ứ, thợ nền có thể đã dừng")
    return _muc("Hàng đợi video", TOT, ghi)


async def _kiem_sao_luu() -> dict:
    kho = ROOT / "data" / "backup"
    ban = sorted(kho.glob("db-*.sql.gz"), reverse=True) if kho.exists() else []
    if not ban:
        return _muc("Sao lưu", HONG,
                    "CHƯA CÓ BẢN SAO NÀO — mất dữ liệu là không cứu được")

    moi = ban[0]
    gio = (time.time() - moi.stat().st_mtime) / 3600
    ghi = f"{len(ban)} bản · gần nhất {gio:.0f} giờ trước ({moi.stat().st_size / 1_048_576:.2f} MB)"
    if gio > 48:
        return _muc("Sao lưu", CANH_BAO, ghi + " — quá 48 giờ, kiểm tra backup_loop")
    return _muc("Sao lưu", TOT, ghi)


async def _kiem_kho_anh() -> dict:
    from agent.core.tools import _catalog
    from agent.video import catalog_images

    sp = _catalog().get("san_pham", [])
    if not sp:
        return _muc("Kho ảnh sản phẩm", CANH_BAO, "danh mục trống")
    co = sum(1 for p in sp if catalog_images.anh_cua(p.get("ma", "")))
    ghi = f"{co}/{len(sp)} sản phẩm có ảnh"
    if co == 0:
        return _muc("Kho ảnh sản phẩm", CANH_BAO, ghi + " — video sẽ chỉ là thẻ chữ")
    return _muc("Kho ảnh sản phẩm", TOT, ghi)


_NOI_BO = ("localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal", "::1")


async def _kiem_cong_cong_khai() -> dict:
    """
    Gọi CHÍNH MÌNH từ ngoài Internet, qua đúng URL mà Zalo/Meta sẽ gọi.

    LỖI THẬT, ĐO ĐƯỢC 04.09.2026

    Tunnel `trycloudflare` sống được 1,5 tiếng rồi bị Cloudflare huỷ từ phía
    họ:

        ERR Register tunnel error from server side
            error="Unauthorized: Tunnel not found"

    Tiến trình `cloudflared` VẪN CHẠY và vẫn thử lại mãi — nên mọi phép kiểm
    kiểu "cloudflared còn sống không" đều trả lời có. Suốt bảy tiếng sau đó:
    URL công khai chết, không webhook nào tới được, mà `/api/suc-khoe` trả
    "tot" và cả bốn kênh hiện `active` với `ly_do_hong` rỗng.

    Xanh giả, đúng kiểu nguy hiểm nhất: đỏ giả thì người ta đi kiểm, xanh
    giả thì không ai kiểm.

    VÌ SAO PHẢI ĐỌC CẢ THÂN PHẢN HỒI

    Tunnel chết mà DNS còn phân giải được thì Cloudflare trả về trang lỗi
    của CHÍNH NÓ. Chỉ xem mã HTTP là có ngày nhận 200 từ một trang báo lỗi.
    Nên phải thấy đúng `"ok": true` do ứng dụng này sinh ra.

    VÌ SAO CHỈ `canh_bao` KHI CHƯA CẤU HÌNH

    `public_base_url` trỏ vào localhost là trạng thái phát triển bình
    thường, không phải sự cố. Gắn nhãn "Hệ thống đang hỏng" cho nó là cách
    nhanh nhất khiến người ta tắt thông báo — và lần sau hỏng thật thì không
    ai thấy.
    """
    import httpx

    goc = (settings.public_base_url or "").strip().rstrip("/")
    if not goc:
        return _muc("Cổng công khai", CANH_BAO,
                    "chưa đặt PUBLIC_BASE_URL — webhook không tới được")
    if any(x in goc for x in _NOI_BO):
        return _muc("Cổng công khai", CANH_BAO,
                    f"{goc} là địa chỉ nội bộ — Zalo/Meta không gọi tới được")

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as c:
            r = await c.get(f"{goc}/healthz")
    except Exception as exc:  # noqa: BLE001
        # Giữ tên ngoại lệ, bỏ thông điệp: httpx nhét URL đầy đủ vào đó, và
        # URL ấy đã từng mang theo token khi có tham số truy vấn.
        return _muc("Cổng công khai", HONG,
                    f"{goc} KHÔNG gọi tới được từ Internet "
                    f"({type(exc).__name__}) — mọi webhook đang rơi vào hư không")

    ms = int((time.perf_counter() - t0) * 1000)
    if r.status_code != 200 or '"ok":true' not in r.text.replace(" ", ""):
        return _muc("Cổng công khai", HONG,
                    f"{goc} trả {r.status_code} chứ không phải ứng dụng này — "
                    "tunnel chết hoặc đang trỏ sang nơi khác", latency_ms=ms)
    return _muc("Cổng công khai", TOT, f"{goc} · {ms}ms", latency_ms=ms)


async def _kiem_khach_gan_nhat() -> dict:
    """Lâu không có tin khách nào là dấu hiệu kênh đứt, không phải ế hàng."""
    try:
        row = await db.fetchrow(
            "SELECT max(created_at) AS gan_nhat FROM messages WHERE role = 'customer'"
        ) or {}
    except Exception as exc:  # noqa: BLE001
        return _muc("Tin khách gần nhất", HONG, f"{type(exc).__name__}"[:100])

    gan = row.get("gan_nhat")
    if gan is None:
        return _muc("Tin khách gần nhất", CANH_BAO, "chưa có tin khách nào")
    gio = (datetime.now(timezone.utc) - gan).total_seconds() / 3600
    ghi = f"{gio:.0f} giờ trước" if gio >= 1 else f"{gio * 60:.0f} phút trước"
    return _muc("Tin khách gần nhất", TOT, ghi)


async def _kiem_khach_cho_lau() -> dict:
    """
    Có ai đã được chuyển cho người mà vẫn đang ngồi chờ quá lâu không.

    Tám phép kiểm còn lại đều hỏi "hệ thống có sống không". Phép này hỏi
    một câu khác hẳn: "có khách nào đang bị bỏ quên không". Hai câu đó
    không thay thế nhau — hệ thống có thể xanh toàn bộ trong khi bảy người
    ngồi chờ từ tối hôm trước, vì lúc đó không có mã nào đang chạy sai;
    chỉ là không có ai vào trả lời.

    `assist` và `escalated` gộp làm một, đúng như khung trực trên
    dashboard: hai trạng thái khác nhau nhưng CÙNG một việc phải làm —
    một người phải vào trả lời khách.
    """
    # NGOÀI GIỜ TRỰC THÌ IM. Không phải vì khách chờ ban đêm không quan
    # trọng, mà vì báo động lúc 2 giờ sáng cho một việc không ai làm được
    # tới 8 giờ sáng là cách nhanh nhất khiến người ta tắt thông báo — rồi
    # lần hỏng thật tiếp theo không ai đọc. Đúng 8 giờ, phép kiểm này sống
    # lại và báo ngay những người đã chờ suốt đêm.
    if not gio_lam_viec.dang_trong_gio():
        return _muc("Khách chờ người", TOT, "ngoài giờ trực")

    nguong = max(1, int(settings.cho_nguoi_toi_da_phut))
    try:
        row = await db.fetchrow(
            """
            SELECT count(*) AS so, min(updated_at) AS lau_nhat
            FROM conversations
            WHERE status IN ('assist', 'escalated')
              AND updated_at < now() - ($1 || ' minutes')::interval
            """,
            str(nguong),
        ) or {}
    except Exception as exc:  # noqa: BLE001
        return _muc("Khách chờ người", HONG, f"{type(exc).__name__}"[:100])

    so = int(row.get("so") or 0)
    if so == 0:
        return _muc("Khách chờ người", TOT, f"không ai chờ quá {nguong} phút")

    lau = row.get("lau_nhat")
    phut = int((datetime.now(timezone.utc) - lau).total_seconds() / 60) if lau else nguong
    ghi = f"{so} khách chờ quá {nguong} phút — lâu nhất {phut} phút"

    # CẢNH BÁO chứ không HỎNG, và đây là lựa chọn có chủ đích. `hong` kéo
    # trạng thái tổng xuống và trong hệ thống này nghĩa là "không phục vụ
    # được" — nhưng khách chờ lâu thường là do người trực đang bận hoặc
    # đang ngoài giờ, không phải do máy hỏng. Gắn nhãn `hong` cho chuyện
    # bình thường của buổi tối là cách nhanh nhất khiến người ta ngừng đọc
    # báo động.
    return _muc("Khách chờ người", CANH_BAO, ghi, so_khach=so, lau_nhat_phut=phut)


async def _kiem_erp() -> dict:
    """Cổng kho/ERP: đang nối nguồn nào, còn sống không, mạch có mở không.

    VÌ SAO PHẢI CÓ Ở ĐÂY
    --------------------
    Cả cổng ERP ghi `log_event` cho mọi sự cố — ngắt mạch, lệch tồn kho, đơn
    kẹt. Nhưng không màn hình nào của dashboard đọc bảng `events`. Không có
    mục này thì toàn bộ hệ thống báo động đó reo trong một căn phòng không
    ai bước vào.
    """
    from agent.erp import nha_may

    if (settings.erp_loai or "tep").strip().lower() == "tep":
        # Hợp lệ, nhưng KHÔNG được hiện ra như "Tốt" trống trơn: người vận
        # hành sẽ tưởng đã nối ERP trong khi đang đọc một file trên đĩa.
        return _muc("Kho / ERP", CANH_BAO,
                    "Đang đọc tệp catalog.json, CHƯA nối ERP thật. "
                    "Đặt ERP_LOAI=erpnext hoặc odoo rồi chạy "
                    "`python -m scripts.thu_erp`.")

    t0 = time.perf_counter()
    try:
        cong = nha_may.cong()
        song = await cong.suc_khoe()
        tt = cong.trang_thai()
    except Exception as exc:  # noqa: BLE001
        return _muc("Kho / ERP", HONG, f"{type(exc).__name__}: {exc}"[:150])

    ms = int((time.perf_counter() - t0) * 1000)
    nguon = tt.get("nguon", "?")
    if tt.get("mach_mo"):
        # Mạch mở nghĩa là MỌI câu hỏi về giá và tồn đang trả "không biết",
        # và agent đang chuyển người nhiều bất thường.
        return _muc("Kho / ERP", HONG,
                    f"nguồn {nguon} · NGẮT MẠCH đang mở sau "
                    f"{tt.get('hong_lien_tiep')} lần hỏng — giá và tồn kho "
                    "đang trả 'không biết'", latency_ms=ms)
    if not song:
        return _muc("Kho / ERP", HONG,
                    f"nguồn {nguon} · không gọi được ({ms}ms)", latency_ms=ms)
    return _muc("Kho / ERP", TOT,
                f"nguồn {nguon} · phản hồi {ms}ms", latency_ms=ms)


async def _kiem_don_ket_erp() -> dict:
    """Đơn kẹt `cho_dong_bo` quá lâu.

    `cho_dong_bo` nghĩa là khách đã được báo "đã ghi nhận, sẽ có người gọi".
    Nếu không ai gọi vì đơn kẹt thì đó là một lời hứa bị bỏ.
    """
    if not settings.erp_ghi_don:
        return _muc("Đơn chờ đồng bộ ERP", TOT,
                    "ERP_GHI_DON đang tắt — đơn không đi sang ERP")
    try:
        row = await db.fetchrow(
            """
            SELECT count(*) AS n,
                   coalesce(max(EXTRACT(EPOCH FROM (now() - created_at))), 0)
                       AS lau_nhat
            FROM orders WHERE trang_thai = 'cho_dong_bo'
            """
        )
    except Exception as exc:  # noqa: BLE001
        return _muc("Đơn chờ đồng bộ ERP", HONG,
                    f"{type(exc).__name__}: {exc}"[:150])

    n = int(row["n"] or 0)
    phut = int(float(row["lau_nhat"] or 0) // 60)
    if n == 0:
        return _muc("Đơn chờ đồng bộ ERP", TOT, "không đơn nào đang kẹt")
    if phut >= 30:
        return _muc("Đơn chờ đồng bộ ERP", HONG,
                    f"{n} đơn kẹt, đơn lâu nhất {phut} phút — khách đã được "
                    "hứa sẽ có người gọi", so_don=n, phut=phut)
    return _muc("Đơn chờ đồng bộ ERP", CANH_BAO,
                f"{n} đơn đang chờ, lâu nhất {phut} phút", so_don=n)


async def tong_kiem() -> dict:
    """
    Chạy mọi phép kiểm song song. Trả trạng thái tổng + chi tiết từng mục.

    Song song vì tổng thời gian phải đủ ngắn để người vận hành bấm F5 xem
    được — nối tiếp thì riêng phép gọi model đã có thể mất 45 giây.
    """
    t0 = time.perf_counter()
    muc = await asyncio.gather(
        _kiem_db(), _kiem_model(), _kiem_embedding_khop(), _kiem_giong_doc(), _kiem_kenh(),
        _kiem_cong_cong_khai(),
        _kiem_hang_doi_video(), _kiem_sao_luu(), _kiem_kho_anh(),
        _kiem_khach_gan_nhat(), _kiem_khach_cho_lau(),
        _kiem_erp(), _kiem_don_ket_erp(),
        return_exceptions=True,
    )

    sach = []
    for m in muc:
        if isinstance(m, BaseException):
            sach.append(_muc("(phép kiểm lỗi)", HONG, f"{type(m).__name__}: {m}"[:120]))
        else:
            sach.append(m)

    co_hong = any(m["trang_thai"] == HONG for m in sach)
    co_canh = any(m["trang_thai"] == CANH_BAO for m in sach)
    return {
        "trang_thai": HONG if co_hong else (CANH_BAO if co_canh else TOT),
        "kiem_trong_ms": int((time.perf_counter() - t0) * 1000),
        "agent": dict(runtime.STATE),
        "muc": sach,
    }
