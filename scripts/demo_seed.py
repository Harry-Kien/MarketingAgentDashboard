"""
Nạp dữ liệu trình diễn để xem dashboard chạy NGAY, chưa cần Zalo hay Vertex.

    python -m scripts.demo_seed

Chỉ cần Postgres đang chạy (docker compose up -d db). Tạo hội thoại mẫu ở đủ
các trạng thái để băng ca trực và các chỉ số hiện ra đúng như khi chạy thật.

Xoá sạch dữ liệu mẫu:  python -m scripts.demo_seed --clear
"""
from __future__ import annotations

import asyncio
import json
import random
import sys

# Console Windows mac dinh cp1252 khong in duoc tieng Viet.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import db  # noqa: E402

MARK = "demo:"

SCRIPTS = [
    # (khách, [(vai, nội dung, có_căn_cứ, tin_cậy)], trạng thái)
    ("Trần Minh Anh", [
        ("customer", "Shop ơi ghế Aurora M1 còn hàng không ạ?", None, None),
        ("agent", "Dạ còn anh nhé, bên em còn 12 chiếc. Giá 4.290.000đ, bảo hành 24 tháng ạ.", True, 0.87),
        ("customer", "Ok em, có màu xám không?", None, None),
        ("agent", "Dạ có ạ, ghế có hai màu Đen và Xám tro anh nhé.", True, 0.84),
    ], "auto"),
    ("Nguyễn Thu Hà", [
        ("customer", "Bàn nâng hạ Aurora Desk Pro giá bao nhiêu?", None, None),
        ("agent", "Dạ bàn Aurora Desk Pro giá 6.890.000đ ạ. Hiện bên em đang hết hàng, chị để lại số em báo khi có nhé.", True, 0.9),
    ], "auto"),
    ("Phạm Quốc Đạt", [
        ("customer", "Anh mua 5 cái thì giảm được bao nhiêu phần trăm?", None, None),
        ("agent", "Dạ mức giảm cho đơn số lượng lớn em chưa có thẩm quyền quyết, em chuyển anh sang bạn phụ trách nhé.", True, 0.62),
    ], "escalated"),
    ("Lê Bảo Ngọc", [
        ("customer", "Đơn DH20260815 của em tới đâu rồi ạ?", None, None),
        ("agent", "Dạ đơn DH20260815 đang giao, dự kiến chị nhận ngày 21/08 ạ.", True, 0.88),
    ], "auto"),
    ("Vũ Hoàng Long", [
        ("customer", "Ghế này có chống được đau lưng do thoát vị đĩa đệm không em?", None, None),
        ("agent", "Dạ phần này liên quan tới sức khoẻ nên em không dám khẳng định. Em chuyển anh cho bạn tư vấn có chuyên môn nhé.", False, 0.41),
    ], "escalated"),
    ("Đặng Khánh Linh", [
        ("customer", "Đèn Lumen dùng được cho trẻ học bài không?", None, None),
        ("agent", "Dạ đèn Aurora Lumen chống chói RG0 và chỉnh được 5 mức nhiệt màu 2700–6500K nên phù hợp bàn học ạ. Giá 890.000đ, còn 47 cái.", True, 0.81),
    ], "assist"),
    ("Hoàng Nam Phong", [
        ("customer", "Cho anh xin video giới thiệu con ghế Aurora M1 với", None, None),
        ("agent", "Dạ em đang dựng video giới thiệu ghế Aurora M1, xong em gửi anh ngay ạ.", True, 0.86),
    ], "assist"),
    ("Bùi Thanh Trúc", [
        ("customer", "Bên mình có xuất hoá đơn đỏ không?", None, None),
        ("agent", "Dạ em chưa có thông tin này trong tài liệu, để em hỏi lại rồi báo chị nhé.", False, 0.38),
    ], "escalated"),
]

DOC = (
    "Chính sách bảo hành Aurora\n\n"
    "Toàn bộ sản phẩm Aurora được bảo hành chính hãng theo thời hạn ghi trên "
    "phiếu bảo hành, tính từ ngày giao hàng thành công.\n\n"
    "Ghế công thái học Aurora M1: bảo hành 24 tháng cho khung, piston và cơ cấu ngả.\n\n"
    "Bàn nâng hạ Aurora Desk Pro: bảo hành 36 tháng cho động cơ và bộ điều khiển, "
    "12 tháng cho mặt bàn.\n\n"
    "Đèn bàn Aurora Lumen: bảo hành 12 tháng cho bo mạch và nguồn.\n\n"
    "Không áp dụng bảo hành với hư hỏng do rơi vỡ, ngập nước, tự ý tháo lắp, "
    "hoặc sử dụng sai công năng."
)


async def clear() -> None:
    await db.execute(
        "DELETE FROM conversations WHERE external_id LIKE $1", MARK + "%"
    )
    await db.execute("DELETE FROM videos WHERE brief LIKE $1", MARK + "%")
    await db.execute("DELETE FROM documents WHERE source = 'demo'")
    print("Đã xoá dữ liệu trình diễn.")


