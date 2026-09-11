"""
Chèn `DANH_SACH_HOAN` đã sinh vào `agent/core/quyen.py`. TỆP TẠM.

Chạy: python -m scripts._chen_danh_sach_hoan
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.core.quyen import MIEN_TRU, moi_route  # noqa: E402
from agent.main import app  # noqa: E402

DICH = Path(__file__).resolve().parent.parent / "agent" / "core" / "quyen.py"
CU = "DANH_SACH_HOAN: frozenset[tuple[str, str]] = frozenset()"


def main() -> None:
    ds = set()
    for r in moi_route(app.routes):
        duong = getattr(r, "path", "")
        if not duong.startswith(("/api", "/tich-hop")):
            continue
        phu_thuoc = getattr(getattr(r, "dependant", None), "dependencies", ())
        if any(getattr(x.call, "quyen_yeu_cau", None) for x in phu_thuoc):
            continue
        for pt in sorted(getattr(r, "methods", None) or set()):
            if pt in {"HEAD", "OPTIONS"} or (pt, duong) in MIEN_TRU:
                continue
            ds.add((pt, duong))

    dong = [f'    ("{pt}", "{duong}"),'
            for pt, duong in sorted(ds, key=lambda x: (x[1], x[0]))]
    moi = ("DANH_SACH_HOAN: frozenset[tuple[str, str]] = frozenset({\n"
           + "\n".join(dong) + "\n})")

    noi_dung = DICH.read_text(encoding="utf-8")
    if CU not in noi_dung:
        raise SystemExit("Không tìm thấy dòng DANH_SACH_HOAN rỗng để thay.")
    DICH.write_text(noi_dung.replace(CU, moi), encoding="utf-8")
    print(f"Đã chèn {len(ds)} cặp vào {DICH.name}")


if __name__ == "__main__":
    main()
