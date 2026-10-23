"""
Đóng gói JavaScript của dashboard: `dashboard/src/*.js` -> `dashboard/app.js`.

    python -m scripts.dong_goi_dashboard          ghi lại app.js
    python -m scripts.dong_goi_dashboard --kiem   chỉ kiểm, mã thoát 1 nếu app.js đã cũ

VÌ SAO NỐI TỆP, KHÔNG DÙNG ES MODULE HAY BUNDLER
------------------------------------------------
`app.js` từng là MỘT tệp 7.100 dòng — không ai đọc hết được, và mỗi lần sửa
là mở một tệp 340 KB. Nay mã nằm ở `dashboard/src/`, mỗi tệp một miền màn
hình (hội thoại, khách hàng, kỹ năng...), vài trăm dòng.

Trình duyệt vẫn tải đúng MỘT `app.js`, và đó là `src/*.js` nối lại NGUYÊN
VĂN theo thứ tự tên tệp. Chọn cách này thay vì `<script type="module">` vì:

  · ES module đổi ngữ nghĩa: hàm không còn là biến toàn cục, mà
    `index.html` gọi chúng thẳng qua `onclick="..."` ở hàng trăm chỗ.
    Đổi sang module là sửa cả hai phía cùng lúc, và chỗ nào sót thì nút
    bấm chết im lặng.
  · Nhiều thẻ `<script>` rời: hàm khai báo ở tệp sau không dùng được trong
    mã CHẠY NGAY của tệp trước (hoisting chỉ trong một tệp) — lỗi chỉ lộ
    ra lúc chạy, trên trình duyệt.
  · Bundler (esbuild, webpack) là một chuỗi công cụ Node chỉ để làm đúng
    việc nối chuỗi này.

Nối nguyên văn thì byte trình duyệt nhận KHÔNG ĐỔI — tách tệp không thể làm
hỏng gì lúc chạy. `tests/test_dong_goi_dashboard.py` đỏ khi `app.js` lệch
với `src/` — cùng khuôn với tài liệu sinh ra (`sinh_so_do --ghi`).
"""
from __future__ import annotations

import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
SRC = GOC / "dashboard" / "src"
DICH = GOC / "dashboard" / "app.js"

DAU_TEP = (
    "/* TỆP SINH RA — ĐỪNG SỬA TAY. Mã nguồn ở dashboard/src/*.js; sửa ở đó rồi\n"
    "   chạy: python -m scripts.dong_goi_dashboard */\n"
)


def cac_tep() -> list[Path]:
    tep = sorted(SRC.glob("*.js"))
    if not tep:
        raise SystemExit(f"Không có tệp nào trong {SRC} — đường dẫn sai?")
    return tep


def dong_goi() -> str:
    return DAU_TEP + "".join(p.read_text(encoding="utf-8") for p in cac_tep())


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    moi = dong_goi()
    cu = DICH.read_text(encoding="utf-8") if DICH.exists() else ""
    if "--kiem" in argv:
        if moi != cu:
            print("dashboard/app.js ĐÃ CŨ so với dashboard/src/ — chạy: "
                  "python -m scripts.dong_goi_dashboard")
            return 1
        print(f"dashboard/app.js khớp {len(cac_tep())} tệp nguồn")
        return 0
    DICH.write_text(moi, encoding="utf-8", newline="\n")
    print(f"Đã ghi dashboard/app.js từ {len(cac_tep())} tệp ({len(moi)} ký tự)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
