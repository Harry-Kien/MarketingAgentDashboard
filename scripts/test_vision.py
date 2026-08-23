"""
Soi riêng bước NHÌN ẢNH, không cần Postgres hay Zalo.

    python -m scripts.test_vision data/mau
    python -m scripts.test_vision anh1.jpg anh2.jpg

Dùng khi video ra bố cục lạ: chạy cái này để biết model nhìn ảnh sai, hay
khâu dựng làm sai. Đây chính là lý do bước nhìn ảnh được tách riêng thay vì
gộp vào lời gọi viết kịch bản — có tách thì mới truy ngược được.
"""
from __future__ import annotations

import asyncio
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.video import assets, vision      # noqa: E402

EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def collect(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            out += sorted(q for q in p.iterdir() if q.suffix.lower() in EXTS)
        elif p.suffix.lower() in EXTS and p.exists():
            out.append(p)
    return out


async def main() -> int:
    paths = collect(sys.argv[1:] or ["data/mau"])
    if not paths:
        print("Không thấy ảnh nào. Dùng: python -m scripts.test_vision <thư mục|ảnh>")
        return 1

    tmp = Path("data/videos/_test/vision")
    saved, warns = await assets.save_uploads(
        tmp, [(p.name, p.read_bytes()) for p in paths]
    )
    for w in warns:
        print("  loại bỏ:", w)
    if not saved:
        print("Không ảnh nào qua được bước chuẩn hoá.")
        return 1

    print(f"Gọi model nhìn {len(saved)} ảnh...\n")
    rows, cost = await vision.analyse_all(saved)

    for row, src in zip(rows, paths, strict=True):
        a = row["analysis"]
        mark = "DÙNG ĐƯỢC" if row["usable"] else "LOẠI"
        print(f"[{row['ord']}] {src.name}  ->  {mark}   ({a['nguon']})")
        print(f"     mô tả:       {a['mo_ta'] or '(trống)'}")
        print(f"     vùng trống:  {a['vung_trong']}      màu chủ đạo: {a['mau_chu_dao']}")
        print(f"     độ sáng:     {a['do_sang']}   hướng: {a['huong']}   "
              f"chất lượng: {a['chat_luong']}")
        print(f"     có chữ sẵn:  {a['co_chu_san']}   là ảnh sản phẩm: {a['phu_hop']}")
        print()

    print(f"Chi phí: {cost:.6f} USD")
    print("\nDanh mục sẽ đưa vào prompt kịch bản:")
    print(vision.catalogue(rows))

    if all(r["analysis"]["nguon"] == "mac_dinh" for r in rows):
        print("\nCẢNH BÁO: mọi ảnh đều rơi về mặc định — model không trả lời được.")
        print("Kiểm tra quota Vertex hoặc GCP_PROJECT_ID. Dây chuyền vẫn chạy,")
        print("nhưng chữ sẽ luôn đặt ở nửa dưới thay vì tránh sản phẩm.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
