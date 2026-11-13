"""
Đối soát tạo vận đơn GHN sau timeout / lỗi kết nối (DEV-08).

Vòng đời một yêu cầu tạo vận đơn trong `shipping_waybill_requests`:
  - `not_sent`: Chưa gửi yêu cầu đến GHN.
  - `sending`: Đang giữ claim gửi GHN (transaction DB đóng TRƯỚC khi gọi HTTP).
  - `confirmed`: GHN xác nhận tạo thành công và đã lưu `orders.ma_van_don`.
  - `rejected`: GHN từ chối tạo rõ ràng (hoặc nhân viên xác nhận GHN chưa tạo),
    an toàn để gửi lại cùng `client_order_code`.
  - `unknown_timeout`: Timeout / rớt mạng / HTTP 5xx / JSON lỗi — chưa xác định
    kết quả, CHẶN gửi tạo lại.
  - `reconciling`: Worker hoặc nhân viên đang đối soát với GHN.
  - `reconciled`: Đã đối soát khôi phục mã vận đơn và đồng bộ ERPNext (DEV-02).
  - `manual_required`: Tự đối soát không kết luận được hoặc vượt số lần thử,
    chờ nhân viên kiểm tra cổng GHN và xác nhận thủ công.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from agent import db
from .models import CreateWaybillResult, InternalShippingStatus

SO_LAN_DOI_SOAT_TOI_DA = 5
KHOA_GUI_QUA_HAN_GIAY = 300
KHOA_DOI_SOAT_QUA_HAN_GIAY = 180
_BACKOFF_GIAY = (30, 120, 300, 900, 1800)

TRANG_THAI_CHAN_TAO_LAI = frozenset({
    "sending",
    "unknown_timeout",
    "reconciling",
    "manual_required",
    "confirmed",
    "reconciled",
})


def _tinh_doi_soat_tiep(so_lan_doi_soat: int, *, base: datetime | None = None) -> datetime:
    now = base or datetime.now(timezone.utc)
    idx = min(max(0, so_lan_doi_soat - 1), len(_BACKOFF_GIAY) - 1)
    return now + timedelta(seconds=_BACKOFF_GIAY[idx])


def _chuan_hoa_trang_thai_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    ra = dict(row)
    for key in ("id", "order_id"):
        if ra.get(key) is not None:
            ra[key] = str(ra[key])
    for key in ("doi_soat_tiep_luc", "khoa_luc", "gui_luc", "xac_nhan_luc", "created_at", "updated_at"):
        if ra.get(key) is not None and hasattr(ra[key], "isoformat"):
            ra[key] = ra[key].isoformat()
    st = str(ra.get("trang_thai") or "not_sent")
    has_waybill = bool(str(ra.get("ma_van_don") or "").strip())
    ra["cho_phep_tao_van_don"] = (st in ("not_sent", "rejected")) and (not has_waybill)
    return ra


async def lay_trang_thai_doi_soat(order_id: uuid.UUID | str) -> dict[str, Any] | None:
    """Đọc trạng thái yêu cầu tạo vận đơn & đối soát theo `order_id` hoặc `ma_don`."""
    try:
        oid = uuid.UUID(str(order_id))
        row = await db.fetchrow(
            "SELECT * FROM shipping_waybill_requests WHERE order_id = $1",
            oid,
        )
    except ValueError:
        row = await db.fetchrow(
            "SELECT * FROM shipping_waybill_requests WHERE ma_don = $1",
            str(order_id),
        )
    return _chuan_hoa_trang_thai_row(dict(row) if row else None)


async def chot_luu_van_don_thanh_cong(
    *,
    order_id: uuid.UUID,
    ma_don: str,
    ma_van_don: str,
    provider_code: str,
    phi_van_chuyen: int = 0,
    ngay_du_kien_giao: datetime | None = None,
    trang_thai_noi_bo: InternalShippingStatus | None = None,
    du_lieu_phan_hoi: dict[str, Any] | None = None,
    trang_thai_yeu_cau: Literal["confirmed", "reconciled"] = "confirmed",
    xac_nhan_boi: str = "ghn_create",
    bang_chung_thu_cong: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Ghi nhận `ma_van_don` vào `orders` và cập nhật `shipping_waybill_requests`
    trong cùng một transaction ngắn, đồng thời bật cờ chờ đồng bộ ERPNext (DEV-02).
    """
    st_giao = (trang_thai_noi_bo or InternalShippingStatus.DELIVERING).value
    now = datetime.now(timezone.utc)
    payload_json = json.dumps(du_lieu_phan_hoi or {}, default=str, ensure_ascii=False)

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            order = await conn.fetchrow(
                """
                UPDATE orders
                SET ma_van_don = COALESCE(NULLIF(TRIM(ma_van_don), ''), $1),
                    don_vi_van_chuyen = COALESCE(NULLIF(TRIM(don_vi_van_chuyen), ''), $2),
                    trang_thai_giao_hang = COALESCE(NULLIF(TRIM(trang_thai_giao_hang), ''), $3),
                    phi_van_chuyen = COALESCE(NULLIF(phi_van_chuyen, 0), $4),
                    ngay_du_kien_giao = COALESCE(ngay_du_kien_giao, $5),
                    cap_nhat_van_chuyen_luc = COALESCE(cap_nhat_van_chuyen_luc, $6),
                    erp_van_chuyen_trang_thai = CASE
                        WHEN erp_ma_don IS NOT NULL AND erp_van_chuyen_trang_thai <> 'synced'
                            THEN 'pending'
                        WHEN erp_ma_don IS NOT NULL THEN erp_van_chuyen_trang_thai
                        ELSE 'not_required' END,
                    erp_van_chuyen_thu_lai_luc = CASE
                        WHEN erp_ma_don IS NOT NULL AND erp_van_chuyen_trang_thai <> 'synced'
                            THEN now()
                        ELSE erp_van_chuyen_thu_lai_luc END,
                    erp_van_chuyen_loi = CASE
                        WHEN erp_ma_don IS NOT NULL AND erp_van_chuyen_trang_thai <> 'synced'
                            THEN NULL
                        ELSE erp_van_chuyen_loi END,
                    updated_at = now()
                WHERE id = $7
                  AND (NULLIF(TRIM(ma_van_don), '') IS NULL OR ma_van_don = $1)
                RETURNING *
                """,
                ma_van_don,
                provider_code,
                st_giao,
                int(phi_van_chuyen or 0),
                ngay_du_kien_giao,
                now,
                order_id,
            )
            if order is None:
                hien = await conn.fetchrow(
                    "SELECT ma_van_don FROM orders WHERE id = $1", order_id
                )
                ma_hien = str((hien or {}).get("ma_van_don") or "")
                raise ValueError(
                    f"Đơn {ma_don} đã có mã vận đơn khác ({ma_hien}), "
                    f"từ chối ghi đè mã mới ({ma_van_don})."
                )

            if bang_chung_thu_cong is not None:
                evidence_json = json.dumps(bang_chung_thu_cong, default=str, ensure_ascii=False)
                await conn.execute(
                    """
                    UPDATE shipping_waybill_requests
                    SET trang_thai = $2,
                        ma_van_don = $3,
                        phi_van_chuyen = COALESCE(NULLIF($4::bigint, 0), phi_van_chuyen),
                        khoa_luc = NULL,
                        khoa_boi = NULL,
                        doi_soat_tiep_luc = NULL,
                        ly_do_chan = NULL,
                        loi_cuoi = NULL,
                        xac_nhan_luc = now(),
                        xac_nhan_boi = $5,
                        du_lieu_phan_hoi = $6::jsonb,
                        bang_chung_thu_cong = $7::jsonb,
                        updated_at = now()
                    WHERE order_id = $1
                    """,
                    order_id,
                    trang_thai_yeu_cau,
                    ma_van_don,
                    int(phi_van_chuyen or 0),
                    xac_nhan_boi,
                    payload_json,
                    evidence_json,
                )
            else:
                await conn.execute(
                    """
                    UPDATE shipping_waybill_requests
                    SET trang_thai = $2,
                        ma_van_don = $3,
                        phi_van_chuyen = COALESCE(NULLIF($4::bigint, 0), phi_van_chuyen),
                        khoa_luc = NULL,
                        khoa_boi = NULL,
                        doi_soat_tiep_luc = NULL,
                        ly_do_chan = NULL,
                        loi_cuoi = NULL,
                        xac_nhan_luc = now(),
                        xac_nhan_boi = $5,
                        du_lieu_phan_hoi = $6::jsonb,
                        updated_at = now()
                    WHERE order_id = $1
                    """,
                    order_id,
                    trang_thai_yeu_cau,
                    ma_van_don,
                    int(phi_van_chuyen or 0),
                    xac_nhan_boi,
                    payload_json,
                )
    return dict(order)


