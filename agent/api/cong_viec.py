"""
API công việc.

Phạm vi giống họ với khách: ai có `cong_viec.xem_tat_ca` thấy hết, còn lại
chỉ thấy việc mình nhận, việc mình giao, và việc CHƯA GIAO cho ai.

Vế cuối là cố ý. Việc do agent đẩy sang luôn ra đời ở trạng thái chưa giao
— nếu người trực không thấy nó thì cả khối này vô nghĩa.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from agent import db
from agent.core import cong_viec as cv

from .routes import can_quyen

router = APIRouter(prefix="/api/cong-viec", tags=["cong-viec"])

_CHON = (
    "cong_viec.id, cong_viec.tieu_de, cong_viec.mo_ta, cong_viec.trang_thai, "
    "cong_viec.uu_tien, cong_viec.han, cong_viec.nguon, "
    "cong_viec.nguoi_nhan, cong_viec.nguoi_giao, cong_viec.contact_id, "
    "cong_viec.conversation_id, cong_viec.tao_luc, cong_viec.xong_luc, "
    "nhan.ho_ten AS nguoi_nhan_ten, giao.ho_ten AS nguoi_giao_ten, "
    "khach.display_name AS khach_ten"
)
_JOIN = (
    "FROM cong_viec "
    "LEFT JOIN nguoi_dung nhan ON nhan.id = cong_viec.nguoi_nhan "
    "LEFT JOIN nguoi_dung giao ON giao.id = cong_viec.nguoi_giao "
    "LEFT JOIN contacts khach ON khach.id = cong_viec.contact_id"
)


class TaoIn(BaseModel):
    tieu_de: str = Field(min_length=3, max_length=200)
    mo_ta: str = Field("", max_length=5000)
    nguoi_nhan: UUID | None = None
    uu_tien: str = "thuong"
    han: datetime | None = None
    contact_id: UUID | None = None
    conversation_id: UUID | None = None


class SuaIn(BaseModel):
    tieu_de: str | None = Field(None, min_length=3, max_length=200)
    mo_ta: str | None = Field(None, max_length=5000)
    trang_thai: str | None = None
    uu_tien: str | None = None
    han: datetime | None = None
    nguoi_nhan: UUID | None = None
    # Phân biệt "không gửi" với "gửi null". Không có cờ này thì không thu
    # hồi được người nhận, và cũng không xoá được hạn.
    xoa_nguoi_nhan: bool = False
    xoa_han: bool = False


def _sach(d: dict) -> dict:
    for k in ("id", "nguoi_nhan", "nguoi_giao", "contact_id", "conversation_id"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    for k in ("han", "tao_luc", "xong_luc"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    d["qua_han"] = cv.qua_han(d)
    return d


@router.get("")
async def liet_ke(
    trang_thai: str | None = Query(None),
    cua_toi: bool = Query(False),
    limit: int = Query(100, ge=1, le=300),
    nguoi: dict = Depends(can_quyen("cong_viec.doc")),
) -> dict[str, Any]:
    loc, ts = cv.dieu_kien_pham_vi(nguoi=nguoi, so_tham_so=0)
    dieu_kien = [loc]
    if trang_thai:
        try:
            cv.kiem_trang_thai(trang_thai)
        except cv.CongViecHong as exc:
            raise HTTPException(422, str(exc)) from exc
        ts.append(trang_thai)
        dieu_kien.append(f"cong_viec.trang_thai = ${len(ts)}")
    if cua_toi:
        ts.append(str(nguoi["id"]))
        dieu_kien.append(f"cong_viec.nguoi_nhan = ${len(ts)}")
    ts.append(limit)

    ds = await db.fetch(
        f"SELECT {_CHON} {_JOIN} WHERE {' AND '.join(dieu_kien)} "   # noqa: S608
        # Việc chưa xong lên trước; trong đó việc có hạn gần lên trước.
        # `NULLS LAST` để việc không hạn không chen lên đầu — nó không gấp
        # hơn một việc phải xong chiều nay.
        f"ORDER BY (cong_viec.trang_thai IN ('xong','huy')), "
        f"         cong_viec.han NULLS LAST, cong_viec.tao_luc DESC "
        f"LIMIT ${len(ts)}",
        *ts)
    return {
        "cong_viec": [_sach(d) for d in ds],
        "trang_thai": [{"ma": m, "nhan": cv.NHAN_TRANG_THAI[m]}
                       for m in cv.TRANG_THAI],
        "uu_tien": [{"ma": m, "nhan": cv.NHAN_UU_TIEN[m]} for m in cv.UU_TIEN],
    }


@router.post("", status_code=201)
async def tao(
    body: TaoIn,
    nguoi: dict = Depends(can_quyen("cong_viec.sua")),
) -> dict[str, Any]:
    try:
        cv.kiem_uu_tien(body.uu_tien)
    except cv.CongViecHong as exc:
        raise HTTPException(422, str(exc)) from exc

    # Giao cho NGƯỜI KHÁC cần quyền riêng. Không tách thì bất kỳ ai tạo
    # được việc cũng đẩy được việc sang đầu người khác, và màn Công việc
    # của họ đầy thứ họ không nhận.
    if body.nguoi_nhan and str(body.nguoi_nhan) != str(nguoi["id"]):
        if "cong_viec.giao" not in (nguoi.get("quyen") or ()):
            raise HTTPException(403, (
                "Thiếu quyền: cong_viec.giao — bạn tạo việc cho mình được, "
                "nhưng giao cho người khác thì cần quyền này."))
        co = await db.fetchrow("SELECT 1 FROM nguoi_dung WHERE id = $1 "
                               "AND khoa = false", body.nguoi_nhan)
        if not co:
            raise HTTPException(422, "Người nhận không tồn tại hoặc đã bị khoá.")

    d = await db.fetchrow(
        "INSERT INTO cong_viec (tieu_de, mo_ta, nguoi_nhan, nguoi_giao, "
        "uu_tien, han, contact_id, conversation_id, nguon) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'nguoi') RETURNING id",
        body.tieu_de.strip(), body.mo_ta.strip(), body.nguoi_nhan,
        UUID(str(nguoi["id"])) if nguoi.get("id") else None,
        body.uu_tien, body.han, body.contact_id, body.conversation_id)

    await db.log_event("cong_viec.tao", actor=nguoi.get("ten_dang_nhap", "?"),
                       ref_id=d["id"], tieu_de=body.tieu_de.strip())
    return {"id": str(d["id"])}


@router.put("/{cong_viec_id}")
async def sua(
    cong_viec_id: UUID,
    body: SuaIn,
    nguoi: dict = Depends(can_quyen("cong_viec.sua")),
) -> dict[str, Any]:
    """
    Sửa một việc.

    `xong_luc` do MÁY CHỦ đặt, không nhận từ client: cột ấy bị ràng buộc
    `CHECK ((trang_thai = 'xong') = (xong_luc IS NOT NULL))`, và để client
    tự điền là mời một 500 khó hiểu mỗi lần nó quên.
    """
    if body.trang_thai:
        try:
            cv.kiem_trang_thai(body.trang_thai)
        except cv.CongViecHong as exc:
            raise HTTPException(422, str(exc)) from exc
    if body.uu_tien:
        try:
            cv.kiem_uu_tien(body.uu_tien)
        except cv.CongViecHong as exc:
            raise HTTPException(422, str(exc)) from exc

    doi_nguoi_nhan = body.nguoi_nhan is not None or body.xoa_nguoi_nhan
    if doi_nguoi_nhan and "cong_viec.giao" not in (nguoi.get("quyen") or ()):
        # Nhận việc CHƯA AI NHẬN về cho mình thì không cần quyền giao — đó
        # là tự nhận việc, không phải đẩy việc sang người khác.
        tu_nhan = (body.nguoi_nhan is not None
                   and str(body.nguoi_nhan) == str(nguoi["id"]))
        if not tu_nhan:
            raise HTTPException(403, "Thiếu quyền: cong_viec.giao")

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            cu = await conn.fetchrow(
                "SELECT trang_thai, nguoi_nhan FROM cong_viec WHERE id = $1 "
                "FOR UPDATE", cong_viec_id)
            if cu is None:
                raise HTTPException(404, "Không tìm thấy công việc")

            if (body.nguoi_nhan is not None
                    and str(body.nguoi_nhan) == str(nguoi["id"])
                    and cu["nguoi_nhan"] is not None
                    and str(cu["nguoi_nhan"]) != str(nguoi["id"])
                    and "cong_viec.giao" not in (nguoi.get("quyen") or ())):
                raise HTTPException(403, (
                    "Việc này đã có người nhận. Giành việc của người khác "
                    "cần quyền cong_viec.giao."))

            moi_tt = body.trang_thai or cu["trang_thai"]
            await conn.execute(
                "UPDATE cong_viec SET "
                "  tieu_de = COALESCE($2, tieu_de), "
                "  mo_ta = COALESCE($3, mo_ta), "
                "  trang_thai = $4, "
                "  uu_tien = COALESCE($5, uu_tien), "
                "  han = CASE WHEN $6 THEN NULL ELSE COALESCE($7, han) END, "
                "  nguoi_nhan = CASE WHEN $8 THEN NULL "
                "                    ELSE COALESCE($9, nguoi_nhan) END, "
                "  xong_luc = CASE WHEN $4 = 'xong' "
                "                  THEN COALESCE(xong_luc, now()) ELSE NULL END, "
                "  sua_luc = now() "
                "WHERE id = $1",
                cong_viec_id,
                body.tieu_de.strip() if body.tieu_de else None,
                body.mo_ta.strip() if body.mo_ta is not None else None,
                moi_tt,
                body.uu_tien,
                body.xoa_han, body.han,
                body.xoa_nguoi_nhan, body.nguoi_nhan)

    await db.log_event("cong_viec.sua", actor=nguoi.get("ten_dang_nhap", "?"),
                       ref_id=cong_viec_id, trang_thai=moi_tt)
    return {"id": str(cong_viec_id), "trang_thai": moi_tt}


@router.delete("/{cong_viec_id}", status_code=204)
async def xoa(
    cong_viec_id: UUID,
    nguoi: dict = Depends(can_quyen("cong_viec.giao")),
) -> None:
    """
    Xoá hẳn một việc.

    Cần `cong_viec.giao` chứ không `cong_viec.sua`: đánh dấu `huy` là thao
    tác hằng ngày và để lại dấu vết; xoá hẳn thì không, nên nó phải ở cùng
    bậc quyền với việc điều phối.
    """
    r = await db.execute("DELETE FROM cong_viec WHERE id = $1", cong_viec_id)
    if r.endswith(" 0"):
        raise HTTPException(404, "Không tìm thấy công việc")
    await db.log_event("cong_viec.xoa", actor=nguoi.get("ten_dang_nhap", "?"),
                       ref_id=cong_viec_id)
