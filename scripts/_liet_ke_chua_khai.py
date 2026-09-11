"""In tên hàm của route chưa khai quyền. TỆP TẠM, xoá ở Việc 10."""
from __future__ import annotations

import os

os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.core.quyen import MIEN_TRU, moi_route  # noqa: E402
from agent.main import app  # noqa: E402


def main() -> None:
    for r in sorted(moi_route(app.routes), key=lambda x: getattr(x, "path", "")):
        duong = getattr(r, "path", "")
        if not duong.startswith(("/api", "/tich-hop")):
            continue
        phu_thuoc = getattr(getattr(r, "dependant", None), "dependencies", ())
        if any(getattr(x.call, "quyen_yeu_cau", None) for x in phu_thuoc):
            continue
        pts = sorted((getattr(r, "methods", None) or set())
                     - {"HEAD", "OPTIONS"})
        pts = [p for p in pts if (p, duong) not in MIEN_TRU]
        if not pts:
            continue
        ten = getattr(getattr(r, "endpoint", None), "__name__", "?")
        print(f'    "{ten}": "",   # {",".join(pts)} {duong}')


if __name__ == "__main__":
    main()
