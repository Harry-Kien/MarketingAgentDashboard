"""
Điểm vào duy nhất: webhook kênh + API dashboard + phục vụ giao diện tĩnh.

Chạy:  uvicorn agent.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from agent import db, runtime
from agent.api.routes import router as api_router
from agent.channels.base import InboundMessage
from agent.channels.zalocrm import ZaloCRMAdapter
from agent.config import ROOT, settings
from agent.core import agent as brain

DASHBOARD_DIR = ROOT / "dashboard"
channel = ZaloCRMAdapter()

HISTORY_TURNS = 12


async def poll_loop() -> None:
    """
    Hỏi ZaloCRM có tin mới không, mỗi vài giây.

    Phải làm thế này vì ZaloCRM chạy webhook qua một chốt chặn SSRF từ chối
    HTTP và mọi địa chỉ loopback/private — tức là không bao giờ gọi được về
    máy local. Giai đoạn 2 (Zalo OA) sẽ là webhook thật; lớp ChannelAdapter
    khiến việc đổi ấy không ảnh hưởng phần còn lại.
    """
    while True:
        try:
            if settings.zalocrm_api_key and runtime.enabled():
                for msg in await channel.fetch_new():
                    await handle_inbound(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — vòng lặp nền không được chết
            await db.log_event("poll.error", error=f"{type(exc).__name__}: {exc}"[:200])
        await asyncio.sleep(settings.zalocrm_poll_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    await db.log_event("app.start", mode=runtime.mode(), enabled=runtime.enabled())

    poller = asyncio.create_task(poll_loop()) if settings.zalocrm_api_key else None
    if poller:
        await db.log_event("poll.start", every_s=settings.zalocrm_poll_seconds)

    yield

    if poller:
        poller.cancel()
        with suppress(asyncio.CancelledError):
            await poller
    await channel.aclose()
    await db.close_db()


app = FastAPI(title="Marketing Agent", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "runtime": dict(runtime.STATE)}


# ---------------------------------------------------------------
#  Webhook — cửa vào của mọi tin nhắn khách
# ---------------------------------------------------------------

@app.post("/webhook")
async def webhook(request: Request, tasks: BackgroundTasks) -> JSONResponse:
    if settings.webhook_secret:
        supplied = request.headers.get("x-webhook-secret", "")
        if supplied != settings.webhook_secret:
            return JSONResponse({"ok": False, "error": "sai secret"}, status_code=401)

    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "payload không phải JSON"}, 400)

    inbound = channel.parse(payload)
    if inbound is None:
        return JSONResponse({"ok": True, "skipped": "không phải tin văn bản đến"})

    # Trả 200 ngay để kênh không retry; xử lý ở nền.
    tasks.add_task(handle_inbound, inbound)
    return JSONResponse({"ok": True, "queued": True})


async def handle_inbound(msg: InboundMessage) -> None:
    """Toàn bộ luồng xử lý một tin nhắn đến."""
    if await db.seen_webhook(msg.dedupe_key):
        return  # đã xử lý — chống gửi trùng

    conv = await db.fetchrow(
        """
        INSERT INTO conversations (channel, external_id, customer_name, customer_ref)
        VALUES ($1,$2,$3,$4)
        ON CONFLICT (channel, external_id) DO UPDATE
            SET customer_name = EXCLUDED.customer_name, updated_at = now()
        RETURNING *
        """,
        msg.channel,
        msg.conversation_ref,
        msg.customer_name,
        msg.customer_ref,
    )
    cid: uuid.UUID = conv["id"]

    await db.execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES ($1,'customer',$2)",
        cid,
        msg.text,
    )
    await db.execute(
        "UPDATE conversations SET msg_count = msg_count + 1, updated_at = now() "
        "WHERE id = $1",
        cid,
    )

    # Công tắc ngắt, hoặc hội thoại đã do người tiếp quản -> agent đứng ngoài.
    if not runtime.enabled() or conv["status"] == "escalated":
        await db.execute(
            "UPDATE conversations SET status = 'escalated', updated_at = now() "
            "WHERE id = $1",
            cid,
        )
        return

    history = await _history(cid)

    runtime.mark_busy(cid)          # dashboard vẽ bong bóng "đang soạn tin"
    try:
        reply = await brain.respond(conversation_id=cid, history=history, question=msg.text)
    except Exception as exc:  # noqa: BLE001 — suy giảm êm, không bao giờ im lặng
        await db.execute(
            "UPDATE conversations SET status = 'escalated', updated_at = now() "
            "WHERE id = $1",
            cid,
        )
        await db.log_event("agent.error", ref_id=cid, error=f"{type(exc).__name__}: {exc}")
        return
    finally:
        runtime.clear_busy(cid)

    # Chế độ assist: soạn nhưng KHÔNG gửi, chờ người duyệt.
    auto_send = runtime.mode() == "auto" and not reply.escalate
    delivered = False
    if auto_send and await channel.can_send_now(msg.conversation_ref):
        delivered = (await channel.send_text(msg.conversation_ref, reply.text)).ok

    await db.execute(
        """
        INSERT INTO messages
            (conversation_id, role, content, delivered, grounded, confidence,
             sources, model, tokens_in, tokens_out, cache_read, cost_usd, latency_ms)
        VALUES ($1,'agent',$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
        """,
        cid,
        reply.text,
        delivered,
        reply.grounded,
        reply.confidence,
        reply.sources,   # codec JSONB tu ma hoa
        reply.model,
        reply.tokens_in,
        reply.tokens_out,
        reply.cache_read,
        reply.cost_usd,
        reply.latency_ms,
    )

    status = "escalated" if reply.escalate else ("auto" if delivered else "assist")
    await db.execute(
        """
        UPDATE conversations
        SET cost_usd = cost_usd + $2,
            msg_count = msg_count + 1,
            status = $3,
            outcome = CASE WHEN $3 = 'escalated' THEN 'escalated' ELSE outcome END,
            updated_at = now()
        WHERE id = $1
        """,
        cid,
        reply.cost_usd,
        status,
    )

    if reply.escalate:
        await db.log_event(
            "conversation.escalated", ref_id=cid, reason=reply.escalate_reason
        )


async def _history(cid: uuid.UUID) -> list[dict]:
    """Lấy các lượt gần nhất, đã chuẩn hoá cho Messages API."""
    rows = await db.fetch(
        """
        SELECT role, content FROM messages
        WHERE conversation_id = $1 AND role IN ('customer','agent','staff')
        ORDER BY created_at DESC LIMIT $2
        """,
        cid,
        HISTORY_TURNS + 1,
    )
    turns = []
    for r in reversed(rows[1:]):  # bỏ tin vừa lưu, nó sẽ là `question`
        turns.append(
            {
                "role": "user" if r["role"] == "customer" else "assistant",
                "content": r["content"],
            }
        )
    # Messages API yêu cầu lượt đầu là user.
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    return turns


# ---------------------------------------------------------------
#  Giao diện
# ---------------------------------------------------------------

if DASHBOARD_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")
