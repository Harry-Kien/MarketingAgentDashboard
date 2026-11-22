"""
Thao tác ghi lên đơn dùng chung cho NGƯỜI (màn Đơn hàng) và cho đề xuất AI
đã được duyệt / mức Tự động (agent/core/uy_quyen.py).

VÌ SAO TÁCH RA KHỎI ROUTE
-------------------------
Huỷ đơn có ba luật không được lệch: không huỷ đơn ĐÃ GIAO, không trả kho hai
lần, và nói rõ phần phải huỷ tay bên ERP/hãng. Đề xuất "Huỷ đơn" của AI phải
chịu ĐÚNG ba luật ấy lúc thi hành. Hai bản sao của cùng một việc thì bản ít
người đọc hơn sẽ mục — nên một bản, hai lối gọi.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from agent import db
from agent.core import kho


class LoiThaoTacDon(Exception):
    """Điều kiện nghiệp vụ không thoả. `ma` là mã HTTP tầng API trả."""

    def __init__(self, ma: int, thong_diep: str) -> None:
        super().__init__(thong_diep)
        self.ma = ma
        self.thong_diep = thong_diep


async def huy_don(oid: UUID, *, actor: str, conversation_id: Any = None) -> dict:
    """
    Huỷ đơn và TRẢ HÀNG VỀ KHO.

    Không trả lại thì mỗi đơn huỷ ăn mất tồn kho vĩnh viễn — bán mười đơn
    huỷ chín đơn là kho báo hết hàng trong khi hàng vẫn nằm nguyên trên kệ.

    KHÔNG huỷ đơn ĐÃ GIAO: hàng đang ở nhà khách, huỷ là cộng kho một món
    không có trên kệ (rà soát 11.2026). Khách trả lại hàng là ĐỔI TRẢ —
    nhận hàng về rồi nhập kho bằng tay.

    `conversation_id` (đường AI): đơn phải thuộc đúng hội thoại ấy — kiểm LẠI
    lúc thi hành, trong cùng giao dịch có khoá, không tin lúc đề xuất.
    """
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            hien = await conn.fetchrow(
                "SELECT trang_thai, conversation_id FROM orders WHERE id=$1 FOR UPDATE", oid)
            if hien is None:
                raise LoiThaoTacDon(404, "Không có đơn này")
            if conversation_id is not None and str(hien["conversation_id"]) != str(conversation_id):
                raise LoiThaoTacDon(409, "Đơn không thuộc hội thoại của đề xuất.")
            cu = hien["trang_thai"]
            if cu == "da_giao":
                raise LoiThaoTacDon(
                    409, "Đơn đã giao — không huỷ được: hàng đang ở chỗ khách, huỷ là "
                         "cộng kho một món không có trên kệ. Xử lý như đổi trả: nhận "
                         "hàng về rồi nhập kho (Kho → Nhập).")
            don = await conn.fetchrow(
                "UPDATE orders SET trang_thai='da_huy', updated_at=now() "
                "WHERE id=$1 AND trang_thai <> 'da_huy' "
                "RETURNING ma_don, erp_ma_don, ma_van_don, so_tien_da_thu", oid,
            )
    if don is None:
        return {"ok": True, "da_huy_tu_truoc": True,
                "ghi_chu": "Đơn đã huỷ từ trước, không trả kho lần nữa."}

    so_dong = await kho.tra_hang(don["ma_don"])
    await db.log_event("order.cancel", actor=actor, ref_id=oid, ma_don=don["ma_don"],
                       so_mat_hang_tra_kho=so_dong, trang_thai_cu=cu)
    kq: dict = {"ok": True, "ma_don": don["ma_don"], "da_tra_kho": so_dong}
    # Huỷ ở đây KHÔNG huỷ bên ERP hay bên hãng vận chuyển. Nói thẳng lúc
    # bấm, để người huỷ tay bên đó — im là ERP vẫn xuất kho, hãng vẫn đi
    # lấy hàng cho một đơn đã huỷ.
    ben = []
    if don.get("erp_ma_don"):
        ben.append(f"ERP (đơn {don['erp_ma_don']})")
    elif cu == "cho_dong_bo":
        # Đang chờ đồng bộ = KHÔNG BIẾT ERP đã nhận chưa (lần đẩy trước có
        # thể đã tới ERP rồi mới đứt mạng). Không có mã ERP để chỉ ra, nhưng
        # im lặng là bỏ sót một đơn sống bên ERP.
        ben.append(f"ERP (đơn đang chờ đồng bộ — tra ERP theo mã {don['ma_don']}, "
                   "có thì huỷ)")
    if don.get("ma_van_don"):
        ben.append(f"hãng vận chuyển (vận đơn {don['ma_van_don']})")
    if ben:
        kq["can_huy_tay"] = ("Đơn đã có bên " + " và ".join(ben)
                             + ": vào đó huỷ tay, hệ thống không tự huỷ hộ.")
        await db.log_event("order.cancel_can_huy_tay", ref_id=oid, ma_don=don["ma_don"],
                           erp_ma_don=don.get("erp_ma_don"), ma_van_don=don.get("ma_van_don"),
                           trang_thai_cu=cu)
    if int(don.get("so_tien_da_thu") or 0) > 0:
        kq["can_hoan_tien"] = (f"Khách đã trả trước {int(don['so_tien_da_thu']):,}đ"
                               .replace(",", ".") + " — nhớ hoàn tiền cho khách.")
    return kq
