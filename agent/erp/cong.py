"""
Cổng: bọc một `NguonERP`, thêm cache có tuổi và ngắt mạch.

QUY TẮC TRUNG TÂM
-----------------
Giá và tồn kho quá hạn mà gọi ERP không được thì cổng trả `None`.
KHÔNG BAO GIỜ trả số cũ.

Cám dỗ ở đây rất lớn: đã có số trong tay, trả ra thì agent chạy mượt, không
ai thấy gì. Đó chính là vấn đề — nó chạy mượt trong khi nói sai. Báo giá sai
rồi mới phát hiện đắt hơn nhiều so với im lặng một phút, và im lặng thì lưới
an toàn đẩy sang người thật.

Tham chiếu (tên, mô tả) thì ngược lại — bản cũ dùng được, vì tên sản phẩm
không đổi trong một buổi chiều.

VÌ SAO ĐỒNG HỒ TIÊM VÀO
-----------------------
Để test TTL không phải ngủ.
"""
from __future__ import annotations

import json
import pathlib
import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent.erp.anh_xa import AnhXa, doc_anh_xa
from agent.erp.hop_dong import Gia, LoiERP, NguonERP, TonKho


# Trần số lời gọi ERP chạy cùng lúc khi nạp danh mục. Bắn 100 lời gọi một
# lượt vào một ERP đang phục vụ người thật là tự gây ra sự cố mình đi chữa.
_SONG_SONG_TOI_DA = 8


@dataclass
class _O:
    """Một ô cache: giá trị và thời điểm ghi."""

    gia_tri: Any
    luc: float


