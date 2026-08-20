"""
Hàng đợi dựng video, lưu trong Postgres.

VÌ SAO CẦN
----------
Trước đây `request_video` gọi thẳng `asyncio.create_task(produce(...))`. Hai
hậu quả, cả hai đều đã xảy ra thật trên máy này:

  1. App tắt hoặc khởi động lại giữa chừng thì video chết cứng ở trạng thái
     dở dang. Không ai nhặt lại, không dòng lỗi nào, thẻ video quay mãi.
     Trong DB còn bản ghi `0c2c9f09` chết đúng kiểu đó.
  2. Nhiều yêu cầu cùng lúc thì bấy nhiêu tiến trình ffmpeg cùng chạy, ăn
     hết CPU của chính tiến trình đang trả lời khách. Video là việc nền,
     không được phép làm chậm việc trước mặt khách.

CÁCH LÀM
--------
Trạng thái công việc nằm trong Postgres chứ không trong bộ nhớ tiến trình.
App khởi động thì NHẶT LẠI những việc dở dang rồi chạy tiếp. Chỉ một video
được dựng tại một thời điểm (đổi bằng VIDEO_WORKERS).

Việc nhận được làm bằng một câu UPDATE nguyên tử có `FOR UPDATE SKIP LOCKED`,
nên chạy hai app cùng lúc trên cùng DB cũng không ai giẫm chân ai.
"""
from __future__ import annotations

import asyncio

from agent import db
from agent.config import settings
from agent.video import pipeline

# Những trạng thái nghĩa là "đang có người làm". Còn kẹt ở đây sau khi app
# khởi động lại tức là tiến trình cũ đã chết giữa chừng.
IN_FLIGHT = ("claimed", "looking", "scripting", "voicing", "rendering")

POLL_SECONDS = 3.0


async def reclaim_stale() -> int:
    """
    Trả những việc dở dang về hàng đợi. Gọi một lần lúc app khởi động.

    An toàn vì mọi bước trong `produce()` đều làm lại được từ đầu: kịch bản
    viết lại, giọng đọc thu lại, hình dựng lại. Ảnh sản phẩm thì vẫn nằm
    nguyên trên đĩa và trong `video_assets`, không phải tải lên lần nữa.
    """
    rows = await db.fetch(
        "UPDATE videos SET status = 'queued', updated_at = now() "
        "WHERE status = ANY($1::text[]) RETURNING id",
        list(IN_FLIGHT),
    )
    if rows:
        await db.log_event(
            "video.reclaim", so_viec=len(rows),
            ghi_chu="app khoi dong lai, nhat lai viec dang do",
        )
    return len(rows)


async def claim_one() -> str | None:
    """
    Nhận MỘT việc từ hàng đợi, nguyên tử.

    `FOR UPDATE SKIP LOCKED` là mấu chốt: hai tiến trình cùng hỏi thì mỗi
    bên nhận một việc khác nhau thay vì cùng giành một việc.
    """
    row = await db.fetchrow(
        """
        UPDATE videos SET status = 'claimed', updated_at = now()
        WHERE id = (
            SELECT id FROM videos
            WHERE status = 'queued'
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id
        """
    )
    return str(row["id"]) if row else None


async def worker_loop(slot: int = 0) -> None:
    """Một tay thợ: nhận việc, dựng, lặp lại. Không bao giờ được chết."""
    while True:
        try:
            video_id = await claim_one()
            if video_id is None:
                await asyncio.sleep(POLL_SECONDS)
                continue

            await db.log_event("video.start", ref_id=video_id, slot=slot)
            await pipeline.produce(video_id)

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — vòng lặp nền không được chết
            await db.log_event(
                "video.worker_error", error=f"{type(exc).__name__}: {exc}"[:200]
            )
            await asyncio.sleep(POLL_SECONDS)


async def start() -> list[asyncio.Task]:
    """Nhặt lại việc dở rồi bật thợ. Trả danh sách task để lifespan tắt sau."""
    await reclaim_stale()
    so_tho = max(1, int(getattr(settings, "video_workers", 1)))
    return [asyncio.create_task(worker_loop(i)) for i in range(so_tho)]
