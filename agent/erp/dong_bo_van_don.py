"""Hàng đợi đồng bộ vận đơn PostgreSQL -> ERPNext cho DEV-02."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from agent import db
from agent.erp.hop_dong import TuChoiERP

SO_LAN_TOI_DA = 8
KHOA_QUA_HAN_PHUT = 15


async def _nhan_viec(ma_don: str | None = None) -> dict[str, Any] | None:
    """Nhận đúng một việc bằng SKIP LOCKED; worker khác không thể nhận trùng."""
    khoa = uuid.uuid4().hex
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            WITH viec AS (
                SELECT id
                FROM orders
                WHERE NULLIF(TRIM(ma_van_don), '') IS NOT NULL
                  AND NULLIF(TRIM(erp_ma_don), '') IS NOT NULL
                  AND ($1::text IS NULL OR ma_don = $1)
                  AND (
                    erp_van_chuyen_trang_thai = 'pending'
                    OR (erp_van_chuyen_trang_thai = 'retry'
                        AND COALESCE(erp_van_chuyen_thu_lai_luc, now()) <= now())
                    OR (erp_van_chuyen_trang_thai = 'processing'
                        AND erp_van_chuyen_khoa_luc <
                            now() - ($2::int * interval '1 minute'))
                  )
                ORDER BY COALESCE(erp_van_chuyen_thu_lai_luc, created_at), created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE orders o
            SET erp_van_chuyen_trang_thai = 'processing',
                erp_van_chuyen_khoa_luc = now(),
                erp_van_chuyen_khoa_boi = $3,
                erp_van_chuyen_so_lan_thu = erp_van_chuyen_so_lan_thu + 1,
                erp_van_chuyen_loi = NULL
            FROM viec
            WHERE o.id = viec.id
            RETURNING o.id, o.ma_don, o.erp_ma_don, o.ma_van_don,
                      o.don_vi_van_chuyen, o.trang_thai_giao_hang,
                      o.cap_nhat_van_chuyen_luc,
                      o.erp_van_chuyen_so_lan_thu, o.erp_van_chuyen_khoa_boi
            """,
            ma_don,
            KHOA_QUA_HAN_PHUT,
            khoa,
        )
    return dict(row) if row else None


async def _thanh_cong(viec: dict[str, Any]) -> str:
    """Chỉ chốt snapshot vừa ghi; webhook mới đến thì trả lại pending."""
    async with db.pool().acquire() as conn:
        trang_thai = await conn.fetchval(
            """
            UPDATE orders
            SET erp_van_chuyen_trang_thai = CASE
                    WHEN ma_van_don = $2
                     AND trang_thai_giao_hang IS NOT DISTINCT FROM $3
                     AND cap_nhat_van_chuyen_luc IS NOT DISTINCT FROM $4
                    THEN 'synced' ELSE 'pending' END,
                erp_van_chuyen_dong_bo_luc = CASE
                    WHEN ma_van_don = $2
                     AND trang_thai_giao_hang IS NOT DISTINCT FROM $3
                     AND cap_nhat_van_chuyen_luc IS NOT DISTINCT FROM $4
                    THEN now() ELSE erp_van_chuyen_dong_bo_luc END,
                erp_van_chuyen_thu_lai_luc = CASE
                    WHEN ma_van_don = $2
                     AND trang_thai_giao_hang IS NOT DISTINCT FROM $3
                     AND cap_nhat_van_chuyen_luc IS NOT DISTINCT FROM $4
                    THEN NULL ELSE now() END,
                erp_van_chuyen_loi = NULL,
                erp_van_chuyen_khoa_luc = NULL,
                erp_van_chuyen_khoa_boi = NULL,
                updated_at = now()
            WHERE id = $1 AND erp_van_chuyen_khoa_boi = $5
            RETURNING erp_van_chuyen_trang_thai
            """,
            viec["id"], viec["ma_van_don"], viec["trang_thai_giao_hang"],
            viec["cap_nhat_van_chuyen_luc"], viec["erp_van_chuyen_khoa_boi"],
        )
    return str(trang_thai or "pending")


