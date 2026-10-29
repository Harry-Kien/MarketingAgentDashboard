"""
API dữ liệu cá nhân (Luật BVDLCN): tra cứu, xin duyệt xoá, xoá, dọn theo hạn.
"""
from __future__ import annotations


from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import (APIRouter, Depends, HTTPException)
from pydantic import BaseModel, Field

from agent.config import settings
from agent.core import du_lieu_ca_nhan, yeu_cau_chu_the

from .phu_thuoc import (
    can_quyen,
)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------
#  Bảo vệ dữ liệu cá nhân — Luật 91/2025/QH15 (hiệu lực 01-01-2026, thay
#  Nghị định 13/2023) và Nghị định 356/2025/NĐ-CP hướng dẫn thi hành.
#
#    Luật Điều 4.1          quyền XEM hệ thống giữ gì -> GET  /api/pdpd/{sdt}
#    Luật Điều 4.1, 14      quyền YÊU CẦU XOÁ         -> POST /api/pdpd/{sdt}/xoa
#    Luật Điều 3.3, 14.1    thời hạn lưu trữ          -> POST /api/pdpd/don-theo-han
#    Luật Điều 4.5,
#    NĐ 356 Điều 5          THỜI HẠN đáp ứng yêu cầu  -> /api/pdpd/yeu-cau
# ---------------------------------------------------------------

class XoaDuLieuIn(BaseModel):
    ly_do: str = Field("khách yêu cầu", max_length=300)
    # Xoá không hoàn tác được. Bắt gõ đúng số điện thoại một lần nữa để
    # không ai xoá nhầm bằng một cú bấm lỡ tay.
    xac_nhan_sdt: str = Field(min_length=9, max_length=20)


class XinDuyetXoaIn(BaseModel):
    ly_do: str = Field(min_length=3, max_length=300)


# ---------------------------------------------------------------
#  Sổ yêu cầu của chủ thể dữ liệu — thời hạn NĐ 356/2025 Điều 5
#
#  KHAI TRƯỚC `/pdpd/{sdt}`: FastAPI khớp route theo thứ tự khai, và
#  "yeu-cau" khớp `{sdt}` — khai sau là GET /pdpd/yeu-cau thành tra cứu số
#  điện thoại "yeu-cau".
# ---------------------------------------------------------------

class YeuCauIn(BaseModel):
    loai: Literal["xem", "sua", "xoa", "rut_dong_y", "han_che", "phan_doi", "bao_ve"]
    sdt: str = Field("", max_length=20)
    kenh_nhan: Literal["chat", "dien_thoai", "email", "truc_tiep", "van_ban"] = "chat"
    noi_dung: str = Field("", max_length=500)
    co_ben_thu_ba: bool = False
    # Ghi lùi được: khách nhắn hôm qua mà hôm nay mới vào sổ thì hạn vẫn
    # tính từ HÔM QUA. Tính từ lúc vào sổ là tặng thêm ngày mà luật không cho.
    nhan_luc: datetime | None = None


class GiaHanIn(BaseModel):
    so_ngay: int = Field(ge=1, le=20)
    ly_do: str = Field(min_length=5, max_length=300)


class DongIn(BaseModel):
    ket_qua: str = Field("", max_length=500)
    tu_choi: bool = False


def _uid(nguoi: dict) -> UUID | None:
    try:
        return UUID(str(nguoi.get("id")))
    except (TypeError, ValueError):
        return None


