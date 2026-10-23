"""
Mã nguồn của tầng API dashboard, cho các test canh bằng văn bản/AST.

Trước 23.10.2026 mọi route nằm trong `agent/api/routes.py`; test đọc thẳng
tệp đó. Sau khi tách theo miền, `routes.py` chỉ còn gộp router — test đọc nó
sẽ thấy RỖNG và đỏ (hoặc tệ hơn: một phép `count(...) == 0` sẽ xanh giả).
Đọc qua đây để test không phụ thuộc chuyện route nằm ở module nào.
"""
from __future__ import annotations

import ast
from pathlib import Path

THU_MUC = Path(__file__).resolve().parents[1] / "agent" / "api"


def cac_tep() -> list[Path]:
    """routes.py + mọi module nó gộp router — đọc từ chính routes.py."""
    goc = THU_MUC / "routes.py"
    ten = []
    for n in ast.parse(goc.read_text(encoding="utf-8")).body:
        if isinstance(n, ast.ImportFrom) and n.level == 1 and n.module is None:
            ten += [a.name for a in n.names]
    tep = [goc, THU_MUC / "phu_thuoc.py", *(THU_MUC / f"{t}.py" for t in ten)]
    thieu = [str(p) for p in tep if not p.exists()]
    assert not thieu, f"routes.py gộp module không tồn tại: {thieu}"
    assert len(tep) > 3, "routes.py không còn gộp module nào — test đọc nguồn sẽ xanh giả"
    return tep


def nguon_api() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in dict.fromkeys(cac_tep()))


def cay_api() -> ast.Module:
    """Một cây AST gộp — đủ cho test tìm hàm theo tên."""
    than: list[ast.stmt] = []
    for p in dict.fromkeys(cac_tep()):
        than += ast.parse(p.read_text(encoding="utf-8")).body
    return ast.Module(body=than, type_ignores=[])


def duong_api() -> set[str]:
    """Mọi đường dẫn route của router dashboard, đã duyệt phẳng router lồng."""
    from agent.api.routes import router
    from agent.core.quyen import moi_route

    return {getattr(r, "path", "") for r in moi_route(router.routes)}
