"""
Sinh sơ đồ cơ sở dữ liệu TỪ `agent/schema.sql`, không vẽ tay.

    python -m scripts.sinh_so_do            in ra màn hình
    python -m scripts.sinh_so_do --ghi      ghi vào docs/kien-truc.md

VÌ SAO SINH RA CHỨ KHÔNG VẼ
---------------------------
Sơ đồ ERD vẽ tay đúng đúng một ngày: ngày người ta vẽ nó. Thêm một cột,
đổi một khoá ngoại, và tài liệu bắt đầu nói dối — im lặng, vì không có gì
kiểm tra sơ đồ với schema.

Repo này đã dính đúng chuyện đó hai lần trong một ngày: README liệt kê bốn
thiếu sót đã làm xong từ lâu, và `he_thong.py` viết rằng proxy "không làm
được" trong khi lớp proxy đang chạy. Cả hai đều là tài liệu nói ngược mã.

Sinh từ `schema.sql` thì sơ đồ không thể sai: nguồn duy nhất là chính file
mà Postgres đọc lúc khởi động.

GIỚI HẠN — NÓI RÕ ĐỂ KHÔNG AI TIN NHẦM
--------------------------------------
Bộ đọc ở đây là regex, không phải bộ phân tích cú pháp SQL đầy đủ. Nó hiểu
đúng lối viết của `schema.sql` hiện tại: `CREATE TABLE IF NOT EXISTS`, cột
một dòng, `REFERENCES <bảng>` nằm cùng dòng với cột. Viết SQL theo kiểu
khác — ràng buộc khoá ngoại tách riêng ở cuối bảng chẳng hạn — thì nó bỏ
sót mà không báo.

Chấp nhận được vì `schema.sql` là file của chính dự án này và giữ một lối
viết. Ngày nào lối viết đổi, phải sửa cả đây — và có test canh việc số bảng
sinh ra khớp với số bảng trong schema.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCHEMA = ROOT / "agent" / "schema.sql"
RA = ROOT / "docs" / "kien-truc.md"

# Nhóm bảng theo phần nghiệp vụ. Một ERD 16 bảng phẳng thì không ai đọc
# nổi; chia nhóm là thứ biến một mớ hộp thành một câu chuyện.
NHOM = {
    "Hội thoại": ["conversations", "messages", "ho_so_khach", "processed_webhooks"],
    "Bán hàng": ["orders", "ton_kho", "kho_bien_dong"],
    "Tri thức (RAG)": ["documents", "chunks"],
    "Nội dung": ["videos", "video_assets", "posts", "post_metrics"],
    "Vận hành": ["nguoi_dung", "phien", "events", "zalo_oa_token"],
}

# Cột nào đáng hiện trên sơ đồ. Vẽ đủ 20 cột mỗi bảng thì sơ đồ thành bảng
# tính. Chỉ giữ khoá, khoá ngoại, và cột mang ý nghĩa nghiệp vụ.
BO_QUA_COT = {
    "created_at", "updated_at", "tokens_in", "tokens_out", "cache_read",
    "latency_ms", "model", "sources", "grounded", "confidence",
}


def doc_schema() -> tuple[dict[str, list[tuple[str, str]]], list[tuple[str, str]]]:
    """Trả về ({bảng: [(cột, kiểu)]}, [(bảng con, bảng cha)])."""
    sql = SCHEMA.read_text(encoding="utf-8")
    bang: dict[str, list[tuple[str, str]]] = {}
    khoa_ngoai: list[tuple[str, str]] = []

    for khoi in re.finditer(
        r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\);", sql, re.S
    ):
        ten, than = khoi.group(1), khoi.group(2)
        cot: list[tuple[str, str]] = []
        for dong in than.splitlines():
            d = dong.strip()
            if not d or d.startswith("--"):
                continue
            m = re.match(r"(\w+)\s+([A-Z][A-Z0-9_]*(?:\(\d+(?:,\s*\d+)?\))?)", d)
            if not m:
                continue
            ten_cot, kieu = m.group(1), m.group(2)
            if (ref := re.search(r"REFERENCES (\w+)", d)):
                khoa_ngoai.append((ten, ref.group(1)))
            if ten_cot not in BO_QUA_COT:
                cot.append((ten_cot, kieu.split("(")[0]))
        bang[ten] = cot
    return bang, khoa_ngoai


def erd(bang: dict, khoa_ngoai: list) -> str:
    """Sơ đồ quan hệ thực thể, dạng Mermaid."""
    d = ["```mermaid", "erDiagram"]
    for ten, cot in bang.items():
        d.append(f"    {ten} {{")
        for c, k in cot[:8]:      # 8 cột là ngưỡng còn đọc được khi in ra giấy
            d.append(f"        {k} {c}")
        if len(cot) > 8:
            d.append(f"        _ con_{len(cot) - 8}_cot_nua")
        d.append("    }")
    for con, cha in sorted(set(khoa_ngoai)):
        d.append(f"    {cha} ||--o{{ {con} : \"\"")
    d.append("```")
    return "\n".join(d)


def kien_truc() -> str:
    """Sơ đồ khối. Phần này VIẾT TAY, vì nó là quyết định chứ không phải dữ liệu."""
    return """```mermaid
flowchart TB
    subgraph kenh["Kênh — ChannelAdapter là ranh giới"]
        zalo["Zalo<br/>(ZaloCRM, kéo)"]
        cw["Facebook · Instagram · WhatsApp<br/>web · email (Chatwoot, đẩy)"]
    end

    subgraph loi["Lõi agent"]
        gac["Chốt vào<br/>trần chi phí · quét injection"]
        rag[("RAG<br/>pgvector")]
        hs[("Hồ sơ khách")]
        llm["Vòng gọi model<br/>+ 7 công cụ"]
        luoi["Năm lớp lưới<br/>tuân thủ · thẩm quyền · hứa suông"]
    end

    subgraph ra["Đầu ra"]
        khach["Khách"]
        nguoi["Hàng đợi trực<br/>chờ-lâu-nhất-trước"]
        video["Hàng đợi video"]
        bai["Đăng bài<br/>n8n → API → thủ công"]
    end

    zalo & cw --> gac
    gac --> rag & hs --> llm --> luoi
    luoi -->|đủ thẩm quyền| khach
    luoi -->|vượt khả năng| nguoi
    llm -.-> video & bai

    canh["Canh gác<br/>9 phép kiểm"] -.->|báo khi ĐỔI trạng thái| nguoi
```"""


def luong_tin() -> str:
    """Luồng một tin nhắn, từ lúc khách gõ tới lúc có người nhận việc."""
    return """```mermaid
sequenceDiagram
    autonumber
    actor K as Khách
    participant C as Kênh
    participant M as handle_inbound
    participant A as core.agent
    participant T as Công cụ
    participant N as Người trực

    K->>C: "da em dầu, có gì hợp không?"
    C->>M: webhook / polling
    M->>M: chống trùng · lưu tin · lưu ảnh kèm

    alt Ảnh không kèm chữ
        M->>N: chuyển người ngay
        M-->>K: câu báo (đổi theo giờ trực)
    else Có chữ
        M->>A: respond(history, hồ sơ khách)
        A->>A: quét prompt injection
        A->>A: tra RAG + nạp hồ sơ khách
        loop tối đa N vòng
            A->>T: tra_cuu_san_pham / goi_y_san_pham …
            T-->>A: số liệu thật
        end
        A->>A: 5 lớp lưới
        alt Đủ thẩm quyền
            A-->>M: câu trả lời có căn cứ
            M-->>K: tách 2-3 tin, có nhịp gõ
        else Vượt khả năng
            A-->>M: escalate + lý do
            M->>N: ghi chú nội bộ + nhãn
            M-->>K: câu CỐ ĐỊNH, không phải lời model
        end
    end
```"""


def truong_hop_dung() -> str:
    return """```mermaid
flowchart LR
    khach((Khách))
    nv((Nhân viên trực))
    qt((Quản trị))
    ngoai((Ứng dụng ngoài<br/>qua MCP))

    khach --- u1["Hỏi sản phẩm, giá, tồn kho"]
    khach --- u2["Hỏi chính sách"]
    khach --- u3["Đặt hàng"]
    khach --- u4["Gửi ảnh"]

    nv --- u5["Nhận hội thoại chuyển người"]
    nv --- u6["Duyệt câu trả lời (chế độ assist)"]
    nv --- u7["Duyệt bài đăng"]
    nv --- u8["Nhập kho, xử lý đơn"]

    qt --- u9["Xoá dữ liệu khách (NĐ 13)"]
    qt --- u10["Bật/tắt agent, đổi ngưỡng"]
    qt --- u11["Quản lý tài khoản"]

    ngoai --- u12["Tra cứu, xem số liệu"]
    ngoai --- u13["Soạn bài nháp"]
```"""


def dung_tai_lieu() -> str:
    bang, kn = doc_schema()
    nhom_md = []
    for ten_nhom, ds in NHOM.items():
        co = [b for b in ds if b in bang]
        nhom_md.append(f"| **{ten_nhom}** | {' · '.join(f'`{b}`' for b in co)} |")
    chua_nhom = [b for b in bang if not any(b in v for v in NHOM.values())]
    if chua_nhom:
        nhom_md.append(f"| (chưa xếp nhóm) | {' · '.join(f'`{b}`' for b in chua_nhom)} |")

    return f"""# Kiến trúc hệ thống

