"""API cho dashboard. Chỉ đọc/ghi Postgres và gọi adapter kênh."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     Response, UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import db, runtime
from agent.channels import registry as channels
from agent.config import settings
from agent.channels import zalocrm_accounts as zalo_acc
from agent.core import du_lieu_ca_nhan, kho, rag, xac_thuc
from agent.publish import analytics, chien_dich, copywriter, registry
from agent.publish import service as post_service
from agent.video import pipeline

router = APIRouter(prefix="/api")

# --- Xác thực: đặt NGAY ĐÂY, trước mọi endpoint ---------------
# Python đánh giá tham số mặc định lúc ĐỊNH NGHĨA hàm, nên
# `Depends(bat_buoc_quan_tri)` ở endpoint dòng 500 cần hàm này đã tồn
# tại từ trước. Để cuối file thì NameError lúc import — và lỗi đó chỉ
# nổ khi khởi động, không phải khi chạy test.
TEN_COOKIE = "phien_marketing_agent"


class DangNhapIn(BaseModel):
    ten_dang_nhap: str = Field(min_length=1, max_length=64)
    mat_khau: str = Field(min_length=1, max_length=200)


class DoiMatKhauIn(BaseModel):
    mat_khau_moi: str = Field(min_length=8, max_length=200)


class TaoNguoiDungIn(BaseModel):
    ten_dang_nhap: str = Field(min_length=3, max_length=64)
    mat_khau: str = Field(min_length=8, max_length=200)
    ho_ten: str = Field("", max_length=120)
    vai_tro: str = Field("nhan_vien")


async def nguoi_hien_tai(request: Request) -> dict | None:
    """Người đứng sau phiên hiện tại, hoặc None."""
    return await xac_thuc.doc_phien(request.cookies.get(TEN_COOKIE, ""))


async def bat_buoc_dang_nhap(request: Request) -> dict:
    nguoi = await nguoi_hien_tai(request)
    if nguoi is None:
        raise HTTPException(401, "Chưa đăng nhập")
    return nguoi


async def bat_buoc_quan_tri(request: Request) -> dict:
    nguoi = await bat_buoc_dang_nhap(request)
    if nguoi["vai_tro"] != "quan_tri":
        raise HTTPException(403, "Việc này cần quyền quản trị")
    return nguoi




def _num(v) -> float:
    return float(v or 0)


# ---------------------------------------------------------------
#  Tổng quan ca trực
# ---------------------------------------------------------------

@router.get("/he-thong")
async def he_thong() -> dict:
    """
    Mọi hệ thống con nhìn từ MỘT chỗ: cái nào sống, mở ở đâu.

    Đây là cổng vào duy nhất để nhớ, không phải tiến trình duy nhất để chạy
    — xem `agent/he_thong.py` để biết vì sao không gộp làm một.
    """
    from agent import he_thong as ht

    return await ht.kiem_tat_ca()


@router.get("/suc-khoe")
async def suc_khoe() -> dict:
    """
    Tự chẩn đoán: mọi mảnh của hệ thống có ĐANG PHỤC VỤ ĐƯỢC không.

    Khác `/healthz` ở chỗ nó gọi thật từng thứ thay vì chỉ xác nhận tiến
    trình còn sống. Tiến trình sống mà hết hạn mức model thì khách vẫn không
    được trả lời — và khoảng thời gian giữa lúc hỏng và lúc có người phát
    hiện chính là khoảng thời gian mất khách.

    Mất vài giây vì có gọi model thật. Đừng đặt vào vòng làm mới tự động.
    """
    from agent import suc_khoe as sk

    return await sk.tong_kiem()


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
    if status == "can_nguoi":
        # Mọi hội thoại ĐANG CHỜ NGƯỜI, gộp một chỗ.
        #
        # `assist` là agent soạn xong chờ duyệt; `escalated` là agent tự nhận
        # không đủ thẩm quyền. Hai trạng thái khác nhau nhưng CÙNG một việc
        # cần làm: một người phải vào trả lời khách.
        #
        # Trước đây khung "Chờ người xử lý" chỉ lọc `assist`, nên hội thoại
        # đã chuyển người biến mất khỏi màn hình trực. Đo trên dữ liệu thật:
        # 2 cái hiện, 7 cái không — bảy khách ngồi đợi mà không ai thấy.
        sql += " WHERE c.status IN ('assist', 'escalated')"
    elif status and status != "all":
        sql += " WHERE c.status = $1"
        args.append(status)
    sql += f" ORDER BY c.updated_at DESC LIMIT {int(limit)}"

    rows = await db.fetch(sql, *args)
    return [
        {
            "id": str(r["id"]),
            "channel": r["channel"],
            # Nền tảng gốc: Chatwoot gom nhiều nơi về một kênh, dashboard
            # cần biết khách thật sự nhắn từ Facebook hay Instagram.
            "nen_tang": r.get("nen_tang"),
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
        "nen_tang": conv["nen_tang"],
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
async def set_runtime(body: RuntimeBody, nguoi: dict = Depends(bat_buoc_quan_tri)) -> dict:
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
    """
    Huỷ đơn và TRẢ HÀNG VỀ KHO.

    Không trả lại thì mỗi đơn huỷ ăn mất tồn kho vĩnh viễn — bán mười đơn
    huỷ chín đơn là kho báo hết hàng trong khi hàng vẫn nằm nguyên trên kệ.
    """
    oid = uuid.UUID(order_id)
    don = await db.fetchrow(
        "UPDATE orders SET trang_thai='da_huy', updated_at=now() "
        "WHERE id=$1 AND trang_thai <> 'da_huy' RETURNING ma_don", oid,
    )
    if don is None:
        return {"ok": True, "ghi_chu": "Đơn đã huỷ từ trước, không trả kho lần nữa."}

    so_dong = await kho.tra_hang(don["ma_don"])
    await db.log_event("order.cancel", actor="staff", ref_id=oid,
                       ma_don=don["ma_don"], so_mat_hang_tra_kho=so_dong)
    return {"ok": True, "ma_don": don["ma_don"], "da_tra_kho": so_dong}


# ---------------------------------------------------------------
#  Kho hàng
# ---------------------------------------------------------------

class NhapKhoIn(BaseModel):
    so_luong: int = Field(gt=0, le=100000)
    ghi_chu: str = Field("", max_length=300)


class KiemKeIn(BaseModel):
    so_luong_moi: int = Field(ge=0, le=100000)
    ly_do: str = Field(min_length=3, max_length=300)


@router.get("/kho")
async def kho_tong_quan() -> dict:
    """Tồn kho sống của mọi mã, kèm tên và giá lấy từ danh mục."""
    import json as _json
    from agent.core.tools import _catalog

    danh_muc = {p["ma"]: p for p in _catalog().get("san_pham", [])}
    ton = await db.fetch("SELECT ma, so_luong, cap_nhat_luc FROM ton_kho ORDER BY ma")
    ra = []
    for t in ton:
        sp = danh_muc.get(t["ma"], {})
        ra.append({
            "ma": t["ma"],
            "ten": sp.get("ten", "(không có trong danh mục)"),
            "loai": sp.get("loai", ""),
            "gia": sp.get("gia", 0),
            "so_luong": int(t["so_luong"]),
            "sap_het": int(t["so_luong"]) <= kho.NGUONG_SAP_HET,
            "cap_nhat_luc": t["cap_nhat_luc"].isoformat(),
        })
    het = [x for x in ra if x["so_luong"] == 0]
    sap = [x for x in ra if 0 < x["so_luong"] <= kho.NGUONG_SAP_HET]
    return {
        "san_pham": ra,
        "tong_ma": len(ra),
        "het_hang": len(het),
        "sap_het": len(sap),
        "nguong_sap_het": kho.NGUONG_SAP_HET,
        "gia_tri_ton": sum(x["so_luong"] * (x["gia"] or 0) for x in ra),
    }


@router.get("/kho/bien-dong")
async def kho_bien_dong(ma: str = "", limit: int = 50) -> dict:
    return {"bien_dong": await kho.so_bien_dong(ma, limit)}


@router.post("/kho/{ma}/nhap")
async def kho_nhap(ma: str, body: NhapKhoIn) -> dict:
    try:
        r = await kho.nhap_hang(ma, body.so_luong, body.ghi_chu)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db.log_event("kho.nhap", actor="nguoi", ma=ma, so_luong=body.so_luong)
    return r


@router.post("/kho/{ma}/kiem-ke")
async def kho_kiem_ke(ma: str, body: KiemKeIn) -> dict:
    """
    Đặt lại số tồn về đúng thực tế đếm được.

    Kho LUÔN lệch — vỡ, mất, đếm sai. Cần một đường sửa hợp lệ, và đường đó
    bắt buộc phải có lý do để sau này truy được.
    """
    try:
        r = await kho.dieu_chinh(ma, body.so_luong_moi, body.ly_do)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db.log_event("kho.kiem_ke", actor="nguoi", **r, ly_do=body.ly_do)
    return r


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


@router.get("/analytics/khach")
async def analytics_khach(ngay: int = 30) -> dict:
    """
    Khách đến từ đâu, và mỗi kênh chạy tốt tới mức nào.

    `/analytics` cũ chỉ nói về BÀI ĐĂNG — lượt xem, lượt thích. Không có gì
    trả lời được câu hỏi cơ bản nhất của người vận hành: khách của mình đến
    từ kênh nào, kênh nào agent tự lo được, kênh nào phải gọi người liên tục.

    Mỗi kênh một dòng, kèm hai tỷ lệ đáng nhìn nhất:
      tu_xu_ly   agent xử lý trọn, không cần người
      chuyen_nguoi  agent tự nhận không đủ thẩm quyền

    Kênh có tỷ lệ chuyển người cao bất thường không phải là kênh tệ — thường
    là kênh có loại câu hỏi khác hẳn, và đó là tín hiệu để bổ sung tài liệu
    cho đúng chỗ.
    """
    tu = datetime.now(timezone.utc) - timedelta(days=max(1, min(ngay, 365)))

    rows = await db.fetch(
        """
        SELECT c.channel,
               -- Gộp theo NỀN TẢNG GỐC khi có. Chatwoot mà không tách thì
               -- Facebook, Instagram, WhatsApp bị nhập làm một dòng, và
               -- bảng này mất đúng thứ nó sinh ra để trả lời.
               coalesce(c.nen_tang, c.channel)                      AS nen_tang,
               count(*)                                            AS hoi_thoai,
               count(DISTINCT c.customer_ref)                      AS khach,
               coalesce(sum(c.msg_count), 0)                       AS tin,
               count(*) FILTER (WHERE c.status = 'auto')           AS tu_xu_ly,
               count(*) FILTER (WHERE c.status = 'escalated')      AS chuyen_nguoi,
               count(*) FILTER (WHERE c.status = 'assist')         AS cho_duyet,
               coalesce(sum(c.cost_usd), 0)                        AS chi_phi,
               max(c.updated_at)                                   AS gan_nhat
        FROM conversations c
        WHERE c.updated_at >= $1
        GROUP BY c.channel, coalesce(c.nen_tang, c.channel)
        ORDER BY count(*) DESC
        """,
        tu,
    )

    # Chất lượng trả lời đo ở bảng `messages`, không gộp chung được vào câu
    # trên vì join sẽ nhân bản dòng và làm sai mọi phép đếm hội thoại.
    chat_luong = {
        r["nen_tang"]: r
        for r in await db.fetch(
            """
            SELECT coalesce(c.nen_tang, c.channel)         AS nen_tang,
                   count(*)                                    AS luot_tra_loi,
                   count(*) FILTER (WHERE m.grounded IS TRUE)  AS co_can_cu,
                   coalesce(avg(m.latency_ms), 0)              AS tre_tb
            FROM messages m JOIN conversations c ON c.id = m.conversation_id
            WHERE m.role = 'agent' AND m.created_at >= $1
            GROUP BY coalesce(c.nen_tang, c.channel)
            """,
            tu,
        )
    }

    kenh = []
    for r in rows:
        tong = int(r["hoi_thoai"]) or 1
        q = chat_luong.get(r["nen_tang"], {})
        tra_loi = int(q.get("luot_tra_loi") or 0)
        kenh.append({
            "kenh": r["channel"],
            "nen_tang": r["nen_tang"],
            "hoi_thoai": int(r["hoi_thoai"]),
            "khach": int(r["khach"] or 0),
            "tin": int(r["tin"] or 0),
            "tu_xu_ly": int(r["tu_xu_ly"]),
            "chuyen_nguoi": int(r["chuyen_nguoi"]),
            "cho_duyet": int(r["cho_duyet"]),
            "ty_le_tu_xu_ly": round(int(r["tu_xu_ly"]) / tong, 4),
            "ty_le_chuyen_nguoi": round(int(r["chuyen_nguoi"]) / tong, 4),
            "co_can_cu": round(int(q.get("co_can_cu") or 0) / tra_loi, 4) if tra_loi else None,
            "tre_tb_ms": int(_num(q.get("tre_tb"))),
            "chi_phi": round(_num(r["chi_phi"]), 6),
            "chi_phi_moi_hoi_thoai": round(_num(r["chi_phi"]) / tong, 6),
            "gan_nhat": r["gan_nhat"].isoformat() if r["gan_nhat"] else None,
        })

    return {
        "ngay": ngay,
        "kenh": kenh,
        "tong": {
            "hoi_thoai": sum(k["hoi_thoai"] for k in kenh),
            "khach": sum(k["khach"] for k in kenh),
            "chi_phi": round(sum(k["chi_phi"] for k in kenh), 6),
            "so_kenh": len(kenh),
        },
    }


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


# ---------------------------------------------------------------
#  Bảo vệ dữ liệu cá nhân — Nghị định 13/2023/NĐ-CP
#
#  Ba quyền của chủ thể dữ liệu mà hệ thống phải đáp ứng được:
#    Điều 9.1.c  quyền BIẾT hệ thống giữ gì   -> GET  /api/pdpd/{sdt}
#    Điều 9.1.đ  quyền YÊU CẦU XOÁ            -> POST /api/pdpd/{sdt}/xoa
#    Điều 16     thời hạn lưu trữ              -> POST /api/pdpd/don-theo-han
# ---------------------------------------------------------------

class XoaDuLieuIn(BaseModel):
    ly_do: str = Field("khách yêu cầu", max_length=300)
    # Xoá không hoàn tác được. Bắt gõ đúng số điện thoại một lần nữa để
    # không ai xoá nhầm bằng một cú bấm lỡ tay.
    xac_nhan_sdt: str = Field(min_length=9, max_length=20)


@router.get("/pdpd/{sdt}")
async def pdpd_tra_cuu(sdt: str) -> dict:
    """Hệ thống đang giữ những gì về số điện thoại này."""
    try:
        return await du_lieu_ca_nhan.tra_cuu(sdt)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/pdpd/{sdt}/xoa")
async def pdpd_xoa(sdt: str, body: XoaDuLieuIn,
                   nguoi: dict = Depends(bat_buoc_quan_tri)) -> dict:
    """
    Thực hiện yêu cầu xoá. KHÔNG HOÀN TÁC ĐƯỢC.

    Hội thoại và tin nhắn xoá hẳn; đơn hàng ẩn danh để giữ nghĩa vụ lưu
    chứng từ kế toán (Luật Kế toán 2015, Điều 41).
    """
    chuan = du_lieu_ca_nhan.chuan_hoa_sdt
    if chuan(body.xac_nhan_sdt) != chuan(sdt):
        raise HTTPException(422, "Số xác nhận không khớp — nhập lại để chắc chắn")
    try:
        # Ghi TÊN THẬT của người xoá, không ghi "nguoi" chung chung. Xoá dữ
        # liệu cá nhân là việc không hoàn tác được; nhật ký phải trả lời
        # được câu "ai đã làm việc này".
        return await du_lieu_ca_nhan.xoa(
            sdt, ly_do=f"{body.ly_do} (bởi {nguoi['ten_dang_nhap']})"
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/pdpd")
async def pdpd_tong_quan() -> dict:
    """Chính sách lưu trữ đang áp dụng và số bản ghi sắp quá hạn."""
    return {
        **await du_lieu_ca_nhan.don_theo_thoi_han(chi_dem=True),
        "tu_dong_don": settings.tu_dong_don_du_lieu,
        "can_cu": [
            "Nghị định 13/2023/NĐ-CP — bảo vệ dữ liệu cá nhân",
            "Luật Kế toán 2015, Điều 41 — thời hạn lưu chứng từ",
        ],
    }


@router.post("/pdpd/don-theo-han")
async def pdpd_don() -> dict:
    """Dọn ngay hội thoại quá thời hạn, không chờ vòng lặp hằng ngày."""
    return await du_lieu_ca_nhan.don_theo_thoi_han()


# ---------------------------------------------------------------
#  Đăng nhập
#
#  Dashboard đọc PII khách hàng, gửi tin nhân danh doanh nghiệp, và xoá
#  vĩnh viễn dữ liệu. Trước lớp này, ai chạm được cổng 8000 đều làm được
#  tất cả — chỉ an toàn nhờ nghe ở 127.0.0.1, tức an toàn cho tới đúng ngày
#  ai đó đưa lên server.
# ---------------------------------------------------------------

@router.post("/dang-nhap")
async def dang_nhap(body: DangNhapIn, response: Response) -> dict:
    token = await xac_thuc.dang_nhap(body.ten_dang_nhap, body.mat_khau)
    if token is None:
        # KHÔNG nói sai tên hay sai mật khẩu. Nói rõ là chỉ ra tên nào có
        # tồn tại, và đó là nửa đầu của việc dò tài khoản.
        raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu không đúng")

    response.set_cookie(
        TEN_COOKIE, token,
        httponly=True,       # JavaScript không đọc được -> XSS không lấy được phiên
        samesite="lax",      # chặn gửi cookie kèm request từ trang khác
        max_age=xac_thuc.PHIEN_NGAY * 86400,
        # secure=True khi chạy sau HTTPS. Bật cứng ở đây thì đăng nhập trên
        # http://localhost hỏng, nên để theo cấu hình.
        secure=settings.cookie_bao_mat,
    )
    nguoi = await xac_thuc.doc_phien(token)
    return {"ok": True, "nguoi": nguoi}


@router.post("/dang-xuat")
async def dang_xuat(request: Request, response: Response) -> dict:
    await xac_thuc.dang_xuat(request.cookies.get(TEN_COOKIE, ""))
    response.delete_cookie(TEN_COOKIE)
    return {"ok": True}


@router.get("/toi")
async def toi(request: Request) -> dict:
    """Ai đang đăng nhập. Dashboard gọi lúc tải để biết có cần vào trang đăng nhập không."""
    nguoi = await nguoi_hien_tai(request)
    if nguoi is None:
        raise HTTPException(401, "Chưa đăng nhập")
    return nguoi


@router.post("/toi/doi-mat-khau")
async def doi_mat_khau(body: DoiMatKhauIn,
                       nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    """Đổi mật khẩu của chính mình. Mọi phiên đang mở bị đá ra."""
    await xac_thuc.doi_mat_khau(nguoi["ten_dang_nhap"], body.mat_khau_moi)
    await db.log_event("auth.doi_mat_khau", actor=nguoi["ten_dang_nhap"])
    return {"ok": True, "ghi_chu": "Đã đổi. Mọi thiết bị phải đăng nhập lại."}


@router.get("/nguoi-dung")
async def danh_sach_nguoi_dung(_: dict = Depends(bat_buoc_quan_tri)) -> dict:
    rows = await db.fetch(
        "SELECT id, ten_dang_nhap, ho_ten, vai_tro, khoa, tao_luc, dang_nhap_cuoi "
        "FROM nguoi_dung ORDER BY tao_luc"
    )
    for r in rows:
        r["id"] = str(r["id"])
        for k in ("tao_luc", "dang_nhap_cuoi"):
            if r.get(k):
                r[k] = r[k].isoformat()
    return {"nguoi_dung": rows}


@router.post("/nguoi-dung")
async def them_nguoi_dung(body: TaoNguoiDungIn,
                          nguoi: dict = Depends(bat_buoc_quan_tri)) -> dict:
    try:
        r = await xac_thuc.tao_nguoi_dung(
            body.ten_dang_nhap, body.mat_khau, body.ho_ten, body.vai_tro
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db.log_event("auth.tao_nguoi_dung", actor=nguoi["ten_dang_nhap"],
                       ten_moi=body.ten_dang_nhap, vai_tro=body.vai_tro)
    return r


@router.post("/nguoi-dung/{ten}/khoa")
async def khoa_nguoi_dung(ten: str, khoa: bool = True,
                          nguoi: dict = Depends(bat_buoc_quan_tri)) -> dict:
    """
    Khoá tài khoản và ĐÁ MỌI PHIÊN ĐANG MỞ.

    Khoá mà không xoá phiên thì người vừa bị khoá vẫn ngồi trong hệ thống
    tới lúc phiên hết hạn — với hệ thống nắm dữ liệu khách hàng, đó là bảy
    ngày quá nhiều.
    """
    if ten.strip().lower() == nguoi["ten_dang_nhap"]:
        raise HTTPException(422, "Không tự khoá tài khoản của mình được")
    r = await db.fetchrow(
        "UPDATE nguoi_dung SET khoa = $2 WHERE ten_dang_nhap = $1 RETURNING id",
        ten.strip().lower(), khoa,
    )
    if r is None:
        raise HTTPException(404, "Không có tài khoản này")
    if khoa:
        await db.execute("DELETE FROM phien WHERE nguoi_dung_id = $1", r["id"])
    await db.log_event("auth.khoa_nguoi_dung", actor=nguoi["ten_dang_nhap"],
                       ten=ten, khoa=khoa)
    return {"ok": True, "ten_dang_nhap": ten, "khoa": khoa}
