"""
API mẫu trả lời nhanh.

Đọc cần `hoi_thoai.tra_loi` — ai trả lời khách thì cần dùng mẫu. Thêm/sửa/
xoá cần `tra_loi_nhanh.sua`: một mẫu là câu mọi người sẽ gửi cho khách, nên
sửa nó là sửa lời của cả cửa hàng.

Mẫu dính cụm cấm quảng cáo mỹ phẩm bị CHẶN lúc lưu (422), khác với bản nháp
AI chỉ bị cảnh báo — lý do ở `0027_tra_loi_nhanh.sql`. Soi bằng đúng hàm
đang soi bản nháp do quản lý sửa: hai bản sao của một luật thì sớm muộn
lệch nhau, và khi ấy một đường bị chặn, đường kia lọt.
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from agent import db
from agent.core.cham_mot_luot import tu_cam_hai_dang

from .routes import can_quyen

router = APIRouter(prefix="/api/tra-loi-nhanh", tags=["tra-loi-nhanh"])

_MA = re.compile(r"^[a-z0-9_-]{1,32}$")


class MauIn(BaseModel):
    ma_tat: str = Field(min_length=1, max_length=32)
    noi_dung: str = Field(min_length=1, max_length=2000)


def _kiem(body: MauIn) -> tuple[str, str]:
    ma = body.ma_tat.strip().lower()
    if not _MA.match(ma):
        raise HTTPException(422, "Mã tắt chỉ gồm chữ thường không dấu, số, gạch "
                                 "ngang hoặc gạch dưới, tối đa 32 ký tự.")
    nd = body.noi_dung.strip()
    if not nd:
        raise HTTPException(422, "Nội dung mẫu không được để trống.")
    cum = tu_cam_hai_dang(nd)
    if cum:
        raise HTTPException(422, {
            "cum": cum,
            "detail": "Mẫu chứa cụm bị cấm trong quảng cáo mỹ phẩm: "
                      + ", ".join(cum) + ". Mẫu được cả cửa hàng dùng lại "
                      "nên không lưu được — sửa câu chữ rồi lưu lại.",
        })
    return ma, nd


def _dong(r) -> dict[str, Any]:
    return {"id": str(r["id"]), "ma_tat": r["ma_tat"], "noi_dung": r["noi_dung"],
            "sua_luc": r["sua_luc"].isoformat()}


@router.get("")
async def liet_ke(
    q: str = Query("", max_length=100),
    _nguoi: dict = Depends(can_quyen("hoi_thoai.tra_loi")),
) -> dict[str, Any]:
    q = q.strip().lower()
    if q:
        # Khớp mã tắt từ ĐẦU (gõ "/sh" ra "ship"), nội dung thì ở đâu cũng
        # được. Thoát ký tự đại diện: gõ "%" không được thành "mọi thứ".
        thoat = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = await db.fetch(
            "SELECT * FROM tra_loi_nhanh WHERE ma_tat LIKE $1 || '%' "
            "OR public.bo_dau(noi_dung) LIKE '%' || public.bo_dau($1) || '%' "
            "ORDER BY (ma_tat LIKE $1 || '%') DESC, ma_tat LIMIT 20", thoat)
    else:
        rows = await db.fetch("SELECT * FROM tra_loi_nhanh ORDER BY ma_tat LIMIT 500")
    return {"mau": [_dong(r) for r in rows]}


@router.post("", status_code=201)
async def tao(body: MauIn,
              nguoi: dict = Depends(can_quyen("tra_loi_nhanh.sua"))) -> dict[str, Any]:
    ma, nd = _kiem(body)
    try:
        r = await db.fetchrow(
            "INSERT INTO tra_loi_nhanh (ma_tat, noi_dung, tao_boi) "
            "VALUES ($1, $2, $3) RETURNING *", ma, nd, UUID(str(nguoi["id"])))
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(409, f"Mã tắt /{ma} đã có.") from exc
    await db.log_event("tra_loi_nhanh.tao", actor=nguoi.get("ten_dang_nhap") or "?", ma_tat=ma)
    return _dong(r)


@router.put("/{mau_id}")
async def sua(mau_id: UUID, body: MauIn,
              nguoi: dict = Depends(can_quyen("tra_loi_nhanh.sua"))) -> dict[str, Any]:
    ma, nd = _kiem(body)
    try:
        r = await db.fetchrow(
            "UPDATE tra_loi_nhanh SET ma_tat = $2, noi_dung = $3, sua_luc = now() "
            "WHERE id = $1 RETURNING *", mau_id, ma, nd)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(409, f"Mã tắt /{ma} đã có.") from exc
    if r is None:
        raise HTTPException(404, "Không thấy mẫu.")
    await db.log_event("tra_loi_nhanh.sua", actor=nguoi.get("ten_dang_nhap") or "?", ma_tat=ma)
    return _dong(r)


@router.delete("/{mau_id}", status_code=204)
async def xoa(mau_id: UUID,
              nguoi: dict = Depends(can_quyen("tra_loi_nhanh.sua"))) -> None:
    r = await db.fetchrow("DELETE FROM tra_loi_nhanh WHERE id = $1 RETURNING ma_tat", mau_id)
    if r is None:
        raise HTTPException(404, "Không thấy mẫu.")
    await db.log_event("tra_loi_nhanh.xoa", actor=nguoi.get("ten_dang_nhap") or "?",
                       ma_tat=r["ma_tat"])
