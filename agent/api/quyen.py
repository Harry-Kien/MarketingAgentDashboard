"""
API vai trò và quyền.

VÌ SAO MỌI PHÉP KIỂM Ở ĐÂY NẰM TRONG GIAO DỊCH
-----------------------------------------------
Ràng buộc "phải còn ít nhất một người có `nguoi_dung.sua`" không kiểm được
bằng cách đọc trước rồi ghi sau: hai quản trị cùng bấm gỡ vai trò của nhau
thì cả hai phép đọc đều thấy "vẫn còn người khác", cả hai phép ghi đều chạy,
và kết quả là không còn ai.

Đó là khoá cứng ngoài hệ thống, và nó im lặng: đăng nhập vẫn được, chỉ có
màn Nhân viên là 403 với tất cả mọi người. Đường vào duy nhất còn lại là sửa
tay trong CSDL.

Nên: ghi trước, đếm sau, cùng một giao dịch, và ROLLBACK nếu đếm ra 0.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agent import db
from agent.core.quyen import QUYEN

from .routes import can_quyen

router = APIRouter(prefix="/api", tags=["quyen"])

# Quyền mà nếu mất người cuối cùng giữ nó thì không ai sửa lại được.
QUYEN_SONG_CON = "nguoi_dung.sua"


class VaiTroIn(BaseModel):
    ten: str = Field(min_length=1, max_length=80)
    mo_ta: str = Field("", max_length=500)
    quyen: list[str] = Field(default_factory=list)


class GanVaiTroIn(BaseModel):
    vai_tro: list[UUID] = Field(default_factory=list)


def _kiem_ma_quyen(ds: list[str]) -> None:
    """
    Tên quyền lạ thì 422, không lưu.

    Lưu âm thầm nghĩa là vai trò cấp một thứ không tồn tại: ô tick trên
    dashboard hiện đã bật, người quản trị tin là đã cấp, và nhân viên vẫn
    không vào được màn đó.
    """
    la = sorted(set(ds) - set(QUYEN))
    if la:
        raise HTTPException(422, f"Quyền không có trong danh mục: {', '.join(la)}")


async def _con_nguoi_giu_quyen_song_con(conn) -> bool:
    return bool(await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM nguoi_dung_vai_tro ndvt "
        "JOIN vai_tro vt ON vt.id = ndvt.vai_tro_id "
        "JOIN nguoi_dung nd ON nd.id = ndvt.nguoi_dung_id "
        "LEFT JOIN vai_tro_quyen vq ON vq.vai_tro_id = vt.id "
        "WHERE nd.khoa = false "
        "  AND (vq.quyen = $1 OR (vt.he_thong AND vt.ten = 'Quản trị')))",
        QUYEN_SONG_CON,
    ))


class KhoaCungNgoaiHeThong(HTTPException):
    def __init__(self) -> None:
        super().__init__(409, (
            f"Việc này lấy đi người cuối cùng có quyền “{QUYEN_SONG_CON}”. "
            "Làm xong thì không ai vào được màn Nhân viên để sửa lại. "
            "Hãy cấp quyền ấy cho một người khác trước."
        ))


# =====================================================================
#  Đọc
# =====================================================================

@router.get("/quyen")
async def danh_muc_quyen(
    _q: dict = Depends(can_quyen("nguoi_dung.doc")),
) -> dict[str, Any]:
    """Danh mục quyền, nhóm theo tiền tố — đúng cách dashboard hiển thị."""
    nhom: dict[str, list[dict[str, str]]] = {}
    for ma, nhan in QUYEN.items():
        nhom.setdefault(ma.split(".")[0], []).append({"ma": ma, "nhan": nhan})
    return {"nhom": nhom}


@router.get("/vai-tro")
async def liet_ke_vai_tro(
    _q: dict = Depends(can_quyen("nguoi_dung.doc")),
) -> dict[str, Any]:
    ds = await db.fetch(
        "SELECT vt.id, vt.ten, vt.mo_ta, vt.he_thong, vt.tao_luc, "
        "       COALESCE(array_agg(DISTINCT vq.quyen) "
        "                FILTER (WHERE vq.quyen IS NOT NULL), "
        "                ARRAY[]::text[]) AS quyen, "
        "       (SELECT count(*) FROM nguoi_dung_vai_tro ndvt "
        "        WHERE ndvt.vai_tro_id = vt.id) AS so_nguoi "
        "FROM vai_tro vt "
        "LEFT JOIN vai_tro_quyen vq ON vq.vai_tro_id = vt.id "
        "GROUP BY vt.id ORDER BY vt.he_thong DESC, vt.ten"
    )
    for v in ds:
        v["id"] = str(v["id"])
        # Vai trò hệ thống `Quản trị` có TOÀN BỘ danh mục, tính từ mã — xem
        # `xac_thuc.doc_phien`. Không hiện đúng như vậy ở đây thì màn cấp
        # quyền nói dối: nó vẽ một vai trò trống trong khi người mang nó
        # làm được mọi thứ.
        if v["he_thong"] and v["ten"] == "Quản trị":
            v["quyen"] = sorted(QUYEN)
            v["toan_quyen"] = True
        else:
            v["quyen"] = sorted(set(v["quyen"]) & set(QUYEN))
            v["toan_quyen"] = False
    return {"vai_tro": ds}


@router.get("/nguoi-dung/{nguoi_dung_id}/quyen")
async def giai_thich_quyen(
    nguoi_dung_id: UUID,
    _q: dict = Depends(can_quyen("nguoi_dung.doc")),
) -> dict[str, Any]:
    """
    Quyền thực tế của một người, kèm VAI TRÒ NÀO cấp quyền ấy.

    Không có màn này thì khi đông vai trò, không ai trả lời được vì sao
    người này vào được màn kia — và câu trả lời duy nhất còn lại là đọc CSDL.
    """
    nguoi = await db.fetchrow(
        "SELECT id, ten_dang_nhap, ho_ten, khoa FROM nguoi_dung WHERE id = $1",
        nguoi_dung_id,
    )
    if nguoi is None:
        raise HTTPException(404, "Không tìm thấy nhân viên")

    ds = await db.fetch(
        "SELECT vt.ten AS vai_tro, vt.he_thong, vq.quyen "
        "FROM nguoi_dung_vai_tro ndvt "
        "JOIN vai_tro vt ON vt.id = ndvt.vai_tro_id "
        "LEFT JOIN vai_tro_quyen vq ON vq.vai_tro_id = vt.id "
        "WHERE ndvt.nguoi_dung_id = $1",
        nguoi_dung_id,
    )

    quyen: dict[str, list[str]] = {}
    for r in ds:
        if r["he_thong"] and r["vai_tro"] == "Quản trị":
            for ma in QUYEN:
                quyen.setdefault(ma, []).append(r["vai_tro"])
            continue
        if r["quyen"] in QUYEN:
            quyen.setdefault(r["quyen"], []).append(r["vai_tro"])

    return {
        "nguoi_dung": {"id": str(nguoi["id"]),
                       "ten_dang_nhap": nguoi["ten_dang_nhap"],
                       "ho_ten": nguoi["ho_ten"], "khoa": nguoi["khoa"]},
        "vai_tro": sorted({r["vai_tro"] for r in ds}),
        "quyen": {k: sorted(set(v)) for k, v in sorted(quyen.items())},
    }


# =====================================================================
#  Ghi
# =====================================================================

@router.post("/vai-tro", status_code=201)
async def tao_vai_tro(
    body: VaiTroIn,
    nguoi: dict = Depends(can_quyen("nguoi_dung.sua")),
) -> dict[str, Any]:
    _kiem_ma_quyen(body.quyen)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            try:
                vid = await conn.fetchval(
                    "INSERT INTO vai_tro (ten, mo_ta) VALUES ($1, $2) RETURNING id",
                    body.ten, body.mo_ta,
                )
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(409, f"Đã có vai trò tên “{body.ten}”.") from exc
            for ma in sorted(set(body.quyen)):
                await conn.execute(
                    "INSERT INTO vai_tro_quyen (vai_tro_id, quyen) VALUES ($1,$2)",
                    vid, ma,
                )
    await db.log_event("vai_tro.tao", actor=nguoi.get("ten_dang_nhap", "?"),
                       ref_id=vid, ten=body.ten, quyen=sorted(set(body.quyen)))
    return {"id": str(vid), "ten": body.ten, "mo_ta": body.mo_ta,
            "quyen": sorted(set(body.quyen)), "he_thong": False}


@router.put("/vai-tro/{vai_tro_id}")
async def sua_vai_tro(
    vai_tro_id: UUID,
    body: VaiTroIn,
    nguoi: dict = Depends(can_quyen("nguoi_dung.sua")),
) -> dict[str, Any]:
    _kiem_ma_quyen(body.quyen)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            cu = await conn.fetchrow(
                "SELECT ten, he_thong FROM vai_tro WHERE id = $1 FOR UPDATE",
                vai_tro_id,
            )
            if cu is None:
                raise HTTPException(404, "Không tìm thấy vai trò")

            # Vai trò `Quản trị` lấy quyền TỪ MÃ, không từ `vai_tro_quyen` —
            # xem `xac_thuc.doc_phien`. Cho sửa tập quyền của nó là để người
            # quản trị bỏ tick, bấm Lưu, thấy báo thành công, và không có gì
            # thay đổi. Một thao tác không tác dụng mà vẫn báo thành công còn
            # tệ hơn một nút bị khoá: người ta tin là đã siết quyền rồi.
            if cu["he_thong"] and cu["ten"] == "Quản trị":
                if sorted(set(body.quyen)) != sorted(QUYEN):
                    raise HTTPException(409, (
                        "Vai trò “Quản trị” luôn có toàn bộ quyền, lấy thẳng "
                        "từ mã — sửa tập quyền của nó không có tác dụng. "
                        "Muốn giới hạn ai đó thì tạo vai trò riêng rồi gán "
                        "cho họ thay vì gán Quản trị."
                    ))
                if body.ten != cu["ten"]:
                    raise HTTPException(409, (
                        "Không đổi được tên vai trò dựng sẵn “Quản trị”: mã "
                        "nhận ra nó bằng đúng cái tên này."
                    ))

            await conn.execute(
                "UPDATE vai_tro SET ten = $2, mo_ta = $3, sua_luc = now() "
                "WHERE id = $1", vai_tro_id, body.ten, body.mo_ta)
            await conn.execute(
                "DELETE FROM vai_tro_quyen WHERE vai_tro_id = $1", vai_tro_id)
            for ma in sorted(set(body.quyen)):
                await conn.execute(
                    "INSERT INTO vai_tro_quyen (vai_tro_id, quyen) VALUES ($1,$2)",
                    vai_tro_id, ma,
                )

            # Ghi TRƯỚC rồi đếm — đọc trước ghi sau thì hai quản trị bấm cùng
            # lúc đều thấy "vẫn còn người khác" và cả hai đều chạy.
            if not await _con_nguoi_giu_quyen_song_con(conn):
                raise KhoaCungNgoaiHeThong()

    await db.log_event("vai_tro.sua", actor=nguoi.get("ten_dang_nhap", "?"),
                       ref_id=vai_tro_id, ten=body.ten,
                       quyen=sorted(set(body.quyen)))
    return {"id": str(vai_tro_id), "ten": body.ten, "mo_ta": body.mo_ta,
            "quyen": sorted(set(body.quyen)), "he_thong": cu["he_thong"]}


@router.delete("/vai-tro/{vai_tro_id}", status_code=204)
async def xoa_vai_tro(
    vai_tro_id: UUID,
    nguoi: dict = Depends(can_quyen("nguoi_dung.sua")),
) -> None:
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            cu = await conn.fetchrow(
                "SELECT ten, he_thong FROM vai_tro WHERE id = $1 FOR UPDATE",
                vai_tro_id,
            )
            if cu is None:
                raise HTTPException(404, "Không tìm thấy vai trò")
            if cu["he_thong"]:
                raise HTTPException(409, (
                    f"“{cu['ten']}” là vai trò dựng sẵn, không xoá được. "
                    "Muốn thu quyền thì gỡ vai trò khỏi từng người."
                ))
            await conn.execute("DELETE FROM vai_tro WHERE id = $1", vai_tro_id)
            if not await _con_nguoi_giu_quyen_song_con(conn):
                raise KhoaCungNgoaiHeThong()

    await db.log_event("vai_tro.xoa", actor=nguoi.get("ten_dang_nhap", "?"),
                       ref_id=vai_tro_id, ten=cu["ten"])


@router.put("/nguoi-dung/{nguoi_dung_id}/vai-tro")
async def gan_vai_tro(
    nguoi_dung_id: UUID,
    body: GanVaiTroIn,
    nguoi: dict = Depends(can_quyen("nguoi_dung.sua")),
) -> dict[str, Any]:
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            co = await conn.fetchval(
                "SELECT 1 FROM nguoi_dung WHERE id = $1", nguoi_dung_id)
            if not co:
                raise HTTPException(404, "Không tìm thấy nhân viên")

            if body.vai_tro:
                so = await conn.fetchval(
                    "SELECT count(*) FROM vai_tro WHERE id = ANY($1::uuid[])",
                    list(body.vai_tro))
                if so != len(set(body.vai_tro)):
                    raise HTTPException(422, "Có vai trò không tồn tại")

            await conn.execute(
                "DELETE FROM nguoi_dung_vai_tro WHERE nguoi_dung_id = $1",
                nguoi_dung_id)
            for vid in sorted(set(body.vai_tro), key=str):
                await conn.execute(
                    "INSERT INTO nguoi_dung_vai_tro "
                    "(nguoi_dung_id, vai_tro_id, gan_boi) VALUES ($1,$2,$3)",
                    nguoi_dung_id, vid,
                    UUID(str(nguoi["id"])) if nguoi.get("id") else None,
                )
            if not await _con_nguoi_giu_quyen_song_con(conn):
                raise KhoaCungNgoaiHeThong()

    await db.log_event("nguoi_dung.vai_tro", actor=nguoi.get("ten_dang_nhap", "?"),
                       ref_id=nguoi_dung_id,
                       vai_tro=[str(v) for v in body.vai_tro])
    return await giai_thich_quyen(nguoi_dung_id, _q=nguoi)
