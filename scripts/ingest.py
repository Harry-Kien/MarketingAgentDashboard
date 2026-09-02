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
from agent.tri_thuc import loc_tep_nap_duoc  # noqa: E402

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

    # CHỐT: khung chưa có người điền thì KHÔNG vào kho.
    #
    # Tệp khung do `scripts.sinh_kho_tri_thuc` sinh ra trông y như tài liệu
    # thật — có tiêu đề, có mục, có cấu trúc. Nạp nó vào pgvector thì
    # `tim_kien_thuc` sẽ trả về những dòng "[CẦN NGƯỜI ĐIỀN: đổi trả bao
    # nhiêu ngày?]" với điểm khớp CAO, vì câu hỏi của khách và câu hỏi
    # trong khung dùng chung từ vựng.
    #
    # Agent đọc đoạn đó như căn cứ. Nó không nói sai con số, nhưng nó cũng
    # không nói "chưa biết" — và độ tin cậy được nâng lên bởi chính đoạn
    # rỗng ấy, nên chốt chuyển người vì độ tin cậy thấp không nổ nữa.
    # Kho rỗng làm agent trông TỰ TIN HƠN agent không có gì.
    files, bi_chan = loc_tep_nap_duoc(files)
    if bi_chan:
        print(f"\nTỪ CHỐI {len(bi_chan)} tệp còn khung chưa điền:\n")
        for path, thieu in bi_chan.items():
            print(f"  {path.name} — còn {len(thieu)} câu chưa trả lời")
            for ch in thieu[:3]:
                print(f"      · {ch}")
            if len(thieu) > 3:
                print(f"      · … và {len(thieu) - 3} câu nữa")
        print("\nĐiền xong rồi chạy lại. Xem agent/tri_thuc/chot.py.\n")
    if not files:
        print("Không còn tệp nào nạp được.")
        return

    await db.init_db()

    # GỠ TÀI LIỆU KHÔNG CÒN TỆP TRÊN ĐĨA.
    #
    # `rag.ingest` thay bản cũ theo `source`, nhưng KHÔNG BAO GIỜ xoá tài
    # liệu mà tệp đã biến mất. Nghĩa là gỡ một tệp tri thức khỏi thư mục
    # thì nội dung nó vẫn sống trong pgvector, và agent vẫn trích dẫn —
    # kèm tên tài liệu, đầy tự tin, từ một tệp không còn tồn tại.
    #
    # Đúng họ với dòng tồn kho mồ côi: đồng bộ chỉ-thêm luôn để lại rác, và
    # rác ở kho tri thức thì được đọc như CĂN CỨ.
    #
    # Chỉ gỡ tài liệu có `source` nằm TRONG thư mục đang nạp. Xoá theo kiểu
    # "không có trong danh sách lần này" là nạp một thư mục con sẽ quét
    # sạch mọi thứ ngoài nó.
    #
    # LỌC TRONG PYTHON, KHÔNG DÙNG `LIKE` TRÊN ĐƯỜNG DẪN.
    #
    # Bản đầu dùng `WHERE source LIKE 'data\knowledge%'`. PostgreSQL coi `\`
    # là ký tự THOÁT trong LIKE, nên mẫu đó bị đọc thành `dataknowledge%` và
    # khớp KHÔNG GÌ CẢ. Kết quả: lệnh chạy, in "Xong", không gỡ tài liệu
    # nào — và không có gì báo là nó vừa không làm việc mình nói.
    #
    # Bảng này vài chục dòng, lọc trong Python vừa đúng vừa hết chuyện.
    con_tren_dia = {str(p) for p in files}
    thu_muc = str(files[0].parent)
    cu = await db.fetch("SELECT title, source FROM documents")
    can_go = [
        r for r in cu
        if str(r["source"]).startswith(thu_muc)
        and r["source"] not in con_tren_dia
    ]
    mo_coi = {r["title"] for r in can_go}
    if can_go:
        await db.execute(
            "DELETE FROM documents WHERE source = ANY($1)",
            [r["source"] for r in can_go],
        )

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
    if mo_coi:
        print(f"Đã gỡ {len(mo_coi)} tài liệu không còn tệp: "
              + ", ".join(sorted(mo_coi)[:5])
              + (" …" if len(mo_coi) > 5 else ""))
    print("Gợi ý: khi corpus đủ lớn, tạo index cho nhanh:")
    print("  CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists=100);")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "data/knowledge"))
