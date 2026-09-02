"""
Ánh xạ mã sản phẩm nội bộ <-> mã bên ERP.

VÌ SAO KHÔNG GIẢ ĐỊNH CHÚNG TRÙNG NHAU
--------------------------------------
Danh mục nội bộ dùng `AS-CL01`; ERP có thể dùng `ITEM-0001`, hoặc mã vạch,
hoặc mã do kế toán đặt từ đời trước. Giả định chúng trùng là giả định không
ai kiểm — và khi sai thì việc hợp nhất hai nửa dữ liệu lặng lẽ trả rỗng:
agent thấy sản phẩm mà không có thông tin tư vấn nào, không lỗi, không log.

Nên có `kiem()`: chạy lúc khởi động, đếm tỷ lệ khớp, và kêu khi thấp.
"""
from __future__ import annotations

import json
import pathlib

from agent.config import ROOT

ANH_XA_PATH = ROOT / "data" / "anh_xa_ma.json"

# Dưới ngưỡng này thì gần như chắc chắn là cấu hình sai chứ không phải vài
# SKU mới chưa nhập. Kêu to còn hơn để im.
NGUONG_BAO_DONG = 0.9


class AnhXa:
    def __init__(self, bang: dict[str, str] | None = None):
        self._sang = dict(bang or {})
        self._ve = {v: k for k, v in self._sang.items()}

    def sang_erp(self, ma: str) -> str:
        return self._sang.get(ma, ma)

    def ve_noi_bo(self, ma_erp: str) -> str:
        return self._ve.get(ma_erp, ma_erp)


def doc_anh_xa(duong_dan: pathlib.Path | None = None) -> AnhXa:
    dd = duong_dan if duong_dan is not None else ANH_XA_PATH
    if not dd.exists():
        return AnhXa()
    try:
        return AnhXa(json.loads(dd.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        # Ánh xạ hỏng thì coi như đồng nhất, nhưng `kiem()` sẽ thấy tỷ lệ
        # khớp tụt và kêu — không cần nổ ở đây.
        return AnhXa()


async def kiem(ma_noi_bo: list[str], ma_erp: list[str], anh_xa: AnhXa) -> dict:
    """Đếm bao nhiêu mã nội bộ tìm được đối ứng bên ERP."""
    tap_erp = set(ma_erp)
    thieu = [m for m in ma_noi_bo if anh_xa.sang_erp(m) not in tap_erp]
    tong = len(ma_noi_bo)
    khop = tong - len(thieu)
    ty_le = (khop / tong) if tong else 0.0

    if tong and ty_le < NGUONG_BAO_DONG:
        try:
            from agent import db

            await db.log_event(
                "erp.anh_xa_lech",
                tong=tong,
                khop=khop,
                ty_le=round(ty_le, 3),
                thieu=thieu[:20],
            )
        except Exception:  # noqa: BLE001
            pass

    return {"tong": tong, "khop": khop, "ty_le": ty_le, "thieu": thieu}
