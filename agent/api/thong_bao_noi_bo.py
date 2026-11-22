"""
API chuông thông báo nội bộ — `/api/toi/thong-bao...`.

VÌ SAO MIỄN QUYỀN MÀ VẪN AN TOÀN
--------------------------------
Cùng họ với `/api/toi/doi-mat-khau`: đây là dữ liệu của CHÍNH người đăng
nhập. Mọi câu SQL lọc `nguoi_nhan_id = người đang đăng nhập`, nên không có
quyền nào để kiểm — đòi một quyền ở đây chỉ làm người bị thu bớt quyền mất
luôn chuông của mình, trong khi những gì chuông chứa đã được chọn người nhận
theo quyền lúc sinh ra (xem `agent/core/thong_bao_noi_bo.py`). Đăng nhập thì
vẫn bắt buộc (`bat_buoc_dang_nhap`), và bốn đường được khai TỪNG CÁI trong
`quyen.MIEN_TRU`.

Đánh dấu đã đọc chỉ đổi dòng thông báo. Không có route nào ở đây chạm hội
thoại, công việc hay bản nháp — đọc không phải là làm xong.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from agent.core import thong_bao_noi_bo as tb

from .phu_thuoc import bat_buoc_dang_nhap

router = APIRouter(prefix="/api/toi/thong-bao", tags=["thong-bao"])


def _toi(nguoi: dict) -> UUID:
    return UUID(str(nguoi["id"]))


@router.get("")
async def danh_sach(
    chua_doc: bool = False,
    gioi_han: int = Query(20, ge=1, le=100),
    bo_qua: int = Query(0, ge=0, le=10_000),
    nguoi: dict = Depends(bat_buoc_dang_nhap),
) -> dict:
    uid = _toi(nguoi)
    ds = await tb.liet_ke(uid, chi_chua_doc=chua_doc, gioi_han=gioi_han, bo_qua=bo_qua)
    return {
        "thong_bao": ds,
        "chua_doc": await tb.dem_chua_doc(uid),
        "con_nua": len(ds) == gioi_han,
        "loai": [{"ma": k, "nhan": v} for k, v in tb.LOAI.items()],
    }


@router.get("/so-chua-doc")
async def so_chua_doc(nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    return {"chua_doc": await tb.dem_chua_doc(_toi(nguoi))}


@router.post("/da-doc-het")
async def da_doc_het(nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    return {"ok": True, "da_danh_dau": await tb.danh_dau_tat_ca(_toi(nguoi))}


@router.post("/{thong_bao_id}/da-doc")
async def da_doc(thong_bao_id: UUID, nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    if not await tb.danh_dau_da_doc(_toi(nguoi), thong_bao_id):
        raise HTTPException(404, "Không tìm thấy thông báo")
    return {"ok": True}