async def _nhan_viec_doi_soat(
    ma_don: str | None = None,
    *,
    bo_qua_lich_hen: bool = False,
) -> dict[str, Any] | None:
    """Nhận nguyên tử một yêu cầu đối soát bằng `FOR UPDATE SKIP LOCKED`."""
    khoa = uuid.uuid4().hex
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            WITH muc_tieu AS (
                SELECT id
                FROM shipping_waybill_requests
                WHERE ($1::text IS NULL OR ma_don = $1)
                  AND (
                    (
                        trang_thai = 'unknown_timeout'
                        AND ($2::boolean OR COALESCE(doi_soat_tiep_luc, now()) <= now())
                    )
                    OR (
                        trang_thai = 'sending'
                        AND khoa_luc IS NOT NULL
                        AND khoa_luc < now() - ($3::int * interval '1 second')
                    )
                    OR (
                        trang_thai = 'reconciling'
                        AND khoa_luc IS NOT NULL
                        AND khoa_luc < now() - ($4::int * interval '1 second')
                    )
                    OR (
                        $2::boolean
                        AND trang_thai = 'manual_required'
                        AND (
                            khoa_luc IS NULL
                            OR khoa_luc < now() - interval '10 seconds'
                        )
                    )
                  )
                ORDER BY COALESCE(doi_soat_tiep_luc, updated_at), created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE shipping_waybill_requests r
            SET trang_thai = 'reconciling',
                khoa_luc = now(),
                khoa_boi = $5,
                so_lan_doi_soat = r.so_lan_doi_soat + 1,
                updated_at = now()
            FROM muc_tieu
            WHERE r.id = muc_tieu.id
            RETURNING r.*
            """,
            ma_don,
            bo_qua_lich_hen,
            KHOA_GUI_QUA_HAN_GIAY,
            KHOA_DOI_SOAT_QUA_HAN_GIAY,
            khoa,
        )
    return dict(row) if row else None


async def doi_soat_mot_yeu_cau(
    viec: dict[str, Any],
    *,
    actor: str = "reconcile_worker",
    provider: Any | None = None,
) -> dict[str, Any]:
    """
    Thực thi một lượt đối soát cho `viec` đã được claim (`reconciling`).

    TUYỆT ĐỐI không giữ transaction DB khi gọi API GHN và không tự gọi
    `tao_van_don()` khi chưa xác minh an toàn.
    """
    from . import service

    order_id = viec["order_id"]
    ma_don = str(viec["ma_don"])
    provider_code = str(viec.get("provider") or "ghn")
    client_order_code = str(viec["client_order_code"])
    khoa_boi = viec.get("khoa_boi")

    # 1. Nếu chính DB `orders` hoặc `shipping_waybill_requests` đã giữ được mã
    #    vận đơn (ví dụ DB lỗi ở bước ghi cuối ngay sau khi GHN trả 200),
    #    khôi phục ngay mà không cần gọi lại GHN.
    order_row = await db.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)
    if not order_row:
        return {"ok": False, "trang_thai": "missing_order", "ma_don": ma_don}

    ma_van_don_san = str(
        order_row.get("ma_van_don") or viec.get("ma_van_don") or ""
    ).strip()
    if ma_van_don_san:
        order_saved = await chot_luu_van_don_thanh_cong(
            order_id=order_id,
            ma_don=ma_don,
            ma_van_don=ma_van_don_san,
            provider_code=provider_code,
            phi_van_chuyen=int(viec.get("phi_van_chuyen") or order_row.get("phi_van_chuyen") or 0),
            ngay_du_kien_giao=order_row.get("ngay_du_kien_giao"),
            du_lieu_phan_hoi=viec.get("du_lieu_phan_hoi") or {"recovered_from": "local_db"},
            trang_thai_yeu_cau="reconciled",
            xac_nhan_boi=actor,
        )
        sync_res = CreateWaybillResult(
            ok=True,
            ma_van_don=ma_van_don_san,
            don_vi=provider_code,
            phi_van_chuyen=int(order_saved.get("phi_van_chuyen") or 0),
            ngay_du_kien_giao=order_saved.get("ngay_du_kien_giao"),
            client_order_code=client_order_code,
        )
        await service._dong_bo_erp_sau_luu(order_saved, sync_res)
        await service._bao_khach(
            order_saved.get("conversation_id"),
            f"Dạ đơn {ma_don} của mình đã được bàn giao cho "
            f"{provider_code.upper()} rồi ạ.\n\n"
            f"Mã vận đơn: {ma_van_don_san}\n"
            "Mình tra mã này trên ứng dụng của hãng để xem hàng đang ở đâu "
            "nha. Có gì cần hỗ trợ mình cứ nhắn em ạ.",
            f"vandon-tao:{ma_van_don_san}",
        )
        await db.log_event(
            "shipping.reconcile_recovered_local",
            ref_id=order_id,
            actor=actor,
            ma_don=ma_don,
            ma_van_don=ma_van_don_san,
            client_order_code=client_order_code,
        )
        return {
            "ok": True,
            "trang_thai": "reconciled",
            "ma_don": ma_don,
            "ma_van_don": ma_van_don_san,
            "client_order_code": client_order_code,
            "erp_sync": sync_res.thong_tin_them.get("erp_sync"),
        }

    # 2. Hỏi GHN qua `client_order_code` ổn định đã lưu.
    prov = provider or service.get_provider(provider_code)
    lookup = await prov.tra_cuu_theo_ma_tham_chieu(client_order_code)

    if lookup.trang_thai == "found" and lookup.ma_van_don:
        order_saved = await chot_luu_van_don_thanh_cong(
            order_id=order_id,
            ma_don=ma_don,
            ma_van_don=lookup.ma_van_don,
            provider_code=provider_code,
            phi_van_chuyen=lookup.phi_van_chuyen,
            ngay_du_kien_giao=lookup.ngay_du_kien_giao,
            trang_thai_noi_bo=lookup.trang_thai_noi_bo,
            du_lieu_phan_hoi=lookup.du_lieu_goc,
            trang_thai_yeu_cau="reconciled",
            xac_nhan_boi=actor,
        )
        sync_res = CreateWaybillResult(
            ok=True,
            ma_van_don=lookup.ma_van_don,
            don_vi=provider_code,
            phi_van_chuyen=lookup.phi_van_chuyen,
            ngay_du_kien_giao=lookup.ngay_du_kien_giao,
            trang_thai_noi_bo=lookup.trang_thai_noi_bo or InternalShippingStatus.DELIVERING,
            client_order_code=client_order_code,
        )
        await service._dong_bo_erp_sau_luu(order_saved, sync_res)
        await service._bao_khach(
            order_saved.get("conversation_id"),
            f"Dạ đơn {ma_don} của mình đã được bàn giao cho "
            f"{prov.name} rồi ạ.\n\n"
            f"Mã vận đơn: {lookup.ma_van_don}\n"
            "Mình tra mã này trên ứng dụng của hãng để xem hàng đang ở đâu "
            "nha. Có gì cần hỗ trợ mình cứ nhắn em ạ.",
            f"vandon-tao:{lookup.ma_van_don}",
        )
        await db.log_event(
            "shipping.reconcile_found",
            ref_id=order_id,
            actor=actor,
            ma_don=ma_don,
            ma_van_don=lookup.ma_van_don,
            client_order_code=client_order_code,
            so_lan_doi_soat=int(viec.get("so_lan_doi_soat") or 1),
        )
        return {
            "ok": True,
            "trang_thai": "reconciled",
            "ma_don": ma_don,
            "ma_van_don": lookup.ma_van_don,
            "client_order_code": client_order_code,
            "erp_sync": sync_res.thong_tin_them.get("erp_sync"),
        }

    # 3. Chưa xác nhận được tồn tại vận đơn -> không tự ý gọi tạo mới.
    so_lan = int(viec.get("so_lan_doi_soat") or 1)
    can_chuyen_thu_cong = (
        lookup.trang_thai == "unsupported"
        or so_lan >= SO_LAN_DOI_SOAT_TOI_DA
    )
    payload_luu = json.dumps(
        {
            "lookup_trang_thai": lookup.trang_thai,
            "lookup_loi": lookup.loi,
            "lookup_data": lookup.du_lieu_goc,
        },
        default=str,
        ensure_ascii=False,
    )

    if can_chuyen_thu_cong:
        if lookup.trang_thai == "not_found":
            ly_do = (
                f"GHN báo không tìm thấy client_order_code '{client_order_code}' "
                f"sau {so_lan} lần đối soát; chưa tự tạo lại vì GHN không bảo đảm "
                "idempotency — cần nhân viên kiểm tra cổng GHN rồi xác nhận thủ công."
            )
        elif lookup.trang_thai == "unsupported":
            ly_do = (
                f"Hãng '{provider_code}' không hỗ trợ tra cứu theo client_order_code; "
                "cần nhân viên kiểm tra và xác nhận thủ công."
            )
        else:
            ly_do = (
                f"Không tra cứu được chắc chắn từ GHN sau {so_lan} lần đối soát; "
                "cần nhân viên kiểm tra cổng GHN và xác nhận thủ công."
            )
        await db.execute(
            """
            UPDATE shipping_waybill_requests
            SET trang_thai = 'manual_required',
                khoa_luc = NULL,
                khoa_boi = NULL,
                doi_soat_tiep_luc = NULL,
                ly_do_chan = $2,
                loi_cuoi = $3,
                du_lieu_phan_hoi = $4::jsonb,
                updated_at = now()
            WHERE id = $1 AND ($5::text IS NULL OR khoa_boi = $5)
            """,
            viec["id"],
            ly_do,
            (lookup.loi or ly_do)[:500],
            payload_luu,
            khoa_boi,
        )
        await db.log_event(
            "shipping.reconcile_escalated_manual",
            ref_id=order_id,
            actor=actor,
            ma_don=ma_don,
            client_order_code=client_order_code,
            lookup_status=lookup.trang_thai,
            so_lan_doi_soat=so_lan,
            loi=(lookup.loi or "")[:300],
        )
        return {
            "ok": False,
            "trang_thai": "manual_required",
            "ma_don": ma_don,
            "client_order_code": client_order_code,
            "lookup_status": lookup.trang_thai,
            "ly_do_chan": ly_do,
            "loi": lookup.loi,
        }

    tiep_theo = _tinh_doi_soat_tiep(so_lan)
    ly_do_tam = (
        f"Đang chờ đối soát GHN lần {so_lan + 1}/{SO_LAN_DOI_SOAT_TOI_DA} "
        f"(trạng thái tra cứu trước: {lookup.trang_thai})."
    )
    await db.execute(
        """
        UPDATE shipping_waybill_requests
        SET trang_thai = 'unknown_timeout',
            khoa_luc = NULL,
            khoa_boi = NULL,
            doi_soat_tiep_luc = $2,
            ly_do_chan = $3,
            loi_cuoi = $4,
            du_lieu_phan_hoi = $5::jsonb,
            updated_at = now()
        WHERE id = $1 AND ($6::text IS NULL OR khoa_boi = $6)
        """,
        viec["id"],
        tiep_theo,
        ly_do_tam,
        (lookup.loi or ly_do_tam)[:500],
        payload_luu,
        khoa_boi,
    )
    await db.log_event(
        "shipping.reconcile_retry_scheduled",
        ref_id=order_id,
        actor=actor,
        ma_don=ma_don,
        client_order_code=client_order_code,
        lookup_status=lookup.trang_thai,
        so_lan_doi_soat=so_lan,
        doi_soat_tiep_luc=tiep_theo.isoformat(),
    )
    return {
        "ok": False,
        "trang_thai": "unknown_timeout",
        "ma_don": ma_don,
        "client_order_code": client_order_code,
        "lookup_status": lookup.trang_thai,
        "doi_soat_tiep_luc": tiep_theo.isoformat(),
        "loi": lookup.loi,
    }


async def quet_doi_soat_van_don(limit: int = 10) -> dict[str, int]:
    """Quét và đối soát tối đa `limit` yêu cầu tạo vận đơn đang chờ."""
    dem = {"da_xu_ly": 0, "da_khoi_phuc": 0, "thu_lai": 0, "can_thu_cong": 0}
    for _ in range(max(1, limit)):
        viec = await _nhan_viec_doi_soat()
        if viec is None:
            break
        dem["da_xu_ly"] += 1
        kq = await doi_soat_mot_yeu_cau(viec, actor="reconcile_worker")
        if kq.get("trang_thai") == "reconciled":
            dem["da_khoi_phuc"] += 1
        elif kq.get("trang_thai") == "manual_required":
            dem["can_thu_cong"] += 1
        else:
            dem["thu_lai"] += 1
    return dem


async def kiem_tra_lai_thu_cong(
    order_id: uuid.UUID,
    *,
    actor: str,
    provider: Any | None = None,
) -> dict[str, Any]:
    """Nhân viên yêu cầu đối soát ngay với GHN theo `client_order_code` ổn định."""
    don = await db.fetchrow(
        "SELECT id, ma_don, ma_van_don, don_vi_van_chuyen FROM orders WHERE id = $1",
        order_id,
    )
    if don is None:
        return {"ok": False, "status_code": 404, "loi": "Không có đơn này"}

    req_row = await db.fetchrow(
        "SELECT * FROM shipping_waybill_requests WHERE order_id = $1",
        order_id,
    )
    if req_row is None:
        if don.get("ma_van_don"):
            return {
                "ok": True,
                "trang_thai": "confirmed",
                "ma_don": don["ma_don"],
                "ma_van_don": don["ma_van_don"],
            }
        return {
            "ok": False,
            "status_code": 409,
            "loi": "Đơn này chưa có yêu cầu tạo vận đơn cần đối soát.",
        }

    if don.get("ma_van_don") or req_row["trang_thai"] in ("confirmed", "reconciled"):
        return {
            "ok": True,
            "trang_thai": req_row["trang_thai"],
            "ma_don": don["ma_don"],
            "ma_van_don": don.get("ma_van_don") or req_row.get("ma_van_don") or "",
            "client_order_code": req_row["client_order_code"],
        }

    if req_row["trang_thai"] in ("not_sent", "rejected"):
        return {
            "ok": True,
            "trang_thai": req_row["trang_thai"],
            "ma_don": don["ma_don"],
            "client_order_code": req_row["client_order_code"],
            "cho_phep_tao_van_don": True,
        }

    # Đưa ngay vào hàng đợi ưu tiên nếu đang ở `unknown_timeout`/`manual_required`
    viec = await _nhan_viec_doi_soat(don["ma_don"], bo_qua_lich_hen=True)
    if viec is None:
        return {
            "ok": False,
            "status_code": 409,
            "loi": "Yêu cầu tạo vận đơn đang được gửi hoặc đối soát bởi tiến trình khác.",
        }

    await db.log_event(
        "shipping.reconcile_manual_trigger",
        ref_id=order_id,
        actor=actor,
        ma_don=don["ma_don"],
        client_order_code=viec["client_order_code"],
    )
    kq = await doi_soat_mot_yeu_cau(viec, actor=actor, provider=provider)
    return {**kq, "trang_thai_chi_tiet": await lay_trang_thai_doi_soat(order_id)}


async def xac_nhan_thu_cong(
    order_id: uuid.UUID,
    *,
    ket_qua: Literal["da_co_van_don", "chua_tao_tren_ghn"],
    ma_van_don: str = "",
    ghi_chu: str,
    actor: str,
) -> dict[str, Any]:
    """
    Nhân viên có quyền xác nhận kết quả sau khi kiểm tra trực tiếp trên GHN.

    - `da_co_van_don`: gắn `ma_van_don` thật, mở khóa `reconciled`, bật DEV-02 ERP sync.
    - `chua_tao_tren_ghn`: chỉ cho phép chuyển về `rejected` (an toàn tạo lại) với
      cùng `client_order_code` và ghi log bằng chứng bắt buộc.
    """
    from . import service

    ghi_chu_sach = str(ghi_chu or "").strip()
    if len(ghi_chu_sach) < 5:
        return {
            "ok": False,
            "status_code": 422,
            "loi": "Cần ghi rõ bằng chứng / ghi chú xác nhận (tối thiểu 5 ký tự).",
        }

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            don = await conn.fetchrow(
                "SELECT * FROM orders WHERE id = $1 FOR UPDATE", order_id
            )
            if don is None:
                return {"ok": False, "status_code": 404, "loi": "Không có đơn này"}

            req_row = await conn.fetchrow(
                "SELECT * FROM shipping_waybill_requests WHERE order_id = $1 FOR UPDATE",
                order_id,
            )
            if req_row is None:
                return {
                    "ok": False,
                    "status_code": 409,
                    "loi": "Đơn chưa có yêu cầu tạo vận đơn để xác nhận thủ công.",
                }

            ma_don = str(don["ma_don"])
            client_code = str(req_row["client_order_code"])
            provider_code = str(req_row.get("provider") or "ghn")
            ma_hien_co = str(don.get("ma_van_don") or "").strip()

            if ket_qua == "da_co_van_don":
                ma_moi = str(ma_van_don or "").strip()
                if not ma_moi:
                    return {
                        "ok": False,
                        "status_code": 422,
                        "loi": "Cần nhập `ma_van_don` khi xác nhận GHN đã tạo vận đơn.",
                    }
                if ma_hien_co and ma_hien_co != ma_moi:
                    return {
                        "ok": False,
                        "status_code": 409,
                        "loi": f"Đơn đã có mã vận đơn '{ma_hien_co}', không thể ghi đè thành '{ma_moi}'.",
                    }
            else:
                if ma_hien_co:
                    return {
                        "ok": False,
                        "status_code": 409,
                        "loi": f"Đơn đã có mã vận đơn '{ma_hien_co}', không thể đánh dấu chưa tạo trên GHN.",
                    }
                if req_row["trang_thai"] not in ("unknown_timeout", "reconciling", "manual_required"):
                    return {
                        "ok": False,
                        "status_code": 409,
                        "loi": f"Trạng thái hiện tại '{req_row['trang_thai']}' không cần mở khoá thủ công.",
                    }

                evidence = {
                    "ket_qua": "chua_tao_tren_ghn",
                    "ghi_chu": ghi_chu_sach,
                    "boi": actor,
                    "luc": datetime.now(timezone.utc).isoformat(),
                }
                await conn.execute(
                    """
                    UPDATE shipping_waybill_requests
                    SET trang_thai = 'rejected',
                        khoa_luc = NULL,
                        khoa_boi = NULL,
                        doi_soat_tiep_luc = NULL,
                        ly_do_chan = NULL,
                        loi_cuoi = $2,
                        xac_nhan_luc = now(),
                        xac_nhan_boi = $3,
                        bang_chung_thu_cong = $4::jsonb,
                        updated_at = now()
                    WHERE order_id = $1
                    """,
                    order_id,
                    f"Nhân viên xác nhận GHN chưa tạo đơn: {ghi_chu_sach}"[:500],
                    actor,
                    json.dumps(evidence, ensure_ascii=False),
                )

    if ket_qua == "chua_tao_tren_ghn":
        await db.log_event(
            "shipping.manual_confirm_absent",
            ref_id=order_id,
            actor=actor,
            ma_don=ma_don,
            client_order_code=client_code,
            ghi_chu=ghi_chu_sach,
        )
        return {
            "ok": True,
            "trang_thai": "rejected",
            "cho_phep_tao_van_don": True,
            "ma_don": ma_don,
            "client_order_code": client_code,
        }

    evidence = {
        "ket_qua": "da_co_van_don",
        "ma_van_don": ma_moi,
        "ghi_chu": ghi_chu_sach,
        "boi": actor,
        "luc": datetime.now(timezone.utc).isoformat(),
    }
    order_saved = await chot_luu_van_don_thanh_cong(
        order_id=order_id,
        ma_don=ma_don,
        ma_van_don=ma_moi,
        provider_code=provider_code,
        du_lieu_phan_hoi={"source": "manual_confirm", "ghi_chu": ghi_chu_sach},
        trang_thai_yeu_cau="reconciled",
        xac_nhan_boi=actor,
        bang_chung_thu_cong=evidence,
    )
    sync_res = CreateWaybillResult(
        ok=True,
        ma_van_don=ma_moi,
        don_vi=provider_code,
        client_order_code=client_code,
    )
    await service._dong_bo_erp_sau_luu(order_saved, sync_res)
    await service._bao_khach(
        order_saved.get("conversation_id"),
        f"Dạ đơn {ma_don} của mình đã được bàn giao cho "
        f"{provider_code.upper()} rồi ạ.\n\n"
        f"Mã vận đơn: {ma_moi}\n"
        "Mình tra mã này trên ứng dụng của hãng để xem hàng đang ở đâu "
        "nha. Có gì cần hỗ trợ mình cứ nhắn em ạ.",
        f"vandon-tao:{ma_moi}",
    )
    await db.log_event(
        "shipping.manual_confirm_found",
        ref_id=order_id,
        actor=actor,
        ma_don=ma_don,
        ma_van_don=ma_moi,
        client_order_code=client_code,
        ghi_chu=ghi_chu_sach,
    )
    return {
        "ok": True,
        "trang_thai": "reconciled",
        "ma_don": ma_don,
        "ma_van_don": ma_moi,
        "client_order_code": client_code,
        "erp_sync": sync_res.thong_tin_them.get("erp_sync"),
    }


async def vong_doi_soat_loop(chu_ky_giay: float = 30.0) -> None:
    """Vòng nền quét các yêu cầu tạo vận đơn GHN bị timeout/mất kết nối."""
    while True:
        try:
            await quet_doi_soat_van_don(limit=10)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — worker nền không được sập app
            try:
                await db.log_event(
                    "shipping.reconcile_loop_error",
                    actor="system",
                    loi=f"{type(exc).__name__}: {exc}"[:300],
                )
            except Exception:
                pass
        await asyncio.sleep(chu_ky_giay)
