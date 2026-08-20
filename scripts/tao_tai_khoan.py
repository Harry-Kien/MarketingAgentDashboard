"""
Tạo tài khoản đăng nhập cho dashboard.

    python -m scripts.tao_tai_khoan admin "Mật khẩu mạnh" --quan-tri
    python -m scripts.tao_tai_khoan lan "Mật khẩu khác"

VÌ SAO LÀ SCRIPT CHỨ KHÔNG PHẢI TRANG "TẠO TÀI KHOẢN ĐẦU TIÊN"
--------------------------------------------------------------
Trang bootstrap trên web là một cửa mở: giữa lúc cài xong và lúc chủ hệ
thống kịp vào tạo tài khoản, bất kỳ ai chạm được cổng đó đều tự phong mình
làm quản trị. Cửa sổ ấy có thể là vài giây, cũng có thể là vài ngày.

Chạy trên máy chủ thì người chạy đã có quyền trên máy đó rồi — không mở
thêm cửa nào.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import db            # noqa: E402
from agent.core import xac_thuc  # noqa: E402


async def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    ten, mat_khau = argv[0], argv[1]
    vai_tro = "quan_tri" if "--quan-tri" in argv else "nhan_vien"

    await db.init_db()
    try:
        dau_tien = not await xac_thuc.co_nguoi_dung_nao_chua()
        if dau_tien and vai_tro != "quan_tri":
            # Tài khoản đầu tiên phải là quản trị, nếu không hệ thống có
            # người dùng mà không ai tạo được người dùng tiếp theo.
            vai_tro = "quan_tri"
            print("Tài khoản đầu tiên -> đặt thành quản trị.")
        nd = await xac_thuc.tao_nguoi_dung(ten, mat_khau, vai_tro=vai_tro)
    except ValueError as exc:
        print(f"Không tạo được: {exc}")
        return 1
    finally:
        await db.close_db()

    print(f"Đã tạo {nd['ten_dang_nhap']} ({nd['vai_tro']}).")
    print("Đăng nhập tại http://127.0.0.1:8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