async def _that_bai(viec: dict[str, Any], exc: Exception, vinh_vien: bool) -> str:
    so_lan = int(viec["erp_van_chuyen_so_lan_thu"] or 1)
    bo_cuoc = vinh_vien or so_lan >= SO_LAN_TOI_DA
    trang_thai = "dead" if bo_cuoc else "retry"
    # 1, 2, 4, ... phút; trần 60 phút để ERP hồi phục không tạo bão request.
    cho_phut = min(60, 2 ** max(0, so_lan - 1))
    await db.execute(
        """
        UPDATE orders
        SET erp_van_chuyen_trang_thai = $2,
            erp_van_chuyen_loi = $3,
            erp_van_chuyen_thu_lai_luc = CASE
                WHEN $2 = 'retry' THEN now() + ($4::int * interval '1 minute')
                ELSE NULL END,
            erp_van_chuyen_khoa_luc = NULL,
            erp_van_chuyen_khoa_boi = NULL,
            updated_at = now()
        WHERE id = $1 AND erp_van_chuyen_khoa_boi = $5
        """,
        viec["id"], trang_thai,
        f"{type(exc).__name__}: {exc}"[:500], cho_phut,
        viec["erp_van_chuyen_khoa_boi"],
    )
    if trang_thai == "dead":
        # Bỏ cuộc mà không ai biết là ERPNext mãi thiếu mã vận đơn của đơn
        # này — kế toán đối soát cuối tháng mới thấy. Việc hệ thống tự báo
        # nhân viên; khoá theo (đơn, vận đơn) để không sinh việc thứ hai.
        from agent.core import cong_viec

        await cong_viec.tao_tu_don_hang(
            str(viec["ma_don"]),
            tieu_de=f"Ghi tay mã vận đơn {viec['ma_van_don']} vào ERP cho đơn {viec['ma_don']}",
            mo_ta=(f"Đồng bộ vận đơn sang ERPNext đã bỏ cuộc: {type(exc).__name__}: "
                   f"{exc}"[:400]),
            khoa=f"erp_van_don:dead:{viec['ma_don']}:{viec['ma_van_don']}",
        )
    return trang_thai


async def _xu_ly(viec: dict[str, Any], nguon) -> dict[str, Any]:
    luc = viec["cap_nhat_van_chuyen_luc"] or datetime.now(timezone.utc)
    try:
        da_ghi = await nguon.dong_bo_van_don(
            erp_ma_don=str(viec["erp_ma_don"]),
            ma_van_don=str(viec["ma_van_don"]),
            don_vi=str(viec["don_vi_van_chuyen"] or "ghn"),
            trang_thai=str(viec["trang_thai_giao_hang"] or "delivering"),
            dong_bo_luc=luc,
            tham_chieu=str(viec["ma_don"]),
        )
        trang_thai = await _thanh_cong(viec)
        await db.log_event(
            "shipping.erp_synced", ref_id=viec["id"],
            ma_don=viec["ma_don"], erp_ma_don=viec["erp_ma_don"],
            ma_van_don=viec["ma_van_don"], da_ghi=da_ghi,
            snapshot_moi=trang_thai == "pending",
        )
        return {"ok": trang_thai == "synced", "trang_thai": trang_thai,
                "da_ghi": da_ghi}
    except TuChoiERP as exc:
        loi = f"{type(exc).__name__}: {exc}"[:300]
        trang_thai = await _that_bai(viec, exc, True)
    except Exception as exc:  # noqa: BLE001 - worker không được chết
        loi = f"{type(exc).__name__}: {exc}"[:300]
        trang_thai = await _that_bai(viec, exc, False)
    await db.log_event(
        "shipping.erp_sync_failed", ref_id=viec["id"],
        ma_don=viec["ma_don"], ma_van_don=viec["ma_van_don"],
        trang_thai=trang_thai,
    )
    return {"ok": False, "trang_thai": trang_thai, "loi": loi}


