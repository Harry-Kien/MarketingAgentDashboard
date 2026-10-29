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
import json

import httpx

from . import db, suc_khoe
from .config import settings

# Trạng thái lần kiểm trước. Giữ trong bộ nhớ là đủ: khởi động lại thì coi
# như chưa biết gì, và lần kiểm đầu sẽ báo nếu đang hỏng.
_truoc: str | None = None

# Trạng thái riêng cho việc "có khách đang bị bỏ quên". Vì sao KHÔNG dùng
# chung `_truoc`: xem ghi chú trong `kiem_mot_lan()`.
_cho_truoc: bool = False

# Tên mục do `suc_khoe._kiem_khach_cho_lau()` đặt. Khớp bằng tên thay vì
# theo thứ tự trong danh sách: thêm một phép kiểm nữa vào giữa là thứ tự
# đổi, và một chốt báo động không được phép hỏng vì lý do đó.
MUC_KHACH_CHO = "Khách chờ người"


def _tom_tat(kq: dict) -> str:
    """Một dòng nói rõ hỏng ở đâu, để người đọc biết ngay có phải dậy không."""
    xau = [
        m for m in kq.get("muc", [])
        if m.get("trang_thai") not in ("tot", "khong_dung")
    ]
    if not xau:
        return "Mọi mục bình thường."
    return " · ".join(f"{m['ten']}: {m.get('ghi_chu', '')}"[:90] for m in xau)


def dung_goi_bao_dong(truong: dict, mau: str = "") -> dict:
    """
    Dựng gói tin gửi tới webhook báo động, theo mẫu khai trong cấu hình.

    VÌ SAO CẦN MẪU
    --------------
    Mỗi nơi nhận đòi một dạng khác: chỗ này cần `text`, chỗ kia cần
    `content`, chỗ khác cần thêm định danh phòng chat. Gắn cứng một hãng vào
    đây là nhốt quyết định VẬN HÀNH vào mã — cùng lý do với PublishAdapter,
    và có test canh đúng điều đó.

    Bắt người dùng dựng thêm một dịch vụ trung gian chỉ để đổi tên ba trường
    cũng không đúng: đó là thêm một tiến trình nữa có thể chết, ngay trên
    đường báo động.

    Mẫu là chuỗi JSON có chỗ trống `{muc_do}`, `{tieu_de}`, `{chi_tiet}`,
    `{trang_thai}`. Trung lập với mọi nhà cung cấp.

    HỎNG THÌ RƠI VỀ DẠNG CŨ, KHÔNG NÉM LỖI
    --------------------------------------
    Mẫu gõ sai mà ta ném lỗi thì đúng lúc hệ thống chết cũng là lúc báo động
    chết theo. Gửi sai dạng còn có cơ hội ai đó nhìn thấy; im lặng thì không.
    """
    if not mau.strip():
        return dict(truong)
    try:
        # KHÔNG dùng str.format: mẫu là JSON, mà JSON đầy dấu ngoặc nhọn —
        # `{"chat_id":"1"}` bị format hiểu thành một chỗ trống tên
        # `"chat_id":"1"`. Chỉ thay đúng những khoá mình biết, mọi ngoặc
        # khác để nguyên.
        #
        # Thoát theo chuẩn JSON trước khi chèn: chi tiết báo động có thể
        # chứa dấu nháy kép, xuống dòng, tiếng Việt. Chèn thô là gói tin vỡ
        # và nơi nhận từ chối đúng lúc cần nhất.
        ra = mau
        for khoa, gia_tri in truong.items():
            cho_trong = "{" + str(khoa) + "}"
            if cho_trong in ra:
                an_toan = json.dumps(str(gia_tri), ensure_ascii=False)[1:-1]
                ra = ra.replace(cho_trong, an_toan)
        return json.loads(ra)
    except (ValueError, TypeError) as exc:
        # Mẫu gõ sai KHÔNG được làm mất báo động — xem docstring.
        del exc
        return dict(truong)


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
            await http.post(
                settings.canh_gac_webhook,
                json=dung_goi_bao_dong(
                    {
                        "muc_do": muc_do,
                        "tieu_de": tieu_de,
                        "chi_tiet": chi_tiet,
                        "trang_thai": kq.get("trang_thai"),
                        "muc": kq.get("muc", []),
                    },
                    mau=settings.canh_gac_goi_tin,
                ),
            )
    except httpx.HTTPError as exc:
        # Báo động gửi hỏng thì ghi lại, KHÔNG ném lên — vòng canh gác chết
        # là mất luôn khả năng biết mọi thứ khác đang hỏng.
        await db.log_event("canh_gac.loi_gui", error=str(exc)[:200])


def _muc_khach_cho(kq: dict) -> dict | None:
    for m in kq.get("muc", []):
        if m.get("ten") == MUC_KHACH_CHO:
            return m
    return None


async def bao_dong(chi_tiet: str, *, tieu_de: str = "Cảnh báo hệ thống",
                   muc_do: str = "canh_bao") -> None:
    """
    Cửa CÔNG KHAI để phần khác của hệ thống phát báo động.

    Trước đây chỉ có `_bao` — hàm riêng, bốn tham số, trong đó một tham số là
    dict kết quả của vòng canh gác. Chỗ khác muốn báo động phải hoặc gọi vào
    hàm riêng, hoặc dựng một dict giả cho vừa chữ ký.

    Cả hai cách đều dẫn tới cùng một chỗ: người ta ngại, rồi thôi không báo
    động nữa — và hệ thống mất đi đúng thứ nó cần nhất.
    """
    await _bao(muc_do, tieu_de, chi_tiet, {})


