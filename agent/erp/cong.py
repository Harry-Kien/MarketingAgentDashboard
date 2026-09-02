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

import pathlib
import random
import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent.erp import ho_so as ho_so_tu_van
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
        han_cho_giay: float = 4.0,
        so_lan_thu: int = 2,
        cache_toi_da: int = 5_000,
        dong_ho: Callable[[], float] = time.monotonic,
        duong_dan_tu_van: pathlib.Path | None = None,
        anh_xa: AnhXa | None = None,
    ):
        self._nguon = nguon
        self._ttl_gia = ttl_gia
        self._ttl_ton = ttl_ton
        self._ngat_mach_so_lan = ngat_mach_so_lan
        self._ngat_mach_giay = ngat_mach_giay
        self._han_cho_giay = han_cho_giay
        self._so_lan_thu = max(1, int(so_lan_thu))
        self._cache_toi_da = max(1, int(cache_toi_da))
        self._dong_ho = dong_ho

        # CACHE CÓ TRẦN, bỏ ô cũ nhất khi đầy.
        #
        # `dict` thuần lớn mãi không giới hạn: với danh mục vài chục nghìn
        # mã thì đó là rò bộ nhớ chạy suốt đời tiến trình — không nổ, chỉ
        # phình, nên không ai phát hiện cho tới lúc máy hết RAM.
        self._cache: dict[str, OrderedDict[str, _O]] = {
            "gia": OrderedDict(), "ton_kho": OrderedDict(),
        }

        # NGẮT MẠCH THEO TỪNG THAO TÁC, không dùng chung một bộ đếm.
        #
        # Bản trước một `_hong_lien_tiep` cho cả nguồn. Nếu chỉ `ton_kho`
        # hỏng — sai quyền kho, `Bin` chưa có bản ghi — thì 5 lần hỏng tồn
        # GIẾT LUÔN tra giá, dù giá vẫn đọc được bình thường. Khách hỏi giá
        # nhận "không biết" vì một sự cố ở chỗ khác.
        self._hong: dict[str, int] = {}
        self._mo_den: dict[str, float] = {}

        # CHỐNG GIẪM ĐẠP CACHE (single-flight).
        #
        # TTL tồn kho là 60s. Hết hạn đúng lúc 20 khách cùng hỏi một mã thì
        # bản trước bắn 20 lời gọi song song cho CÙNG một câu hỏi. Nay lời
        # gọi đầu tiên đi, 19 người còn lại chờ chính kết quả đó.
        self._dang_bay: dict[tuple[str, str], asyncio.Future] = {}
        self._duong_dan_tu_van = duong_dan_tu_van
        self._anh_xa = anh_xa if anh_xa is not None else doc_anh_xa()

    @property
    def nguon(self) -> NguonERP:
        """
        Nguồn ERP cổng này đang bọc.

        Mở ra để `agent/erp/kiem_ket_noi.py` soi ĐÚNG đối tượng agent đang
        dùng, thay vì tự dựng một nguồn mới từ cấu hình. Dựng mới thì phép
        kiểm sức khoẻ nói về một hệ thống khác với hệ thống đang chạy — và
        nó nói bằng màu xanh.
        """
        return self._nguon

    async def gia(self, ma: str, bo_qua_cache: bool = False) -> Gia | None:
        return await self._lay(
            "gia", self._ttl_gia, ma, bo_qua_cache, self._nguon.gia
        )

    async def ton_kho(self, ma: str, bo_qua_cache: bool = False) -> TonKho | None:
        return await self._lay(
            "ton_kho", self._ttl_ton, ma, bo_qua_cache, self._nguon.ton_kho
        )

    def _ghi_cache(self, ten: str, ma: str, gia_tri, luc: float) -> None:
        """Ghi vào cache LRU, bỏ ô cũ nhất khi vượt trần."""
        cache = self._cache[ten]
        cache[ma] = _O(gia_tri, luc)
        cache.move_to_end(ma)
        while len(cache) > self._cache_toi_da:
            cache.popitem(last=False)

    async def _lay(self, ten: str, ttl, ma, bo_qua_cache, ham):
        bay_gio = self._dong_ho()
        cache = self._cache[ten]
        if not bo_qua_cache:
            o = cache.get(ma)
            if o is not None and bay_gio - o.luc < ttl:
                # Chạm vào là mới lại — đó là chữ "gần đây" trong LRU.
                cache.move_to_end(ma)
                return o.gia_tri

        # Mạch của THAO TÁC NÀY đang mở: không gọi, trả `None` ngay. Gọi tiếp
        # là bắt mỗi khách đang chờ phải ăn trọn thời gian timeout của ERP.
        if bay_gio < self._mo_den.get(ten, 0.0):
            return None

        # CHỐNG GIẪM ĐẠP: cùng một (thao tác, mã) chỉ có MỘT lời gọi đang bay.
        #
        # Người đến sau chờ chính lời gọi đó thay vì mở thêm một lời gọi nữa
        # hỏi đúng câu hỏi ấy. `shield` để việc một người bỏ cuộc không huỷ
        # lời gọi mà những người còn lại đang chờ.
        khoa = (ten, ma)
        dang = self._dang_bay.get(khoa)
        if dang is not None:
            xong, gia_tri = await asyncio.shield(dang)
            return gia_tri if xong else None

        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._dang_bay[khoa] = fut
        try:
            gia_tri = await self._goi_co_thu_lai(ham, ma)
        except asyncio.CancelledError:
            # Đánh thức người đang chờ rồi mới ném tiếp — bỏ đi lặng lẽ là
            # để họ treo tới hết hạn của chính họ.
            if not fut.done():
                fut.set_result((False, None))
            self._dang_bay.pop(khoa, None)
            raise
        except Exception:  # noqa: BLE001
            # MỘT chuỗi thử hỏng = MỘT lần hỏng, không phải N.
            #
            # Đếm từng lần thử thì ngắt mạch mở nhanh gấp `so_lan_thu` lần
            # so với con số người vận hành đặt trong `.env`. Họ viết 5 và
            # nghĩ là 5 sự cố, chứ không phải 2 hay 3.
            #
            # Và những người đang chờ ké cũng KHÔNG bị đếm thêm: cả nhóm
            # dùng chung đúng một lời gọi, nên đó là một sự cố.
            self._hong[ten] = self._hong.get(ten, 0) + 1
            if self._hong[ten] >= self._ngat_mach_so_lan:
                self._mo_den[ten] = bay_gio + self._ngat_mach_giay
                await self._bao_ngat_mach(ten)
            if not fut.done():
                fut.set_result((False, None))
            self._dang_bay.pop(khoa, None)
            # Không trả ô cache cũ. Xem QUY TẮC TRUNG TÂM ở đầu file.
            return None

        self._hong[ten] = 0
        self._mo_den[ten] = 0.0
        self._ghi_cache(ten, ma, gia_tri, bay_gio)
        if not fut.done():
            fut.set_result((True, gia_tri))
        self._dang_bay.pop(khoa, None)
        return gia_tri

    async def _goi_co_thu_lai(self, ham, ma: str):
        """
        Gọi ERP với hạn giờ mỗi lần, thử lại khi hỏng. Hỏng hết thì NÉM.

        VÌ SAO THỬ LẠI — VÀ VÌ SAO CHỈ Ở ĐÂY
        ------------------------------------
        Trước đây một cú chớp mạng là một câu trả lời hỏng: khách hỏi giá
        đúng lúc ERP nấc một nhịp thì agent nói "em chưa tra được" rồi
        chuyển người. Mất một khách vì một sự cố kéo dài 200ms.

        Cổng này chỉ bọc `gia`, `ton_kho`, `danh_muc`, `suc_khoe` — toàn
        thao tác ĐỌC, gọi lại vô hại. Đường GHI đơn đi qua
        `agent/erp/day_don.py` và KHÔNG qua đây; thử lại mù ở đó là nguy cơ
        tạo đơn trùng, một lỗi tốn tiền thật.

        VÌ SAO CÓ HẠN GIỜ RIÊNG
        -----------------------
        Adapter đặt timeout 15 giây — hạn của thư viện HTTP, hợp lý cho tác
        vụ nền. Nhưng đây là đường trả lời khách: ERP treo là người ta ngồi
        nhìn khung chat 15 giây rồi mới nhận lời từ chối.

        VÌ SAO CÓ JITTER
        ----------------
        Nhiều khách cùng gặp sự cố sẽ cùng thử lại đúng một nhịp, dồn thành
        một đợt sóng đập vào ERP vừa mới hồi. Lệch ngẫu nhiên thì tản ra.
        """
        cuoi: Exception | None = None
        for lan in range(self._so_lan_thu):
            try:
                return await asyncio.wait_for(ham(ma), timeout=self._han_cho_giay)
            except asyncio.CancelledError:
                # Người gọi huỷ (khách đóng chat, tiến trình tắt) — KHÔNG
                # phải ERP hỏng. Nuốt nó thành lỗi ERP là vừa thử lại vô ích
                # vừa đẩy ngắt mạch mở oan.
                raise
            except Exception as exc:  # noqa: BLE001
                cuoi = exc
                if lan + 1 < self._so_lan_thu:
                    await asyncio.sleep(0.1 + random.random() * 0.2)
        raise cuoi if cuoi is not None else LoiERP("gọi ERP thất bại")

    async def _bao_ngat_mach(self, thao_tac: str) -> None:
        """Ngắt mạch phải để lại dấu vết.

        Không có nhật ký thì ERP hỏng cả buổi mà biểu hiện duy nhất ra ngoài
        là 'hôm nay agent chuyển người nhiều hơn mọi khi'.

        Ghi kèm TÊN THAO TÁC: mạch nay tách theo thao tác, nên "ngắt mạch"
        trần không nói được là giá hỏng hay tồn hỏng — hai chuyện đi tìm ở
        hai chỗ khác nhau.
        """
        try:
            from agent import db

            await db.log_event(
                "erp.ngat_mach",
                nguon=getattr(self._nguon, "ten", "?"),
                thao_tac=thao_tac,
                hong_lien_tiep=self._hong.get(thao_tac, 0),
            )
        except Exception:  # noqa: BLE001
            pass

    def trang_thai(self) -> dict:
        """
        Trạng thái cổng.

        GIỮ NGUYÊN `mach_mo` VÀ `hong_lien_tiep` Ở DẠNG GỘP.
        Ba nơi đang đọc hai khoá này — `agent/api/erp.py`,
        `agent/mcp_server.py`, `agent/suc_khoe.py` — cộng dashboard. Đổi hình
        dạng để "cho sạch" là làm hỏng ba màn hình cùng lúc, và cái giá đó
        không đáng.

        `mach_mo` gộp theo kiểu BI QUAN: một thao tác mở là báo mở. Người
        vận hành mở màn hình ra để biết "có gì đang hỏng không", nên câu trả
        lời an toàn là có. Chi tiết nằm ở `theo_thao_tac`.
        """
        bay_gio = self._dong_ho()
        theo = {
            ten: {
                "mach_mo": bay_gio < self._mo_den.get(ten, 0.0),
                "hong_lien_tiep": self._hong.get(ten, 0),
            }
            for ten in ("gia", "ton_kho")
        }
        return {
            "nguon": getattr(self._nguon, "ten", "?"),
            "mach_mo": any(x["mach_mo"] for x in theo.values()),
            "hong_lien_tiep": max(x["hong_lien_tiep"] for x in theo.values()),
            "theo_thao_tac": theo,
            "so_o_cache": {ten: len(c) for ten, c in self._cache.items()},
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

        ho_so, don_hang = ho_so_tu_van.doc(self._duong_dan_tu_van)
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