async def seed() -> None:
    now = datetime.now(timezone.utc)
    rng = random.Random(20260819)

    for i, (name, turns, status) in enumerate(SCRIPTS):
        when = now - timedelta(minutes=17 * (len(SCRIPTS) - i) + rng.randint(0, 9))
        conv = await db.fetchrow(
            """
            INSERT INTO conversations
                (channel, external_id, customer_name, customer_ref, status,
                 outcome, msg_count, created_at, updated_at)
            VALUES ('zalocrm',$1,$2,$1,$3,$4,$5,$6,$6)
            ON CONFLICT (channel, external_id) DO UPDATE
                SET status = EXCLUDED.status, updated_at = EXCLUDED.updated_at
            RETURNING id
            """,
            f"{MARK}{i}",
            name,
            status,
            "escalated" if status == "escalated" else None,
            len(turns),
            when,
        )
        cid = conv["id"]
        await db.execute("DELETE FROM messages WHERE conversation_id = $1", cid)

        total = 0.0
        for j, (role, text, grounded, conf) in enumerate(turns):
            cost = round(rng.uniform(0.0016, 0.0052), 6) if role == "agent" else 0.0
            total += cost
            await db.execute(
                """
                INSERT INTO messages
                    (conversation_id, role, content, delivered, grounded, confidence,
                     sources, model, tokens_in, tokens_out, cache_read, cost_usd,
                     latency_ms, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                """,
                cid, role, text,
                not (role == "agent" and status == "assist"),
                grounded, conf,
                json.dumps(["Chính sách bảo hành Aurora"] if grounded else [],
                           ensure_ascii=False),
                "claude-sonnet-5" if role == "agent" else None,
                rng.randint(700, 1500) if role == "agent" else 0,
                rng.randint(60, 190) if role == "agent" else 0,
                rng.randint(1800, 5200) if role == "agent" else 0,
                cost,
                rng.randint(900, 2600) if role == "agent" else None,
                when + timedelta(seconds=42 * j),
            )
        await db.execute(
            "UPDATE conversations SET cost_usd = $2 WHERE id = $1", cid, total
        )

    # Một video ở trạng thái chờ duyệt để thấy hàng đợi hoạt động.
    await db.execute(
        """
        INSERT INTO videos (title, brief, kind, status, renderer, duration_s,
                            scenes, cost_usd, created_at, updated_at)
        VALUES ($1,$2,'product','pending_review','ffmpeg',28.4,$3,0.0184,
                now() - interval '22 minutes', now() - interval '18 minutes')
        """,
        "Giới thiệu ghế Aurora M1",
        MARK + " Ghế công thái học Aurora M1, lưng lưới thoáng khí, bảo hành 24 tháng.",
        json.dumps([
            {"loi_thoai": "Ngồi tám tiếng mà lưng vẫn không mỏi.",
             "text_man_hinh": "Tám tiếng, không mỏi",
             "duration": 4.6, "timing_source": "ffprobe", "start": 0},
            {"loi_thoai": "Lưng lưới thoáng khí, tựa đầu chỉnh được ba hướng.",
             "text_man_hinh": "Tựa đầu chỉnh 3 hướng",
             "duration": 5.2, "timing_source": "ffprobe", "start": 4.6},
            {"loi_thoai": "Ngả một trăm ba mươi lăm độ, có khoá ở mọi vị trí.",
             "text_man_hinh": "Ngả 135 độ", "nhan_manh": True,
             "duration": 5.9, "timing_source": "ffprobe", "start": 9.8},
            {"loi_thoai": "Aurora M1, bốn triệu hai chín, bảo hành hai năm.",
             "text_man_hinh": "4.290.000đ", "nhan_manh": True,
             "duration": 6.1, "timing_source": "ffprobe", "start": 15.7},
            {"loi_thoai": "Nhắn tin ngay để giữ hàng hôm nay.",
             "text_man_hinh": "Nhắn để giữ hàng",
             "duration": 6.6, "timing_source": "ffprobe", "start": 21.8},
        ], ensure_ascii=False),
    )

    exists = await db.fetchrow("SELECT id FROM documents WHERE source = 'demo'")
    if not exists:
        doc = await db.fetchrow(
            "INSERT INTO documents (title, source, chunk_count) "
            "VALUES ($1,'demo',$2) RETURNING id",
            "Chính sách bảo hành Aurora", 1,
        )
        await db.execute(
            "INSERT INTO chunks (document_id, ord, content) VALUES ($1,0,$2)",
            doc["id"], DOC,
        )

    await db.log_event("demo.seed", actor="script", conversations=len(SCRIPTS))
    print(f"Đã nạp {len(SCRIPTS)} hội thoại, 1 video, 1 tài liệu.")
    print("Mở http://localhost:8000 để xem.")
    print("\nLưu ý: tài liệu mẫu chưa có embedding (cần Vertex). Nạp thật bằng:")
    print("  python -m scripts.ingest data/knowledge")


async def main() -> None:
    await db.init_db()
    try:
        if "--clear" in sys.argv:
            await clear()
        else:
            await seed()
    finally:
        await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())
