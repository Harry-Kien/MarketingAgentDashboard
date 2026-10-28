"""
Luồng xử lý MỘT tin nhắn đến, mọi kênh — TRẠM B1 trong bản đồ ba chặng.

Chặng giữa là `agent/core/agent.py:respond()`; chặng cuối là outbox worker.

VÌ SAO TÁCH KHỎI main.py
------------------------
Trước 23.10.2026 hàm này nằm trong `agent/main.py`, nên năm bộ webhook ở
`agent/api/` phải `from agent.main import handle_inbound` TRONG thân hàm để
tránh import vòng (main import router của chúng). Import trong thân hàm là
lỗi chờ nổ lúc chạy, không phải lúc khởi động — và test phải vá `main` để
chặn một hàm mà webhook lấy từ chỗ khác. Giờ có MỘT chỗ để gọi và MỘT chỗ
để vá: `xu_ly_tin_vao.handle_inbound`.
"""
from __future__ import annotations

import uuid
from contextlib import suppress

from agent import cau_hinh_dong, db, runtime
from agent.channels import registry as channels
from agent.channels.base import InboundMessage
from agent.config import settings
from agent.core import agent as brain
from agent.core import agent_bat, agent_ho_so, anh_khach, cong_viec, gio_lam_viec, tu_nhien
from agent.omnichannel import giai_quyet, thong_bao_ai, tu_dong
from agent.omnichannel.inbox_service import InboxService, PostgresInboxRepository
from agent.omnichannel.outbound_service import (
    OutboundService,
    PostgresOutboundRepository,
    QueuedOutbound,
    handover_idempotency_key,
)

HISTORY_TURNS = 12


async def _queue_ai_text(
    cid: uuid.UUID,
    text: str,
    idempotency_key: str,
    metadata: dict | None = None,
) -> QueuedOutbound:
    return await OutboundService(PostgresOutboundRepository()).queue_text(
        conversation_id=cid,
        role="agent",
        text=text,
        idempotency_key=idempotency_key,
        metadata=metadata,
    )


async def _queue_ai_file(
    cid: uuid.UUID,
    path: str,
    caption: str,
    idempotency_key: str,
) -> QueuedOutbound:
    return await OutboundService(PostgresOutboundRepository()).queue_file(
        conversation_id=cid,
        role="agent",
        path=path,
        caption=caption,
        idempotency_key=idempotency_key,
    )


async def _gui_nhu_nguoi(
    _adapter,
    msg,
    cid,
    text: str,
    metadata: dict | None = None,
) -> list[QueuedOutbound]:
    """
    Gửi câu trả lời theo nhịp của một người thật đang nhắn tin.

    Ba việc, theo thứ tự:
      1. Dọn dấu hiệu lộ bot (markdown, chào lại, câu kết sáo rỗng) và tách
         khối dài thành 2-3 tin ngắn — xem agent/core/tu_nhien.py.
      2. Nghỉ giữa các tin đúng khoảng thời gian gõ chừng ấy chữ. Ba tin
         nhảy ra cùng một giây thì dù nội dung có tự nhiên đến mấy, khách
         vẫn biết ngay là máy.
      3. Giữ cờ "đang soạn tin" suốt quá trình để dashboard hiển thị đúng.

    Mỗi phần được ghi message + outbox trong cùng transaction. Provider chỉ
    được gọi bởi worker sau commit; vì thế kết quả ở đây là ``queued``, chưa
    phải ``delivered``.
    """
    lan_dau = await _la_tin_dau(cid)
    # Công tắc `NHIP_NGUOI_THAT` phải THẬT SỰ tắt được.
    #
    # Trước đây nó được khai trong `config.py` kèm chú thích "tắt đi thì gửi
    # một cục" — nhưng không ai đọc, nên tắt cũng không có tác dụng gì. Một
    # công tắc nói dối tệ hơn không có công tắc: người vận hành tưởng đã tắt
    # rồi đi tìm nguyên nhân ở chỗ khác.
    tins = (tu_nhien.lam_tu_nhien(text, lan_dau=lan_dau)
            if settings.nhip_nguoi_that else [text.strip()])
    tins = [t for t in tins if t]
    if not tins:
        return []

    queued: list[QueuedOutbound] = []
    for i, phan in enumerate(tins):
        queued.append(
            await _queue_ai_text(
                cid,
                phan,
                f"ai:{msg.dedupe_key}:part:{i}",
                metadata if i == 0 else None,
            )
        )
    runtime.clear_busy(cid)
    return queued


