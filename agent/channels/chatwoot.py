"""
Adapter Chatwoot — cửa vào đa nền tảng.

VÌ SAO THÊM CHATWOOT KHI ĐÃ CÓ ZALOCRM
--------------------------------------
ZaloCRM chỉ nói chuyện được với Zalo. Chatwoot gom Facebook Messenger,
Instagram DM, WhatsApp, khung chat trên website và email về CÙNG một hộp
thư, với cùng một hình dạng dữ liệu. Thêm một adapter ở đây là thêm bốn
nền tảng cho agent, không phải bốn lần viết lại agent.

Khác biệt kỹ thuật đáng chú ý so với ZaloCRM: Chatwoot KHÔNG có chốt chặn
SSRF, nên webhook về `http://host.docker.internal:8000` chạy được thật.
Nghĩa là kênh này đi bằng WEBHOOK (đẩy, tức thì) trong khi ZaloCRM phải đi
bằng POLLING (kéo, trễ vài giây). Hai cơ chế trái ngược nhau, mà phần trên
— agent, RAG, video, dashboard — không biết và không cần biết. Đó chính là
điều lớp ChannelAdapter được dựng ra để làm.

Lưu ý thực tế: Chatwoot kết nối Facebook/Instagram vẫn cần Meta App Review
như mọi cách khác. Khung chat website và email thì dùng được ngay.

HỢP ĐỒNG API
  Webhook (Chatwoot -> ta), sự kiện message_created:
    {event, message_type: "incoming"|"outgoing", content,
     conversation: {id, ...}, sender: {id, name}, account: {id}}
  Gửi (ta -> Chatwoot):
    POST /api/v1/accounts/{acc}/conversations/{conv}/messages
    body {content, message_type: "outgoing"}
    header api_access_token
"""
from __future__ import annotations

import os
from contextlib import suppress
from datetime import datetime, timezone

import httpx

from agent.channels.base import ChannelAdapter, Delivery, InboundMessage
from agent.config import settings


# Nhãn gắn lên hội thoại cần người xử lý. Đặt một chỗ để trưởng nhóm lọc
# được, và để đổi tên không phải đi tìm khắp nơi.
NHAN_CHO_NGUOI = "can-nguoi-ho-tro"


def _doc_dinh_kem(payload: dict) -> list[dict]:
    """
    Ảnh và file khách gửi kèm.

    ĐƯỜNG DẪN ĐI QUA PROXY, KHÔNG TRỎ THẲNG VÀO CHATWOOT
    ----------------------------------------------------
    Chatwoot trả `data_url` trỏ vào chính nó (`http://localhost:3200/...`),
    và đường đó đòi phiên đăng nhập CỦA CHATWOOT. Nhét thẳng vào dashboard
    thì người trực thấy toàn ô ảnh vỡ, trừ khi họ tình cờ cũng đang đăng
    nhập Chatwoot ở tab khác.

    Đổi sang đường proxy `/tich-hop/chatwoot/...` thì ảnh đi qua phiên
    dashboard — một lần đăng nhập, xem được mọi thứ.
    """
    ra = []
    for a in payload.get("attachments") or []:
        if not isinstance(a, dict):
            continue
        url = str(a.get("data_url") or a.get("thumb_url") or "")
        if not url:
            continue
        # Chỉ giữ phần đường dẫn; phần gốc do lớp proxy quyết định.
        duong = url.split("://", 1)[-1]
        duong = duong[duong.index("/"):] if "/" in duong else "/"
        ra.append({
            "loai": str(a.get("file_type") or "file"),
            "url": f"/tich-hop/chatwoot{duong}",
            "goc": url,
        })
    return ra


