"""
Cấu hình chung → SLA & Giờ làm việc: lịch làm việc chung và chế độ /
ngưỡng cảnh báo của từng mục tiêu SLA (mục 15, 22.11.2026).

Số phút của từng mục tiêu theo kênh × mức ưu tiên vẫn ở
`PUT /api/routing/sla-policies` (routing_admin.py) — thêm ô
`handover_response_minutes`. Ngưỡng CHUNG `SLA_NGUONG_CANH_BAO` và việc làm
khi trễ `SLA_KHI_TRE` vẫn đi qua Cài đặt API (`cau_hinh_dong`).

Quyền: xem `dinh_tuyen.doc`, sửa `dinh_tuyen.sua` — cùng cặp quyền với
chính sách SLA, vì lịch quyết định hạn SLA y như số phút.

`GET /api/sla/xem-truoc-han` (UX-15-03) trả lời câu "khách nhắn lúc X trên
kênh Y, mức Z thì hạn là mấy giờ" bằng CHÍNH biểu thức SQL đặt hạn thật
(`sla_gio.bieu_thuc_han` → `sla_han_lich`) và CHÍNH luật chọn chính sách của
đường đổi ưu tiên / mở lại. Dashboard không tự tính: một công thức chép sang
JavaScript là một công thức sẽ lệch, và một màn "thử tính" nói sai là màn
dạy người quản trị tin vào hạn không có thật.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from agent import cau_hinh_dong, db
from agent.core import lich_lam_viec
from agent.omnichannel import sla_muc_tieu
from agent.omnichannel.sla_gio import bieu_thuc_han

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
        # Việc làm khi trễ — để tab Cảnh báo hiện hai lựa chọn bằng lời thay
        # cho mã kỹ thuật `bao` / `bao_va_nang_uu_tien` (UX-15-05). Ghi vẫn
        # đi qua `/api/cai-dat-api` (quyền `cau_hinh.sua`): một đường lưu.
        "khi_tre": cau_hinh_dong.lay("SLA_KHI_TRE") or "bao",
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


# ---------------------------------------------------------------- thử tính hạn

# Luật chọn chính sách: đúng mức (lui về `normal`), chính sách riêng của kênh
# thắng chính sách chung — y hệt `uu_tien._SQL_HAN_MOI` và
# `giai_quyet._CHON_CHINH_SACH`. Test canh khối này trùng từng chữ với bản
# của đường đổi ưu tiên: lệch là màn thử tính chọn một chính sách khác với
# chính sách hội thoại thật nhận.
_CHON_CHINH_SACH = """
    FROM sla_policies policy
    WHERE policy.active
      AND policy.priority IN ($1, 'normal')
      AND (policy.account_id = $2 OR policy.account_id IS NULL)
    ORDER BY (policy.account_id IS NOT NULL) DESC, (policy.priority = $1) DESC
    LIMIT 1
