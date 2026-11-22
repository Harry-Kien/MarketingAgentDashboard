"""
Nhãn và ghi chú nội bộ theo hội thoại.

Mọi route đi qua `chan_neu_ngoai_kenh`: hội thoại của kênh không được giao
thì 404 — gắn nhãn hay đọc ghi chú bàn giao cũng là nhìn vào hội thoại ấy.

NHÃN chọn từ danh mục (migration 0056, `agent/core/nhan.py`), không gõ chữ
tự do nữa. Đường cũ nhận TÊN nhãn (`{"nhan": "chờ hàng"}`) vẫn chạy, nhưng
chỉ tra tên trong danh mục — tên chưa có thì 422 chỉ đường sang Quản lý
nhãn, không tự tạo: tự tạo là quay lại đúng mớ "VIP"/"vip " cũ.

Ghi chú KHÔNG BAO GIỜ đi ra kênh. File này không import gì của outbox, và
test canh rằng tạo ghi chú không sinh `outbox_jobs` nào.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agent import db
from agent.core import nhan as nhan_loi

from .routes import can_quyen, chan_neu_ngoai_kenh

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


class NhanIn(BaseModel):
    nhan_id: UUID | None = None
    # Đường cũ: tên nhãn. Chỉ tra danh mục, không tạo.
    nhan: str | None = Field(None, min_length=1, max_length=nhan_loi.TEN_TOI_DA)


class GhiChuIn(BaseModel):
    noi_dung: str = Field(min_length=1, max_length=5000)


def _actor(nguoi: dict) -> str:
    return str(nguoi.get("ten_dang_nhap") or "?")


async def _tim_id(conn, khoa: str | UUID | None, ten: str | None) -> UUID:
    """id nhãn hội thoại từ id, hoặc từ tên (đường cũ)."""
    if isinstance(khoa, UUID):
        return khoa
    if khoa:
        try:
            return UUID(str(khoa))
        except ValueError:
            ten = str(khoa)
    if not ten:
        raise HTTPException(422, "Cần nhan_id (chọn nhãn trong danh mục).")
    try:
        n = await nhan_loi.tim_theo_ten(conn, "hoi_thoai", ten)
    except nhan_loi.NhanHong as exc:
        raise HTTPException(422, str(exc)) from exc
    if n is None:
        raise HTTPException(422, (
            f"Chưa có nhãn hội thoại «{ten.strip()}» trong danh mục — tạo ở "
            "Cấu hình → Quản lý nhãn rồi chọn lại."))
    return UUID(str(n["id"]))


@router.get("/nhan")
async def liet_ke_nhan(nguoi: dict = Depends(can_quyen("hoi_thoai.doc"))) -> dict[str, Any]:
    """
    Nhãn hội thoại đang GẮN, kèm số hội thoại — chỉ đếm hội thoại người này
    thấy. Nuôi hàng chip lọc của hộp thư; nhãn đã ngừng mà còn gắn vẫn hiện,
    vì vẫn lọc được.
    """
    rows = await db.fetch(
        "SELECT n.id, n.ten, n.mau, n.dang_dung, count(*) AS so "
        "FROM hoi_thoai_gan_nhan g JOIN nhan n ON n.id = g.nhan_id "
        "JOIN conversations cv ON cv.id = g.conversation_id "
        "WHERE $1 OR EXISTS (SELECT 1 FROM account_memberships am "
        "  WHERE am.account_id = cv.account_id AND am.user_id = $2) "
        "GROUP BY n.id ORDER BY so DESC, lower(n.ten) LIMIT 200",
        "hoi_thoai.xem_tat_ca" in (nguoi.get("quyen") or ()), UUID(str(nguoi["id"])))
    # `nhan` (tên) giữ cho mã cũ đọc chip lọc theo tên.
    return {"nhan": [{"id": str(r["id"]), "nhan": r["ten"], "ten": r["ten"], "mau": r["mau"],
                      "mau_chu": nhan_loi.mau_chu(r["mau"]), "dang_dung": r["dang_dung"],
                      "so": r["so"]} for r in rows]}


@router.get("/conversations/{conversation_id}/nhan")
async def nhan_cua_hoi_thoai(conversation_id: UUID,
                             nguoi: dict = Depends(can_quyen("hoi_thoai.doc"))) -> dict[str, Any]:
    await chan_neu_ngoai_kenh(conversation_id, nguoi)
    ds = await db.fetchrow(
        "SELECT " + nhan_loi.sql_nhan_da_gan("hoi_thoai_gan_nhan", "conversation_id", "$1")
        + " AS ds", conversation_id)
    return {"nhan": (ds or {}).get("ds") or []}


@router.post("/conversations/{conversation_id}/nhan", status_code=201)
async def gan_nhan(conversation_id: UUID, body: NhanIn,
                   nguoi: dict = Depends(can_quyen("hoi_thoai.tra_loi"))) -> dict[str, Any]:
    await chan_neu_ngoai_kenh(conversation_id, nguoi)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            if not await conn.fetchval("SELECT 1 FROM conversations WHERE id = $1",
                                       conversation_id):
                raise HTTPException(404, "Không thấy hội thoại")
            nid = await _tim_id(conn, body.nhan_id, body.nhan)
            try:
                n, moi = await nhan_loi.gan_hoi_thoai(
                    conn, conversation_id=conversation_id, nhan_id=nid,
                    gan_boi=UUID(str(nguoi["id"])), actor=_actor(nguoi))
            except nhan_loi.NhanKhongThay as exc:
                raise HTTPException(404, str(exc)) from exc
            except nhan_loi.NhanHong as exc:
                raise HTTPException(422, str(exc)) from exc
    return {"nhan_id": str(n["id"]), "nhan": n["ten"], "ten": n["ten"], "mau": n["mau"],
            "moi_gan": moi}


@router.delete("/conversations/{conversation_id}/nhan/{khoa}", status_code=204)
async def go_nhan(conversation_id: UUID, khoa: str,
                  nguoi: dict = Depends(can_quyen("hoi_thoai.tra_loi"))) -> None:
    """`khoa` là id nhãn; tên nhãn (đường cũ) cũng nhận."""
    await chan_neu_ngoai_kenh(conversation_id, nguoi)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            nid = await _tim_id(conn, khoa, None)
            await nhan_loi.go_hoi_thoai(conn, conversation_id=conversation_id,
                                        nhan_id=nid, actor=_actor(nguoi))


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
    r = await db.fetchrow_chac(
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
    try:
        return await giai_quyet.giai_quyet(
            conversation_id, UUID(str(nguoi["id"]))
        )
    except giai_quyet.ConversationHasPendingTasksError as exc:
        raise HTTPException(status_code=409, detail=exc.api_detail()) from exc
