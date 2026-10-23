"""
API nội dung: soạn, duyệt, đăng bài, chiến dịch, số liệu, phân tích.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import (APIRouter, Depends, HTTPException, Query)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import db
from agent.publish import analytics, chien_dich, copywriter, registry
from agent.publish import service as post_service

from .phu_thuoc import (
    _num,
    can_quyen,
)

router = APIRouter(prefix="/api")


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
async def publish_channels(_quyen: dict = Depends(can_quyen("noi_dung.doc"))) -> dict:
    """Kênh nào đang đi đường nào, và nếu chưa dùng được thì vì sao."""
    return {"kenh": await registry.trang_thai_kenh()}


@router.post("/posts/draft")
async def draft_post(body: SoanBaiIn, _quyen: dict = Depends(can_quyen("noi_dung.doc"))) -> dict:
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
async def list_posts(trang_thai: str | None = None, limit: int = 50, _quyen: dict = Depends(can_quyen("noi_dung.doc"))) -> dict:
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
async def create_post(body: TaoBaiIn, _quyen: dict = Depends(can_quyen("noi_dung.doc"))) -> dict:
    try:
        return await post_service.tao_bai(
            tieu_de=body.tieu_de, noi_dung=body.noi_dung, kenh=body.kenh,
            hashtags=body.hashtags, video_id=body.video_id,
            lich_dang=body.lich_dang, tao_boi="nguoi",
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/posts/{post_id}/approve")
async def approve_post(post_id: uuid.UUID, _quyen: dict = Depends(can_quyen("noi_dung.duyet"))) -> dict:
    try:
        return await post_service.duyet(str(post_id))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/posts/{post_id}/cancel")
async def cancel_post(post_id: uuid.UUID, _quyen: dict = Depends(can_quyen("noi_dung.duyet"))) -> dict:
    row = await db.fetchrow(
        "UPDATE posts SET trang_thai='da_huy', updated_at=now() "
        "WHERE id=$1 RETURNING *", post_id,
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy bài đăng")
    await db.log_event("post.cancelled", actor="nguoi", ref_id=post_id)
    return row


@router.post("/posts/{post_id}/callback")
async def post_callback(post_id: uuid.UUID, body: CallbackIn,
                        token: str = Query("")) -> dict:
    """
    n8n gọi về đây sau khi workflow chạy xong.

    KHÔNG đòi đăng nhập, và KHÔNG đòi quyền. Bên gọi là n8n — một tiến
    trình, không phải người — và nó không có cookie phiên. Trước bản này
    đường này nằm sau cả hai chốt, nên mọi lần n8n gọi về đều nhận 401:
    bài vẫn được đăng thật lên nền tảng, chỉ có kết quả là không bao giờ
    ghi lại. Không nổ, không nhật ký, dashboard hiện "đang đăng" mãi.

    Chốt thay thế là VÉ MỘT LẦN cấp lúc đẩy bài sang n8n, so bằng
    `compare_digest`. Vé chỉ mở đúng bài của nó, và biến mất khi bài không
    còn kênh nào chờ. Vé sai hay thiếu -> 401, không phải 404: 404 nói cho
    người dò biết bài nào có thật.
    """
    if not await post_service.kiem_ve_callback(str(post_id), token):
        await db.log_event("post.callback_ve_sai", actor="n8n",
                           ref_id=str(post_id))
        raise HTTPException(401, "Vé callback không hợp lệ")
    row = await post_service.ghi_nhan_callback(
        str(post_id), body.kenh, body.ok, body.url, body.detail
    )
    if row is None:
        raise HTTPException(404, "Không tìm thấy bài đăng")
    return row


@router.post("/posts/{post_id}/metrics")
async def add_metrics(post_id: uuid.UUID, body: SoLieuIn, _quyen: dict = Depends(can_quyen("noi_dung.duyet"))) -> dict:
    return await analytics.ghi_so_lieu(
        str(post_id), body.kenh, luot_xem=body.luot_xem,
        luot_thich=body.luot_thich, binh_luan=body.binh_luan,
        chia_se=body.chia_se, luot_click=body.luot_click, url=body.url,
    )


@router.get("/posts/{post_id}/metrics")
async def get_metrics(post_id: uuid.UUID, _quyen: dict = Depends(can_quyen("noi_dung.doc"))) -> dict:
    return {"so_lieu": await analytics.moi_nhat_theo_bai(str(post_id))}


@router.get("/analytics/khach")
async def analytics_khach(ngay: int = 30, _quyen: dict = Depends(can_quyen("bao_cao.doc"))) -> dict:
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
async def get_analytics(ngay: int = 30, _quyen: dict = Depends(can_quyen("bao_cao.doc"))) -> dict:
    tq = await analytics.tong_quan(ngay)
    tq["bai_tot_nhat"] = await analytics.bai_tot_nhat()
    return tq


class ChienDichIn(BaseModel):
    ten: str = Field(min_length=1, max_length=200)
    kenh: list[str] = Field(default_factory=lambda: ["facebook", "tiktok"])
    san_pham: str = ""
    y_tuong: str = ""
    video_id: str | None = None
    bat_dau: datetime | None = None
    gian_cach_phut: int = Field(30, ge=0, le=1440)


@router.post("/campaigns")
async def create_campaign(body: ChienDichIn, _quyen: dict = Depends(can_quyen("noi_dung.duyet"))) -> dict:
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
async def approve_all(trang_thai: str = "cho_duyet", _quyen: dict = Depends(can_quyen("noi_dung.duyet"))) -> dict:
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
async def post_kit(post_id: uuid.UUID, _quyen: dict = Depends(can_quyen("noi_dung.doc"))) -> dict:
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
async def post_video(post_id: uuid.UUID, _quyen: dict = Depends(can_quyen("noi_dung.doc"))):
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
async def mark_posted(post_id: uuid.UUID, body: CallbackIn, _quyen: dict = Depends(can_quyen("noi_dung.duyet"))) -> dict:
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
