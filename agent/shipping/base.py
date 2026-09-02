"""
<<<<<<< HEAD
Giao diện cơ sở cho mọi đơn vị vận chuyển (GHN, GHTK, ViettelPost, Mock).
=======
Hợp đồng chung cho mọi đơn vị vận chuyển (GHN, GHTK, Viettel Post, Mock).

Lớp AI và dashboard không cần biết đang nói chuyện với hãng nào.

VÌ SAO CHỈ BỐN TRẠNG THÁI
-------------------------
Mỗi hãng có cả chục mã riêng: đã lấy hàng, đang trung chuyển, đang giao,
giao không thành, lưu kho, chờ xử lý... Đưa hết vào hệ thống là bắt dashboard,
agent và người trực học từ vựng của từng hãng.

Bốn trạng thái là đủ để trả lời câu khách hỏi, và không phụ thuộc hãng nào.
Chúng khai ở `models.InternalShippingStatus`.
>>>>>>> origin/main
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import (
    CreateWaybillRequest,
    CreateWaybillResult,
    InternalShippingStatus,
    TrackingResult,
    WebhookEventResult,
)

<<<<<<< HEAD
=======
# Bảng mã của các hãng -> trạng thái nội bộ. KHỚP CHÍNH XÁC, không khớp
# chuỗi con.
#
# Khớp chuỗi con nghe linh hoạt hơn nhưng sai ở đúng chỗ nguy hiểm nhất:
# "return_transporting" chứa "return", nên hàng MỚI TRÊN ĐƯỜNG quay về sẽ bị
# đọc thành ĐÃ VỀ KHO. Xem chú thích RETURNED bên dưới.
#
# Mã lạ rơi ra ngoài bảng này -> `None` -> người xem. Đó là chủ ý.
_BANG_MA: dict[str, InternalShippingStatus] = {}


def _nap(trang_thai: InternalShippingStatus, *ma: str) -> None:
    for m in ma:
        _BANG_MA[m] = trang_thai


# Đang đi — hàng vẫn đang trên đường tới khách.
_nap(InternalShippingStatus.DELIVERING,
     "ready_to_pick", "picking", "picked", "pickup", "money_collect_picking",
     "storing", "transporting", "sorting", "delivering", "in_transit",
     "dang_giao", "lay_hang", "dang_lay_hang")

# Đã tới tay khách.
_nap(InternalShippingStatus.DELIVERED,
     "delivered", "delivery_success", "success", "finish", "completed",
     "da_giao", "giao_thanh_cong", "thanh_cong")

# CHỈ những mã nghĩa là HÀNG ĐÃ VỀ TỚI KHO mới nằm ở đây.
#
# Trạng thái này KÍCH HOẠT HOÀN KHO — hệ thống cộng hàng trở lại số tồn. Xếp
# nhầm một mã vào đây là kho báo có hàng trong khi kệ trống, rồi bán tiếp cái
# không tồn tại.
#
# Vì thế `lost`, `damage`, `return_transporting`, `waiting_to_return` KHÔNG
# nằm ở đây: hàng mất, hàng vỡ, hàng còn trên xe — không cái nào đang nằm
# trên kệ. Bản của cộng sự xếp `damage` và `lost` vào RETURNED.
_nap(InternalShippingStatus.RETURNED,
     "returned", "return_complete", "da_hoan", "hoan_ve", "da_ve_kho")

# Cần người xử lý: chưa giao được, hoặc hàng đang trên đường về, hoặc mất.
# Không tự động làm gì với kho — người kiểm rồi mới quyết.
_nap(InternalShippingStatus.DELIVERY_FAILED,
     "delivery_fail", "delivery_failed", "failed", "fail", "exception",
     "cancel", "cancelled", "damage", "lost", "return_fail",
     "waiting_to_return", "return", "returning", "return_transporting",
     "return_sorting", "khach_hen_lai", "that_bai", "khong_giao_duoc")


def anh_xa_trang_thai(ma_hang: str) -> tuple[InternalShippingStatus | None, str]:
    """
    Mã trạng thái của hãng -> (trạng thái nội bộ, mã gốc).

    MÃ LẠ KHÔNG BỊ NUỐT IM LẶNG — TRẢ None, KHÔNG ĐOÁN
    ---------------------------------------------------
    Bản của cộng sự trả `DELIVERING` cho mọi mã không nhận ra. Nghĩa là một
    kiện `lost` hoặc một mã GHN vừa thêm sẽ hiện "đang giao" mãi mãi: khách
    hỏi "đơn tới đâu rồi", agent trả lời "đang giao" cho kiện hàng đã mất, và
    không gì trong hệ thống biết mình đang nói sai.

    Trả `None` buộc chỗ gọi phải quyết: giữ nguyên trạng thái cũ, ghi nhật ký
    cho người xem, và KHÔNG nói bừa với khách.

    Đây là bài học đã trả giá ở lớp outbox trong chính dự án này: một trạng
    thái không ánh xạ được đã làm job kẹt vĩnh viễn mà lý do thật bị rollback
    mất.

    Giữ mã gốc để người vận hành đọc được hãng đang nói gì, và để bổ sung vào
    `_BANG_MA` khi thấy nó lặp lại.
    """
    thap = str(ma_hang or "").strip().lower()
    return _BANG_MA.get(thap), str(ma_hang or "")

>>>>>>> origin/main

class BaseShippingProvider(ABC):
    """
    Hợp đồng trừu tượng cho đối tác vận chuyển.
