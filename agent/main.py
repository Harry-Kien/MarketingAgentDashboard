"""
Điểm vào duy nhất: webhook kênh + API dashboard + phục vụ giao diện tĩnh.

Chạy:  uvicorn agent.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import secrets
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from agent import db, runtime
from agent.api.routes import TEN_COOKIE
from agent.api.routes import router as api_router
from agent.channels.base import InboundMessage
from agent.channels import registry as channels
from agent.channels import zalocrm_accounts as zalo_acc
from agent.config import ROOT, settings
from agent.core import agent as brain
from agent import canh_gac
from agent.core import du_lieu_ca_nhan, xac_thuc
from agent.core import tu_nhien
from agent.publish import registry as pub_registry
from agent.publish import service as post_service
from agent.video import worker as video_worker

DASHBOARD_DIR = ROOT / "dashboard"

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
                for msg in await channels.keo_tin_moi():
                    await handle_inbound(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — vòng lặp nền không được chết
            await db.log_event("poll.error", error=f"{type(exc).__name__}: {exc}"[:200])
        await asyncio.sleep(settings.zalocrm_poll_seconds)


async def schedule_loop() -> None:
    """
    Đăng những bài ĐÃ DUYỆT và đã tới giờ hẹn.

    Chỉ đụng tới trạng thái `da_len_lich` — bài chưa duyệt không bao giờ
    lọt vào đây, dù có lịch hẹn hay không. Hẹn giờ là tiện lợi, không phải
    đường vòng qua khâu duyệt.
    """
    while True:
        try:
            for row in await post_service.den_gio_dang():
                await post_service.dang_bai(str(row["id"]), boi="lich_hen")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await db.log_event("schedule.error",
                               error=f"{type(exc).__name__}: {exc}"[:200])
        await asyncio.sleep(30)


async def backup_loop() -> None:
    """
    Sao lưu CSDL mỗi ngày một lần.

    Đặt trong app chứ không giao cho Task Scheduler của Windows vì lý do rất
    thực tế: việc gì phải nhớ mới làm thì sẽ có ngày không ai nhớ. Sao lưu
    là thứ chỉ có giá trị khi nó chạy đều, và mất dữ liệu là loại hỏng duy
    nhất trong hệ thống này KHÔNG sửa được sau.

    Chạy trong luồng riêng vì `pg_dump` là lời gọi đồng bộ và có thể mất vài
    giây — đủ lâu để làm nghẽn việc trả lời khách nếu chạy thẳng.
    """
    while True:
        try:
            if settings.sao_luu_moi_ngay:
                from scripts import sao_luu as bk

                dau = __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).strftime("%Y%m%d-%H%M%S")
                ok, ghi_chu = await asyncio.to_thread(
                    bk.sao_luu_db, bk.KHO / f"db-{dau}.sql.gz"
                )
                await asyncio.to_thread(bk.sao_luu_tai_lieu,
                                        bk.KHO / f"knowledge-{dau}.tar.gz")
                await asyncio.to_thread(bk.don_ban_cu, settings.sao_luu_giu_lai)
                await db.log_event(
                    "backup.done" if ok else "backup.failed", ghi_chu=ghi_chu[:200]
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — vòng lặp nền không được chết
            await db.log_event("backup.error",
                               error=f"{type(exc).__name__}: {exc}"[:200])
        await asyncio.sleep(24 * 3600)


async def don_du_lieu_loop() -> None:
    """
    Dọn hội thoại quá thời hạn lưu trữ, mỗi ngày một lần.

    Nghị định 13/2023/NĐ-CP Điều 16: dữ liệu chỉ được lưu trong thời hạn
    phù hợp với mục đích đã thông báo. Không có vòng này thì "chính sách
    lưu 180 ngày" chỉ là một dòng trong tài liệu, còn dữ liệu thì nằm đó
    mãi mãi.

    Chạy một lần lúc khởi động rồi cứ 24 giờ một lần. Chỉ đụng hội thoại,
    KHÔNG đụng đơn hàng — chứng từ kế toán có thời hạn riêng dài hơn nhiều.
    """
    while True:
        try:
            if settings.tu_dong_don_du_lieu:
                kq = await du_lieu_ca_nhan.don_theo_thoi_han()
                if kq["da_xoa"]:
                    await db.log_event(
                        "pdpd.auto", so_hoi_thoai=kq["da_xoa"],
                        thoi_han_ngay=kq["thoi_han_ngay"],
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await db.log_event(
                "pdpd.error", error=f"{type(exc).__name__}: {exc}"[:200]
            )
        await asyncio.sleep(24 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    await db.log_event("app.start", mode=runtime.mode(), enabled=runtime.enabled())

    poller = asyncio.create_task(poll_loop()) if settings.zalocrm_api_key else None
    scheduler = asyncio.create_task(schedule_loop())
    don_du_lieu = asyncio.create_task(don_du_lieu_loop())
    # Canh gác: phát hiện SUY GIẢM (model chết, kênh mất kết nối, sao
    # lưu cũ). KHÔNG phát hiện được chính tiến trình này chết — lúc đó
    # nó chết theo. Xem scripts/canh_gac_ngoai.py cho trường hợp ấy.
    canh = asyncio.create_task(canh_gac.vong_canh_gac())
    # Thợ dựng video: nhặt lại việc dở dang của lần chạy trước rồi chạy tiếp.
    # Không có bước này thì app tắt giữa chừng là video chết cứng ở trạng
    # thái dở, không ai nhặt lại và không dòng lỗi nào.
    video_workers = await video_worker.start()
    backuper = asyncio.create_task(backup_loop())
    if poller:
        await db.log_event("poll.start", every_s=settings.zalocrm_poll_seconds)

    yield

    backuper.cancel()
    with suppress(asyncio.CancelledError):
        await backuper
    for w in video_workers:
        w.cancel()
    for w in video_workers:
        with suppress(asyncio.CancelledError):
            await w
    for t in (scheduler, don_du_lieu, canh):
        t.cancel()
        with suppress(asyncio.CancelledError):
            await t
    if poller:
        poller.cancel()
        with suppress(asyncio.CancelledError):
            await poller
    await pub_registry.dong_tat_ca()
    await zalo_acc.aclose()
    await channels.dong_tat_ca()
    await db.close_db()


app = FastAPI(title="Marketing Agent", version="0.1.0", lifespan=lifespan)


# Đường KHÔNG cần đăng nhập. Danh sách ngắn có chủ đích — mỗi mục là một
# quyết định cân nhắc riêng, không phải một tiện lợi.
_MO = (
    "/api/dang-nhap",     # phải vào được mới đăng nhập được
    "/api/dang-xuat",     # đăng xuất luôn phải chạy, kể cả phiên đã hỏng
)


@app.middleware("http")
async def chan_neu_chua_dang_nhap(request: Request, call_next):
    """
    Chặn mọi /api/* nếu chưa đăng nhập.

    LÀM Ở MIDDLEWARE CHỨ KHÔNG GẮN Depends VÀO TỪNG ENDPOINT — đây là điểm
    quan trọng nhất của cả lớp bảo vệ này.

    Gắn từng endpoint là cơ chế HỎNG-MỞ: hơn bốn mươi endpoint, quên một
    cái là cái đó phơi ra, và không có gì báo. Người thêm endpoint mới tháng
    sau cũng không biết là phải nhớ.

    Middleware là cơ chế HỎNG-ĐÓNG: endpoint mới được bảo vệ theo mặc định,
    và muốn mở thì phải cố ý thêm vào danh sách trên — một việc nhìn thấy
    được khi đọc lại mã.

    `/webhook*` không đi qua đây vì nó không nằm dưới `/api` — nó tự xác
    thực bằng `WEBHOOK_SECRET`, do bên gọi là Chatwoot chứ không phải người.
    `/healthz` để mở để công cụ giám sát hỏi được mà không cần tài khoản.
    """
    duong = request.url.path
    if duong.startswith("/api/") and duong not in _MO:
        nguoi = await xac_thuc.doc_phien(request.cookies.get(TEN_COOKIE, ""))
        if nguoi is None:
            return JSONResponse({"error": "Chưa đăng nhập"}, status_code=401)
        # Gắn vào request để endpoint biết AI đang thao tác — nhật ký ghi
        # tên thật thay vì "nguoi" hay "staff" chung chung.
        request.state.nguoi = nguoi
    return await call_next(request)


app.include_router(api_router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "runtime": dict(runtime.STATE)}


# ---------------------------------------------------------------
#  Webhook — cửa vào của mọi tin nhắn khách
# ---------------------------------------------------------------

@app.post("/webhook")
@app.post("/webhook/{kenh}")
async def webhook(
    request: Request, tasks: BackgroundTasks, kenh: str = "zalocrm"
) -> JSONResponse:
    """
    Cửa vào chung cho mọi kênh đẩy webhook.

    `/webhook` không có tên kênh vẫn về ZaloCRM để cấu hình cũ không hỏng.
    Chatwoot trỏ về `/webhook/chatwoot`.
    """
    # Nhận secret ở header HOẶC ở tham số URL. Cần cả hai vì giao diện
    # webhook của Chatwoot không cho thêm header tuỳ ý — bắt buộc header là
    # khoá cửa luôn kênh đó. Dùng so sánh hằng thời gian để không rò rỉ
    # secret qua thời gian phản hồi.
    if settings.webhook_secret:
        supplied = (request.headers.get("x-webhook-secret")
                    or request.query_params.get("token", ""))
        if not secrets.compare_digest(supplied, settings.webhook_secret):
            return JSONResponse({"ok": False, "error": "sai secret"}, status_code=401)

    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "payload không phải JSON"}, 400)

    inbound = channels.get(kenh).parse(payload)
    if inbound is None:
        return JSONResponse({"ok": True, "skipped": "không phải tin văn bản đến"})

    # Trả 200 ngay để kênh không retry; xử lý ở nền.
    tasks.add_task(handle_inbound, inbound)
    return JSONResponse({"ok": True, "queued": True})


async def _gui_nhu_nguoi(adapter, msg, cid, text: str) -> bool:
    """
    Gửi câu trả lời theo nhịp của một người thật đang nhắn tin.

    Ba việc, theo thứ tự:
      1. Dọn dấu hiệu lộ bot (markdown, chào lại, câu kết sáo rỗng) và tách
         khối dài thành 2-3 tin ngắn — xem agent/core/tu_nhien.py.
      2. Nghỉ giữa các tin đúng khoảng thời gian gõ chừng ấy chữ. Ba tin
         nhảy ra cùng một giây thì dù nội dung có tự nhiên đến mấy, khách
         vẫn biết ngay là máy.
      3. Giữ cờ "đang soạn tin" suốt quá trình để dashboard hiển thị đúng.

    Trả True nếu tin ĐẦU TIÊN đi được. Tin đầu là tin quyết định khách có
    nhận được câu trả lời hay không; các tin sau chỉ bổ sung, hỏng một tin
    sau không có nghĩa là cả câu trả lời thất bại.
    """
    lan_dau = await _la_tin_dau(cid)
    tins = tu_nhien.lam_tu_nhien(text, lan_dau=lan_dau)
    if not tins:
        return False

    ok_dau = False
    for i, phan in enumerate(tins):
        if i and settings.nhip_nguoi_that:
            runtime.mark_busy(cid)
            await asyncio.sleep(tu_nhien.nhip_go(phan))
        kq = await adapter.send_text(msg.conversation_ref, phan)
        if i == 0:
            ok_dau = kq.ok
            if not kq.ok:
                break        # tin đầu hỏng thì gửi tiếp cũng vô nghĩa
    runtime.clear_busy(cid)
    return ok_dau


async def _la_tin_dau(cid) -> bool:
    """Agent đã nói câu nào trong hội thoại này chưa? Quyết định có chào không."""
    r = await db.fetchrow(
        "SELECT count(*) n FROM messages WHERE conversation_id = $1 AND role = 'agent'",
        cid,
    )
    return (r["n"] if r else 0) == 0


async def handle_inbound(msg: InboundMessage) -> None:
    """Toàn bộ luồng xử lý một tin nhắn đến."""
    if await db.seen_webhook(msg.dedupe_key):
        return  # đã xử lý — chống gửi trùng

    conv = await db.fetchrow(
        """
        INSERT INTO conversations
            (channel, external_id, customer_name, customer_ref, nen_tang)
        VALUES ($1,$2,$3,$4,$5)
        ON CONFLICT (channel, external_id) DO UPDATE
            SET customer_name = EXCLUDED.customer_name,
                -- Chỉ ghi đè khi tin mới CÓ nền tảng. Kênh nào không biết
                -- nền tảng gốc thì để nguyên giá trị cũ, không xoá mất.
                nen_tang = coalesce(EXCLUDED.nen_tang, conversations.nen_tang),
                updated_at = now()
        RETURNING *
        """,
        msg.channel,
        msg.conversation_ref,
        msg.customer_name,
        msg.customer_ref,
        (msg.meta or {}).get("nen_tang_goc"),
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
    # Và báo luôn cho kênh, để KHÁCH cũng thấy — không chỉ người vận hành.
    # Màn hình im lặng rồi bỗng hiện ra một đoạn dài là dấu hiệu máy trả
    # lời; thấy "đang soạn tin" thì cảm giác hoàn toàn khác.
    adapter = channels.get(msg.channel)
    with suppress(Exception):
        await adapter.bao_dang_go(msg.conversation_ref, True)
    try:
        reply = await brain.respond(
            conversation_id=cid, history=history, question=msg.text,
            customer_ref=msg.customer_ref, channel=msg.channel,
        )
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
        with suppress(Exception):
            await adapter.bao_dang_go(msg.conversation_ref, False)

    # Chế độ assist: soạn nhưng KHÔNG gửi, chờ người duyệt.
    auto_send = runtime.mode() == "auto" and not reply.escalate
    delivered = False
    if auto_send and await adapter.can_send_now(msg.conversation_ref):
        delivered = await _gui_nhu_nguoi(adapter, msg, cid, reply.text)

        # Ảnh đi SAU lời, không đi trước. Nhận ảnh trước khi biết đó là gì
        # thì khách phải tự đoán; nhận lời trước rồi thấy ảnh là đúng thứ
        # tự nhiên của một người bán hàng.
        for anh in reply.anh_can_gui:
            with suppress(Exception):
                await adapter.send_file(
                    msg.conversation_ref, anh["duong_dan"], caption=anh["ten"]
                )

    # Chuyển người mà không nói gì với khách là để họ ngồi im không biết có
    # ai thấy tin của mình chưa. Nhân viên thì đã có việc trong hàng chờ,
    # còn khách thì chịu toàn bộ khoảng lặng đó.
    #
    # Gửi câu CỐ ĐỊNH trong cấu hình chứ không gửi lời model vừa sinh ra:
    # lúc chuyển người là lúc agent đã tự nhận không đủ thẩm quyền, nên đó
    # chính là lúc không nên để nó tự chọn chữ. Câu cố định không thể chứa
    # lời khuyên, không thể hứa gì, và không thể vi phạm quảng cáo.
    #
    # Chỉ ở chế độ auto. Chế độ assist thì người duyệt mọi thứ, tự gửi thêm
    # một câu là đi ngược ý nghĩa của chế độ đó.
    elif reply.escalate and runtime.mode() == "auto":
        # Câu báo chuyển người là tin QUAN TRỌNG NHẤT trong luồng này: khách
        # vừa hỏi một chuyện agent không đủ thẩm quyền trả lời, và nếu không
        # nhận được gì thì họ ngồi chờ trong im lặng. Đã bắt gặp thật trên
        # Chatwoot: hai hội thoại về retinol khi mang thai, khách không nhận
        # được dòng nào — chỉ có ghi chú nội bộ mà họ không nhìn thấy.
        #
        # Trước đây bọc trong `suppress(Exception)`: gửi hỏng thì nuốt luôn,
        # không ai biết. Nay hỏng vẫn không làm sập luồng, nhưng PHẢI để lại
        # dấu vết để người trực còn biết mà nhắn tay.
        try:
            if await adapter.can_send_now(msg.conversation_ref):
                kq = await adapter.send_text(
                    msg.conversation_ref, settings.tin_chuyen_nguoi
                )
                if not getattr(kq, "ok", True):
                    await db.log_event(
                        "escalate.bao_that_bai", ref_id=cid,
                        ly_do=str(getattr(kq, "error", ""))[:200],
                    )
            else:
                await db.log_event(
                    "escalate.khong_gui_duoc", ref_id=cid,
                    ly_do="kênh từ chối gửi lúc này (ngoài cửa sổ cho phép)",
                )
        except Exception as exc:  # noqa: BLE001 — không được làm sập luồng
            await db.log_event(
                "escalate.bao_that_bai", ref_id=cid,
                ly_do=f"{type(exc).__name__}: {exc}"[:200],
            )

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
        # Bàn giao NHÌN THẤY ĐƯỢC ở phía kênh. Ghi vào CSDL của mình thôi
        # thì nhân viên đang làm việc trong hộp thư của kênh không thấy gì:
        # hội thoại trông như đã xử lý xong, khách ngồi chờ, không ai biết.
        # Bàn giao chỉ là bàn giao khi bên nhận nhìn thấy.
        with suppress(Exception):
            await adapter.bao_chuyen_nguoi(
                msg.conversation_ref,
                reply.escalate_reason or "agent không xử lý được",
                tom_tat=msg.text[:200],
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

# Video tĩnh — n8n và Instagram Graph API cần TẢI ĐƯỢC file qua HTTP,
# không nhận đường dẫn ổ đĩa. Phải mount TRƯỚC "/" vì mount "/" nuốt hết.
_VIDEO_DIR = settings.video_out_path
if _VIDEO_DIR.exists():
    app.mount("/media/videos",
              StaticFiles(directory=str(_VIDEO_DIR)), name="media-videos")

if DASHBOARD_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")
