"""API cho dashboard. Chỉ đọc/ghi Postgres và gọi adapter kênh."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import db, runtime
from agent.channels.zalocrm import ZaloCRMAdapter
from agent.core import rag
from agent.video import pipeline

router = APIRouter(prefix="/api")
_channel = ZaloCRMAdapter()


def _num(v) -> float:
    return float(v or 0)


# ---------------------------------------------------------------
#  Tổng quan ca trực
# ---------------------------------------------------------------

@router.get("/overview")
async def overview() -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    conv = await db.fetchrow(
        """
        SELECT count(*)                                              AS total,
               count(*) FILTER (WHERE status = 'auto')               AS handled,
               count(*) FILTER (WHERE status = 'escalated')          AS escalated,
               count(*) FILTER (WHERE status = 'assist')             AS waiting,
               coalesce(sum(cost_usd), 0)                            AS cost
        FROM conversations WHERE updated_at >= $1
        """,
        since,
    ) or {}

    msg = await db.fetchrow(
        """
        SELECT count(*)                                           AS replies,
               count(*) FILTER (WHERE grounded IS TRUE)            AS grounded,
               coalesce(avg(latency_ms), 0)                        AS latency,
               coalesce(sum(tokens_in), 0)                         AS tin,
               coalesce(sum(tokens_out), 0)                        AS tout,
               coalesce(sum(cache_read), 0)                        AS cached
        FROM messages WHERE role = 'agent' AND created_at >= $1
        """,
        since,
    ) or {}

    vid = await db.fetchrow(
        """
        SELECT count(*)                                              AS total,
               count(*) FILTER (WHERE status = 'pending_review')      AS review,
               count(*) FILTER (WHERE status = 'failed')              AS failed,
               coalesce(sum(cost_usd), 0)                             AS cost,
               coalesce(sum(duration_s), 0)                           AS seconds
        FROM videos WHERE created_at >= $1
        """,
        since,
    ) or {}

    # Băng ca trực — signature của dashboard.
    tape = await db.fetch(
        """
        SELECT id, status, outcome, customer_name, updated_at, cost_usd, msg_count
        FROM conversations
        ORDER BY updated_at DESC
        LIMIT 72
        """
    )

    total = int(conv.get("total") or 0)
    handled = int(conv.get("handled") or 0)
    replies = int(msg.get("replies") or 0)
    grounded = int(msg.get("grounded") or 0)

    return {
        "conversations": {
            "total": total,
            "handled": handled,
            "escalated": int(conv.get("escalated") or 0),
            "waiting": int(conv.get("waiting") or 0),
            "containment": round(handled / total, 4) if total else None,
        },
        "quality": {
            "replies": replies,
            "grounding": round(grounded / replies, 4) if replies else None,
            "latency_ms": int(_num(msg.get("latency"))),
        },
        "cost": {
            "total_usd": round(_num(conv.get("cost")) + _num(vid.get("cost")), 6),
            "chat_usd": round(_num(conv.get("cost")), 6),
            "video_usd": round(_num(vid.get("cost")), 6),
            "per_conversation": round(_num(conv.get("cost")) / total, 6) if total else None,
            "tokens_in": int(msg.get("tin") or 0),
            "tokens_out": int(msg.get("tout") or 0),
            "cache_read": int(msg.get("cached") or 0),
        },
        "video": {
            "total": int(vid.get("total") or 0),
            "review": int(vid.get("review") or 0),
            "failed": int(vid.get("failed") or 0),
            "seconds": round(_num(vid.get("seconds")), 1),
        },
        "runtime": dict(runtime.STATE),
        "tape": [
            {
                "id": str(t["id"]),
                "status": t["status"],
                "outcome": t["outcome"],
                "customer": t["customer_name"],
                "at": t["updated_at"].isoformat(),
                "cost": round(_num(t["cost_usd"]), 6),
                "messages": t["msg_count"],
            }
            for t in reversed(tape)
        ],
    }


# ---------------------------------------------------------------
#  Hội thoại
# ---------------------------------------------------------------

@router.get("/conversations")
async def list_conversations(status: str | None = None, limit: int = 60) -> list[dict]:
    sql = """
        SELECT c.*,
               (SELECT content FROM messages m WHERE m.conversation_id = c.id
                ORDER BY created_at DESC LIMIT 1) AS last_message
        FROM conversations c
    """
    args: list = []
    if status and status != "all":
        sql += " WHERE c.status = $1"
        args.append(status)
    sql += f" ORDER BY c.updated_at DESC LIMIT {int(limit)}"

    rows = await db.fetch(sql, *args)
    return [
        {
            "id": str(r["id"]),
            "channel": r["channel"],
            "customer": r["customer_name"],
            "status": r["status"],
            "outcome": r["outcome"],
            "cost": round(_num(r["cost_usd"]), 6),
            "messages": r["msg_count"],
            "updated_at": r["updated_at"].isoformat(),
            "last_message": r["last_message"],
            "typing": runtime.is_busy(r["id"]),
        }
        for r in rows
    ]


@router.get("/conversations/{conv_id}")
async def conversation_detail(conv_id: str) -> dict:
    cid = uuid.UUID(conv_id)
    conv = await db.fetchrow("SELECT * FROM conversations WHERE id = $1", cid)
    if not conv:
        raise HTTPException(404, "Không thấy hội thoại")

    msgs = await db.fetch(
        "SELECT * FROM messages WHERE conversation_id = $1 ORDER BY created_at", cid
    )
    return {
        "id": str(conv["id"]),
        "customer": conv["customer_name"],
        "channel": conv["channel"],
        "external_id": conv["external_id"],
        "status": conv["status"],
        "typing": runtime.is_busy(conv["id"]),
        "cost": round(_num(conv["cost_usd"]), 6),
        "messages": [
            {
                "id": str(m["id"]),
                "role": m["role"],
                "content": m["content"],
                "delivered": m["delivered"],
                "grounded": m["grounded"],
                "confidence": m["confidence"],
                "sources": m["sources"],
                "cost": round(_num(m["cost_usd"]), 6),
                "latency_ms": m["latency_ms"],
                "at": m["created_at"].isoformat(),
            }
            for m in msgs
        ],
    }


class SendBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/conversations/{conv_id}/send")
async def staff_send(conv_id: str, body: SendBody) -> dict:
    """Nhân viên gửi tin trực tiếp (hoặc gửi bản đã sửa của agent)."""
    cid = uuid.UUID(conv_id)
    conv = await db.fetchrow("SELECT * FROM conversations WHERE id = $1", cid)
    if not conv:
        raise HTTPException(404, "Không thấy hội thoại")

    delivery = await _channel.send_text(conv["external_id"], body.text)
    await db.execute(
        "INSERT INTO messages (conversation_id, role, content, delivered) "
        "VALUES ($1,'staff',$2,$3)",
        cid,
        body.text,
        delivery.ok,
    )
    await db.execute(
        "UPDATE conversations SET msg_count = msg_count + 1, updated_at = now() "
        "WHERE id = $1",
        cid,
    )
    await db.log_event("staff.send", actor="staff", ref_id=cid, ok=delivery.ok)
    return {"ok": delivery.ok, "detail": delivery.detail}


@router.post("/messages/{message_id}/approve")
async def approve_draft(message_id: str) -> dict:
    """Chế độ assist: người duyệt bản nháp của agent rồi mới gửi đi."""
    mid = uuid.UUID(message_id)
    msg = await db.fetchrow("SELECT * FROM messages WHERE id = $1", mid)
    if not msg:
        raise HTTPException(404, "Không thấy tin nhắn")
    if msg["delivered"]:
        return {"ok": True, "detail": "đã gửi trước đó"}

    conv = await db.fetchrow(
        "SELECT * FROM conversations WHERE id = $1", msg["conversation_id"]
    )
    delivery = await _channel.send_text(conv["external_id"], msg["content"])
    if delivery.ok:
        await db.execute("UPDATE messages SET delivered = TRUE WHERE id = $1", mid)
        await db.execute(
            "UPDATE conversations SET status = 'auto', updated_at = now() WHERE id = $1",
            conv["id"],
        )
    await db.log_event("draft.approve", actor="staff", ref_id=mid, ok=delivery.ok)
    return {"ok": delivery.ok, "detail": delivery.detail}


@router.post("/conversations/{conv_id}/takeover")
async def takeover(conv_id: str) -> dict:
    """Người giành lại quyền. Agent ngừng trả lời hội thoại này."""
    cid = uuid.UUID(conv_id)
    await db.execute(
        "UPDATE conversations SET status = 'escalated', outcome = 'escalated', "
        "updated_at = now() WHERE id = $1",
        cid,
    )
    await db.log_event("conversation.takeover", actor="staff", ref_id=cid)
    return {"ok": True}


@router.post("/conversations/{conv_id}/release")
async def release(conv_id: str) -> dict:
    """Trả hội thoại lại cho agent."""
    cid = uuid.UUID(conv_id)
    await db.execute(
        "UPDATE conversations SET status = 'auto', outcome = NULL, "
        "updated_at = now() WHERE id = $1",
        cid,
    )
    await db.log_event("conversation.release", actor="staff", ref_id=cid)
    return {"ok": True}


# ---------------------------------------------------------------
#  Video
# ---------------------------------------------------------------

@router.get("/videos")
async def list_videos(limit: int = 40) -> list[dict]:
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


@router.post("/videos")
async def create_video(body: VideoBody) -> dict:
    vid = await pipeline.request_video(
        title=body.title, brief=body.brief, kind=body.kind
    )
    return {"id": vid}


@router.post("/videos/upload")
async def create_video_with_images(
    title: str = Form(...),
    brief: str = Form(...),
    kind: str = Form("product"),
    images: list[UploadFile] = File(default=[]),
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
async def list_video_assets(video_id: str) -> list[dict]:
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
async def video_asset_file(video_id: str, ord: int):
    row = await db.fetchrow(
        "SELECT file_path FROM video_assets WHERE video_id = $1 AND ord = $2",
        uuid.UUID(video_id),
        ord,
    )
    if not row or not Path(row["file_path"]).exists():
        raise HTTPException(404, "Không có ảnh")
    return FileResponse(row["file_path"], media_type="image/jpeg")


@router.get("/videos/{video_id}/file")
async def video_file(video_id: str):
    row = await db.fetchrow(
        "SELECT file_path, title FROM videos WHERE id = $1", uuid.UUID(video_id)
    )
    if not row or not row["file_path"] or not Path(row["file_path"]).exists():
        raise HTTPException(404, "Chưa có file")
    return FileResponse(row["file_path"], media_type="video/mp4")


@router.post("/videos/{video_id}/approve")
async def approve_video(video_id: str) -> dict:
    vid = uuid.UUID(video_id)
    await db.execute(
        "UPDATE videos SET status = 'ready', updated_at = now() WHERE id = $1", vid
    )
    await db.log_event("video.approve", actor="staff", ref_id=vid)
    return {"ok": True}


# ---------------------------------------------------------------
#  Cơ sở tri thức
# ---------------------------------------------------------------

@router.get("/knowledge")
async def list_documents() -> list[dict]:
    rows = await db.fetch(
        "SELECT id, title, source, chunk_count, created_at "
        "FROM documents ORDER BY created_at DESC"
    )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "source": r["source"],
            "chunks": r["chunk_count"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


class DocBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=20)


@router.post("/knowledge")
async def add_document(body: DocBody) -> dict:
    n = await rag.ingest(body.title, "dashboard", body.text)
    return {"ok": True, "chunks": n}


@router.delete("/knowledge/{doc_id}")
async def delete_document(doc_id: str) -> dict:
    await db.execute("DELETE FROM documents WHERE id = $1", uuid.UUID(doc_id))
    return {"ok": True}


class ProbeBody(BaseModel):
    question: str = Field(min_length=2)


@router.post("/knowledge/probe")
async def probe(body: ProbeBody) -> dict:
    """Thử truy vấn RAG mà không tốn một lượt gọi model."""
    hits = await rag.retrieve(body.question, k=5)
    return {
        "hits": [
            {"doc": h.doc_title, "score": round(h.score, 4), "excerpt": h.content[:280]}
            for h in hits
        ]
    }


# ---------------------------------------------------------------
#  Vận hành
# ---------------------------------------------------------------

class RuntimeBody(BaseModel):
    enabled: bool | None = None
    mode: str | None = None
    confidence_floor: float | None = None
    max_cost_per_conversation: float | None = None


@router.post("/runtime")
async def set_runtime(body: RuntimeBody) -> dict:
    state = runtime.update(**body.model_dump(exclude_none=True))
    await db.log_event("runtime.update", actor="staff", **{k: str(v) for k, v in state.items()})
    return state


@router.get("/events")
async def recent_events(limit: int = 50) -> list[dict]:
    rows = await db.fetch(
        f"SELECT kind, actor, ref_id, detail, created_at FROM events "
        f"ORDER BY created_at DESC LIMIT {int(limit)}"
    )
    return [
        {
            "kind": r["kind"],
            "actor": r["actor"],
            "ref_id": str(r["ref_id"]) if r["ref_id"] else None,
            "detail": r["detail"],
            "at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


# ---------------------------------------------------------------
#  Đơn hàng
# ---------------------------------------------------------------

@router.get("/orders")
async def list_orders(status: str | None = None, limit: int = 60) -> list[dict]:
    sql = "SELECT * FROM orders"
    args: list = []
    if status and status != "all":
        sql += " WHERE trang_thai = $1"
        args.append(status)
    sql += f" ORDER BY created_at DESC LIMIT {int(limit)}"
    rows = await db.fetch(sql, *args)
    return [
        {
            "id": str(r["id"]),
            "ma_don": r["ma_don"],
            "khach_ten": r["khach_ten"],
            "khach_sdt": r["khach_sdt"],
            "khach_dia_chi": r["khach_dia_chi"],
            "items": r["items"],
            "tong_tien": int(r["tong_tien"]),
            "trang_thai": r["trang_thai"],
            "channel": r["channel"],
            "ghi_chu": r["ghi_chu"],
            "conversation_id": str(r["conversation_id"]) if r["conversation_id"] else None,
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


@router.post("/orders/{order_id}/approve")
async def approve_order(order_id: str) -> dict:
    oid = uuid.UUID(order_id)
    await db.execute(
        "UPDATE orders SET trang_thai='da_chot', updated_at=now() WHERE id=$1", oid
    )
    await db.log_event("order.approve", actor="staff", ref_id=oid)
    return {"ok": True}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str) -> dict:
    oid = uuid.UUID(order_id)
    await db.execute(
        "UPDATE orders SET trang_thai='da_huy', updated_at=now() WHERE id=$1", oid
    )
    await db.log_event("order.cancel", actor="staff", ref_id=oid)
    return {"ok": True}
