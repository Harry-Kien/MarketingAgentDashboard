"""
API đơn hàng, tồn kho, danh mục và ảnh sản phẩm.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import (APIRouter, Depends, HTTPException, Query, Response)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import db
from agent.core import cong_viec as cong_viec_core, kho
from agent.erp.hop_dong import LoiERP

from .phu_thuoc import (
    _nguoi_id,
    bat_buoc_dang_nhap,
    can_quyen,
)

router = APIRouter(prefix="/api")


@router.get("/san-pham/{ma}/anh")
async def anh_san_pham_file(ma: str, _nguoi: dict = Depends(bat_buoc_dang_nhap), _quyen: dict = Depends(can_quyen("kho.doc"))):
    """
    Ảnh sản phẩm cho màn hình Kho và cho ô chọn khi nhân viên gửi ảnh.

    ĐƯỜNG DẪN DO MÁY CHỦ DỰNG, KHÔNG DO CLIENT
    ------------------------------------------
    `_anh_san_pham` tra mã trong danh mục rồi trả đường dẫn tương ứng. Client
    chỉ gửi MÃ, không gửi đường dẫn — nên một mã dạng `../../.env` không đi
    tới đâu cả: nó đơn giản không có trong danh mục.

    Đòi đăng nhập: ảnh sản phẩm không phải bí mật, nhưng mọi thứ dưới `/api`
    đều sau cổng đăng nhập, và mở một ngoại lệ là mở một đường để dò.
    """
    from agent.core.tools import _anh_san_pham

    duong = _anh_san_pham(ma)
    if duong is None or not duong.exists():
        raise HTTPException(404, f"Không có ảnh cho mã {ma}")
    return FileResponse(str(duong), media_type="image/jpeg")


# ---------------------------------------------------------------
#  Đơn hàng
# ---------------------------------------------------------------

@router.get("/orders")
async def list_orders(status: str | None = None, limit: int = 60, _quyen: dict = Depends(can_quyen("don.doc"))) -> list[dict]:
    # LỌC THEO KÊNH, như hội thoại và khách. Đơn mang SĐT và địa chỉ giao
    # hàng; trước 16.11.2026 route này trả đơn của MỌI kênh cho ai có
    # `don.doc` — nhân viên chỉ được giao kênh A đọc được danh bạ khách kênh
    # B qua màn Đơn hàng, lách đúng bộ lọc kênh mà màn Khách hàng giữ.
    #
    # Đơn nối kênh qua hội thoại sinh ra nó. Đơn mồ côi (hội thoại đã xoá
    # theo thời hạn lưu) không thuộc kênh nào → chỉ người xem-tất-cả thấy.
    # $1 = xem mọi kênh, $2 = người hỏi.
    #
    # Kèm trạng thái yêu cầu tạo vận đơn (DEV-08, bảng
    # shipping_waybill_requests) để màn Đơn hiện đơn cần đối soát tay.
    xem_tat_ca = any(q in (_quyen.get("quyen") or ())
                     for q in ("khach.xem_tat_ca", "hoi_thoai.xem_tat_ca"))
    sql = ("SELECT o.*, "
           "cv_ord.nen_tang AS nen_tang, "
           "r.trang_thai AS van_don_trang_thai_yeucau, "
           "r.client_order_code AS van_don_client_order_code, "
           "r.ly_do_chan AS van_don_ly_do_chan, "
           "r.so_lan_doi_soat AS van_don_so_lan_doi_soat, "
           "r.loi_cuoi AS van_don_loi_cuoi "
           "FROM orders o "
           "LEFT JOIN conversations cv_ord ON cv_ord.id = o.conversation_id "
           "LEFT JOIN shipping_waybill_requests r ON r.order_id = o.id "
           "WHERE ($1 OR EXISTS (SELECT 1 FROM conversations cv "
           "  JOIN account_memberships am ON am.account_id = cv.account_id "
           "  WHERE cv.id = o.conversation_id AND am.user_id = $2))")
    args: list = [xem_tat_ca, uuid.UUID(str(_quyen["id"]))]
    if status and status != "all":
        args.append(status)
        sql += f" AND o.trang_thai = ${len(args)}"
    sql += f" ORDER BY o.created_at DESC LIMIT {int(limit)}"
    rows = await db.fetch(sql, *args)
    return [
        {
            "id": str(r["id"]),
            "ma_don": r["ma_don"],
            "khach_ten": r["khach_ten"],
            "khach_sdt": r["khach_sdt"],
            "khach_dia_chi": r["khach_dia_chi"],
            "items": r["items"],
            "tong_tien": int(r["tong_tien"]),
            "trang_thai": r["trang_thai"],
            "channel": r["channel"],
            "nen_tang": r.get("nen_tang"),
            "ghi_chu": r["ghi_chu"],
            "conversation_id": str(r["conversation_id"]) if r["conversation_id"] else None,
            "created_at": r["created_at"].isoformat(),
            # Màn Đơn hàng VẼ các trường dưới (cờ "Khách xin huỷ", lỗi đồng bộ
            # ERP, mã vận đơn) — nhưng trước 29.10.2026 API không trả chúng,
            # nên cờ xin huỷ KHÔNG BAOỜ hiện: hàng vẫn gói, khách từ chối
            # nhận, shop chịu phí hoàn, không lỗi nào. Có test canh mọi trường
            # màn hình đọc đều có mặt ở đây.
            **{k: _iso(r.get(k)) for k in _TRUONG_PHU_DON},
            "van_don_trang_thai_yeucau": r.get("van_don_trang_thai_yeucau")
            or ("confirmed" if str(r.get("ma_van_don") or "").strip() else "not_sent"),
            "van_don_client_order_code": r.get("van_don_client_order_code") or r["ma_don"],
            "van_don_ly_do_chan": r.get("van_don_ly_do_chan"),
            "van_don_so_lan_doi_soat": int(r.get("van_don_so_lan_doi_soat") or 0),
            "van_don_loi_cuoi": r.get("van_don_loi_cuoi"),
        }
        for r in rows
    ]


_TRUONG_PHU_DON = (
    "yeu_cau_huy_luc", "yeu_cau_huy_ly_do",
    "yeu_cau_doi_tra_luc", "yeu_cau_doi_tra_loai", "yeu_cau_doi_tra_ly_do",
    "erp_ma_don", "erp_loi", "erp_so_lan_thu",
    "ma_van_don", "don_vi_van_chuyen", "trang_thai_giao_hang",
    "van_don_da_lay_hang",
    # Tiền khách đã trả trước (VietQR). Màn hình hiện "Đã thu Xđ" — thiếu ở
    # đây là người đóng gói không biết đơn đã trả, và vận đơn thu hộ lần hai.
    "so_tien_da_thu", "da_thu_luc", "phi_van_chuyen",
    "erp_van_chuyen_trang_thai", "erp_van_chuyen_so_lan_thu",
    "erp_van_chuyen_thu_lai_luc", "erp_van_chuyen_loi",
    "erp_van_chuyen_dong_bo_luc",
)

_VN_TZ = timezone(timedelta(hours=7))

_SQL_CAN_XU_LY = (
    "(o.trang_thai IN ('cho_duyet', 'cho_dong_bo') "
    "OR (o.yeu_cau_huy_luc IS NOT NULL AND o.trang_thai NOT IN ('da_huy', 'da_giao')) "
    "OR (o.yeu_cau_doi_tra_luc IS NOT NULL AND o.trang_thai <> 'da_huy') "
    "OR r.trang_thai IN ('sending', 'unknown_timeout', 'reconciling', 'manual_required') "
    "OR o.trang_thai_giao_hang IN ('delivery_failed', 'returning') "
    "OR o.erp_van_chuyen_trang_thai IN ('retry', 'dead'))"
)


def _pham_vi_don(nguoi: dict) -> tuple[bool, uuid.UUID]:
    xem_tat_ca = any(
        q in (nguoi.get("quyen") or ())
        for q in ("khach.xem_tat_ca", "hoi_thoai.xem_tat_ca")
    )
    return xem_tat_ca, uuid.UUID(str(nguoi["id"]))


def _dong_don_api(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "ma_don": r["ma_don"],
        "khach_ten": r["khach_ten"],
        "khach_sdt": r["khach_sdt"],
        "khach_dia_chi": r["khach_dia_chi"],
        "items": _items(r.get("items")),
        "tong_tien": int(r["tong_tien"]),
        "trang_thai": r["trang_thai"],
        "channel": r["channel"],
        "nen_tang": r.get("nen_tang"),
        "ghi_chu": r["ghi_chu"],
        "conversation_id": str(r["conversation_id"]) if r.get("conversation_id") else None,
        "created_at": _iso(r["created_at"]),
        "updated_at": _iso(r.get("updated_at")),
        **{k: _iso(r.get(k)) for k in _TRUONG_PHU_DON},
        "van_don_trang_thai_yeucau": r.get("van_don_trang_thai_yeucau")
        or ("confirmed" if str(r.get("ma_van_don") or "").strip() else "not_sent"),
        "van_don_client_order_code": r.get("van_don_client_order_code") or r["ma_don"],
        "van_don_ly_do_chan": r.get("van_don_ly_do_chan"),
        "van_don_so_lan_doi_soat": int(r.get("van_don_so_lan_doi_soat") or 0),
        "van_don_loi_cuoi": r.get("van_don_loi_cuoi"),
    }


def _ngay_dau(chu: str | None) -> datetime | None:
    s = (chu or "").strip()
    if not s:
        return None
    try:
        d = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=_VN_TZ)
        return d.astimezone(timezone.utc)
    except ValueError:
        raise HTTPException(422, "Ngày lọc phải có định dạng YYYY-MM-DD và là ngày hợp lệ") from None


@router.get("/orders/bang")
async def list_orders_bang(
    status: str = Query("all", max_length=32),
    q: str = Query("", max_length=120),
    channel: str = Query("all", max_length=40),
    thanh_toan: str = Query("all", max_length=32),
    van_chuyen: str = Query("all", max_length=32),
    tu_ngay: str = Query("", max_length=20),
    den_ngay: str = Query("", max_length=20),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=5, le=100),
    nguoi: dict = Depends(can_quyen("don.doc")),
) -> dict:
    """Danh sách đơn hàng dạng bảng: tìm kiếm, lọc đa chiều, KPI, đếm chip và phân trang."""
    xem_tat_ca, uid = _pham_vi_don(nguoi)
    from_sql = (
        "FROM orders o "
        "LEFT JOIN conversations cv_ord ON cv_ord.id = o.conversation_id "
        "LEFT JOIN shipping_waybill_requests r ON r.order_id = o.id "
    )
    base_where = (
        "($1 OR EXISTS (SELECT 1 FROM conversations cv "
        "  JOIN account_memberships am ON am.account_id = cv.account_id "
        "  WHERE cv.id = o.conversation_id AND am.user_id = $2))"
    )

    # 1. Tổng quan KPI và số đếm chip trong phạm vi kênh của người dùng
    summary_row = await db.fetchrow(
        f"""
        SELECT
            COUNT(*)::int AS tong_don,
            COUNT(*) FILTER (WHERE o.trang_thai = 'cho_duyet')::int AS cho_duyet,
            COUNT(*) FILTER (WHERE o.trang_thai = 'da_chot')::int AS da_chot,
            COUNT(*) FILTER (WHERE o.trang_thai = 'cho_dong_bo')::int AS cho_dong_bo,
            COUNT(*) FILTER (WHERE o.trang_thai = 'da_giao')::int AS da_giao,
            COUNT(*) FILTER (WHERE o.trang_thai = 'da_huy')::int AS da_huy,
            COUNT(*) FILTER (WHERE {_SQL_CAN_XU_LY})::int AS can_xu_ly
        {from_sql}
        WHERE {base_where}
        """,
        xem_tat_ca,
        uid,
    )
    kenh_rows = await db.fetch(
        f"""
        SELECT DISTINCT COALESCE(NULLIF(TRIM(LOWER(cv_ord.nen_tang)), ''), LOWER(o.channel)) AS kenh
        {from_sql}
        WHERE {base_where}
        ORDER BY 1
        """,
        xem_tat_ca,
        uid,
    )

    # 2. Bộ lọc chi tiết
    where = [base_where]
    args: list = [xem_tat_ca, uid]

    st = (status or "all").strip()
    if st == "can_xu_ly":
        where.append(_SQL_CAN_XU_LY)
    elif st and st != "all":
        args.append(st)
        where.append(f"o.trang_thai = ${len(args)}")

    tu = (q or "").strip()
    if tu:
        th = tu.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        args.append(th)
        idx_q = len(args)
        so = "".join(ch for ch in tu if ch.isdigit())
        if len(so) >= 3:
            args.append(so)
            idx_so = len(args)
            where.append(
                f"(o.ma_don ILIKE '%' || ${idx_q} || '%' "
                f"OR o.khach_ten ILIKE '%' || ${idx_q} || '%' "
                f"OR o.khach_sdt ILIKE '%' || ${idx_q} || '%' "
                f"OR regexp_replace(o.khach_sdt, '\\D', '', 'g') LIKE '%' || ${idx_so} || '%')"
            )
        else:
            where.append(
                f"(o.ma_don ILIKE '%' || ${idx_q} || '%' "
                f"OR o.khach_ten ILIKE '%' || ${idx_q} || '%' "
                f"OR o.khach_sdt ILIKE '%' || ${idx_q} || '%')"
            )

    ch = (channel or "all").strip().lower()
    if ch and ch != "all":
        if ch == "facebook":
            where.append(
                "(LOWER(o.channel) IN ('facebook', 'messenger') "
                "OR LOWER(COALESCE(cv_ord.nen_tang, '')) IN ('facebook', 'facebookpage', 'facebook_comment'))"
            )
        elif ch == "webchat":
            where.append(
                "(LOWER(o.channel) IN ('webchat', 'web') "
                "OR LOWER(COALESCE(cv_ord.nen_tang, '')) IN ('webchat', 'webwidget'))"
            )
        else:
            args.append(ch)
            idx_c = len(args)
            where.append(
                f"(LOWER(o.channel) = ${idx_c} OR LOWER(COALESCE(cv_ord.nen_tang, '')) = ${idx_c})"
            )

    tt_pay = (thanh_toan or "all").strip()
    if tt_pay == "chua_thu":
        where.append("COALESCE(o.so_tien_da_thu, 0) = 0")
    elif tt_pay == "thu_mot_phan":
        where.append("COALESCE(o.so_tien_da_thu, 0) > 0 AND COALESCE(o.so_tien_da_thu, 0) < o.tong_tien")
    elif tt_pay == "da_thu_du":
        where.append("COALESCE(o.so_tien_da_thu, 0) >= o.tong_tien AND o.tong_tien > 0")

    vc = (van_chuyen or "all").strip()
    if vc == "chua_tao":
        where.append(
            "NULLIF(TRIM(o.ma_van_don), '') IS NULL "
            "AND COALESCE(r.trang_thai, 'not_sent') NOT IN ('sending', 'unknown_timeout', 'reconciling', 'manual_required')"
        )
    elif vc == "cho_doi_soat":
        where.append(
            "NULLIF(TRIM(o.ma_van_don), '') IS NULL "
            "AND r.trang_thai IN ('sending', 'unknown_timeout', 'reconciling', 'manual_required')"
        )
    elif vc and vc != "all":
        args.append(vc)
        where.append(f"o.trang_thai_giao_hang = ${len(args)}")

    d_tu = _ngay_dau(tu_ngay)
    if d_tu is not None:
        args.append(d_tu)
        where.append(f"o.created_at >= ${len(args)}")
    d_den = _ngay_dau(den_ngay)
    if d_tu is not None and d_den is not None and d_tu > d_den:
        raise HTTPException(422, "Từ ngày không được sau Đến ngày")
    if d_den is not None:
        args.append(d_den + timedelta(days=1))
        where.append(f"o.created_at < ${len(args)}")

    where_sql = " AND ".join(where)
    total_row = await db.fetchrow(f"SELECT COUNT(*)::int AS n {from_sql} WHERE {where_sql}", *args)
    total = int((total_row or {}).get("n") or 0)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page_thuc = min(page, total_pages)
    offset = (page_thuc - 1) * page_size

    rows = await db.fetch(
        f"""
        SELECT o.*,
               cv_ord.nen_tang AS nen_tang,
               r.trang_thai AS van_don_trang_thai_yeucau,
               r.client_order_code AS van_don_client_order_code,
               r.ly_do_chan AS van_don_ly_do_chan,
               r.so_lan_doi_soat AS van_don_so_lan_doi_soat,
               r.loi_cuoi AS van_don_loi_cuoi
        {from_sql}
        WHERE {where_sql}
        ORDER BY o.created_at DESC, o.id DESC
        LIMIT {int(page_size)} OFFSET {int(offset)}
        """,
        *args,
    )

    s = dict(summary_row) if summary_row else {}
    return {
        "items": [_dong_don_api(dict(r)) for r in rows],
        "total": total,
        "page": page_thuc,
        "page_size": page_size,
        "total_pages": total_pages,
        "kpi": {
            "tong_don": int(s.get("tong_don") or 0),
            "cho_duyet": int(s.get("cho_duyet") or 0),
            "da_chot": int(s.get("da_chot") or 0),
            "can_xu_ly": int(s.get("can_xu_ly") or 0),
        },
        "dem_trang_thai": {
            "all": int(s.get("tong_don") or 0),
            "cho_duyet": int(s.get("cho_duyet") or 0),
            "da_chot": int(s.get("da_chot") or 0),
            "cho_dong_bo": int(s.get("cho_dong_bo") or 0),
            "da_giao": int(s.get("da_giao") or 0),
            "da_huy": int(s.get("da_huy") or 0),
        },
        "kenh_co": [r["kenh"] for r in kenh_rows if r.get("kenh")],
    }


@router.get("/orders/{order_id}")
async def get_order_detail(
    order_id: str,
    nguoi: dict = Depends(can_quyen("don.doc")),
) -> dict:
    """Chi tiết đầy đủ một đơn hàng cho side panel (Tổng quan / Vận chuyển / Đồng bộ ERP)."""
    oid = _uuid_don(order_id)
    xem_tat_ca, uid = _pham_vi_don(nguoi)
    r = await db.fetchrow(
        """
        SELECT o.*,
               cv_ord.nen_tang AS nen_tang,
               cv_ord.customer_name AS conv_customer_name,
               cv_ord.state AS conv_state,
               r.trang_thai AS van_don_trang_thai_yeucau,
               r.client_order_code AS van_don_client_order_code,
               r.ly_do_chan AS van_don_ly_do_chan,
               r.so_lan_doi_soat AS van_don_so_lan_doi_soat,
               r.loi_cuoi AS van_don_loi_cuoi,
               r.gui_luc AS van_don_gui_luc,
               r.xac_nhan_luc AS van_don_xac_nhan_luc,
               r.xac_nhan_boi AS van_don_xac_nhan_boi,
               r.doi_soat_tiep_luc AS van_don_doi_soat_tiep_luc
        FROM orders o
        LEFT JOIN conversations cv_ord ON cv_ord.id = o.conversation_id
        LEFT JOIN shipping_waybill_requests r ON r.order_id = o.id
        WHERE o.id = $1
          AND ($2 OR EXISTS (SELECT 1 FROM conversations cv
              JOIN account_memberships am ON am.account_id = cv.account_id
              WHERE cv.id = o.conversation_id AND am.user_id = $3))
        """,
        oid,
        xem_tat_ca,
        uid,
    )
    if r is None:
        raise HTTPException(404, "Không tìm thấy đơn hàng")

    don = _dong_don_api(dict(r))
    raw_ls = r.get("lich_su_giao_hang")
    if isinstance(raw_ls, str):
        try:
            raw_ls = json.loads(raw_ls)
        except ValueError:
            raw_ls = []
    don["lich_su_giao_hang"] = list(raw_ls or [])
    don["ngay_du_kien_giao"] = _iso(r.get("ngay_du_kien_giao"))
    don["cap_nhat_van_chuyen_luc"] = _iso(r.get("cap_nhat_van_chuyen_luc"))
    don["reconciliation"] = {
        "trang_thai": don["van_don_trang_thai_yeucau"],
        "client_order_code": don["van_don_client_order_code"],
        "ly_do_chan": don["van_don_ly_do_chan"],
        "so_lan_doi_soat": don["van_don_so_lan_doi_soat"],
        "loi_cuoi": don["van_don_loi_cuoi"],
        "gui_luc": _iso(r.get("van_don_gui_luc")),
        "xac_nhan_luc": _iso(r.get("van_don_xac_nhan_luc")),
        "xac_nhan_boi": r.get("van_don_xac_nhan_boi"),
        "doi_soat_tiep_luc": _iso(r.get("van_don_doi_soat_tiep_luc")),
    }
    don["conversation"] = (
        {
            "id": str(r["conversation_id"]),
            "customer_name": r.get("conv_customer_name") or r["khach_ten"],
            "channel": r["channel"],
            "nen_tang": r.get("nen_tang"),
            "state": r.get("conv_state"),
        }
        if r.get("conversation_id")
        else None
    )

    bd_rows = await db.fetch(
        "SELECT id, ma, thay_doi, ly_do, ma_don, ghi_chu, luc "
        "FROM kho_bien_dong WHERE ma_don = $1 ORDER BY luc DESC, id DESC LIMIT 30",
        r["ma_don"],
    )
    don["bien_dong_kho"] = [
        {
            "id": int(b["id"]),
            "ma": b["ma"],
            "thay_doi": int(b["thay_doi"]),
            "ly_do": b["ly_do"],
            "ghi_chu": b["ghi_chu"] or "",
            "luc": _iso(b["luc"]),
        }
        for b in bd_rows
    ]

    cv_rows = await db.fetch(
        "SELECT id, tieu_de, trang_thai, uu_tien, ket_qua, tao_luc, xong_luc "
        "FROM cong_viec WHERE order_id = $1 OR khoa_chong_trung LIKE $2 "
        "ORDER BY tao_luc DESC LIMIT 10",
        oid,
        f"%:{r['ma_don']}",
    )
    don["cong_viec"] = [
        {
            "id": str(c["id"]),
            "tieu_de": c["tieu_de"],
            "trang_thai": c["trang_thai"],
            "uu_tien": c["uu_tien"],
            "ket_qua": c.get("ket_qua") or "",
            "tao_luc": _iso(c["tao_luc"]),
            "xong_luc": _iso(c.get("xong_luc")),
        }
        for c in cv_rows
    ]
    return don


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _items(gia_tri) -> list[dict]:
    if isinstance(gia_tri, str):
        import json

        try:
            gia_tri = json.loads(gia_tri)
        except ValueError:
            return []
    return list(gia_tri or [])


def _uuid_don(order_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(404, "Không có đơn này") from None


class XacNhanKetQuaDonIn(BaseModel):
    cong_viec_id: uuid.UUID
    loai: Literal["sua", "huy"]
    ket_qua: Literal["thanh_cong", "khong_the", "cho_doi_soat"]
    ly_do: str = Field("", max_length=1000)
    # Với sửa đơn, Dashboard gửi đúng `modified` vừa đọc trên ERPNext.
    # Backend đọc lại và so khớp để không chốt theo một màn hình đã cũ.
    erp_modified_at: datetime | None = None


@router.get("/orders/{order_id}/action-evidence")
async def lay_bang_chung_xu_ly_don(
    order_id: str,
    cong_viec_id: uuid.UUID,
    nguoi: dict = Depends(can_quyen("don.sua", "cong_viec.sua")),
) -> dict:
    """Đọc snapshot ERP cho UI; không nhận timestamp do nhân viên tự nhập."""
    oid = _uuid_don(order_id)
    try:
        return await cong_viec_core.lay_bang_chung_xu_ly_don(
            order_id=oid,
            cong_viec_id=cong_viec_id,
            nguoi_id=uuid.UUID(str(nguoi["id"])),
            quyen=frozenset(nguoi.get("quyen") or ()),
        )
    except cong_viec_core.KhongTimThayXuLyDon as exc:
        raise HTTPException(404, str(exc)) from exc
    except cong_viec_core.KhongDuPhamViXuLyDon as exc:
        raise HTTPException(403, str(exc)) from exc
    except cong_viec_core.XungDotXuLyDon as exc:
        raise HTTPException(409, str(exc)) from exc
    except LoiERP as exc:
        raise HTTPException(
            503, "Chưa đọc được ERPNext; thử đối soát lại sau"
        ) from exc


@router.post("/orders/{order_id}/confirm-action-result")
async def xac_nhan_ket_qua_xu_ly_don(
    order_id: str,
    body: XacNhanKetQuaDonIn,
    response: Response,
    nguoi: dict = Depends(can_quyen("don.sua", "cong_viec.sua")),
) -> dict:
    """Ghi nhận kết quả người đã làm trên ERP; endpoint này chỉ ĐỌC ERP."""
    oid = _uuid_don(order_id)
    try:
        ket_qua = await cong_viec_core.xac_nhan_ket_qua_don(
            order_id=oid,
            cong_viec_id=body.cong_viec_id,
            loai=body.loai,
            ket_qua=body.ket_qua,
            ly_do=body.ly_do,
            erp_modified_at=body.erp_modified_at,
            nguoi_id=uuid.UUID(str(nguoi["id"])),
            quyen=frozenset(nguoi.get("quyen") or ()),
        )
    except cong_viec_core.KhongTimThayXuLyDon as exc:
        raise HTTPException(404, str(exc)) from exc
    except cong_viec_core.KhongDuPhamViXuLyDon as exc:
        raise HTTPException(403, str(exc)) from exc
    except cong_viec_core.XungDotXuLyDon as exc:
        await db.log_event(
            "order.action_result.mismatch",
            actor=nguoi.get("ten_dang_nhap", "?"),
            ref_id=body.cong_viec_id,
            order_id=str(oid),
            loai=body.loai,
        )
        raise HTTPException(409, str(exc)) from exc
    except cong_viec_core.CongViecHong as exc:
        raise HTTPException(422, str(exc)) from exc

    if not ket_qua.da_xu_ly_truoc:
        event = (
            "order.action_result.pending"
            if ket_qua.ket_qua == "cho_doi_soat"
            else "order.action_result.confirmed"
        )
        await db.log_event(
            event,
            actor=nguoi.get("ten_dang_nhap", "?"),
            ref_id=body.cong_viec_id,
            order_id=str(oid),
            loai=body.loai,
            ket_qua=ket_qua.ket_qua,
        )
    if ket_qua.ket_qua == "cho_doi_soat":
        response.status_code = 202
    return ket_qua.api_dict()


@router.post("/orders/{order_id}/approve")
async def approve_order(order_id: str, nguoi: dict = Depends(can_quyen("don.sua"))) -> dict:
    """
    Duyệt đơn đang CHỜ DUYỆT (đơn từ ngưỡng tự chốt trở lên) — rồi đẩy sang
    ERP như đơn agent tự chốt.

    Hai lỗi của bản trước (rà soát 29.10.2026):
      - Không kiểm trạng thái: bấm Duyệt trên một đơn ĐÃ HUỶ (hàng đã trả về
        kho) làm nó thành `da_chot` mà kho không trừ lại — bán một món không
        còn trên kệ. Nay chỉ `cho_duyet` → `da_chot`, nguyên tử trong một câu.
      - Không đẩy ERP: đơn lớn nhất không bao giờ vào ERP. Xem
        `day_don.day_don_da_luu`.
    """
    from agent.erp import day_don

    oid = _uuid_don(order_id)
    # Đặt lại `erp_so_lan_thu`: đơn về `cho_duyet` có thể vì vòng nền ERP đã
    # BỎ CUỘC sau 8 lần. Không đặt lại thì duyệt xong, ERP chớp một lần là
    # vòng nền thấy "đã thử 9 lần" và bỏ cuộc ngay — người sửa xong cấu hình
    # rồi bấm Duyệt mà đơn không bao giờ được thử lại (rà soát 11.2026).
    don = await db.fetchrow(
        "UPDATE orders SET trang_thai='da_chot', erp_so_lan_thu=0, erp_loi=NULL, "
        "updated_at=now() WHERE id=$1 AND trang_thai='cho_duyet' RETURNING *", oid,
    )
    if don is None:
        hien = await db.fetchrow("SELECT trang_thai FROM orders WHERE id=$1", oid)
        if hien is None:
            raise HTTPException(404, "Không có đơn này")
        raise HTTPException(
            409, f"Đơn đang ở trạng thái '{hien['trang_thai']}' — chỉ duyệt được "
                 "đơn đang chờ duyệt.")
    ten = str(nguoi.get("ten_dang_nhap") or nguoi.get("id") or "")
    await db.log_event(
        "order.approve", actor=ten or "system", ref_id=oid, ma_don=don["ma_don"],
        boi=ten, nguoi_phe_duyet=ten, nguon_thuc_thi="thu_cong",
        vai_tro=nguoi.get("vai_tro") or None,
    )
    # Duyệt ở màn Đơn hàng thì thẻ đề xuất AI của đơn này đã xong việc.
    # Duyệt QUA thẻ thì đề xuất đã ở `da_duyet`, câu này không chạm tới nó.
    from agent.core import thong_bao_noi_bo, uy_quyen

    await uy_quyen.dong_theo_don(oid, "duyet", boi=ten)
    await thong_bao_noi_bo.ket_thuc_duyet_don(None, oid)
    kq = await day_don.day_don_da_luu(
        oid, ma_don=don["ma_don"], khach_ten=str(don.get("khach_ten") or ""),
        khach_sdt=str(don.get("khach_sdt") or ""),
        khach_dia_chi=str(don.get("khach_dia_chi") or ""),
        items=_items(don.get("items")), ghi_chu=str(don.get("ghi_chu") or ""),
    )
    trang_thai = {"tu_choi": "da_huy", "cho_lai": "cho_dong_bo"}.get(kq.ket_cuc, "da_chot")
    return {"ok": kq.ket_cuc != "tu_choi", "ma_don": don["ma_don"], "trang_thai": trang_thai,
            "erp": kq.ket_cuc, "erp_ma_don": kq.erp_ma_don or None, "erp_loi": kq.ly_do or None}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, _quyen: dict = Depends(can_quyen("don.sua"))) -> dict:
    """
    Huỷ đơn và TRẢ HÀNG VỀ KHO — luật ở `agent/core/thao_tac_don.huy_don`,
    dùng chung với đề xuất "Huỷ đơn" của AI đã được duyệt.
    """
    from agent.core import thao_tac_don, uy_quyen

    oid = _uuid_don(order_id)
    ten = str(_quyen.get("ten_dang_nhap") or _quyen.get("id") or "")
    try:
        kq = await thao_tac_don.huy_don(oid, actor=ten or "system")
    except thao_tac_don.LoiThaoTacDon as exc:
        raise HTTPException(exc.ma, exc.thong_diep) from exc
    if kq.pop("da_huy_tu_truoc", False):
        return kq
    # Huỷ ở màn này thì thẻ đề xuất AI của chính đơn không được còn nút Duyệt.
    await uy_quyen.dong_theo_don(oid, "huy", boi=ten)
    return kq


class DaThuTienIn(BaseModel):
    # TỔNG đã thu của đơn tới giờ, không phải "thu thêm": bấm hai lần (mạng
    # chậm, hai tab) mà cộng dồn là COD bị trừ đôi và shop mất tiền.
    so_tien: int = Field(gt=0, le=1_000_000_000)
    ghi_chu: str = Field("", max_length=300)


@router.post("/orders/{order_id}/da-thu-tien")
async def da_thu_tien(order_id: str, body: DaThuTienIn,
                      nguoi: dict = Depends(can_quyen("don.sua"))) -> dict:
    """
    Ghi nhận khách ĐÃ TRẢ (chuyển khoản VietQR) — nút "Đã nhận tiền".

    Trước bản này không có chỗ nào ghi, và vận đơn luôn thu hộ COD bằng tổng
    tiền: khách đã chuyển khoản bị shipper thu lần nữa (rà soát 11.2026).
    Nay vận đơn thu hộ `tong_tien - so_tien_da_thu`
    (`shipping.service.tien_thu_ho`).

    Người bấm phải đối chiếu sao kê ngân hàng — hệ thống KHÔNG đọc được tài
    khoản ngân hàng. Ghi ai bấm, lúc nào, vào cả đơn lẫn nhật ký.
    """
    oid = _uuid_don(order_id)
    don = await db.fetchrow(
        "UPDATE orders SET so_tien_da_thu=$2, da_thu_luc=now(), da_thu_boi=$3, "
        "updated_at=now() WHERE id=$1 AND trang_thai <> 'da_huy' "
        "RETURNING ma_don, tong_tien, so_tien_da_thu, ma_van_don",
        oid, body.so_tien, _nguoi_id(nguoi),
    )
    if don is None:
        hien = await db.fetchrow("SELECT trang_thai FROM orders WHERE id=$1", oid)
        if hien is None:
            raise HTTPException(404, "Không có đơn này")
        raise HTTPException(409, "Đơn đã huỷ — tiền khách đã trả là việc hoàn tiền, "
                                 "không ghi vào đơn huỷ.")
    from agent.shipping.service import tien_thu_ho

    cod = tien_thu_ho(don)
    await db.log_event("thanh_toan.da_thu_tien", actor=nguoi.get("ten_dang_nhap") or "?",
                       ref_id=oid, ma_don=don["ma_don"], so_tien=body.so_tien,
                       ghi_chu=body.ghi_chu[:200], cod_con_lai=cod)
    kq: dict = {"ok": True, "ma_don": don["ma_don"],
                "so_tien_da_thu": int(don["so_tien_da_thu"]), "thu_ho_cod": cod}
    if don.get("ma_van_don"):
        # Vận đơn đã tạo với COD cũ. Hệ thống không sửa hộ phía hãng — nói
        # ra, kẻo shipper vẫn thu đủ tổng tiền.
        kq["can_sua_cod"] = (f"Vận đơn {don['ma_van_don']} đã tạo trước đó với tiền thu hộ "
                             f"cũ: vào trang hãng sửa COD thành {cod:,}đ.".replace(",", "."))
    return kq


@router.get("/van-chuyen/cau-hinh")
async def van_chuyen_cau_hinh(_quyen: dict = Depends(can_quyen("don.doc"))) -> dict:
    """Màn Đơn hàng hỏi: đã nối hãng thật chưa — để biết có hiện nút tạo vận đơn."""
    from agent.config import settings

    hang = (settings.shipping_provider or "mock").strip().lower()
    return {"hang": hang, "that": hang in HANG_THAT}


class VanDonIn(BaseModel):
    # Trống = hãng mặc định (SHIPPING_PROVIDER).
    hang: str = Field("", max_length=10)


@router.post("/orders/{order_id}/van-don")
async def tao_van_don(order_id: str, body: VanDonIn | None = None,
                      nguoi: dict = Depends(can_quyen("don.sua"))) -> dict:
    """
    Tạo vận đơn GHN/GHTK cho một đơn đã chốt — nút "Tạo vận đơn" trên màn
    Đơn hàng. Bốn chốt (trạng thái, đủ thông tin, đã giữ hàng, chống trùng)
    nằm trong `shipping.service.tao_van_don_cho_don`; hàm ấy có từ lâu nhưng
    trước 29.10.2026 không nối vào đâu cả.

    TỪ CHỐI hãng giả lập: vận đơn giả vẫn nhắn khách "đã bàn giao cho hãng,
    mã vận đơn …" — một mã không tra được ở đâu, cho một kiện chưa rời kệ.

    Khoá theo mã đơn trong lúc gọi hãng: bấm hai lần (hai tab, mạng chậm)
    không được tạo hai vận đơn — chốt "chưa có mã vận đơn" chỉ đọc, hai lời
    gọi cùng lúc đều thấy chưa có.
    """
    from agent.config import settings
    from agent.shipping import service

    hang = ((body.hang if body else "") or settings.shipping_provider or "mock").strip().lower()
    if hang not in HANG_THAT:
        raise HTTPException(
            409, f"Chưa nối hãng vận chuyển thật (đang là '{hang}'). Đặt SHIPPING_PROVIDER="
                 "ghn hoặc ghtk cùng khoá API của hãng trong .env rồi khởi động lại.")
    oid = _uuid_don(order_id)
    don = await db.fetchrow("SELECT ma_don FROM orders WHERE id=$1", oid)
    if don is None:
        raise HTTPException(404, "Không có đơn này")
    ma_don = don["ma_don"]
    async with db.pool().acquire() as conn:
        if not await conn.fetchval(
                "SELECT pg_try_advisory_lock(hashtext('van_don:' || $1))", ma_don):
            raise HTTPException(409, "Đang tạo vận đơn cho đơn này — đợi vài giây rồi tải lại.")
        try:
            kq = await service.tao_van_don_cho_don(ma_don, hang)
        finally:
            await conn.execute("SELECT pg_advisory_unlock(hashtext('van_don:' || $1))", ma_don)
    if not kq.ok:
        if kq.khong_ro_ket_qua:
            st_yeu_cau = (kq.thong_tin_them or {}).get("trang_thai_yeu_cau") or "unknown_timeout"
            ref_code = kq.client_order_code or (kq.thong_tin_them or {}).get("client_order_code") or ma_don
            await db.log_event(
                "shipping.tao_chua_ro_ket_qua",
                ref_id=oid,
                ma_don=ma_don,
                hang=hang,
                client_order_code=ref_code,
                trang_thai=st_yeu_cau,
                loi=(kq.loi or "")[:300],
                boi=nguoi.get("ten_dang_nhap"),
            )
            raise HTTPException(
                409,
                f"{kq.loi or 'Chưa rõ kết quả tạo vận đơn.'} "
                f"(trạng thái: {st_yeu_cau}, client_order_code: {ref_code})",
            )
        await db.log_event("shipping.tao_that_bai", ref_id=oid, ma_don=ma_don, hang=hang,
                           loi=(kq.loi or "")[:300], boi=nguoi.get("ten_dang_nhap"))
        raise HTTPException(422, kq.loi or "Hãng từ chối tạo vận đơn.")
    return {"ok": True, "ma_don": ma_don, "ma_van_don": kq.ma_van_don, "hang": hang,
            "phi_van_chuyen": kq.phi_van_chuyen,
            "client_order_code": kq.client_order_code or ma_don,
            "da_co_san": bool((kq.thong_tin_them or {}).get("da_co_san")),
            "erp_sync": (kq.thong_tin_them or {}).get("erp_sync")}


@router.get("/orders/{order_id}/shipping-reconciliation")
async def xem_doi_soat_van_don(
    order_id: str, _quyen: dict = Depends(can_quyen("don.doc"))
) -> dict:
    """Xem trạng thái yêu cầu tạo vận đơn và tiến trình đối soát với GHN."""
    from agent.shipping.doi_soat import lay_trang_thai_doi_soat

    oid = _uuid_don(order_id)
    don = await db.fetchrow(
        "SELECT id, ma_don, ma_van_don, don_vi_van_chuyen, trang_thai_giao_hang, "
        "erp_ma_don, erp_van_chuyen_trang_thai "
        "FROM orders WHERE id = $1",
        oid,
    )
    if don is None:
        raise HTTPException(404, "Không có đơn này")
    chi_tiet = await lay_trang_thai_doi_soat(oid)
    if chi_tiet is None:
        chi_tiet = {
            "order_id": str(oid),
            "ma_don": don["ma_don"],
            "provider": don.get("don_vi_van_chuyen") or "ghn",
            "client_order_code": don["ma_don"],
            "trang_thai": "confirmed" if don.get("ma_van_don") else "not_sent",
            "ma_van_don": don.get("ma_van_don"),
            "so_lan_gui": 1 if don.get("ma_van_don") else 0,
            "so_lan_doi_soat": 0,
            "ly_do_chan": None,
            "loi_cuoi": None,
            "cho_phep_tao_van_don": not bool(don.get("ma_van_don")),
        }
    return {
        "order_id": str(oid),
        "ma_don": don["ma_don"],
        "ma_van_don": don.get("ma_van_don"),
        "erp_van_chuyen_trang_thai": don.get("erp_van_chuyen_trang_thai"),
        "reconciliation": chi_tiet,
    }


@router.post("/orders/{order_id}/shipping-reconcile")
async def doi_soat_van_don_ngay(
    order_id: str, nguoi: dict = Depends(can_quyen("don.sua"))
) -> dict:
    """Nhân viên yêu cầu kiểm tra lại ngay trên GHN bằng `client_order_code` ổn định."""
    from agent.shipping.doi_soat import kiem_tra_lai_thu_cong

    oid = _uuid_don(order_id)
    kq = await kiem_tra_lai_thu_cong(
        oid, actor=str(nguoi.get("ten_dang_nhap") or "staff")
    )
    if not kq.get("ok") and kq.get("status_code") in (404, 409):
        raise HTTPException(int(kq["status_code"]), str(kq.get("loi") or "Không thể đối soát"))
    return kq


class XacNhanVanDonThuCongIn(BaseModel):
    ket_qua: Literal["da_co_van_don", "chua_tao_tren_ghn"]
    ma_van_don: str = Field("", max_length=64)
    ghi_chu: str = Field(min_length=5, max_length=500)


@router.post("/orders/{order_id}/shipping-manual-confirm")
async def xac_nhan_van_don_thu_cong(
    order_id: str,
    body: XacNhanVanDonThuCongIn,
    nguoi: dict = Depends(can_quyen("don.sua")),
) -> dict:
    """
    Nhân viên có quyền ghi nhận kết quả đối soát thủ công sau khi kiểm tra cổng GHN.
    Không bao giờ tự động tạo lại nếu thiếu xác nhận này khi tự đối soát chưa kết luận.
    """
    from agent.shipping.doi_soat import xac_nhan_thu_cong

    oid = _uuid_don(order_id)
    kq = await xac_nhan_thu_cong(
        oid,
        ket_qua=body.ket_qua,
        ma_van_don=body.ma_van_don,
        ghi_chu=body.ghi_chu,
        actor=str(nguoi.get("ten_dang_nhap") or "staff"),
    )
    if not kq.get("ok"):
        raise HTTPException(
            int(kq.get("status_code") or 409),
            str(kq.get("loi") or "Không xác nhận được"),
        )
    return kq


@router.post("/orders/{order_id}/shipping-erp-retry")
async def thu_lai_dong_bo_van_don_erp(
    order_id: str, nguoi: dict = Depends(can_quyen("don.sua"))
) -> dict:
    """Retry đúng bước ERP; endpoint này không gọi API tạo vận đơn GHN."""
    from agent.erp.dong_bo_van_don import cho_thu_lai, dong_bo_ngay

    oid = _uuid_don(order_id)
    don = await db.fetchrow(
        "SELECT id, ma_don, ma_van_don, erp_ma_don FROM orders WHERE id=$1", oid
    )
    if don is None:
        raise HTTPException(404, "Không có đơn này")
    if not don.get("ma_van_don"):
        raise HTTPException(409, "Đơn chưa có mã vận đơn GHN")
    if not don.get("erp_ma_don"):
        raise HTTPException(409, "Đơn chưa liên kết Sales Order ERPNext")
    if not await cho_thu_lai(don["ma_don"]):
        raise HTTPException(409, "Đồng bộ ERP đang được worker khác xử lý")
    await db.log_event(
        "shipping.erp_sync_manual_retry", actor=nguoi.get("ten_dang_nhap", "?"),
        ref_id=oid, ma_don=don["ma_don"], ma_van_don=don["ma_van_don"],
    )
    return await dong_bo_ngay(don["ma_don"])


# Hãng có bộ nối thật. `mock` cố ý KHÔNG có ở đây — xem `tao_van_don`.
HANG_THAT = ("ghn", "ghtk")


# ---------------------------------------------------------------
#  Kho hàng
# ---------------------------------------------------------------

class NhapKhoIn(BaseModel):
    so_luong: int = Field(gt=0, le=100000)
    ghi_chu: str = Field("", max_length=300)
    loai: Literal["nhap", "hoan_hang"] = "nhap"
    ma_don: str | None = Field(None, max_length=64)
    khoa_chong_trung: str | None = Field(None, max_length=120)


class KiemKeIn(BaseModel):
    so_luong_moi: int = Field(ge=0, le=100000)
    ly_do: str = Field(min_length=3, max_length=300)


@router.get("/kho")
async def kho_tong_quan(_quyen: dict = Depends(can_quyen("kho.doc"))) -> dict:
    """Tồn kho sống của mọi mã, kèm tên và giá lấy từ danh mục."""
    from agent.core.tools import _anh_san_pham, _catalog

    danh_muc = {p["ma"]: p for p in _catalog().get("san_pham", [])}
    ton = await db.fetch("SELECT ma, so_luong, cap_nhat_luc FROM ton_kho ORDER BY ma")

    # Giá của mã KHÔNG nằm trong danh mục thì hỏi ERP.
    #
    # `catalog.json` cố ý chỉ chứa hàng ĐANG BÁN — đó là thứ agent được phép
    # tư vấn, và nhồi hàng ngừng bán vào đó là agent bắt đầu chào bán chúng.
    # Nhưng màn Kho trả lời một câu hỏi KHÁC: "trong kho còn gì, đáng bao
    # nhiêu". Đo được 14.09.2026: 22 trong 35 dòng tồn kho là hàng thật đã
    # ngừng bán, còn 1.088 đơn vị, có giá đầy đủ ở ERPNext — và ô "Giá trị
    # tồn" bỏ sót toàn bộ, riêng một mã đã 28 triệu.
    #
    # Hỏi SONG SONG và chỉ hỏi mã còn thiếu: mỗi lời gọi là một vòng mạng,
    # và cổng đã có cache giá TTL dài nên lần sau gần như miễn phí.
    thieu_gia = [x["ma"] for x in ton if x["ma"] not in danh_muc]
    gia_erp: dict[str, int | None] = {}
    if thieu_gia:
        import asyncio as _asyncio

        from agent.erp import nha_may as _nha_may

        _cong = _nha_may.cong()

        async def _hoi_gia(ma: str):
            try:
                g = await _cong.gia(ma)
            except Exception:  # noqa: BLE001 — ERP sập không được làm mất bảng
                return ma, None
            return ma, (int(g.gia_ban) if g and g.gia_ban else None)

        for ma, g in await _asyncio.gather(*(_hoi_gia(m) for m in thieu_gia)):
            gia_erp[ma] = g

    ra = []
    for t in ton:
        sp = danh_muc.get(t["ma"], {})
        # None = CHƯA TRA ĐƯỢC, khác hẳn 0. Gộp hai thứ là nói dối một cách
        # tự tin: cộng thêm 0 vào "giá trị tồn" trông y hệt như món ấy không
        # đáng gì, trong khi sự thật là chưa biết.
        gia = sp.get("gia") if t["ma"] in danh_muc else gia_erp.get(t["ma"])
        ra.append({
            "ma": t["ma"],
            "ten": sp.get("ten", "(không có trong danh mục)"),
            "loai": sp.get("loai", ""),
            "gia": gia,
            "so_luong": int(t["so_luong"]),
            "sap_het": int(t["so_luong"]) <= kho.NGUONG_SAP_HET,
            "cap_nhat_luc": t["cap_nhat_luc"].isoformat(),
            # Người trực cần thấy ẢNH để đối chiếu khi khách mô tả sản phẩm
            # bằng lời — "cái chai xanh xanh ấy" — thay vì mở thư mục ra tìm.
            "co_anh": _anh_san_pham(t["ma"]) is not None,
            "dung_tich": sp.get("dung_tich", ""),
            "da_phu_hop": sp.get("da_phu_hop", []),
            "van_de_ho_tro": sp.get("van_de_ho_tro", []),
        })
    het = [x for x in ra if x["so_luong"] == 0]
    sap = [x for x in ra if 0 < x["so_luong"] <= kho.NGUONG_SAP_HET]
    return {
        "san_pham": ra,
        "tong_ma": len(ra),
        "het_hang": len(het),
        "sap_het": len(sap),
        "nguong_sap_het": kho.NGUONG_SAP_HET,
        "gia_tri_ton": sum(x["so_luong"] * (x["gia"] or 0) for x in ra),
        # Đếm ra chứ không giấu: không có con số này thì người đọc tưởng
        # tổng đã đủ, trong khi vài mã còn chưa tra được giá.
        "so_ma_chua_biet_gia": sum(1 for x in ra if x["gia"] is None),
    }


@router.get("/kho/bien-dong")
async def kho_bien_dong(ma: str = "", limit: int = 50, _quyen: dict = Depends(can_quyen("kho.doc"))) -> dict:
    return {"bien_dong": await kho.so_bien_dong(ma, limit)}


@router.get("/kho/bien-dong/bang")
async def kho_bien_dong_bang(
    q: str = Query("", max_length=120),
    ly_do: str = Query("all", max_length=32),
    chieu: str = Query("all", max_length=16),
    tu_ngay: str = Query("", max_length=20),
    den_ngay: str = Query("", max_length=20),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=5, le=100),
    _quyen: dict = Depends(can_quyen("kho.doc")),
) -> dict:
    """Sổ biến động kho dạng bảng: lọc theo từ khoá/loại/chiều/ngày, tồn sau và phân trang."""
    from agent.core.tools import _catalog

    d_tu = _ngay_dau(tu_ngay)
    d_den = _ngay_dau(den_ngay)
    if d_tu is not None and d_den is not None and d_tu > d_den:
        raise HTTPException(422, "Từ ngày không được sau Đến ngày")
    d_den_exclusive = (d_den + timedelta(days=1)) if d_den is not None else None
    ten_theo_ma = {p["ma"]: str(p.get("ten") or "") for p in _catalog().get("san_pham", []) if p.get("ma")}
    return await kho.so_bien_dong_bang(
        q=q,
        ly_do=ly_do,
        chieu=chieu,
        d_tu=d_tu,
        d_den_exclusive=d_den_exclusive,
        page=page,
        page_size=page_size,
        ten_theo_ma=ten_theo_ma,
    )


@router.get("/kho/{ma}/hoan-hang-info")
async def kho_hoan_hang_info(
    ma: str,
    ma_don: str = Query("", max_length=64),
    _quyen: dict = Depends(can_quyen("kho.doc")),
) -> dict:
    """Kiểm tra điều kiện và số lượng đã bán / đã hoàn / còn được nhập của đơn hàng hoàn."""
    return await kho.thong_tin_nhap_hoan(ma, ma_don)


@router.post("/kho/{ma}/nhap")
async def kho_nhap(ma: str, body: NhapKhoIn, nguoi: dict = Depends(can_quyen("kho.sua"))) -> dict:
    khoa = (body.khoa_chong_trung or "").strip()
    ma_don = (body.ma_don or "").strip()
    if body.loai == "hoan_hang":
        if not ma_don:
            raise HTTPException(422, "Nhập hàng hoàn bắt buộc phải nhập mã đơn hàng (ma_don).")
        try:
            actor_uid = uuid.UUID(str(nguoi["id"])) if nguoi.get("id") else None
        except ValueError:
            actor_uid = None
        try:
            r = await kho.nhap_hang_hoan(
                ma,
                body.so_luong,
                ma_don,
                body.ghi_chu,
                khoa_chong_trung=khoa,
                actor_id=actor_uid,
            )
        except kho.LoiNhapHangHoan as exc:
            raise HTTPException(exc.ma, exc.thong_diep) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not r.get("da_nhap_tu_truoc"):
            await db.log_event(
                "kho.nhap_hoan",
                actor=nguoi.get("ten_dang_nhap", "nguoi"),
                ma=ma,
                ma_don=ma_don,
                so_luong=body.so_luong,
                bien_dong_id=r.get("bien_dong_id"),
            )
        return r

    if ma_don:
        raise HTTPException(
            422,
            "Nhập kho thông thường không gắn mã đơn hàng — chọn loại 'hoan_hang' để nhập hàng hoàn.",
        )
    try:
        r = await kho.nhap_hang(ma, body.so_luong, body.ghi_chu, khoa_chong_trung=khoa)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not r.get("da_nhap_tu_truoc"):
        await db.log_event(
            "kho.nhap",
            actor=nguoi.get("ten_dang_nhap", "nguoi"),
            ma=ma,
            so_luong=body.so_luong,
            bien_dong_id=r.get("bien_dong_id"),
        )
    return r


@router.post("/kho/{ma}/kiem-ke")
async def kho_kiem_ke(ma: str, body: KiemKeIn, nguoi: dict = Depends(can_quyen("kho.sua"))) -> dict:
    """
    Đặt lại số tồn về đúng thực tế đếm được.

    Kho LUÔN lệch — vỡ, mất, đếm sai. Cần một đường sửa hợp lệ, và đường đó
    bắt buộc phải có lý do để sau này truy được.
    """
    try:
        r = await kho.dieu_chinh(ma, body.so_luong_moi, body.ly_do)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db.log_event("kho.kiem_ke", actor=nguoi.get("ten_dang_nhap", "nguoi"), **r, ly_do=body.ly_do)
    return r
