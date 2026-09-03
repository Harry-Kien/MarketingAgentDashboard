"""
Triển khai kết nối API Giao Hàng Nhanh (GHN Open API v2).
Tài liệu tham khảo: https://api.ghn.vn/home/docs/detail
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any

import httpx

from agent.config import ROOT, settings
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

CACHE_DIR = ROOT / "data" / "cache"
GHN_CACHE_TTL_SECONDS = 7 * 86400  # 7 ngày


def _read_disk_cache(path: Path) -> Any | None:
    try:
        if path.exists():
            stat = path.stat()
            if (time.time() - stat.st_mtime) < GHN_CACHE_TTL_SECONDS:
                return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _write_disk_cache(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# Tiền tố hành chính cần bỏ khi so khớp. Phải khớp NGUYÊN TỪ.
_TIEN_TO = (
    "thanh pho", "tinh", "quan", "huyen", "phuong", "xa", "thi tran",
    "thi xa", "tp", "q", "p", "h", "tt",
)

_TACH_TU = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    """Bỏ dấu (giữ đ thành d), bỏ tiền tố hành chính khi đứng riêng lẻ."""
    text = unicodedata.normalize("NFD", str(s or "").lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    tu = [t for t in _TACH_TU.split(text) if t]
    return " ".join(t for t in tu if t not in _TIEN_TO)


class GHNShippingProvider(BaseShippingProvider):
    def __init__(
        self,
        api_url: str | None = None,
        token: str | None = None,
        shop_id: str | None = None,
    ) -> None:
        self._api_url = (api_url if api_url is not None else settings.ghn_api_url).rstrip("/")
        self._token = token if token is not None else settings.ghn_token
        self._shop_id = shop_id if shop_id is not None else settings.ghn_shop_id

    @property
    def code(self) -> str:
        return "ghn"

    @property
    def name(self) -> str:
        return "Giao Hàng Nhanh (GHN)"

    def _headers(self) -> dict[str, str]:
        """
        Header cho lời gọi thuộc về một cửa hàng cụ thể.

        `ShopId` KHÔNG còn tuỳ chọn: nó cho GHN biết lấy hàng ở kho nào, và
        thiếu nó thì mọi lời gọi tạo vận đơn đều bị từ chối. Bỏ header đi khi
        trống chỉ đẩy lỗi sang phía GHN, nơi thông báo nói bằng từ vựng của
        họ chứ không nói "bạn quên điền GHN_SHOP_ID".
        """
        return {
            "Content-Type": "application/json",
            "Token": self._token,
            "ShopId": str(self._shop_id),
        }

    async def _resolve_address(self, dia_chi: str) -> tuple[int | None, str | None]:
        """Tự động phân tích địa chỉ để lấy to_district_id và to_ward_code từ GHN."""
        global _DISTRICTS_CACHE, _WARDS_CACHE
        if not self._token:
            return None, None

        raw_addr = unicodedata.normalize("NFD", str(dia_chi or "").lower())
        raw_addr = "".join(ch for ch in raw_addr if unicodedata.category(ch) != "Mn").replace("đ", "d")
        addr_clean = _norm(dia_chi)
        if not addr_clean:
            return None, None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                if _DISTRICTS_CACHE is None:
                    disk_districts = _read_disk_cache(CACHE_DIR / "ghn_districts.json")
                    if disk_districts:
                        _DISTRICTS_CACHE = disk_districts
                    else:
                        res = await client.get(
                            f"{self._api_url.replace('/v2', '')}/master-data/district",
                            headers={"Token": self._token},
                        )
                        if res.status_code == 200:
                            _DISTRICTS_CACHE = res.json().get("data", [])
                            _write_disk_cache(CACHE_DIR / "ghn_districts.json", _DISTRICTS_CACHE)
                        else:
                            _DISTRICTS_CACHE = []

                # 1. Tìm các ứng viên Quận/Huyện phù hợp
                candidates: list[tuple[int, dict[str, Any]]] = []
                if _DISTRICTS_CACHE:
                    for d in _DISTRICTS_CACHE:
                        d_name = _norm(d.get("DistrictName", ""))
                        matched_phrase = ""
                        if d_name:
                            if d_name.isdigit():
                                m = re.search(rf"\b(q|quan|district)\s*\.?\s*{d_name}\b", raw_addr)
                                if m:
                                    matched_phrase = m.group(0)
                            else:
                                if f" {d_name} " in f" {addr_clean} " or addr_clean.endswith(f" {d_name}"):
                                    matched_phrase = d_name

                        if not matched_phrase:
                            for ext in d.get("NameExtension", []) or []:
                                ext_clean = _norm(ext)
                                if ext_clean.isdigit():
                                    m = re.search(rf"\b(q|quan|district)\s*\.?\s*{ext_clean}\b", raw_addr)
                                    if m:
                                        matched_phrase = m.group(0)
                                        break
                                else:
                                    if ext_clean and (f" {ext_clean} " in f" {addr_clean} " or addr_clean.endswith(f" {ext_clean}")):
                                        matched_phrase = ext_clean
                                        break

                        if matched_phrase:
                            candidates.append((len(matched_phrase), d))

                if not candidates:
                    return None, None

                # Ưu tiên quận có cụm từ khớp dài nhất (tránh nhầm số nhà với tên quận)
                candidates.sort(key=lambda x: x[0], reverse=True)

                # 2. Tìm Phường/Xã cho ứng viên quận và xác nhận sự tồn tại của Phường trong Quận đó
                for _, c in candidates:
                    dist_id = c.get("DistrictID")
                    if not dist_id:
                        continue
                    if dist_id not in _WARDS_CACHE:
                        disk_wards = _read_disk_cache(CACHE_DIR / f"ghn_wards_{dist_id}.json")
                        if disk_wards:
                            _WARDS_CACHE[dist_id] = disk_wards
                        else:
                            res_w = await client.post(
                                f"{self._api_url.replace('/v2', '')}/master-data/ward",
                                headers={"Token": self._token},
                                json={"district_id": dist_id},
                            )
                            if res_w.status_code == 200:
                                _WARDS_CACHE[dist_id] = res_w.json().get("data", [])
                                _write_disk_cache(CACHE_DIR / f"ghn_wards_{dist_id}.json", _WARDS_CACHE[dist_id])
                            else:
                                _WARDS_CACHE[dist_id] = []

                    wards = _WARDS_CACHE.get(dist_id, [])
                    ward_candidates: list[tuple[int, dict[str, Any]]] = []
                    for w in wards:
                        w_name = _norm(w.get("WardName", ""))
                        w_matched_phrase = ""
                        if w_name:
                            if w_name.isdigit():
                                m = re.search(rf"\b(p|phuong|xa|ward)\s*\.?\s*{w_name}\b", raw_addr)
                                if m:
                                    w_matched_phrase = m.group(0)
                            else:
                                if f" {w_name} " in f" {addr_clean} " or addr_clean.endswith(f" {w_name}"):
                                    w_matched_phrase = w_name

                        if not w_matched_phrase:
                            for ext in w.get("NameExtension", []) or []:
                                ext_clean = _norm(ext)
                                if ext_clean.isdigit():
                                    m = re.search(rf"\b(p|phuong|xa|ward)\s*\.?\s*{ext_clean}\b", raw_addr)
                                    if m:
                                        w_matched_phrase = m.group(0)
                                        break
                                else:
                                    if ext_clean and (f" {ext_clean} " in f" {addr_clean} " or addr_clean.endswith(f" {ext_clean}")):
                                        w_matched_phrase = ext_clean
                                        break

                        if w_matched_phrase:
                            ward_candidates.append((len(w_matched_phrase), w))

                    if ward_candidates:
                        ward_candidates.sort(key=lambda x: x[0], reverse=True)
                        best_w = ward_candidates[0][1]
                        return dist_id, str(best_w.get("WardCode", ""))

                return None, None
        except Exception:
            return None, None

    async def tao_van_don(self, req: CreateWaybillRequest) -> CreateWaybillResult:
        thieu = [ten for ten, gia_tri in (
            ("GHN_TOKEN", self._token), ("GHN_SHOP_ID", self._shop_id),
        ) if not str(gia_tri or "").strip()]
        if thieu:
            return CreateWaybillResult(
                ok=False,
                can_nguoi_xac_nhan=True,
                loi=(
                    "Chưa cấu hình " + " và ".join(thieu) + " trong .env. "
                    "Lấy ở GHN → Quản lý cửa hàng: Token nằm ở mục API, "
                    "ShopId là mã cửa hàng. Không có ShopId thì GHN không "
                    "biết lấy hàng ở kho nào."
                ),
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
        if not dist_id or not ward_code:
            return CreateWaybillResult(
                ok=False,
                can_nguoi_xac_nhan=True,
                loi=(
                    "Không xác định được quận/huyện và phường/xã từ địa chỉ: "
                    f"'{req.khach_dia_chi}'. KHÔNG tạo vận đơn để tránh gửi "
                    "sai nơi. Hỏi lại khách địa chỉ đầy đủ gồm số nhà, đường, "
                    "phường/xã, quận/huyện, tỉnh/thành — hoặc để nhân viên "
                    "tạo vận đơn tay trên trang GHN."
                ),
            )

        payload: dict[str, Any] = {
            "payment_type_id": 2,
            "note": req.ghi_chu or "Mỹ phẩm, xin nhẹ tay",
            "required_note": req.yeu_cau_giao or "KHONGCHOXEMHANG",
            "client_order_code": req.ma_don,
            "to_name": req.khach_ten,
            "to_phone": req.khach_sdt,
            "to_address": req.khach_dia_chi,
            "to_district_id": dist_id,
            "to_ward_code": ward_code,
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
                        trang_thai_noi_bo=self.map_status(st) or InternalShippingStatus.DELIVERING,
                        dia_diem=str(log.get("station", "")),
                        mo_ta=str(log.get("status_name", "")),
                    )
                )

            return TrackingResult(
                ok=True,
                ma_van_don=ma_van_don,
                don_vi="ghn",
                trang_thai_noi_bo=internal_status or InternalShippingStatus.DELIVERING,
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
        # KHÔNG xác thực ở đây — xem `service.kiem_bi_mat_webhook`.
        #
        # Bản trước tự kiểm chữ ký tại chỗ và có hai lỗ hổng chồng nhau:
        #   `if secret:` -> chưa cấu hình thì bỏ qua toàn bộ
        #   `if sig:`    -> kẻ gọi chỉ cần KHÔNG gửi header là đi thẳng qua
        # Và nó ký trên `str(body)` — chuỗi repr của dict Python, không phải
        # body thô — nên kể cả khi có chữ ký thật cũng không bao giờ khớp.
        #
        # Ngoài ra GHN KHÔNG ký webhook: tài liệu của họ chỉ có "điền URL
        # callback". Bảo vệ đúng cách là bí mật nằm trong chính URL, kiểm ở
        # lớp HTTP cho mọi hãng — một chỗ, không phải mỗi hãng một kiểu.

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

    async def huy_van_don(self, ma_van_don: str, ly_do: str = "") -> tuple[bool, str]:
        thieu = [ten for ten, gia_tri in (
            ("GHN_TOKEN", self._token), ("GHN_SHOP_ID", self._shop_id),
        ) if not str(gia_tri or "").strip()]
        if thieu:
            return False, f"Thiếu cấu hình {', '.join(thieu)}"

        url = f"{self._api_url}/switch-status/cancel"
        payload = {
            "order_codes": [ma_van_don],
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, headers=self._headers(), json=payload)
                data = res.json()

            if res.status_code != 200 or data.get("code") != 200:
                msg = data.get("message") or data.get("code_message_value") or res.text
                return False, f"GHN từ chối huỷ đơn: {msg}"

            res_data = data.get("data") or []
            if res_data and isinstance(res_data, list):
                item = res_data[0]
                if item.get("result") is False:
                    return False, str(item.get("message") or "Hãng không thể huỷ đơn này")

            return True, "Huỷ vận đơn GHN thành công"
        except Exception as exc:  # noqa: BLE001
            return False, f"Lỗi kết nối GHN khi huỷ vận đơn: {exc}"