> **Sơ đồ cơ sở dữ liệu trong tài liệu này được SINH RA từ
> `agent/schema.sql`** bằng `python -m scripts.sinh_so_do --ghi`.
> Đừng sửa tay phần đó — sửa schema rồi sinh lại.
>
> Lý do: sơ đồ vẽ tay đúng đúng một ngày, ngày người ta vẽ nó. Repo này đã
> dính hai lần tài liệu nói ngược mã trong cùng một ngày, nên phần nào sinh
> được thì sinh.

---

## 1. Sơ đồ khối

Hai ranh giới quyết định toàn bộ hình dạng hệ thống: `ChannelAdapter` ở đầu
vào và `PublishAdapter` ở đầu ra. Đổi Zalo cá nhân sang Zalo OA là viết
thêm một lớp con — không đụng agent, RAG, video hay dashboard.

{kien_truc()}

---

## 2. Luồng một tin nhắn

Đường đi từ lúc khách gõ tới lúc có người nhận việc. Nhánh **ảnh không kèm
chữ** tách riêng có chủ đích: nhìn ảnh da rồi khuyên dùng gì chính là chẩn
đoán, việc mà hệ thống không có thẩm quyền.

{luong_tin()}

---

## 3. Trường hợp sử dụng

{truong_hop_dung()}

