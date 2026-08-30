"""
Adapter Odoo — JSON-RPC cổ điển tại `/jsonrpc`.

CHƯA XÁC MINH TRÊN INSTANCE THẬT
--------------------------------
`python -m scripts.thu_erp` gọi thật và in ra thứ nó tìm thấy. Chạy nó TRƯỚC
khi cho khách thật đi qua đường này.

VÌ SAO `/jsonrpc` CHỨ KHÔNG PHẢI `/json/2/`
-------------------------------------------
Odoo 19 (saas-19.3+) có API mới `/json/2/<model>/<method>` với
`Authorization: bearer`. Gọn hơn thật, nhưng bản tự host phổ biến là 16/17/18
và chúng KHÔNG có endpoint đó. `/jsonrpc` chạy trên cả bốn.

VÌ SAO KHÔNG DÙNG `xmlrpc.client`
---------------------------------
Đó là cách tài liệu Odoo hay ví dụ nhất, nhưng nó ĐỒNG BỘ. Gọi nó trong
vòng lặp sự kiện là chặn cả tiến trình — ở contact center nghĩa là mọi khách
khác đứng chờ. JSON-RPC nói cùng một `execute_kw`, qua httpx bất đồng bộ.

BỐN CÁI BẪY
-----------
1. `free_qty`, KHÔNG phải `qty_available`. Cái sau là hàng trong kho; cái
   trước đã trừ phần bị đơn khác giữ chỗ.

2. Không truyền `context={"warehouse": id}` thì Odoo trả tồn TOÀN CÔNG TY.
   Con số đó trông hoàn toàn hợp lý và sai.

3. `sale_ok` và `active`. Odoo giữ cả hàng ngừng bán lẫn hàng đã lưu trữ.

4. `default_code` được phép rỗng. Không mã thì không nối được với nửa tư
   vấn, nên bỏ qua chứ đừng đưa vào danh mục.

GIÁ: CHƯA QUA BẢNG GIÁ
----------------------
Adapter này đọc `list_price` — giá bán công khai trên phiếu sản phẩm. Giá
theo `product.pricelist` cần gọi `_get_product_price`, mà chữ ký hàm đó đổi
giữa các phiên bản Odoo. Trường `Gia.nguon` nói thẳng "list_price" để không
ai tưởng nó đã qua bảng giá, và `scripts/thu_erp.py` bắt NGƯỜI xác nhận.
"""
from __future__ import annotations

from typing import Any

import httpx

from agent.config import settings
from agent.erp.hop_dong import (DongDon, Gia, KetQuaDon, LoiERP, SanPhamERP,
                                TonKho, TuChoiERP)

_TRUONG_SP = ["default_code", "name", "categ_id", "uom_id", "list_price",
              "sale_ok"]
_TRUONG_TON = ["default_code", "free_qty"]
_TRUONG_GIA = ["default_code", "list_price"]

NGUON_GIA = "list_price (giá bán công khai, chưa qua bảng giá)"

# Khớp `agent/core/du_lieu_ca_nhan.AN_DANH`.
AN_DANH = "[đã ẩn danh theo yêu cầu]"

# `stock.picking.state` của Odoo -> bộ trạng thái NỘI BỘ. Tường minh, và
# giá trị lạ thì trả None chứ không đoán.
#
# `draft` và `waiting` KHÔNG ánh xạ: hàng chưa sẵn sàng thì chưa phải "đang
# giao", và nói với khách là đang giao lúc đó là hứa sớm.
_TRANG_THAI_GIAO = {
    "confirmed": "delivering",
    "assigned": "delivering",
    "done": "delivered",
    "cancel": "returned",
}


def _nhan(v: Any) -> str:
    """Trường many2one của Odoo trả `[id, "nhãn"]`, hoặc `False` khi trống."""
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        return str(v[1])
    return ""


