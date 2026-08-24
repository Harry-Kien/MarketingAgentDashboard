"""
Adapter Facebook Messenger — nối THẲNG Meta Graph API, không qua Chatwoot.

VÌ SAO CÓ ĐƯỜNG THỨ HAI KHI CHATWOOT ĐÃ LÀM ĐƯỢC MESSENGER
----------------------------------------------------------
Chatwoot gom Messenger, Instagram, WhatsApp, chat web và email về một hộp
thư — tiện, và vẫn là đường đúng khi bạn cần người trực làm việc trong một
giao diện. Nhưng nó kéo theo một ứng dụng Rails, một Postgres và một Redis
nữa phải nuôi, và mọi tin khách đi qua một hệ thống nữa mới tới agent.

Đường thẳng này đổi lại: ít một dịch vụ, ít một chặng, và webhook về đúng
tiến trình đang xử lý. Với cửa hàng chỉ cần Messenger thì đó là khác biệt
giữa nuôi năm container và nuôi hai.

HAI ĐƯỜNG CÙNG TỒN TẠI CÓ CHỦ Ý. Không đường nào thay thế đường nào — chọn
theo việc, và `ChannelAdapter` làm cho lựa chọn ấy không lan ra chỗ khác.

ĐIỀU NÀY *KHÔNG* BỎ QUA ĐƯỢC APP REVIEW CỦA META
------------------------------------------------
Nói rõ để không ai hiểu nhầm: quyền `pages_messaging` phải được Meta duyệt,
dù đi qua Chatwoot hay đi thẳng. Đó là luật của Meta, không phải hệ quả của
kiến trúc. Cái tích hợp thẳng tiết kiệm được là *hạ tầng*, không phải *thủ
tục*.

BỐN CHỖ MESSENGER KHÁC MỌI KÊNH KHÁC TRONG REPO NÀY
---------------------------------------------------
  MỘT POST, NHIỀU TIN   `entry[].messaging[]` — khách gõ ba tin liên tiếp
                        thì cả ba về cùng một request. Đó là lý do hợp đồng
                        có `parse_nhieu()`; dùng `parse()` ở đây là đánh
                        rơi tin thứ hai trở đi trong im lặng.

  TIN VỌNG (echo)       Meta đẩy lại CHÍNH tin mà Page vừa gửi, kèm cờ
                        `is_echo`. Không lọc thì agent đọc câu trả lời của
                        chính nó như tin khách và trả lời tiếp — vòng lặp
                        vô hạn, tính tiền theo mỗi vòng.

  XÁC MINH HAI KIỂU     GET mang `hub.challenge` phải dội lại nguyên văn
                        (Meta dùng để bắt tay lần đầu); POST ký bằng
                        `X-Hub-Signature-256`. Chốt `WEBHOOK_SECRET` chung
                        của repo không áp được vì Meta không cho thêm header
                        tuỳ ý.

  CỬA SỔ 24 GIỜ         Ngoài cửa sổ kể từ tin cuối của khách, tin tự do bị
                        từ chối; muốn liên hệ phải dùng Message Tag hoặc
                        quảng cáo. Xem `con_trong_cua_so()` trong base.

TRẠNG THÁI: CHƯA CHẠY VỚI API THẬT
----------------------------------
Chưa có Page token nên chưa gọi được lần nào. Viết theo tài liệu Graph API
và **phải đối chiếu lại** khi có tài khoản — test ở đây dùng payload giả,
xanh KHÔNG có nghĩa là kênh chạy được. `cau_hinh_du()` trả False khi thiếu
khoá nên registry không bật, không có gì chạy nhầm.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone

import httpx

from agent.channels.base import (ChannelAdapter, Delivery, InboundMessage,
                                 con_trong_cua_so)
from agent.config import settings


# Hộp thư mặc định của Facebook Page. Con số này do Meta đặt và giống nhau
# ở mọi Page trên thế giới — nó KHÔNG phải id của bạn, đừng đổi.
#
# Đây là "địa chỉ" để trao quyền hội thoại cho người thật: sau khi trao,
# nhân viên trả lời trong Page Inbox hoặc Meta Business Suite như bình
# thường, còn app này lùi xuống làm bên nhận phụ.
APP_HOP_THU_PAGE = "263902037430900"


def _doc_dinh_kem(tin: dict) -> list[dict]:
    """
    Ảnh và tệp khách gửi, chuẩn hoá về đúng hình dạng dashboard đang vẽ.

    Giữ khoá `loai`/`url`/`goc` giống Chatwoot và Zalo OA. `dashboard/app.js`
    đọc đúng ba khoá đó — kênh nào trả khác là ảnh vỡ trên màn hình người
    trực, và không có gì báo.
    """
    ra = []
    for a in (tin.get("attachments") or []):
        if not isinstance(a, dict):
            continue
        url = str((a.get("payload") or {}).get("url") or "")
        if not url:
            continue
        ra.append({"loai": str(a.get("type") or "file"), "url": url, "goc": url})
    return ra


def kiem_chu_ky(than: bytes, chu_ky: str) -> bool:
    """
    Xác minh `X-Hub-Signature-256` của Meta.

    PHẢI KÝ TRÊN THÂN THÔ, không phải trên dict đã parse: `json.dumps()` lại
    cho ra chuỗi khác về khoảng trắng và thứ tự khoá, và HMAC sẽ không bao
    giờ khớp. Đây là chỗ mọi hiện thực webhook Meta sai ít nhất một lần.

    Thiếu app secret thì trả False chứ KHÔNG bỏ qua phép kiểm. Bỏ qua nghĩa
    là bất kỳ ai biết địa chỉ webhook đều bơm được tin giả vào hộp thư của
    cửa hàng — và tin giả đó sẽ được agent trả lời như tin thật.
    """
    khoa = settings.messenger_app_secret
    if not khoa or not chu_ky:
        return False
    mong_doi = "sha256=" + hmac.new(
        khoa.encode(), than, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(mong_doi, chu_ky)


def tra_loi_xac_minh(params) -> str | None:
    """
    Bắt tay lần đầu: Meta gọi GET kèm `hub.challenge` và chờ dội lại nguyên văn.

    Trả None khi verify token sai — không dội lại thì Meta báo lỗi cấu hình
    ngay trên màn hình của họ, tức là hỏng ỒN ÀO, đúng thứ ta muốn ở đây.
    """
    if params.get("hub.mode") != "subscribe":
        return None
    mong_doi = settings.messenger_verify_token
    if not mong_doi or params.get("hub.verify_token") != mong_doi:
        return None
    return params.get("hub.challenge")


class MessengerAdapter(ChannelAdapter):
    name = "messenger"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.messenger_api_base.rstrip("/"), timeout=20.0
        )

    def cau_hinh_du(self) -> bool:
        return bool(settings.messenger_page_token and settings.messenger_app_secret)

    # ---------------- vào ----------------

    def parse(self, payload: dict) -> InboundMessage | None:
        """Tin ĐẦU TIÊN trong lô. Luồng thật dùng `parse_nhieu()`."""
        ds = self.parse_nhieu(payload)
        return ds[0] if ds else None

    def parse_nhieu(self, payload: dict) -> list[InboundMessage]:
        """
        Cả lô webhook -> danh sách tin.

        Meta gói `entry[].messaging[]`. Duyệt hết hai tầng; bỏ qua thứ không
        phải tin khách nhưng KHÔNG bỏ qua tin chỉ có ảnh.
        """
        if payload.get("object") != "page":
            return []          # Instagram, WhatsApp đi object khác

        ra: list[InboundMessage] = []
        for entry in (payload.get("entry") or []):
            if not isinstance(entry, dict):
                continue
            for su_kien in (entry.get("messaging") or []):
                if (m := self._mot_tin(su_kien)) is not None:
                    ra.append(m)
            # `standby[]` — tin khách gửi TRONG LÚC người thật đang phụ trách.
            #
            # Không đọc mảng này thì hồ sơ khách đứt một đoạn: suốt thời gian
            # nhân viên trả lời trong Page Inbox, hệ thống không biết khách
            # đã nói gì. Lần sau agent nhận lại việc, nó thiếu đúng khúc giữa
            # — và hỏi lại những điều khách vừa kể cho người kia.
            #
            # Gắn cờ `standby` để `handle_inbound` LƯU mà KHÔNG TRẢ LỜI.
            # Đây là chỗ dễ sai nhất của Handover Protocol: đọc được tin rồi
            # tưởng mình còn quyền, thế là hai giọng cùng nói với một khách.
            for su_kien in (entry.get("standby") or []):
                if (m := self._mot_tin(su_kien)) is not None:
                    m.meta["standby"] = True
                    ra.append(m)
        return ra

    def doc_ban_giao(self, payload: dict) -> list[dict]:
        """
        Sự kiện đổi quyền hội thoại: ai vừa nhận, ai vừa trả.

        Meta gửi ba loại trong `messaging[]`:
            pass_thread_control    có bên trao quyền — nếu `new_owner_app_id`
                                   là ta thì NHÂN VIÊN ĐÃ XONG, agent nhận lại
            take_thread_control    app khác giành quyền
            request_thread_control app phụ xin quyền

        Trả về danh sách `{"khach": id, "loai": ..., "ve_tay_ta": bool}`.
        """
        ra = []
        for entry in (payload.get("entry") or []):
            if not isinstance(entry, dict):
                continue
            for su_kien in (entry.get("messaging") or []):
                if not isinstance(su_kien, dict):
                    continue
                for loai in ("pass_thread_control", "take_thread_control",
                             "request_thread_control"):
                    if (d := su_kien.get(loai)) is None:
                        continue
                    khach = str((su_kien.get("sender") or {}).get("id") or "")
                    if not khach:
                        continue
                    chu_moi = str(d.get("new_owner_app_id") or "")
                    ra.append({
                        "khach": khach,
                        "loai": loai,
                        # So bằng app id CỦA TA, không phải "khác Page Inbox":
                        # một Page có thể gắn nhiều app, và trao cho app thứ
                        # ba không có nghĩa là ta được nhận lại.
                        "ve_tay_ta": bool(
                            loai == "pass_thread_control"
                            and chu_moi
                            and chu_moi == str(settings.messenger_app_id or "")
                        ),
                    })
        return ra

    def _mot_tin(self, su_kien: dict) -> InboundMessage | None:
        if not isinstance(su_kien, dict):
            return None
        tin = su_kien.get("message")
        if not isinstance(tin, dict):
            return None        # delivery / read / postback — không phải tin

        # TIN VỌNG: Meta đẩy lại chính tin Page vừa gửi. Không chặn ở đây thì
        # agent đọc câu trả lời của mình như tin khách, trả lời tiếp, rồi lại
        # nhận vọng — vòng lặp vô hạn và mỗi vòng đều tính tiền.
        if tin.get("is_echo"):
            return None

        khach = str((su_kien.get("sender") or {}).get("id") or "")
        if not khach:
            return None

        text = str(tin.get("text") or "").strip()
        dinh_kem = _doc_dinh_kem(tin)
        # Tin chỉ có ảnh VẪN là tin. Lỗi nghiêm trọng nhất từng tìm ra trong
        # repo này là bộ đọc webhook lặng lẽ bỏ đúng loại tin đó — và người
        # gửi ảnh không kèm chữ thường lại là người cần giúp nhất.
        if not text and not dinh_kem:
            return None

        return InboundMessage(
            channel=self.name,
            conversation_ref=khach,     # Messenger: mỗi khách một luồng
            customer_ref=khach,
            customer_name="Khách",      # Graph API phải gọi riêng mới có tên
            text=text,
            dedupe_key=f"{self.name}:{tin.get('mid') or su_kien.get('timestamp')}",
            received_at=_thoi_diem(su_kien.get("timestamp")),
            attachments=dinh_kem,
            meta={"nen_tang_goc": "facebookpage"},
        )

    # ---------------- ra ----------------

    async def _gui(self, body: dict) -> Delivery:
        try:
            r = await self._client.post(
                "/me/messages",
                params={"access_token": settings.messenger_page_token},
                json=body,
            )
        except httpx.HTTPError as exc:
            return Delivery(False, str(exc)[:200])
        return _doc_ket_qua(r)

    async def send_text(self, conversation_ref: str, text: str) -> Delivery:
        if not self.cau_hinh_du():
            return Delivery(False, "Messenger chưa cấu hình")
        return await self._gui({
            "recipient": {"id": conversation_ref},
            "message": {"text": text},
            # RESPONSE = đang trả lời tin khách vừa gửi. Gắn sai loại là lý
            # do phổ biến nhất khiến Meta từ chối tin trong cửa sổ 24h.
            "messaging_type": "RESPONSE",
        })

    async def send_file(
        self, conversation_ref: str, path: str, caption: str = ""
    ) -> Delivery:
        """
        Gửi ảnh: tải lên lấy `attachment_id`, rồi gắn vào tin.

        Chú thích đi thành MỘT TIN RIÊNG trước ảnh — Messenger không cho
        kèm chữ vào tin ảnh. Gửi ảnh trần không lời thì khách phải tự đoán
        đang xem cái gì.
        """
        if not self.cau_hinh_du():
            return Delivery(False, "Messenger chưa cấu hình")
        if not os.path.exists(path):
            return Delivery(False, f"không thấy file: {path}")

        try:
            with open(path, "rb") as fh:
                up = await self._client.post(
                    "/me/message_attachments",
                    params={"access_token": settings.messenger_page_token},
                    data={"message": '{"attachment":{"type":"image",'
                                     '"payload":{"is_reusable":true}}}'},
                    files={"filedata": (os.path.basename(path), fh)},
                )
        except (httpx.HTTPError, OSError) as exc:
            return Delivery(False, str(exc)[:200])

        kq_up = _doc_ket_qua(up)
        if not kq_up.ok:
            return Delivery(False, f"tải ảnh lên hỏng: {kq_up.detail}")
        try:
            anh_id = str(up.json().get("attachment_id") or "")
        except ValueError:
            anh_id = ""
        if not anh_id:
            return Delivery(False, "Meta không trả attachment_id")

        if caption:
            await self.send_text(conversation_ref, caption)
        return await self._gui({
            "recipient": {"id": conversation_ref},
            "message": {"attachment": {"type": "image",
                                       "payload": {"attachment_id": anh_id}}},
            "messaging_type": "RESPONSE",
        })

    # ---------------- luật riêng của kênh ----------------

    async def bao_dang_go(self, conversation_ref: str, bat: bool) -> None:
        """
        Messenger CÓ dấu 'đang gõ' thật — khác ZaloCRM.

        Đây là chi tiết nhỏ nhưng nó là khác biệt giữa "có người đang trả
        lời" và "màn hình im lặng rồi bỗng hiện ra một đoạn dài".
        """
        if not self.cau_hinh_du():
            return
        await self._gui({
            "recipient": {"id": conversation_ref},
            "sender_action": "typing_on" if bat else "typing_off",
        })

    async def bao_chuyen_nguoi(
        self, conversation_ref: str, ly_do: str, tom_tat: str = ""
    ) -> None:
        """
        Trao quyền hội thoại cho Page Inbox — bàn giao THẬT, do Meta cưỡng chế.

        VÌ SAO KHÔNG CHỈ ĐẶT CỜ TRONG CSDL NHƯ CÁC KÊNH KHÁC
        ----------------------------------------------------
        Đặt `status='escalated'` chỉ làm agent im. Nó KHÔNG giải quyết chiều
        ngược lại: nhân viên mở Facebook Page Inbox trả lời khách trực tiếp,
        mà hệ thống này không hề hay biết. Agent vẫn tưởng mình phụ trách,
        khách nhắn tiếp là nó trả lời tiếp — hai giọng nói cùng lúc với một
        khách hàng, và không có gì trên màn hình nói ra điều đó.

        `pass_thread_control` đẩy ranh giới ấy xuống tầng Meta: sau lời gọi
        này, tin của khách KHÔNG còn về `messaging[]` nữa mà sang
        `standby[]`. Agent im vì nền tảng không cho nó nói, không phải vì
        một cờ trong CSDL của ta còn nhớ.

        Ranh giới cưỡng chế được luôn đáng tin hơn ranh giới tự canh.

        Hỏng thì KHÔNG ném lên trên — `bao_nhan_vien_tiep_quan` trong
        `main.py` đã bọc và ghi `escalate.bao_kenh_that_bai`.
        """
        if not self.cau_hinh_du():
            return
        ghi_chu = f"[Agent chuyển người] {ly_do}"
        if tom_tat:
            ghi_chu += f" | {tom_tat}"
        kq = await self._ban_giao("pass_thread_control", conversation_ref, {
            "target_app_id": APP_HOP_THU_PAGE,
            # Nhân viên tiếp quản đọc được VÌ SAO agent dừng, ngay trong Page
            # Inbox — không phải đọc lại cả hội thoại để đoán.
            "metadata": ghi_chu[:1000],
        })
        if not kq.ok:
            raise RuntimeError(f"trao quyền hội thoại hỏng: {kq.detail}")

    async def nhan_lai_quyen(self, conversation_ref: str) -> Delivery:
        """
        Giành lại quyền hội thoại — dùng khi người trực bấm 'Trả lại cho agent'.

        Cần vì `pass_thread_control` là một chiều: trao xong thì app này nằm
        ngoài cho tới khi có ai trả lại. Không có hàm này thì nút trên
        dashboard đổi được cờ trong CSDL mà tin khách vẫn đi vào `standby[]`
        — agent "bật" mà câm, đúng kiểu hỏng trông như đang chạy.
        """
        if not self.cau_hinh_du():
            return Delivery(False, "Messenger chưa cấu hình")
        return await self._ban_giao("take_thread_control", conversation_ref, {})

    async def _ban_giao(self, hanh_dong: str, khach: str, them: dict) -> Delivery:
        try:
            r = await self._client.post(
                f"/me/{hanh_dong}",
                params={"access_token": settings.messenger_page_token},
                json={"recipient": {"id": khach}, **them},
            )
        except httpx.HTTPError as exc:
            return Delivery(False, str(exc)[:200])
        return _doc_ket_qua(r)

    async def can_send_now(self, conversation_ref: str) -> bool:
        """
        Cửa sổ 24 giờ tiêu chuẩn của Meta, tính từ tin cuối của khách.

        Dùng chung `con_trong_cua_so()` với Zalo OA — cùng một luật, hai con
        số. Viết hai bản là tự tạo lại lỗi hai-nhánh-song-sinh đã phải đi
        sửa ở `agent/main.py`.
        """
        return await con_trong_cua_so(
            self.name, conversation_ref, float(settings.messenger_cua_so_gio or 0)
        )

    async def aclose(self) -> None:
        await self._client.aclose()


def _doc_ket_qua(r: httpx.Response) -> Delivery:
    """
    Graph API báo lỗi bằng khoá `error` trong thân, và không phải lúc nào
    cũng kèm mã HTTP >= 400. Đọc cả hai tầng.
    """
    try:
        d = r.json()
    except ValueError:
        if r.status_code >= 400:
            return Delivery(False, f"{r.status_code} {r.text[:200]}")
        return Delivery(False, f"phản hồi không phải JSON: {r.text[:200]}")

    if (loi := d.get("error")):
        ma = loi.get("code")
        return Delivery(False, f"error={ma} {str(loi.get('message') or '')[:180]}")
    if r.status_code >= 400:
        return Delivery(False, f"{r.status_code} {r.text[:200]}")
    return Delivery(True)


def _thoi_diem(value) -> datetime:
    """Meta gửi timestamp bằng MILI giây."""
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
