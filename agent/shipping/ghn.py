"""
Triển khai kết nối API Giao Hàng Nhanh (GHN Open API v2).
Tài liệu tham khảo: https://api.ghn.vn/home/docs/detail
"""
from __future__ import annotations

import re
import time
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


# Tiền tố hành chính cần bỏ khi so khớp. Phải khớp NGUYÊN TỪ.
#
# Bản trước dùng `.replace("quan", "")` — cắt mọi chỗ có ba chữ đó, kể cả khi
# nằm giữa một từ khác. Đo được:
#     "TP Ha Long, Quang Ninh"  ->  "ha long, g ninh"
#     "TP Tam Ky, Quang Nam"    ->  "tam ky, g nam"
# Năm tỉnh Quảng — Ninh, Nam, Bình, Trị, Ngãi — bị băm nát, nên không bao giờ
# khớp được quận, rồi rơi vào mặc định "Quận 1 TP.HCM" ở dưới. Hàng đi sai
# tỉnh mà không ai biết.
_TIEN_TO = ("thanh pho", "tinh", "quan", "huyen", "phuong", "xa", "thi tran",
            "thi xa", "tp", "q", "p", "h", "tt")

_TACH_TU = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    """Bỏ dấu, bỏ tiền tố hành chính — nhưng chỉ khi nó là MỘT TỪ RIÊNG."""
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode("utf-8")
    tu = [t for t in _TACH_TU.split(s.lower()) if t]
    return " ".join(t for t in tu if t not in _TIEN_TO)


class GHNShippingProvider(BaseShippingProvider):
    def __init__(
        self,
        api_url: str | None = None,
        token: str | None = None,
        shop_id: str | None = None,
    ) -> None:
        from agent import cau_hinh_dong

        self._api_url = (api_url or settings.ghn_api_url).rstrip("/")
        self._token = token or cau_hinh_dong.lay("GHN_TOKEN")
        self._shop_id = shop_id or cau_hinh_dong.lay("GHN_SHOP_ID")

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

                # KHÔNG đoán. Không khớp được quận thì DỪNG.
                #
                # Bản trước mặc định về 1442 (Quận 1 TP.HCM). GHN định tuyến
                # theo `to_district_id`, KHÔNG theo chữ trong `to_address` —
                # nên vận đơn ghi địa chỉ Hạ Long mà kiện hàng đi Sài Gòn.
                # Shop trả phí giao lẫn phí hoàn, khách không nhận được hàng,
                # và không ai biết cho tới khi khách kêu.
                #
                # Hỏi lại khách một câu rẻ hơn nhiều so với gửi sai một tỉnh.
                if not matched_dist_id:
                    return None, None

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

                # Lấy bừa phường đầu tiên trong quận cũng là đoán — chỉ
                # sai nhỏ hơn. Vẫn dừng.
                if not matched_ward_code:
                    return None, None

                return matched_dist_id, matched_ward_code
        except Exception:
            # Mạng hỏng KHÔNG được biến thành "gửi về Quận 1". Trả None để
            # lớp trên báo lỗi và chuyển người.
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


async def kiem_ket_noi(
    *, token: str, shop_id: str, api_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[bool, str, int]:
    """
    Token có sống và shop id có thuộc tài khoản này không. CHỈ ĐỌC.

    `shop/all` là lời gọi rẻ nhất cần token mà không tạo gì. Tách riêng khỏi
    `GHNShippingProvider` để dashboard kiểm bằng giá trị CHƯA LƯU.
    """
    goc = (api_url or settings.ghn_api_url).rstrip("/")
    t0 = time.perf_counter()
    dong = client is None
    client = client or httpx.AsyncClient(timeout=15.0)
    try:
        r = await client.post(
            f"{goc}/shop/all",
            headers={"Token": token, "Content-Type": "application/json"},
            json={"offset": 0, "limit": 50},
        )
    except httpx.HTTPError as exc:
        return False, f"{type(exc).__name__}: không nối được GHN", int((time.perf_counter() - t0) * 1000)
    finally:
        if dong:
            await client.aclose()
    ms = int((time.perf_counter() - t0) * 1000)
    if r.status_code in (401, 403):
        return False, "GHN từ chối token", ms
    if r.status_code >= 400:
        return False, f"GHN {r.status_code}: {r.text[:120]}", ms
    shops = ((r.json().get("data") or {}).get("shops") or [])
    ids = {str(s.get("_id")) for s in shops}
    if shop_id and str(shop_id) not in ids:
        return False, f"token đúng nhưng shop id {shop_id} không thuộc tài khoản này", ms
    return True, f"{len(shops)} shop · {ms}ms", ms
