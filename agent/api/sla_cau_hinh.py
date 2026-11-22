"""
Cấu hình chung → SLA & Giờ làm việc: lịch làm việc chung và chế độ /
ngưỡng cảnh báo của từng mục tiêu SLA (mục 15, 22.11.2026).

Số phút của từng mục tiêu theo kênh × mức ưu tiên vẫn ở
`PUT /api/routing/sla-policies` (routing_admin.py) — thêm ô
`handover_response_minutes`. Ngưỡng CHUNG `SLA_NGUONG_CANH_BAO` và việc làm
khi trễ `SLA_KHI_TRE` vẫn đi qua Cài đặt API (`cau_hinh_dong`).

Quyền: xem `dinh_tuyen.doc`, sửa `dinh_tuyen.sua` — cùng cặp quyền với
chính sách SLA, vì lịch quyết định hạn SLA y như số phút.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agent import db
from agent.core import lich_lam_viec
from agent.omnichannel import sla_muc_tieu

from .phu_thuoc import can_quyen

router = APIRouter(prefix="/api/sla", tags=["sla-cau-hinh"])


class NgayIn(BaseModel):
    nghi: bool = False
    mo: str = Field(default="", max_length=5)
    dong: str = Field(default="", max_length=5)


class NgayLeIn(BaseModel):
    ngay: str = Field(max_length=10)
    ten: str = Field(default="", max_length=80)


class LichIn(BaseModel):
    bat: bool = True
    tuan: list[NgayIn] = Field(min_length=7, max_length=7)
    ngay_nghi: list[NgayLeIn] = Field(default_factory=list,
                                      max_length=lich_lam_viec.TOI_DA_NGAY_NGHI)


class MucTieuIn(BaseModel):
    ma: str = Field(max_length=40)
    che_do: str = Field(max_length=20)
    nguong_canh_bao: int | None = None


class CacMucTieuIn(BaseModel):
    muc_tieu: list[MucTieuIn] = Field(min_length=1, max_length=3)


def _nguoi(nguoi: dict) -> str:
    return str(nguoi.get("ten_dang_nhap") or nguoi.get("id") or "dashboard")


async def _cau_hinh() -> dict[str, Any]:
    from datetime import datetime, timezone

    lich = lich_lam_viec.hien_hanh()
    bay_gio = datetime.now(timezone.utc)
    mo = lich.lan_mo_ke_tiep(bay_gio)
    gio_rieng = await db.fetch(
        "SELECT p.id, p.account_id, p.priority, p.business_hours, ca.display_name "
        "FROM sla_policies p LEFT JOIN channel_accounts ca ON ca.id = p.account_id "
        "WHERE p.active AND p.business_hours <> '{}'::jsonb ORDER BY p.account_id, p.priority")
    return {
        "lich": lich_lam_viec.mo_ta(lich),
        "lich_env": lich_lam_viec.mo_ta(lich_lam_viec.lich_env()),
        "trang_thai": {
            "dang_trong_gio": lich.dang_mo(bay_gio),
            "mo_ke_tiep": mo.isoformat() if mo is not None else None,
        },
        "muc_tieu": sla_muc_tieu.mo_ta(),
        "che_do": sla_muc_tieu.CHE_DO,
        "nguong_chung": sla_muc_tieu.nguong_chung(),
        # Giờ riêng của chính sách chỉ còn tác dụng khi lịch lui về .env —
        # nói ra, đừng để người quản trị tin giờ 9–18 của kênh X đang chạy.
        "gio_rieng_chinh_sach": {
            "con_tac_dung": lich.gio_rieng,
            "ds": [{"id": str(r["id"]),
                    "kenh": r["display_name"] or ("mọi kênh" if r["account_id"] is None
                                                  else "kênh đã xoá"),
                    "uu_tien": r["priority"], "gio": r["business_hours"]} for r in gio_rieng],
        },
    }


@router.get("/cau-hinh")
async def doc_cau_hinh(_q: dict = Depends(can_quyen("dinh_tuyen.doc"))) -> dict[str, Any]:
    # Đọc lại từ CSDL: tiến trình này có thể chưa thấy bản vừa lưu ở
    # tiến trình khác — màn cấu hình phải nói đúng điều đang có hiệu lực.
    await sla_muc_tieu.nap()
    return await _cau_hinh()


@router.put("/lich-lam-viec")
async def luu_lich(body: LichIn, nguoi: dict = Depends(can_quyen("dinh_tuyen.sua"))) -> dict[str, Any]:
    try:
        await lich_lam_viec.luu(body.model_dump(), sua_boi=_nguoi(nguoi))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await _cau_hinh()


@router.delete("/lich-lam-viec")
async def bo_lich(nguoi: dict = Depends(can_quyen("dinh_tuyen.sua"))) -> dict[str, Any]:
    await lich_lam_viec.xoa(sua_boi=_nguoi(nguoi))
    return await _cau_hinh()


@router.put("/muc-tieu")
async def luu_muc_tieu(body: CacMucTieuIn,
                       nguoi: dict = Depends(can_quyen("dinh_tuyen.sua"))) -> dict[str, Any]:
    try:
        await sla_muc_tieu.luu([m.model_dump() for m in body.muc_tieu], sua_boi=_nguoi(nguoi))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return await _cau_hinh()
