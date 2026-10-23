"""
API hội thoại của dashboard: danh sách, chi tiết, gửi tin/tệp, duyệt nháp,
tiếp quản, ghim nick. Mọi đường gửi đi qua chốt phạm vi kênh, mức tầm nhìn
và cửa sổ nhắn tin (phu_thuoc.py).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import db, runtime
from agent.channels import registry as channels
from agent.channels import zalocrm_accounts as zalo_acc
from agent.core.cham_mot_luot import tu_cam_hai_dang
from agent.omnichannel.outbound_service import (
    ConversationNotFound,
    OutboundMessageNotFound,
    OutboundService,
    PostgresOutboundRepository,
)
from agent.omnichannel.routing import (
    AssignmentDenied,
    ConversationConflict,
    ConversationNotFound as RoutingConversationNotFound,
    ConversationRoutingService,
    PostgresRoutingRepository,
)

from .phu_thuoc import (
    _nguoi_id,
    _num,
    _xem_tat_ca_kenh,
    _xet_cua_so_hoac_409,
    bat_buoc_dang_nhap,
    can_quyen,
    chan_neu_khong_duoc_tra_loi,
    chan_neu_ngoai_kenh,
)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------
#  Hội thoại
# ---------------------------------------------------------------

@router.get("/conversations")
async def list_conversations(status: str | None = None, limit: int = 60, _quyen: dict = Depends(can_quyen("hoi_thoai.doc"))) -> list[dict]:
    # $1 = xem mọi kênh, $2 = người hỏi. Cùng mệnh đề với `inbox.py` — xem
    # `chan_neu_ngoai_kenh` về vì sao route cũ cũng phải lọc.
    sql = """
        SELECT c.*,
               (SELECT content FROM messages m WHERE m.conversation_id = c.id
                ORDER BY created_at DESC LIMIT 1) AS last_message
        FROM conversations c
        -- hội thoại phòng thử không phải khách
        WHERE c.channel <> 'phong_thu'
          AND ($1 OR EXISTS (SELECT 1 FROM account_memberships am
                             WHERE am.account_id = c.account_id AND am.user_id = $2))
    """
    args: list = [_xem_tat_ca_kenh(_quyen), uuid.UUID(str(_quyen["id"]))]
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
        sql += " AND c.status IN ('assist', 'escalated')"
    elif status and status != "all":
        args.append(status)
        sql += f" AND c.status = ${len(args)}"

    # THỨ TỰ: hàng đợi trực xếp NGƯỢC với mọi màn hình khác.
    #
    # Mọi chỗ khác trong dashboard là dòng thời gian — mới nhất lên đầu,
    # đúng như người ta mong đợi. Nhưng "Chờ người xử lý" không phải dòng
    # thời gian, nó là HÀNG ĐỢI. Xếp mới-nhất-trước ở đây có nghĩa: khách
    # vừa nhắn xong được phục vụ trước, còn người đã ngồi đợi bốn mươi phút
    # bị đẩy xuống đáy màn hình — và khi có nhiều hơn một trang thì rơi hẳn
    # khỏi danh sách.
    #
    # Đây đúng là cách bảy khách biến mất khỏi khung trực lần trước, chỉ
    # khác nguyên nhân: lần đó do lọc thiếu trạng thái, lần này do thứ tự
    # và mức cắt. Ai chờ lâu nhất phải nằm trên cùng.
    thu_tu = "ASC" if status == "can_nguoi" else "DESC"
    sql += f" ORDER BY c.updated_at {thu_tu} LIMIT {int(limit)}"

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
            # Chờ bao lâu rồi, tính sẵn ở đây thay vì để trình duyệt tự trừ:
            # máy của người trực có thể lệch giờ, và một hàng đợi mà con số
            # chờ sai thì tệ hơn một hàng đợi không có con số nào.
            "cho_bao_lau_phut": max(
                0,
                int((datetime.now(timezone.utc) - r["updated_at"]).total_seconds() // 60),
            ),
            "last_message": r["last_message"],
            "typing": runtime.is_busy(r["id"]),
        }
        for r in rows
    ]


@router.get("/conversations/{conv_id}")
async def conversation_detail(conv_id: str, _quyen: dict = Depends(can_quyen("hoi_thoai.doc"))) -> dict:
    cid = uuid.UUID(conv_id)
    await chan_neu_ngoai_kenh(cid, _quyen)
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
                # Ảnh khách gửi. Đường dẫn đã trỏ qua proxy `/tich-hop/
                # chatwoot/...` ngay từ lúc đọc webhook, nên dashboard hiện
                # được bằng chính phiên đăng nhập của nó — người trực không
                # phải đăng nhập Chatwoot lần nữa chỉ để xem một tấm ảnh.
                "attachments": m.get("attachments") or [],
                "cost": round(_num(m["cost_usd"]), 6),
                "latency_ms": m["latency_ms"],
                "at": m["created_at"].isoformat(),
            }
            for m in msgs
        ],
    }


class SendBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


async def _queue_staff_reply(cid: uuid.UUID, body: SendBody,
                             the: str | None = None,
                             gui_boi: uuid.UUID | None = None):
    key = body.idempotency_key or f"staff:{uuid.uuid4()}"
    return await OutboundService(PostgresOutboundRepository()).queue_text(
        conversation_id=cid,
        role="staff",
        text=body.text,
        idempotency_key=key,
        the=the,
        gui_boi=gui_boi,
    )


@router.post("/conversations/{conv_id}/send")
async def staff_send(conv_id: str, body: SendBody,
                     nguoi: dict = Depends(can_quyen("hoi_thoai.tra_loi"))) -> dict:
    """Ghi tin nhân viên vào outbox; worker mới là nơi gọi provider."""
    cid = uuid.UUID(conv_id)
    await chan_neu_khong_duoc_tra_loi(cid, nguoi)
    the = await _xet_cua_so_hoac_409(cid)   # xet_tin_nhan_vien
    try:
        queued = await _queue_staff_reply(cid, body, the, _nguoi_id(nguoi))
    except ConversationNotFound as exc:
        raise HTTPException(404, "Không thấy hội thoại") from exc
    return {
        "ok": True,
        "queued": True,
        "job_id": str(queued.job_id),
        "message_id": str(queued.message_id),
        "duplicate": queued.duplicate,
    }


DAI_TOI_DA_BAN_NHAP = 4000


class LoiSuaNhap(ValueError):
    """Bản nháp này không sửa được. Thông điệp nói rõ vì sao."""


class CanXacNhanQuangCao(Exception):
    """
    Nội dung người sửa chứa cụm cấm quảng cáo mỹ phẩm — hỏi lại trước khi gửi.

    CẢNH BÁO CHỨ KHÔNG CHẶN, và đó là một quyết định chứ không phải nửa vời:
    người bấm nút là người chịu trách nhiệm pháp lý, còn máy thì không đủ
    ngữ cảnh để phán một câu cụ thể là vi phạm hay đang trích lại lời khách.
    Nhưng họ phải THẤY trước khi tin rời đi, và lần bấm bỏ qua phải để lại
    dấu vết — xem `xac_nhan` ở `_queue_approved_draft`.
    """

    def __init__(self, cum: list[str]):
        super().__init__(", ".join(cum))
        self.cum = cum


def kiem_sua_nhap(hang, noi_dung: str) -> str:
    """
    Kiểm một lần sửa bản nháp. Trả nội dung đã cắt khoảng trắng, hoặc ném.

    Hàm THUẦN — không CSDL, không mạng. Nhờ vậy mọi luật ở đây kiểm được
    bằng một dict trần, và `_queue_approved_draft` chỉ còn phần ghi.
    """
    if hang is None:
        raise LoiSuaNhap("Không tìm thấy bản nháp.")

    # "Đã gửi" kiểm TRƯỚC "không phải nháp", dù cái sau bao hàm cái trước.
    # Thứ tự này chỉ đổi THÔNG ĐIỆP, và thông điệp mới là thứ người trực
    # đọc lúc 22 giờ: "tin đã gửi rồi" nói đúng chuyện vừa xảy ra, còn "chỉ
    # sửa được bản nháp" nghe như một lỗi cấu hình và khiến họ đi bấm lại.
    if hang["delivered"] or hang.get("delivery_status") in {"sent", "delivered", "read"}:
        raise LoiSuaNhap("Tin này đã gửi cho khách rồi, không sửa được nữa.")
    # Tin của khách là chuyện đã xảy ra; tin nhân viên thì tự họ gõ. Không
    # cái nào "sửa" được qua đường này theo nghĩa nào có ích.
    if hang["role"] != "agent" or hang.get("delivery_status") != "draft":
        raise LoiSuaNhap("Chỉ sửa được bản nháp AI chưa gửi.")

    sach = (noi_dung or "").strip()
    if not sach:
        raise LoiSuaNhap("Nội dung trống. Gửi một tin trắng cho khách là im lặng "
                         "mang hình dạng một câu trả lời.")
    if len(sach) > DAI_TOI_DA_BAN_NHAP:
        raise LoiSuaNhap(
            f"Nội dung dài {len(sach)} ký tự, quá {DAI_TOI_DA_BAN_NHAP}. Đây là "
            "đúng trần của ô nhân viên gõ tay — cùng một đường ra, cùng một trần."
        )
    return sach


async def _queue_approved_draft(
    mid: uuid.UUID, noi_dung: str | None = None, *,
    boi: str = "", xac_nhan: bool = False, the: str | None = None,
):
    """
    Duyệt một bản nháp, có thể kèm nội dung đã sửa.

    `noi_dung=None` là đường CŨ, giữ nguyên từng bước: nút "Duyệt và gửi"
    không sửa gì thì không được đụng vào dòng `messages`.
    """
    message = await db.fetchrow(
        """
        SELECT id, conversation_id, role, content, delivered, delivery_status,
               noi_dung_goc
        FROM messages WHERE id = $1
        """,
        mid,
    )
    if message is None:
        raise OutboundMessageNotFound("không tìm thấy bản nháp")

    van_ban = message["content"]
    if noi_dung is not None:
        van_ban = kiem_sua_nhap(message, noi_dung)

        # Soi cụm cấm TRƯỚC mọi lời ghi. Ném ở đây thì CSDL chưa đụng tới,
        # nên bấm "để tôi sửa lại" là quay về đúng trạng thái cũ.
        if not xac_nhan and (cum := tu_cam_hai_dang(van_ban)):
            raise CanXacNhanQuangCao(cum)

        # `coalesce` giữ bản AI ĐẦU TIÊN: `noi_dung_goc` là bản mô hình
        # viết, không phải "bản trước lần sửa này". Gán thẳng `content` vào
        # đây ở lần sửa thứ hai là mất bản AI vĩnh viễn mà không ai biết.
        await db.execute(
            """
            UPDATE messages
               SET noi_dung_goc = coalesce(noi_dung_goc, content),
                   content = $2, sua_boi = $3, sua_luc = now()
             WHERE id = $1
            """,
            mid, van_ban, boi,
        )
        # Nhật ký ghi SỐ ĐO, không chép nội dung: `events` không phải chỗ
        # nhân bản chữ gửi cho khách. Xem docs/du-lieu-ca-nhan.md.
        await db.log_event(
            "tin_nhan.sua_ban_nhap", actor=boi, ref_id=mid,
            ky_tu_truoc=len(message["content"] or ""), ky_tu_sau=len(van_ban),
        )
        if xac_nhan and (cum := tu_cam_hai_dang(van_ban)):
            await db.log_event(
                "tin_nhan.bo_qua_canh_bao_quang_cao",
                actor=boi, ref_id=mid, cum=", ".join(cum),
            )

    if message["delivered"] or message.get("delivery_status") in {
        "sent",
        "delivered",
        "read",
    }:
        return None
    return await OutboundService(PostgresOutboundRepository()).queue_existing_text(
        conversation_id=message["conversation_id"],
        message_id=message["id"],
        text=van_ban,
        idempotency_key=f"approve:{message['id']}",
        the=the,
    )


class DuyetBody(BaseModel):
    noi_dung: str | None = None
    xac_nhan: bool = False


@router.post("/messages/{message_id}/approve")
async def approve_draft(
    message_id: str,
    body: DuyetBody | None = None,
    nguoi: dict = Depends(bat_buoc_dang_nhap),
    _quyen: dict = Depends(can_quyen("hoi_thoai.tra_loi")),
) -> dict:
    """
    Chế độ assist: duyệt bản nháp rồi enqueue, không gọi provider tại API.

    Có `body.noi_dung` là quản lý đã sửa. Không có body — đúng cách dashboard
    gọi trước đây — thì hành vi y như cũ.

    Duyệt bản nháp cũng là GỬI TIN cho khách, nên nó chịu cùng chốt tầm nhìn
    với hai đường kia — chỉ khác là phải tra hội thoại qua tin nhắn.
    """
    mid = uuid.UUID(message_id)
    dong = await db.fetchrow(
        "SELECT conversation_id FROM messages WHERE id = $1", mid)
    if dong is not None:
        await chan_neu_khong_duoc_tra_loi(dong["conversation_id"], nguoi)
    # Duyệt bản nháp cũng là người gửi tin — cùng phép xét cửa sổ.
    the = (await _xet_cua_so_hoac_409(dong["conversation_id"])  # xet_tin_nhan_vien
           if dong else None)
    try:
        queued = await _queue_approved_draft(
            mid,
            body.noi_dung if body else None,
            boi=nguoi.get("ten_dang_nhap", ""),
            xac_nhan=bool(body and body.xac_nhan),
            the=the,
        )
    except OutboundMessageNotFound as exc:
        raise HTTPException(404, "Không thấy tin nhắn") from exc
    except LoiSuaNhap as exc:
        raise HTTPException(422, str(exc)) from exc
    except CanXacNhanQuangCao as exc:
        # 409 chứ không phải 400: yêu cầu hợp lệ, chỉ là đang xung đột với
        # một luật mà người dùng được quyền bỏ qua. Dashboard đọc `cum` để
        # nói rõ cụm nào, rồi gọi lại với `xac_nhan: true`.
        raise HTTPException(409, {
            "can_xac_nhan": True, "cum": exc.cum,
            "detail": "Nội dung chứa cụm bị cấm trong quảng cáo mỹ phẩm: "
                      + ", ".join(exc.cum),
        }) from exc
    if queued is None:
        return {"ok": True, "detail": "đã gửi trước đó"}
    return {
        "ok": True,
        "queued": True,
        "job_id": str(queued.job_id),
        "message_id": str(queued.message_id),
        "duplicate": queued.duplicate,
    }


@router.post("/conversations/{conv_id}/takeover")
async def takeover(
    conv_id: str,
    nguoi: dict = Depends(bat_buoc_dang_nhap),
    _quyen: dict = Depends(can_quyen("hoi_thoai.nhan")),
) -> dict:
    """Người giành lại quyền. Agent ngừng trả lời hội thoại này."""
    cid = uuid.UUID(conv_id)
    current = await db.fetchrow(
        "SELECT version FROM conversations WHERE id = $1", cid
    )
    if current is None:
        raise HTTPException(404, "Không thấy hội thoại")
    actor_id = uuid.UUID(str(nguoi["id"]))
    try:
        state = await ConversationRoutingService(
            PostgresRoutingRepository()
        ).takeover(
            conversation_id=cid,
            actor_id=actor_id,
            assignee_id=actor_id,
            expected_version=int(current["version"]),
            reason="Nhân viên nhận từ dashboard legacy",
            actor_is_admin="hoi_thoai.xem_tat_ca" in nguoi.get("quyen", ()),
        )
    except RoutingConversationNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ConversationConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except AssignmentDenied as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"ok": True, "mode": state.mode, "version": state.version}


@router.post("/conversations/{conv_id}/release")
async def release(
    conv_id: str,
    nguoi: dict = Depends(bat_buoc_dang_nhap),
    _quyen: dict = Depends(can_quyen("hoi_thoai.nhan")),
) -> dict:
    """
    Trả hội thoại lại cho agent.

    VỚI MESSENGER, ĐỔI CỜ TRONG CSDL THÔI LÀ CHƯA ĐỦ. Nếu hội thoại đã được
    trao cho Page Inbox bằng `pass_thread_control`, tin của khách vẫn đi vào
    `standby[]` cho tới khi có ai giành quyền lại — nghĩa là agent bật mà
    câm, và trên màn hình nó trông như đang chạy.

    Phải xin quyền lại từ Meta. Hỏng thì nói thẳng ra trong phản hồi thay vì
    báo `ok: True` cho một việc chưa xong.
    """
    cid = uuid.UUID(conv_id)
    conv = await db.fetchrow(
        "SELECT account_id, channel, external_id, version "
        "FROM conversations WHERE id = $1", cid
    )
    if conv is None:
        raise HTTPException(404, "Không thấy hội thoại")
    actor_id = uuid.UUID(str(nguoi["id"]))
    try:
        state = await ConversationRoutingService(
            PostgresRoutingRepository()
        ).release(
            conversation_id=cid,
            actor_id=actor_id,
            expected_version=int(conv["version"]),
            reason="Nhân viên release từ dashboard legacy",
            actor_is_admin="hoi_thoai.xem_tat_ca" in nguoi.get("quyen", ()),
        )
    except RoutingConversationNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ConversationConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except AssignmentDenied as exc:
        raise HTTPException(403, str(exc)) from exc

    ghi_chu = ""
    if conv and conv["channel"] == "messenger":
        ad = await channels.get_for_account(conv["account_id"])
        if (lay := getattr(ad, "nhan_lai_quyen", None)) is not None:
            kq = await lay(conv["external_id"])
            if not getattr(kq, "ok", True):
                ghi_chu = f"đã bật agent, nhưng chưa giành lại được quyền từ Meta: {kq.detail}"
                await db.log_event("banGiao.nhan_lai_that_bai", ref_id=cid,
                                   ly_do=str(kq.detail)[:200])
    result = {"ok": True, "mode": state.mode, "version": state.version}
    if ghi_chu:
        result["ghi_chu"] = ghi_chu
    return result


# Kiểu tệp suy từ đuôi. Danh sách CHO PHÉP — thứ lạ trả về
# `application/octet-stream`, tức trình duyệt tải xuống thay vì mở, và không
# có gì chạy được trong tab của người xem.
_MIME_THEO_DUOI = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif", ".pdf": "application/pdf",
}


@router.get("/attachments/{attachment_id}/file")
async def attachment_file(
    attachment_id: str, _nguoi: dict = Depends(bat_buoc_dang_nhap),
    _quyen: dict = Depends(can_quyen("hoi_thoai.doc")),
):
    """
    Phục vụ tệp đính kèm cho khung chat.

    VÌ SAO CẦN ĐƯỜNG NÀY
    --------------------
    `queue_file` lưu `storage_key` — đường dẫn TRÊN MÁY CHỦ — và để `url`
    rỗng. Dashboard vẽ `url` nên ra ảnh vỡ: người trực gửi ảnh cho khách
    xong, nhìn lại khung chat thì thấy một biểu tượng hỏng.

    KHÔNG NHẬN ĐƯỜNG DẪN TỪ CLIENT
    ------------------------------
    Client gửi ID của bản ghi; đường dẫn lấy từ CSDL. Nếu nhận đường dẫn thì
    `?path=../../.env` đọc được mọi tệp trên máy chủ.

    Và vẫn kiểm lần nữa rằng tệp nằm TRONG `data/`: một bản ghi hỏng hoặc bị
    sửa tay không được biến thành đường đọc toàn ổ đĩa.
    """
    try:
        aid = uuid.UUID(attachment_id)
    except ValueError as exc:
        raise HTTPException(404, "Không có tệp") from exc

    row = await db.fetchrow(
        "SELECT storage_key, mime_type, metadata FROM attachments WHERE id = $1",
        aid,
    )
    if row is None or not row["storage_key"]:
        raise HTTPException(404, "Không có tệp")

    duong = Path(str(row["storage_key"])).resolve()
    goc_du_lieu = (Path(__file__).resolve().parents[2] / "data").resolve()
    if goc_du_lieu not in duong.parents:
        await db.log_event("attachment.ngoai_thu_muc_du_lieu",
                           attachment_id=str(aid))
        raise HTTPException(404, "Không có tệp")
    if not duong.is_file():
        raise HTTPException(404, "Tệp không còn trên máy chủ")

    mime = str(row["mime_type"] or "") or _MIME_THEO_DUOI.get(
        duong.suffix.lower(), "application/octet-stream")
    return FileResponse(str(duong), media_type=mime)


# ---------------------------------------------------------------
#  Nick Zalo
#
#  Public API của ZaloCRM không liệt kê được nick, nên phần này đọc
#  CHỈ ĐỌC từ CSDL của nó. Xem agent/channels/zalocrm_accounts.py.
# ---------------------------------------------------------------

class ChonNickIn(BaseModel):
    zalo_account_id: str


@router.get("/zalo/accounts")
async def zalo_accounts(_quyen: dict = Depends(can_quyen("kenh.doc"))) -> dict:
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
async def set_default_account(body: ChonNickIn, _quyen: dict = Depends(can_quyen("kenh.sua"))) -> dict:
    """Đặt nick mặc định cho mọi hội thoại chưa ghim riêng."""
    if body.zalo_account_id and not await zalo_acc.hop_le(body.zalo_account_id):
        raise HTTPException(422, "Nick không tồn tại hoặc đang không kết nối")
    runtime.update(zalo_account_id=body.zalo_account_id)
    await db.log_event("zalo.account.default", actor="nguoi",
                       account_id=body.zalo_account_id)
    return {"dang_chon": body.zalo_account_id}


@router.post("/conversations/{conv_id}/account")
async def pin_conversation_account(conv_id: uuid.UUID, body: ChonNickIn, _quyen: dict = Depends(can_quyen("hoi_thoai.nhan"))) -> dict:
    """Ghim một nick cho riêng hội thoại này. Chuỗi rỗng = bỏ ghim."""
    await chan_neu_ngoai_kenh(conv_id, _quyen)
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


# ===============================================================
#  Nhân viên gửi ảnh và tài liệu — như mọi công cụ chat thật
# ===============================================================
#
# `OutboundService.queue_file` đã có từ trước: agent dùng nó gửi ảnh sản
# phẩm và đường đó chạy được. Nhưng không có route nào cho NGƯỜI, nên khung
# soạn tin chỉ có ô chữ.
#
# Nghĩa là agent gửi được ảnh còn người trực thì không — khách hỏi "cho xem
# ảnh thật cái đã mở nắp" thì họ phải mở Zalo riêng ra gửi, và tin đó nằm
# ngoài hội thoại, không ai truy được về sau.

# Danh sách CHO PHÉP, không phải danh sách cấm.
#
# `image/svg+xml` trông như ảnh nhưng SVG CHẠY ĐƯỢC MÃ trong trình duyệt
# người xem. `text/html` cũng vậy. Danh sách cấm thì luôn thiếu một mục, và
# mục thiếu đó là mục bị khai thác.
MIME_GUI_DUOC: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
}

# Zalo và Meta đều chặn tệp lớn hơn mức này ở phía họ. Chặn sớm để người
# trực biết ngay, thay vì chờ outbox thử ba lần rồi mới báo hỏng.
TOI_DA_BYTE_GUI = 10 * 1024 * 1024

THU_MUC_TAI_LEN = Path(__file__).resolve().parents[2] / "data" / "uploads"


def _ten_file_an_toan(ten_goc: str, mime: str) -> str:
    r"""
    Sinh tên file MỚI. Không bao giờ dùng tên client gửi lên.

    VÌ SAO KHÔNG LỌC TÊN XẤU MÀ VỨT HẲN
    -----------------------------------
    Tên như `../../../.env` nối vào đường dẫn là ghi đè file bí mật của
    chính hệ thống. Lọc từng mẫu xấu là trò đuổi bắt không bao giờ thắng:
    `..\`, `....//`, ký tự đã mã hoá URL, ký tự Unicode trông giống dấu gạch.

    Sinh tên mới thì cả lớp lỗ hổng đó biến mất — không còn gì của client
    trong đường dẫn.

    Đuôi lấy theo MIME chứ không theo tên: `virus.exe` gửi kèm
    `Content-Type: image/png` thì tin MIME. Kiểu tệp là quyết định của máy
    chủ, không phải của người gửi.
    """
    return f"{uuid.uuid4().hex}{MIME_GUI_DUOC.get(mime, '.bin')}"


@router.post("/conversations/{conv_id}/send-file")
async def staff_send_file(
    conv_id: str,
    ma_san_pham: str = Form(""),
    chu_thich: str = Form(""),
    tep: UploadFile | None = File(None),
    nguoi: dict = Depends(can_quyen("hoi_thoai.tra_loi")),
) -> dict:
    """
    Gửi ảnh sản phẩm theo mã, hoặc tải một tệp lên rồi gửi.

    HAI ĐƯỜNG, VÀ VÌ SAO CẢ HAI
    ---------------------------
    Theo MÃ SẢN PHẨM là việc người trực làm nhiều nhất — ảnh đã nằm sẵn
    trong kho, không tải lên gì cả, không mở thêm bề mặt tấn công nào.

    TẢI TỆP LÊN cần cho ảnh chụp thật, hoá đơn, hướng dẫn dùng. Nhưng mỗi
    lần nhận tệp từ trình duyệt là một lần phải tự bảo vệ — xem
    `_ten_file_an_toan` và `MIME_GUI_DUOC`.

    Đi qua outbox như mọi tin khác. Gọi thẳng provider ở đây là mất hết thứ
    outbox đang giữ: thử lại, chống trùng, dead-letter, và thứ tự tin.
    """
    from agent.core.tools import _anh_san_pham

    cid = uuid.UUID(conv_id)
    # Cùng chốt với gửi chữ: gửi ẢNH cho khách của người khác cũng là trả
    # lời khách ấy. Chặn một đường mà để hở đường kia là không chặn gì cả.
    await chan_neu_khong_duoc_tra_loi(cid, nguoi)
    # Xét cửa sổ TRƯỚC khi ghi tệp lên đĩa: 409 thì không để lại tệp mồ côi.
    the = await _xet_cua_so_hoac_409(cid, "tep")   # xet_tin_nhan_vien

    if ma_san_pham.strip():
        duong = _anh_san_pham(ma_san_pham.strip())
        if duong is None:
            raise HTTPException(404, f"Không có ảnh cho mã {ma_san_pham}")
        khoa = f"staff-file:{uuid.uuid4()}"
        ten_hien = chu_thich or ma_san_pham.strip()
    else:
        if tep is None:
            raise HTTPException(422, "Cần chọn mã sản phẩm hoặc một tệp")
        mime = (tep.content_type or "").split(";")[0].strip().lower()
        if mime not in MIME_GUI_DUOC:
            raise HTTPException(
                415,
                f"Không gửi được kiểu tệp này ({mime or 'không rõ'}). "
                "Chỉ nhận ảnh JPG/PNG/WEBP/GIF và PDF.",
            )
        noi_dung = await tep.read()
        if not noi_dung:
            raise HTTPException(422, "Tệp rỗng")
        if len(noi_dung) > TOI_DA_BYTE_GUI:
            raise HTTPException(
                413,
                f"Tệp {len(noi_dung) // 1024 // 1024}MB, vượt mức "
                f"{TOI_DA_BYTE_GUI // 1024 // 1024}MB.",
            )

        THU_MUC_TAI_LEN.mkdir(parents=True, exist_ok=True)
        duong = THU_MUC_TAI_LEN / _ten_file_an_toan(tep.filename or "", mime)
        duong.write_bytes(noi_dung)
        khoa = f"staff-file:{duong.name}"
        ten_hien = chu_thich or (tep.filename or "tệp đính kèm")[:80]

    try:
        queued = await OutboundService(PostgresOutboundRepository()).queue_file(
            conversation_id=cid,
            role="staff",
            path=str(duong),
            caption=ten_hien,
            idempotency_key=khoa,
            the=the,
            gui_boi=_nguoi_id(nguoi),
        )
    except ConversationNotFound as exc:
        raise HTTPException(404, "Không thấy hội thoại") from exc

    await db.log_event("staff.gui_file", ref_id=cid,
                       ten=ten_hien[:80], ma_san_pham=ma_san_pham or None)
    return {
        "ok": True,
        "queued": True,
        "job_id": str(queued.job_id),
        "message_id": str(queued.message_id),
        "duplicate": queued.duplicate,
    }