"""

_MOC = "$3::timestamptz"
_SQL_XEM_TRUOC = (
    "SELECT policy.id, policy.account_id, policy.priority, policy.business_hours, "
    "policy.first_response_minutes, policy.handover_response_minutes, "
    "policy.resolution_minutes, "
    f"{bieu_thuc_han('first_response_minutes', 4, moc=_MOC)} AS han_phan_hoi_dau, "
    f"{bieu_thuc_han('handover_response_minutes', 5, moc=_MOC)} AS han_phan_hoi_sau_chuyen_giao, "
    f"{bieu_thuc_han('resolution_minutes', 6, moc=_MOC)} AS han_giai_quyet"
    + _CHON_CHINH_SACH)

_COT_PHUT = {"phan_hoi_dau": "first_response_minutes",
             "phan_hoi_sau_chuyen_giao": "handover_response_minutes",
             "giai_quyet": "resolution_minutes"}

# Đồng hồ của mỗi mục tiêu bắt đầu ở một sự kiện khác nhau; màn thử tính
# dùng chung một mốc, nên phải nói mốc ấy nghĩa là gì với từng mục tiêu.
_TU_DAU = {"phan_hoi_dau": "tính từ lúc khách nhắn (bắt đầu chu kỳ SLA)",
           "phan_hoi_sau_chuyen_giao": "tính từ lúc AI chuyển cho người",
           "giai_quyet": "tính từ lúc bắt đầu lượt phục vụ"}


def _chu_vn(t: datetime) -> str:
    """`Thứ Hai 23/11/2026 08:20` giờ VN — trình duyệt đặt múi khác cũng không lệch."""
    v = lich_lam_viec.gio_vn(t)
    return f"{lich_lam_viec.THU[v.weekday()]} {v:%d/%m/%Y %H:%M}"


def _doc_moc(chu: str | None) -> datetime:
    if not chu:
        return datetime.now(timezone.utc)
    try:
        t = datetime.fromisoformat(chu.strip())
    except ValueError as exc:
        raise HTTPException(422, "Thời điểm cần dạng NNNN-TT-NNTGG:PP, ví dụ 2026-11-23T09:00.") from exc
    # Ô datetime-local không mang múi giờ: người quản trị gõ giờ Việt Nam.
    return t.replace(tzinfo=lich_lam_viec.VN) if t.tzinfo is None else t


@router.get("/xem-truoc-han")
async def xem_truoc_han(
    uu_tien: Literal["low", "normal", "high", "urgent"] = "normal",
    account_id: uuid.UUID | None = None,
    bat_dau: str | None = Query(default=None, max_length=40),
    _q: dict = Depends(can_quyen("dinh_tuyen.doc")),
) -> dict[str, Any]:
    """
    Hạn của ba mục tiêu nếu đồng hồ bắt đầu ở `bat_dau` (giờ VN). CHỈ ĐỌC.

    Mỗi mục tiêu chạy đồng hồ riêng (`sla_muc_tieu.lich_sql`) — cùng tham số
    ba chỗ đặt hạn thật truyền vào; giờ riêng của chính sách có áp hay không
    là việc của `sla_lich_chinh_sach` trong SQL, y như lúc chạy thật.
    """
    moc = _doc_moc(bat_dau)
    # Đọc lại từ CSDL như màn cấu hình: tiến trình này có thể chưa thấy lịch
    # vừa lưu ở tiến trình khác, và thử tính trên lịch cũ là xanh giả.
    await sla_muc_tieu.nap()
    lich = lich_lam_viec.hien_hanh()
    r = await db.fetchrow(_SQL_XEM_TRUOC, uu_tien, account_id, moc,
                          sla_muc_tieu.lich_sql("phan_hoi_dau"),
                          sla_muc_tieu.lich_sql("phan_hoi_sau_chuyen_giao"),
                          sla_muc_tieu.lich_sql("giai_quyet"))
    chinh_sach: dict[str, Any] | None = None
    if r is not None:
        gio = r["business_hours"] or {}
        if isinstance(gio, str):
            # Dòng cũ lưu JSONB dạng chuỗi (mã hoá hai lần) — vẫn còn trong CSDL.
            import json
            gio = json.loads(gio) or {}
        chinh_sach = {
            "id": str(r["id"]),
            "pham_vi": "kenh" if r["account_id"] is not None else "chung",
            "muc": r["priority"],
            # Không có chính sách đúng mức → lui về mức "thường".
            "lui_ve_thuong": r["priority"] != uu_tien,
            "gio_rieng": gio or None,
            "gio_rieng_co_tac_dung": bool(gio) and lich.gio_rieng,
        }
    muc_tieu = []
    for ma, ten in sla_muc_tieu.MUC_TIEU.items():
        phut = r[_COT_PHUT[ma]] if r is not None else None
        han = r[f"han_{ma}"] if r is not None else None
        ty_le = sla_muc_tieu.nguong(ma)
        muc_tieu.append({
            "ma": ma, "ten": ten, "tu": _TU_DAU[ma],
            "che_do": "gio_lam_viec" if sla_muc_tieu.lich_cho(ma) is not None else "24_7",
            "phut": phut,
            "han": han.isoformat() if han is not None else None,
            "han_chu": _chu_vn(han) if han is not None else None,
            # Khoảng chờ THẬT trên đồng hồ treo tường — khác số phút khi
            # đồng hồ SLA dừng ngoài giờ; đó là điều người quản trị cần thấy.
            "cho_thuc_phut": round((han - moc).total_seconds() / 60, 1) if han is not None else None,
            "nguong_phan_tram": round(ty_le * 100),
            # Cùng phép tính với `sla._warning_threshold`: phần của số phút
            # cho phép, đo trên đồng hồ của chính mục tiêu.
            "canh_bao_sau_phut": round(phut * ty_le, 1) if phut else None,
        })
    return {
        "bat_dau": moc.isoformat(), "bat_dau_chu": _chu_vn(moc),
        "uu_tien": uu_tien, "account_id": str(account_id) if account_id else None,
        "lich": {"nguon": lich.nguon, "bat": lich.bat, "dang_mo_luc_bat_dau": lich.dang_mo(moc)},
        "chinh_sach": chinh_sach,
        "muc_tieu": muc_tieu,
    }