---

## 4. Cơ sở dữ liệu

{len(bang)} bảng, chia theo phần nghiệp vụ:

| Nhóm | Bảng |
|---|---|
{chr(10).join(nhom_md)}

{erd(bang, kn)}

Sơ đồ lược bớt các cột đo lường (`tokens_in`, `latency_ms`, `created_at`…)
để còn đọc được. Định nghĩa đầy đủ nằm ở [`agent/schema.sql`](../agent/schema.sql).

---

## 5. Bốn nguyên tắc

| Nguyên tắc | Nằm ở đâu |
|---|---|
| Không phát ngôn không căn cứ — giá, tồn kho, đơn chỉ đến từ công cụ | `agent/core/tools.py` |
| Nội dung ra công chúng luôn phải có người duyệt — ràng buộc trong MÃ, không trong prompt | `agent/publish/service.py` |
| Âm thanh trước, hình sau — thời lượng đo bằng `ffprobe`, không để model đoán | `agent/video/timing.py` |
| Biết dừng đúng lúc — năm lớp lưới độc lập, mỗi lớp canh một cách trượt | `agent/core/agent.py` |
"""


def main() -> int:
    md = dung_tai_lieu()
    if "--ghi" in sys.argv:
        RA.write_text(md, encoding="utf-8")
        print(f"Đã ghi {RA.relative_to(ROOT)}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
