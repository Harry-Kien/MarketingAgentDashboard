"""
Bộ điều phối nghiệp vụ vận chuyển: 4 chốt kiểm duyệt, xử lý Webhook và tra cứu Real-time.
"""
from __future__ import annotations

import hmac
from contextlib import suppress
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from agent import db
from agent.config import settings
from agent.core import cong_viec, kho
from . import doi_soat
from .base import BaseShippingProvider
from .ghn import GHNShippingProvider
from .ghtk import GHTKShippingProvider
from .mock import MockShippingProvider
from .models import (
    CreateWaybillRequest,
    CreateWaybillResult,
    InternalShippingStatus,
    ShippingItem,
    TRANG_THAI_DA_LAY_HANG,
    TrackingResult,
    WebhookEventResult,
)


def _jsonb(gia_tri: Any) -> Any:
    """
    Giá trị truyền vào tham số `$n::jsonb`: dict/list THƯỜNG, không phải chuỗi.

    Codec JSONB ở `agent/db.py` đã `json.dumps` hộ. Truyền chuỗi đã dumps
    là mã hoá HAI lần: cột lưu một chuỗi JSON thay vì một object, và mọi
    câu `du_lieu_phan_hoi->>'...'` trả NULL — lặng lẽ. Vòng qua
    `dumps(default=str)` rồi `loads` để datetime/Decimal vẫn ghi được.
    """
    return json.loads(json.dumps(gia_tri, default=str, ensure_ascii=False))


_PROVIDERS: dict[str, BaseShippingProvider] = {}


def get_provider(name: str | None = None) -> BaseShippingProvider:
    global _PROVIDERS
    key = ((settings.shipping_provider if name is None else name) or "").strip().lower()
    if key not in {"ghn", "ghtk", "mock"}:
        raise ValueError("Chưa chọn hãng vận chuyển hợp lệ (ghn/ghtk); mock chỉ dùng diễn tập.")
    if key not in _PROVIDERS:
        if key == "ghn":
            _PROVIDERS[key] = GHNShippingProvider()
        elif key == "ghtk":
            _PROVIDERS[key] = GHTKShippingProvider()
        else:
            _PROVIDERS[key] = MockShippingProvider(code=key, name="Mock Shipping Partner")
    return _PROVIDERS[key]


async def _bao_khach(conversation_id, text: str, khoa: str) -> None:
    """
    Gửi tin cho khách QUA OUTBOX. Không bao giờ gọi thẳng adapter.

    VÌ SAO
    ------
    Bản trước gọi `adapter.send_text(...)` rồi `except Exception: pass`. Bốn
    thứ mất cùng lúc:

        thử lại      provider lỗi một giây là tin bay mất
        chống trùng  webhook GHN phát lại là khách nhận hai lần
        lưu vết      tin KHÔNG vào bảng `messages`, nên nó không hiện trong
                     khung chat, Customer 360 không thấy, kiểm toán không có
        báo lỗi      `except: pass` nuốt im

    Mọi tin khác trong hệ thống đều đi qua outbox. Không có lý do gì để tin
    vận chuyển là ngoại lệ.

    Mục đích để mặc định `transactional`: báo mã đơn cho khách vừa đặt hàng
    là tin giao dịch, không phải quảng cáo. Xếp nhầm sang `marketing` là
    chốt chặn consent chặn luôn, và khách không nhận được mã đơn của chính
    mình.
    """
    if not conversation_id:
        return
    from agent.omnichannel.outbound_service import (
        OutboundService, PostgresOutboundRepository,
    )

    try:
        await OutboundService(PostgresOutboundRepository()).queue_text(
            conversation_id=conversation_id,
            role="system",
            text=text,
            idempotency_key=khoa,
        )
    except Exception as exc:  # noqa: BLE001
        # Vận đơn ĐÃ tạo ở phía hãng. Để lỗi gửi tin làm cả hàm ném là hàng
        # vẫn đi mà hệ thống tưởng chưa tạo — rồi có người tạo vận đơn thứ
        # hai cho cùng một đơn.
        #
        # Nhưng KHÔNG nuốt im: ghi lại để người trực báo khách bằng tay.
        await db.log_event(
            "shipping.bao_khach_that_bai", khoa=khoa[:80],
            error=f"{type(exc).__name__}: {exc}"[:200],
        )


def tien_thu_ho(order: dict) -> int:
    """
    Tiền shipper thu hộ (COD) = tổng hàng trừ phần khách ĐÃ trả trước.

    Bản trước luôn thu hộ bằng tổng tiền: khách đã chuyển khoản theo mã
    VietQR vẫn bị thu lần nữa lúc nhận hàng — và không có chỗ nào ghi là
    khách đã trả (rà soát 11.2026). `so_tien_da_thu` do người ghi bằng nút
    "Đã nhận tiền" trên màn Đơn hàng. Không bao giờ âm: khách trả dư (cả
    phí ship) thì COD là 0, không phải shipper trả lại tiền.
    """
    tong = int(order.get("tong_tien") or 0)
    da_thu = int(order.get("so_tien_da_thu") or 0)
    return max(0, tong - da_thu)


async def _dong_bo_erp_sau_luu(
    order: dict[str, Any], result: CreateWaybillResult
) -> None:
    """Thử riêng bước ERP; lỗi ERP không được làm mất kết quả GHN."""
    if not order.get("erp_ma_don"):
        result.thong_tin_them["erp_sync"] = {
            "ok": False, "trang_thai": "not_required",
            "loi": "Đơn chưa có liên kết Sales Order ERPNext",
        }
        return
    from agent.erp.dong_bo_van_don import dong_bo_ngay

    try:
        result.thong_tin_them["erp_sync"] = await dong_bo_ngay(
            str(order["ma_don"])
        )
    except Exception as exc:  # noqa: BLE001 - mã GHN vẫn phải được trả về
        result.thong_tin_them["erp_sync"] = {
            "ok": False, "trang_thai": "retry",
            "loi": f"{type(exc).__name__}: {exc}"[:300],
        }
        await db.log_event(
            "shipping.erp_sync_dispatch_failed", ref_id=order.get("id"),
            ma_don=order.get("ma_don"), ma_van_don=result.ma_van_don,
        )


def _st_giao_tu_don(order: dict[str, Any] | None) -> InternalShippingStatus:
    """Đọc trạng thái giao hàng thực tế trên đơn, tránh gán cứng DELIVERING."""
    raw = str((order or {}).get("trang_thai_giao_hang") or "").strip()
    if raw:
        try:
            return InternalShippingStatus(raw)
        except ValueError:
            pass
    return InternalShippingStatus.READY_TO_PICK


