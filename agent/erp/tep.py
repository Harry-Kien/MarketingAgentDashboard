"""
Adapter đọc `data/catalog.json` — nguồn MẶC ĐỊNH.

VÌ SAO NÓ TỒN TẠI KHI ĐÃ CÓ ADAPTER ERP THẬT
--------------------------------------------
`catalog.json` nằm trong .gitignore nên không đi theo repo. Không có adapter
này làm mặc định thì máy vừa clone về phải dựng xong Odoo mới chạy được một
dòng — và CI job `clone-sach` chết.

Nó cũng là bản đối chiếu: test hợp đồng chạy chung cho cả bốn adapter, và
adapter này là cái rẻ nhất để chạy chúng.

VÌ SAO FILE HỎNG THÌ NÉM CHỨ KHÔNG TRẢ RỖNG
-------------------------------------------
Trả rỗng nghĩa là "cửa hàng không có sản phẩm nào". Agent tin, chuyển hết
cho người, và không có dòng log nào nói vì sao. Đó đúng là khuôn hỏng im
lặng đã cắn repo này bốn lần.
"""
from __future__ import annotations

import json
import pathlib

from agent.config import ROOT
from agent.erp.hop_dong import Gia, LoiERP, SanPhamERP, TonKho

CATALOG = ROOT / "data" / "catalog.json"
CATALOG_MAU = ROOT / "data" / "catalog.example.json"


class NguonTep:
    ten = "tep"

    def __init__(self, duong_dan: pathlib.Path | None = None):
        self._duong_dan = duong_dan

    def _duong(self) -> pathlib.Path:
        # Bỏ qua `duong_dan` khi file đó KHÔNG tồn tại là có chủ ý: đó là
        # đường lui về bản mẫu. Nhưng file tồn tại mà hỏng thì vẫn phải nổ —
        # xem `_doc`.
        dd = self._duong_dan
        if dd is not None and dd.exists():
            return dd
        return CATALOG if CATALOG.exists() else CATALOG_MAU

    def _doc(self) -> dict:
        dd = self._duong()
        try:
            return json.loads(dd.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise LoiERP(f"Không đọc được danh mục {dd.name}: {exc}") from exc

    async def danh_sach_san_pham(
        self, chi_ban_duoc: bool = True
    ) -> list[SanPhamERP]:
        ds = [
            SanPhamERP(
                ma=str(sp.get("ma", "")),
                ten=str(sp.get("ten", "")),
                loai=str(sp.get("loai") or ""),
                dung_tich=str(sp.get("dung_tich") or ""),
                ban_duoc_phep=not sp.get("ngung_ban", False),
            )
            for sp in self._doc().get("san_pham", [])
        ]
        return [sp for sp in ds if sp.ban_duoc_phep] if chi_ban_duoc else ds

    async def gia(self, ma: str) -> Gia | None:
        for sp in self._doc().get("san_pham", []):
            if sp.get("ma") == ma and sp.get("gia") is not None:
                return Gia(gia_ban=int(sp["gia"]), nguon="catalog.json")
        return None

    async def ton_kho(self, ma: str) -> TonKho | None:
        for sp in self._doc().get("san_pham", []):
            if sp.get("ma") == ma and sp.get("ton_kho") is not None:
                return TonKho(ban_duoc=int(sp["ton_kho"]))
        return None

    async def suc_khoe(self) -> bool:
        try:
            self._doc()
        except LoiERP:
            return False
        return True