async def _lam(coro):
    try:
        return await coro
    except yeu_cau_chu_the.YeuCauHong as exc:
        raise HTTPException(422, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/pdpd/yeu-cau")
async def yc_liet_ke(ca_da_xong: bool = False,
                     _q: dict = Depends(can_quyen("khach.pii"))) -> dict:
    return {"yeu_cau": await yeu_cau_chu_the.liet_ke(ca_da_xong=ca_da_xong),
            "dem": await yeu_cau_chu_the.dem_canh_bao(),
            "loai": {k: {"ten": v.ten, "ngay": v.ngay, "ngay_ben_thu_ba": v.ngay_ben_thu_ba,
                         "gia_han_toi_da": v.gia_han_toi_da} for k, v in yeu_cau_chu_the.LOAI.items()},
            "can_cu": yeu_cau_chu_the.CAN_CU}


@router.post("/pdpd/yeu-cau", status_code=201)
async def yc_tao(body: YeuCauIn, nguoi: dict = Depends(can_quyen("khach.pii"))) -> dict:
    return await _lam(yeu_cau_chu_the.tao(
        loai=body.loai, sdt=body.sdt, kenh_nhan=body.kenh_nhan, noi_dung=body.noi_dung,
        co_ben_thu_ba=body.co_ben_thu_ba, nhan_luc=body.nhan_luc, tao_boi=_uid(nguoi)))


@router.post("/pdpd/yeu-cau/{yid}/phan-hoi")
async def yc_phan_hoi(yid: UUID, nguoi: dict = Depends(can_quyen("khach.pii"))) -> dict:
    return await _lam(yeu_cau_chu_the.da_phan_hoi(yid, boi=_uid(nguoi)))


@router.post("/pdpd/yeu-cau/{yid}/gia-han")
async def yc_gia_han(yid: UUID, body: GiaHanIn, nguoi: dict = Depends(can_quyen("khach.pii"))) -> dict:
    return await _lam(yeu_cau_chu_the.gia_han(yid, so_ngay=body.so_ngay, ly_do=body.ly_do,
                                               boi=_uid(nguoi)))


@router.post("/pdpd/yeu-cau/{yid}/dong")
async def yc_dong(yid: UUID, body: DongIn, nguoi: dict = Depends(can_quyen("khach.pii"))) -> dict:
    return await _lam(yeu_cau_chu_the.dong(yid, ket_qua=body.ket_qua, tu_choi=body.tu_choi,
                                            boi=_uid(nguoi)))


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
        kq = await du_lieu_ca_nhan.xoa(
            sdt, ly_do=f"{body.ly_do} (bởi {nguoi['ten_dang_nhap']})"
        )
    except du_lieu_ca_nhan.ChuaDuyet as exc:
        # 409 chứ không 422: người vận hành không gõ sai gì cả, chỉ là chưa
        # có người thứ hai duyệt. 422 đẩy họ đi soi lại ô nhập trong khi thứ
        # cần làm nằm ở màn khác.
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # Chỉ đóng sổ khi đã xoá TRỌN (kể cả bên ERP). `da_xoa=False` mà vẫn
    # đóng là ghi "đã đáp ứng" cho một yêu cầu còn dở.
    # Số KHÔNG CÒN dữ liệu nào (đã dọn theo hạn, hoặc chưa từng có) cũng là
    # đã đáp ứng — để mở là sổ báo quá hạn cho một yêu cầu không còn gì để
    # làm: đỏ giả (rà soát 28.10.2026). Chỉ đóng yêu cầu khớp ĐÚNG dấu băm số
    # này, nên gõ nhầm số không đóng nhầm yêu cầu của người khác.
    if kq.get("da_xoa") or kq.get("khong_con_du_lieu"):
        kq["yeu_cau_da_dong"] = await yeu_cau_chu_the.dong_yeu_cau_xoa_theo_sdt(
            du_lieu_ca_nhan.chuan_hoa_sdt(sdt),
            ket_qua=("đã xoá qua trang PDPD" if kq.get("da_xoa")
                     else "hệ thống không còn dữ liệu nào của số này")
            + f" (bởi {nguoi['ten_dang_nhap']})")
    return kq


@router.get("/pdpd")
async def pdpd_tong_quan(_quyen: dict = Depends(can_quyen("khach.pii"))) -> dict:
    """Chính sách lưu trữ đang áp dụng và số bản ghi sắp quá hạn."""
    return {
        **await du_lieu_ca_nhan.don_theo_thoi_han(chi_dem=True),
        "tu_dong_don": settings.tu_dong_don_du_lieu,
        "can_cu": [
            "Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15",
            "Nghị định 356/2025/NĐ-CP — hướng dẫn Luật BVDLCN",
            "Luật Kế toán 2015, Điều 41 — thời hạn lưu chứng từ",
        ],
    }


@router.post("/pdpd/don-theo-han")
async def pdpd_don(_quyen: dict = Depends(can_quyen("khach.pii"))) -> dict:
    """Dọn ngay hội thoại quá thời hạn, không chờ vòng lặp hằng ngày."""
    return await du_lieu_ca_nhan.don_theo_thoi_han()
