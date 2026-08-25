"""
Triển khai kết nối API Giao Hàng Nhanh (GHN Open API v2).
Tài liệu tham khảo: https://api.ghn.vn/home/docs/detail
"""
from __future__ import annotations

import hashlib
import hmac
import unicodedata
from datetime import datetime, timezone
from typing import Any

import httpx

from agent.config import settings
from .base import BaseShippingProvider
from .models import (
    CreateWaybillRequest,
    CreateWaybillResult,
    InternalShippingStatus,
    TrackingResult,
    TrackingTimelineItem,
    WebhookEventResult,
)

_DISTRICTS_CACHE: list[dict[str, Any]] | None = None
_WARDS_CACHE: dict[int, list[dict[str, Any]]] = {}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode("utf-8")
    return s.lower().replace("quan", "").replace("phuong", "").replace("quan ", "").replace("huyen", "").replace("tp", "").replace("thanh pho", "").replace(".", "").strip()


class GHNShippingProvider(BaseShippingProvider):
    def __init__(
        self,
        api_url: str | None = None,
        token: str | None = None,
        shop_id: str | None = None,
    ) -> None:
        self._api_url = (api_url or settings.ghn_api_url).rstrip("/")
        self._token = token or settings.ghn_token
        self._shop_id = shop_id or settings.ghn_shop_id

    @property
    def code(self) -> str:
        return "ghn"

    @property
    def name(self) -> str:
        return "Giao Hàng Nhanh (GHN)"

    def map_status(self, carrier_status: str) -> InternalShippingStatus:
        s = str(carrier_status).strip().lower()
        if s in ("delivered", "finish"):
            return InternalShippingStatus.DELIVERED
        if s in ("delivery_fail", "waiting_to_return"):
            return InternalShippingStatus.DELIVERY_FAILED
        if s in ("return", "returned", "return_fail", "damage", "lost", "cancel", "exception"):
            return InternalShippingStatus.RETURNED
        return InternalShippingStatus.DELIVERING

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Token": self._token,
        }
        if self._shop_id:
            headers["ShopId"] = str(self._shop_id)
        return headers

    async def _resolve_address(self, dia_chi: str) -> tuple[int | None, str | None]:
        """Tự động phân tích địa chỉ để lấy to_district_id và to_ward_code từ GHN."""
        global _DISTRICTS_CACHE, _WARDS_CACHE
        if not self._token:
            return None, None

        addr_clean = _norm(dia_chi)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if _DISTRICTS_CACHE is None:
                    res = await client.get(
                        f"{self._api_url.replace('/v2', '')}/master-data/district",
                        headers={"Token": self._token},
                    )
                    if res.status_code == 200:
                        _DISTRICTS_CACHE = res.json().get("data", [])
                    else:
                        _DISTRICTS_CACHE = []

                # 1. Tìm District
                matched_dist_id = None
                if _DISTRICTS_CACHE:
                    for d in _DISTRICTS_CACHE:
                        d_name = _norm(d.get("DistrictName", ""))
                        if d_name and (f" {d_name} " in f" {addr_clean} " or addr_clean.endswith(f" {d_name}")):
                            matched_dist_id = d.get("DistrictID")
                            break
                        # Kiểm tra name extension (ví dụ: Q1, Q.1)
                        for ext in d.get("NameExtension", []) or []:
                            ext_clean = _norm(ext)
                            if ext_clean and f" {ext_clean} " in f" {addr_clean} ":
                                matched_dist_id = d.get("DistrictID")
                                break
                        if matched_dist_id:
                            break

                # Mặc định về Quận 1 TP.HCM nếu không bắt được quận cụ thể
                if not matched_dist_id:
                    matched_dist_id = 1442  # Quận 1 HCM

                # 2. Tìm Ward
                matched_ward_code = None
                if matched_dist_id not in _WARDS_CACHE:
                    res_w = await client.post(
                        f"{self._api_url.replace('/v2', '')}/master-data/ward",
                        headers={"Token": self._token},
                        json={"district_id": matched_dist_id},
                    )
                    if res_w.status_code == 200:
                        _WARDS_CACHE[matched_dist_id] = res_w.json().get("data", [])
                    else:
                        _WARDS_CACHE[matched_dist_id] = []

                wards = _WARDS_CACHE.get(matched_dist_id, [])
                for w in wards:
                    w_name = _norm(w.get("WardName", ""))
                    if w_name and (f" {w_name} " in f" {addr_clean} " or addr_clean.endswith(f" {w_name}")):
                        matched_ward_code = str(w.get("WardCode", ""))
                        break
                    for ext in w.get("NameExtension", []) or []:
                        ext_clean = _norm(ext)
                        if ext_clean and f" {ext_clean} " in f" {addr_clean} ":
                            matched_ward_code = str(w.get("WardCode", ""))
                            break
                    if matched_ward_code:
                        break

                if not matched_ward_code and wards:
                    matched_ward_code = str(wards[0].get("WardCode", "20102"))

                return matched_dist_id, matched_ward_code
        except Exception:
            return 1442, "20102"

    async def tao_van_don(self, req: CreateWaybillRequest) -> CreateWaybillResult:
        if not self._token:
            return CreateWaybillResult(
                ok=False,
                loi="Chưa cấu hình GHN_TOKEN trong .env. Vui lòng cung cấp token GHN.",
            )

        url = f"{self._api_url}/shipping-order/create"

        items_payload = [
            {
                "name": it.ten,
                "code": it.ma,
                "quantity": it.so_luong,
                "price": it.don_gia,
                "weight": it.khoi_luong_gram,
            }
            for it in req.items
        ]

        dist_id, ward_code = await self._resolve_address(req.khach_dia_chi)

        payload: dict[str, Any] = {
            "payment_type_id": 2,
            "note": req.ghi_chu or "Mỹ phẩm, xin nhẹ tay",
            "required_note": req.yeu_cau_giao or "KHONGCHOXEMHANG",
            "client_order_code": req.ma_don,
            "to_name": req.khach_ten,
            "to_phone": req.khach_sdt,
            "to_address": req.khach_dia_chi,
            "to_district_id": dist_id or 1442,
            "to_ward_code": ward_code or "20102",
            "weight": req.tong_khoi_luong_gram,
            "cod_amount": req.thu_ho_cod,
            "service_type_id": 2,
            "items": items_payload,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=self._headers(), json=payload)
                data = resp.json()

            if resp.status_code != 200 or data.get("code") != 200:
                msg = data.get("message") or data.get("code_message_value") or resp.text
                if "FROM_ADDRESS_CONVERT_FAIL" in str(msg) or "SHOP_INFO_ERROR" in str(msg):
                    msg += " (Vui lòng cập nhật đầy đủ Địa chỉ kho lấy hàng của shop trên trang quản lý GHN)"
                return CreateWaybillResult(ok=False, loi=f"GHN từ chối tạo đơn: {msg}")

            res_data = data.get("data", {})
            tracking_code = str(res_data.get("order_code", ""))
            total_fee = int(res_data.get("total_fee", 0))
            expected_delivery = None
            if res_data.get("expected_delivery_time"):
                try:
                    expected_delivery = datetime.fromisoformat(
                        res_data["expected_delivery_time"].replace("Z", "+00:00")
                    )
                except Exception:
                    pass

            return CreateWaybillResult(
                ok=True,
                ma_van_don=tracking_code,
                don_vi="ghn",
                phi_van_chuyen=total_fee,
                ngay_du_kien_giao=expected_delivery,
                trang_thai_noi_bo=InternalShippingStatus.DELIVERING,
                thong_tin_them=res_data,
            )
        except Exception as exc:
            return CreateWaybillResult(
                ok=False, loi=f"Lỗi mạng khi kết nối GHN API: {type(exc).__name__}: {exc}"
            )

    async def tra_cuu(self, ma_van_don: str) -> TrackingResult:
        if not self._token:
            return TrackingResult(
                ok=False,
                ma_van_don=ma_van_don,
                don_vi="ghn",
                trang_thai_noi_bo=InternalShippingStatus.DELIVERING,
                trang_thai_goc="unknown",
                loi="Chưa cấu hình GHN_TOKEN trong .env",
            )

        url = f"{self._api_url}/shipping-order/detail"
        payload = {"order_code": ma_van_don}

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, headers=self._headers(), json=payload)
                data = resp.json()

            if resp.status_code != 200 or data.get("code") != 200:
                msg = data.get("message") or resp.text
                return TrackingResult(
                    ok=False,
                    ma_van_don=ma_van_don,
                    don_vi="ghn",
                    trang_thai_noi_bo=InternalShippingStatus.DELIVERING,
                    trang_thai_goc="error",
                    loi=f"Không tra cứu được đơn GHN: {msg}",
                )

            d = data.get("data", {})
            carrier_status = str(d.get("status") or "")
            internal_status = self.map_status(carrier_status)
            station = str(d.get("station_name") or d.get("to_address") or "")

            timeline = []
            for log in d.get("log", []):
                t_str = log.get("updated_date")
                t_dt = datetime.now(timezone.utc)
                if t_str:
                    try:
                        t_dt = datetime.fromisoformat(t_str.replace("Z", "+00:00"))
                    except Exception:
                        pass
                st = str(log.get("status", ""))
                timeline.append(
                    TrackingTimelineItem(
                        thoi_gian=t_dt,
                        trang_thai_hang=st,
                        trang_thai_noi_bo=self.map_status(st),
                        dia_diem=str(log.get("station", "")),
                        mo_ta=str(log.get("status_name", "")),
                    )
                )

            return TrackingResult(
                ok=True,
                ma_van_don=ma_van_don,
                don_vi="ghn",
                trang_thai_noi_bo=internal_status,
                trang_thai_goc=carrier_status,
                vi_tri_hien_tai=station,
                lich_su=timeline,
            )
        except Exception as exc:
            return TrackingResult(
                ok=False,
                ma_van_don=ma_van_don,
                don_vi="ghn",
                trang_thai_noi_bo=InternalShippingStatus.DELIVERING,
                trang_thai_goc="network_error",
                loi=f"Lỗi mạng khi tra cứu GHN: {exc}",
            )

    def parse_webhook(
        self, body: dict[str, Any], headers: dict[str, Any]
    ) -> WebhookEventResult:
        secret = settings.shipping_webhook_secret
        if secret:
            sig = headers.get("x-ghn-signature") or headers.get("signature")
            if sig:
                expected = hmac.new(
                    secret.encode("utf-8"),
                    str(body).encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()
                if not hmac.compare_digest(sig, expected):
                    return WebhookEventResult(hop_le=False, loi="Chữ ký webhook GHN không hợp lệ")

        order_code = str(body.get("OrderCode") or body.get("order_code") or "")
        client_code = str(body.get("ClientOrderCode") or body.get("client_order_code") or "")
        status = str(body.get("Status") or body.get("status") or "")
        desc = str(body.get("Description") or body.get("description") or "")

        return WebhookEventResult(
            hop_le=True,
            ma_don=client_code,
            ma_van_don=order_code,
            don_vi="ghn",
            trang_thai_goc=status,
            trang_thai_noi_bo=self.map_status(status),
            mo_ta=desc,
            thoi_gian=datetime.now(timezone.utc),
            du_lieu_goc=body,
        )
