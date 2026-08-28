"""
Adapter ERPNext — REST của Frappe.

CHƯA XÁC MINH TRÊN INSTANCE THẬT
--------------------------------
Dựng theo tài liệu Frappe. Tên DocType và tên trường ở bản ERPNext của bạn
có thể khác. `python -m scripts.thu_erp` gọi thật và in ra thứ nó tìm thấy —
chạy nó TRƯỚC khi cho khách thật đi qua đường này.

BA CÁI BẪY, CẢ BA ĐỀU HỎNG IM LẶNG
----------------------------------
1. `limit_page_length=0`. Frappe mặc định trả 20 bản ghi. Quên tham số này
   thì cửa hàng 60 SKU chỉ thấy 20, agent tư vấn trên danh mục bị cắt cụt,
   và không có lỗi nào được ném.

2. `ban_duoc = actual_qty - reserved_qty`. `actual_qty` là hàng trong kho;
   phần đã bị đơn khác đặt nằm ở `reserved_qty`. Lấy nhầm `actual_qty` là
   hứa bán món đã có người mua.

3. Danh sách rỗng KHÁC số 0. Không có bản ghi `Bin` nghĩa là chưa biết, và
   trả 0 là nói dối một cách tự tin — tầng trên không phân biệt được.

VÌ SAO NÉM CHỨ KHÔNG NUỐT LỖI
-----------------------------
Adapter ném `LoiERP`; `agent/erp/cong.py` là nơi DUY NHẤT quyết định biến
lỗi thành `None`. Nuốt lỗi ở đây thì bộ đếm ngắt mạch không bao giờ tăng và
mạch không bao giờ mở.
"""
from __future__ import annotations

import json

import httpx

from agent.config import settings
from agent.erp.hop_dong import (DongDon, Gia, KetQuaDon, LoiERP, SanPhamERP,
                                TonKho, TuChoiERP)

# Frappe mặc định phân trang 20. Xem bẫy số 1 ở đầu file.
KHONG_PHAN_TRANG = "0"

_TRUONG_ITEM = ["item_code", "item_name", "item_group", "stock_uom",
                "is_sales_item"]
_TRUONG_GIA = ["price_list_rate", "currency", "price_list", "valid_upto"]
_TRUONG_BIN = ["actual_qty", "reserved_qty", "warehouse"]


def _thong_diep_loi(res: httpx.Response) -> str:
    """Bóc thông điệp người đọc được ra khỏi lỗi của Frappe.

    Frappe nhét lỗi thật vào `exception` hoặc `_server_messages` (một chuỗi
    JSON lồng trong JSON). Trả nguyên `res.text` là ném cả trang HTML lỗi
    vào ghi chú đơn, và người trực không đọc nổi.
    """
    try:
        goi = res.json()
    except ValueError:
        return f"ERPNext {res.status_code}"
    if goi.get("exception"):
        return str(goi["exception"])
    tin = goi.get("_server_messages")
    if tin:
        try:
            trong = json.loads(tin)
            if trong:
                return str(json.loads(trong[0]).get("message") or trong[0])
        except (ValueError, TypeError, KeyError):
            return str(tin)
    return str(goi.get("message") or f"ERPNext {res.status_code}")


