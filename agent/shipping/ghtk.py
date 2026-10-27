"""
Kết nối Giao Hàng Tiết Kiệm (GHTK Open API).

Tài liệu (đọc 27.10.2026):
  · tạo đơn   https://api.ghtk.vn/en/docs/submit-order/submit-order-express/
  · webhook   https://api.ghtk.vn/en/docs/submit-order/webhook
  · tra, huỷ  https://pro-docs.ghtk.vn/3-shipping_api/

BA CHỖ KHÁC GHN, VÀ CẢ BA LÀ CHỖ DỄ HỎNG IM LẶNG
------------------------------------------------
1. GHTK định tuyến theo CHỮ tỉnh/quận/phường, không theo mã. Không có bước
   tra mã nào để thất bại — nên phải tự từ chối khi không tách được địa chỉ
   rõ ràng, thay vì gửi bừa một chuỗi rồi để GHTK đoán.
2. Webhook gửi dạng FORM (`application/x-www-form-urlencoded`), không phải
   JSON. Cổng webhook chỉ nhận JSON là trả 400 cho MỌI cập nhật — và GHTK
   chỉ gửi lại MỘT lần (tài liệu webhook), rồi bỏ.
3. Có mã "shipper báo đã giao" (45) bên cạnh "đã giao" (5). Tài liệu nói rõ
   mã shipper chỉ để tham khảo. Đọc 45 thành đã giao là đóng đơn và nhắn
   cảm ơn khách trước khi hàng thật sự tới.
"""
from __future__ import annotations

import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from agent.config import settings

from .base import BaseShippingProvider
from .models import (
    CreateWaybillRequest,
    CreateWaybillResult,
    InternalShippingStatus,
    TrackingResult,
    WebhookEventResult,
)

_D = InternalShippingStatus
_VN = timezone(timedelta(hours=7))

# Khoá GHTK lấy từ cấu hình động (dashboard) — cùng chỗ với GHN.
KHOA_LAY_HANG = ("GHTK_LAY_TEN", "GHTK_LAY_SDT", "GHTK_LAY_DIA_CHI",
                 "GHTK_LAY_TINH", "GHTK_LAY_HUYEN")


def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower()).replace("đ", "d")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()


_DAU_PHUONG = re.compile(r"^(phuong|xa|thi tran|p\.?|tt\.?)(\s|\d|$)")
_DAU_QUAN = re.compile(r"^(quan|huyen|thi xa|thanh pho|tp\.?|q\.?|h\.?|tx\.?)(\s|\d|$)")


def tach_dia_chi(dia_chi: str) -> dict[str, str] | None:
    """
    "12 Lê Lợi, Phường Bến Nghé, Quận 1, TP Hồ Chí Minh"
        -> {address, ward, district, province}

    Trả None khi KHÔNG CHẮC. Đòi đủ bốn phần cách nhau bằng dấu phẩy, phần
    áp chót bắt đầu bằng quận/huyện/thị xã/thành phố và phần trước nó bằng
    phường/xã/thị trấn. Lỏng hơn là đoán: "Hẻm 5, 123 Lê Lợi, Q1, HCM" tách
    thẳng thành phường "123 Lê Lợi" — GHTK nhận tên phường bằng chữ, và một
    tên phường sai là kiện hàng đi tìm một phường không có.

    Địa chỉ hai cấp sau sáp nhập 2025 (không có quận/huyện) cũng bị trả
    None: tài liệu tạo đơn GHTK vẫn ghi `district` là bắt buộc. Hỏi lại
    khách, hoặc tạo tay trên trang GHTK — rẻ hơn một kiện hàng đi lạc.
    """
    phan = [p.strip() for p in str(dia_chi or "").split(",") if p.strip()]
    if len(phan) < 4:
        return None
    phuong, quan, tinh = phan[-3], phan[-2], phan[-1]
    if not _DAU_PHUONG.match(_bo_dau(phuong)) or not _DAU_QUAN.match(_bo_dau(quan)):
        return None
    if _DAU_PHUONG.match(_bo_dau(tinh)) or re.match(r"^(quan|huyen)\b", _bo_dau(tinh)):
        return None
    return {"address": ", ".join(phan[:-3]), "ward": phuong, "district": quan, "province": tinh}


