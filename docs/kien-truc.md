# Kiến trúc hệ thống

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

```mermaid
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
```

---

## 2. Luồng một tin nhắn

Đường đi từ lúc khách gõ tới lúc có người nhận việc. Nhánh **ảnh không kèm
chữ** tách riêng có chủ đích: nhìn ảnh da rồi khuyên dùng gì chính là chẩn
đoán, việc mà hệ thống không có thẩm quyền.

```mermaid
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
```

---

## 3. Trường hợp sử dụng

```mermaid
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
```

---

## 4. Cơ sở dữ liệu

17 bảng, chia theo phần nghiệp vụ:

| Nhóm | Bảng |
|---|---|
| **Hội thoại** | `conversations` · `messages` · `ho_so_khach` · `processed_webhooks` |
| **Bán hàng** | `orders` · `ton_kho` · `kho_bien_dong` |
| **Tri thức (RAG)** | `documents` · `chunks` |
| **Nội dung** | `videos` · `video_assets` · `posts` · `post_metrics` |
| **Vận hành** | `nguoi_dung` · `phien` · `events` · `zalo_oa_token` |

```mermaid
erDiagram
    conversations {
        UUID id
        TEXT channel
        TEXT nen_tang
        TEXT external_id
        TEXT customer_name
        TEXT customer_ref
        TEXT status
        TEXT outcome
        _ con_2_cot_nua
    }
    messages {
        UUID id
        UUID conversation_id
        TEXT role
        TEXT content
        BOOLEAN delivered
        NUMERIC cost_usd
    }
    documents {
        UUID id
        TEXT title
        TEXT source
        INT chunk_count
    }
    chunks {
        UUID id
        UUID document_id
        INT ord
        TEXT content
    }
    videos {
        UUID id
        UUID conversation_id
        TEXT title
        TEXT brief
        TEXT kind
        TEXT status
        TEXT renderer
        REAL duration_s
        _ con_4_cot_nua
    }
    video_assets {
        UUID id
        UUID video_id
        INT ord
        TEXT file_path
        INT width
        INT height
        JSONB analysis
        BOOLEAN usable
    }
    events {
        BIGSERIAL id
        TEXT kind
        TEXT actor
        UUID ref_id
        JSONB detail
    }
    processed_webhooks {
        TEXT message_key
    }
    orders {
        UUID id
        TEXT ma_don
        UUID conversation_id
        TEXT channel
        TEXT khach_ten
        TEXT khach_sdt
        TEXT khach_dia_chi
        JSONB items
        _ con_11_cot_nua
    }
    posts {
        UUID id
        UUID video_id
        TEXT tieu_de
        TEXT noi_dung
        JSONB hashtags
        JSONB kenh
        TEXT trang_thai
        TIMESTAMPTZ lich_dang
        _ con_2_cot_nua
    }
    post_metrics {
        BIGSERIAL id
        UUID post_id
        TEXT kenh
        TEXT url
        BIGINT luot_xem
        BIGINT luot_thich
        BIGINT binh_luan
        BIGINT chia_se
        _ con_2_cot_nua
    }
    ho_so_khach {
        UUID id
        TEXT customer_ref
        TEXT channel
        TEXT ten
        TEXT sdt
        JSONB ghi_nho
        TIMESTAMPTZ lan_dau
        TIMESTAMPTZ lan_cuoi
    }
    ton_kho {
        TEXT ma
        INT so_luong
        TIMESTAMPTZ cap_nhat_luc
    }
    kho_bien_dong {
        BIGSERIAL id
        TEXT ma
        INT thay_doi
        TEXT ly_do
        TEXT ma_don
        TEXT ghi_chu
        TIMESTAMPTZ luc
    }
    nguoi_dung {
        UUID id
        TEXT ten_dang_nhap
        TEXT mat_khau_bam
        TEXT ho_ten
        TEXT vai_tro
        BOOLEAN khoa
        TIMESTAMPTZ tao_luc
        TIMESTAMPTZ dang_nhap_cuoi
    }
    phien {
        TEXT token
        UUID nguoi_dung_id
        TIMESTAMPTZ tao_luc
        TIMESTAMPTZ het_han
    }
    zalo_oa_token {
        TEXT app_id
        TEXT refresh_token
    }
    documents ||--o{ chunks : ""
    conversations ||--o{ messages : ""
    conversations ||--o{ orders : ""
    nguoi_dung ||--o{ phien : ""
    posts ||--o{ post_metrics : ""
    videos ||--o{ posts : ""
    videos ||--o{ video_assets : ""
    conversations ||--o{ videos : ""
```

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
