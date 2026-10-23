"""
API tổng quan hệ thống: sức khoẻ, số liệu tổng, chi phí, công tắc runtime, nhật ký.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import (APIRouter, Depends)
from pydantic import BaseModel

from agent import db, runtime
from agent.channels import registry as channels
from agent.config import settings

from .phu_thuoc import (
    _num,
    can_quyen,
)

router = APIRouter(prefix="/api")


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
async def overview(_quyen: dict = Depends(can_quyen("hoi_thoai.doc"))) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    conv = await db.fetchrow(
        """
        SELECT count(*)                                              AS total,
               count(*) FILTER (WHERE status = 'auto')               AS handled,
               count(*) FILTER (WHERE status = 'escalated')          AS escalated,
               count(*) FILTER (WHERE status = 'assist')             AS waiting,
               coalesce(sum(cost_usd), 0)                            AS cost
        -- hội thoại phòng thử không phải khách
        FROM conversations WHERE updated_at >= $1 AND channel <> 'phong_thu'
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
        -- hội thoại phòng thử không phải khách
        WHERE channel <> 'phong_thu'
        ORDER BY updated_at DESC
        LIMIT 72
        """
    )

    # TIN CHẾT — không giới hạn 24 giờ, có chủ ý.
    #
    # Một tin không gửi được cho khách vẫn là một tin không gửi được, dù nó
    # chết từ tuần trước. Đo được trên hệ thống thật: ba tin của nhân viên
    # chết rải hơn một tuần mà không ai biết, vì không có chỗ nào đếm chúng.
    #
    # Cắt theo 24 giờ là để chúng tự biến mất khỏi màn hình sau một đêm —
    # đúng cái đã xảy ra.
    chet = await db.fetchrow(
        "SELECT count(*) AS n, max(updated_at) AS gan_nhat "
        "FROM outbox_jobs WHERE status = 'dead'"
    ) or {}

    # KHÁCH CHƯA CÓ CHỦ — cùng lý lẽ với tin chết ở trên, cũng không cắt
    # theo 24 giờ.
    #
    # Chủ dự án chọn "khách chưa giao là của chung, không tự gán chủ". Hệ
    # quả đã biết trước: phần lớn khách sẽ ở mãi trạng thái vô chủ. Một hàng
    # chờ không ai đếm thì không ai thấy — nên nó phải là một con số thường
    # trực, kèm TUỔI của khách vô chủ lâu nhất.
    #
    # Con số đứng im ở 400 thì người ta còn thấy. "Lâu nhất 62 ngày" thì họ
    # dừng lại.
    #
    # Dùng đúng mệnh đề của `/api/khach-vo-chu`: hai định nghĩa lệch nhau là
    # con số nói một đằng, danh sách hiện một nẻo.
    vo_chu = await db.fetchrow(
        "SELECT count(*) AS n, min(first_seen) AS lau_nhat FROM contacts "
        "WHERE owner_user_id IS NULL AND status = 'active'"
    ) or {}

    # VIỆC QUÁ HẠN — cùng họ với hai ô trên, cũng không cắt theo 24 giờ.
    #
    # Việc đã `xong` hoặc `huy` KHÔNG tính, dù hạn đã qua. Đếm chúng vào là
    # con số chỉ tăng và không bao giờ giảm — và một con số chỉ tăng là con
    # số người ta thôi nhìn sau tuần đầu.
    #
    # Đếm riêng việc CHƯA GIAO cho ai: đó là thứ dễ rơi nhất, vì không ai
    # thấy nó trong danh sách "việc của tôi".
    viec = await db.fetchrow(
        "SELECT count(*) FILTER (WHERE han < now()) AS qua_han, "
        "       count(*) FILTER (WHERE nguoi_nhan IS NULL) AS chua_giao, "
        "       min(han) FILTER (WHERE han < now()) AS han_cu_nhat "
        "FROM cong_viec WHERE trang_thai IN ('moi', 'dang_lam')"
    ) or {}

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
        "tin_chet": {
            "so": int(chet.get("n") or 0),
            "gan_nhat": (
                chet["gan_nhat"].isoformat() if chet.get("gan_nhat") else None
            ),
        },
        "khach_vo_chu": {
            "so": int(vo_chu.get("n") or 0),
            "lau_nhat": (
                vo_chu["lau_nhat"].isoformat() if vo_chu.get("lau_nhat") else None
            ),
        },
        "cong_viec": {
            "qua_han": int(viec.get("qua_han") or 0),
            "chua_giao": int(viec.get("chua_giao") or 0),
            "han_cu_nhat": (
                viec["han_cu_nhat"].isoformat()
                if viec.get("han_cu_nhat") else None
            ),
        },
        "runtime": dict(runtime.STATE),
        # Địa chỉ CÔNG KHAI để dashboard dựng URL callback cho Meta.
        # Trình duyệt chỉ biết `location.origin` — tức 127.0.0.1 khi
        # người vận hành mở dashboard tại chỗ. Copy địa chỉ đó dán vào
        # Meta là Meta không bao giờ gọi vào được, mà không có gì nói
        # ra nguyên nhân. Chỉ máy chủ biết địa chỉ thật.
        "public_base_url": settings.public_base_url.rstrip("/"),
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
#  Vận hành
# ---------------------------------------------------------------

class RuntimeBody(BaseModel):
    enabled: bool | None = None
    mode: str | None = None
    confidence_floor: float | None = None
    max_cost_per_conversation: float | None = None
    tran_chi_phi_ngay_usd: float | None = None
    phong_thu_tran_ngay_usd: float | None = None


@router.post("/runtime")
async def set_runtime(body: RuntimeBody, nguoi: dict = Depends(can_quyen("agent.dieu_khien"))) -> dict:
    state = await runtime.luu(body.model_dump(exclude_none=True), boi=nguoi["ten_dang_nhap"])
    await db.log_event("runtime.update", actor="staff", **{k: str(v) for k, v in state.items()})
    return state


@router.get("/events")
async def recent_events(limit: int = 50, _quyen: dict = Depends(can_quyen("hoi_thoai.doc"))) -> list[dict]:
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


@router.get("/channels")
async def list_channels(_quyen: dict = Depends(can_quyen("kenh.doc"))) -> dict:
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


# ---------------------------------------------------------------
#  Chi phí và hiệu năng
#
#  Thay cho Langfuse. Mọi số ở đây đã nằm sẵn trong bảng `messages` từ
#  ngày đầu — model, token vào/ra, token đọc từ cache, chi phí, độ trễ.
#  Dựng lên từ dữ liệu của chính mình thì không phải cài thêm hệ thống,
#  không phải tạo tài khoản, và không có gì chạy nền mà không dùng.
# ---------------------------------------------------------------

@router.get("/cost")
async def cost_report(ngay: int = 7, _quyen: dict = Depends(can_quyen("bao_cao.doc"))) -> dict:
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
