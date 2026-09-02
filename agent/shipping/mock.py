"""
Mock Shipping Provider phục vụ kiểm thử và môi trường phát triển offline.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .base import BaseShippingProvider
from .models import (
    CreateWaybillRequest,
    CreateWaybillResult,
    InternalShippingStatus,
    TrackingResult,
    TrackingTimelineItem,
    WebhookEventResult,
)


class MockShippingProvider(BaseShippingProvider):
    def __init__(self, code: str = "mock", name: str = "Mock Carrier") -> None:
        self._code = code
        self._name = name
        self._storage: dict[str, dict[str, Any]] = {}

    @property
    def code(self) -> str:
        return self._code

    @property
    def name(self) -> str:
        return self._name

    async def tao_van_don(self, req: CreateWaybillRequest) -> CreateWaybillResult:
        tracking_code = f"MOCK-{self._code.upper()}-{int(time.time())}-{req.ma_don}"
        now = datetime.now(timezone.utc)
        eta = now + timedelta(days=2)

        data = {
            "ma_don": req.ma_don,
            "ma_van_don": tracking_code,
            "khach_ten": req.khach_ten,
            "khach_sdt": req.khach_sdt,
            "khach_dia_chi": req.khach_dia_chi,
            "tong_tien": req.tong_tien,
            "thu_ho_cod": req.thu_ho_cod,
            "trang_thai_goc": "picking",
            "trang_thai_noi_bo": InternalShippingStatus.DELIVERING,
            "phi_van_chuyen": 25000,
            "ngay_du_kien_giao": eta,
            "created_at": now,
            "lich_su": [
                {
                    "thoi_gian": now,
                    "trang_thai_hang": "picking",
                    "trang_thai_noi_bo": InternalShippingStatus.DELIVERING,
                    "dia_diem": "Kho Aurora Skin - TP.HCM",
                    "mo_ta": "Đã tiếp nhận yêu cầu lấy hàng từ người gửi.",
                }
            ],
        }
        self._storage[tracking_code] = data

        return CreateWaybillResult(
            ok=True,
            ma_van_don=tracking_code,
            don_vi=self._code,
            phi_van_chuyen=25000,
            ngay_du_kien_giao=eta,
            trang_thai_noi_bo=InternalShippingStatus.DELIVERING,
            thong_tin_them={"note": "Đơn thử nghiệm Mock Carrier"},
        )

    async def tra_cuu(self, ma_van_don: str) -> TrackingResult:
        data = self._storage.get(ma_van_don)
        now = datetime.now(timezone.utc)
        if not data:
            # Sinh dữ liệu mẫu hợp lý nếu tra cứu mã mới
            return TrackingResult(
                ok=True,
                ma_van_don=ma_van_don,
                don_vi=self._code,
                trang_thai_noi_bo=InternalShippingStatus.DELIVERING,
                trang_thai_goc="delivering",
                vi_tri_hien_tai="Bưu cục trung tâm Quận 1",
                ngay_du_kien_giao=now + timedelta(hours=6),
                lich_su=[
                    TrackingTimelineItem(
                        thoi_gian=now - timedelta(hours=4),
                        trang_thai_hang="picking",
                        trang_thai_noi_bo=InternalShippingStatus.DELIVERING,
                        dia_diem="Kho xuất hàng",
                        mo_ta="Bưu tá đã lấy hàng từ shop",
                    ),
                    TrackingTimelineItem(
                        thoi_gian=now,
                        trang_thai_hang="delivering",
                        trang_thai_noi_bo=InternalShippingStatus.DELIVERING,
                        dia_diem="Bưu cục Quận 1",
                        mo_ta="Bưu tá đang trên đường đi giao đến người nhận",
                    ),
                ],
            )

        timeline = [
            TrackingTimelineItem(
                thoi_gian=item["thoi_gian"],
                trang_thai_hang=item["trang_thai_hang"],
                trang_thai_noi_bo=item["trang_thai_noi_bo"],
                dia_diem=item.get("dia_diem", ""),
                mo_ta=item.get("mo_ta", ""),
            )
            for item in data.get("lich_su", [])
        ]
        return TrackingResult(
            ok=True,
            ma_van_don=ma_van_don,
            don_vi=self._code,
            trang_thai_noi_bo=data["trang_thai_noi_bo"],
            trang_thai_goc=data["trang_thai_goc"],
            vi_tri_hien_tai="Kho hàng",
            ngay_du_kien_giao=data.get("ngay_du_kien_giao"),
            lich_su=timeline,
        )

    def parse_webhook(
        self, body: dict[str, Any], headers: dict[str, Any]
    ) -> WebhookEventResult:
        ma_van_don = str(body.get("OrderCode") or body.get("tracking_code") or body.get("ma_van_don") or "")
        ma_don = str(body.get("ClientOrderCode") or body.get("order_id") or body.get("ma_don") or "")
        carrier_status = str(body.get("Status") or body.get("status") or body.get("trang_thai") or "delivering")
        internal_status = self.map_status(carrier_status)

        return WebhookEventResult(
            hop_le=True,
            ma_don=ma_don,
            ma_van_don=ma_van_don,
            don_vi=self._code,
            trang_thai_goc=carrier_status,
            trang_thai_noi_bo=internal_status,
            mo_ta=str(body.get("Description") or body.get("mo_ta") or ""),
            thoi_gian=datetime.now(timezone.utc),
            du_lieu_goc=body,
        )