<<<<<<< HEAD
    Mọi hãng (GHN, GHTK, Viettel Post) đều phải hiện thực đủ 4 phương thức này.
=======

    Mọi hãng đều phải hiện thực đủ các phương thức này.
>>>>>>> origin/main
    """

    @property
    @abstractmethod
    def code(self) -> str:
        """Mã định danh của hãng (ví dụ: 'ghn', 'ghtk', 'mock')."""
<<<<<<< HEAD
        ...
=======
>>>>>>> origin/main

    @property
    @abstractmethod
    def name(self) -> str:
        """Tên hiển thị (ví dụ: 'Giao Hàng Nhanh')."""
<<<<<<< HEAD
        ...

    @abstractmethod
    async def tao_van_don(self, req: CreateWaybillRequest) -> CreateWaybillResult:
        """Gọi API hãng để tạo vận đơn mới và nhận mã tracking."""
        ...

    @abstractmethod
    async def tra_cuu(self, ma_van_don: str) -> TrackingResult:
        """Tra cứu trạng thái và lộ trình thời gian thực theo mã vận đơn."""
        ...
=======

    @abstractmethod
    async def tao_van_don(self, req: CreateWaybillRequest) -> CreateWaybillResult:
        """
        Gọi API hãng tạo vận đơn mới.

        HÀNH ĐỘNG KHÔNG ĐẢO NGƯỢC: tốn phí ship, hàng rời kho, huỷ phải gọi
        điện. Mọi chốt kiểm nằm ở `service.tao_van_don_cho_don`, không nằm ở
        adapter — adapter chỉ biết nói chuyện với hãng.
        """

    @abstractmethod
    async def tra_cuu(self, ma_van_don: str) -> TrackingResult:
        """Tra trạng thái và lộ trình theo mã vận đơn."""
>>>>>>> origin/main

    @abstractmethod
    def parse_webhook(
        self, body: dict[str, Any], headers: dict[str, Any]
    ) -> WebhookEventResult:
        """
<<<<<<< HEAD
        Xác thực chữ ký và phân tích payload webhook từ hãng gửi về.
        Ánh xạ trạng thái riêng của hãng về 4 trạng thái nội bộ.
        """
        ...

    @abstractmethod
    def map_status(self, carrier_status: str) -> InternalShippingStatus:
        """Ánh xạ trạng thái chi tiết của hãng về 4 trạng thái cốt lõi."""
        ...
=======
        Đọc webhook của hãng.

        Xác thực KHÔNG làm ở đây: nó là việc của lớp HTTP, và làm ở đây thì
        mỗi hãng lại tự nghĩ ra một kiểu — đúng cách một lỗ hổng ra đời.
        Xem `service.kiem_bi_mat_webhook`.
        """

    def map_status(self, carrier_status: str) -> InternalShippingStatus | None:
        """
        Mặc định dùng bộ ánh xạ chung. Ghi đè khi hãng có mã đặc thù.

        Trả `None` nghĩa là KHÔNG NHẬN RA — chỗ gọi phải xử lý, không được
        coi như "đang giao".
        """
        trang_thai, _goc = anh_xa_trang_thai(carrier_status)
        return trang_thai

    async def huy_van_don(self, ma_van_don: str) -> tuple[bool, str]:
        """Mặc định: hãng không cho huỷ qua API. Ghi đè nếu hãng hỗ trợ."""
        return False, "Hãng này không cho huỷ vận đơn qua API"

    async def san_sang(self) -> tuple[bool, str]:
        """Dùng được chưa? Trả (được/không, lý do) — dashboard hiện lý do."""
        return True, ""
>>>>>>> origin/main
