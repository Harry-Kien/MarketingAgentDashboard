"""
Dây chuyền sản xuất video.

Thứ tự KHÔNG được đảo:
    (ảnh -> NHÌN ẢNH) -> kịch bản -> giọng đọc -> ĐO thời lượng -> dựng hình

Hai bước viết hoa là hai chỗ hệ thống ĐO THỰC TẾ thay vì tin model đoán.
Đo thời lượng trước khi dựng tách video khớp lời khỏi video lệch lời — để
model tự gán "cảnh này 5 giây" thì hình chuyển trước khi nói xong. Nhìn ảnh
trước khi dựng tách video có bố cục khỏi video đè chữ lên mặt sản phẩm.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from agent import db
from agent.config import ROOT, settings
from agent.core import llm
from agent.video import assets, catalog_images, renderers, timing, tts, vision

PROMPT = (ROOT / "agent" / "prompts" / "video_script.md").read_text(encoding="utf-8")

async def write_script(
    brief: str, seconds: int = 30, catalogue: str = ""
) -> tuple[dict | None, float]:
    """Bước 1 — model viết kịch bản chia cảnh."""
    ask = (
        f"Yêu cầu: {brief}\n"
        f"Thời lượng mục tiêu: khoảng {seconds} giây.\n"
    )
    if catalogue:
        # Danh mục ảnh nằm ở tin nhắn user chứ không nhét vào system prompt:
        # nó đổi theo từng video, để trong khối ổn định là phá điểm cache.
        ask += (
            "\nẢnh sản phẩm có sẵn, chọn bằng `anh_index`:\n"
            f"{catalogue}\n"
        )
    ask += "\nTrả về JSON đúng định dạng đã quy định."

    result = await llm.complete(
        system=llm.cached_system(PROMPT),
        messages=[{"role": "user", "content": ask}],
        model=settings.model_chat,
        max_tokens=2000,
        effort="medium",
    )
    kich_ban = llm.parse_json(result.text)
    if kich_ban is None:
        # Không nuốt nguyên nhân. "Không dựng được kịch bản hợp lệ" không nói
        # được gì cho ai: model trả rỗng vì chạm hạn mức, bị cắt vì hết token,
        # hay trả văn xuôi thay vì JSON — ba chuyện khác nhau, ba cách sửa
        # khác nhau. Kèm luôn phần đầu câu trả lời để còn truy được.
        raise ValueError(
            f"model không trả JSON hợp lệ "
            f"(stop={result.stop_reason or 'không rõ'}, "
            f"{result.tokens_out} token ra): {result.text[:200] or '(rỗng)'}"
        )
    return kich_ban, result.cost_usd


def bind_scenes_to_assets(scenes: list[dict], asset_rows: list[dict]) -> None:
    """
    Gán ảnh cho từng cảnh, tại chỗ. KHÔNG tin `anh_index` model trả về.

    Model có thể trả chỉ số ngoài phạm vi, trả chuỗi thay vì số, hoặc trỏ vào
    ảnh đã bị loại vì mờ. Cả ba trường hợp đều được sửa lặng lẽ ở đây thay vì
    làm hỏng cả video — nhưng ảnh xấu thì không bao giờ được chọn thay ảnh tốt.
    """
    if not asset_rows:
        return

    good = [r["ord"] for r in asset_rows if r.get("usable")] or [
        r["ord"] for r in asset_rows
    ]
    valid = {r["ord"] for r in asset_rows}

    for i, scene in enumerate(scenes):
        idx = scene.get("anh_index")
        if isinstance(idx, str) and idx.strip().lstrip("-").isdigit():
            idx = int(idx)
        if not isinstance(idx, int) or idx not in valid:
            idx = good[i % len(good)]
        elif idx not in good:
            idx = good[i % len(good)]      # model trỏ vào ảnh đã bị loại
        scene["anh_index"] = idx


async def voice_scenes(scenes: list[dict], audio_dir: Path) -> list[Path | None]:
    """Bước 2 — đọc từng cảnh thành file wav (song song)."""
    audio_dir.mkdir(parents=True, exist_ok=True)

    async def one(i: int, scene: dict) -> Path | None:
        line = str(scene.get("loi_thoai", "")).strip()
        if not line:
            return None
        return await tts.synthesize(line, audio_dir / f"scene_{i:02d}.wav")

    return list(
        await asyncio.gather(*(one(i, s) for i, s in enumerate(scenes)))
    )


async def produce(video_id: str) -> None:
    """Chạy trọn dây chuyền cho một bản ghi video. Gọi ở background task."""
    row = await db.fetchrow("SELECT * FROM videos WHERE id = $1", uuid.UUID(video_id))
    if row is None:
        return

    async def mark(status: str, **fields) -> None:
        sets = ["status = $2", "updated_at = now()"]
        args: list = [uuid.UUID(video_id), status]
        for i, (k, v) in enumerate(fields.items(), start=3):
            sets.append(f"{k} = ${i}")
            args.append(v)
        await db.execute(
            f"UPDATE videos SET {', '.join(sets)} WHERE id = $1", *args
        )

    try:
        # --- 0. Nhìn ảnh (chỉ khi có ảnh) ---
        asset_rows = await db.fetch(
            "SELECT ord, file_path, width, height, analysis, usable "
            "FROM video_assets WHERE video_id = $1 ORDER BY ord",
            uuid.UUID(video_id),
        )
        vision_cost = 0.0
        if asset_rows:
            await mark("looking")
            asset_rows, vision_cost = await vision.analyse_all(asset_rows)
            for r in asset_rows:
                await db.execute(
                    "UPDATE video_assets SET analysis = $3, usable = $4 "
                    "WHERE video_id = $1 AND ord = $2",
                    uuid.UUID(video_id), r["ord"], r["analysis"], r["usable"],
                )

        # --- 1. Kịch bản ---
        await mark("scripting")
        script, cost = await write_script(
            row["brief"], seconds=30, catalogue=vision.catalogue(asset_rows)
        )
        cost += vision_cost
        if not script or not script.get("canh"):
            await mark("failed", error="Kịch bản trả về không có cảnh nào")
            return
        scenes = script["canh"]
        title = script.get("tieu_de") or row["title"]
        bind_scenes_to_assets(scenes, asset_rows)

        # --- 2. Giọng đọc ---
        await mark("voicing", cost_usd=cost)
        audio_dir = settings.video_out_path / video_id / "audio"
        audio_paths = await voice_scenes(scenes, audio_dir)

        # --- 3. Đo thời lượng THẬT (ffprobe) ---
        total = await timing.measure_scenes(scenes, audio_paths)

        # --- 4. Dựng hình ---
        await mark(
            "rendering",
            scenes=scenes,   # codec JSONB tu ma hoa
            duration_s=total,
        )
        out_path = settings.video_out_path / video_id / "video.mp4"
        result = await renderers.render(
            renderers.RenderContext(
                title=title,
                scenes=scenes,
                audio_dir=audio_dir,
                out_path=out_path,
                assets=asset_rows,
            )
        )
        ok, backend, detail = result.ok, result.backend, result.detail

        if not ok:
            await mark("failed", error=detail[:900], renderer=backend)
            await db.log_event("video.failed", ref_id=uuid.UUID(video_id), detail=detail[:300])
            return

        # Chờ người duyệt — không bao giờ tự đăng ra kênh công khai.
        await mark(
            "pending_review",
            file_path=str(out_path),
            renderer=backend,
            duration_s=total,
            scenes=scenes,   # codec JSONB tu ma hoa
            error=None,
        )
        await db.log_event(
            "video.ready",
            ref_id=uuid.UUID(video_id),
            backend=backend,
            duration_s=total,
            note=detail,
        )
    except Exception as exc:  # noqa: BLE001 — job nền, không được để sập app
        await mark("failed", error=f"{type(exc).__name__}: {exc}"[:900])


async def request_video(
    *,
    title: str,
    brief: str,
    kind: str = "explainer",
    conversation_id=None,
    images: list | None = None,
    ma_san_pham: str | None = None,
) -> str:
    """Tạo bản ghi và khởi động dây chuyền ở nền. Trả về video id."""
    # Hội thoại có thể đã bị xoá giữa chừng — khoá ngoại sẽ nổ và làm hỏng cả
    # lượt trả lời. Kiểm tra trước, không có thì vẫn tạo video nhưng bỏ liên kết.
    if conversation_id is not None:
        exists = await db.fetchrow(
            "SELECT 1 FROM conversations WHERE id = $1", conversation_id
        )
        if not exists:
            conversation_id = None

    row = await db.fetchrow(
        "INSERT INTO videos (conversation_id, title, brief, kind, status) "
        "VALUES ($1,$2,$3,$4,'queued') RETURNING id",
        conversation_id,
        title[:200],
        brief,
        kind,
    )
    vid = str(row["id"])

    # Ảnh phải nằm trên đĩa và trong DB TRƯỚC khi job nền chạy, vì bước đầu
    # của dây chuyền là đọc chúng ra để nhìn.
    # Không ai tải ảnh lên nhưng biết mã sản phẩm thì lấy từ kho ảnh. Đây là
    # mắt xích khiến agent tự dựng được video: khách nhắn "làm video giới
    # thiệu serum phục hồi", agent gọi tool kèm mã, dây chuyền tự có ảnh.
    if not images and ma_san_pham:
        for a in catalog_images.asset_rows_cho(ma_san_pham):
            await db.execute(
                "INSERT INTO video_assets (video_id, ord, file_path, width, height) "
                "VALUES ($1,$2,$3,$4,$5) ON CONFLICT (video_id, ord) DO NOTHING",
                uuid.UUID(vid), a["ord"], a["file_path"], a["width"], a["height"],
            )

    if images:
        saved, warnings = await assets.save_uploads(
            settings.video_out_path / vid / "assets", images
        )
        for a in saved:
            await db.execute(
                "INSERT INTO video_assets (video_id, ord, file_path, width, height) "
                "VALUES ($1,$2,$3,$4,$5) ON CONFLICT (video_id, ord) DO NOTHING",
                uuid.UUID(vid), a["ord"], a["file_path"], a["width"], a["height"],
            )
        if warnings:
            await db.log_event(
                "video.assets", ref_id=uuid.UUID(vid),
                nhan=len(saved), loai=warnings[:5],
            )

    # KHÔNG chạy ngay tại đây. Video nằm lại hàng đợi trong Postgres, thợ
    # nền (agent/video/worker.py) nhận và dựng. Nhờ vậy app tắt giữa chừng
    # thì việc được nhặt lại ở lần khởi động sau, và nhiều yêu cầu cùng lúc
    # không sinh ra bấy nhiêu tiến trình ffmpeg tranh CPU với việc trả lời
    # khách đang đợi trước mặt.
    return vid
