"""
Nạp tài liệu vào cơ sở tri thức.

    python -m scripts.ingest data/knowledge

Đọc mọi file .md / .txt trong thư mục, cắt đoạn, tạo embedding, ghi vào pgvector.
Cần: Postgres đang chạy + đã `gcloud auth application-default login`.
"""
from __future__ import annotations

import asyncio
import sys

# Console Windows mac dinh cp1252 khong in duoc tieng Viet.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import db          # noqa: E402
from agent.core import rag    # noqa: E402

GIAN_CACH_GIAY = 3.0
SUFFIXES = {".md", ".txt"}


async def main(folder: str) -> None:
    root = Path(folder)
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in SUFFIXES)         if root.exists() else []

    # Máy vừa clone repo về không có `data/knowledge/` — thư mục đó chứa
    # tài liệu THẬT của doanh nghiệp nên nằm trong .gitignore. Rơi về bản
    # mẫu đi kèm repo, đúng cách `_catalog()` rơi về catalog.example.json.
    # Không có bước này thì người mới clone chạy agent với kho tri thức
    # rỗng, và không hiểu vì sao agent trả lời "chưa có thông tin đó".
    if not files:
        mau = root.parent / f"{root.name}.example"
        if mau.exists():
            files = sorted(p for p in mau.rglob("*") if p.suffix.lower() in SUFFIXES)
            if files:
                print(f"Không có tài liệu thật trong {root} — dùng bản mẫu {mau.name}")
    if not files:
        print(f"Không có file .md hoặc .txt trong {root}")
        return

    await db.init_db()
    total = 0
    try:
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if len(text) < 20:
                print(f"  bỏ qua (quá ngắn): {path.name}")
                continue
            n = await rag.ingest(path.stem, str(path), text)
            total += n
            print(f"  {path.name}: {n} đoạn", flush=True)
            # Giãn nhịp giữa các tài liệu. Hạn mức embedding của Vertex tính
            # theo phút, nên bắn 12 tài liệu liên tiếp là chạm trần rồi phải
            # ngồi chờ backoff — chậm hơn nhiều so với đi đều từ đầu.
            await asyncio.sleep(GIAN_CACH_GIAY)
    finally:
        await db.close_db()

    print(f"\nXong. {len(files)} tài liệu, {total} đoạn.")
    print("Gợi ý: khi corpus đủ lớn, tạo index cho nhanh:")
    print("  CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists=100);")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "data/knowledge"))