class NguonOdoo:
    ten = "odoo"

    def __init__(
        self,
        goc: str | None = None,
        db: str | None = None,
        dang_nhap: str | None = None,
        api_key: str | None = None,
        ma_kho: str | None = None,
        client: httpx.AsyncClient | None = None,
        han_cho: float = 20.0,
    ):
        self._goc = (goc if goc is not None else settings.odoo_url).rstrip("/")
        self._db = db if db is not None else settings.odoo_db
        self._dang_nhap = (
            dang_nhap if dang_nhap is not None else settings.odoo_dang_nhap
        )
        self._api_key = api_key if api_key is not None else settings.odoo_api_key
        self._ma_kho = ma_kho if ma_kho is not None else settings.erp_ma_kho

        if not self._goc:
            raise ValueError("Thiếu ODOO_URL")
        if not self._db:
            raise ValueError("Thiếu ODOO_DB")
        if not self._dang_nhap:
            raise ValueError("Thiếu ODOO_DANG_NHAP")
        if not self._api_key:
            raise ValueError("Thiếu ODOO_API_KEY")
        if not self._ma_kho:
            raise ValueError(
                "Thiếu ERP_MA_KHO. Không truyền kho thì Odoo trả tồn toàn "
                "công ty — một con số trông hợp lý và sai."
            )

        self._client = client or httpx.AsyncClient(
            base_url=self._goc, timeout=han_cho
        )
        self._uid: int | None = None
        self._kho_id: int | None = None
        self._so_thu_tu = 0

    # --- tầng JSON-RPC ------------------------------------------------

    async def _rpc(self, service: str, method: str, args: list) -> Any:
        self._so_thu_tu += 1
        try:
            res = await self._client.post(
                "/jsonrpc",
                json={
                    "jsonrpc": "2.0",
                    "method": "call",
                    "id": self._so_thu_tu,
                    "params": {"service": service, "method": method,
                               "args": args},
                },
            )
        except httpx.HTTPError as exc:
            raise LoiERP(f"Không gọi được Odoo: {exc}") from exc

        if res.status_code != 200:
            raise LoiERP(f"Odoo trả HTTP {res.status_code}")
        try:
            goi = res.json()
        except ValueError as exc:
            raise LoiERP("Odoo trả thân không phải JSON") from exc

        if "error" in goi:
            # Odoo nhét thông điệp thật vào `error.data.message`; `error.message`
            # chỉ là "Odoo Server Error", vô dụng khi đi dò lỗi.
            loi = goi["error"]
            data = loi.get("data") or {}
            chi_tiet = data.get("message") or loi.get("message")
            # Phân biệt TỪ CHỐI với SỰ CỐ. Odoo đặt tên ngoại lệ ở
            # `data.name`; ValidationError/UserError nghĩa là nó HIỂU yêu cầu
            # và không đồng ý — thử lại bao nhiêu lần cũng thế. Gộp chung là
            # thử lại vô ích một đơn sẽ luôn bị từ chối.
            ten_loi = str(data.get("name") or "")
            if any(k in ten_loi or k in str(chi_tiet)
                   for k in ("ValidationError", "UserError", "AccessError")):
                raise TuChoiERP(f"Odoo từ chối: {chi_tiet}")
            raise LoiERP(f"Odoo báo lỗi: {chi_tiet}")
        return goi.get("result")

    async def _dam_bao_uid(self) -> int:
        # Giữ uid lại. Gọi `authenticate` mỗi lần là nhân đôi số vòng mạng
        # cho mọi câu hỏi của khách.
        if self._uid is None:
            uid = await self._rpc(
                "common", "authenticate",
                [self._db, self._dang_nhap, self._api_key, {}],
            )
            if not uid:
                raise LoiERP(
                    "Odoo từ chối đăng nhập — kiểm ODOO_DB, ODOO_DANG_NHAP, "
                    "ODOO_API_KEY"
                )
            self._uid = int(uid)
        return self._uid

    async def _doc(
        self, model: str, mien: list, truong: list[str],
        ngu_canh: dict | None = None,
    ) -> list[dict]:
        uid = await self._dam_bao_uid()
        kwargs: dict = {"fields": truong}
        if ngu_canh:
            kwargs["context"] = ngu_canh
        kq = await self._rpc(
            "object", "execute_kw",
            [self._db, uid, self._api_key, model, "search_read",
             [mien], kwargs],
        )
        return kq or []

    async def _dam_bao_kho_id(self) -> int:
        if self._kho_id is None:
            if str(self._ma_kho).isdigit():
                self._kho_id = int(self._ma_kho)
            else:
                rows = await self._doc(
                    "stock.warehouse", [["code", "=", self._ma_kho]], ["id"]
                )
                if not rows:
                    raise LoiERP(
                        f"Không có kho nào mã {self._ma_kho!r} trong Odoo. "
                        "ERP_MA_KHO nhận mã kho (`code`) hoặc id dạng số."
                    )
                self._kho_id = int(rows[0]["id"])
        return self._kho_id

    # --- hợp đồng -----------------------------------------------------

    async def danh_sach_san_pham(
        self, chi_ban_duoc: bool = True
    ) -> list[SanPhamERP]:
        mien: list = [["active", "=", True]]
        if chi_ban_duoc:
            mien.append(["sale_ok", "=", True])
        rows = await self._doc("product.product", mien, _TRUONG_SP)
        return [
            SanPhamERP(
                ma=str(r["default_code"]),
                ten=str(r.get("name") or ""),
                loai=_nhan(r.get("categ_id")),
                dung_tich=_nhan(r.get("uom_id")),
                ban_duoc_phep=bool(r.get("sale_ok", True)),
            )
            for r in rows
            # `default_code` được phép rỗng (Odoo trả `False`). Không mã thì
            # không nối được với nửa tư vấn — bỏ qua thay vì tạo một dòng
            # không ai tra được.
            if r.get("default_code")
        ]

    async def gia(self, ma: str) -> Gia | None:
        rows = await self._doc(
            "product.product",
            [["default_code", "=", ma], ["active", "=", True]],
            _TRUONG_GIA,
        )
        if not rows or rows[0].get("list_price") is None:
            return None
        return Gia(
            gia_ban=int(round(float(rows[0]["list_price"]))),
            don_vi="VND",
            nguon=NGUON_GIA,
        )

    async def ton_kho(self, ma: str) -> TonKho | None:
        kho_id = await self._dam_bao_kho_id()
        rows = await self._doc(
            "product.product",
            [["default_code", "=", ma], ["active", "=", True]],
            _TRUONG_TON,
            ngu_canh={"warehouse": kho_id},
        )
        if not rows:
            # Chưa biết, KHÔNG phải hết hàng.
            return None
        con = rows[0].get("free_qty")
        if con is None:
            return None
        # `free_qty` âm được khi kho đang lệch; số âm làm mọi phép so sánh
        # "đủ hàng không" phía trên hành xử lạ.
        return TonKho(ban_duoc=max(0, int(float(con))), ma_kho=str(self._ma_kho))

    async def suc_khoe(self) -> bool:
        try:
            await self._rpc("common", "version", [])
        except Exception:  # noqa: BLE001
            return False
        return True

    # --- đường GHI ----------------------------------------------------
    #
    # Mọi thứ dưới đây tạo dữ liệu KHÔNG XOÁ ĐƯỢC trong Odoo của cửa hàng.
    # Chúng chỉ chạy khi `ERP_GHI_DON=true` — xem agent/erp/day_don.py.

    async def _ghi(self, model: str, method: str, args: list) -> Any:
        uid = await self._dam_bao_uid()
        return await self._rpc(
            "object", "execute_kw",
            [self._db, uid, self._api_key, model, method, args],
        )

    async def bao_dam_khach(self, ten: str, sdt: str, dia_chi: str) -> str:
        # Tra theo số điện thoại TRƯỚC. Odoo không có ràng buộc duy nhất trên
        # `phone`, nên tạo mới mỗi đơn là một người thành mười `res.partner`.
        co = await self._doc(
            "res.partner", ["|", ["phone", "=", sdt], ["mobile", "=", sdt]],
            ["id"],
        )
        if co:
            return str(co[0]["id"])
        moi = await self._ghi("res.partner", "create", [{
            "name": ten,
            "phone": sdt,
            "street": dia_chi,
            "company_type": "person",
        }])
        return str(moi)

    async def tim_don(self, khoa: str) -> str | None:
        co = await self._doc(
            "sale.order", [["client_order_ref", "=", khoa]], ["name"]
        )
        return str(co[0]["name"]) if co else None

    async def tao_don(
        self, khoa: str, khach_id: str, dong: list[DongDon], ghi_chu: str = ""
    ) -> KetQuaDon:
        if not dong:
            raise ValueError("Đơn không có dòng hàng nào")

        # Odoo nối dòng đơn bằng ID nội bộ, không bằng `default_code`. Phải
        # dịch trước, và mã nào không dịch được thì DỪNG — tạo đơn thiếu dòng
        # là bán thiếu hàng cho khách mà không ai thấy.
        ids: dict[str, int] = {}
        for d in dong:
            row = await self._doc(
                "product.product", [["default_code", "=", d.ma]], ["id"]
            )
            if not row:
                return KetQuaDon(
                    thanh_cong=False,
                    ly_do=f"Odoo không có sản phẩm mã {d.ma}",
                )
            ids[d.ma] = int(row[0]["id"])

        try:
            don_id = await self._ghi("sale.order", "create", [{
                "partner_id": int(khach_id),
                # `client_order_ref` mang khoá idempotency, và cũng là thứ
                # `tim_don` tra — hai bên phải dùng ĐÚNG một trường.
                "client_order_ref": khoa,
                "note": ghi_chu,
                "order_line": [
                    (0, 0, {"product_id": ids[d.ma],
                            "product_uom_qty": d.so_luong,
                            "price_unit": d.don_gia})
                    for d in dong
                ],
            }])
        except TuChoiERP as exc:
            return KetQuaDon(thanh_cong=False, ly_do=str(exc))

        # `create` trả id dạng số; mã đơn người đọc được nằm ở `name`.
        ten_don = await self._ghi("sale.order", "read", [[don_id], ["name"]])
        ma_don = ""
        if ten_don:
            ma_don = str(ten_don[0].get("name") or don_id)
        return KetQuaDon(thanh_cong=True, erp_ma_don=ma_don or str(don_id))

    async def trang_thai_giao(self, erp_ma_don: str) -> str | None:
        """Phiếu xuất kho của đơn này tới đâu rồi.

        `None` khi chưa có phiếu, hoặc khi Odoo trả một `state` ngoài bảng
        ánh xạ. Cả hai là "chưa biết", và chưa biết KHÁC "đang giao".
        """
        rows = await self._doc(
            "stock.picking",
            [["sale_id.client_order_ref", "=", erp_ma_don]],
            ["id", "state"],
        )
        if not rows:
            return None
        return _TRANG_THAI_GIAO.get(str(rows[0].get("state") or ""))

    async def an_danh_khach(self, sdt: str) -> int:
        """Xoá thông tin nhận dạng khỏi res.partner, GIỮ bản ghi.

        Odoo chặn xoá `res.partner` đã gắn với `sale.order`, và cũng không
        nên xoá: chứng từ kế toán phải còn. Ẩn danh giữ chứng từ mà không
        giữ người.
        """
        co = await self._doc(
            "res.partner", ["|", ["phone", "=", sdt], ["mobile", "=", sdt]],
            ["id"],
        )
        if not co:
            return 0
        ids = [int(r["id"]) for r in co]
        await self._ghi("res.partner", "write", [ids, {
            "name": AN_DANH, "phone": False, "mobile": False,
            "email": False, "street": False, "street2": False,
        }])
        return len(ids)
