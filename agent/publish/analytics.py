"""
Phân tích hiệu quả bài đăng — và trả kết quả đó NGƯỢC LẠI cho agent.

Phần lớn hệ thống "đăng bài tự động" dừng ở chỗ đăng xong. Vòng lặp chỉ
khép kín khi số liệu quay lại ảnh hưởng tới nội dung lần sau. Đó là điểm
khác biệt đáng nói trong khoá luận: agent không chỉ sản xuất, nó còn học
từ kết quả.

Nguồn số liệu, theo thứ tự ưu tiên:
  1. Insights API của nền tảng  (cần quyền -> hiện chưa có)
  2. n8n gọi về /api/posts/{id}/metrics  (chạy được ngay)
  3. Người nhập tay trên dashboard        (luôn dùng được)

Cả ba đều ghi vào post_metrics theo cùng một hình dạng, nên phân tích
không cần biết số liệu tới từ đâu.
"""
from __future__ import annotations

from .. import db


async def ghi_so_lieu(post_id: str, kenh: str, *, luot_xem=0, luot_thich=0,
                      binh_luan=0, chia_se=0, luot_click=0,
                      url: str = "", nguon: str = "thu_cong") -> dict:
    """
    Mỗi lần thu thập ghi một dòng MỚI, không cập nhật đè.

    Giữ lịch sử để vẽ được đường tăng trưởng — biết bài đạt 10k view sau
    1 giờ hay sau 1 tuần là hai câu chuyện hoàn toàn khác nhau.
    """
    row = await db.fetchrow(
        "INSERT INTO post_metrics (post_id, kenh, url, luot_xem, luot_thich, "
        "binh_luan, chia_se, luot_click) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) "
        "RETURNING *",
        post_id, kenh, url, luot_xem, luot_thich, binh_luan, chia_se, luot_click,
    )
    await db.log_event("metric.ingested", actor=nguon, ref_id=post_id, kenh=kenh)
    return row


async def moi_nhat_theo_bai(post_id: str) -> list[dict]:
    """Bản ghi mới nhất của mỗi kênh cho một bài."""
    return await db.fetch(
        "SELECT DISTINCT ON (kenh) * FROM post_metrics WHERE post_id = $1 "
        "ORDER BY kenh, thu_thap_luc DESC",
        post_id,
    )


async def tong_quan(ngay: int = 30) -> dict:
    """Số liệu tổng cho dashboard. Chỉ lấy bản ghi mới nhất mỗi (bài, kênh)."""
    rows = await db.fetch(
        """
        WITH moi_nhat AS (
            SELECT DISTINCT ON (m.post_id, m.kenh) m.*
            FROM post_metrics m
            JOIN posts p ON p.id = m.post_id
            WHERE p.created_at > now() - ($1 || ' days')::interval
            ORDER BY m.post_id, m.kenh, m.thu_thap_luc DESC
        )
        SELECT kenh,
               count(*)              AS so_bai,
               sum(luot_xem)         AS luot_xem,
               sum(luot_thich)       AS luot_thich,
               sum(binh_luan)        AS binh_luan,
               sum(chia_se)          AS chia_se,
               sum(luot_click)       AS luot_click
        FROM moi_nhat GROUP BY kenh ORDER BY luot_xem DESC NULLS LAST
        """,
        str(ngay),
    )
    trang_thai = await db.fetch(
        "SELECT trang_thai, count(*) AS n FROM posts "
        "WHERE created_at > now() - ($1 || ' days')::interval "
        "GROUP BY trang_thai",
        str(ngay),
    )
    # sum() của Postgres trên bigint trả numeric -> asyncpg cho ra Decimal ->
    # JSON hoá thành CHUỖI. Ép về int ngay tại đây, nếu không thì phía
    # dashboard cộng "4950" + "406" ra "4950406" mà không báo lỗi gì.
    for r in rows:
        for k in ("so_bai", "luot_xem", "luot_thich", "binh_luan",
                  "chia_se", "luot_click"):
            r[k] = int(r[k] or 0)

    tong = {
        "luot_xem": sum(r["luot_xem"] for r in rows),
        "luot_thich": sum(r["luot_thich"] for r in rows),
        "binh_luan": sum(r["binh_luan"] for r in rows),
        "chia_se": sum(r["chia_se"] for r in rows),
        "luot_click": sum(r["luot_click"] for r in rows),
    }
    # Tương tác trên lượt xem — chỉ số này so sánh được giữa các bài có
    # lượt xem chênh nhau hàng chục lần, còn số tuyệt đối thì không.
    tuong_tac = tong["luot_thich"] + tong["binh_luan"] + tong["chia_se"]
    tong["ty_le_tuong_tac"] = (
        round(tuong_tac / tong["luot_xem"] * 100, 2) if tong["luot_xem"] else 0.0
    )
    return {
        "ngay": ngay,
        "theo_kenh": rows,
        "theo_trang_thai": {r["trang_thai"]: r["n"] for r in trang_thai},
        "tong": tong,
    }


async def bai_tot_nhat(n: int = 5) -> list[dict]:
    rows = await db.fetch(
        """
        WITH moi_nhat AS (
            SELECT DISTINCT ON (post_id, kenh) *
            FROM post_metrics ORDER BY post_id, kenh, thu_thap_luc DESC
        )
        SELECT p.id, p.tieu_de, m.kenh, m.url, m.luot_xem, m.luot_thich,
               m.binh_luan, m.chia_se,
               CASE WHEN m.luot_xem > 0
                    THEN round((m.luot_thich + m.binh_luan + m.chia_se)
                               * 100.0 / m.luot_xem, 2)
                    ELSE 0 END AS ty_le_tuong_tac
        FROM moi_nhat m JOIN posts p ON p.id = m.post_id
        ORDER BY m.luot_xem DESC NULLS LAST LIMIT $1
        """,
        n,
    )
    for r in rows:
        r["ty_le_tuong_tac"] = float(r["ty_le_tuong_tac"] or 0)
    return rows


async def goi_y_cho_agent(n: int = 3) -> str:
    """
    Biến số liệu thành vài dòng chữ nhét được vào prompt soạn bài.

    Trả rỗng khi chưa đủ dữ liệu — thà không gợi ý còn hơn gợi ý dựa trên
    hai bài đăng, vì đó là nhiễu chứ không phải xu hướng.
    """
    top = await bai_tot_nhat(n)
    co_so_lieu = [t for t in top if (t["luot_xem"] or 0) > 0]
    if len(co_so_lieu) < 2:
        return ""
    dong = [
        f"- \"{t['tieu_de']}\" ({t['kenh']}): {t['luot_xem']:,} lượt xem, "
        f"tương tác {t['ty_le_tuong_tac']}%"
        for t in co_so_lieu
    ]
    return (
        "Các bài chạy tốt nhất gần đây, tham khảo giọng điệu và cách mở đầu:\n"
        + "\n".join(dong)
    )
