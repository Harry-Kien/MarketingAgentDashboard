"""
Ranh giới kênh — mảnh kiến trúc quan trọng nhất của hệ thống.

Mọi thứ phía trên lớp này (agent, RAG, video, dashboard) KHÔNG được biết
mình đang chạy trên Zalo cá nhân hay Zalo OA. Chuyển giai đoạn 1 -> 2
chỉ là viết thêm một lớp con, không đụng phần còn lại.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid5


LEGACY_ACCOUNT_NAMESPACE = UUID("d5a0f4ad-cb42-4a70-a035-c1249fc71f78")


def legacy_account_id(channel: str) -> UUID:
    """UUID ổn định, trùng với backfill SQL cho connector giai đoạn cũ."""
    return uuid5(LEGACY_ACCOUNT_NAMESPACE, f"legacy:{channel}")


@dataclass(slots=True)
class InboundMessage:
    """Tin nhắn đã chuẩn hoá, không còn dấu vết của kênh gốc."""

    account_id: UUID                 # tài khoản nguồn để reply đúng nick
    channel: str
    conversation_ref: str          # id hội thoại phía kênh
    customer_ref: str              # id khách phía kênh
    customer_name: str
    text: str
    dedupe_key: str                # để chống xử lý trùng
    received_at: datetime
    attachments: list[dict] = field(default_factory=list)
    # Thông tin riêng của kênh mà lớp trên KHÔNG được phụ thuộc vào — chỉ
    # dùng để hiển thị. Ví dụ Chatwoot cho biết tin tới từ Facebook hay
    # Instagram; agent trả lời y hệt nhau, chỉ dashboard gắn huy hiệu khác.
    meta: dict = field(default_factory=dict)


@dataclass(slots=True)
class Delivery:
    ok: bool
    detail: str = ""
    provider_message_id: str = ""


@dataclass(frozen=True, slots=True)
class ConnectionCheck:
    ok: bool
    code: str
    external_account_id: str | None = None
    detail: dict = field(default_factory=dict)


class ChannelAdapter(ABC):
    """Hợp đồng mà mọi kênh phải tuân thủ."""

    name: str = "base"

    def __init__(self, *, account_id: UUID | None = None) -> None:
        self.account_id = account_id or legacy_account_id(self.name)

    @abstractmethod
    def parse(self, payload: dict) -> InboundMessage | None:
        """Chuyển payload webhook thô thành InboundMessage. None = bỏ qua."""

    def parse_nhieu(self, payload: dict) -> list[InboundMessage]:
        """
        MỘT payload webhook có thể chứa NHIỀU tin. Trả về hết.

        VÌ SAO PHẢI CÓ, KHI ĐÃ CÓ `parse()`
        -----------------------------------
        ZaloCRM và Chatwoot đẩy mỗi lần một tin, nên `parse()` trả một
        `InboundMessage` là đủ. Meta thì KHÔNG: một POST của Messenger mang
        `entry[]`, mỗi entry mang `messaging[]` — khách gõ ba tin liên tiếp
        thì cả ba về trong cùng một request.

        Ép hình dạng đó vào một hàm trả về đúng một tin nghĩa là hai tin sau
        BIẾN MẤT: không lỗi, không nhật ký, không ai biết. Đúng họ với lỗi
        bộ đọc webhook từng bỏ tin chỉ có ảnh.

        Mặc định bọc `parse()` để hai kênh cũ không phải sửa gì. Kênh nào
        gộp lô thì ghi đè.
        """
        m = self.parse(payload)
        return [m] if m else []

    @abstractmethod
    async def send_text(self, conversation_ref: str, text: str) -> Delivery: ...

    @abstractmethod
    async def send_file(
        self, conversation_ref: str, path: str, caption: str = ""
    ) -> Delivery: ...

    async def fetch_new(self, per_conversation: int = 8) -> list[InboundMessage]:
        """
        Kéo tin mới về. Kênh đi bằng webhook thì để nguyên mặc định này.

        Có cả hai cơ chế vì hai kênh thật đang chạy ngược nhau: ZaloCRM bị
        chốt SSRF chặn nên phải kéo, Chatwoot đẩy được nên dùng webhook.
        """
        return []

    async def verify_connection(self) -> ConnectionCheck:
        """Probe không gửi tin; connector phải override để được kích hoạt."""
        return ConnectionCheck(False, "provider.verification_not_supported")

    async def bao_dang_go(self, conversation_ref: str, bat: bool) -> None:
        """
        Bật/tắt dấu hiệu "đang gõ" phía kênh.

        Kênh nào không có thì để nguyên mặc định. Đây là chi tiết nhỏ nhưng
        nó là khác biệt giữa "có người đang trả lời" và "màn hình im lặng
        rồi bỗng hiện ra một đoạn dài".
        """
        return None

    async def bao_chuyen_nguoi(
        self, conversation_ref: str, ly_do: str, tom_tat: str = ""
    ) -> None:
        """
        Báo cho kênh biết hội thoại này cần người tiếp quản.

        VÌ SAO PHẢI CÓ: agent chuyển người mà chỉ ghi vào CSDL của mình thì
        nhân viên đang làm việc trong hộp thư của kênh KHÔNG THẤY GÌ. Hội
        thoại trông như đã xử lý xong, khách ngồi chờ, và không ai biết.
        Bàn giao chỉ là bàn giao khi bên nhận nhìn thấy.

        Kênh nào không hỗ trợ thì để nguyên mặc định — ZaloCRM là ví dụ,
        Public API của nó không có endpoint nào làm việc này.
        """
        return None

    async def aclose(self) -> None:
        """
        Đóng tài nguyên (client HTTP) lúc tắt ứng dụng.

        Nằm trong hợp đồng vì `registry.dong_tat_ca()` gọi nó cho MỌI
        adapter trong cache mà không phòng bị. Bảy adapter hiện có đều tự
        khai, nên chưa nổ; một adapter mới quên là AttributeError đúng lúc
        shutdown — và lỗi lúc shutdown là thứ không ai đọc.
        """
        return None

    async def can_send_now(self, conversation_ref: str) -> bool:
        """
        Kênh có cho phép gửi chủ động lúc này không?

        Zalo cá nhân: luôn True.
        Zalo OA / Messenger: chỉ True trong cửa sổ kể từ tin cuối của khách;
        ngoài cửa sổ phải dùng mẫu đã duyệt (ZNS, hoặc Message Tag của Meta).
        Toàn bộ phần trên chỉ cần hỏi hàm này, không cần biết luật của kênh.
        """
        return True


async def con_trong_cua_so(
    channel: str,
    conversation_ref: str,
    gio: float,
    *,
    account_id: UUID | None = None,
) -> bool:
    """
    Tin cuối CỦA KHÁCH còn nằm trong `gio` giờ trở lại đây không?

    MỘT BẢN DÙNG CHUNG CHO MỌI KÊNH CÓ CỬA SỔ. Zalo OA và Messenger áp
    cùng một luật với hai con số khác nhau (7 ngày và 24 giờ). Viết hai
    bản là tạo lại đúng lỗi đã phải đi sửa ở `agent/main.py`: hai bản sao
    của một việc, rồi bản ít người đọc hơn mục đi.

    BA QUYẾT ĐỊNH NẰM TRONG HÀM NÀY, VÀ CẢ BA ĐỀU CÓ THỂ SAI THEO KIỂU IM LẶNG:

    1. Đo từ tin của KHÁCH, không phải tin cuối hội thoại. Nếu không thì
       agent tự nhắn thêm là cửa sổ không bao giờ đóng — và tin thứ hai
       trở đi bị nền tảng từ chối.
    2. Chưa có tin nào của khách = chưa có cửa sổ nào mở, trả False.
    3. CSDL hỏng thì trả False, không đoán bừa True. Chặn nhầm thì người
       trực thấy `escalate.khong_gui_duoc` trong nhật ký và nhắn tay; đoán
       bừa thì tin bay vào hư không và không ai biết.
    """
    if gio <= 0:
        return True          # cấu hình tắt phép kiểm — chỉ dùng khi thử
    from agent import db
    try:
        r = await db.fetchrow(
            """
            SELECT max(m.created_at) AS lan_cuoi
            FROM messages m JOIN conversations c ON c.id = m.conversation_id
            WHERE c.account_id = $1 AND c.external_id = $2
              AND m.role = 'customer'
            """,
            account_id or legacy_account_id(channel),
            conversation_ref,
        )
    except Exception:  # noqa: BLE001 — CSDL hỏng thì im lặng an toàn hơn đoán
        return False
    lan_cuoi = r["lan_cuoi"] if r else None
    if lan_cuoi is None:
        return False
    return datetime.now(timezone.utc) - lan_cuoi < timedelta(hours=gio)