async def _la_tin_dau(cid) -> bool:
    """Agent đã nói câu nào trong hội thoại này chưa? Quyết định có chào không."""
    r = await db.fetchrow(
        "SELECT count(*) n FROM messages WHERE conversation_id = $1 AND role = 'agent'",
        cid,
    )
    return (r["n"] if r else 0) == 0


async def _ingest_inbound(msg: InboundMessage):
    """Commit inbox trước khi AI hoặc provider bên ngoài được gọi."""
    return await InboxService(PostgresInboxRepository()).ingest(msg)


async def _xu_ly_binh_luan(msg, cid: uuid.UUID) -> None:
    await db.execute(
        "UPDATE conversations SET status = 'escalated', mode = 'human', "
        "version = version + 1, updated_at = now() WHERE id = $1", cid)
    meta = msg.meta or {}
    if not meta.get("co_sdt") or cau_hinh_dong.lay("AN_BINH_LUAN_CO_SDT") != "bat":
        return
    # Ẩn là hành động CÔNG KHAI trên Trang của khách hàng — chỉ khi cửa hàng
    # bật. Hỏng thì ghi nhật ký cảnh báo, không nuốt: số điện thoại của
    # khách đang nằm công khai, người trực cần biết để ẩn tay.
    try:
        ad = await channels.get_for_account(msg.account_id)
        kq = await ad.an_binh_luan(str(meta.get("comment_id")))
        ok, chi_tiet = kq.ok, kq.detail
    except Exception as exc:  # noqa: BLE001 — ghi lại, không làm rơi tin
        ok, chi_tiet = False, f"{type(exc).__name__}: {exc}"[:200]
    await db.log_event(
        "binh_luan.da_an" if ok else "binh_luan.an_that_bai", ref_id=cid,
        comment_id=meta.get("comment_id"), chi_tiet=chi_tiet or None)


