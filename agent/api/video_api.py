"""
API video: tạo, tải lên, duyệt, tải tệp.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import db
from agent.video import pipeline

from .phu_thuoc import (
    _num,
    can_quyen,
)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------
#  Video
# ---------------------------------------------------------------

@router.get("/videos")
async def list_videos(limit: int = 40, _quyen: dict = Depends(can_quyen("noi_dung.doc"))) -> list[dict]:
    rows = await db.fetch(
        f"SELECT * FROM videos ORDER BY created_at DESC LIMIT {int(limit)}"
    )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "brief": r["brief"],
            "kind": r["kind"],
            "status": r["status"],
            "renderer": r["renderer"],
            "duration_s": r["duration_s"],
            "scenes": r["scenes"],
            "cost": round(_num(r["cost_usd"]), 6),
            "error": r["error"],
            "has_file": bool(r["file_path"] and Path(r["file_path"]).exists()),
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


class VideoBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    brief: str = Field(min_length=10, max_length=4000)
    kind: str = "explainer"
    # Có mã thì lấy ảnh trong kho sản phẩm. Thiếu trường này thì người dùng
    # dashboard chỉ dựng được video thẻ chữ, dù kho có sẵn ảnh cho đúng sản
    # phẩm đó — agent thì lấy được, người thì không. Một hệ thống mà công cụ
    # nội bộ mạnh hơn giao diện cho người dùng là hệ thống thiết kế hỏng.
    ma_san_pham: str = ""


@router.post("/videos")
async def create_video(body: VideoBody, _quyen: dict = Depends(can_quyen("noi_dung.doc"))) -> dict:
    from agent.video import catalog_images

    ma = body.ma_san_pham.strip().upper()
    vid = await pipeline.request_video(
        title=body.title, brief=body.brief, kind=body.kind,
        ma_san_pham=ma or None,
    )
    return {"id": vid, "so_anh_kho": len(catalog_images.anh_cua(ma)) if ma else 0}


@router.post("/videos/upload")
async def create_video_with_images(
    title: str = Form(...),
    brief: str = Form(...),
    kind: str = Form("product"),
    images: list[UploadFile] = File(default=[]),
    _quyen: dict = Depends(can_quyen("noi_dung.doc")),
) -> dict:
    """
    Đặt video KÈM ẢNH SẢN PHẨM.

    Tách khỏi `POST /videos` (dạng JSON) có chủ ý: endpoint cũ vẫn phục vụ
    tool của agent và mọi mã gọi sẵn có, không phải sửa gì. Ai cần ảnh thì
    gọi endpoint này.

    Ảnh được kiểm và chuẩn hoá trong `agent/video/assets.py` — sai định dạng
    hay quá nặng thì bị loại lặng lẽ, phần còn lại vẫn chạy.
    """
    if not title.strip() or len(brief.strip()) < 10:
        raise HTTPException(422, "Thiếu tiêu đề hoặc mô tả quá ngắn")

    payload: list[tuple[str, bytes]] = []
    for f in images or []:
        raw = await f.read()
        if raw:
            payload.append((f.filename or "anh.jpg", raw))

    vid = await pipeline.request_video(
        title=title.strip(), brief=brief.strip(), kind=kind, images=payload
    )
    return {"id": vid, "so_anh_nhan": len(payload)}


@router.get("/videos/{video_id}/assets")
async def list_video_assets(video_id: str, _quyen: dict = Depends(can_quyen("noi_dung.doc"))) -> list[dict]:
    """Ảnh của một video kèm kết quả bước nhìn ảnh — để soi khi video xấu."""
    rows = await db.fetch(
        "SELECT ord, file_path, width, height, analysis, usable "
        "FROM video_assets WHERE video_id = $1 ORDER BY ord",
        uuid.UUID(video_id),
    )
    return [
        {
            "ord": r["ord"],
            "width": r["width"],
            "height": r["height"],
            "analysis": r["analysis"],
            "usable": r["usable"],
            "co_file": bool(r["file_path"] and Path(r["file_path"]).exists()),
        }
        for r in rows
    ]


@router.get("/videos/{video_id}/assets/{ord}/file")
async def video_asset_file(video_id: str, ord: int, _quyen: dict = Depends(can_quyen("noi_dung.doc"))):
    row = await db.fetchrow(
        "SELECT file_path FROM video_assets WHERE video_id = $1 AND ord = $2",
        uuid.UUID(video_id),
        ord,
    )
    if not row or not Path(row["file_path"]).exists():
        raise HTTPException(404, "Không có ảnh")
    return FileResponse(row["file_path"], media_type="image/jpeg")


@router.get("/videos/{video_id}/file")
async def video_file(video_id: str, _quyen: dict = Depends(can_quyen("noi_dung.doc"))):
    row = await db.fetchrow(
        "SELECT file_path, title FROM videos WHERE id = $1", uuid.UUID(video_id)
    )
    if not row or not row["file_path"] or not Path(row["file_path"]).exists():
        raise HTTPException(404, "Chưa có file")
    return FileResponse(row["file_path"], media_type="video/mp4")


@router.post("/videos/{video_id}/retry")
async def retry_video(video_id: str, _quyen: dict = Depends(can_quyen("noi_dung.doc"))) -> dict:
    """
    Đưa một video hỏng trở lại hàng đợi.

    Ảnh sản phẩm vẫn nằm nguyên trên đĩa và trong `video_assets`, nên không
    phải tải lên lại. Mọi bước còn lại đều làm lại được từ đầu.
    """
    vid = uuid.UUID(video_id)
    row = await db.fetchrow(
        "UPDATE videos SET status = 'queued', error = NULL, updated_at = now() "
        "WHERE id = $1 AND status = 'failed' RETURNING id",
        vid,
    )
    if not row:
        raise HTTPException(409, "Chỉ chạy lại được video đang ở trạng thái lỗi")
    await db.log_event("video.retry", actor="staff", ref_id=vid)
    return {"ok": True}


@router.post("/videos/{video_id}/approve")
async def approve_video(video_id: str, _quyen: dict = Depends(can_quyen("noi_dung.duyet"))) -> dict:
    """
    Duyệt video. CHỈ duyệt được khi file thật sự có trên đĩa.

    Trước đây endpoint này đặt thẳng `ready` mà không kiểm gì. Kết quả là
    trong CSDL có video mang trạng thái "đã duyệt" với `file_path = NULL` —
    dashboard hiện là xong, gắn vào bài đăng được, và bộ đăng tay báo "có
    video" rồi nút tải trả 404.

    Hai bản ghi đã ở đúng tình trạng đó khi rà lại.
    """
    vid = uuid.UUID(video_id)
    v = await db.fetchrow("SELECT file_path, status FROM videos WHERE id = $1", vid)
    if v is None:
        raise HTTPException(404, "Không tìm thấy video")

    fp = v["file_path"]
    if not fp or not Path(fp).exists():
        raise HTTPException(
            422,
            "Video chưa có file dựng xong nên không duyệt được. "
            f"Trạng thái hiện tại: {v['status']}.",
        )

    await db.execute(
        "UPDATE videos SET status = 'ready', updated_at = now() WHERE id = $1", vid
    )
    await db.log_event("video.approve", actor="staff", ref_id=vid)
    return {"ok": True}
