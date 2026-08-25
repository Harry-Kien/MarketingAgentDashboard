"""
Giao diện cơ sở cho mọi đơn vị vận chuyển (GHN, GHTK, ViettelPost, Mock).
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


class BaseShippingProvider(ABC):
    """
    Hợp đồng trừu tượng cho đối tác vận chuyển.
    Mọi hãng (GHN, GHTK, Viettel Post) đều phải hiện thực đủ 4 phương thức này.
    """

    @property
    @abstractmethod
    def code(self) -> str:
        """Mã định danh của hãng (ví dụ: 'ghn', 'ghtk', 'mock')."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Tên hiển thị (ví dụ: 'Giao Hàng Nhanh')."""
        ...

    @abstractmethod
    async def tao_van_don(self, req: CreateWaybillRequest) -> CreateWaybillResult:
        """Gọi API hãng để tạo vận đơn mới và nhận mã tracking."""
        ...

    @abstractmethod
    async def tra_cuu(self, ma_van_don: str) -> TrackingResult:
        """Tra cứu trạng thái và lộ trình thời gian thực theo mã vận đơn."""
        ...

    @abstractmethod
    def parse_webhook(
        self, body: dict[str, Any], headers: dict[str, Any]
    ) -> WebhookEventResult:
        """
        Xác thực chữ ký và phân tích payload webhook từ hãng gửi về.
        Ánh xạ trạng thái riêng của hãng về 4 trạng thái nội bộ.
        """
        ...

    @abstractmethod
    def map_status(self, carrier_status: str) -> InternalShippingStatus:
        """Ánh xạ trạng thái chi tiết của hãng về 4 trạng thái cốt lõi."""
        ...
