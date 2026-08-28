"""
Đẩy một đơn đã chốt sang ERP.

CÔNG TẮC MẶC ĐỊNH TẮT
---------------------
`ERP_GHI_DON=false` là mặc định CÓ CHỦ Ý, theo đúng khuôn `shipping_provider`
đã đặt ra trong repo này: bật lên là hành động có hậu quả không rút lại được,
nên nó phải là một quyết định rõ ràng của người vận hành, không phải hệ quả
của việc cập nhật mã.

Tắt thì đơn vẫn lưu Postgres như trước. Không có gì hỏng, chỉ là ERP không
biết — đúng trạng thái hệ thống đã sống suốt thời gian qua.

BỐN LƯỚI CHỐNG ĐƠN TRÙNG
------------------------
Bốn, không phải một, vì hậu quả là khách bị tính tiền hai lần:

  1. `tim_don(khoa)` — tra trước khi tạo. Chặn trường hợp ERP đã nhận nhưng
     mạng đứt trước khi ta thấy phản hồi.
  2. Khoá idempotency gửi kèm (`po_no` / `client_order_ref`) — để lưới 1 có
     cái mà tra.
  3. `orders.erp_ma_don` đã có giá trị thì không đẩy nữa.
  4. UNIQUE index trên `orders.erp_ma_don` — lưới cuối, ở tầng CSDL. Ba lưới
     trên đều là mã, và mã thì trượt được.

BA KẾT CỤC, KHÔNG PHẢI HAI
--------------------------
  xong      ERP nhận → `da_chot` + `erp_ma_don`. Báo khách đã chốt.
  tu_choi   ERP hiểu và không đồng ý → `da_huy`. Đây là CÂU TRẢ LỜI, thử lại
            bao nhiêu lần cũng thế. Báo khách và chuyển người.
  cho_lai   Mất mạng, 5xx, timeout → `cho_dong_bo`. Ta KHÔNG BIẾT ERP đã ghi
            hay chưa. Nói với khách "đã ghi nhận", TUYỆT ĐỐI không nói "đã
            chốt xong".

Gộp `tu_choi` với `cho_lai` là hoặc thử lại vô ích một đơn sẽ luôn bị từ
chối, hoặc bỏ mất một đơn chỉ vì mạng chớp.
"""
from __future__ import annotations

from dataclasses import dataclass

from agent.config import settings
from agent.erp.hop_dong import DongDon, LoiERP, NguonGhiERP, TuChoiERP


@dataclass(frozen=True)
class KetQuaDay:
    """Kết cục của một lần đẩy. `ket_cuc` quyết định ta nói gì với khách."""

    ket_cuc: str            # "tat" | "xong" | "tu_choi" | "cho_lai"
    erp_ma_don: str = ""
    ly_do: str = ""

    @property
    def duoc_noi_da_chot(self) -> bool:
        """Chỉ được nói 'đã chốt' khi ERP đã xác nhận, hoặc khi tính năng tắt.

        Đây là ranh giới quan trọng nhất của cả module. `cho_lai` nghĩa là ta
        không biết ERP có đơn hay không — nói 'đã chốt' lúc đó là hứa một
        thứ có thể không tồn tại.
        """
        return self.ket_cuc in ("xong", "tat")


def _dong_tu_items(items: list[dict]) -> list[DongDon]:
    return [
        DongDon(
            ma=str(it["ma"]),
            so_luong=int(it.get("so_luong") or 1),
            don_gia=int(it.get("don_gia") or 0),
        )
        for it in items
    ]


async def day_don(
    ma_don: str,
    khach_ten: str,
    khach_sdt: str,
    khach_dia_chi: str,
    items: list[dict],
    ghi_chu: str = "",
    nguon: NguonGhiERP | None = None,
) -> KetQuaDay:
    """Đẩy một đơn sang ERP. Không bao giờ ném — luôn trả một kết cục.

    Ném ra ngoài là để một lỗi ERP làm hỏng luồng chốt đơn vốn đã chạy đúng.
    Đơn đã nằm trong Postgres rồi; việc còn lại chỉ là ERP có biết hay không.
    """
    if not settings.erp_ghi_don:
        return KetQuaDay(ket_cuc="tat")

    if nguon is None:
        from agent.erp import nha_may

        nguon = nha_may.tao_nguon()  # type: ignore[assignment]

    if not isinstance(nguon, NguonGhiERP):
        # Cấu hình mâu thuẫn: bật ghi đơn nhưng nguồn đang là `tep`. Nói ra
        # chứ đừng im lặng coi như đã đẩy.
        return KetQuaDay(
            ket_cuc="tu_choi",
            ly_do=f"ERP_GHI_DON đang bật nhưng nguồn {getattr(nguon, 'ten', '?')!r} "
                  "không ghi được. Đặt ERP_LOAI=erpnext hoặc odoo.",
        )

    try:
        # Lưới 1: ERP đã có đơn này chưa. Chặn trường hợp lần trước ERP đã
        # nhận nhưng ta mất phản hồi.
        da_co = await nguon.tim_don(ma_don)
        if da_co:
            await _ghi_nhat_ky("erp.don_da_ton_tai", ma_don=ma_don,
                               erp_ma_don=da_co)
            return KetQuaDay(ket_cuc="xong", erp_ma_don=da_co)

        khach_id = await nguon.bao_dam_khach(khach_ten, khach_sdt, khach_dia_chi)
        if not khach_id:
            return KetQuaDay(
                ket_cuc="cho_lai",
                ly_do="ERP không trả về mã khách hàng",
            )

        kq = await nguon.tao_don(ma_don, khach_id, _dong_tu_items(items),
                                 ghi_chu)
    except TuChoiERP as exc:
        await _ghi_nhat_ky("erp.don_bi_tu_choi", ma_don=ma_don, ly_do=str(exc))
        return KetQuaDay(ket_cuc="tu_choi", ly_do=str(exc))
    except LoiERP as exc:
        # KHÔNG BIẾT ERP đã ghi hay chưa. Thử lại, và lưới 1 sẽ chặn đơn thứ
        # hai ở lần sau.
        await _ghi_nhat_ky("erp.don_cho_dong_bo", ma_don=ma_don, ly_do=str(exc))
        return KetQuaDay(ket_cuc="cho_lai", ly_do=str(exc))
    except Exception as exc:  # noqa: BLE001
        # Lỗi ngoài dự kiến cũng là KHÔNG BIẾT. Không được im.
        await _ghi_nhat_ky("erp.don_loi_la", ma_don=ma_don,
                           loi=type(exc).__name__)
        return KetQuaDay(ket_cuc="cho_lai", ly_do=f"{type(exc).__name__}: {exc}")

    if not kq.thanh_cong:
        await _ghi_nhat_ky("erp.don_bi_tu_choi", ma_don=ma_don, ly_do=kq.ly_do)
        return KetQuaDay(ket_cuc="tu_choi", ly_do=kq.ly_do)

    await _ghi_nhat_ky("erp.don_da_day", ma_don=ma_don,
                       erp_ma_don=kq.erp_ma_don)
    return KetQuaDay(ket_cuc="xong", erp_ma_don=kq.erp_ma_don)


async def _ghi_nhat_ky(loai: str, **chi_tiet) -> None:
    """Mọi kết cục đều để lại dấu vết.

    Không có nhật ký thì đơn kẹt `cho_dong_bo` chỉ lộ ra khi khách gọi hỏi
    hàng đâu.
    """
    try:
        from agent import db

        await db.log_event(loai, **chi_tiet)
    except Exception:  # noqa: BLE001
        pass
