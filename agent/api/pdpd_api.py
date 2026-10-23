"""
API dữ liệu cá nhân (Luật BVDLCN): tra cứu, xin duyệt xoá, xoá, dọn theo hạn.
"""
from __future__ import annotations


from fastapi import (APIRouter, Depends, HTTPException)
from pydantic import BaseModel, Field

from agent.config import settings
from agent.core import du_lieu_ca_nhan

from .phu_thuoc import (
    can_quyen,
)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------
#  Bảo vệ dữ liệu cá nhân — Nghị định 13/2023/NĐ-CP
#
#  Ba quyền của chủ thể dữ liệu mà hệ thống phải đáp ứng được:
#    Điều 9.1.c  quyền BIẾT hệ thống giữ gì   -> GET  /api/pdpd/{sdt}
#    Điều 9.1.đ  quyền YÊU CẦU XOÁ            -> POST /api/pdpd/{sdt}/xoa
#    Điều 16     thời hạn lưu trữ              -> POST /api/pdpd/don-theo-han
# ---------------------------------------------------------------

class XoaDuLieuIn(BaseModel):
    ly_do: str = Field("khách yêu cầu", max_length=300)
    # Xoá không hoàn tác được. Bắt gõ đúng số điện thoại một lần nữa để
    # không ai xoá nhầm bằng một cú bấm lỡ tay.
    xac_nhan_sdt: str = Field(min_length=9, max_length=20)


class XinDuyetXoaIn(BaseModel):
    ly_do: str = Field(min_length=3, max_length=300)


@router.get("/pdpd/{sdt}")
async def pdpd_tra_cuu(sdt: str, _quyen: dict = Depends(can_quyen("khach.pii"))) -> dict:
    """Hệ thống đang giữ những gì về số điện thoại này."""
    try:
        # Kèm luôn trạng thái phiếu duyệt: không kèm thì giao diện phải đoán,
        # và cách đoán duy nhất là cho bấm Xoá rồi đọc lỗi trả về — tức là
        # dạy người vận hành rằng nút Xoá đôi khi không xoá.
        return {**await du_lieu_ca_nhan.tra_cuu(sdt),
                "phieu_duyet": await du_lieu_ca_nhan.trang_thai_phieu(sdt)}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/pdpd/{sdt}/xin-duyet")
async def pdpd_xin_duyet(sdt: str, body: XinDuyetXoaIn,
                         nguoi: dict = Depends(can_quyen("khach.xoa"))) -> dict:
    """
    Xin một phiếu duyệt để xoá số này. NGƯỜI KHÁC phải duyệt ở màn Nhật ký.

    Phiếu khoá theo số điện thoại — đúng khoá mà `pdpd_xoa` dùng. Phiếu tạo
    từ hồ sơ khách (`/api/contacts/{id}/retention-jobs`) khoá theo khách, và
    phần lớn hồ sơ khách chưa có số, nên đường ấy không mở được nút xoá.
    """
    try:
        return await du_lieu_ca_nhan.xin_duyet_xoa(
            sdt, ly_do=body.ly_do,
            nguoi_id=nguoi["id"], nguoi_ten=nguoi["ten_dang_nhap"],
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/pdpd/{sdt}/xoa")
async def pdpd_xoa(sdt: str, body: XoaDuLieuIn,
                   nguoi: dict = Depends(can_quyen("khach.xoa"))) -> dict:
    """
    Thực hiện yêu cầu xoá. KHÔNG HOÀN TÁC ĐƯỢC.

    Hội thoại và tin nhắn xoá hẳn; đơn hàng ẩn danh để giữ nghĩa vụ lưu
    chứng từ kế toán (Luật Kế toán 2015, Điều 41).
    """
    chuan = du_lieu_ca_nhan.chuan_hoa_sdt
    if chuan(body.xac_nhan_sdt) != chuan(sdt):
        raise HTTPException(422, "Số xác nhận không khớp — nhập lại để chắc chắn")
    try:
        # Ghi TÊN THẬT của người xoá, không ghi "nguoi" chung chung. Xoá dữ
        # liệu cá nhân là việc không hoàn tác được; nhật ký phải trả lời
        # được câu "ai đã làm việc này".
        return await du_lieu_ca_nhan.xoa(
            sdt, ly_do=f"{body.ly_do} (bởi {nguoi['ten_dang_nhap']})"
        )
    except du_lieu_ca_nhan.ChuaDuyet as exc:
        # 409 chứ không 422: người vận hành không gõ sai gì cả, chỉ là chưa
        # có người thứ hai duyệt. 422 đẩy họ đi soi lại ô nhập trong khi thứ
        # cần làm nằm ở màn khác.
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/pdpd")
async def pdpd_tong_quan(_quyen: dict = Depends(can_quyen("khach.pii"))) -> dict:
    """Chính sách lưu trữ đang áp dụng và số bản ghi sắp quá hạn."""
    return {
        **await du_lieu_ca_nhan.don_theo_thoi_han(chi_dem=True),
        "tu_dong_don": settings.tu_dong_don_du_lieu,
        "can_cu": [
            "Nghị định 13/2023/NĐ-CP — bảo vệ dữ liệu cá nhân",
            "Luật Kế toán 2015, Điều 41 — thời hạn lưu chứng từ",
        ],
    }


@router.post("/pdpd/don-theo-han")
async def pdpd_don(_quyen: dict = Depends(can_quyen("khach.pii"))) -> dict:
    """Dọn ngay hội thoại quá thời hạn, không chờ vòng lặp hằng ngày."""
    return await du_lieu_ca_nhan.don_theo_thoi_han()
