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

import hashlib
import json
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


async def bang_chung_sua_don(ma_don: str, conversation_id: Any) -> dict:
    """Snapshot scoped to conversation; ERP is authoritative when linked.

    This is evidence for manual review, NOT permission to mutate a Sales Order.
    No stock reservation or ERP write is performed here.
    """
    don = await db.fetchrow(
        "SELECT id, ma_don, trang_thai, items, updated_at, erp_ma_don, "
        "ma_van_don, trang_thai_giao_hang, yeu_cau_huy_luc "
        "FROM orders WHERE ma_don=$1 AND conversation_id=$2",
        ma_don, UUID(str(conversation_id)),
    )
    if not don:
        raise LoiThaoTacDon(404, "Không tìm thấy đơn thuộc hội thoại này; hỏi lại mã đơn.")
    if (don["trang_thai"] != "da_chot" or don.get("ma_van_don")
            or don.get("yeu_cau_huy_luc")
            or don.get("trang_thai_giao_hang") not in (None, "", "pending")):
        raise LoiThaoTacDon(409, "Đơn không đủ điều kiện đề xuất sửa; cần nhân viên kiểm tra.")
    erp = None
    if don.get("erp_ma_don"):
        from agent.erp import nha_may

        try:
            erp = await nha_may.cong().doc_don(don["erp_ma_don"])
        except Exception as exc:
            raise LoiThaoTacDon(503, "Chưa xác minh được ERP; chưa sửa đơn, cần đối soát.") from exc
        if (not erp or erp.get("name") != don["erp_ma_don"]
                or (erp.get("docstatus"), erp.get("status")) not in (
                    (0, "Draft"), (1, "To Deliver and Bill"), (1, "To Deliver"))
                or not erp.get("modified")):
            raise LoiThaoTacDon(409, "Trạng thái ERP không đủ điều kiện; cần xử lý thủ công.")
        erp = {k: erp[k] for k in ("name", "docstatus", "status", "modified")}
    items = don["items"]
    if isinstance(items, str):
        items = json.loads(items)
    return {
        "order_id": str(don["id"]), "ma_don": don["ma_don"],
        "trang_thai": don["trang_thai"], "items": items,
        "updated_at": str(don["updated_at"]), "erp": erp,
    }


async def de_xuat_sua_don(args: dict, conversation_id: Any) -> dict:
    from agent.core import uy_quyen

    ma = str(args.get("ma_don") or "").strip()
    sp = str(args.get("ma_san_pham") or "").strip()
    ly_do = str(args.get("ly_do") or "").strip()
    sl = args.get("so_luong")
    if (not ma or not sp or not ly_do or not conversation_id
            or type(sl) is not int or not 1 <= sl <= 999
            or set(args) - {"ma_don", "ma_san_pham", "ly_do", "so_luong"}):
        return {"da_de_xuat": False, "da_sua": False,
                "ghi_chu": "Hỏi lại mã đơn, mã sản phẩm, số lượng mới (1–999) và lý do. "
                           "Chỉ hỗ trợ đề xuất sửa số lượng; không tự suy đoán."}
    try:
        truoc = await bang_chung_sua_don(ma, conversation_id)
    except (LoiThaoTacDon, ValueError) as exc:
        return {"da_de_xuat": False, "da_sua": False, "can_chuyen_nhan_vien": True,
                "ghi_chu": str(exc)}
    dong = [it for it in truoc["items"] if it.get("ma") == sp]
    if len(dong) != 1 or dong[0].get("so_luong") == sl:
        return {"da_de_xuat": False, "da_sua": False,
                "ghi_chu": "Sản phẩm không xác định duy nhất hoặc số lượng không đổi; hỏi lại khách."}
    sau = {"items": [dict(it, so_luong=sl) if it.get("ma") == sp else dict(it)
                      for it in truoc["items"]],
           "ghi_chu": "Số lượng khách yêu cầu, chưa thực thi; giá và tồn kho cần nhân viên kiểm tra."}
    tham_so = {"ma_don": ma, "ma_san_pham": sp, "so_luong": sl, "ly_do": ly_do[:500]}
    digest = hashlib.sha256(json.dumps(
        [truoc, tham_so], sort_keys=True, default=str).encode()).hexdigest()
    did, _ = await uy_quyen.tao_de_xuat(
        conversation_id=conversation_id,
        quyet=uy_quyen.QuyetDinh("sua_don", "goi_y", "co_phe_duyet"),
        ly_do_can_duyet="Chỉ đề xuất; nhân viên có quyền duyệt và xử lý ERP thủ công.",
        tham_so=tham_so,
        de_xuat={"tieu_de": f"Đề xuất sửa đơn {ma}", "ly_do": ly_do[:500],
                 "truoc": truoc, "sau": sau, "tao_boi": "agent"},
        can_cu={"nguon": ["Sổ đơn cùng hội thoại; ERP đọc sống nếu đã liên kết"],
                "thieu": ["Adapter chưa hỗ trợ sửa Sales Order; không tự động thực thi"],
                "rui_ro": ["Nhân viên phải kiểm lại giá, tồn kho và điều kiện giao hàng"]},
        khoa_trung=f"sua_don:{digest}", order_id=truoc["order_id"],
    )
    return {"da_de_xuat": True, "da_sua": False, "de_xuat_id": str(did),
            "ghi_chu": "Đã gửi đề xuất chờ duyệt. Đơn CHƯA sửa; nhân viên sẽ kiểm tra và xử lý."}