def _nguon_mac_dinh():
    from agent.erp import nha_may

    nguon = nha_may.tao_nguon()
    if not hasattr(nguon, "dong_bo_van_don"):
        raise TuChoiERP("Nguồn ERP hiện tại không hỗ trợ đồng bộ vận đơn")
    return nguon


async def _dong_nguon(nguon) -> None:
    client = getattr(nguon, "_client", None)
    aclose = getattr(client, "aclose", None)
    if callable(aclose):
        try:
            await aclose()
        except Exception:  # noqa: BLE001
            pass


async def dong_bo_ngay(ma_don: str, nguon=None) -> dict[str, Any]:
    """Thử một lần sau khi lưu GHN; thất bại được giữ lại cho worker."""
    viec = await _nhan_viec(ma_don)
    if viec is None:
        row = await db.fetchrow(
            "SELECT erp_van_chuyen_trang_thai, erp_van_chuyen_loi "
            "FROM orders WHERE ma_don=$1", ma_don,
        )
        return {"ok": bool(row and row.get("erp_van_chuyen_trang_thai") == "synced"),
                "trang_thai": (row or {}).get("erp_van_chuyen_trang_thai", "not_found"),
                "loi": (row or {}).get("erp_van_chuyen_loi")}
    tu_tao = None
    try:
        if nguon is None:
            tu_tao = _nguon_mac_dinh()
            nguon = tu_tao
    except Exception as exc:  # cấu hình sai cũng phải trả việc về hàng đợi
        trang_thai = await _that_bai(viec, exc, isinstance(exc, TuChoiERP))
        return {"ok": False, "trang_thai": trang_thai, "loi": str(exc)}
    try:
        return await _xu_ly(viec, nguon)
    finally:
        if tu_tao is not None:
            await _dong_nguon(tu_tao)


async def quet_dong_bo_van_don(nguon=None, gioi_han: int = 20) -> dict[str, int]:
    """Quét hàng đợi nền. Có thể tiêm adapter giả trong test."""
    dem = {"da_xet": 0, "dong_bo": 0, "cho_lai": 0, "dead": 0}
    tu_tao = None
    try:
        for _ in range(max(0, gioi_han)):
            viec = await _nhan_viec()
            if viec is None:
                break
            dem["da_xet"] += 1
            try:
                if nguon is None and tu_tao is None:
                    tu_tao = _nguon_mac_dinh()
                n = nguon or tu_tao
            except Exception as exc:
                st = await _that_bai(viec, exc, isinstance(exc, TuChoiERP))
                dem["dead" if st == "dead" else "cho_lai"] += 1
                continue
            kq = await _xu_ly(viec, n)
            if kq["trang_thai"] == "synced":
                dem["dong_bo"] += 1
            elif kq["trang_thai"] == "dead":
                dem["dead"] += 1
            else:
                dem["cho_lai"] += 1
    finally:
        if tu_tao is not None:
            await _dong_nguon(tu_tao)
    return dem


async def cho_thu_lai(ma_don: str) -> bool:
    """Người vận hành retry riêng bước ERP; tuyệt đối không gọi GHN."""
    tag = await db.execute(
        """
        UPDATE orders
        SET erp_van_chuyen_trang_thai='pending',
            erp_van_chuyen_thu_lai_luc=now(), erp_van_chuyen_loi=NULL,
            erp_van_chuyen_khoa_luc=NULL, erp_van_chuyen_khoa_boi=NULL,
            updated_at=now()
        WHERE ma_don=$1
          AND NULLIF(TRIM(ma_van_don), '') IS NOT NULL
          AND NULLIF(TRIM(erp_ma_don), '') IS NOT NULL
          AND erp_van_chuyen_trang_thai <> 'processing'
        """,
        ma_don,
    )
    return tag.endswith(" 1")
