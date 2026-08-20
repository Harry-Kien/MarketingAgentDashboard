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
from pathlib import Path

from agent import db, runtime
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
    from agent.core import llm

    try:
        r = await asyncio.wait_for(
            llm.complete(
                system=llm.cached_system("Trả lời đúng một chữ: ok"),
                messages=[{"role": "user", "content": "ok?"}],
                model=settings.model_cheap, max_tokens=8, effort="low",
            ),
            timeout=45,
        )
        return _muc("Model ngôn ngữ", TOT,
                    f"{r.model} · {r.latency_ms}ms", latency_ms=r.latency_ms)
    except asyncio.TimeoutError:
        return _muc("Model ngôn ngữ", HONG, "quá 45 giây không trả lời")
    except Exception as exc:  # noqa: BLE001
        loi = str(exc)
        if "429" in loi or "exhaust" in loi.lower():
            return _muc("Model ngôn ngữ", HONG,
                        "HẾT HẠN MỨC — agent không trả lời được khách")
        return _muc("Model ngôn ngữ", HONG, f"{type(exc).__name__}: {loi}"[:150])


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


async def _kiem_kenh() -> dict:
    """Kênh nhận tin. Chưa cấu hình thì là lựa chọn, không phải hỏng."""
    from agent.channels import registry as channels

    bat = []
    if settings.zalocrm_api_key:
        bat.append("zalocrm")
    if settings.chatwoot_base_url and settings.chatwoot_api_token:
        bat.append("chatwoot")
    if not bat:
        return _muc("Kênh nhận tin", CANH_BAO,
                    "chưa nối kênh nào — hệ thống chạy nhưng không có khách vào")

    try:
        tin = await asyncio.wait_for(channels.keo_tin_moi(), timeout=20)
        return _muc("Kênh nhận tin", TOT, f"{', '.join(bat)} · {len(tin)} tin chờ")
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


async def tong_kiem() -> dict:
    """
    Chạy mọi phép kiểm song song. Trả trạng thái tổng + chi tiết từng mục.

    Song song vì tổng thời gian phải đủ ngắn để người vận hành bấm F5 xem
    được — nối tiếp thì riêng phép gọi model đã có thể mất 45 giây.
    """
    t0 = time.perf_counter()
    muc = await asyncio.gather(
        _kiem_db(), _kiem_model(), _kiem_giong_doc(), _kiem_kenh(),
        _kiem_hang_doi_video(), _kiem_sao_luu(), _kiem_kho_anh(),
        _kiem_khach_gan_nhat(),
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
