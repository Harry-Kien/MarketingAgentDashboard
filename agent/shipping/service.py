"""
Bộ điều phối nghiệp vụ vận chuyển: 4 chốt kiểm duyệt, xử lý Webhook và tra cứu Real-time.
"""
from __future__ import annotations

import hmac
import json
from datetime import datetime, timezone
from typing import Any

from agent import db
from agent.config import settings
from agent.core import kho
from .base import BaseShippingProvider
from .ghn import GHNShippingProvider
from .mock import MockShippingProvider
from .models import (
    CreateWaybillRequest,
    CreateWaybillResult,
    InternalShippingStatus,
    ShippingItem,
    TrackingResult,
    WebhookEventResult,
)

_PROVIDERS: dict[str, BaseShippingProvider] = {}


def get_provider(name: str | None = None) -> BaseShippingProvider:
    global _PROVIDERS
    key = (name or settings.shipping_provider or "mock").strip().lower()
    if key not in _PROVIDERS:
        if key == "ghn":
            _PROVIDERS[key] = GHNShippingProvider()
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
        return CreateWaybillResult(
            ok=True,
            ma_van_don=ma_van_don_cu,
            don_vi=str(order.get("don_vi_van_chuyen") or "ghn"),
            phi_van_chuyen=int(order.get("phi_van_chuyen") or 0),
            ngay_du_kien_giao=order.get("ngay_du_kien_giao"),
            trang_thai_noi_bo=InternalShippingStatus.DELIVERING,
            thong_tin_them={"da_co_san": True, "ghi_chu": "Vận đơn đã được tạo trước đó."},
        )

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
    req = CreateWaybillRequest(
        ma_don=ma_don,
        khach_ten=khach_ten,
        khach_sdt=khach_sdt,
        khach_dia_chi=khach_dia_chi,
        items=shipping_items,
        tong_tien=tong_tien,
        thu_ho_cod=tong_tien,  # Mặc định thu hộ COD = tổng tiền đơn
        tong_khoi_luong_gram=max(300, tong_gram),
        ghi_chu=str(order.get("ghi_chu") or ""),
    )

    provider = get_provider(provider_name)
    result = await provider.tao_van_don(req)

    if result.ok and result.ma_van_don:
        now = datetime.now(timezone.utc)
        await db.execute(
            """
            UPDATE orders
            SET ma_van_don = $1,
                don_vi_van_chuyen = $2,
                trang_thai_giao_hang = $3,
                phi_van_chuyen = $4,
                ngay_du_kien_giao = $5,
                cap_nhat_van_chuyen_luc = $6,
                updated_at = now()
            WHERE ma_don = $7
            """,
            result.ma_van_don,
            provider.code,
            InternalShippingStatus.DELIVERING.value,
            result.phi_van_chuyen,
            result.ngay_du_kien_giao,
            now,
            ma_don,
        )
        await db.log_event(
            "shipping.created",
            ma_don=ma_don,
            ma_van_don=result.ma_van_don,
            carrier=provider.code,
            phi=result.phi_van_chuyen,
        )

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
            order.get("conversation_id"),
            f"Dạ đơn {ma_don} của mình đã được bàn giao cho "
            f"{provider.name} rồi ạ.\n\n"
            f"Mã vận đơn: {result.ma_van_don}\n"
            "Mình tra mã này trên ứng dụng của hãng để xem hàng đang ở đâu "
            "nha. Có gì cần hỗ trợ mình cứ nhắn em ạ.",
            f"vandon-tao:{result.ma_van_don}",
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
        provider = get_provider()
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
    provider = get_provider(provider_name)
    result = await provider.tra_cuu(ma_van_don)

    # Cập nhật lại vị trí / trạng thái vào CSDL nếu có thay đổi
    if result.ok:
        await db.execute(
            """
            UPDATE orders
            SET trang_thai_giao_hang = $1,
                cap_nhat_van_chuyen_luc = now(),
                updated_at = now()
            WHERE ma_van_don = $2
            """,
            result.trang_thai_noi_bo.value,
            ma_van_don,
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

    provider = get_provider(provider_name)
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

    # Mã hãng không nhận ra: GIỮ NGUYÊN trạng thái cũ, gọi người, và KHÔNG
    # nói gì với khách. Đoán bừa "đang giao" là trả lời sai cho kiện đã mất.
    if st_noi_bo is None:
        await db.log_event(
            "shipping.trang_thai_la", carrier=provider_name,
            ma_don=str(order.get("ma_don") or ""),
            ma_van_don=event.ma_van_don,
            trang_thai_goc=event.trang_thai_goc,
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

    # Cập nhật trạng thái và lộ trình giao hàng vào CSDL
    await db.execute(
        """
        UPDATE orders
        SET trang_thai_giao_hang = $1,
            cap_nhat_van_chuyen_luc = now(),
            updated_at = now()
        WHERE id = $2
        """,
        st_noi_bo.value,
        order["id"],
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
        await db.execute(
            "UPDATE orders SET trang_thai = 'da_giao', updated_at = now() WHERE id = $1",
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

    # 2. HOÀN VỀ (RETURNED): Tự động cộng lại hàng vào kho (Restock) & Ghi nhật ký
    elif st_noi_bo == InternalShippingStatus.RETURNED:
        await db.execute(
            "UPDATE orders SET trang_thai = 'da_huy', updated_at = now() WHERE id = $1",
            order["id"],
        )
        so_mon_hoan = await kho.tra_hang(ma_don, ly_do="hoan_hang")
        await db.log_event(
            "shipping.restocked",
            ma_don=ma_don,
            ma_van_don=ma_van_don,
            so_san_pham=so_mon_hoan,
        )

    # 3. GIAO THẤT BẠI (DELIVERY_FAILED): Báo động cho nhân viên
    elif st_noi_bo == InternalShippingStatus.DELIVERY_FAILED:
        await db.log_event(
            "shipping.delivery_alert",
            ma_don=ma_don,
            ma_van_don=ma_van_don,
            ly_do=event.mo_ta or "Giao hàng không thành công",
        )

    return {
        "ok": True,
        "ma_don": ma_don,
        "ma_van_don": ma_van_don,
        "trang_thai_noi_bo": st_noi_bo.value,
    }