# Giữ tham chiếu tới việc nền: asyncio chỉ giữ tham chiếu YẾU, task không ai
# giữ có thể bị dọn rác giữa chừng — tin báo nhân viên mất mà không lỗi.
_viec_nen: set[asyncio.Task] = set()


async def bao_nhan_vien(tieu_de: str, chi_tiet: str) -> bool:
    """
    Báo NHÂN VIÊN có việc cần người — gửi ra ngoài dashboard. Trả đã gửi chưa.

    VÌ SAO CẦN
    ----------
    Trước bản này, chuyển người trên Zalo, Instagram, WhatsApp, chat web chỉ
    đổi màu một dòng trên dashboard (`bao_chuyen_nguoi` của các kênh ấy
    không làm gì). Không ai mở dashboard thì khách ngồi chờ, và lời hứa "có
    nhân viên hỗ trợ" thành lời nói suông (rà soát 29.10.2026).

    Đi chung đường webhook với báo động (n8n / Telegram / Zalo bot) — một
    chỗ cấu hình cho cửa hàng nhỏ. Đặt BAO_NHAN_VIEN_WEBHOOK khi muốn tin
    khách cần người đi vào nhóm khác với tin máy hỏng.

    KHÔNG gửi tên hay lời khách: tin đi qua bên thứ ba (Telegram…), chỉ cần
    đủ để người trực biết phải mở dashboard. Dữ liệu cá nhân ở lại trong máy.
    """
    if not settings.bao_nhan_vien_chuyen_nguoi:
        return False
    if settings.bao_nhan_vien_webhook:
        url, mau = settings.bao_nhan_vien_webhook, settings.bao_nhan_vien_goi_tin
    else:
        url, mau = settings.canh_gac_webhook, settings.canh_gac_goi_tin
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.post(url, json=dung_goi_bao_dong(
                {"muc_do": "can_nguoi", "tieu_de": tieu_de,
                 "chi_tiet": chi_tiet, "trang_thai": "can_nguoi"}, mau=mau))
            r.raise_for_status()
    except httpx.HTTPError as exc:
        # KHÔNG ghi str(exc): lỗi HTTP của httpx chứa URL, mà URL Telegram
        # chứa token bot — token vào nhật ký là lộ.
        ma = getattr(getattr(exc, "response", None), "status_code", None)
        await db.log_event("bao_nhan_vien.loi_gui", loi=type(exc).__name__,
                           ma_http=ma, tieu_de=tieu_de[:120])
        return False
    return True


def bao_nhan_vien_nen(tieu_de: str, chi_tiet: str) -> None:
    """
    Gửi `bao_nhan_vien` trong nền. Đường xử lý tin khách không được chờ một
    webhook bên ngoài (Telegram chậm 10 giây là khách chờ thêm 10 giây), và
    lỗi gửi không được làm hỏng lượt trả lời.
    """
    try:
        vong = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _chay() -> None:
        try:
            await bao_nhan_vien(tieu_de, chi_tiet)
        except Exception as exc:  # noqa: BLE001 — việc nền: ghi lại, không ném
            import logging

            logging.getLogger("agent.canh_gac").error(
                "Báo nhân viên hỏng: %s", type(exc).__name__)

    t = vong.create_task(_chay())
    _viec_nen.add(t)
    t.add_done_callback(_viec_nen.discard)


async def kiem_mot_lan() -> dict:
    """Kiểm một lượt và báo nếu trạng thái đổi. Trả kết quả chẩn đoán."""
    global _truoc, _cho_truoc
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

    # KHÁCH BỊ BỎ QUÊN — ĐƯỜNG BÁO ĐỘNG RIÊNG
    # ---------------------------------------
    # Phép kiểm này trả `canh_bao`, và luồng ở trên cố tình không báo khi
    # chỉ có cảnh báo. Nếu để nguyên thì nó im lặng mãi mãi — đúng cái lỗ
    # hổng mà nó sinh ra để bịt.
    #
    # Nhưng cũng KHÔNG được nâng nó lên `hong`: `hong` nghĩa là hệ thống
    # không phục vụ được, và nó kéo trạng thái tổng xuống. Khách chờ lâu
    # lúc 9 giờ tối là chuyện bình thường của một tiệm đã đóng cửa, không
    # phải máy hỏng. Gắn nhãn "Hệ thống đang hỏng" cho chuyện đó là cách
    # nhanh nhất khiến người ta tắt thông báo.
    #
    # Nên nó có đường riêng, với trạng thái riêng — và vẫn giữ đúng luật
    # của cả module này: CHỈ BÁO KHI ĐỔI, không báo mỗi lượt kiểm.
    muc = _muc_khach_cho(kq)
    cho_nay = bool(muc and muc.get("trang_thai") == suc_khoe.CANH_BAO)
    if cho_nay and not _cho_truoc:
        await _bao("khach_cho", "Có khách đang chờ người",
                   (muc or {}).get("ghi_chu", ""), kq)
    elif _cho_truoc and not cho_nay:
        await _bao("khach_cho_xong", "Đã xử lý hết khách chờ",
                   muc.get("ghi_chu", "") if muc else "", kq)
    _cho_truoc = cho_nay

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
