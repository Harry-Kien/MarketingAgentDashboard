"""
API hồ sơ agent.

Ô nhập trên màn này chỉ SIẾT được, không nới được — xem
`agent/core/agent_ho_so.py`. API vẫn nhận giá trị lỏng hơn ngưỡng toàn cục
và LƯU nguyên như người dùng gõ, nhưng `siet()` ép lại lúc dùng, và phần
trả về nói rõ giá trị thật sự có hiệu lực.

Vì sao không từ chối thẳng giá trị lỏng: ngưỡng toàn cục đổi được lúc chạy.
Một hồ sơ đặt 0.5 là lỏng hôm nay có thể là chặt hơn vào tuần sau khi quản
trị hạ ngưỡng toàn cục xuống 0.4. Từ chối lúc lưu là khoá người dùng khỏi
một cấu hình sẽ hợp lệ, và bắt họ nhớ quay lại sửa.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agent import db
from agent.core import agent_ho_so

from .routes import can_quyen

router = APIRouter(prefix="/api/ho-so-agent", tags=["agent"])


class HoSoIn(BaseModel):
    ten: str = Field(min_length=1, max_length=80)
    mo_ta: str = Field("", max_length=500)
    huong_dan: str = Field("", max_length=4000)
    nguong_tu_tin: float | None = Field(None, ge=0, le=1)
    tran_chi_phi: float | None = Field(None, gt=0)
    bat: bool = True


def _cong_khai(d: dict) -> dict[str, Any]:
    """
    Trả kèm giá trị THẬT SỰ CÓ HIỆU LỰC, không chỉ giá trị đã lưu.

    Hiện mỗi giá trị đã lưu là màn hình nói dối: người dùng gõ 0.3, màn
    hình hiện 0.3, còn hệ thống chạy bằng 0.55 — và không có gì nói cho họ
    biết vì sao agent vẫn chuyển người sớm như trước.
    """
    hieu_luc = agent_ho_so.siet(d)
    return {
        "id": str(d["id"]),
        "ten": d["ten"],
        "mo_ta": d["mo_ta"],
        "huong_dan": d["huong_dan"],
        "bat": d["bat"],
        "nguong_tu_tin": (float(d["nguong_tu_tin"])
                          if d["nguong_tu_tin"] is not None else None),
        "tran_chi_phi": (float(d["tran_chi_phi"])
                         if d["tran_chi_phi"] is not None else None),
        "nguong_hieu_luc": hieu_luc.nguong_tu_tin,
        "tran_hieu_luc": hieu_luc.tran_chi_phi,
        "so_kenh": d.get("so_kenh", 0),
    }


@router.get("")
async def liet_ke(
    _q: dict = Depends(can_quyen("agent.doc")),
) -> dict[str, Any]:
    ds = await db.fetch(
        "SELECT hs.*, (SELECT count(*) FROM channel_accounts tk "
        "              WHERE tk.agent_ho_so_id = hs.id) AS so_kenh "
        "FROM agent_ho_so hs ORDER BY hs.ten")
    mac_dinh = agent_ho_so.mac_dinh()
    return {
        "ho_so": [_cong_khai(dict(d)) for d in ds],
        # Ngưỡng toàn cục hiện lên màn để người dùng biết mình đang siết so
        # với cái gì. Không hiện thì con số họ gõ không có điểm tựa nào.
        "toan_cuc": {"nguong_tu_tin": mac_dinh.nguong_tu_tin,
                     "tran_chi_phi": mac_dinh.tran_chi_phi},
    }


@router.post("", status_code=201)
async def tao(
    body: HoSoIn,
    nguoi: dict = Depends(can_quyen("agent.dieu_khien")),
) -> dict[str, Any]:
    try:
        d = await db.fetchrow(
            "INSERT INTO agent_ho_so (ten, mo_ta, huong_dan, nguong_tu_tin, "
            "tran_chi_phi, bat) VALUES ($1,$2,$3,$4,$5,$6) RETURNING *",
            body.ten.strip(), body.mo_ta.strip(), body.huong_dan.strip(),
            body.nguong_tu_tin, body.tran_chi_phi, body.bat)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(409, f"Đã có hồ sơ tên “{body.ten}”.") from exc

    await db.log_event("ho_so_agent.tao", actor=nguoi.get("ten_dang_nhap", "?"),
                       ref_id=d["id"], ten=body.ten.strip())
    return _cong_khai(dict(d) | {"so_kenh": 0})


@router.put("/{ho_so_id}")
async def sua(
    ho_so_id: UUID,
    body: HoSoIn,
    nguoi: dict = Depends(can_quyen("agent.dieu_khien")),
) -> dict[str, Any]:
    d = await db.fetchrow(
        "UPDATE agent_ho_so SET ten=$2, mo_ta=$3, huong_dan=$4, "
        "nguong_tu_tin=$5, tran_chi_phi=$6, bat=$7, sua_luc=now() "
        "WHERE id=$1 RETURNING *",
        ho_so_id, body.ten.strip(), body.mo_ta.strip(), body.huong_dan.strip(),
        body.nguong_tu_tin, body.tran_chi_phi, body.bat)
    if d is None:
        raise HTTPException(404, "Không tìm thấy hồ sơ agent")

    await db.log_event("ho_so_agent.sua", actor=nguoi.get("ten_dang_nhap", "?"),
                       ref_id=ho_so_id, ten=body.ten.strip())
    return _cong_khai(dict(d))


@router.delete("/{ho_so_id}", status_code=204)
async def xoa(
    ho_so_id: UUID,
    nguoi: dict = Depends(can_quyen("agent.dieu_khien")),
) -> None:
    """
    Xoá một hồ sơ.

    Kênh đang dùng nó KHÔNG ngừng trả lời — khoá ngoại là `ON DELETE SET
    NULL`, nên chúng rơi về hành vi mặc định. Chặn xoá khi còn kênh dùng
    nghe an toàn hơn, nhưng thực tế là người ta sẽ gỡ từng kênh ra rồi mới
    xoá, và giữa hai thao tác ấy hệ thống ở đúng trạng thái mà việc chặn
    định tránh.
    """
    d = await db.fetchrow(
        "DELETE FROM agent_ho_so WHERE id = $1 RETURNING ten", ho_so_id)
    if d is None:
        raise HTTPException(404, "Không tìm thấy hồ sơ agent")
    await db.log_event("ho_so_agent.xoa", actor=nguoi.get("ten_dang_nhap", "?"),
                       ref_id=ho_so_id, ten=d["ten"])
