"""
Adapter Zalo OA — cổng chính thức, dựng sẵn và TẮT cho tới khi có khoá.

VÌ SAO CÓ FILE NÀY KHI CHƯA NỐI OA
----------------------------------
`ZaloCRMAdapter` điều khiển một nick Zalo CÁ NHÂN. Điều khoản của Zalo không
cho phép việc đó, và cái giá khi bị bắt là khoá nick — mất luôn toàn bộ lịch
sử hội thoại với khách, tức là mất chính tài sản mà hồ sơ khách đang gây
dựng. Đường đúng cho production là Official Account.

Dựng lớp này TRƯỚC khi có khoá, thay vì đợi đến lúc cần, vì hai thứ dưới đây
không bổ sung được về sau mà không viết lại phần trên:

  CỬA SỔ GỬI   OA không cho nhắn tự do bất cứ lúc nào. Ngoài cửa sổ kể từ
               tin cuối của khách thì tin bị từ chối. Toàn bộ luồng
               `handle_inbound` đã hỏi `can_send_now()` trước khi gửi —
               nhưng chỉ vì hàm đó có sẵn trong hợp đồng từ đầu. Kênh nào
               không trả lời được câu hỏi ấy sẽ đẩy `if` vào khắp nơi.

  LÀM MỚI TOKEN  `access_token` của OA sống khoảng một giờ. Một adapter chỉ
               đọc token từ `.env` sẽ chạy đúng trong buổi cài đặt rồi chết
               âm thầm sau bữa trưa — và chết theo kiểu tệ nhất: tin khách
               vẫn vào, agent vẫn soạn, chỉ có câu trả lời là không bao giờ
               tới nơi.

TRẠNG THÁI: CHƯA CHẠY VỚI API THẬT
----------------------------------
Không có khoá OA nên chưa gọi được lần nào. Những chỗ dưới đây viết theo tài
liệu Zalo và **phải đối chiếu lại** khi có tài khoản thật — đừng tin là đúng
chỉ vì test xanh, test ở đây dùng máy chủ giả:

  * tên trường trong payload webhook (`event_name`, `sender.id`, `message`)
  * đường dẫn gửi tin và hình dạng body
  * độ dài cửa sổ gửi — Zalo đã đổi con số này ít nhất một lần, nên nó nằm
    trong cấu hình (`ZALO_OA_CUA_SO_GIO`) chứ không nằm trong mã
  * cách ký webhook

`cau_hinh_du()` trả False khi thiếu khoá, nên registry không bật kênh này và
không có gì chạy nhầm. Muốn bật: điền khoá vào `.env` rồi chạy
`python -m scripts.san_sang`.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import httpx

from agent import db
from agent.channels.base import (ChannelAdapter, Delivery, InboundMessage,
                                 con_trong_cua_so)
from agent.config import settings

# Sự kiện webhook mang tin của KHÁCH. Zalo còn đẩy nhiều loại khác (khách
# theo dõi OA, bỏ theo dõi, đã xem tin...) — không phải tin nhắn, bỏ qua.
SU_KIEN_KHACH = {
    "user_send_text",
    "user_send_image",
    "user_send_file",
    "user_send_sticker",
    "user_send_gif",
    "user_send_link",
    "user_send_audio",
    "user_send_video",
    "user_send_location",
}

# Sự kiện chỉ có tệp đính kèm, không có chữ. TÁCH RIÊNG CÓ CHỦ Ý: lỗi nghiêm
# trọng nhất từng tìm ra trong repo này là bộ đọc webhook lặng lẽ bỏ tin chỉ
# có ảnh — khách gửi ảnh vùng da rồi không ai trả lời, và không có gì báo.
# Danh sách này để `parse()` không bao giờ trả None chỉ vì `text` rỗng.
SU_KIEN_DINH_KEM = SU_KIEN_KHACH - {"user_send_text", "user_send_link"}

# Đổi token sớm hơn hạn một quãng. Làm mới đúng lúc hết hạn là canh một cuộc
# đua mà mình chắc chắn thua: token chết giữa đường bay của request.
_DEM_TRUOC_GIAY = 300


def _doc_dinh_kem(payload: dict) -> list[dict]:
    """
    Ảnh và tệp khách gửi, chuẩn hoá về đúng hình dạng dashboard đang vẽ.

    Giữ nguyên khoá `loai`/`url`/`goc` như adapter Chatwoot. Đây không phải
    trùng lặp tình cờ — dashboard đọc đúng ba khoá đó (`dashboard/app.js`),
    nên kênh nào trả khác là ảnh vỡ trên màn hình người trực.
    """
    ra = []
    for a in ((payload.get("message") or {}).get("attachments") or []):
        if not isinstance(a, dict):
            continue
        tep = a.get("payload") or {}
        url = str(tep.get("url") or tep.get("thumbnail") or "")
        if not url:
            continue
        ra.append({
            "loai": str(a.get("type") or "file"),
            # Ảnh của Zalo nằm trên CDN công khai, không đòi phiên đăng nhập
            # như Chatwoot — nên không cần proxy, dùng thẳng được.
            "url": url,
            "goc": url,
        })
    return ra


class ZaloOAAdapter(ChannelAdapter):
    name = "zalo_oa"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.zalo_oa_api_base.rstrip("/"), timeout=20.0
        )
        # Token nằm trong bộ nhớ tiến trình; bản bền nằm trong CSDL. Giữ
        # cả hai vì mỗi lượt gửi mà hỏi CSDL một lần là công vô ích.
        self._token: str = ""
        self._het_han: float = 0.0

    def cau_hinh_du(self) -> bool:
        return bool(
            settings.zalo_oa_app_id
            and settings.zalo_oa_secret_key
            and (settings.zalo_oa_refresh_token or self._token)
        )

    # ---------------- token ----------------

    async def _lay_token(self) -> str:
        """
        Access token còn sống, làm mới nếu cần.

        REFRESH TOKEN CỦA ZALO XOAY VÒNG: mỗi lần đổi, Zalo trả về một
        refresh token MỚI và vô hiệu cái cũ. Ghi đè lại là bắt buộc — quên
        ghi thì lần làm mới sau dùng token đã chết, và kênh im lặng ngừng
        gửi được. Cái cũ không dùng lại được, kể cả khi khởi động lại app.

        Nên bản bền phải nằm trong CSDL, không nằm trong `.env`: `.env` là
        file người sửa tay, còn thứ này máy phải tự ghi mỗi giờ.
        """
        if self._token and time.time() < self._het_han - _DEM_TRUOC_GIAY:
            return self._token

        refresh = await self._doc_refresh_da_luu() or settings.zalo_oa_refresh_token
        if not refresh:
            return ""

        r = await self._client.post(
            settings.zalo_oa_oauth_url,
            data={
                "app_id": settings.zalo_oa_app_id,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
            headers={"secret_key": settings.zalo_oa_secret_key},
        )
        r.raise_for_status()
        d = r.json()
        token = str(d.get("access_token") or "")
        if not token:
            # Zalo trả 200 kèm thân lỗi. Coi 200 là thành công ở đây nghĩa
            # là ghi một token rỗng đè lên token đang chạy.
            raise RuntimeError(f"Zalo OA không trả access_token: {str(d)[:200]}")

        self._token = token
        self._het_han = time.time() + float(d.get("expires_in") or 3600)
        if (moi := str(d.get("refresh_token") or "")):
            await self._luu_refresh(moi)
        return token

    async def _doc_refresh_da_luu(self) -> str:
        r = await db.fetchrow(
            "SELECT refresh_token FROM zalo_oa_token WHERE app_id = $1",
            settings.zalo_oa_app_id,
        )
        return str(r["refresh_token"]) if r else ""

    async def _luu_refresh(self, token: str) -> None:
        await db.execute(
            """
            INSERT INTO zalo_oa_token (app_id, refresh_token, updated_at)
            VALUES ($1, $2, now())
            ON CONFLICT (app_id) DO UPDATE
                SET refresh_token = EXCLUDED.refresh_token, updated_at = now()
            """,
            settings.zalo_oa_app_id, token,
        )

    # ---------------- vào ----------------

    def parse(self, payload: dict) -> InboundMessage | None:
        """
        Webhook Zalo OA -> InboundMessage.

        KHÔNG lọc theo `text` rỗng. Tin chỉ có ảnh vẫn là tin — xem
        `SU_KIEN_DINH_KEM` ở đầu file để biết vì sao câu này quan trọng.
        """
        su_kien = str(payload.get("event_name") or "")
        if su_kien not in SU_KIEN_KHACH:
            return None

        nguoi = payload.get("sender") or {}
        khach = str(nguoi.get("id") or "")
        if not khach:
            return None

        tin = payload.get("message") or {}
        text = str(tin.get("text") or "").strip()
        dinh_kem = _doc_dinh_kem(payload)
        if not text and not dinh_kem:
            return None      # sự kiện rỗng thật, không phải tin

        # OA không có khái niệm "hội thoại" tách khỏi người gửi: mỗi khách là
        # một luồng. Dùng luôn id khách làm conversation_ref.
        return InboundMessage(
            channel=self.name,
            conversation_ref=khach,
            customer_ref=khach,
            customer_name=str((payload.get("sender") or {}).get("name") or "") or "Khách",
            text=text,
            dedupe_key=f"{self.name}:{tin.get('msg_id') or payload.get('timestamp')}",
            received_at=_thoi_diem(payload.get("timestamp")),
            attachments=dinh_kem,
            meta={"nen_tang": "zalo", "su_kien": su_kien},
        )

    # ---------------- ra ----------------

    async def send_text(self, conversation_ref: str, text: str) -> Delivery:
        if not self.cau_hinh_du():
            return Delivery(False, "Zalo OA chưa cấu hình")
        try:
            token = await self._lay_token()
            if not token:
                return Delivery(False, "không lấy được access_token")
            r = await self._client.post(
                "/message/cs",
                headers={"access_token": token},
                json={
                    "recipient": {"user_id": conversation_ref},
                    "message": {"text": text},
                },
            )
        except (httpx.HTTPError, RuntimeError) as exc:
            return Delivery(False, str(exc)[:200])
        return _doc_ket_qua(r)

    async def send_file(
        self, conversation_ref: str, path: str, caption: str = ""
    ) -> Delivery:
        """
        Gửi ảnh. Zalo OA đòi TẢI LÊN TRƯỚC rồi mới gửi bằng `attachment_id`,
        không nhận đường dẫn cục bộ như Chatwoot.

        Hai bước, và bước một hỏng thì dừng — gửi tiếp bằng một id rỗng chỉ
        tạo thêm một lỗi khó đọc hơn.
        """
        if not self.cau_hinh_du():
            return Delivery(False, "Zalo OA chưa cấu hình")
        if not os.path.exists(path):
            return Delivery(False, f"không thấy file: {path}")
        try:
            token = await self._lay_token()
            if not token:
                return Delivery(False, "không lấy được access_token")

            with open(path, "rb") as fh:
                up = await self._client.post(
                    "/upload/image",
                    headers={"access_token": token},
                    files={"file": (os.path.basename(path), fh)},
                )
            kq_up = _doc_ket_qua(up)
            if not kq_up.ok:
                return Delivery(False, f"tải ảnh lên hỏng: {kq_up.detail}")
            anh_id = ((up.json().get("data") or {}).get("attachment_id") or "")
            if not anh_id:
                return Delivery(False, "Zalo không trả attachment_id")

            r = await self._client.post(
                "/message/cs",
                headers={"access_token": token},
                json={
                    "recipient": {"user_id": conversation_ref},
                    "message": {
                        "text": caption or "",
                        "attachment": {
                            "type": "template",
                            "payload": {
                                "template_type": "media",
                                "elements": [
                                    {"media_type": "image", "attachment_id": anh_id}
                                ],
                            },
                        },
                    },
                },
            )
        except (httpx.HTTPError, RuntimeError, OSError) as exc:
            return Delivery(False, str(exc)[:200])
        return _doc_ket_qua(r)

    # ---------------- luật riêng của kênh ----------------

    async def can_send_now(self, conversation_ref: str) -> bool:
        """
        Còn trong cửa sổ được nhắn tự do không?

        ĐÂY LÀ KHÁC BIỆT LỚN NHẤT so với Zalo cá nhân, và là lý do
        `can_send_now()` có mặt trong hợp đồng ngay từ đầu. Ngoài cửa sổ,
        tin tự do bị Zalo từ chối; muốn liên hệ phải dùng ZNS với mẫu đã
        duyệt — một cơ chế khác hẳn, không phải việc của adapter này.

        Đo từ tin CUỐI CỦA KHÁCH, không phải tin cuối của hội thoại: agent
        tự nhắn thêm không mở lại cửa sổ, nếu không thì chỉ cần agent nói
        chuyện một mình là cửa sổ không bao giờ đóng.

        Không tra được CSDL thì trả False. Chặn nhầm một tin gửi được thì
        người trực thấy nhật ký `escalate.khong_gui_duoc` và nhắn tay; đoán
        bừa là True thì tin bay vào hư không và không ai biết.
        """
        return await con_trong_cua_so(
            self.name, conversation_ref, float(settings.zalo_oa_cua_so_gio or 0)
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _doc_ket_qua(r: httpx.Response) -> Delivery:
    """
    Zalo trả HTTP 200 kèm `error != 0` khi hỏng. Chỉ nhìn mã HTTP là coi
    mọi lỗi nghiệp vụ — hết hạn mức, ngoài cửa sổ, sai user_id — thành
    thành công.
    """
    if r.status_code >= 400:
        return Delivery(False, f"{r.status_code} {r.text[:200]}")
    try:
        d = r.json()
    except ValueError:
        return Delivery(False, f"phản hồi không phải JSON: {r.text[:200]}")
    ma = d.get("error")
    if ma in (0, None):
        return Delivery(True)
    return Delivery(False, f"error={ma} {str(d.get('message') or '')[:180]}")


def _thoi_diem(value) -> datetime:
    """Zalo gửi timestamp bằng MILI giây, dạng chuỗi."""
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
