"""
Nhật ký kiểm toán — tra cứu, lượt AI, đề xuất/phê duyệt, sự cố.

Cài đặt & Quản trị → Hệ thống & Nhật ký → tab "Nhật ký" (phiếu việc mục 18).
Mô hình đọc và mọi quy tắc làm sạch nằm ở `agent/core/nhat_ky_kiem_toan.py`;
tệp này chỉ là cổng HTTP và CHỐT QUYỀN.

HAI CỬA ĐỌC, HAI MỨC QUYỀN (điểm 9)
----------------------------------
`/api/nhat-ky…` tra TOÀN BỘ — cần `nhat_ky.doc`: nhật ký ghi cả đổi quyền,
khoá tài khoản, xoá dữ liệu khách của mọi kênh.

`/api/nhat-ky/hoi-thoai/{id}…` chỉ MỘT hội thoại — cần `hoi_thoai.doc` và
hội thoại phải thuộc kênh người này được xử lý (`chan_neu_ngoai_kenh`, 404
chứ không 403). Nhân viên trực cần biết "AI đã làm gì với khách mình đang
giữ" mà không cần thấy nhật ký của cả cửa hàng.

GHI (điểm 10–12) cần `nhat_ky.su_co`, và LUÔN là dòng mới: bảng `events` có
trigger chặn sửa/xoá (migration 0064).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent import db
from agent.core import nhat_ky_kiem_toan as nk
from agent.core.gio_lam_viec import VN

from .phu_thuoc import can_quyen, chan_neu_ngoai_kenh

router = APIRouter(prefix="/api/nhat-ky", tags=["nhat-ky"])

LoaiTacNhan = Literal["ai", "nhan_vien", "he_thong"]
TrangThai = Literal["su_co", "loi", "cho_duyet", "chuyen_nguoi", "thanh_cong"]


def _ten(nguoi: dict) -> str:
    return str(nguoi.get("ten_dang_nhap") or nguoi.get("id") or "?")


def _gio(t: datetime | None) -> datetime | None:
    """
    Giờ không kèm múi là giờ VIỆT NAM — người tra gõ "8 giờ sáng" theo đồng
    hồ cửa hàng. Để asyncpg tự hiểu là UTC thì mọi khoảng lọc lệch 7 tiếng
    và sự kiện buổi sáng rơi khỏi kết quả mà không ai biết vì sao.
    """
    if t is not None and t.tzinfo is None:
        return t.replace(tzinfo=VN)
    return t


@router.get("/danh-muc")
async def danh_muc(_q: dict = Depends(can_quyen("nhat_ky.doc"))) -> dict[str, Any]:
    """Giá trị cho các ô lọc: nhóm hành động, loại tác nhân, trạng thái, người."""
    nguoi = await db.fetch(
        "SELECT id, COALESCE(NULLIF(ho_ten, ''), ten_dang_nhap) AS ten "
        "FROM nguoi_dung ORDER BY 2")
    return {
        "nhom": [{"ma": m, "nhan": n} for m, n, _ in nk.NHOM_HANH_DONG]
        + [{"ma": nk.NHOM_MAC_DINH[0], "nhan": nk.NHOM_MAC_DINH[1]}],
        "loai_tac_nhan": [{"ma": m, "nhan": n} for m, n in nk.LOAI_TAC_NHAN.items()],
        "trang_thai": [{"ma": m, "nhan": n} for m, n in nk.TRANG_THAI.items()],
        "nguoi": [{"id": str(r["id"]), "ten": r["ten"]} for r in nguoi],
        "buoc_can_thiep": [{"ma": m, "nhan": n} for m, n in nk.BUOC_CAN_THIEP.items()],
        "trang_thai_de_xuat": [{"ma": m, "nhan": n} for m, n in nk.TRANG_THAI_DE_XUAT.items()],
    }


@router.get("")
async def tra_cuu(
    tu: datetime | None = None,
    den: datetime | None = None,
    hoi_thoai_id: UUID | None = None,
    loai_tac_nhan: LoaiTacNhan | None = None,
    nguoi_id: UUID | None = None,
    nhom: str | None = Query(None, max_length=40),
    kind: str | None = Query(None, max_length=80),
    trang_thai: TrangThai | None = None,
    luot_id: str | None = Query(None, max_length=40),
    truoc: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=nk.TOI_DA_TRANG),
    _q: dict = Depends(can_quyen("nhat_ky.doc")),
) -> dict[str, Any]:
    tu, den = _gio(tu), _gio(den)
    if tu and den and tu >= den:
        # Khoảng rỗng trả danh sách rỗng là để người tra tưởng "không có gì
        # xảy ra" — nói thẳng là bộ lọc sai.
        raise HTTPException(422, "Thời điểm bắt đầu phải trước thời điểm kết thúc")
    return await nk.tim(tu=tu, den=den, hoi_thoai_id=hoi_thoai_id,
                        loai_tac_nhan=loai_tac_nhan, nguoi_id=nguoi_id, nhom=nhom,
                        kind=kind, trang_thai=trang_thai, luot_id=luot_id,
                        truoc=truoc, limit=limit)


_COT_CSV = ("id", "luc", "hanh_dong", "kind", "nhom", "tac_nhan", "ten_tac_nhan",
            "hoi_thoai_id", "luot_id", "che_do_ai", "muc_uy_quyen", "trang_thai", "ket_qua")


@router.get("/xuat.csv")
async def xuat_csv(
    tu: datetime | None = None,
    den: datetime | None = None,
    hoi_thoai_id: UUID | None = None,
    loai_tac_nhan: LoaiTacNhan | None = None,
    nguoi_id: UUID | None = None,
    nhom: str | None = Query(None, max_length=40),
    trang_thai: TrangThai | None = None,
    nguoi: dict = Depends(can_quyen("nhat_ky.doc")),
) -> StreamingResponse:
    """
    Xuất CSV theo đúng bộ lọc đang xem, tối đa 5.000 dòng.

    CSV chỉ có cột đã làm sạch — không có `chi_tiet` thô. Bản xuất rời khỏi
    hệ thống (email, ổ đĩa), nên nó là chỗ cuối cùng được phép rò rỉ. Việc
    xuất cũng được ghi lại: ai đã mang nhật ký ra ngoài là câu hỏi kiểm toán.
    """
    tu, den = _gio(tu), _gio(den)
    dong: list[dict[str, Any]] = []
    truoc: int | None = None
    while len(dong) < 5000:
        kq = await nk.tim(tu=tu, den=den, hoi_thoai_id=hoi_thoai_id,
                          loai_tac_nhan=loai_tac_nhan, nguoi_id=nguoi_id, nhom=nhom,
                          trang_thai=trang_thai, truoc=truoc, limit=nk.TOI_DA_TRANG)
        dong.extend(kq["items"])
        truoc = kq["next_cursor"]
        if truoc is None:
            break
    dong = dong[:5000]
    buf = io.StringIO()
    buf.write("﻿")  # Excel đọc đúng tiếng Việt khi có BOM
    w = csv.writer(buf)
    w.writerow(_COT_CSV)
    for b in dong:
        w.writerow([b["id"], b["luc"], b["hanh_dong"], b["kind"], b["nhom"]["nhan"],
                    b["tac_nhan"]["nhan"], b["tac_nhan"]["ten"] or "", b["hoi_thoai_id"] or "",
                    b["luot_id"] or "", b["che_do_ai"] or "", b["muc_uy_quyen"] or "",
                    b["trang_thai"]["nhan"], b["ket_qua"]])
    await db.log_event("nhat_ky.xuat", actor=_ten(nguoi), so_dong=len(dong),
                       loc={"tu": tu.isoformat() if tu else None,
                            "den": den.isoformat() if den else None,
                            "hoi_thoai_id": str(hoi_thoai_id) if hoi_thoai_id else None,
                            "loai_tac_nhan": loai_tac_nhan, "nhom": nhom,
                            "trang_thai": trang_thai})
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8")]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="nhat-ky.csv"'})


@router.get("/de-xuat")
async def de_xuat(
    hoi_thoai_id: UUID | None = None,
    trang_thai: str | None = Query(None, max_length=30),
    truoc: datetime | None = None,
    limit: int = Query(50, ge=1, le=nk.TOI_DA_TRANG),
    _q: dict = Depends(can_quyen("nhat_ky.doc")),
) -> dict[str, Any]:
    """Lịch sử đề xuất của AI và quyết định của người (điểm 6)."""
    return await nk.de_xuat(hoi_thoai_id=hoi_thoai_id, trang_thai=trang_thai,
                            truoc=_gio(truoc), limit=limit)


@router.get("/luot/{luot_id}")
async def mot_luot(luot_id: str,
                   _q: dict = Depends(can_quyen("nhat_ky.doc"))) -> dict[str, Any]:
    kq = await nk.luot(luot_id[:40])
    if kq is None:
        raise HTTPException(404, "Không thấy lượt AI này")
    return kq


# ------------------------------------------------------------------ theo hội thoại

@router.get("/hoi-thoai/{cid}")
async def nhat_ky_hoi_thoai(
    cid: UUID,
    truoc: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=nk.TOI_DA_TRANG),
    nguoi: dict = Depends(can_quyen("hoi_thoai.doc")),
) -> dict[str, Any]:
    """Nhật ký của MỘT hội thoại, cho người được xử lý hội thoại ấy."""
    await chan_neu_ngoai_kenh(cid, nguoi)
    return await nk.tim(hoi_thoai_id=cid, truoc=truoc, limit=limit)


@router.get("/hoi-thoai/{cid}/luot/{luot_id}")
async def luot_trong_hoi_thoai(
    cid: UUID, luot_id: str,
    nguoi: dict = Depends(can_quyen("hoi_thoai.doc")),
) -> dict[str, Any]:
    """
    Lượt AI xem từ màn hội thoại. Lượt phải THUỘC hội thoại trong đường dẫn —
    không thì đổi `cid` sang hội thoại mình được xem là đọc được lượt của
    hội thoại bất kỳ.
    """
    await chan_neu_ngoai_kenh(cid, nguoi)
    kq = await nk.luot(luot_id[:40])
    if kq is None or kq.get("hoi_thoai_id") != str(cid):
        raise HTTPException(404, "Không thấy lượt AI này trong hội thoại")
    return kq


# ------------------------------------------------------------------ sự cố, giải trình

class SuCoBody(BaseModel):
    ghi_chu: str = Field(min_length=3, max_length=2000)


class BuocBody(BaseModel):
    loai: Literal["tiep_quan", "tat_ai", "doi_chinh_sach", "lien_he_khach", "khac"]
    ghi_chu: str = Field("", max_length=2000)


class KetThucBody(BaseModel):
    ket_qua: str = Field(min_length=3, max_length=500)
    ghi_chu: str = Field("", max_length=2000)


async def _ghi_hoac_loi(coro) -> dict[str, Any]:
    try:
        return {"ok": True, "id": await coro}
    except nk.KhongThay as exc:
        raise HTTPException(404, str(exc)) from exc
    except nk.KhongHopLe as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/su-co/{su_co_id}/buoc", status_code=201)
async def buoc_can_thiep(su_co_id: int, body: BuocBody,
                         nguoi: dict = Depends(can_quyen("nhat_ky.su_co"))) -> dict[str, Any]:
    """Một bước can thiệp: đã tiếp quản, đã tắt AI, đã đổi chính sách…"""
    return await _ghi_hoac_loi(nk.ghi_buoc_can_thiep(
        su_co_id, loai=body.loai, ghi_chu=body.ghi_chu, boi=_ten(nguoi)))


@router.post("/su-co/{su_co_id}/ket-thuc", status_code=201)
async def ket_thuc_su_co(su_co_id: int, body: KetThucBody,
                         nguoi: dict = Depends(can_quyen("nhat_ky.su_co"))) -> dict[str, Any]:
    return await _ghi_hoac_loi(nk.ghi_ket_thuc_su_co(
        su_co_id, ket_qua=body.ket_qua, ghi_chu=body.ghi_chu, boi=_ten(nguoi)))


@router.post("/{event_id}/su-co", status_code=201)
async def danh_dau_su_co(event_id: int, body: SuCoBody,
                         nguoi: dict = Depends(can_quyen("nhat_ky.su_co"))) -> dict[str, Any]:
    """Đánh dấu một hành động là sự cố. Dòng gốc giữ nguyên; đây là dòng mới."""
    return await _ghi_hoac_loi(nk.ghi_su_co(event_id, ghi_chu=body.ghi_chu, boi=_ten(nguoi)))


@router.post("/{event_id}/giai-trinh", status_code=201)
async def giai_trinh(event_id: int, body: SuCoBody,
                     nguoi: dict = Depends(can_quyen("nhat_ky.su_co"))) -> dict[str, Any]:
    """Đính chính / giải trình — cách DUY NHẤT để "sửa" một dòng nhật ký."""
    return await _ghi_hoac_loi(nk.ghi_giai_trinh(event_id, ghi_chu=body.ghi_chu, boi=_ten(nguoi)))


@router.get("/{event_id}")
async def mot_ban_ghi(event_id: int,
                      _q: dict = Depends(can_quyen("nhat_ky.doc"))) -> dict[str, Any]:
    kq = await nk.mot(event_id)
    if kq is None:
        raise HTTPException(404, "Không thấy sự kiện")
    if kq.get("luot_id"):
        kq["luot"] = await nk.luot(kq["luot_id"])
    return kq