class ChatwootAdapter(ChannelAdapter):
    name = "chatwoot"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.chatwoot_base_url.rstrip("/"),
            headers={"api_access_token": settings.chatwoot_api_token},
            timeout=20.0,
        )

    def cau_hinh_du(self) -> bool:
        return bool(settings.chatwoot_base_url and settings.chatwoot_api_token
                    and settings.chatwoot_account_id)

    # ---------------- vào ----------------

    def parse(self, payload: dict) -> InboundMessage | None:
        """
        Chatwoot bắn nhiều loại sự kiện về cùng một URL. Chỉ nhận tin nhắn
        ĐẾN từ khách — bỏ qua tin đi (chính ta vừa gửi, nếu không sẽ tự trả
        lời chính mình thành vòng lặp vô tận) và các sự kiện vòng đời khác.
        """
        if payload.get("event") != "message_created":
            return None
        if payload.get("message_type") != "incoming":
            return None

        # ẢNH VÀ FILE — TỪNG BỊ BỎ HẲN Ở ĐÂY
        # -----------------------------------
        # Bản cũ: `if not text.strip(): return None`, kèm chú thích "ảnh,
        # file, tin hệ thống — chưa xử lý". Hậu quả không phải "chưa xử lý"
        # mà là BIẾN MẤT: khách gửi ảnh vùng da đang nổi mụn, không kèm
        # chữ nào, và tin đó không tạo hội thoại, không vào CSDL, không ai
        # trong hệ thống biết nó từng tồn tại. Khách ngồi chờ một câu trả
        # lời sẽ không bao giờ tới.
        #
        # Trớ trêu là đúng những khách cần giúp nhất lại gửi kiểu đó —
        # người ta chụp chỗ da có vấn đề thay vì tả bằng lời.
        anh = _doc_dinh_kem(payload)
        text = payload.get("content")
        text = text.strip() if isinstance(text, str) else ""
        if not text and not anh:
            return None      # tin hệ thống thật sự rỗng — bỏ đúng

        conv = payload.get("conversation") or {}
        conv_id = str(conv.get("id") or "")
        if not conv_id:
            return None

        sender = payload.get("sender") or {}
        # Nền tảng gốc nằm trong conversation.channel, ví dụ
        # "Channel::FacebookPage". Giữ lại để dashboard gắn đúng huy hiệu.
        goc = str(conv.get("channel") or "").replace("Channel::", "") or "Chatwoot"

        return InboundMessage(
            channel=self.name,
            conversation_ref=conv_id,
            customer_ref=str(sender.get("id") or conv_id),
            customer_name=str(sender.get("name") or "Khách"),
            text=text,
            dedupe_key=f"{self.name}:{payload.get('id')}",
            received_at=_thoi_diem(payload.get("created_at")),
            attachments=anh,
            meta={"nen_tang_goc": goc},
        )

    async def fetch_new(self, per_conversation: int = 8) -> list[InboundMessage]:
        """Chatwoot đẩy bằng webhook, không cần kéo."""
        return []

    # ---------------- ra ----------------

    async def send_text(self, conversation_ref: str, text: str) -> Delivery:
        if not self.cau_hinh_du():
            return Delivery(False, "Chưa cấu hình CHATWOOT_* trong .env")
        try:
            r = await self._client.post(
                f"/api/v1/accounts/{settings.chatwoot_account_id}"
                f"/conversations/{conversation_ref}/messages",
                json={"content": text, "message_type": "outgoing"},
            )
        except httpx.HTTPError as exc:
            return Delivery(False, str(exc)[:200])
        if r.status_code < 400:
            return Delivery(True)
        return Delivery(False, f"{r.status_code} {r.text[:200]}")

    async def send_file(
        self, conversation_ref: str, path: str, caption: str = ""
    ) -> Delivery:
        """Chatwoot nhận file qua multipart, khác hẳn ZaloCRM chỉ có văn bản."""
        if not os.path.exists(path):
            return Delivery(False, f"không thấy file: {path}")
        try:
            with open(path, "rb") as fh:
                r = await self._client.post(
                    f"/api/v1/accounts/{settings.chatwoot_account_id}"
                    f"/conversations/{conversation_ref}/messages",
                    data={"content": caption, "message_type": "outgoing"},
                    files={"attachments[]": (os.path.basename(path), fh)},
                )
        except httpx.HTTPError as exc:
            return Delivery(False, str(exc)[:200])
        if r.status_code < 400:
            return Delivery(True)
        return Delivery(False, f"{r.status_code} {r.text[:200]}")

    # ---------------- bàn giao cho người ----------------

    async def bao_dang_go(self, conversation_ref: str, bat: bool) -> None:
        if not self.cau_hinh_du():
            return
        with suppress(httpx.HTTPError):
            await self._client.post(
                f"/api/v1/accounts/{settings.chatwoot_account_id}"
                f"/conversations/{conversation_ref}/toggle_typing_status",
                json={"typing_status": "on" if bat else "off"},
            )

    async def bao_chuyen_nguoi(
        self, conversation_ref: str, ly_do: str, tom_tat: str = ""
    ) -> None:
        """
        Bàn giao nhìn thấy được: ghi chú nội bộ, gắn nhãn, mở lại hội thoại.

        Ba việc, mỗi việc phục vụ một người khác nhau:

          ghi chú nội bộ  nhân viên tiếp quản đọc được VÌ SAO agent dừng,
                          không phải đọc lại cả hội thoại để đoán. Ghi chú
                          `private` nên khách không thấy.
          nhãn            trưởng nhóm lọc được hàng chờ trong hộp thư
          mở lại          Chatwoot tự đóng hội thoại khi agent trả lời xong;
                          không mở lại thì nó nằm ở tab "đã xử lý" và không
                          ai ngó tới

        Cố ý KHÔNG tự gán cho một nhân viên cụ thể: gán sai người thì việc
        nằm im trong hàng của người đang nghỉ. Để hàng chờ chung, ai rảnh
        nhận — đó là cách một tổ chăm sóc khách hàng thật vận hành.
        """
        if not self.cau_hinh_du():
            return
        goc = f"/api/v1/accounts/{settings.chatwoot_account_id}/conversations/{conversation_ref}"

        ghi_chu = f"[Agent chuyển người] {ly_do}"
        if tom_tat:
            ghi_chu += f"\n\nTóm tắt: {tom_tat}"

        with suppress(httpx.HTTPError):
            await self._client.post(
                f"{goc}/messages",
                json={"content": ghi_chu, "message_type": "outgoing", "private": True},
            )
        with suppress(httpx.HTTPError):
            await self._client.post(f"{goc}/labels", json={"labels": [NHAN_CHO_NGUOI]})
        with suppress(httpx.HTTPError):
            await self._client.post(f"{goc}/toggle_status", json={"status": "open"})

    async def aclose(self) -> None:
        await self._client.aclose()


def _thoi_diem(value) -> datetime:
    if isinstance(value, (int, float)):      # Chatwoot trả epoch giây
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