async def handle_inbound(msg: InboundMessage) -> None:
    """Toàn bộ luồng xử lý một tin nhắn đến."""
    # ĐỌC: ══ ĐIỂM VÀO CỦA MỌI TIN NHẮN, MỌI KÊNH ═══════════════════════════
    # ĐỌC: Đọc hàm này TRƯỚC khi đọc lifespan(). Nó là một đầu của luồng;
    # ĐỌC: agent/core/agent.py:respond() là phần giữa; outbox worker là đầu kia.
    # ĐỌC:
    # ĐỌC: Địa chỉ trong bản đồ ba chặng: TRẠM B1. Bản đồ đầy đủ, gồm cả
    # ĐỌC: chặng cài kỹ năng, ở agent/ky_nang/__init__.py.
    # ĐỌC:
    # ĐỌC: Thứ tự sáu việc, và thứ tự này quan trọng:
    # ĐỌC:   1. _ingest_inbound  → chống trùng, lưu tin, COMMIT
    # ĐỌC:   2. kiểm standby / mode=human → người thật đang phụ trách thì đứng ngoài
    # ĐỌC:   3. ảnh KHÔNG kèm chữ → chuyển người NGAY, mô hình không được nhìn
    # ĐỌC:   4. _history(cid)    → lấy lượt trước, BỎ tin vừa lưu
    # ĐỌC:   5. brain.respond()  → cửa vào lõi agent
    # ĐỌC:   6. _gui_nhu_nguoi   → tách 2–3 tin, ghi message + outbox CÙNG transaction
    # ĐỌC:
    # ĐỌC: Nguyên tắc xuyên suốt: COMMIT XONG MỚI GỌI RA NGOÀI. App chết đúng
    # ĐỌC: giây đó thì tin vẫn còn, và worker sẽ gửi lại sau.
    ingested = await _ingest_inbound(msg)
    if ingested.duplicate:
        return
    if ingested.conversation_id is None:
        raise RuntimeError("inbox ingest không trả conversation_id")
    cid: uuid.UUID = ingested.conversation_id
    conv = {
        "id": cid,
        "status": ingested.conversation_status or "auto",
        "mode": ingested.conversation_mode or "auto",
    }

    # TIN VỀ QUA `standby` — người thật đang phụ trách hội thoại này.
    #
    # Meta đã chuyển quyền cho Page Inbox, nghĩa là nhân viên đang trả lời
    # khách ở đó. Tin vẫn phải LƯU để hồ sơ khách không đứt một đoạn, nhưng
    # agent tuyệt đối không được nói chen vào.
    #
    # Đặt cờ `escalated` luôn: nếu hội thoại chưa được đánh dấu (ví dụ quyền
    # bị app khác giành, không đi qua đường chuyển người của ta) thì đây là
    # lần duy nhất hệ thống biết được điều đó.
    if (msg.meta or {}).get("standby"):
        await db.execute(
            "UPDATE conversations SET status = 'escalated', mode = 'human', "
            "version = version + 1, updated_at = now() "
            "WHERE id = $1", cid,
        )
        return

    # BÌNH LUẬN dưới bài đăng: lưu, chuyển người, ẩn nếu có SĐT.
    #
    # Agent KHÔNG tự trả lời: Meta chỉ cho trả lời riêng MỘT tin mỗi bình
    # luận, còn agent tách câu trả lời thành 2–3 tin — tin thứ hai trở đi
    # chết trong outbox. Xem agent/channels/binh_luan_meta.py.
    if (msg.meta or {}).get("loai") == "binh_luan":
        await _xu_ly_binh_luan(msg, cid)
        return

    # Hội thoại ĐÃ GIẢI QUYẾT nhận tin mới: hoặc là điểm CSAT đang chờ (ghi
    # điểm, đóng lại, agent đứng ngoài), hoặc là một lượt phục vụ mới (mở
    # lại, trả cho agent). Xem agent/omnichannel/giai_quyet.py.
    # Chỉ hội thoại đang ĐÓNG mới cần xét: không thêm truy vấn nào vào
    # đường đi của tin thường.
    if conv["status"] == "closed":
        if await giai_quyet.ghi_diem_neu_la_csat(cid, msg.text or ""):
            return
        if await giai_quyet.mo_lai_neu_da_giai_quyet(cid):
            conv["status"], conv["mode"] = "auto", "auto"

    # QUY TẮC TỰ ĐỘNG của cửa hàng (agent/omnichannel/tu_dong.py) — chạy
    # TRƯỚC agent: quy tắc "chuyển người" phải chặn được agent ngay ở tin
    # này, không phải từ tin sau. Hỏng thì tự ghi nhật ký và không chặn gì.
    tu_dong_kq = await tu_dong.chay_tin_khach(
        msg, cid, nguoi_dang_tiep=conv.get("mode") == "human")
    if tu_dong_kq.dung_agent:
        return

    # Agent có được trả lời hội thoại này không — ba nấc: công tắc toàn cục,
    # bật/tắt theo TÀI KHOẢN KÊNH, và người đã tiếp quản hội thoại.
    #
    # TẮT KHÔNG PHẢI LÀ IM. Hội thoại chuyển sang người VÀ sinh một công
    # việc. Bỏ vế thứ hai thì "agent là tuỳ chọn" biến thành "kênh chết im
    # lặng": tin vào, không ai trả lời, và dashboard vẫn xanh vì không có gì
    # hỏng cả.
    cho_phep = await agent_bat.agent_duoc_tra_loi(msg.account_id, conv)
    if not cho_phep.duoc:
        await db.execute(
            "UPDATE conversations SET status = 'escalated', mode = 'human', "
            "version = version + 1, updated_at = now() "
            "WHERE id = $1",
            cid,
        )
        # Hội thoại người đã cầm rồi thì KHÔNG sinh việc mới: họ đang làm,
        # và một việc nữa chỉ làm loãng danh sách. Chỉ sinh khi agent bị
        # chặn vì cấu hình — đó mới là lúc chưa ai biết mình phải vào.
        if "đã do người tiếp quản" not in cho_phep.ly_do:
            await db.log_event("conversation.escalated", ref_id=cid,
                               reason=cho_phep.ly_do)
            # Tên khách: `tao_tu_chuyen_nguoi` tự đọc từ hội thoại.
            await cong_viec.tao_tu_chuyen_nguoi(cid, ly_do=cho_phep.ly_do)
        return

    # KHÁCH ĐÒI GẶP NGƯỜI -> chuyển ngay, không qua model. Câu thông báo AI
    # (thong_bao_ai.py) hứa "nhắn gặp nhân viên là gặp người"; lời hứa ấy
    # giữ bằng mã — NĐ 356/2025 Điều 10 khoản 3 cho khách quyền không bị xử
    # lý tự động, và để model tự hiểu là có lúc nó "dạ em hỗ trợ mình luôn".
    if thong_bao_ai.khach_doi_gap_nguoi(msg.text or ""):
        await db.execute(
            "UPDATE conversations SET status = 'escalated', mode = 'human', "
            "version = version + 1, outcome = 'escalated', updated_at = now() "
            "WHERE id = $1", cid,
        )
        await db.log_event("conversation.escalated", ref_id=cid, reason="khách đòi gặp nhân viên")
        await cong_viec.tao_tu_chuyen_nguoi(cid, ly_do="Khách đòi gặp nhân viên.")
        # Báo khách ở MỌI chế độ, kể cả Gợi ý: câu báo là câu cố định trong
        # cấu hình, không phải lời model — và khách vừa đòi gặp người mà
        # nhận lại im lặng là đúng thứ vừa hứa sẽ không xảy ra.
        with suppress(Exception):
            ad = await channels.get_for_account(msg.account_id)
            await bao_nhan_vien_tiep_quan(ad, msg.conversation_ref, cid, "khách đòi gặp nhân viên")
            await bao_khach_dang_chuyen_nguoi(ad, msg.conversation_ref, cid)
        return

    # KHÁCH GỬI ẢNH KHÔNG KÈM CHỮ -> CHUYỂN NGƯỜI, KHÔNG ĐOÁN
    # -------------------------------------------------------
    # Model đang chạy nhìn được ảnh, nhưng đó không phải lý do để nó trả
    # lời. Người ta chụp chỗ da đang có vấn đề thay vì tả bằng lời — và
    # nhìn ảnh da rồi khuyên dùng gì chính là chẩn đoán, đúng việc mà
    # prompt đã cấm và `_bat_buoc_chuyen` đã chặn khi khách MÔ TẢ bằng chữ.
    # Chặn chữ mà bỏ lọt ảnh thì chốt tuân thủ chỉ là hình thức: khách nào
    # gửi ảnh là đi vòng qua được.
    #
    # Ảnh CÓ kèm chữ thì đi đường thường: câu chữ cho agent đủ căn cứ để
    # biết mình có đủ thẩm quyền hay không, và các lớp lưới cũ vẫn chạy.
    if msg.attachments and not msg.text.strip():
        await db.execute(
            "UPDATE conversations SET status = 'escalated', mode = 'human', "
            "version = version + 1, "
            "outcome = 'escalated', updated_at = now() WHERE id = $1", cid,
        )
        await db.log_event("conversation.escalated", ref_id=cid,
                           reason="khách gửi ảnh không kèm chữ")
        # Một dòng nhật ký không phải một người chịu trách nhiệm. Không
        # tạo việc thì chuyện này chỉ được nhớ tới nếu tình cờ có ai mở
        # đúng hội thoại — và "tình cờ" không phải một cơ chế.
        await cong_viec.tao_tu_chuyen_nguoi(
            cid, ly_do="Khách gửi ảnh không kèm chữ — agent không đoán.")
        with suppress(Exception):
            await adapter_bao_nguoi(msg, cid)
        return

    # Agent SẮP trả lời: báo khách đang nói với trợ lý AI (một lần mỗi hội
    # thoại). Đặt ở đây chứ không sớm hơn: các nhánh phía trên đều là lúc
    # NGƯỜI tiếp khách, và "em là trợ lý AI" khi ấy là nói sai.
    await thong_bao_ai.gui_neu_chua(msg, cid)

    history = await _history(cid)

    runtime.mark_busy(cid)          # dashboard vẽ bong bóng "đang soạn tin"
    # Và báo luôn cho kênh, để KHÁCH cũng thấy — không chỉ người vận hành.
    # Màn hình im lặng rồi bỗng hiện ra một đoạn dài là dấu hiệu máy trả
    # lời; thấy "đang soạn tin" thì cảm giác hoàn toàn khác.
    adapter = await channels.get_for_account(msg.account_id)
    with suppress(Exception):
        await adapter.bao_dang_go(msg.conversation_ref, True)
    try:
        # Agent phải BIẾT là có ảnh. Không nói thì nó trả lời câu chữ như
        # thể ảnh không tồn tại — khách gửi ảnh kèm "cái này còn hàng
        # không ạ?" mà nhận về câu hỏi lại "mình muốn hỏi sản phẩm nào ạ?".
        # Agent NHÌN ĐƯỢC ảnh khách gửi.
        #
        # Bản trước nói thẳng với model "[bạn KHÔNG xem được nội dung ảnh]" —
        # trung thực và đúng lúc đó, nhưng nghĩa là mọi ca khách gửi ảnh đều
        # phải chuyển người: ảnh sản phẩm muốn mua, ảnh hàng nhận được bị vỡ,
        # ảnh màn hình chuyển khoản.
        #
        # Tải ảnh hỏng thì rơi về đúng hành vi cũ, không làm đứt lượt trả
        # lời: tin nhắn của khách mới là việc chính.
        cau_hoi = msg.text
        khoi_anh: list[dict] = []
        if msg.attachments:
            async def _ghi_loi_anh(ly_do: str) -> None:
                await db.log_event("anh_khach.tai_that_bai", ref_id=cid,
                                   ly_do=ly_do)

            khoi_anh = await anh_khach.lay_khoi_anh(
                msg.attachments, ghi_loi=_ghi_loi_anh)
            if not khoi_anh:
                cau_hoi = (f"[khách gửi kèm {len(msg.attachments)} tệp nhưng "
                           f"hệ thống KHÔNG tải về xem được] {msg.text}")

        # Hồ sơ agent của KÊNH này. Chưa gán thì `cho_kenh` trả hồ sơ mặc
        # định, mang đúng ngưỡng toàn cục — nên không cần rẽ nhánh ở đây.
        ho_so = await agent_ho_so.cho_kenh(msg.account_id)
        reply = await brain.respond(
            conversation_id=cid, history=history, question=cau_hoi,
            customer_ref=msg.customer_ref, channel=msg.channel,
            anh=khoi_anh or None, ho_so=ho_so,
        )
    except Exception as exc:  # noqa: BLE001 — suy giảm êm, không bao giờ im lặng
        await db.execute(
            "UPDATE conversations SET status = 'escalated', mode = 'human', "
            "version = version + 1, updated_at = now() "
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
    queued_parts: list[QueuedOutbound] = []
    if auto_send and await adapter.can_send_now(msg.conversation_ref):
        metadata = {
            "grounded": reply.grounded,
            "confidence": reply.confidence,
            "sources": reply.sources,
            "model": reply.model,
            "tokens_in": reply.tokens_in,
            "tokens_out": reply.tokens_out,
            "cache_read": reply.cache_read,
            "cost_usd": reply.cost_usd,
            "latency_ms": reply.latency_ms,
        }
        try:
            queued_parts = await _gui_nhu_nguoi(
                adapter, msg, cid, reply.text, metadata
            )
        except Exception as exc:  # noqa: BLE001 — giữ draft để người gửi tay
            await db.log_event(
                "outbox.enqueue_error",
                ref_id=cid,
                error=f"{type(exc).__name__}: {exc}"[:500],
            )
            queued_parts = []

        # Ảnh đi SAU lời, không đi trước. Nhận ảnh trước khi biết đó là gì
        # thì khách phải tự đoán; nhận lời trước rồi thấy ảnh là đúng thứ
        # tự nhiên của một người bán hàng.
        for i, anh in enumerate(reply.anh_can_gui):
            try:
                await _queue_ai_file(
                    cid,
                    anh["duong_dan"],
                    anh["ten"],
                    f"ai:{msg.dedupe_key}:file:{i}",
                )
            except Exception as exc:  # noqa: BLE001 — một ảnh hỏng không chặn ảnh sau
                await db.log_event(
                    "anh.queue_that_bai", ref_id=cid, ten=anh.get("ten", ""),
                    ly_do=f"{type(exc).__name__}: {exc}"[:200],
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
        await bao_khach_dang_chuyen_nguoi(adapter, msg.conversation_ref, cid)

    # Khi đã enqueue, OutboundService đã tạo message cùng transaction với job.
    # Chỉ lưu bản nháp ở đây cho assist/escalate hoặc khi enqueue hỏng.
    stored_draft = not queued_parts
    if stored_draft:
        await db.execute(
            """
            INSERT INTO messages
                (conversation_id, role, content, delivered, direction,
                 delivery_status, grounded, confidence, sources, model,
                 tokens_in, tokens_out, cache_read, cost_usd, latency_ms)
            VALUES (
                $1,'agent',$2,false,'outbound','draft',$3,$4,$5,$6,$7,$8,$9,$10,$11
            )
            """,
            cid,
            reply.text,
            reply.grounded,
            reply.confidence,
            reply.sources,
            reply.model,
            reply.tokens_in,
            reply.tokens_out,
            reply.cache_read,
            reply.cost_usd,
            reply.latency_ms,
        )

    status = (
        "escalated" if reply.escalate else ("auto" if queued_parts else "assist")
    )
    await db.execute(
        """
        UPDATE conversations
        SET cost_usd = cost_usd + $2,
            msg_count = msg_count + $4,
            status = $3,
            mode = CASE
                WHEN $3 = 'escalated' THEN 'human'
                WHEN $3 = 'assist' THEN 'assist'
                ELSE mode
            END,
            version = version + 1,
            outcome = CASE WHEN $3 = 'escalated' THEN 'escalated' ELSE outcome END,
            updated_at = now()
        WHERE id = $1
        """,
        cid,
        reply.cost_usd,
        status,
        1 if stored_draft else 0,
    )

    if reply.escalate:
        await db.log_event(
            "conversation.escalated", ref_id=cid, reason=reply.escalate_reason
        )
        await cong_viec.tao_tu_chuyen_nguoi(
            cid, ly_do=reply.escalate_reason or "agent không xử lý được")
        await bao_nhan_vien_tiep_quan(
            adapter, msg.conversation_ref, cid,
            reply.escalate_reason or "agent không xử lý được",
            tom_tat=msg.text[:200],
        )


async def adapter_bao_nguoi(msg: InboundMessage, cid: uuid.UUID) -> None:
    """
    Báo cả hai phía khi chuyển người: khách nhận một câu, nhân viên nhận
    ghi chú trong hộp thư của kênh.

    Tách ra dùng chung vì nhánh "ảnh không kèm chữ" thoát sớm, không đi qua
    đoạn báo chuyển người ở cuối `handle_inbound`. Không gọi ở đây thì khách
    gửi ảnh xong nhận lại đúng sự im lặng — tức là vẫn bị bỏ rơi, chỉ khác
    là nay có bản ghi trong CSDL để sau này truy ra.
    """
    adapter = await channels.get_for_account(msg.account_id)
    await bao_nhan_vien_tiep_quan(
        adapter, msg.conversation_ref, cid, "khách gửi ảnh, cần người xem"
    )
    if runtime.mode() == "auto":
        await bao_khach_dang_chuyen_nguoi(adapter, msg.conversation_ref, cid)


async def bao_khach_dang_chuyen_nguoi(adapter, conversation_ref: str, cid) -> None:
    """
    Nói với KHÁCH rằng việc đang được chuyển cho người. MỘT bản, hai lối gọi.

    VÌ SAO GỘP LẠI THAY VÌ VÁ TỪNG CHỖ
    ----------------------------------
    Trước đây hai nhánh tự viết lấy đoạn này: nhánh tin có chữ, và nhánh tin
    CHỈ CÓ ẢNH. Nhánh có chữ từng gửi hỏng mà nuốt luôn — bắt gặp thật trên
    Chatwoot, hai hội thoại hỏi retinol khi mang thai, khách không nhận được
    dòng nào — nên nó được sửa để ghi nhật ký. Nhánh ảnh thì KHÔNG ai sửa,
    và nó nằm im với `suppress(Exception)` câm thêm một thời gian nữa.

    Đó không phải lỗi của người sửa. Đó là điều luôn xảy ra với hai bản sao
    của cùng một việc: bản ít người đọc hơn sẽ mục. Nên cách sửa đúng không
    phải vá bản thứ hai, mà là bỏ nó đi.

    Câu gửi đi là câu CỐ ĐỊNH trong cấu hình, không phải lời model vừa sinh:
    lúc chuyển người là lúc agent đã tự nhận không đủ thẩm quyền, nên đó
    chính là lúc không nên để nó tự chọn chữ. Câu cố định không thể chứa lời
    khuyên, không thể hứa gì, không thể vi phạm luật quảng cáo.

    Hỏng thì KHÔNG làm sập luồng, nhưng PHẢI để lại dấu vết — người trực còn
    biết mà nhắn tay. Im lặng ở đây nghĩa là khách ngồi chờ một câu trả lời
    không bao giờ tới, và không ai trong nhà biết điều đó đang xảy ra.
    """
    try:
        if not await adapter.can_send_now(conversation_ref):
            await db.log_event(
                "escalate.khong_gui_duoc", ref_id=cid,
                ly_do="kênh từ chối gửi lúc này (ngoài cửa sổ cho phép)",
            )
            return
        # Câu đổi theo giờ: trong giờ thì "sẽ nhắn lại sớm" là thật; ngoài
        # giờ phải nói rõ mấy giờ có người, vì lúc 2 giờ sáng chữ "sớm" là
        # một lời hứa không ai giữ được.
        await _queue_handover_notice(cid, gio_lam_viec.tin_chuyen_nguoi())
    except Exception as exc:  # noqa: BLE001 — không được làm sập luồng
        await db.log_event(
            "escalate.bao_that_bai", ref_id=cid,
            ly_do=f"{type(exc).__name__}: {exc}"[:200],
        )


async def _queue_handover_notice(cid: uuid.UUID, text: str) -> QueuedOutbound:
    conversation = await db.fetchrow(
        "SELECT version FROM conversations WHERE id = $1",
        cid,
    )
    version = int(conversation["version"]) if conversation else 1
    return await OutboundService(PostgresOutboundRepository()).queue_text(
        conversation_id=cid,
        role="system",
        text=text,
        idempotency_key=handover_idempotency_key(cid, version),
    )


async def bao_nhan_vien_tiep_quan(
    adapter, conversation_ref: str, cid, ly_do: str, tom_tat: str = ""
) -> None:
    """
    Bàn giao nhìn thấy được ở phía kênh — và biết được khi nó hỏng.

    Ghi 'escalated' vào CSDL của mình thôi thì nhân viên đang làm việc trong
    hộp thư của kênh không thấy gì: hội thoại trông như đã xử lý xong, khách
    ngồi chờ, không ai biết. Bàn giao chỉ là bàn giao khi bên nhận nhìn
    thấy — nên khi bước này hỏng, đó là hàng chờ đang rò rỉ, không phải một
    chi tiết trang trí.
    """
    try:
        await adapter.bao_chuyen_nguoi(conversation_ref, ly_do, tom_tat=tom_tat)
    except Exception as exc:  # noqa: BLE001 — không được làm sập luồng
        await db.log_event(
            "escalate.bao_kenh_that_bai", ref_id=cid,
            ly_do=f"{type(exc).__name__}: {exc}"[:200],
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
