"""
Nửa TƯ VẤN của sản phẩm: da phù hợp, thành phần, pH, số công bố…

VÌ SAO LÀ MODULE RIÊNG
----------------------
Trước đây đường dẫn `catalog.json` sống trong `tep.py`, và `cong.py` phải
`from agent.erp.tep import CATALOG` để đọc nửa tư vấn.

Đó là một đảo ngược lớp: `Cong` là cái cổng TỔNG QUÁT, nó không được biết
adapter `tep` có tồn tại hay không. Cắm Odoo vào thì `tep` vẫn bị kéo theo,
chỉ vì nó tình cờ giữ hai hằng số đường dẫn.

Tách ra đây thì cả hai bên cùng phụ thuộc vào một module trung lập, và
`Cong` gỡ được một trách nhiệm.

VÌ SAO NỬA NÀY KHÔNG NẰM TRONG ERP
----------------------------------
Đối chiếu 14 trường của bản ghi sản phẩm với những gì Odoo/ERPNext cho sẵn:
chín trường không tồn tại bên ERP — và chín trường đó chính là toàn bộ chất
tư vấn. ERP kế toán không phải chỗ chứa văn bản tư vấn, và để chúng ở đây
thì đổi ERP không mất gì.
"""
from __future__ import annotations

import json
import pathlib

from agent.config import ROOT

CATALOG = ROOT / "data" / "catalog.json"
CATALOG_MAU = ROOT / "data" / "catalog.example.json"


def duong_dan(uu_tien: pathlib.Path | None = None) -> pathlib.Path:
    """File nào đang giữ nửa tư vấn.

    Bỏ qua `uu_tien` khi file đó KHÔNG tồn tại là có chủ ý: đó là đường lui
    về bản mẫu. `catalog.json` nằm trong .gitignore nên không đi theo repo,
    và thiếu đường lui thì máy vừa clone chạy ra rỗng.
    """
    if uu_tien is not None and uu_tien.exists():
        return uu_tien
    return CATALOG if CATALOG.exists() else CATALOG_MAU


def doc(uu_tien: pathlib.Path | None = None) -> tuple[dict[str, dict], list]:
    """Trả `({mã: hồ sơ tư vấn}, đơn hàng mẫu)`.

    File hỏng thì trả rỗng chứ không ném: thiếu nửa tư vấn làm agent nghèo
    đi, nhưng KHÔNG làm nó nói sai giá hay tồn kho. Hai mức nghiêm trọng
    khác nhau nên xử lý khác nhau — đường ĐỌC danh mục thì ném (xem
    `tep.py`), đường đọc hồ sơ thì chịu.
    """
    dd = duong_dan(uu_tien)
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
