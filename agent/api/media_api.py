"""
API cho khung "Media khách gửi" (Cài đặt & Quản trị → Hệ thống → Sao lưu).

QUYỀN
-----
Xem: `cau_hinh.doc` — cùng quyền đọc thời hạn lưu trữ (`MEDIA_LUU_NGAY`)
hiện ngay cạnh. Dọn, thử lại: `cau_hinh.sua` — cùng quyền đổi thời hạn; ai
được đổi "giữ bao lâu" thì được bảo hệ thống áp nó ngay bây giờ.

DỌN PHẢI XEM TRƯỚC
------------------
`POST /don` mặc định là XEM TRƯỚC. Muốn xoá thật phải gửi `xem_truoc=false`
một cách tường minh — gửi thiếu trường không được thành một lệnh xoá.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agent import db
from agent.omnichannel import media_don

from .routes import can_quyen

router = APIRouter(prefix="/api/media", tags=["media"])


class DonIn(BaseModel):
    xem_truoc: bool = True


def _nguoi(user: dict) -> str:
    return str(user.get("ten_dang_nhap") or user.get("id") or "nguoi")


@router.get("/tong-quan")
async def tong_quan(_: dict = Depends(can_quyen("cau_hinh.doc"))) -> dict[str, Any]:
    return await media_don.tong_quan()


@router.post("/don")
async def don_ngay(body: DonIn, user: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict[str, Any]:
    return await media_don.don(nguon="thu_cong", xem_truoc=body.xem_truoc, boi=_nguoi(user))


@router.post("/thu-lai")
async def thu_lai_tep_loi(user: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict[str, Any]:
    """
    Đưa tệp `loi` về hàng chờ, đếm lần thử lại từ đầu.

    Chỉ `loi` — hỏng sau đủ số lần thử, thường vì mạng hay CDN chết một lúc.
    `het_han` (hãng đã xoá link) và `qua_lon` (cố ý không tải) thử lại cũng
    không ra kết quả khác.
    """
    r = await db.execute(
        "UPDATE attachments SET media_trang_thai = 'cho', media_so_lan_thu = 0, "
        "media_thu_lai_luc = NULL WHERE media_trang_thai = 'loi'")
    so = int(r.split()[-1]) if r.split() and r.split()[-1].isdigit() else 0
    await db.log_event("media.thu_lai", actor=_nguoi(user), so_tep=so)
    return {"so_tep": so}