async def tao_van_don_cho_don(
    ma_don: str, provider_name: str | None = None
) -> CreateWaybillResult:
    """
    Tạo vận đơn cho đơn hàng với BỐN CHỐT KIỂM DUYỆT BẮT BUỘC:
      1. Chốt 1: Trạng thái đơn hợp lệ (da_chot / cho_duyet).
      2. Chốt 2: Đầy đủ thông tin người nhận (Tên, SĐT hợp lệ, Địa chỉ chi tiết, COD, Khối lượng).
      3. Chốt 3: Kho còn hàng & đã trừ kho thành công.
      4. Chốt 4: Chống tạo trùng (Đơn chưa có mã vận đơn).
    """
    try:
        provider = get_provider(provider_name)
    except ValueError as exc:
        return CreateWaybillResult(ok=False, loi=str(exc))
    order = await db.fetchrow(
        "SELECT * FROM orders WHERE ma_don = $1", ma_don
    )
    if not order:
        return CreateWaybillResult(ok=False, loi=f"Không tìm thấy đơn hàng mã '{ma_don}' trong CSDL.")

    # --- CHỐT 1: Trạng thái đơn hàng hợp lệ ---
    trang_thai = str(order.get("trang_thai", ""))
    if trang_thai in ("da_huy", "huy"):
        return CreateWaybillResult(ok=False, loi=f"Đơn hàng '{ma_don}' đã bị huỷ, không thể tạo vận đơn.")
    # `cho_duyet` KHÔNG được tạo vận đơn.
    #
    # Bản trước cho phép. Nhưng `cho_duyet` nghĩa là đơn vượt ngưỡng giá trị
    # và đang đợi NGƯỜI xác nhận — chốt chặn đó có mặt chính vì lý do đó.
    # Tạo vận đơn là hàng rời kho: nó đi vòng qua đúng cái chốt vừa dựng lên.
    if trang_thai == "cho_duyet":
        return CreateWaybillResult(
            ok=False,
            can_nguoi_xac_nhan=True,
            loi=(f"Đơn '{ma_don}' đang chờ người duyệt. Duyệt đơn trên "
                 "dashboard trước, rồi mới tạo vận đơn."),
        )
    if trang_thai not in ("da_chot",):
        return CreateWaybillResult(
            ok=False, loi=f"Đơn hàng đang ở trạng thái '{trang_thai}', chưa đủ điều kiện xuất kho."
        )

    # --- CHỐT 4: Chống tạo trùng vận đơn (Idempotency) ---
    ma_van_don_cu = str(order.get("ma_van_don") or "").strip()
    if ma_van_don_cu:
        result = CreateWaybillResult(
            ok=True,
            ma_van_don=ma_van_don_cu,
            don_vi=str(order.get("don_vi_van_chuyen") or "ghn"),
            phi_van_chuyen=int(order.get("phi_van_chuyen") or 0),
            ngay_du_kien_giao=order.get("ngay_du_kien_giao"),
            trang_thai_noi_bo=_st_giao_tu_don(order),
            thong_tin_them={"da_co_san": True, "ghi_chu": "Vận đơn đã được tạo trước đó."},
        )
        # Retry RIÊNG ERP (không gọi hãng lần nữa), trừ khi đã synced hoặc ERP đã huỷ (skipped_cancelled).
        tt_erp = str(order.get("erp_van_chuyen_trang_thai") or "")
        if order.get("erp_ma_don") and tt_erp not in ("synced", "skipped_cancelled"):
            await db.execute(
                "UPDATE orders SET erp_van_chuyen_trang_thai='pending', "
                "erp_van_chuyen_thu_lai_luc=now() WHERE id=$1 "
                "AND erp_van_chuyen_trang_thai NOT IN ('processing', 'skipped_cancelled')",
                order["id"],
            )
        if tt_erp == "skipped_cancelled":
            result.thong_tin_them["erp_sync"] = {
                "ok": True,
                "trang_thai": "skipped_cancelled",
                "loi": order.get("erp_van_chuyen_loi"),
            }
        else:
            await _dong_bo_erp_sau_luu(order, result)
        return result

    # --- CHỐT 2: Đầy đủ và chuẩn hóa thông tin giao nhận ---
    khach_ten = str(order.get("khach_ten") or "").strip()
    khach_sdt = "".join(c for c in str(order.get("khach_sdt") or "") if c.isdigit())
    khach_dia_chi = str(order.get("khach_dia_chi") or "").strip()

    thieu = []
    if not khach_ten:
        thieu.append("Tên người nhận")
    if len(khach_sdt) < 9 or len(khach_sdt) > 11:
        thieu.append("Số điện thoại hợp lệ (9-11 số)")
    if len(khach_dia_chi) < 10:
        thieu.append("Địa chỉ chi tiết (tối thiểu 10 ký tự)")

    raw_items = order.get("items") or []
    if isinstance(raw_items, str):
        try:
            raw_items = json.loads(raw_items)
        except Exception:
            raw_items = []
    if not raw_items:
        thieu.append("Danh sách sản phẩm trong đơn")

    if thieu:
        return CreateWaybillResult(
            ok=False,
            loi=f"Thiếu thông tin giao hàng: {', '.join(thieu)}. Vui lòng bổ sung trước khi đẩy vận đơn.",
        )

    # --- CHỐT 3: Tồn kho đã được giữ hàng (kiểm tra sổ biến động) ---
    bien_dong = await db.fetchrow(
        "SELECT 1 FROM kho_bien_dong WHERE ma_don = $1 AND ly_do = 'ban' LIMIT 1",
        ma_don,
    )
    if not bien_dong:
        # Thử trừ kho nếu chưa trừ
        ok_kho, ly_do_kho = await kho.giu_hang(raw_items, ma_don)
        if not ok_kho:
            return CreateWaybillResult(ok=False, loi=f"Không thể xuất kho: {ly_do_kho}")

    # Chuyển đổi danh sách items sang model ShippingItem
    shipping_items = []
    tong_gram = 0
    for it in raw_items:
        sl = max(1, int(it.get("so_luong") or 1))
        gram = sl * 200  # Ước lượng 200g mỗi sản phẩm mỹ phẩm
        tong_gram += gram
        shipping_items.append(
            ShippingItem(
                ma=str(it.get("ma") or "SKU"),
                ten=str(it.get("ten") or "Sản phẩm"),
                so_luong=sl,
                don_gia=int(it.get("don_gia") or 0),
                khoi_luong_gram=gram,
            )
        )

    tong_tien = int(order.get("tong_tien") or 0)
    provider = get_provider(provider_name)

    # --- CHỐT 5 (DEV-08): Yêu cầu tạo vận đơn nguyên tử & mã tham chiếu ổn định ---
    # Không giữ transaction PostgreSQL trong suốt lúc gọi HTTP ra GHN.
    claim_token = uuid.uuid4().hex
    claimed_client_code = ma_don
    khoa_bo_qua: CreateWaybillResult | None = None
    recover_existing: dict[str, Any] | None = None

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            order_locked = await conn.fetchrow(
                "SELECT * FROM orders WHERE id = $1 FOR UPDATE",
                order["id"],
            )
            if not order_locked:
                return CreateWaybillResult(
                    ok=False, loi=f"Không tìm thấy đơn hàng mã '{ma_don}' trong CSDL."
                )
            # Kiểm tra lại trạng thái đơn BÊN TRONG khoá FOR UPDATE để chống
            # tranh chấp khi nhân viên vừa bấm huỷ đơn đồng thời với tạo vận đơn.
            tt_locked = str(order_locked.get("trang_thai") or "")
            if tt_locked != "da_chot":
                return CreateWaybillResult(
                    ok=False,
                    loi=(
                        f"Đơn hàng '{ma_don}' không còn ở trạng thái đã chốt "
                        f"('{tt_locked}'), không thể tạo vận đơn."
                    ),
                )
            ma_vd_moi = str(order_locked.get("ma_van_don") or "").strip()
            if ma_vd_moi:
                try:
                    st_cu = InternalShippingStatus(
                        str(order_locked.get("trang_thai_giao_hang") or "ready_to_pick")
                    )
                except ValueError:
                    st_cu = InternalShippingStatus.READY_TO_PICK
                khoa_bo_qua = CreateWaybillResult(
                    ok=True,
                    ma_van_don=ma_vd_moi,
                    don_vi=str(order_locked.get("don_vi_van_chuyen") or provider.code),
                    phi_van_chuyen=int(order_locked.get("phi_van_chuyen") or 0),
                    ngay_du_kien_giao=order_locked.get("ngay_du_kien_giao"),
                    trang_thai_noi_bo=st_cu,
                    thong_tin_them={"da_co_san": True, "ghi_chu": "Vận đơn đã được tạo trước đó."},
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO shipping_waybill_requests (
                        order_id, ma_don, provider, client_order_code, trang_thai
                    )
                    VALUES ($1, $2, $3, $4, 'not_sent')
                    ON CONFLICT (order_id) DO NOTHING
                    """,
                    order["id"],
                    ma_don,
                    provider.code,
                    ma_don,
                )
                req_row = await conn.fetchrow(
                    "SELECT * FROM shipping_waybill_requests WHERE order_id = $1 FOR UPDATE",
                    order["id"],
                )
                claimed_client_code = str(req_row["client_order_code"])
                st_req = str(req_row["trang_thai"])
                now_db = datetime.now(timezone.utc)

                if st_req in ("confirmed", "reconciled") and str(req_row.get("ma_van_don") or "").strip():
                    recover_existing = dict(req_row)
                elif st_req == "sending":
                    khoa_luc = req_row.get("khoa_luc")
                    da_qua_han = (
                        khoa_luc is not None
                        and (now_db - khoa_luc).total_seconds() >= doi_soat.KHOA_GUI_QUA_HAN_GIAY
                    )
                    if da_qua_han:
                        ly_do = (
                            "Phiên gửi tạo vận đơn trước bị ngắt giữa chừng; "
                            "chuyển sang đối soát với GHN trước khi cho tạo lại."
                        )
                        await conn.execute(
                            """
                            UPDATE shipping_waybill_requests
                            SET trang_thai = 'unknown_timeout',
                                khoa_luc = NULL,
                                khoa_boi = NULL,
                                doi_soat_tiep_luc = now(),
                                ly_do_chan = $2,
                                updated_at = now()
                            WHERE id = $1
                            """,
                            req_row["id"],
                            ly_do,
                        )
                        st_req = "unknown_timeout"
                    else:
                        ly_do = "Đang có tiến trình khác gửi yêu cầu tạo vận đơn đến hãng — chặn gửi trùng."
                    khoa_bo_qua = CreateWaybillResult(
                        ok=False,
                        khong_ro_ket_qua=True,
                        don_vi=provider.code,
                        client_order_code=claimed_client_code,
                        thong_tin_them={
                            "trang_thai_yeu_cau": st_req,
                            "client_order_code": claimed_client_code,
                            "ly_do_chan": ly_do,
                        },
                        loi=ly_do,
                    )
                elif st_req in ("unknown_timeout", "reconciling", "manual_required"):
                    ly_do = str(req_row.get("ly_do_chan") or "").strip() or (
                        f"Yêu cầu tạo vận đơn đang ở trạng thái '{st_req}'; "
                        "phải đối soát hoặc xác nhận thủ công trước khi tạo lại."
                    )
                    khoa_bo_qua = CreateWaybillResult(
                        ok=False,
                        khong_ro_ket_qua=True,
                        can_nguoi_xac_nhan=(st_req == "manual_required"),
                        don_vi=provider.code,
                        client_order_code=claimed_client_code,
                        thong_tin_them={
                            "trang_thai_yeu_cau": st_req,
                            "client_order_code": claimed_client_code,
                            "ly_do_chan": ly_do,
                        },
                        loi=ly_do,
                    )
                else:
                    # Chỉ `not_sent` hoặc `rejected` mới được claim gửi tạo mới,
                    # luôn giữ nguyên `client_order_code` ban đầu.
                    await conn.execute(
                        """
                        UPDATE shipping_waybill_requests
                        SET trang_thai = 'sending',
                            provider = $2,
                            so_lan_gui = so_lan_gui + 1,
                            khoa_luc = now(),
                            khoa_boi = $3,
                            gui_luc = now(),
                            ly_do_chan = NULL,
                            loi_cuoi = NULL,
                            updated_at = now()
                        WHERE id = $1
                        """,
                        req_row["id"],
                        provider.code,
                        claim_token,
                    )

    if recover_existing is not None:
        ma_vd_san = str(recover_existing["ma_van_don"]).strip()
        order_saved = await doi_soat.chot_luu_van_don_thanh_cong(
            order_id=order["id"],
            ma_don=ma_don,
            ma_van_don=ma_vd_san,
            provider_code=str(recover_existing.get("provider") or provider.code),
            phi_van_chuyen=int(recover_existing.get("phi_van_chuyen") or 0),
            du_lieu_phan_hoi=recover_existing.get("du_lieu_phan_hoi") or {},
            trang_thai_yeu_cau="reconciled",
            xac_nhan_boi="local_req_recovery",
        )
        res_rec = CreateWaybillResult(
            ok=True,
            ma_van_don=ma_vd_san,
            don_vi=str(recover_existing.get("provider") or provider.code),
            phi_van_chuyen=int(recover_existing.get("phi_van_chuyen") or 0),
            trang_thai_noi_bo=_st_giao_tu_don(order_saved),
            thong_tin_them={"da_co_san": True, "khoi_phuc_tu_yeu_cau": True},
            client_order_code=claimed_client_code,
        )
        if str(order_saved.get("erp_van_chuyen_trang_thai") or "") == "skipped_cancelled":
            res_rec.thong_tin_them["erp_sync"] = {
                "ok": True,
                "trang_thai": "skipped_cancelled",
                "loi": order_saved.get("erp_van_chuyen_loi"),
            }
        else:
            await _dong_bo_erp_sau_luu(order_saved, res_rec)
        return res_rec

    if khoa_bo_qua is not None:
        if khoa_bo_qua.ok and khoa_bo_qua.ma_van_don:
            tt_erp_k = str(order.get("erp_van_chuyen_trang_thai") or "")
            if order.get("erp_ma_don") and tt_erp_k not in ("synced", "skipped_cancelled"):
                await db.execute(
                    "UPDATE orders SET erp_van_chuyen_trang_thai='pending', "
                    "erp_van_chuyen_thu_lai_luc=now() WHERE id=$1 "
                    "AND erp_van_chuyen_trang_thai NOT IN ('processing', 'skipped_cancelled')",
                    order["id"],
                )
            if tt_erp_k == "skipped_cancelled":
                khoa_bo_qua.thong_tin_them["erp_sync"] = {
                    "ok": True,
                    "trang_thai": "skipped_cancelled",
                    "loi": order.get("erp_van_chuyen_loi"),
                }
            else:
                await _dong_bo_erp_sau_luu(order, khoa_bo_qua)
        else:
            await db.log_event(
                "shipping.create_blocked_reconcile",
                ref_id=order["id"],
                ma_don=ma_don,
                client_order_code=claimed_client_code,
                trang_thai=(khoa_bo_qua.thong_tin_them or {}).get("trang_thai_yeu_cau"),
                ly_do=(khoa_bo_qua.loi or "")[:300],
            )
        return khoa_bo_qua

    req = CreateWaybillRequest(
        ma_don=ma_don,
        khach_ten=khach_ten,
        khach_sdt=khach_sdt,
        khach_dia_chi=khach_dia_chi,
        items=shipping_items,
        tong_tien=tong_tien,
        thu_ho_cod=tien_thu_ho(order),
        tong_khoi_luong_gram=max(300, tong_gram),
        ghi_chu=str(order.get("ghi_chu") or ""),
        client_order_code=claimed_client_code,
    )

    result = await provider.tao_van_don(req)
    if not result.client_order_code:
        result.client_order_code = claimed_client_code

    if result.ok and result.ma_van_don:
        try:
            order_saved = await doi_soat.chot_luu_van_don_thanh_cong(
                order_id=order["id"],
                ma_don=ma_don,
                ma_van_don=result.ma_van_don,
                provider_code=provider.code,
                phi_van_chuyen=result.phi_van_chuyen,
                ngay_du_kien_giao=result.ngay_du_kien_giao,
                trang_thai_noi_bo=result.trang_thai_noi_bo,
                du_lieu_phan_hoi=result.thong_tin_them,
                trang_thai_yeu_cau="confirmed",
                xac_nhan_boi="ghn_create",
            )
        except doi_soat.DonKhongConChot:
            # Vận đơn ĐÃ có bên hãng, đơn thì không còn `da_chot`. Không ai
            # huỷ hộ phía hãng — sinh việc, kẻo shipper vẫn tới lấy hàng.
            # Yêu cầu tạo vận đơn chuyển `manual_required` để không bị coi
            # là còn treo và không ai bấm tạo lại.
            with suppress(Exception):
                await db.execute(
                    "UPDATE shipping_waybill_requests SET trang_thai = 'manual_required', "
                    "ma_van_don = $2, khoa_luc = NULL, khoa_boi = NULL, "
                    "ly_do_chan = 'Đơn bị huỷ trong lúc chờ hãng; cần huỷ vận đơn bên hãng', "
                    "updated_at = now() WHERE order_id = $1 AND khoa_boi = $3",
                    order["id"], result.ma_van_don, claim_token)
            await db.log_event(
                "shipping.van_don_cho_don_da_huy", ma_don=ma_don,
                ma_van_don=result.ma_van_don, carrier=provider.code,
            )
            await cong_viec.tao_tu_van_chuyen(
                ma_don,
                tieu_de=f"Huỷ vận đơn {result.ma_van_don} bên {provider.name}",
                mo_ta=(f"Vận đơn {result.ma_van_don} được tạo cho đơn {ma_don}, "
                       "nhưng đơn đã bị huỷ (hoặc đổi trạng thái) trong lúc chờ hãng "
                       "trả lời. Vào trang hãng huỷ vận đơn này, kẻo shipper vẫn "
                       "tới lấy hàng."),
                khoa=f"van_chuyen:huy_tay:{result.ma_van_don}",
                conversation_id=order.get("conversation_id"),
            )
            return CreateWaybillResult(
                ok=False,
                loi=(f"Đơn {ma_don} không còn ở trạng thái đã chốt (vừa bị huỷ?) "
                     f"nhưng hãng ĐÃ tạo vận đơn {result.ma_van_don}. Vào trang "
                     "hãng huỷ tay vận đơn này — đã sinh việc nhắc."),
            )
        except Exception as db_exc:  # noqa: BLE001 — GHN đã tạo vận đơn nhưng DB lỗi khi lưu
            ly_do_db = (
                f"Hãng đã trả mã vận đơn '{result.ma_van_don}' nhưng lưu CSDL thất bại "
                f"({type(db_exc).__name__}); tạm khoá tạo lại để đối soát khôi phục."
            )
            try:
                await db.execute(
                    """
                    UPDATE shipping_waybill_requests
                    SET trang_thai = 'unknown_timeout',
                        ma_van_don = COALESCE(NULLIF(TRIM(ma_van_don), ''), $2),
                        phi_van_chuyen = COALESCE(NULLIF($3::bigint, 0), phi_van_chuyen),
                        doi_soat_tiep_luc = now(),
                        khoa_luc = NULL,
                        khoa_boi = NULL,
                        ly_do_chan = $4,
                        loi_cuoi = $5,
                        updated_at = now()
                    WHERE order_id = $1 AND khoa_boi = $6
                    """,
                    order["id"],
                    result.ma_van_don,
                    int(result.phi_van_chuyen or 0),
                    ly_do_db,
                    f"{type(db_exc).__name__}: {db_exc}"[:500],
                    claim_token,
                )
            except Exception:  # noqa: BLE001 — không nuốt trạng thái lỗi DB gốc
                pass
            try:
                await db.log_event(
                    "shipping.save_after_create_failed",
                    ref_id=order["id"],
                    ma_don=ma_don,
                    ma_van_don=result.ma_van_don,
                    client_order_code=claimed_client_code,
                    loi=f"{type(db_exc).__name__}: {db_exc}"[:300],
                )
            except Exception:
                pass
            return CreateWaybillResult(
                ok=False,
                khong_ro_ket_qua=True,
                ma_van_don=result.ma_van_don,
                don_vi=provider.code,
                phi_van_chuyen=result.phi_van_chuyen,
                ngay_du_kien_giao=result.ngay_du_kien_giao,
                client_order_code=claimed_client_code,
                thong_tin_them={
                    **(result.thong_tin_them or {}),
                    "db_save_failed": True,
                    "trang_thai_yeu_cau": "unknown_timeout",
                    "client_order_code": claimed_client_code,
                },
                loi=ly_do_db,
            )

        await db.log_event(
            "shipping.created",
            ma_don=ma_don,
            ma_van_don=result.ma_van_don,
            carrier=provider.code,
            phi=result.phi_van_chuyen,
            client_order_code=claimed_client_code,
        )

        await _dong_bo_erp_sau_luu(order_saved, result)

        # BÁO MÃ CHO KHÁCH.
        #
        # Bản trước lưu mã vào bảng rồi dừng. Khách chỉ nghe tin khi hàng ĐÃ
        # giao — tức suốt hai tới bốn ngày chờ, họ không biết đơn đã đi chưa
        # và không có mã để tự tra. Đó đúng là câu hỏi phổ biến nhất sau bán.
        #
        # KHÔNG hứa ngày giao: hệ thống đọc sổ cửa hàng, không đọc vị trí
        # kiện hàng theo thời gian thực. Đưa mã cho khách tự tra trên ứng
        # dụng hãng mới là thông tin chính xác.
        await _bao_khach(
            order_saved.get("conversation_id"),
            f"Dạ đơn {ma_don} của mình đã được bàn giao cho "
            f"{provider.name} rồi ạ.\n\n"
            f"Mã vận đơn: {result.ma_van_don}\n"
            "Mình tra mã này trên ứng dụng của hãng để xem hàng đang ở đâu "
            "nha. Có gì cần hỗ trợ mình cứ nhắn em ạ.",
            f"vandon-tao:{result.ma_van_don}",
        )
        return result

    if result.khong_ro_ket_qua:
        ly_do_treo = (
            f"Chưa xác định được kết quả tạo vận đơn phía {provider.code.upper()} "
            "(timeout/mất kết nối); đang chờ đối soát trước khi cho phép tạo lại."
        )
        await db.execute(
            """
            UPDATE shipping_waybill_requests
            SET trang_thai = 'unknown_timeout',
                doi_soat_tiep_luc = now(),
                khoa_luc = NULL,
                khoa_boi = NULL,
                ly_do_chan = $2,
                loi_cuoi = $3,
                du_lieu_phan_hoi = $4::jsonb,
                updated_at = now()
            WHERE order_id = $1 AND khoa_boi = $5
            """,
            order["id"],
            ly_do_treo,
            (result.loi or ly_do_treo)[:500],
            _jsonb(result.thong_tin_them or {}),
            claim_token,
        )
        await db.log_event(
            "shipping.create_unknown_timeout",
            ref_id=order["id"],
            ma_don=ma_don,
            carrier=provider.code,
            client_order_code=claimed_client_code,
            loi=(result.loi or "")[:300],
        )
        result.thong_tin_them["trang_thai_yeu_cau"] = "unknown_timeout"
        result.thong_tin_them["client_order_code"] = claimed_client_code
        result.thong_tin_them["ly_do_chan"] = ly_do_treo
        return result

    # Thất bại rõ ràng: hoặc kiểm tra trước khi gửi (chưa chạm GHN -> trả về
    # `not_sent`) hoặc hãng từ chối rõ ràng (`rejected`). Cả hai đều cho phép
    # gửi lại với CÙNG `client_order_code`.
    if result.can_nguoi_xac_nhan:
        await db.execute(
            """
            UPDATE shipping_waybill_requests
            SET trang_thai = 'not_sent',
                so_lan_gui = GREATEST(0, so_lan_gui - 1),
                khoa_luc = NULL,
                khoa_boi = NULL,
                loi_cuoi = $2,
                updated_at = now()
            WHERE order_id = $1 AND khoa_boi = $3
            """,
            order["id"],
            (result.loi or "")[:500],
            claim_token,
        )
    else:
        await db.execute(
            """
            UPDATE shipping_waybill_requests
            SET trang_thai = 'rejected',
                khoa_luc = NULL,
                khoa_boi = NULL,
                ly_do_chan = NULL,
                loi_cuoi = $2,
                du_lieu_phan_hoi = $3::jsonb,
                updated_at = now()
            WHERE order_id = $1 AND khoa_boi = $4
            """,
            order["id"],
            (result.loi or "")[:500],
            _jsonb(result.thong_tin_them or {}),
            claim_token,
        )
        await db.log_event(
            "shipping.create_rejected",
            ref_id=order["id"],
            ma_don=ma_don,
            carrier=provider.code,
            client_order_code=claimed_client_code,
            loi=(result.loi or "")[:300],
        )

    return result


async def tra_cuu_van_don(ma_tra_cuu: str) -> TrackingResult:
    """
    Tra cứu thời gian thực theo mã đơn hoặc mã vận đơn.
    """
    ma_sach = ma_tra_cuu.strip()
    order = await db.fetchrow(
        "SELECT * FROM orders WHERE ma_don = $1 OR ma_van_don = $1", ma_sach
    )
    if not order:
        # Thử tra trực tiếp sang hãng nếu là mã vận đơn rời
        try:
            provider = get_provider()
        except ValueError as exc:
            return TrackingResult(ok=False, ma_van_don=ma_sach, don_vi="",
                                  trang_thai_noi_bo=InternalShippingStatus.DELIVERING,
                                  trang_thai_goc="khong_tra_duoc", loi=str(exc))
        return await provider.tra_cuu(ma_sach)

    ma_van_don = str(order.get("ma_van_don") or "").strip()
    if not ma_van_don:
        return TrackingResult(
            ok=True,
            ma_van_don="",
            don_vi=str(order.get("don_vi_van_chuyen") or "ghn"),
            trang_thai_noi_bo=InternalShippingStatus.DELIVERING,
            trang_thai_goc="chua_tao_van_don",
            vi_tri_hien_tai="Kho hàng shop (Đang chuẩn bị đóng gói)",
            loi="Đơn hàng đang được chuẩn bị tại kho, chưa bàn giao cho bưu tá.",
        )

    provider_name = str(order.get("don_vi_van_chuyen") or "mock")
    try:
        provider = get_provider(provider_name)
    except ValueError as exc:
        return TrackingResult(ok=False, ma_van_don=ma_van_don, don_vi=provider_name,
                              trang_thai_noi_bo=InternalShippingStatus.DELIVERING,
                              trang_thai_goc="khong_tra_duoc", loi=str(exc))
    result = await provider.tra_cuu(ma_van_don)

    # Cập nhật lại vị trí / trạng thái vào CSDL nếu có thay đổi
    if result.ok:
        da_lay = result.trang_thai_noi_bo in TRANG_THAI_DA_LAY_HANG
        await db.execute(
            """
            UPDATE orders
            SET trang_thai_giao_hang = $1,
                van_don_da_lay_hang = CASE
                    WHEN van_don_da_lay_hang IS TRUE OR $3 THEN TRUE
                    ELSE van_don_da_lay_hang END,
                cap_nhat_van_chuyen_luc = now(),
                erp_van_chuyen_trang_thai = CASE
                    WHEN erp_ma_don IS NOT NULL
                     AND erp_van_chuyen_trang_thai <> 'skipped_cancelled'
                     AND trang_thai_giao_hang IS DISTINCT FROM $1
                    THEN 'pending' ELSE erp_van_chuyen_trang_thai END,
                erp_van_chuyen_thu_lai_luc = CASE
                    WHEN erp_ma_don IS NOT NULL
                     AND erp_van_chuyen_trang_thai <> 'skipped_cancelled'
                     AND trang_thai_giao_hang IS DISTINCT FROM $1
                    THEN now() ELSE erp_van_chuyen_thu_lai_luc END,
                updated_at = now()
            WHERE ma_van_don = $2
            """,
            result.trang_thai_noi_bo.value,
            ma_van_don,
            da_lay,
        )

    return result


def kiem_bi_mat_webhook(headers: dict[str, Any], query_token: str = "") -> tuple[bool, str]:
    """
    Cổng duy nhất canh webhook vận chuyển. Trả (cho qua, lý do từ chối).

    VÌ SAO BÍ MẬT NẰM TRONG URL, KHÔNG PHẢI CHỮ KÝ HMAC
    ----------------------------------------------------
    GHN KHÔNG ký webhook — tài liệu của họ chỉ có ô "điền URL callback".
    Không có gì để mà kiểm chữ ký. Cách bảo vệ đúng với thực tế đó là đặt
    một bí mật dài trong chính URL, và chỉ khai URL ấy cho hãng.

    VÌ SAO CHƯA CẤU HÌNH THÌ TỪ CHỐI, KHÔNG PHẢI CHO QUA
    -----------------------------------------------------
    Bản trước viết `if secret:` rồi `if sig:` — hai lớp bỏ qua chồng nhau.
    Chưa đặt bí mật thì không kiểm gì; đặt rồi mà kẻ gọi không gửi header thì
    cũng không kiểm gì. Tức là `POST /webhook/shipping` mở toang cho mọi
    người trên Internet.

    Ai biết mã đơn đều có thể đánh dấu đơn "đã giao", hoặc "hoàn về" — mà
    hoàn về sẽ CỘNG HÀNG LẠI VÀO KHO dù hàng chưa quay lại, và GỬI TIN cho
    khách. Kho sai số, khách nhận tin sai, không dấu vết.

    Repo này đã giải đúng bài đó ở `agent/api/native_webhooks.py`: danh sách
    token rỗng thì TỪ CHỐI, không phải chấp nhận tất cả. Cùng nguyên tắc.
    """
    bi_mat = str(settings.shipping_webhook_secret or "").strip()
    if not bi_mat:
        return False, (
            "SHIPPING_WEBHOOK_SECRET chưa cấu hình. Từ chối mọi webhook vận "
            "chuyển cho tới khi đặt bí mật — sinh bằng: "
            "python -m scripts.sinh_token SHIPPING_WEBHOOK_SECRET"
        )

    gui_len = str(
        query_token
        or headers.get("x-shipping-token")
        or headers.get("X-Shipping-Token")
        or ""
    ).strip()
    if not gui_len:
        return False, "Webhook không kèm bí mật"

    # compare_digest: so sánh thường thoát sớm ở byte đầu khác nhau, đủ để
    # dò từng ký tự bằng cách đo thời gian.
    if not hmac.compare_digest(gui_len, bi_mat):
        return False, "Bí mật webhook không đúng"
    return True, ""


async def xu_ly_webhook_van_chuyen(
    provider_name: str,
    payload: dict[str, Any],
    headers: dict[str, Any],
    query_token: str = "",
) -> dict[str, Any]:
    """
    Xử lý Webhook từ hãng vận chuyển gửi sang:
      1. Parse & Xác thực chữ ký.
      2. Ánh xạ về 4 trạng thái nội bộ.
      3. Cập nhật đơn hàng trong DB.
      4. Kích hoạt thông báo cho khách hoặc hoàn kho nếu đơn bị hoàn về.
    """
    cho_qua, ly_do_chan = kiem_bi_mat_webhook(headers, query_token)
    if not cho_qua:
        await db.log_event(
            "shipping.webhook_tu_choi", carrier=provider_name, ly_do=ly_do_chan,
        )
        return {"ok": False, "error": ly_do_chan, "http_status": 401}

    try:
        provider = get_provider(provider_name)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "http_status": 400}
    event: WebhookEventResult = provider.parse_webhook(payload, headers)

    if not event.hop_le:
        await db.log_event("shipping.webhook_invalid", carrier=provider_name, loi=event.loi)
        return {"ok": False, "error": event.loi}

    # Tìm đơn hàng tương ứng theo ma_van_don hoặc ma_don
    order = None
    if event.ma_van_don:
        order = await db.fetchrow("SELECT * FROM orders WHERE ma_van_don = $1", event.ma_van_don)
    if not order and event.ma_don:
        order = await db.fetchrow("SELECT * FROM orders WHERE ma_don = $1", event.ma_don)

    if not order:
        await db.log_event(
            "shipping.webhook_orphan",
            carrier=provider_name,
            ma_van_don=event.ma_van_don,
            ma_don=event.ma_don,
        )
        return {"ok": True, "note": "Không tìm thấy đơn hàng trong hệ thống"}

    st_noi_bo = event.trang_thai_noi_bo

    # Mã hãng NHẬN RA nhưng không phải trạng thái chính thức (GHTK: shipper
    # tự báo "đã giao", đối soát công nợ). Ghi lại để tra cứu, KHÔNG đổi đơn,
    # không nhắn khách, không đụng kho — và không gọi người như mã lạ, vì
    # người chẳng có gì để làm. Đọc "shipper báo đã giao" thành đã giao là
    # nhắn cảm ơn khách trước khi hàng tới.
    if event.chi_thong_tin:
        await db.log_event(
            "shipping.thong_tin", carrier=provider_name,
            ma_don=str(order.get("ma_don") or ""), ma_van_don=event.ma_van_don,
            trang_thai_goc=event.trang_thai_goc, mo_ta=event.mo_ta[:200],
        )
        return {"ok": True, "chi_thong_tin": True}

    # Mã hãng không nhận ra: GIỮ NGUYÊN trạng thái cũ, gọi người, và KHÔNG
    # nói gì với khách. Đoán bừa "đang giao" là trả lời sai cho kiện đã mất.
    if st_noi_bo is None:
        await db.log_event(
            "shipping.trang_thai_la", carrier=provider_name,
            ma_don=str(order.get("ma_don") or ""),
            ma_van_don=event.ma_van_don,
            trang_thai_goc=event.trang_thai_goc,
        )
        # Nhật ký thôi là không ai biết: kiện có thể đang lạc. Sinh VIỆC cho
        # người tra trên trang hãng (rà soát 29.10.2026).
        await cong_viec.tao_tu_van_chuyen(
            str(order.get("ma_don") or ""),
            tieu_de=f"Kiểm vận đơn {event.ma_van_don or order.get('ma_don')}: "
                    f"{provider_name} báo mã lạ",
            mo_ta=(f"Hãng {provider_name} gửi mã trạng thái "
                   f"'{event.trang_thai_goc}' mà hệ thống không nhận ra. Trạng "
                   "thái đơn GIỮ NGUYÊN, khách chưa được báo gì. Tra mã vận đơn "
                   f"trên trang hãng để biết kiện đang ở đâu. {event.mo_ta or ''}").strip()[:1000],
            khoa=f"van_chuyen:la:{event.ma_van_don or order.get('ma_don')}:{event.trang_thai_goc}",
            conversation_id=order.get("conversation_id"), uu_tien="thuong",
        )
        return {
            "ok": True,
            "can_nguoi_xem": True,
            "note": (
                f"Không nhận ra mã trạng thái '{event.trang_thai_goc}' của "
                f"{provider_name}. Giữ nguyên trạng thái đơn, cần người kiểm."
            ),
        }
    ma_don = order["ma_don"]
    ma_van_don = order["ma_van_don"] or event.ma_van_don
    event_time = event.thoi_gian or datetime.now(timezone.utc)

    da_lay_hang = st_noi_bo in TRANG_THAI_DA_LAY_HANG

    # Chỉ sự kiện mới hơn mới được đổi trạng thái. UPDATE nguyên tử cũng là
    # chốt chống webhook lặp: không có dòng RETURNING thì không chạy các tác
    # dụng phụ (nhắn khách, hoàn kho, tạo công việc) lần nữa.
    updated = await db.fetchrow(
        """
        UPDATE orders
        SET trang_thai_giao_hang = $1,
            van_don_da_lay_hang = CASE
                WHEN van_don_da_lay_hang IS TRUE OR $8 THEN TRUE
                ELSE van_don_da_lay_hang END,
            ma_van_don = COALESCE(ma_van_don, $4),
            don_vi_van_chuyen = COALESCE(don_vi_van_chuyen, $7),
            cap_nhat_van_chuyen_luc = $3,
            lich_su_giao_hang = COALESCE(lich_su_giao_hang, '[]'::jsonb)
                || jsonb_build_array(jsonb_build_object(
                    'time', $3, 'status', $5::text, 'description', $6::text,
                    'carrier', $7::text)),
            erp_van_chuyen_trang_thai = CASE
                WHEN erp_ma_don IS NOT NULL
                 AND erp_van_chuyen_trang_thai <> 'skipped_cancelled'
                    THEN 'pending'
                ELSE erp_van_chuyen_trang_thai END,
            erp_van_chuyen_thu_lai_luc = CASE
                WHEN erp_ma_don IS NOT NULL
                 AND erp_van_chuyen_trang_thai <> 'skipped_cancelled'
                    THEN now()
                ELSE erp_van_chuyen_thu_lai_luc END,
            erp_van_chuyen_loi = CASE
                WHEN erp_ma_don IS NOT NULL
                 AND erp_van_chuyen_trang_thai <> 'skipped_cancelled'
                    THEN NULL
                ELSE erp_van_chuyen_loi END,
            updated_at = now()
        WHERE id = $2
          AND $3 >= COALESCE(cap_nhat_van_chuyen_luc, '-infinity'::timestamptz)
          AND (trang_thai_giao_hang IS DISTINCT FROM $1
               OR ma_van_don IS NULL)
        RETURNING *
        """,
        st_noi_bo.value,
        order["id"],
        event_time,
        event.ma_van_don or None,
        event.trang_thai_goc,
        event.mo_ta[:300],
        provider_name,
        da_lay_hang,
    )
    if updated is None:
        await db.log_event(
            "shipping.webhook_ignored", ref_id=order["id"],
            ma_don=ma_don, ma_van_don=ma_van_don,
            ly_do="duplicate_or_stale", event_time=event_time.isoformat(),
        )
        return {"ok": True, "ignored": True, "note": "Webhook trùng hoặc cũ"}
    order = updated

    if ma_van_don:
        await db.execute(
            """
            UPDATE shipping_waybill_requests
            SET trang_thai = 'reconciled',
                ma_van_don = COALESCE(NULLIF(TRIM(ma_van_don), ''), $2),
                khoa_luc = NULL,
                khoa_boi = NULL,
                doi_soat_tiep_luc = NULL,
                ly_do_chan = NULL,
                xac_nhan_luc = COALESCE(xac_nhan_luc, now()),
                xac_nhan_boi = COALESCE(xac_nhan_boi, 'webhook'),
                updated_at = now()
            WHERE order_id = $1
              AND trang_thai IN ('not_sent', 'sending', 'unknown_timeout', 'reconciling', 'manual_required')
            """,
            order["id"],
            ma_van_don,
        )

    await db.log_event(
        "shipping.status_changed",
        ma_don=ma_don,
        ma_van_don=ma_van_don,
        st_goc=event.trang_thai_goc,
        st_noi_bo=st_noi_bo.value,
    )

    # Xử lý theo từng trạng thái cốt lõi:
    # 1. ĐÃ GIAO (DELIVERED): Đóng đơn hàng thành công & Nhắn tin cảm ơn khách
    if st_noi_bo == InternalShippingStatus.DELIVERED:
        # Đơn ĐÃ HUỶ bên này (hàng đã cộng lại vào kho) mà hãng báo đã giao:
        # KHÔNG đổi sang `da_giao`. Bản trước đổi — kho vẫn đếm món đang ở
        # nhà khách, và đơn huỷ "sống lại" không ai biết. Hàng thật đã đi:
        # người phải quyết thu tiền hay thu hồi, và trừ lại kho.
        if order.get("trang_thai") == "da_huy":
            await db.log_event(
                "shipping.giao_don_da_huy", ma_don=ma_don, ma_van_don=ma_van_don,
                carrier=provider_name,
            )
            await cong_viec.tao_tu_don_hang(
                ma_don,
                tieu_de=f"Hãng báo ĐÃ GIAO đơn đã huỷ {ma_don}",
                mo_ta=(f"Đơn {ma_don} đã huỷ (hàng đã cộng lại kho), nhưng "
                       f"{provider_name} báo đã giao vận đơn {ma_van_don}. Liên hệ "
                       "khách để thu tiền hoặc thu hồi hàng, rồi kiểm kê lại kho "
                       "(Kho → Kiểm kê) — hệ thống KHÔNG tự trừ kho."),
                khoa=f"don_hang:giao_don_da_huy:{ma_van_don or ma_don}",
                conversation_id=order.get("conversation_id"),
            )
            return {
                "ok": True,
                "can_nguoi_xem": True,
                "ma_don": ma_don,
                "note": "Đơn đã huỷ mà hãng báo đã giao — giữ trạng thái, đã sinh việc.",
            }
        await db.execute(
            "UPDATE orders SET trang_thai = 'da_giao', updated_at = now() "
            "WHERE id = $1 AND trang_thai <> 'da_huy'",
            order["id"],
        )
        # Khoá gắn theo MÃ VẬN ĐƠN và trạng thái: GHN phát lại webhook là
        # chuyện thường, và lần phát thứ hai không được sinh tin thứ hai.
        await _bao_khach(
            order.get("conversation_id"),
            f"Dạ đơn {ma_don} đã giao thành công tới mình rồi ạ. "
            "Cảm ơn mình đã tin tưởng shop nha. Sản phẩm có gì cần hỗ trợ "
            "mình cứ nhắn em ạ.",
            f"vandon-dagiao:{ma_van_don}",
        )

    # 2. ĐÃ HOÀN HÀNG VỀ KHO (RETURNED):
    # Theo nghiệp vụ BUG-17-04: webhook `returned` chỉ xác nhận hãng đã hoàn
    # kiện về shop, KHÔNG tự động cộng tồn kho (mỹ phẩm cần kiểm tra số lượng,
    # tình trạng và nguyên seal trước khi nhập lại qua Kho → Nhập).
    elif st_noi_bo == InternalShippingStatus.RETURNED:
        await db.execute(
            "UPDATE orders SET trang_thai = 'da_huy', updated_at = now() "
            "WHERE id = $1 AND trang_thai NOT IN ('da_huy', 'da_giao')",
            order["id"],
        )
        await db.log_event(
            "shipping.returned_cho_kiem_hang",
            ref_id=order["id"],
            ma_don=ma_don,
            ma_van_don=ma_van_don,
            carrier=provider_name,
        )
        nhac_erp = (
            f" Đồng thời kiểm tra/xử lý chứng từ ERPNext ({order['erp_ma_don']})."
            if order.get("erp_ma_don")
            else ""
        )
        await cong_viec.tao_tu_don_hang(
            ma_don,
            tieu_de=f"Kiểm tra hàng hoàn đơn {ma_don}",
            mo_ta=(
                f"Hãng {provider_name.upper()} xác nhận đã hoàn vận đơn "
                f"{ma_van_don} về kho. Kiểm tra số lượng và tình trạng/nguyên "
                "seal sản phẩm trước khi nhập lại kho (Kho → Nhập). Hệ thống "
                f"KHÔNG tự động cộng tồn kho.{nhac_erp}"
            )[:1000],
            khoa=f"don_hang:kiem_hang_hoan:{ma_don}",
            conversation_id=order.get("conversation_id"),
            uu_tien="cao",
        )

    # 3. ĐANG HOÀN HÀNG (RETURNING): Hàng đang quay về, chưa về kệ -> không đụng kho
    elif st_noi_bo == InternalShippingStatus.RETURNING:
        await db.log_event(
            "shipping.returning",
            ref_id=order["id"],
            ma_don=ma_don,
            ma_van_don=ma_van_don,
            carrier=provider_name,
            st_goc=event.trang_thai_goc,
        )

    # 4. ĐÃ HUỶ VẬN ĐƠN TRÊN HÃNG (CANCELLED):
    # - Chỉ tự động cộng tồn kho khi `van_don_da_lay_hang IS FALSE` (bằng chứng
    #   rõ ràng shipper chưa từng lấy hàng rời kho).
    # - Đơn cũ (`van_don_da_lay_hang IS NULL`) hoặc đã qua bước lấy hàng (`TRUE`):
    #   KHÔNG tự động hoàn tồn -> sinh việc kiểm tra kho thực tế.
    elif st_noi_bo == InternalShippingStatus.CANCELLED:
        await db.execute(
            "UPDATE orders SET trang_thai = 'da_huy', updated_at = now() "
            "WHERE id = $1 AND trang_thai NOT IN ('da_huy', 'da_giao')",
            order["id"],
        )
        if order.get("van_don_da_lay_hang") is False:
            so_mon_hoan = await kho.tra_hang(ma_don, ly_do="huy_don")
            await db.log_event(
                "shipping.cancelled_restocked",
                ref_id=order["id"],
                ma_don=ma_don,
                ma_van_don=ma_van_don,
                carrier=provider_name,
                so_san_pham=so_mon_hoan,
            )
        else:
            await db.log_event(
                "shipping.cancelled_cho_kiem_kho",
                ref_id=order["id"],
                ma_don=ma_don,
                ma_van_don=ma_van_don,
                carrier=provider_name,
                da_lay_hang=order.get("van_don_da_lay_hang"),
            )
            await cong_viec.tao_tu_don_hang(
                ma_don,
                tieu_de=f"Kiểm tra tồn kho đơn {ma_don} (vận đơn đã huỷ)",
                mo_ta=(
                    f"Hãng {provider_name.upper()} báo vận đơn {ma_van_don} đã huỷ, "
                    "nhưng hệ thống không đủ bằng chứng hàng chưa rời kho (đơn cũ "
                    "hoặc đã ghi nhận bước lấy hàng). Kiểm tra hàng thực tế tại kho "
                    "trước khi nhập lại kho thủ công (Kho → Nhập)."
                )[:1000],
                khoa=f"don_hang:kiem_kho_huy_vd:{ma_don}",
                conversation_id=order.get("conversation_id"),
                uu_tien="cao",
            )
        if order.get("erp_ma_don"):
            await cong_viec.tao_tu_don_hang(
                ma_don,
                tieu_de=f"Huỷ Sales Order {order['erp_ma_don']} trên ERPNext cho đơn {ma_don}",
                mo_ta=(
                    f"Vận đơn {ma_van_don} của đơn {ma_don} đã huỷ trên "
                    f"{provider_name.upper()} và đơn nội bộ đã chuyển sang đã huỷ. "
                    f"Kiểm tra và huỷ chứng từ {order['erp_ma_don']} trên ERPNext."
                )[:1000],
                khoa=f"don_hang:erp_huy_tay:{ma_don}",
                conversation_id=order.get("conversation_id"),
                uu_tien="cao",
            )

    # 5. GIAO THẤT BẠI (DELIVERY_FAILED): Báo động cho nhân viên
    elif st_noi_bo == InternalShippingStatus.DELIVERY_FAILED:
        await db.log_event(
            "shipping.delivery_alert",
            ma_don=ma_don,
            ma_van_don=ma_van_don,
            ly_do=event.mo_ta or "Giao hàng không thành công",
        )
        # "Báo động" chỉ là nhật ký thì không ai báo cả. Giao hỏng cần một
        # người gọi khách hẹn giao lại TRƯỚC khi hãng thử lần cuối rồi hoàn
        # hàng — shop chịu phí hoàn (rà soát 29.10.2026).
        await cong_viec.tao_tu_van_chuyen(
            ma_don,
            tieu_de=f"Gọi khách hẹn giao lại đơn {ma_don}",
            mo_ta=(f"Hãng báo giao không thành công (mã {event.trang_thai_goc}). "
                   f"Lý do hãng ghi: {event.mo_ta or 'không ghi'}. Gọi khách hẹn "
                   "lại, rồi báo hãng trên trang của họ.")[:1000],
            khoa=f"van_chuyen:that_bai:{ma_van_don}:{event.trang_thai_goc}",
            conversation_id=order.get("conversation_id"),
        )

    return {
        "ok": True,
        "ma_don": ma_don,
        "ma_van_don": ma_van_don,
        "trang_thai_noi_bo": st_noi_bo.value,
    }