def _ngay_du_kien(chu: Any) -> datetime | None:
    """GHTK trả "Chiều 2017-07-01" — lấy phần ngày, bỏ phần buổi."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(chu or ""))
    if not m:
        return None
    try:
        return datetime(int(m[1]), int(m[2]), int(m[3]), 12, tzinfo=_VN)
    except ValueError:
        return None


def _so(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


class GHTKShippingProvider(BaseShippingProvider):
    # status_id theo tài liệu webhook GHTK. CHỈ "21 — đã trả hàng về shop"
    # là RETURNED: trạng thái đó CỘNG HÀNG LẠI VÀO KHO (xem base.py), nên
    # 20 (đang trả), 26 (hàng hoàn nhập kho GHTK, chưa về shop), 13 (bồi
    # hoàn — hàng mất) đều không được nằm đó.
    BANG_MA_RIENG = {
        **dict.fromkeys(("1", "2", "3", "4", "8", "12", "30", "31", "91"), _D.DELIVERING),
        **dict.fromkeys(("5", "6"), _D.DELIVERED),
        "21": _D.RETURNED,
        # 10 = khách hẹn giao lại: cùng chỗ với `khach_hen_lai` của bảng chung.
        **dict.fromkeys(("-1", "7", "9", "10", "13", "20", "26"), _D.DELIVERY_FAILED),
    }
    # 11 = đối soát công nợ đơn hoàn: việc kế toán, không phải hàng đã về.
    # Xếp vào RETURNED là hoàn kho theo một bút toán. Còn lại là mã shipper
    # tự báo — tài liệu: chỉ để tham khảo, không phải trạng thái chính thức.
    MA_CHI_THONG_TIN = frozenset({"11", "45", "49", "123", "127", "128", "410"})

    def __init__(self, api_url: str | None = None, token: str | None = None) -> None:
        from agent import cau_hinh_dong

        self._lay = cau_hinh_dong.lay
        self._api_url = (api_url or settings.ghtk_api_url).rstrip("/")
        self._token_co_dinh = token

    @property
    def code(self) -> str:
        return "ghtk"

    @property
    def name(self) -> str:
        return "Giao Hàng Tiết Kiệm (GHTK)"

    # Đọc khoá MỖI LẦN gọi, không giữ từ lúc dựng: provider được cache suốt
    # đời tiến trình (service._PROVIDERS), và người vận hành đổi token trên
    # dashboard thì lần gọi kế phải dùng token mới — không phải đợi khởi động lại.
    def _k(self, khoa: str) -> str:
        if khoa == "GHTK_TOKEN" and self._token_co_dinh is not None:
            return self._token_co_dinh
        return str(self._lay(khoa) or "").strip()

    def _headers(self) -> dict[str, str]:
        h = {"Token": self._k("GHTK_TOKEN"), "Content-Type": "application/json"}
        if self._k("GHTK_MA_DOI_TAC"):
            h["X-Client-Source"] = self._k("GHTK_MA_DOI_TAC")
        return h

    def _thieu_cau_hinh(self) -> str:
        if not self._k("GHTK_TOKEN"):
            return ("Chưa cấu hình GHTK_TOKEN. Lấy ở trang khách hàng GHTK → "
                    "Thông tin cửa hàng → API Token.")
        if self._k("GHTK_KHO_ID"):
            return ""
        thieu = [k for k in KHOA_LAY_HANG if not self._k(k)]
        if thieu:
            return ("Chưa cấu hình nơi lấy hàng: điền GHTK_KHO_ID (mã kho trên "
                    "trang GHTK → Sửa thông tin cửa hàng), hoặc đủ "
                    + ", ".join(thieu) + ". Không có thì GHTK không biết lấy hàng ở đâu.")
        return ""

    def _lay_hang(self) -> dict[str, Any]:
        ra: dict[str, Any] = {}
        if self._k("GHTK_KHO_ID"):
            ra["pick_address_id"] = self._k("GHTK_KHO_ID")
        for khoa, truong in zip(
            KHOA_LAY_HANG + ("GHTK_LAY_PHUONG",),
            ("pick_name", "pick_tel", "pick_address", "pick_province",
             "pick_district", "pick_ward"),
            strict=True,
        ):
            if self._k(khoa):
                ra[truong] = self._k(khoa)
        return ra

    async def san_sang(self) -> tuple[bool, str]:
        loi = self._thieu_cau_hinh()
        return (not loi), loi

    async def tao_van_don(self, req: CreateWaybillRequest) -> CreateWaybillResult:
        loi = self._thieu_cau_hinh()
        if loi:
            return CreateWaybillResult(ok=False, can_nguoi_xac_nhan=True, loi=loi)

        dc = tach_dia_chi(req.khach_dia_chi)
        if dc is None:
            return CreateWaybillResult(
                ok=False, can_nguoi_xac_nhan=True,
                loi=("Không tách được địa chỉ thành số nhà/đường, phường/xã, "
                     f"quận/huyện, tỉnh/thành: '{req.khach_dia_chi}'. KHÔNG tạo "
                     "vận đơn để tránh gửi sai nơi. Hỏi lại khách địa chỉ dạng "
                     "'12 Lê Lợi, Phường Bến Nghé, Quận 1, TP Hồ Chí Minh' — hoặc "
                     "để nhân viên tạo vận đơn tay trên trang GHTK."),
            )

        products = [{
            "name": it.ten[:120],
            "product_code": it.ma,
            "quantity": it.so_luong,
            "price": it.don_gia,
            # weight_option=gram: khối lượng MỘT đơn vị, không phải cả dòng.
            "weight": max(1, it.khoi_luong_gram // max(1, it.so_luong)),
        } for it in req.items]

        order: dict[str, Any] = {
            "id": req.ma_don,
            **self._lay_hang(),
            "name": req.khach_ten,
            "tel": req.khach_sdt,
            "address": dc["address"],
            "ward": dc["ward"],
            "district": dc["district"],
            "province": dc["province"],
            "hamlet": "Khác",
            # 0 = khách trả cả tiền hàng lẫn phí ship — cùng cách tính với
            # GHN (`payment_type_id: 2`), để đổi hãng không đổi giá khách trả.
            "is_freeship": 0,
            "pick_money": req.thu_ho_cod,
            "value": req.tong_tien,
            # GHTK cắt ghi chú ở 120 ký tự từ 24.02.2020.
            "note": (req.ghi_chu or "Mỹ phẩm, xin nhẹ tay")[:120],
            "weight_option": "gram",
            "total_weight": req.tong_khoi_luong_gram,
            "transport": "road",
            "pick_option": "cod",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self._api_url}/services/shipment/order/?ver=1.5",
                                         headers=self._headers(),
                                         json={"products": products, "order": order})
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            # Đứt mạng giữa chừng: GHTK có thể ĐÃ tạo đơn. Lần thử lại sẽ
            # nhận ORDER_ID_EXIST kèm mã cũ ở nhánh dưới — không sinh đơn thứ hai.
            return CreateWaybillResult(
                ok=False, loi=f"Lỗi mạng khi gọi GHTK: {type(exc).__name__}: {exc}")
        if not isinstance(data, dict):
            return CreateWaybillResult(ok=False, loi=f"GHTK trả {resp.status_code}, thân không phải JSON")

        if not data.get("success"):
            loi_ghtk = data.get("error") or {}
            if isinstance(loi_ghtk, dict) and loi_ghtk.get("code") == "ORDER_ID_EXIST":
                nhan = str(loi_ghtk.get("ghtk_label") or "")
                # Mã đơn đã có trên GHTK — lần gọi trước đã thành công mà ta
                # không biết (đứt mạng, hoặc ghi CSDL hỏng sau đó). Nhận lại
                # mã cũ thay vì báo lỗi: báo lỗi là nhân viên tạo tay một vận
                # đơn THỨ HAI. Trừ khi đơn cũ đã huỷ — khi ấy phải có người quyết.
                if nhan and str(loi_ghtk.get("status")) != "-1":
                    return CreateWaybillResult(
                        ok=True, ma_van_don=nhan, don_vi="ghtk",
                        trang_thai_noi_bo=self.map_status(str(loi_ghtk.get("status"))) or _D.DELIVERING,
                        thong_tin_them={"da_co_san": True, "ghtk": loi_ghtk},
                    )
                return CreateWaybillResult(
                    ok=False, can_nguoi_xac_nhan=True,
                    loi=(f"Mã đơn {req.ma_don} đã có trên GHTK ({nhan or 'không rõ mã'}) "
                         "và đơn đó đã huỷ. GHTK không cho dùng lại mã đơn — tạo tay trên trang GHTK."))
            return CreateWaybillResult(ok=False, loi=f"GHTK từ chối tạo đơn: {data.get('message') or resp.text[:200]}")

        o = data.get("order") or {}
        nhan = str(o.get("label") or "")
        if not nhan:
            return CreateWaybillResult(ok=False, loi="GHTK báo thành công nhưng không trả mã vận đơn — cần người kiểm trên trang GHTK")
        return CreateWaybillResult(
            ok=True, ma_van_don=nhan, don_vi="ghtk",
            phi_van_chuyen=_so(o.get("fee")) + _so(o.get("insurance_fee")),
            ngay_du_kien_giao=_ngay_du_kien(o.get("estimated_deliver_time")),
            trang_thai_noi_bo=_D.DELIVERING, thong_tin_them=o,
        )

    async def tra_cuu(self, ma_van_don: str) -> TrackingResult:
        def hong(loi: str, goc: str = "error") -> TrackingResult:
            return TrackingResult(ok=False, ma_van_don=ma_van_don, don_vi="ghtk",
                                  trang_thai_noi_bo=_D.DELIVERING, trang_thai_goc=goc, loi=loi)

        if not self._k("GHTK_TOKEN"):
            return hong("Chưa cấu hình GHTK_TOKEN", "unknown")
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(f"{self._api_url}/services/shipment/v2/{ma_van_don}",
                                        headers=self._headers())
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return hong(f"Lỗi mạng khi tra GHTK: {type(exc).__name__}", "network_error")
        if not isinstance(data, dict) or not data.get("success"):
            msg = data.get("message") if isinstance(data, dict) else resp.text[:120]
            return hong(f"Không tra được đơn GHTK: {msg}")

        o = data.get("order") or {}
        goc = str(o.get("status") or "")
        mo_ta = str(o.get("status_text") or "")
        st = self.map_status(goc)
        if st is None or self.chi_thong_tin(goc):
            # ok=False: `tra_cuu_van_don` chỉ ghi trạng thái xuống đơn khi ok.
            # Mã lạ hoặc mã chỉ-thông-tin không được ghi đè trạng thái đã biết.
            r = hong(f"GHTK báo «{mo_ta or goc}» — giữ nguyên trạng thái đơn, người kiểm nếu cần", goc)
            r.vi_tri_hien_tai = mo_ta
            return r
        return TrackingResult(ok=True, ma_van_don=ma_van_don, don_vi="ghtk",
                              trang_thai_noi_bo=st, trang_thai_goc=goc,
                              vi_tri_hien_tai=mo_ta,
                              ngay_du_kien_giao=_ngay_du_kien(o.get("deliver_date")))

    async def huy_van_don(self, ma_van_don: str) -> tuple[bool, str]:
        if not self._k("GHTK_TOKEN"):
            return False, "Chưa cấu hình GHTK_TOKEN"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(f"{self._api_url}/services/shipment/cancel/{ma_van_don}",
                                         headers=self._headers())
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return False, f"Lỗi mạng khi huỷ trên GHTK: {type(exc).__name__}"
        if isinstance(data, dict) and data.get("success"):
            return True, ""
        # GHTK chỉ cho huỷ khi đơn ở trạng thái 1, 2, 12 (chưa lấy hàng).
        msg = data.get("message") if isinstance(data, dict) else resp.text[:120]
        return False, f"GHTK không huỷ được: {msg}"

    def parse_webhook(self, body: dict[str, Any], headers: dict[str, Any]) -> WebhookEventResult:
        # Xác thực ở lớp HTTP (service.kiem_bi_mat_webhook) — GHTK không ký
        # webhook; bí mật nằm trong URL khai với GHTK.
        nhan = str(body.get("label_id") or "").strip()
        ma_don = str(body.get("partner_id") or "").strip()
        goc = str(body.get("status_id") if body.get("status_id") is not None else "").strip()
        if not (nhan or ma_don) or not goc:
            return WebhookEventResult(hop_le=False, don_vi="ghtk",
                                      loi="webhook GHTK thiếu label_id/partner_id hoặc status_id",
                                      du_lieu_goc=body)
        return WebhookEventResult(
            hop_le=True, ma_don=ma_don, ma_van_don=nhan, don_vi="ghtk",
            trang_thai_goc=goc,
            trang_thai_noi_bo=None if self.chi_thong_tin(goc) else self.map_status(goc),
            chi_thong_tin=self.chi_thong_tin(goc),
            mo_ta=str(body.get("reason") or ""),
            thoi_gian=datetime.now(timezone.utc), du_lieu_goc=body,
        )


async def kiem_ket_noi(*, token: str, ma_doi_tac: str = "", api_url: str | None = None,
                       client: httpx.AsyncClient | None = None) -> tuple[bool, str, int]:
    """
    Token có sống không. CHỈ ĐỌC: danh sách giải pháp của shop là lời gọi rẻ
    nhất cần token mà không tạo gì. Tách khỏi provider để dashboard kiểm bằng
    giá trị CHƯA LƯU.
    """
    goc = (api_url or settings.ghtk_api_url).rstrip("/")
    h = {"Token": token}
    if ma_doi_tac:
        h["X-Client-Source"] = ma_doi_tac
    t0 = time.perf_counter()
    dong = client is None
    client = client or httpx.AsyncClient(timeout=15.0)
    try:
        r = await client.get(f"{goc}/open/api/v1/shop/solution/list", headers=h)
    except httpx.HTTPError as exc:
        return False, f"{type(exc).__name__}: không nối được GHTK", int((time.perf_counter() - t0) * 1000)
    finally:
        if dong:
            await client.aclose()
    ms = int((time.perf_counter() - t0) * 1000)
    if r.status_code in (401, 403):
        return False, "GHTK từ chối token", ms
    try:
        du_lieu = r.json()
    except ValueError:
        return False, f"GHTK trả {r.status_code}, thân không phải JSON", ms
    if not isinstance(du_lieu, dict) or not du_lieu.get("success"):
        msg = du_lieu.get("message") if isinstance(du_lieu, dict) else ""
        return False, f"GHTK từ chối: {str(msg)[:120] or r.status_code}", ms
    return True, f"token hợp lệ · {ms}ms", ms
