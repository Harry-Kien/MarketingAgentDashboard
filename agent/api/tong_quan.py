"""
API tổng quan hệ thống: sức khoẻ, số liệu tổng, chi phí, khách theo kênh, công tắc runtime, nhật ký.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import (APIRouter, Depends)
from pydantic import BaseModel

from agent import db, runtime
from agent.channels import registry as channels
from agent.config import settings
from agent.core import nhat_ky_kiem_toan

from .phu_thuoc import (
    _num,
    _xem_tat_ca_kenh,
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

    # PHẠM VI KÊNH — cùng mệnh đề với `GET /conversations` (hoi_thoai_cu.py)
    # và `inbox.py`. Trước đây overview không lọc: nhân viên chỉ được giao
    # kênh A vẫn thấy số chờ của mọi kênh, và băng ca trực (tooltip) hiện
    # TÊN KHÁCH kênh B — đúng thứ màn inbox đã giấu. Một lớp lọc chỉ chặn ở
    # danh sách mà rò ở ô tổng quan là lớp sơn.
    #
    # Hai tham số: xem mọi kênh, người hỏi. Dùng chung cho đếm hội thoại, đếm
    # tin agent và băng ca trực.
    xem_het = _xem_tat_ca_kenh(_quyen)
    nguoi_id = uuid.UUID(str(_quyen["id"]))
    pham_vi = (
        "($%d OR EXISTS (SELECT 1 FROM account_memberships am "
        "WHERE am.account_id = c.account_id AND am.user_id = $%d))"
    )

    conv = await db.fetchrow(
        f"""
        SELECT count(*)                                              AS total,
               count(*) FILTER (WHERE status = 'auto')               AS handled,
               count(*) FILTER (WHERE status = 'escalated')          AS escalated,
               count(*) FILTER (WHERE status = 'assist')             AS waiting,
               coalesce(sum(cost_usd), 0)                            AS cost
        -- hội thoại phòng thử không phải khách
        FROM conversations c WHERE updated_at >= $1 AND channel <> 'phong_thu'
          AND {pham_vi % (2, 3)}
        """,
        since, xem_het, nguoi_id,
    ) or {}

    msg = await db.fetchrow(
        f"""
        SELECT count(*)                                           AS replies,
               count(*) FILTER (WHERE grounded IS TRUE)            AS grounded,
               coalesce(avg(latency_ms), 0)                        AS latency,
               coalesce(sum(tokens_in), 0)                         AS tin,
               coalesce(sum(tokens_out), 0)                        AS tout,
               coalesce(sum(cache_read), 0)                        AS cached
        FROM messages m WHERE m.role = 'agent' AND m.created_at >= $1
          AND ($2 OR EXISTS (SELECT 1 FROM conversations c
                             WHERE c.id = m.conversation_id
                               AND {pham_vi % (2, 3)}))
        """,
        since, xem_het, nguoi_id,
    ) or {}

    # AI TỰ LO — đếm theo SỰ KIỆN, không theo `status` lúc này.
    #
    # Bản cũ: containment = hội thoại `status = 'auto'` / tổng. Duyệt một bản
    # nháp AI lật `assist` → `auto` (outbox.py), nên hội thoại người phải đọc
    # và bấm duyệt từng câu cũng thành "Agent tự xử lý" — con số tô hồng đúng
    # thứ nó sinh ra để đo (rà soát 20.11.2026). Giờ: trong số hội thoại có
    # tin AI trong 24 giờ, bao nhiêu KHÔNG có người can thiệp trong 24 giờ ấy
    # (chuyển người, tiếp quản, nhân viên gửi tin, duyệt nháp) — cùng định
    # nghĩa với màn Phân tích (agent/api/phan_tich.py).
    from .phan_tich import co_nguoi_can_thiep

    ai = await db.fetchrow(
        f"""
        WITH ai AS (
            SELECT DISTINCT m.conversation_id
            FROM messages m JOIN conversations c ON c.id = m.conversation_id
            WHERE m.role = 'agent' AND m.created_at >= $1 AND c.channel <> 'phong_thu'
              AND {pham_vi % (2, 3)}
        )
        SELECT count(*) AS ai,
               count(*) FILTER (WHERE NOT {co_nguoi_can_thiep(
                   'ai.conversation_id', '$1', "'infinity'::timestamptz")}) AS tu_lo
        FROM ai
        """,
        since, xem_het, nguoi_id,
    ) or {}

    # Băng ca trực — signature của dashboard.
    tape = await db.fetch(
        f"""
        SELECT id, status, outcome, customer_name, updated_at, cost_usd, msg_count
        FROM conversations c
        -- hội thoại phòng thử không phải khách
        WHERE channel <> 'phong_thu'
          AND {pham_vi % (1, 2)}
        ORDER BY updated_at DESC
        LIMIT 72
        """,
        xem_het, nguoi_id,
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
    from agent.core.lien_he_nhom import sql_khong_phai_nhom

    vo_chu = await db.fetchrow(
        "SELECT count(*) AS n, min(first_seen) AS lau_nhat FROM contacts "
        "WHERE owner_user_id IS NULL AND status = 'active' AND "
        + sql_khong_phai_nhom("contacts")
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
    co_ai = int(ai.get("ai") or 0)
    ai_tu_lo = int(ai.get("tu_lo") or 0)
    replies = int(msg.get("replies") or 0)
    grounded = int(msg.get("grounded") or 0)

    return {
        "conversations": {
            "total": total,
            "handled": handled,
            "escalated": int(conv.get("escalated") or 0),
            "waiting": int(conv.get("waiting") or 0),
            # `handled` giữ cho khách cũ của API, nhưng KHÔNG còn là tử số
            # của `containment`: nó là ảnh chụp `status = 'auto'`, gồm cả
            # hội thoại người đã duyệt từng câu. Xem khối "AI TỰ LO" ở trên.
            "ai": co_ai,
            "ai_tu_lo": ai_tu_lo,
            "containment": round(ai_tu_lo / co_ai, 4) if co_ai else None,
        },
        "quality": {
            "replies": replies,
            "grounding": round(grounded / replies, 4) if replies else None,
            "latency_ms": int(_num(msg.get("latency"))),
        },
        "cost": {
            "total_usd": round(_num(conv.get("cost")), 6),
            "chat_usd": round(_num(conv.get("cost")), 6),
            "per_conversation": round(_num(conv.get("cost")) / total, 6) if total else None,
            "tokens_in": int(msg.get("tin") or 0),
            "tokens_out": int(msg.get("tout") or 0),
            "cache_read": int(msg.get("cached") or 0),
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
async def recent_events(limit: int = 50, _quyen: dict = Depends(can_quyen("nhat_ky.doc"))) -> list[dict]:
    rows = await db.fetch(
        f"SELECT kind, actor, ref_id, detail, created_at FROM events "
        f"ORDER BY created_at DESC LIMIT {int(limit)}"
    )
    return [
        {
            "kind": r["kind"],
            "actor": r["actor"],
            "ref_id": str(r["ref_id"]) if r["ref_id"] else None,
            # Làm sạch lúc ĐỌC (phiếu việc mục 18 điểm 13): dòng cũ ghi trước
            # khi có quy tắc che vẫn nằm trong bảng.
            "detail": nhat_ky_kiem_toan.lam_sach(r["detail"]),
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


@router.get("/analytics/khach")
async def analytics_khach(ngay: int = 30, _quyen: dict = Depends(can_quyen("bao_cao.doc"))) -> dict:
    """
    Khách đến từ đâu, và mỗi kênh chạy tốt tới mức nào.

    Trả lời câu hỏi cơ bản nhất của người vận hành: khách của mình đến từ
    kênh nào, kênh nào agent tự lo được, kênh nào phải gọi người liên tục.
    (Từng nằm trong `noi_dung_api.py` cạnh số liệu bài đăng; chuyển sang
    đây khi gỡ tính năng đăng bài ngày 19.11.2026.)

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
