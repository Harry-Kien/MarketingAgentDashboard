"""
Danh mục nhãn — Cài đặt & Quản trị → Cấu hình chung → "Quản lý nhãn".

Quản lý danh mục là `cau_hinh.sua` (đọc: `cau_hinh.doc`): nhãn là bộ từ
vựng chung của cả cửa hàng, đổi tên một nhãn là đổi nó ở mọi khách và mọi
hội thoại cùng lúc — cùng tầm với một tham số cấu hình, không phải việc của
từng nhân viên trực.

Ô chọn nhãn trên màn nghiệp vụ đọc qua HAI đường riêng theo loại —
`/hoi-thoai` cần `hoi_thoai.doc`, `/khach` cần `khach.doc` — để người trực
hội thoại không cần quyền cấu hình chỉ để thấy danh sách nhãn. Hai đường
chỉ trả nhãn ĐANG DÙNG: nhãn đã ngừng không gắn mới được, đưa nó vào ô
chọn là mời người ta bấm vào một lỗi 422.

Gắn/gỡ nhãn KHÔNG nằm ở đây: nhãn hội thoại ở `hoi_thoai_nhan.py` (chốt
kênh của hội thoại), nhãn khách ở `contacts.py` (chốt kênh của khách).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from agent import db
from agent.core import nhan as nhan_loi

from .routes import can_quyen

router = APIRouter(prefix="/api/nhan", tags=["nhan"])


class NhanTaoIn(BaseModel):
    loai: str
    ten: str = Field(min_length=1, max_length=200)
    mau: str | None = None
    mo_ta: str = Field("", max_length=nhan_loi.MO_TA_TOI_DA)
    thu_tu: int = Field(100, ge=0, le=10000)


class NhanSuaIn(BaseModel):
    """
    Sửa được mọi thứ TRỪ `loai`. Đổi nhãn khách thành nhãn hội thoại thì
    mọi chỗ đã gắn thành sai chỗ — khoá ngoại hai cột (nhan_id, loai) của
    0056 cũng chặn việc ấy ở CSDL.
    """
    ten: str = Field(min_length=1, max_length=200)
    mau: str
    mo_ta: str = Field("", max_length=nhan_loi.MO_TA_TOI_DA)
    thu_tu: int = Field(100, ge=0, le=10000)


def _actor(nguoi: dict) -> str:
    return str(nguoi.get("ten_dang_nhap") or "?")


def _loi(exc: Exception) -> HTTPException:
    if isinstance(exc, nhan_loi.NhanKhongThay):
        return HTTPException(404, str(exc))
    return HTTPException(422, str(exc))


# Số chỗ đang dùng một nhãn — hiện ở màn quản lý để người ta biết ngừng
# một nhãn là đụng tới bao nhiêu khách / hội thoại / quy tắc.
_SQL_DANH_MUC = """
    SELECT n.*,
           (SELECT count(*) FROM hoi_thoai_gan_nhan g WHERE g.nhan_id = n.id) AS so_hoi_thoai,
           (SELECT count(*) FROM khach_gan_nhan g WHERE g.nhan_id = n.id) AS so_khach,
           (SELECT count(*) FROM quy_tac_tu_dong q
             WHERE strpos(q.dieu_kien::text, n.id::text) > 0
                OR strpos(q.hanh_dong::text, n.id::text) > 0) AS so_quy_tac
    FROM nhan n
