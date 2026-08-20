"""API cho dashboard. Chỉ đọc/ghi Postgres và gọi adapter kênh."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import db, runtime
from agent.channels import registry as channels
from agent.config import settings
from agent.channels import zalocrm_accounts as zalo_acc
from agent.core import rag
from agent.publish import analytics, chien_dich, copywriter, registry
from agent.publish import service as post_service
from agent.video import pipeline

router = APIRouter(prefix="/api")


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
        "zalo_account_id": conv["zalo_account_id"] or "",
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

    delivery = await channels.get(conv["channel"]).send_text(conv["external_id"], body.text)
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
    delivery = await channels.get(conv["channel"]).send_text(conv["external_id"], msg["content"])
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
    # Có mã thì lấy ảnh trong kho sản phẩm. Thiếu trường này thì người dùng
    # dashboard chỉ dựng được video thẻ chữ, dù kho có sẵn ảnh cho đúng sản
    # phẩm đó — agent thì lấy được, người thì không. Một hệ thống mà công cụ
    # nội bộ mạnh hơn giao diện cho người dùng là hệ thống thiết kế hỏng.
    ma_san_pham: str = ""


@router.post("/videos")
async def create_video(body: VideoBody) -> dict:
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


@router.post("/videos/{video_id}/retry")
async def retry_video(video_id: str) -> dict:
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


# ---------------------------------------------------------------
#  Bài đăng mạng xã hội
#
#  Luồng: agent soạn -> người duyệt -> PublishAdapter phân phối ->
#  số liệu quay về -> agent dùng số liệu đó cho bài sau.
#  Không có nhánh nào bỏ qua bước duyệt.
# ---------------------------------------------------------------

class SoanBaiIn(BaseModel):
    kenh: str = Field("facebook")
    san_pham: str = ""
    y_tuong: str = ""
    video_id: str | None = None


class TaoBaiIn(BaseModel):
    tieu_de: str
    noi_dung: str
    kenh: list[str] = Field(default_factory=lambda: ["facebook"])
    hashtags: list[str] | None = None
    video_id: str | None = None
    lich_dang: datetime | None = None


class SoLieuIn(BaseModel):
    kenh: str
    luot_xem: int = 0
    luot_thich: int = 0
    binh_luan: int = 0
    chia_se: int = 0
    luot_click: int = 0
    url: str = ""


class CallbackIn(BaseModel):
    kenh: str
    ok: bool = True
    url: str = ""
    detail: str = ""


@router.get("/publish/channels")
async def publish_channels() -> dict:
    """Kênh nào đang đi đường nào, và nếu chưa dùng được thì vì sao."""
    return {"kenh": await registry.trang_thai_kenh()}


@router.post("/posts/draft")
async def draft_post(body: SoanBaiIn) -> dict:
    try:
        return await copywriter.soan(
            kenh=body.kenh, san_pham=body.san_pham,
            y_tuong=body.y_tuong, video_id=body.video_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/posts")
async def list_posts(trang_thai: str | None = None, limit: int = 50) -> dict:
    sql = (
        "SELECT p.*, v.file_path AS video_path FROM posts p "
        "LEFT JOIN videos v ON v.id = p.video_id "
    )
    args: list = []
    if trang_thai:
        sql += "WHERE p.trang_thai = $1 "
        args.append(trang_thai)
    sql += f"ORDER BY p.created_at DESC LIMIT ${len(args) + 1}"
    args.append(min(limit, 200))
    rows = await db.fetch(sql, *args)
    for r in rows:
        r["co_video"] = bool(r.pop("video_path", None))
    return {"posts": rows}


@router.post("/posts")
async def create_post(body: TaoBaiIn) -> dict:
    try:
        return await post_service.tao_bai(
            tieu_de=body.tieu_de, noi_dung=body.noi_dung, kenh=body.kenh,
            hashtags=body.hashtags, video_id=body.video_id,
            lich_dang=body.lich_dang, tao_boi="nguoi",
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/posts/{post_id}/approve")
async def approve_post(post_id: uuid.UUID) -> dict:
    try:
        return await post_service.duyet(str(post_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/posts/{post_id}/cancel")
async def cancel_post(post_id: uuid.UUID) -> dict:
    row = await db.fetchrow(
        "UPDATE posts SET trang_thai='da_huy', updated_at=now() "
        "WHERE id=$1 RETURNING *", post_id,
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy bài đăng")
    await db.log_event("post.cancelled", actor="nguoi", ref_id=post_id)
    return row


@router.post("/posts/{post_id}/callback")
async def post_callback(post_id: uuid.UUID, body: CallbackIn) -> dict:
    """n8n gọi về đây sau khi workflow chạy xong."""
    row = await post_service.ghi_nhan_callback(
        str(post_id), body.kenh, body.ok, body.url, body.detail
    )
    if row is None:
        raise HTTPException(404, "Không tìm thấy bài đăng")
    return row


@router.post("/posts/{post_id}/metrics")
async def add_metrics(post_id: uuid.UUID, body: SoLieuIn) -> dict:
    return await analytics.ghi_so_lieu(
        str(post_id), body.kenh, luot_xem=body.luot_xem,
        luot_thich=body.luot_thich, binh_luan=body.binh_luan,
        chia_se=body.chia_se, luot_click=body.luot_click, url=body.url,
    )


@router.get("/posts/{post_id}/metrics")
async def get_metrics(post_id: uuid.UUID) -> dict:
    return {"so_lieu": await analytics.moi_nhat_theo_bai(str(post_id))}


@router.get("/analytics")
async def get_analytics(ngay: int = 30) -> dict:
    tq = await analytics.tong_quan(ngay)
    tq["bai_tot_nhat"] = await analytics.bai_tot_nhat()
    return tq


@router.get("/catalog/products")
async def catalog_products() -> dict:
    """
    Danh sách gọn cho ô gợi ý sản phẩm khi soạn bài hoặc đặt video.

    Đọc qua `tools._catalog()` chứ không mở thẳng `catalog.json`: máy vừa
    clone repo về chưa có file đó, mở thẳng là ném FileNotFoundError và cả
    trang trắng. Hàm kia tự rơi về bản mẫu đi kèm repo.

    `so_anh` cho biết sản phẩm nào dựng video có hình được, sản phẩm nào chỉ
    ra thẻ chữ — biết trước vẫn hơn nhận về rồi mới thấy.
    """
    from agent.core.tools import _catalog
    from agent.video import catalog_images

    return {"san_pham": [
        {
            "ma": p["ma"],
            "ten": p["ten"],
            "loai": p.get("loai", ""),
            "so_anh": len(catalog_images.anh_cua(p["ma"])),
        }
        for p in _catalog().get("san_pham", [])
    ]}


# ---------------------------------------------------------------
#  Nick Zalo
#
#  Public API của ZaloCRM không liệt kê được nick, nên phần này đọc
#  CHỈ ĐỌC từ CSDL của nó. Xem agent/channels/zalocrm_accounts.py.
# ---------------------------------------------------------------

class ChonNickIn(BaseModel):
    zalo_account_id: str


@router.get("/zalo/accounts")
async def zalo_accounts() -> dict:
    ds = await zalo_acc.danh_sach()
    return {
        "accounts": ds,
        "dang_chon": runtime.STATE.get("zalo_account_id") or "",
        "ghi_chu": "" if ds else (
            "Không đọc được danh sách nick. Kiểm tra container zalo-crm-db "
            "đang chạy và ZALOCRM_DB_URL trong .env."
        ),
    }


@router.post("/zalo/account")
async def set_default_account(body: ChonNickIn) -> dict:
    """Đặt nick mặc định cho mọi hội thoại chưa ghim riêng."""
    if body.zalo_account_id and not await zalo_acc.hop_le(body.zalo_account_id):
        raise HTTPException(422, "Nick không tồn tại hoặc đang không kết nối")
    runtime.update(zalo_account_id=body.zalo_account_id)
    await db.log_event("zalo.account.default", actor="nguoi",
                       account_id=body.zalo_account_id)
    return {"dang_chon": body.zalo_account_id}


@router.post("/conversations/{conv_id}/account")
async def pin_conversation_account(conv_id: uuid.UUID, body: ChonNickIn) -> dict:
    """Ghim một nick cho riêng hội thoại này. Chuỗi rỗng = bỏ ghim."""
    acc = body.zalo_account_id or None
    if acc and not await zalo_acc.hop_le(acc):
        raise HTTPException(422, "Nick không tồn tại hoặc đang không kết nối")
    row = await db.fetchrow(
        "UPDATE conversations SET zalo_account_id = $2, updated_at = now() "
        "WHERE id = $1 RETURNING id, zalo_account_id", conv_id, acc,
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy hội thoại")
    await db.log_event("zalo.account.pinned", actor="nguoi",
                       ref_id=conv_id, account_id=acc)
    return row


@router.get("/channels")
async def list_channels() -> dict:
    """
    Kênh nào đang nối vào hệ thống, và đi bằng cơ chế gì.

    Hai kênh chạy ngược nhau (ZaloCRM kéo, Chatwoot đẩy) mà agent không
    phân biệt — đây là chỗ nhìn thấy điều đó.
    """
    bat = set(channels.dang_bat())
    co_che = {"zalocrm": "polling", "chatwoot": "webhook"}
    return {"channels": [
        {
            "ten": ten,
            "dang_bat": ten in bat,
            "co_che": co_che.get(ten, "webhook"),
            "webhook_url": (
                f"{settings.public_base_url}/webhook/{ten}"
                if co_che.get(ten) == "webhook" else ""
            ),
        }
        for ten in channels.tat_ca()
    ]}


class ChienDichIn(BaseModel):
    ten: str = Field(min_length=1, max_length=200)
    kenh: list[str] = Field(default_factory=lambda: ["facebook", "tiktok"])
    san_pham: str = ""
    y_tuong: str = ""
    video_id: str | None = None
    bat_dau: datetime | None = None
    gian_cach_phut: int = Field(30, ge=0, le=1440)


@router.post("/campaigns")
async def create_campaign(body: ChienDichIn) -> dict:
    """
    Một ý tưởng -> mỗi nền tảng một bài viết riêng, tất cả vào hàng chờ duyệt.

    Không phải copy-paste một caption ra bốn chỗ: mỗi kênh được soạn riêng
    theo hành vi người dùng của nó. Xem agent/publish/chien_dich.py.
    """
    try:
        return await chien_dich.tao(
            ten=body.ten, kenh=body.kenh, san_pham=body.san_pham,
            y_tuong=body.y_tuong, video_id=body.video_id,
            bat_dau=body.bat_dau, gian_cach_phut=body.gian_cach_phut,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/posts/approve-all")
async def approve_all(trang_thai: str = "cho_duyet") -> dict:
    """
    Duyệt hàng loạt — nhưng vẫn là NGƯỜI bấm, không phải hệ thống tự quyết.

    Bài vi phạm quảng cáo bị chặn riêng lẻ và báo rõ, không kéo đổ cả lô.
    """
    rows = await db.fetch(
        "SELECT id FROM posts WHERE trang_thai = $1 ORDER BY created_at", trang_thai
    )
    xong, chan = [], []
    for r in rows:
        try:
            kq = await post_service.duyet(str(r["id"]))
            xong.append({"id": str(r["id"]), "trang_thai": kq["trang_thai"]})
        except ValueError as exc:
            chan.append({"id": str(r["id"]), "ly_do": str(exc)})
    return {"da_duyet": len(xong), "bi_chan": len(chan),
            "chi_tiet": xong, "vi_pham": chan}


@router.get("/posts/{post_id}/kit")
async def post_kit(post_id: uuid.UUID) -> dict:
    """
    Gói mọi thứ cần để một người đăng bài THỦ CÔNG trong một phút.

    Đây không phải tính năng tạm bợ: chừng nào Facebook và TikTok chưa duyệt
    quyền, đây là con đường DUY NHẤT nội dung ra được cả bốn nền tảng. Làm
    cho nó nhanh và không sai sót còn giá trị hơn chờ App Review.

    Caption trả về đã ghép sẵn hashtag đúng định dạng từng nền tảng.
    """
    p = await db.fetchrow(
        "SELECT p.*, v.file_path FROM posts p "
        "LEFT JOIN videos v ON v.id = p.video_id WHERE p.id = $1", post_id,
    )
    if not p:
        raise HTTPException(404, "Không tìm thấy bài đăng")

    tags = [t if t.startswith("#") else f"#{t}" for t in (p["hashtags"] or [])]
    caption = f"{p['noi_dung']}\n\n{' '.join(tags)}".strip() if tags else p["noi_dung"]
    co_video = bool(p["file_path"] and Path(p["file_path"]).exists())

    # Mỗi nền tảng một chỗ đăng và một ràng buộc riêng — nói trước để người
    # đăng không phải nhớ, và không bị nền tảng từ chối vì sai định dạng.
    luu_y = {
        "facebook": "Trang cá nhân/Fanpage › Tạo bài viết. Video dọc hiển thị tốt trong Reels.",
        "instagram": "Chỉ đăng được từ điện thoại. Reels nhận video dọc 9:16, tối đa 90 giây.",
        "tiktok": "Video dọc 9:16. Caption tối đa 2.200 ký tự, hashtag tính trong giới hạn đó.",
        "youtube": "Shorts cần video dọc dưới 60 giây và có #Shorts trong tiêu đề hoặc mô tả.",
    }
    return {
        "id": str(post_id),
        "tieu_de": p["tieu_de"],
        "caption": caption,
        "hashtags": tags,
        "kenh": p["kenh"],
        "trang_thai": p["trang_thai"],
        "co_video": co_video,
        "video_url": f"/api/posts/{post_id}/video" if co_video else "",
        "luu_y": {k: luu_y.get(k, "") for k in (p["kenh"] or [])},
    }


@router.get("/posts/{post_id}/video")
async def post_video(post_id: uuid.UUID):
    """Tải video của bài về máy để đăng thủ công."""
    p = await db.fetchrow(
        "SELECT v.file_path FROM posts p JOIN videos v ON v.id = p.video_id "
        "WHERE p.id = $1", post_id,
    )
    if not p or not p["file_path"]:
        raise HTTPException(404, "Bài này không gắn video")
    f = Path(p["file_path"])
    if not f.exists():
        raise HTTPException(404, f"Không thấy file: {f.name}")
    return FileResponse(f, media_type="video/mp4", filename=f.name)


@router.post("/posts/{post_id}/mark-posted")
async def mark_posted(post_id: uuid.UUID, body: CallbackIn) -> dict:
    """
    Người đã đăng tay xong thì đánh dấu ở đây, kèm link bài thật.

    Có link mới đo được hiệu quả — không có nó thì bài coi như biến mất
    khỏi hệ thống ngay sau khi đăng, và vòng phản hồi số liệu đứt.
    """
    row = await post_service.ghi_nhan_callback(
        str(post_id), body.kenh, True, body.url, body.detail or "đăng thủ công"
    )
    if row is None:
        raise HTTPException(404, "Không tìm thấy bài đăng")
    return row


# ---------------------------------------------------------------
#  Chi phí và hiệu năng
#
#  Thay cho Langfuse. Mọi số ở đây đã nằm sẵn trong bảng `messages` từ
#  ngày đầu — model, token vào/ra, token đọc từ cache, chi phí, độ trễ.
#  Dựng lên từ dữ liệu của chính mình thì không phải cài thêm hệ thống,
#  không phải tạo tài khoản, và không có gì chạy nền mà không dùng.
# ---------------------------------------------------------------

@router.get("/cost")
async def cost_report(ngay: int = 7) -> dict:
    """Chi phí theo ngày, theo model, và các hội thoại tốn nhất."""
    theo_ngay = await db.fetch(
        """
        SELECT date_trunc('day', created_at)::date AS ngay,
               count(*)                            AS so_tin,
               coalesce(sum(cost_usd), 0)          AS chi_phi,
               coalesce(sum(tokens_in), 0)         AS token_vao,
               coalesce(sum(tokens_out), 0)        AS token_ra,
               coalesce(sum(cache_read), 0)        AS token_cache
        FROM messages
        WHERE role = 'agent' AND created_at > now() - ($1 || ' days')::interval
        GROUP BY 1 ORDER BY 1
        """,
        str(ngay),
    )
    theo_model = await db.fetch(
        """
        SELECT coalesce(model, '(không ghi)')      AS model,
               count(*)                            AS so_tin,
               coalesce(sum(cost_usd), 0)          AS chi_phi,
               coalesce(avg(latency_ms), 0)        AS tre_tb
        FROM messages
        WHERE role = 'agent' AND created_at > now() - ($1 || ' days')::interval
        GROUP BY 1 ORDER BY chi_phi DESC
        """,
        str(ngay),
    )
    dat_nhat = await db.fetch(
        """
        SELECT c.id, c.customer_name, c.channel, c.msg_count,
               coalesce(c.cost_usd, 0) AS chi_phi
        FROM conversations c
        WHERE c.updated_at > now() - ($1 || ' days')::interval
        ORDER BY c.cost_usd DESC NULLS LAST LIMIT 5
        """,
        str(ngay),
    )

    def _so(rows, *cot):
        for r in rows:
            for k in cot:
                r[k] = float(r[k] or 0)
        return rows

    _so(theo_ngay, "chi_phi")
    _so(theo_model, "chi_phi", "tre_tb")
    _so(dat_nhat, "chi_phi")
    for r in theo_ngay:
        r["ngay"] = r["ngay"].isoformat()
        for k in ("so_tin", "token_vao", "token_ra", "token_cache"):
            r[k] = int(r[k] or 0)
    for r in dat_nhat:
        r["id"] = str(r["id"])

    tong = sum(r["chi_phi"] for r in theo_ngay)
    t_vao = sum(r["token_vao"] for r in theo_ngay)
    t_cache = sum(r["token_cache"] for r in theo_ngay)
    so_tin = sum(r["so_tin"] for r in theo_ngay)

    return {
        "ngay": ngay,
        "theo_ngay": theo_ngay,
        "theo_model": theo_model,
        "hoi_thoai_dat_nhat": dat_nhat,
        "tong": {
            "chi_phi_usd": round(tong, 6),
            "chi_phi_vnd": round(tong * 25000),
            "so_tin": so_tin,
            "trung_binh_moi_tin": round(tong / so_tin, 6) if so_tin else 0,
            "token_vao": t_vao,
            "token_ra": sum(r["token_ra"] for r in theo_ngay),
            # Tỉ lệ token đọc từ cache. Vertex không tự cache, phải tự đặt
            # cache_control lên khối ổn định — con số này cho biết việc đó
            # có thật sự ăn thua không.
            "ty_le_cache": round(t_cache / t_vao * 100, 1) if t_vao else 0.0,
        },
    }
