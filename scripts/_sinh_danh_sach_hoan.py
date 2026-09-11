"""
Sinh `DANH_SACH_HOAN` cho `agent/core/quyen.py`. TỆP TẠM — xoá ở Việc 10.

Gõ tay 158 cặp (phương thức, đường dẫn) là gõ sai. Sai theo hướng thừa thì
danh sách không rỗng được; sai theo hướng thiếu thì máy chủ không khởi động
giữa chừng A1 và không ai biết vì sao.

Chạy: python -m scripts._sinh_danh_sach_hoan
"""
from __future__ import annotations

import os

os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.core.quyen import MIEN_TRU, moi_route  # noqa: E402
from agent.main import app  # noqa: E402


def main() -> None:
    ds = set()
    for r in moi_route(app.routes):
        duong = getattr(r, "path", "")
        if not duong.startswith(("/api", "/tich-hop")):
            continue
        phu_thuoc = getattr(getattr(r, "dependant", None), "dependencies", ())
        if any(getattr(x.call, "quyen_yeu_cau", None) for x in phu_thuoc):
            continue                      # đã khai quyền rồi, không hoãn nữa
        for pt in sorted(getattr(r, "methods", None) or set()):
            if pt in {"HEAD", "OPTIONS"} or (pt, duong) in MIEN_TRU:
                continue
            ds.add((pt, duong))

    for pt, duong in sorted(ds, key=lambda x: (x[1], x[0])):
        print(f'    ("{pt}", "{duong}"),')
    print(f"    # tổng: {len(ds)}")


if __name__ == "__main__":
    main()