"""


@router.get("")
async def danh_muc(
    loai: str | None = Query(None),
    _q: dict = Depends(can_quyen("cau_hinh.doc")),
) -> dict[str, Any]:
    """Toàn bộ danh mục, CẢ nhãn đã ngừng, kèm số chỗ đang dùng."""
    if loai is not None and loai not in nhan_loi.LOAI:
        raise HTTPException(422, f"loai phải là một trong: {', '.join(nhan_loi.LOAI)}")
    rows = await db.fetch(
        _SQL_DANH_MUC + " WHERE $1::text IS NULL OR n.loai = $1 "
        "ORDER BY n.loai, NOT n.dang_dung, n.thu_tu, lower(n.ten)", loai)
    return {
        "nhan": [nhan_loi.dong(r) for r in rows],
        "loai": [{"ma": k, "ten": nhan_loi.TEN_LOAI[k]} for k in nhan_loi.LOAI],
        "bang_mau": list(nhan_loi.BANG_MAU),
    }


async def _dang_dung(loai: str) -> dict[str, Any]:
    rows = await db.fetch(
        "SELECT id, loai, ten, mau, mo_ta, dang_dung, thu_tu FROM nhan "
        "WHERE loai = $1 AND dang_dung ORDER BY thu_tu, lower(ten)", loai)
    return {"nhan": [nhan_loi.dong(r) for r in rows]}


@router.get("/hoi-thoai")
async def nhan_hoi_thoai_dang_dung(
    _q: dict = Depends(can_quyen("hoi_thoai.doc")),
) -> dict[str, Any]:
    return await _dang_dung("hoi_thoai")


@router.get("/khach")
async def nhan_khach_dang_dung(
    _q: dict = Depends(can_quyen("khach.doc")),
) -> dict[str, Any]:
    return await _dang_dung("khach")


async def _trung_ten(conn, loai: str, ten: str, tru_id: UUID | None = None) -> None:
    cu = await conn.fetchrow(
        "SELECT id, ten, dang_dung FROM nhan WHERE loai = $1 AND lower(ten) = lower($2) "
        "AND ($3::uuid IS NULL OR id <> $3)", loai, ten, tru_id)
    if cu is None:
        return
    if not cu["dang_dung"]:
        # Nói đường ra: tạo bản thứ hai là tách lịch sử của cùng một nhãn
        # làm hai.
        raise HTTPException(409, f"Đã có nhãn «{cu['ten']}» (đang ngừng sử dụng) — "
                                 "bấm «Dùng lại» thay vì tạo mới.")
    raise HTTPException(409, f"Đã có nhãn «{cu['ten']}».")


@router.post("", status_code=201)
async def tao_nhan(body: NhanTaoIn,
                   nguoi: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict[str, Any]:
    if body.loai not in nhan_loi.LOAI:
        raise HTTPException(422, f"loai phải là một trong: {', '.join(nhan_loi.LOAI)}")
    try:
        ten = nhan_loi.chuan_ten(body.ten)
        mau = nhan_loi.chuan_mau(body.mau) if body.mau else None
    except nhan_loi.NhanHong as exc:
        raise _loi(exc) from exc
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await _trung_ten(conn, body.loai, ten)
            if mau is None:
                so = await conn.fetchval("SELECT count(*) FROM nhan WHERE loai = $1", body.loai)
                mau = nhan_loi.BANG_MAU[int(so) % len(nhan_loi.BANG_MAU)]
            try:
                r = await conn.fetchrow(
                    "INSERT INTO nhan (loai, ten, mau, mo_ta, thu_tu, tao_boi) "
                    "VALUES ($1,$2,$3,$4,$5,$6) RETURNING *",
                    body.loai, ten, mau, body.mo_ta.strip(), body.thu_tu,
                    UUID(str(nguoi["id"])))
            except asyncpg.UniqueViolationError as exc:
                # Hai người tạo cùng lúc: kiểm ở trên không thấy, chỉ mục bắt.
                raise HTTPException(409, f"Đã có nhãn «{ten}».") from exc
            await nhan_loi.ghi_su_kien(conn, "nhan.tao", _actor(nguoi), r["id"],
                                        {"loai": body.loai, "ten": ten, "mau": mau})
    return nhan_loi.dong(r)


@router.put("/{nhan_id}")
async def sua_nhan(nhan_id: UUID, body: NhanSuaIn,
                   nguoi: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict[str, Any]:
    try:
        ten = nhan_loi.chuan_ten(body.ten)
        mau = nhan_loi.chuan_mau(body.mau)
    except nhan_loi.NhanHong as exc:
        raise _loi(exc) from exc
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            cu = await conn.fetchrow("SELECT * FROM nhan WHERE id = $1 FOR UPDATE", nhan_id)
            if cu is None:
                raise HTTPException(404, "Không có nhãn này.")
            await _trung_ten(conn, cu["loai"], ten, nhan_id)
            try:
                r = await conn.fetchrow(
                    "UPDATE nhan SET ten=$2, mau=$3, mo_ta=$4, thu_tu=$5, sua_luc=now() "
                    "WHERE id=$1 RETURNING *",
                    nhan_id, ten, mau, body.mo_ta.strip(), body.thu_tu)
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(409, f"Đã có nhãn «{ten}».") from exc
            # Ghi CẢ giá trị cũ: "nhãn này trước kia tên gì" là câu hỏi
            # duy nhất nhật ký trả lời được sau khi đổi tên.
            doi = {k: {"cu": cu[k], "moi": r[k]} for k in ("ten", "mau", "mo_ta", "thu_tu")
                   if cu[k] != r[k]}
            await nhan_loi.ghi_su_kien(conn, "nhan.sua", _actor(nguoi), nhan_id,
                                        {"loai": cu["loai"], "ten": ten, "doi": doi})
    return nhan_loi.dong(r)


async def _doi_trang_thai(nhan_id: UUID, dang_dung: bool, nguoi: dict) -> dict[str, Any]:
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            r = await conn.fetchrow(
                "UPDATE nhan SET dang_dung = $2, sua_luc = now() WHERE id = $1 RETURNING *",
                nhan_id, dang_dung)
            if r is None:
                raise HTTPException(404, "Không có nhãn này.")
            await nhan_loi.ghi_su_kien(
                conn, "nhan.dung_lai" if dang_dung else "nhan.ngung", _actor(nguoi),
                nhan_id, {"loai": r["loai"], "ten": r["ten"]})
            dem = await conn.fetchrow(_SQL_DANH_MUC + " WHERE n.id = $1", nhan_id)
    ra = nhan_loi.dong(dem)
    if not dang_dung and ra["so_quy_tac"]:
        # Quy tắc gắn nhãn đã ngừng sẽ ghi "hỏng" ở lần chạy sau — nói
        # ngay bây giờ, lúc người bấm còn nhớ mình vừa làm gì.
        ra["canh_bao"] = (f"{ra['so_quy_tac']} quy tắc tự động đang nhắc tới nhãn này. "
                          "Quy tắc GẮN nhãn đã ngừng sẽ báo hỏng; hãy sửa quy tắc.")
    return ra


@router.post("/{nhan_id}/ngung")
async def ngung_nhan(nhan_id: UUID,
                     nguoi: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict[str, Any]:
    """Ngừng sử dụng: ẩn khỏi ô chọn, chỗ đã gắn GIỮ NGUYÊN (hiện xám)."""
    return await _doi_trang_thai(nhan_id, False, nguoi)


@router.post("/{nhan_id}/dung-lai")
async def dung_lai_nhan(nhan_id: UUID,
                        nguoi: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict[str, Any]:
    return await _doi_trang_thai(nhan_id, True, nguoi)


@router.delete("/{nhan_id}", status_code=204)
async def xoa_nhan(nhan_id: UUID,
                   nguoi: dict = Depends(can_quyen("cau_hinh.sua"))) -> None:
    """
    Chỉ xoá được nhãn CHƯA TỪNG dùng (tạo nhầm). Đã gắn ở đâu, hoặc quy tắc
    nào nhắc tới, thì 409 kèm con số — dùng «Ngừng sử dụng».

    Khoá ngoại RESTRICT ở bảng gắn là chốt thứ hai: kể cả khi kiểm ở đây sót
    một đường, CSDL vẫn không cho xoá nhãn đang gắn.
    """
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            r = await conn.fetchrow(_SQL_DANH_MUC + " WHERE n.id = $1 FOR UPDATE OF n", nhan_id)
            if r is None:
                raise HTTPException(404, "Không có nhãn này.")
            dung = int(r["so_hoi_thoai"]) + int(r["so_khach"]) + int(r["so_quy_tac"])
            if dung:
                raise HTTPException(409, (
                    f"Nhãn «{r['ten']}» đang được dùng ({r['so_khach']} khách, "
                    f"{r['so_hoi_thoai']} hội thoại, {r['so_quy_tac']} quy tắc) — "
                    "không xoá được nhãn đã dùng, vì lịch sử sẽ mất tên. Hãy "
                    "«Ngừng sử dụng»."))
            try:
                await conn.execute("DELETE FROM nhan WHERE id = $1", nhan_id)
            except asyncpg.ForeignKeyViolationError as exc:
                raise HTTPException(409, "Nhãn vừa được gắn ở đâu đó — hãy «Ngừng sử dụng».") from exc
            await nhan_loi.ghi_su_kien(conn, "nhan.xoa", _actor(nguoi), nhan_id,
                                        {"loai": r["loai"], "ten": r["ten"]})
