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


_TRANG_THAI_DOI_SOAT_VD_CHAN = frozenset({
    "sending", "unknown_timeout", "reconciling", "manual_required",
})


async def huy_don(oid: UUID, *, actor: str, conversation_id: Any = None) -> dict:
    """
    Huỷ đơn theo nguyên tắc toàn vẹn tồn kho & vận đơn (BUG-17-04):

    - Chặn huỷ (`409`) khi:
      1. Đơn đã giao thành công (`da_giao` hoặc vận đơn `delivered`).
      2. Đơn đang treo đối soát tạo vận đơn (`sending`, `unknown_timeout`,
         `reconciling`, `manual_required`).
      3. Đơn đã có mã vận đơn nhưng hãng chưa xác nhận huỷ (`cancelled`) hoặc
         chưa hoàn hàng về kho (`returned`) — kể cả đơn cũ không rõ trạng thái
         lấy hàng (`trang_thai_giao_hang` rỗng).
    - Chỉ tự động trả kho (`kho.tra_hang`) khi chắc chắn hàng chưa rời kho:
      1. Chưa tạo vận đơn và không có yêu cầu tạo vận đơn đang treo, HOẶC
      2. Vận đơn đã được hãng xác nhận `cancelled` và `van_don_da_lay_hang IS FALSE`.
    - Khi vận đơn ở trạng thái `returned` hoặc `cancelled` nhưng thiếu bằng chứng
      chưa lấy hàng (đơn cũ `van_don_da_lay_hang IS NULL` hoặc đã lấy `TRUE`):
      KHÔNG tự động cộng tồn kho — sinh công việc kiểm tra thực tế trước khi
      nhập kho thủ công (Kho → Nhập), chống trùng theo `khoa_chong_trung`.
    - Khoá dòng theo cùng thứ tự (`orders` → `shipping_waybill_requests`) với
      `tao_van_don_cho_don` để chống race condition và deadlock.
    """
    from agent.core import cong_viec

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            hien = await conn.fetchrow(
                """
                SELECT trang_thai, conversation_id, ma_don, erp_ma_don,
                       ma_van_don, don_vi_van_chuyen, trang_thai_giao_hang,
                       van_don_da_lay_hang, so_tien_da_thu
                FROM orders WHERE id=$1 FOR UPDATE
                """,
                oid,
            )
            if hien is None:
                raise LoiThaoTacDon(404, "Không có đơn này")
            if conversation_id is not None and str(hien["conversation_id"]) != str(conversation_id):
                raise LoiThaoTacDon(409, "Đơn không thuộc hội thoại của đề xuất.")
            cu = str(hien["trang_thai"] or "")
            if cu == "da_huy":
                return {
                    "ok": True,
                    "da_huy_tu_truoc": True,
                    "ghi_chu": "Đơn đã huỷ từ trước, không trả kho lần nữa.",
                }
            if cu == "da_giao":
                raise LoiThaoTacDon(
                    409,
                    "Đơn đã giao — không huỷ được: hàng đang ở chỗ khách, huỷ là "
                    "cộng kho một món không có trên kệ. Xử lý như đổi trả: nhận "
                    "hàng về rồi nhập kho (Kho → Nhập).",
                )

            yc_vd = await conn.fetchrow(
                "SELECT trang_thai, ma_van_don FROM shipping_waybill_requests "
                "WHERE order_id = $1 FOR UPDATE",
                oid,
            )
            tt_yc = str((yc_vd or {}).get("trang_thai") or "")
            if tt_yc in _TRANG_THAI_DOI_SOAT_VD_CHAN:
                raise LoiThaoTacDon(
                    409,
                    f"Đơn đang chờ đối soát tạo vận đơn ({tt_yc}) — không thể huỷ "
                    "lúc này. Hoàn tất đối soát với hãng vận chuyển trước để tránh "
                    "vừa tạo vận đơn vừa trả kho.",
                )

            ma_vd = str(hien.get("ma_van_don") or (yc_vd or {}).get("ma_van_don") or "").strip()
            tt_giao = str(hien.get("trang_thai_giao_hang") or "").strip()

            if ma_vd:
                if tt_giao == "delivered":
                    raise LoiThaoTacDon(
                        409,
                        f"Vận đơn {ma_vd} đã giao thành công — không huỷ được. "
                        "Xử lý như đổi trả: nhận hàng về rồi nhập kho (Kho → Nhập).",
                    )
                if tt_giao == "ready_to_pick":
                    raise LoiThaoTacDon(
                        409,
                        f"Đơn đã có vận đơn {ma_vd} (chờ lấy hàng) — cần huỷ vận đơn "
                        "trên cổng hãng vận chuyển trước. Khi hãng xác nhận huỷ vận "
                        "đơn, hệ thống sẽ tự cập nhật đơn.",
                    )
                if tt_giao in ("delivering", "delivery_failed", "returning"):
                    nhan_tt = {
                        "delivering": "đang giao hàng",
                        "delivery_failed": "giao thất bại",
                        "returning": "đang hoàn hàng về kho",
                    }[tt_giao]
                    raise LoiThaoTacDon(
                        409,
                        f"Đơn đã có vận đơn {ma_vd} ({nhan_tt}) — hàng đã rời kho nên "
                        "không thể huỷ trực tiếp và không được cộng tồn kho. Liên hệ "
                        "hãng hoàn hàng; khi hãng xác nhận đã hoàn về kho, nhân viên "
                        "kiểm tra thực tế rồi nhập lại kho (Kho → Nhập).",
                    )
                if tt_giao not in ("cancelled", "returned"):
                    raise LoiThaoTacDon(
                        409,
                        f"Đơn đã có vận đơn {ma_vd} nhưng chưa xác định rõ trạng thái "
                        "lấy hàng/hoàn hàng — chặn huỷ tự động để tránh cộng tồn kho "
                        "sai. Kiểm tra vận đơn trên cổng hãng trước.",
                    )

            don = await conn.fetchrow(
                "UPDATE orders SET trang_thai='da_huy', updated_at=now() "
                "WHERE id=$1 AND trang_thai <> 'da_huy' "
                "RETURNING ma_don, erp_ma_don, ma_van_don, don_vi_van_chuyen, "
                "trang_thai_giao_hang, van_don_da_lay_hang, so_tien_da_thu, conversation_id",
                oid,
            )
    if don is None:
        return {
            "ok": True,
            "da_huy_tu_truoc": True,
            "ghi_chu": "Đơn đã huỷ từ trước, không trả kho lần nữa.",
        }

    ma_don = str(don["ma_don"])
    ma_vd_sau = str(don.get("ma_van_don") or "").strip()
    tt_giao_sau = str(don.get("trang_thai_giao_hang") or "").strip()
    da_lay_hang = don.get("van_don_da_lay_hang")

    so_dong = 0
    can_kiem_kho = False
    if not ma_vd_sau:
        so_dong = await kho.tra_hang(ma_don, ly_do="huy_don")
    elif tt_giao_sau == "cancelled" and da_lay_hang is False:
        so_dong = await kho.tra_hang(ma_don, ly_do="huy_don")
    elif tt_giao_sau == "returned":
        can_kiem_kho = True
        await cong_viec.tao_tu_don_hang(
            ma_don,
            tieu_de=f"Kiểm tra hàng hoàn đơn {ma_don}",
            mo_ta=(
                f"Đơn {ma_don} (vận đơn {ma_vd_sau}) đã hoàn về kho. Kiểm tra "
                "số lượng và tình trạng/nguyên seal sản phẩm trước khi nhập lại "
                "kho thủ công (Kho → Nhập). Hệ thống KHÔNG tự động cộng tồn kho."
            )[:1000],
            khoa=f"don_hang:kiem_hang_hoan:{ma_don}",
            conversation_id=don.get("conversation_id"),
            uu_tien="cao",
        )
    elif tt_giao_sau == "cancelled":
        can_kiem_kho = True
        await cong_viec.tao_tu_don_hang(
            ma_don,
            tieu_de=f"Kiểm tra tồn kho đơn {ma_don} (vận đơn đã huỷ)",
            mo_ta=(
                f"Đơn {ma_don} (vận đơn {ma_vd_sau}) đã huỷ nhưng không đủ bằng "
                "chứng hàng chưa rời kho (đơn cũ hoặc đã lấy hàng). Kiểm tra hàng "
                "thực tế tại kho trước khi nhập lại kho thủ công (Kho → Nhập)."
            )[:1000],
            khoa=f"don_hang:kiem_kho_huy_vd:{ma_don}",
            conversation_id=don.get("conversation_id"),
            uu_tien="cao",
        )

    await db.log_event(
        "order.cancel",
        actor=actor,
        ref_id=oid,
        ma_don=ma_don,
        so_mat_hang_tra_kho=so_dong,
        trang_thai_cu=cu,
        can_kiem_kho=can_kiem_kho,
    )
    from agent.core import thong_bao_noi_bo

    await thong_bao_noi_bo.ket_thuc_duyet_don(None, oid)
    kq: dict = {
        "ok": True,
        "ma_don": ma_don,
        "da_tra_kho": so_dong,
        "can_kiem_kho": can_kiem_kho,
    }
    # Huỷ ở đây KHÔNG huỷ bên ERP. Nói thẳng lúc bấm và tạo việc chống trùng
    # để nhân viên xử lý chứng từ bên ERPNext.
    ben = []
    if don.get("erp_ma_don"):
        ben.append(f"ERP (đơn {don['erp_ma_don']})")
        await cong_viec.tao_tu_don_hang(
            ma_don,
            tieu_de=f"Huỷ Sales Order {don['erp_ma_don']} trên ERPNext cho đơn {ma_don}",
            mo_ta=(
                f"Đơn nội bộ {ma_don} đã bị huỷ. Kiểm tra và huỷ Sales Order "
                f"{don['erp_ma_don']} trên ERPNext để tránh lệch số liệu kho/kế toán."
            )[:1000],
            khoa=f"don_hang:erp_huy_tay:{ma_don}",
            conversation_id=don.get("conversation_id"),
            uu_tien="cao",
        )
    elif cu == "cho_dong_bo":
        ben.append(
            f"ERP (đơn đang chờ đồng bộ — tra ERP theo mã {ma_don}, có thì huỷ)"
        )
        await cong_viec.tao_tu_don_hang(
            ma_don,
            tieu_de=f"Kiểm tra & huỷ đơn {ma_don} trên ERPNext (đang chờ đồng bộ)",
            mo_ta=(
                f"Đơn {ma_don} bị huỷ khi đang chờ đồng bộ ERPNext. Tra Sales Order "
                f"theo po_no={ma_don} trên ERPNext; nếu đã tạo thì huỷ tay."
            )[:1000],
            khoa=f"don_hang:erp_huy_tay:{ma_don}",
            conversation_id=don.get("conversation_id"),
            uu_tien="cao",
        )
    if ben:
        kq["can_huy_tay"] = (
            "Đơn đã có bên " + " và ".join(ben)
            + ": vào đó huỷ tay, hệ thống không tự huỷ hộ."
        )
        await db.log_event(
            "order.cancel_can_huy_tay",
            actor=actor,
            ref_id=oid,
            ma_don=ma_don,
            erp_ma_don=don.get("erp_ma_don"),
            ma_van_don=ma_vd_sau or None,
            trang_thai_cu=cu,
        )
    if int(don.get("so_tien_da_thu") or 0) > 0:
        kq["can_hoan_tien"] = (
            f"Khách đã trả trước {int(don['so_tien_da_thu']):,}đ".replace(",", ".")
            + " — nhớ hoàn tiền cho khách."
        )
    return kq