class NguonErpNext:
    ten = "erpnext"

    def __init__(
        self,
        goc: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        ma_kho: str | None = None,
        pricelist: str | None = None,
        client: httpx.AsyncClient | None = None,
        han_cho: float = 15.0,
    ):
        self._goc = (goc if goc is not None else settings.erpnext_url).rstrip("/")
        khoa = api_key if api_key is not None else settings.erpnext_api_key
        bi_mat = (
            api_secret if api_secret is not None else settings.erpnext_api_secret
        )
        self._ma_kho = ma_kho if ma_kho is not None else settings.erp_ma_kho
        self._pricelist = (
            pricelist if pricelist is not None else settings.erp_pricelist
        )

        # Nổ lúc DỰNG, không đợi tới lời gọi đầu tiên.
        #
        # Thiếu mã kho mà vẫn chạy được thì lời gọi `Bin` trả về tồn của MỌI
        # kho cộng lại — một con số trông hoàn toàn hợp lý và sai. Không ai
        # phát hiện cho tới khi giao hàng từ kho không có hàng.
        if not self._goc:
            raise ValueError("Thiếu ERPNEXT_URL")
        if not khoa:
            raise ValueError("Thiếu ERPNEXT_API_KEY")
        if not bi_mat:
            raise ValueError("Thiếu ERPNEXT_API_SECRET")
        if not self._ma_kho:
            raise ValueError(
                "Thiếu ERP_MA_KHO. Bin của ERPNext là theo từng kho, nên "
                "'còn bao nhiêu' là câu hỏi không có đáp án nếu không nói "
                "kho nào."
            )
        if not self._pricelist:
            raise ValueError(
                "Thiếu ERP_PRICELIST. Không nói bảng giá nào thì mỗi sản "
                "phẩm có thể trả về nhiều mức giá khác nhau."
            )

        self._client = client or httpx.AsyncClient(
            base_url=self._goc, timeout=han_cho
        )
        self._headers = {"Authorization": f"token {khoa}:{bi_mat}"}

    # --- gọi thô ------------------------------------------------------

    async def _lay(self, doctype: str, loc: list, truong: list[str]) -> list[dict]:
        try:
            res = await self._client.get(
                f"/api/resource/{doctype}",
                params={
                    "filters": json.dumps(loc),
                    "fields": json.dumps(truong),
                    "limit_page_length": KHONG_PHAN_TRANG,
                },
                headers=self._headers,
            )
        except httpx.HTTPError as exc:
            raise LoiERP(f"Không gọi được ERPNext: {exc}") from exc

        if res.status_code != 200:
            # Ném chứ không trả rỗng. Rỗng nghĩa là "không có hàng nào" —
            # một câu trả lời khác hẳn "không hỏi được".
            raise LoiERP(
                f"ERPNext trả {res.status_code} khi đọc {doctype}"
            )
        try:
            return res.json().get("data", [])
        except ValueError as exc:
            raise LoiERP(f"ERPNext trả thân không phải JSON cho {doctype}") from exc

    # --- hợp đồng -----------------------------------------------------

    async def danh_sach_san_pham(
        self, chi_ban_duoc: bool = True
    ) -> list[SanPhamERP]:
        loc: list = [["disabled", "=", 0]]
        if chi_ban_duoc:
            loc.append(["is_sales_item", "=", 1])
        rows = await self._lay("Item", loc, _TRUONG_ITEM)
        return [
            SanPhamERP(
                ma=str(r.get("item_code") or ""),
                ten=str(r.get("item_name") or r.get("item_code") or ""),
                loai=str(r.get("item_group") or ""),
                dung_tich=str(r.get("stock_uom") or ""),
                # Đọc từ dữ liệu, KHÔNG suy từ tham số lọc. Suy ra thì khi
                # gọi với chi_ban_duoc=False mọi món đều mang cờ True —
                # sai, và sai một cách không thể phát hiện từ bên ngoài.
                ban_duoc_phep=bool(r.get("is_sales_item", 1)),
            )
            for r in rows
            if r.get("item_code")
        ]

    async def gia(self, ma: str) -> Gia | None:
        rows = await self._lay(
            "Item Price",
            [
                ["item_code", "=", ma],
                ["price_list", "=", self._pricelist],
                ["selling", "=", 1],
            ],
            _TRUONG_GIA,
        )
        if not rows:
            return None
        r = rows[0]
        gia_ban = r.get("price_list_rate")
        if gia_ban is None:
            return None
        return Gia(
            gia_ban=int(round(float(gia_ban))),
            don_vi=str(r.get("currency") or "VND"),
            nguon=str(r.get("price_list") or self._pricelist),
            hieu_luc_den=r.get("valid_upto") or None,
        )

    async def ton_kho(self, ma: str) -> TonKho | None:
        rows = await self._lay(
            "Bin",
            [["item_code", "=", ma], ["warehouse", "=", self._ma_kho]],
            _TRUONG_BIN,
        )
        if not rows:
            # Chưa biết, KHÔNG phải hết hàng. Xem bẫy số 3 ở đầu file.
            return None
        r = rows[0]
        co = float(r.get("actual_qty") or 0)
        giu = float(r.get("reserved_qty") or 0)
        # `max(0, ...)`: reserved > actual xảy ra thật khi kho đang lệch, và
        # số âm làm mọi phép so sánh "đủ hàng không" phía trên hành xử lạ.
        return TonKho(
            ban_duoc=max(0, int(co - giu)),
            ma_kho=str(r.get("warehouse") or self._ma_kho),
        )

    async def suc_khoe(self) -> bool:
        try:
            res = await self._client.get(
                "/api/method/frappe.auth.get_logged_user",
                headers=self._headers,
            )
        except Exception:  # noqa: BLE001
            return False
        return res.status_code == 200

    # --- đường GHI ----------------------------------------------------
    #
    # Mọi thứ dưới đây tạo dữ liệu KHÔNG XOÁ ĐƯỢC trong ERP của cửa hàng.
    # Chúng chỉ chạy khi `ERP_GHI_DON=true` — xem agent/erp/day_don.py.

    async def _tao(self, doctype: str, than: dict) -> dict:
        try:
            res = await self._client.post(
                f"/api/resource/{doctype}",
                json=than,
                headers={**self._headers, "content-type": "application/json"},
            )
        except httpx.HTTPError as exc:
            # NÉM, không trả thất bại. Mất mạng giữa chừng nghĩa là KHÔNG
            # BIẾT ERP đã nhận hay chưa — tầng trên phải thử lại, và bước tra
            # trước khi tạo sẽ chặn đơn thứ hai.
            raise LoiERP(f"Mất kết nối khi tạo {doctype}: {exc}") from exc

        if res.status_code in (200, 201):
            return res.json().get("data", {})
        if res.status_code >= 500:
            # 5xx cũng là KHÔNG BIẾT: ERP có thể đã ghi xong rồi mới ngã.
            raise LoiERP(f"ERPNext {res.status_code} khi tạo {doctype}")
        # 4xx là ERP hiểu và TỪ CHỐI. Đây là câu trả lời, không phải sự cố.
        raise TuChoiERP(_thong_diep_loi(res))

    async def bao_dam_khach(self, ten: str, sdt: str, dia_chi: str) -> str:
        # Tra theo số điện thoại TRƯỚC. Tạo mới mỗi đơn thì một người thành
        # mười bản ghi, và báo cáo bán hàng bên ERP thành vô nghĩa.
        co = await self._lay(
            "Customer", [["mobile_no", "=", sdt]], ["name"]
        )
        if co:
            return str(co[0]["name"])
        moi = await self._tao("Customer", {
            "customer_name": ten,
            "mobile_no": sdt,
            "customer_type": "Individual",
            "customer_group": "All Customer Groups",
            "territory": "All Territories",
            "primary_address": dia_chi,
        })
        return str(moi.get("name") or "")

    async def tim_don(self, khoa: str) -> str | None:
        co = await self._lay("Sales Order", [["po_no", "=", khoa]], ["name"])
        return str(co[0]["name"]) if co else None

    async def tao_don(
        self, khoa: str, khach_id: str, dong: list[DongDon], ghi_chu: str = ""
    ) -> KetQuaDon:
        if not dong:
            raise ValueError("Đơn không có dòng hàng nào")
        try:
            kq = await self._tao("Sales Order", {
                "customer": khach_id,
                # `po_no` mang khoá idempotency. Nó cũng là thứ `tim_don`
                # tra, nên hai bên phải dùng ĐÚNG một trường.
                "po_no": khoa,
                "set_warehouse": self._ma_kho,
                "selling_price_list": self._pricelist,
                "items": [
                    {"item_code": d.ma, "qty": d.so_luong, "rate": d.don_gia}
                    for d in dong
                ],
                "remarks": ghi_chu,
            })
        except TuChoiERP as exc:
            return KetQuaDon(thanh_cong=False, ly_do=str(exc))
        return KetQuaDon(thanh_cong=True, erp_ma_don=str(kq.get("name") or ""))
