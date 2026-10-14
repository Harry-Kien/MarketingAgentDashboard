"""
Nhãn và ghi chú nội bộ theo hội thoại.

Mọi route đi qua `chan_neu_ngoai_kenh`: hội thoại của kênh không được giao
thì 404 — gắn nhãn hay đọc ghi chú bàn giao cũng là nhìn vào hội thoại ấy.

Ghi chú KHÔNG BAO GIỜ đi ra kênh. File này không import gì của outbox, và
test canh rằng tạo ghi chú không sinh `outbox_jobs` nào.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from agent import db

from .routes import can_quyen, chan_neu_ngoai_kenh

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


class NhanIn(BaseModel):
    nhan: str = Field(min_length=1, max_length=40)


class GhiChuIn(BaseModel):
    noi_dung: str = Field(min_length=1, max_length=5000)


def _chuan_nhan(nhan: str) -> str:
    # Gộp khoảng trắng và hạ chữ thường: "Chờ  hàng" và "chờ hàng" là MỘT
    # nhãn. Không chuẩn hoá thì bộ lọc tách đôi danh sách mà không ai thấy.
    return " ".join(nhan.split()).lower()


@router.get("/nhan")
async def liet_ke_nhan(nguoi: dict = Depends(can_quyen("hoi_thoai.doc"))) -> dict[str, Any]:
    """Các nhãn đang dùng, kèm số hội thoại — chỉ đếm hội thoại người này thấy."""
    rows = await db.fetch(
        "SELECT hn.nhan, count(*) AS so FROM hoi_thoai_nhan hn "
        "JOIN conversations cv ON cv.id = hn.conversation_id "
        "WHERE $1 OR EXISTS (SELECT 1 FROM account_memberships am "
        "  WHERE am.account_id = cv.account_id AND am.user_id = $2) "
        "GROUP BY hn.nhan ORDER BY so DESC, hn.nhan LIMIT 200",
        "hoi_thoai.xem_tat_ca" in (nguoi.get("quyen") or ()), UUID(str(nguoi["id"])))
    return {"nhan": [{"nhan": r["nhan"], "so": r["so"]} for r in rows]}


@router.post("/conversations/{conversation_id}/nhan", status_code=201)
async def gan_nhan(conversation_id: UUID, body: NhanIn,
                   nguoi: dict = Depends(can_quyen("hoi_thoai.tra_loi"))) -> dict[str, Any]:
    await chan_neu_ngoai_kenh(conversation_id, nguoi)
    nhan = _chuan_nhan(body.nhan)
    await db.execute(
        "INSERT INTO hoi_thoai_nhan (conversation_id, nhan, tao_boi) VALUES ($1,$2,$3) "
        "ON CONFLICT DO NOTHING", conversation_id, nhan, UUID(str(nguoi["id"])))
    return {"nhan": nhan}


@router.delete("/conversations/{conversation_id}/nhan/{nhan}", status_code=204)
async def go_nhan(conversation_id: UUID, nhan: str,
                  nguoi: dict = Depends(can_quyen("hoi_thoai.tra_loi"))) -> None:
    await chan_neu_ngoai_kenh(conversation_id, nguoi)
    await db.execute("DELETE FROM hoi_thoai_nhan WHERE conversation_id = $1 AND nhan = $2",
                     conversation_id, _chuan_nhan(nhan))


@router.get("/conversations/{conversation_id}/ghi-chu")
async def doc_ghi_chu(conversation_id: UUID,
                      nguoi: dict = Depends(can_quyen("hoi_thoai.doc"))) -> dict[str, Any]:
    await chan_neu_ngoai_kenh(conversation_id, nguoi)
    rows = await db.fetch(
        "SELECT g.id, g.noi_dung, g.tao_luc, n.ho_ten FROM hoi_thoai_ghi_chu g "
        "LEFT JOIN nguoi_dung n ON n.id = g.tao_boi "
        "WHERE g.conversation_id = $1 ORDER BY g.tao_luc DESC LIMIT 100", conversation_id)
    return {"ghi_chu": [{"id": str(r["id"]), "noi_dung": r["noi_dung"],
                         "tao_luc": r["tao_luc"].isoformat(), "nguoi": r["ho_ten"] or ""}
                        for r in rows]}


@router.post("/conversations/{conversation_id}/ghi-chu", status_code=201)
async def them_ghi_chu(conversation_id: UUID, body: GhiChuIn,
                       nguoi: dict = Depends(can_quyen("hoi_thoai.tra_loi"))) -> dict[str, Any]:
    await chan_neu_ngoai_kenh(conversation_id, nguoi)
    r = await db.fetchrow(
        "INSERT INTO hoi_thoai_ghi_chu (conversation_id, noi_dung, tao_boi) "
        "VALUES ($1,$2,$3) RETURNING id, tao_luc",
        conversation_id, body.noi_dung.strip(), UUID(str(nguoi["id"])))
    return {"id": str(r["id"]), "tao_luc": r["tao_luc"].isoformat()}


@router.post("/conversations/{conversation_id}/giai-quyet")
async def giai_quyet_hoi_thoai(
    conversation_id: UUID,
    nguoi: dict = Depends(can_quyen("hoi_thoai.nhan")),
) -> dict[str, Any]:
    """
    Đánh dấu ĐÃ GIẢI QUYẾT: ghi `resolved_at` (SLA giải quyết đo được), kết
    thúc lượt giao, và hỏi CSAT nếu bật. Khách nhắn tiếp thì tự mở lại.
    Xem agent/omnichannel/giai_quyet.py.
    """
    from fastapi import HTTPException

    from agent.omnichannel import giai_quyet

    await chan_neu_ngoai_kenh(conversation_id, nguoi)
    if await db.fetchrow("SELECT 1 FROM conversations WHERE id = $1", conversation_id) is None:
        raise HTTPException(404, "Không thấy hội thoại")
    return await giai_quyet.giai_quyet(conversation_id, UUID(str(nguoi["id"])))
