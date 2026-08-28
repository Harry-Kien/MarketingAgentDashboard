"""
Vòng nền: thử lại đơn kẹt `cho_dong_bo`, và đối soát tồn kho.

VÌ SAO PHẢI CÓ
--------------
`cho_dong_bo` nghĩa là "đã ghi nhận, chưa vào được ERP". Không có ai thử lại
thì nó là NGÕ CỤT: đơn nằm đó mãi, khách chờ, và biểu hiện duy nhất ra ngoài
là một dòng trạng thái không ai xem.

Và không có bộ đối soát thì tồn kho lệch chỉ lộ ra khi khách phàn nàn.

BACKOFF, KHÔNG PHẢI THỬ LIÊN TỤC
--------------------------------
ERP đang bảo trì mà quét mỗi 30 giây là đập vào một hệ thống đang ốm. Giãn
theo số lần đã thử, tối đa `TRE_TOI_DA_GIAY`.

BỎ CUỘC CÓ TIẾNG, KHÔNG BỎ CUỘC IM LẶNG
---------------------------------------
Quá `SO_LAN_TOI_DA` thì dừng thử và KÊU. Thử mãi mãi là giấu một đơn hỏng
sau một vòng lặp bận rộn — nhìn từ ngoài không phân biệt được với đang chạy
bình thường.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

MOI_GIAY = 60.0

# Quá số lần này thì dừng thử và kêu. Người phải vào xem.
SO_LAN_TOI_DA = 8

# Giãn dần: 2^n phút, chặn ở 30 phút.
TRE_TOI_DA_GIAY = 1800

# Đơn kẹt lâu hơn mức này là chuyện của người, không phải của máy.
CANH_BAO_SAU_PHUT = 30


def tre_lan_sau(so_lan_da_thu: int) -> float:
    """Giây phải chờ trước lần thử kế tiếp."""
    return float(min(2 ** max(0, so_lan_da_thu) * 60, TRE_TOI_DA_GIAY))


class KhoDon(Protocol):
    """Những gì vòng nền cần từ CSDL. Tách ra để test không cần Postgres."""

    async def don_cho_dong_bo(self, gioi_han: int = 20) -> list[dict]: ...

    async def danh_dau_da_day(self, id_don: Any, erp_ma_don: str) -> None: ...

    async def danh_dau_that_bai(self, id_don: Any, ly_do: str) -> None: ...

    async def danh_dau_bo_cuoc(self, id_don: Any, ly_do: str) -> None: ...


async def quet_mot_luot(
    kho_don: KhoDon,
    day: Callable[[dict], Awaitable[Any]],
    ghi_nhat_ky: Callable[..., Awaitable[None]] | None = None,
) -> dict:
    """Thử lại mọi đơn đang kẹt. Trả về thống kê một lượt quét.

    KHÔNG bao giờ ném: một đơn hỏng không được làm dừng cả vòng nền, nếu
    không thì đơn thứ hai trở đi không bao giờ được thử.
    """
    thong_ke = {"da_xet": 0, "xong": 0, "bo_cuoc": 0, "con_cho": 0, "hoan": 0}

    for don in await kho_don.don_cho_dong_bo():
        thong_ke["da_xet"] += 1
        so_lan = int(don.get("erp_so_lan_thu") or 0)

        if so_lan >= SO_LAN_TOI_DA:
            await kho_don.danh_dau_bo_cuoc(
                don["id"], f"Đã thử {so_lan} lần, dừng lại. Cần người xem."
            )
            await _kêu(ghi_nhat_ky, "erp.don_bo_cuoc",
                       ma_don=don.get("ma_don"), so_lan=so_lan)
            thong_ke["bo_cuoc"] += 1
            continue

        # Chưa tới lượt. Không phải lỗi — chỉ là backoff.
        if float(don.get("_giay_tu_lan_thu_cuoi") or 1e9) < tre_lan_sau(so_lan):
            thong_ke["hoan"] += 1
            continue

        try:
            kq = await day(don)
        except Exception as exc:  # noqa: BLE001
            # Vòng nền không được chết. Ghi lại rồi đi tiếp sang đơn sau.
            await kho_don.danh_dau_that_bai(
                don["id"], f"{type(exc).__name__}: {exc}"[:200]
            )
            thong_ke["con_cho"] += 1
            continue

        if kq.ket_cuc == "xong":
            await kho_don.danh_dau_da_day(don["id"], kq.erp_ma_don)
            await _kêu(ghi_nhat_ky, "erp.don_dong_bo_muon",
                       ma_don=don.get("ma_don"), erp_ma_don=kq.erp_ma_don,
                       so_lan=so_lan + 1)
            thong_ke["xong"] += 1
        elif kq.ket_cuc == "tu_choi":
            # Từ chối là CÂU TRẢ LỜI. Thử lại vô nghĩa.
            await kho_don.danh_dau_bo_cuoc(don["id"], kq.ly_do)
            await _kêu(ghi_nhat_ky, "erp.don_bi_tu_choi_khi_thu_lai",
                       ma_don=don.get("ma_don"), ly_do=kq.ly_do)
            thong_ke["bo_cuoc"] += 1
        else:
            await kho_don.danh_dau_that_bai(don["id"], kq.ly_do)
            thong_ke["con_cho"] += 1

    return thong_ke


async def _kêu(ghi_nhat_ky, loai: str, **chi_tiet) -> None:
    if ghi_nhat_ky is None:
        return
    try:
        await ghi_nhat_ky(loai, **chi_tiet)
    except Exception:  # noqa: BLE001
        pass


class PostgresKhoDon:
    """Hiện thực `KhoDon` trên bảng `orders`.

    Bảng `orders` CHÍNH LÀ hàng đợi — xem migration 0008. Không dựng bảng
    job riêng, vì thế là một đơn tồn tại ở hai nơi.
    """

    async def don_cho_dong_bo(self, gioi_han: int = 20) -> list[dict]:
        from agent import db

        rows = await db.fetch(
            """
            SELECT id, ma_don, khach_ten, khach_sdt, khach_dia_chi, items,
                   ghi_chu, erp_so_lan_thu,
                   EXTRACT(EPOCH FROM (now() - updated_at)) AS _giay_tu_lan_thu_cuoi
            FROM orders
            WHERE trang_thai = 'cho_dong_bo'
            ORDER BY created_at
            LIMIT $1
            """,
            gioi_han,
        )
        return [dict(r) for r in rows]

    async def danh_dau_da_day(self, id_don, erp_ma_don: str) -> None:
        from agent import db

        await db.execute(
            "UPDATE orders SET trang_thai='da_chot', erp_ma_don=$2, "
            "erp_dong_bo_luc=now(), erp_loi=NULL, updated_at=now() "
            "WHERE id=$1",
            id_don, erp_ma_don,
        )

    async def danh_dau_that_bai(self, id_don, ly_do: str) -> None:
        from agent import db

        await db.execute(
            "UPDATE orders SET erp_so_lan_thu = erp_so_lan_thu + 1, "
            "erp_loi=$2, updated_at=now() WHERE id=$1",
            id_don, ly_do[:500],
        )

    async def danh_dau_bo_cuoc(self, id_don, ly_do: str) -> None:
        from agent import db

        # `cho_duyet` chứ không phải `da_huy`: máy bỏ cuộc, NGƯỜI quyết định
        # số phận đơn. Tự huỷ đơn của khách vì ERP không nhận là vượt thẩm
        # quyền — có thể chỉ là cấu hình sai, sửa xong là đẩy được.
        await db.execute(
            "UPDATE orders SET trang_thai='cho_duyet', erp_loi=$2, "
            "updated_at=now() WHERE id=$1",
            id_don, ly_do[:500],
        )


async def vong_dong_bo_loop() -> None:
    """Chạy mãi. Chỉ làm gì khi `ERP_GHI_DON` bật."""
    from agent import db
    from agent.config import settings
    from agent.erp import day_don as _day_don

    kho_don = PostgresKhoDon()

    async def _day(don: dict):
        return await _day_don.day_don(
            ma_don=don["ma_don"],
            khach_ten=don["khach_ten"],
            khach_sdt=don["khach_sdt"],
            khach_dia_chi=don["khach_dia_chi"],
            items=don["items"] or [],
            ghi_chu=str(don.get("ghi_chu") or ""),
        )

    while True:
        if settings.erp_ghi_don:
            try:
                await quet_mot_luot(kho_don, _day, db.log_event)
            except Exception as exc:  # noqa: BLE001 — vòng nền không được chết
                await db.log_event(
                    "erp.vong_dong_bo_loi",
                    error=f"{type(exc).__name__}: {exc}"[:200],
                )
        await asyncio.sleep(MOI_GIAY)
