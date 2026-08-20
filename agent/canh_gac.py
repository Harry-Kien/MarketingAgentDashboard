"""
Canh gác — hỏi sức khoẻ đều đặn và BÁO khi hỏng.

VẤN ĐỀ
------
`agent/suc_khoe.py` chẩn đoán được chín thứ, nhưng chỉ khi có người mở
dashboard ra xem. Agent hỏng lúc 2 giờ sáng thì tới sáng mới biết, và
trong khoảng đó khách nhắn vào không ai trả lời.

BÁO KHI ĐỔI TRẠNG THÁI, KHÔNG BÁO MỖI LẦN KIỂM
----------------------------------------------
Báo mỗi 5 phút khi đang hỏng thì sau nửa tiếng người ta tắt thông báo, và
lần hỏng thật tiếp theo không ai đọc. Chỉ báo khi trạng thái ĐỔI:

    tốt -> hỏng    báo động
    hỏng -> tốt    báo đã bình thường trở lại
    hỏng -> hỏng   im lặng

Báo phục hồi quan trọng ngang báo động: không có nó thì người trực không
biết khi nào được đi ngủ.

GIỚI HẠN PHẢI NÓI RÕ
--------------------
Lớp này chạy TRONG tiến trình agent. Nó phát hiện được suy giảm — model
chết, kênh mất kết nối, sao lưu cũ — nhưng KHÔNG phát hiện được chính tiến
trình chết, vì lúc đó nó cũng chết theo.

Muốn bắt cả trường hợp đó thì cần một tiến trình BÊN NGOÀI:
`scripts/canh_gac_ngoai.py`, chạy bằng Task Scheduler hoặc cron.
"""
from __future__ import annotations

import asyncio

import httpx

from . import db, suc_khoe
from .config import settings

# Trạng thái lần kiểm trước. Giữ trong bộ nhớ là đủ: khởi động lại thì coi
# như chưa biết gì, và lần kiểm đầu sẽ báo nếu đang hỏng.
_truoc: str | None = None


def _tom_tat(kq: dict) -> str:
    """Một dòng nói rõ hỏng ở đâu, để người đọc biết ngay có phải dậy không."""
    xau = [
        m for m in kq.get("muc", [])
        if m.get("trang_thai") not in ("tot", "khong_dung")
    ]
    if not xau:
        return "Mọi mục bình thường."
    return " · ".join(f"{m['ten']}: {m.get('ghi_chu', '')}"[:90] for m in xau)


async def _bao(muc_do: str, tieu_de: str, chi_tiet: str, kq: dict) -> None:
    """
    Gửi báo động. Luôn ghi nhật ký; gửi ra ngoài nếu có cấu hình.

    Đi qua một webhook chứ không gửi thẳng Zalo hay email: nơi nhận là việc
    của doanh nghiệp, và n8n đã chạy sẵn để định tuyến đi đâu tuỳ ý. Cùng
    lý do với PublishAdapter — không nhốt một quyết định vận hành vào mã.
    """
    await db.log_event(
        "canh_gac", actor="he_thong",
        muc_do=muc_do, tieu_de=tieu_de, chi_tiet=chi_tiet[:400],
        trang_thai=kq.get("trang_thai"),
    )
    if not settings.canh_gac_webhook:
        return
    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            await http.post(settings.canh_gac_webhook, json={
                "muc_do": muc_do,
                "tieu_de": tieu_de,
                "chi_tiet": chi_tiet,
                "trang_thai": kq.get("trang_thai"),
                "muc": kq.get("muc", []),
            })
    except httpx.HTTPError as exc:
        # Báo động gửi hỏng thì ghi lại, KHÔNG ném lên — vòng canh gác chết
        # là mất luôn khả năng biết mọi thứ khác đang hỏng.
        await db.log_event("canh_gac.loi_gui", error=str(exc)[:200])


async def kiem_mot_lan() -> dict:
    """Kiểm một lượt và báo nếu trạng thái đổi. Trả kết quả chẩn đoán."""
    global _truoc
    kq = await suc_khoe.tong_kiem()
    nay = kq.get("trang_thai", "khong_ro")

    # "canh_bao" chưa phải hỏng — không đánh thức ai lúc nửa đêm vì nó.
    hong_nay = nay == "hong"
    hong_truoc = _truoc == "hong"

    if hong_nay and not hong_truoc:
        await _bao("hong", "Hệ thống đang hỏng", _tom_tat(kq), kq)
    elif hong_truoc and not hong_nay:
        await _bao("phuc_hoi", "Đã bình thường trở lại", _tom_tat(kq), kq)

    _truoc = nay
    return kq


async def vong_canh_gac() -> None:
    """Chạy nền suốt vòng đời app."""
    # Chờ một nhịp trước khi kiểm lần đầu: lúc mới khởi động, kênh và hàng
    # đợi chưa kịp ổn định, kiểm ngay sẽ báo động giả.
    await asyncio.sleep(60)
    while True:
        try:
            if settings.canh_gac_bat:
                await kiem_mot_lan()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await db.log_event(
                "canh_gac.loi", error=f"{type(exc).__name__}: {exc}"[:200]
            )
        await asyncio.sleep(max(60, settings.canh_gac_moi_giay))