class Cong:
    def __init__(
        self,
        nguon: NguonERP,
        ttl_gia: float = 900.0,
        ttl_ton: float = 60.0,
        ngat_mach_so_lan: int = 5,
        ngat_mach_giay: float = 30.0,
        dong_ho: Callable[[], float] = time.monotonic,
        duong_dan_tu_van: pathlib.Path | None = None,
        anh_xa: AnhXa | None = None,
    ):
        self._nguon = nguon
        self._ttl_gia = ttl_gia
        self._ttl_ton = ttl_ton
        self._ngat_mach_so_lan = ngat_mach_so_lan
        self._ngat_mach_giay = ngat_mach_giay
        self._dong_ho = dong_ho
        self._cache_gia: dict[str, _O] = {}
        self._cache_ton: dict[str, _O] = {}
        self._hong_lien_tiep = 0
        self._mo_mach_den = 0.0
        self._duong_dan_tu_van = duong_dan_tu_van
        self._anh_xa = anh_xa if anh_xa is not None else doc_anh_xa()

    async def gia(self, ma: str, bo_qua_cache: bool = False) -> Gia | None:
        return await self._lay(
            self._cache_gia, self._ttl_gia, ma, bo_qua_cache, self._nguon.gia
        )

    async def ton_kho(self, ma: str, bo_qua_cache: bool = False) -> TonKho | None:
        return await self._lay(
            self._cache_ton, self._ttl_ton, ma, bo_qua_cache, self._nguon.ton_kho
        )

    async def _lay(self, cache, ttl, ma, bo_qua_cache, ham):
        bay_gio = self._dong_ho()
        if not bo_qua_cache:
            o = cache.get(ma)
            if o is not None and bay_gio - o.luc < ttl:
                return o.gia_tri

        # Mạch đang mở: không gọi, trả `None` ngay. Gọi tiếp là bắt mỗi khách
        # đang chờ phải ăn trọn thời gian timeout của ERP.
        if bay_gio < self._mo_mach_den:
            return None

        try:
            gia_tri = await ham(ma)
        except Exception:  # noqa: BLE001
            self._hong_lien_tiep += 1
            if self._hong_lien_tiep >= self._ngat_mach_so_lan:
                self._mo_mach_den = bay_gio + self._ngat_mach_giay
                await self._bao_ngat_mach()
            # Không trả ô cache cũ. Xem QUY TẮC TRUNG TÂM ở đầu file.
            return None

        self._hong_lien_tiep = 0
        self._mo_mach_den = 0.0
        cache[ma] = _O(gia_tri, bay_gio)
        return gia_tri

    async def _bao_ngat_mach(self) -> None:
        """Ngắt mạch phải để lại dấu vết.

        Không có nhật ký thì ERP hỏng cả buổi mà biểu hiện duy nhất ra ngoài
        là 'hôm nay agent chuyển người nhiều hơn mọi khi'.
        """
        try:
            from agent import db

            await db.log_event(
                "erp.ngat_mach",
                nguon=getattr(self._nguon, "ten", "?"),
                hong_lien_tiep=self._hong_lien_tiep,
            )
        except Exception:  # noqa: BLE001
            pass

    def trang_thai(self) -> dict:
        return {
            "nguon": getattr(self._nguon, "ten", "?"),
            "mach_mo": self._dong_ho() < self._mo_mach_den,
            "hong_lien_tiep": self._hong_lien_tiep,
        }

    async def suc_khoe(self) -> bool:
        """Nguồn còn sống không.

        Có mặt ở đây để tầng trên không phải chọc vào `_nguon` — bọc nguồn
        lại rồi để lộ nó ra là chưa bọc.
        """
        try:
            return bool(await self._nguon.suc_khoe())
        except Exception:  # noqa: BLE001
            return False

    def _ho_so_tu_van(self) -> tuple[dict[str, dict], list]:
        """Nửa tư vấn: đọc từ kho nội bộ, KHÔNG từ ERP.

        Chín trên mười bốn trường của bản ghi sản phẩm (da_phu_hop,
        thanh_phan_chinh, so_cong_bo...) không tồn tại trong Odoo hay ERPNext.
        Nhét chúng vào ERP là dùng sai công cụ, và mất sạch khi đổi ERP.
        """
        from agent.erp.tep import CATALOG, CATALOG_MAU

        dd = self._duong_dan_tu_van
        if dd is None or not dd.exists():
            dd = CATALOG if CATALOG.exists() else CATALOG_MAU
        if not dd.exists():
            return {}, []
        try:
            data = json.loads(dd.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}, []
        return (
            {sp["ma"]: sp for sp in data.get("san_pham", []) if sp.get("ma")},
            data.get("don_hang", []),
        )

    async def danh_muc(self) -> dict:
        """Danh mục hợp nhất, đúng hình dạng `tools._catalog()` đang trả."""
        try:
            ds = await self._nguon.danh_sach_san_pham()
        except Exception as exc:  # noqa: BLE001
            # Ném chứ không trả rỗng: rỗng nghĩa là "cửa hàng không có hàng
            # nào", agent tin, chuyển hết cho người, và không ai biết vì sao.
            raise LoiERP(
                f"Không lấy được danh mục từ nguồn {getattr(self._nguon, 'ten', '?')}"
            ) from exc

        ho_so, don_hang = self._ho_so_tu_van()
        thieu: list[str] = []
        ket_qua: list[dict] = []

        # Hỏi giá và tồn của MỌI sản phẩm SONG SONG.
        #
        # Bản đầu gọi nối tiếp, và đo thật thì 22 SKU với độ trễ 150ms/lời
        # gọi mất 6,9 giây cho một lần nạp — lặp lại mỗi khi cache tồn kho
        # hết hạn. Ở contact center nghĩa là cứ mỗi phút có một khách phải
        # chờ chừng ấy, và cửa hàng 100 SKU thì chờ 31 giây.
        #
        # Chặn ở `_SONG_SONG_TOI_DA`: bắn 100 lời gọi cùng lúc vào một ERP
        # đang phục vụ người thật là tự gây ra sự cố mình đi chữa.
        chan = asyncio.Semaphore(_SONG_SONG_TOI_DA)

        async def _hoi(ma: str):
            async with chan:
                return await asyncio.gather(self.gia(ma), self.ton_kho(ma))

        cap = await asyncio.gather(*(_hoi(sp.ma) for sp in ds))

        for sp, (g, t) in zip(ds, cap, strict=True):
            ma_noi_bo = self._anh_xa.ve_noi_bo(sp.ma)
            if g is None or t is None:
                # Không có giá hoặc không biết tồn thì đừng đưa ra. Đưa ra là
                # mời khách hỏi rồi trả lời bằng số bịa.
                continue
            ban_ghi = dict(ho_so.get(ma_noi_bo, {}))
            if ma_noi_bo not in ho_so:
                thieu.append(ma_noi_bo)
            ban_ghi.update(
                ma=ma_noi_bo,
                ten=sp.ten,
                loai=sp.loai or ban_ghi.get("loai", ""),
                dung_tich=sp.dung_tich or ban_ghi.get("dung_tich", ""),
                gia=g.gia_ban,
                ton_kho=t.ban_duoc,
                duoc_gioi_thieu=ma_noi_bo in ho_so,
            )
            ket_qua.append(ban_ghi)

        if thieu:
            try:
                from agent import db

                await db.log_event(
                    "erp.thieu_ho_so", so_luong=len(thieu), ma=thieu[:20]
                )
            except Exception:  # noqa: BLE001
                pass

        return {"san_pham": ket_qua, "don_hang": don_hang}