async def kiem_tra_bang_chung_thu_cong(dx: dict, *, ma_tham_chieu: str = "") -> dict:
    """
    Kiểm tra lại đơn hàng và đối soát bằng chứng xử lý thủ công trước khi đóng
    đề xuất `cho_xu_ly_thu_cong`. Chỉ ĐỌC sổ đơn và ERPNext, không tự ghi/sửa ERP.

    Bắt buộc đối chiếu số lượng thực tế của đúng `ma_san_pham` sau khi sửa với
    `so_luong` khách yêu cầu — không cho đóng chỉ vì `updated_at`, trạng thái
    hay trường không liên quan thay đổi.
    """
    oid = dx.get("order_id")
    cid = dx.get("conversation_id")
    if not oid or not cid:
        raise LoiThaoTacDon(409, "Đề xuất thiếu liên kết đơn hàng hoặc hội thoại; không thể đóng.")
    don = await db.fetchrow(
        "SELECT id, ma_don, trang_thai, items, updated_at, erp_ma_don, "
        "ma_van_don, trang_thai_giao_hang, yeu_cau_huy_luc "
        "FROM orders WHERE id = $1 AND conversation_id = $2",
        UUID(str(oid)),
        UUID(str(cid)),
    )
    if not don:
        raise LoiThaoTacDon(409, "Đơn hàng không còn tồn tại trong hội thoại; không thể xác nhận.")
    if don["trang_thai"] == "da_huy":
        raise LoiThaoTacDon(409, "Đơn hàng đã bị huỷ; không thể xác nhận đã sửa số lượng.")

    truoc = (dx.get("de_xuat") or {}).get("truoc") or {}
    ts = dx.get("tham_so") or {}
    items = don["items"]
    if isinstance(items, str):
        items = json.loads(items)
    items = items or []

    truoc_items = truoc.get("items") or []
    sp = str(ts.get("ma_san_pham") or "").strip()
    sl_moi = ts.get("so_luong")
    if not sp or type(sl_moi) is not int:
        raise LoiThaoTacDon(409, "Dữ liệu đề xuất thiếu mã sản phẩm hoặc số lượng yêu cầu.")

    dong_cu = [it for it in truoc_items if str(it.get("ma") or "") == sp]
    sl_cu = dong_cu[0].get("so_luong") if len(dong_cu) == 1 else None

    dong_sp = [it for it in items if str(it.get("ma") or "") == sp]
    if len(dong_sp) != 1:
        raise LoiThaoTacDon(
            409,
            f"Không tìm thấy duy nhất dòng sản phẩm «{sp}» trên đơn hiện tại; chưa thể đóng đề xuất.",
        )
    sl_thuc_te = dong_sp[0].get("so_luong")
    if sl_cu is not None and sl_thuc_te == sl_cu:
        raise LoiThaoTacDon(
            409,
            f"Chưa có bằng chứng sửa đơn: số lượng sản phẩm «{sp}» vẫn là {sl_thuc_te} "
            f"(khách yêu cầu {sl_moi}).",
        )
    if sl_thuc_te != sl_moi:
        raise LoiThaoTacDon(
            409,
            f"Số lượng thực tế của sản phẩm «{sp}» ({sl_thuc_te}) không khớp số lượng "
            f"khách yêu cầu ({sl_moi}); chưa thể đóng đề xuất.",
        )

    erp_changed = False
    erp_hien: dict[str, Any] | None = None
    truoc_erp = truoc.get("erp") or {}
    if don.get("erp_ma_don"):
        from agent.erp import nha_may

        try:
            erp_hien = await nha_may.cong().doc_don(don["erp_ma_don"])
        except Exception as exc:
            raise LoiThaoTacDon(
                503,
                "Chưa đọc được ERPNext để đối soát bằng chứng xử lý; chưa đóng đề xuất.",
            ) from exc
        if not erp_hien or erp_hien.get("name") != don["erp_ma_don"]:
            raise LoiThaoTacDon(409, "ERPNext không trả về Sales Order khớp với đơn hàng.")
        if (
            int(erp_hien.get("docstatus") or 0) == 2
            or str(erp_hien.get("status") or "").strip().lower() in {"cancelled", "canceled", "closed"}
        ):
            raise LoiThaoTacDon(
                409,
                "Sales Order trên ERPNext đã huỷ/đóng; không thể xác nhận đã sửa số lượng.",
            )
        erp_changed = (
            str(erp_hien.get("modified") or "") != str(truoc_erp.get("modified") or "")
            or (erp_hien.get("docstatus"), erp_hien.get("status"))
            != (truoc_erp.get("docstatus"), truoc_erp.get("status"))
        )
        if not erp_changed:
            raise LoiThaoTacDon(
                409,
                "Chưa có bằng chứng Sales Order ERPNext đã được cập nhật so với lúc đề xuất; "
                "cần xử lý trên ERPNext trước khi xác nhận.",
            )
        if isinstance(erp_hien.get("items"), list):
            dong_erp = [
                it for it in erp_hien["items"]
                if str(it.get("item_code") or it.get("ma") or "") == sp
            ]
            if len(dong_erp) != 1 or int(dong_erp[0].get("qty") or dong_erp[0].get("so_luong") or 0) != sl_moi:
                raise LoiThaoTacDon(
                    409,
                    f"Số lượng sản phẩm «{sp}» trên ERPNext không khớp yêu cầu ({sl_moi}); chưa thể đóng đề xuất.",
                )

    bang_chung: dict[str, Any] = {
        "ma_don": don["ma_don"],
        "trang_thai_don": don["trang_thai"],
        "updated_at": str(don["updated_at"]),
        "ma_san_pham": sp,
        "so_luong_truoc": sl_cu,
        "so_luong_yeu_cau": sl_moi,
        "so_luong_thuc_te": sl_thuc_te,
        "da_khop_so_luong_yeu_cau": True,
        "thay_doi_noi_bo": True,
    }
    if don.get("erp_ma_don") and erp_hien is not None:
        bang_chung["erp_ma_don"] = don["erp_ma_don"]
        bang_chung["erp_truoc_modified"] = str(truoc_erp.get("modified") or "")
        bang_chung["erp_sau"] = {k: erp_hien.get(k) for k in ("name", "docstatus", "status", "modified")}
        bang_chung["thay_doi_erp"] = bool(erp_changed)
    if ma_tham_chieu.strip():
        bang_chung["ma_tham_chieu"] = ma_tham_chieu.strip()[:120]
    return bang_chung


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
