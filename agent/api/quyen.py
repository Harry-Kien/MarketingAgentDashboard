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

VÌ SAO LỊCH SỬ ĐỔI QUYỀN GHI TRONG CÙNG GIAO DỊCH (22.11.2026)
---------------------------------------------------------------
`db.log_event` nuốt lỗi — đúng cho nhật ký thường: ghi nhật ký hỏng không
được làm hỏng việc chính. Với đổi quyền thì ngược lại: một lần cấp quyền
không để lại dấu vết là đúng thứ mục 12.8 của phiếu việc cấm. Nên ở đây
lịch sử ghi bằng chính kết nối của giao dịch: ghi lịch sử hỏng thì việc đổi
quyền cũng không xảy ra.

Lịch sử ghi TRƯỚC/SAU (danh sách đầy đủ) chứ không chỉ "đã sửa": câu hỏi
người ta mang tới màn Lịch sử luôn là "hôm ấy vai trò này mất quyền gì".
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agent import db
from agent.core.quyen import NHOM_QUYEN, QUYEN

from .routes import can_quyen

router = APIRouter(prefix="/api", tags=["quyen"])

# Quyền mà nếu mất người cuối cùng giữ nó thì không ai sửa lại được.
QUYEN_SONG_CON = "nguoi_dung.sua"


# ---------------------------------------------------------------------
#  KHÔNG CẤP ĐƯỢC THỨ MÌNH KHÔNG CÓ (rà soát 20.11.2026)
# ---------------------------------------------------------------------
# Trước bản này `nguoi_dung.sua` là chìa khoá vạn năng: ai được giao quản
# lý nhân sự tự gán được vai trò "Quản trị" cho mình, hoặc tạo một vai trò
# tick đủ 40 quyền rồi gán cho mình — một bước là chiếm toàn hệ thống, và
# nhật ký chỉ ghi "nguoi_dung.vai_tro" như mọi lần gán bình thường.
#
# Luật: người thao tác chỉ được tạo/sửa/xoá/gán/ngừng dùng vai trò mà TẬP
# QUYỀN nằm trọn trong tập quyền của chính mình, và chỉ được đụng tới người
# có tập quyền nằm trọn trong tập quyền của mình (không hạ được, không khoá
# được, không lấy việc của cấp trên). Quản trị có đủ quyền nên không bị ảnh
# hưởng.


async def quyen_cua_vai_tro(conn, ids, *, chi_dang_dung: bool = False) -> set[str]:
    """
    Tập quyền của các vai trò — "Quản trị" dựng sẵn = toàn bộ.

    `chi_dang_dung=False` (mặc định) tính cả vai trò đã ngừng dùng: dùng khi
    xét NỘI DUNG vai trò (ai được sửa, ngừng, dùng lại nó). Vai trò ngừng
    dùng vẫn có thể được dùng lại, nên người yếu hơn không được đụng vào nó
    — không thì đó là chỗ "đậu" một vai trò mạnh để bật lên sau.
    """
    ids = list(ids)
    if not ids:
        return set()
    if await conn.fetchval(
        "SELECT bool_or(he_thong AND ten = 'Quản trị') FROM vai_tro "
        "WHERE id = ANY($1::uuid[]) AND (dang_dung OR NOT $2::bool)",
        ids, chi_dang_dung):
        return set(QUYEN)
    rows = await conn.fetch(
        "SELECT DISTINCT vq.quyen FROM vai_tro_quyen vq "
        "JOIN vai_tro vt ON vt.id = vq.vai_tro_id "
        "WHERE vq.vai_tro_id = ANY($1::uuid[]) AND (vt.dang_dung OR NOT $2::bool)",
        ids, chi_dang_dung)
    return {r["quyen"] for r in rows} & set(QUYEN)


async def quyen_cua_nguoi(conn, nguoi_dung_id) -> set[str]:
    """Quyền HIỆU LỰC của một người: hợp quyền các vai trò ĐANG DÙNG."""
    ids = [r["vai_tro_id"] for r in await conn.fetch(
        "SELECT vai_tro_id FROM nguoi_dung_vai_tro WHERE nguoi_dung_id = $1",
        nguoi_dung_id)]
    return await quyen_cua_vai_tro(conn, ids, chi_dang_dung=True)


def chan_cap_vuot(nguoi: dict, can: set[str], viec: str) -> None:
    """403 nếu `can` có quyền người thao tác không có."""
    thieu = sorted(set(can) - set(nguoi.get("quyen") or ()))
    if thieu:
        raise HTTPException(403, (
            f"Không {viec} được: thao tác này liên quan tới quyền bạn không có "
            f"({', '.join(thieu[:6])}{'…' if len(thieu) > 6 else ''}). "
            "Chỉ người có đủ các quyền ấy mới làm được."))


async def ghi_lich_su(conn, loai: str, *, nguoi: dict, ref_id=None, **chi_tiet) -> None:
    """
    Ghi một dòng lịch sử nhân sự/phân quyền BẰNG KẾT NỐI CỦA GIAO DỊCH.

    Không nuốt lỗi — xem đầu tệp. Hỏng ở đây thì giao dịch rollback và thao
    tác báo lỗi, thay vì một lần đổi quyền không ai truy được.
    """
    await conn.execute(
        "INSERT INTO events (kind, actor, ref_id, detail) VALUES ($1,$2,$3,$4)",
        loai, nguoi.get("ten_dang_nhap", "?"), ref_id, chi_tiet,
    )


class VaiTroIn(BaseModel):
    ten: str = Field(min_length=1, max_length=80)
    mo_ta: str = Field("", max_length=500)
    quyen: list[str] = Field(default_factory=list)


class GanVaiTroIn(BaseModel):
    vai_tro: list[UUID] = Field(default_factory=list)


class TrangThaiVaiTroIn(BaseModel):
    dang_dung: bool


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
        "JOIN vai_tro vt ON vt.id = ndvt.vai_tro_id AND vt.dang_dung "
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


async def _anh_vai_tro(conn, vai_tro_id) -> dict[str, Any]:
    """Ảnh chụp một vai trò cho lịch sử: tên, mô tả, quyền (đã lọc danh mục)."""
    vt = await conn.fetchrow(
        "SELECT ten, mo_ta FROM vai_tro WHERE id = $1", vai_tro_id)
    return {"ten": vt["ten"] if vt else "", "mo_ta": vt["mo_ta"] if vt else "",
            "quyen": sorted(await quyen_cua_vai_tro(conn, [vai_tro_id]))}


async def _ten_vai_tro_cua(conn, nguoi_dung_id) -> list[str]:
    return [r["ten"] for r in await conn.fetch(
        "SELECT vt.ten FROM nguoi_dung_vai_tro x "
        "JOIN vai_tro vt ON vt.id = x.vai_tro_id "
        "WHERE x.nguoi_dung_id = $1 ORDER BY vt.ten", nguoi_dung_id)]


# =====================================================================
#  Đọc
# =====================================================================

@router.get("/quyen")
async def danh_muc_quyen(
    _q: dict = Depends(can_quyen("nguoi_dung.doc")),
) -> dict[str, Any]:
    """
    Danh mục quyền.

    `nhom_hien_thi` là thứ màn cấp quyền vẽ: theo chức năng dashboard, đúng
    thứ tự phiếu việc mục 12.2. `nhom` (theo tiền tố mã) giữ lại cho màn cũ
    và cho ai đang đọc API này.
    """
    nhom: dict[str, list[dict[str, str]]] = {}
    for ma, nhan in QUYEN.items():
        nhom.setdefault(ma.split(".")[0], []).append({"ma": ma, "nhan": nhan})
    return {
        "nhom": nhom,
        "nhom_hien_thi": [
            {"ma": ma_nhom, "ten": ten,
             "quyen": [{"ma": q, "nhan": QUYEN[q]} for q in ds]}
            for ma_nhom, ten, ds in NHOM_QUYEN
        ],
    }


@router.get("/vai-tro")
async def liet_ke_vai_tro(
    _q: dict = Depends(can_quyen("nguoi_dung.doc")),
) -> dict[str, Any]:
    ds = await db.fetch(
        "SELECT vt.id, vt.ten, vt.mo_ta, vt.he_thong, vt.tao_luc, vt.sua_luc, "
        "       vt.dang_dung, vt.tung_gan_luc, "
        "       COALESCE(array_agg(DISTINCT vq.quyen) "
        "                FILTER (WHERE vq.quyen IS NOT NULL), "
        "                ARRAY[]::text[]) AS quyen, "
        "       (SELECT count(*) FROM nguoi_dung_vai_tro ndvt "
        "        WHERE ndvt.vai_tro_id = vt.id) AS so_nguoi "
        "FROM vai_tro vt "
        "LEFT JOIN vai_tro_quyen vq ON vq.vai_tro_id = vt.id "
        "GROUP BY vt.id ORDER BY vt.he_thong DESC, vt.dang_dung DESC, vt.ten"
    )
    for v in ds:
        v["id"] = str(v["id"])
        for k in ("tao_luc", "sua_luc", "tung_gan_luc"):
            if v.get(k):
                v[k] = v[k].isoformat()
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
        # Màn hình vẽ nút Xoá theo đúng luật máy chủ dùng — nút bấm vào rồi
        # mới báo 409 dạy người ta rằng lỗi là chuyện bình thường.
        v["xoa_duoc"] = (not v["he_thong"] and not v["tung_gan_luc"]
                         and not v["so_nguoi"])
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

    Vai trò đã ngừng dùng nằm riêng ở `vai_tro_ngung`: người ấy vẫn "mang"
    nó (để lịch sử đọc được) nhưng nó KHÔNG cấp gì — trộn vào `vai_tro` là
    màn hình nói một người có quyền mà thật ra không có.
    """
    nguoi = await db.fetchrow(
        "SELECT id, ten_dang_nhap, ho_ten, khoa FROM nguoi_dung WHERE id = $1",
        nguoi_dung_id,
    )
    if nguoi is None:
        raise HTTPException(404, "Không tìm thấy nhân viên")

    ds = await db.fetch(
        "SELECT vt.ten AS vai_tro, vt.he_thong, vt.dang_dung, vq.quyen "
        "FROM nguoi_dung_vai_tro ndvt "
        "JOIN vai_tro vt ON vt.id = ndvt.vai_tro_id "
        "LEFT JOIN vai_tro_quyen vq ON vq.vai_tro_id = vt.id "
        "WHERE ndvt.nguoi_dung_id = $1",
        nguoi_dung_id,
    )

    quyen: dict[str, list[str]] = {}
    for r in ds:
        if not r["dang_dung"]:
            continue
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
        "vai_tro": sorted({r["vai_tro"] for r in ds if r["dang_dung"]}),
        "vai_tro_ngung": sorted({r["vai_tro"] for r in ds if not r["dang_dung"]}),
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
    chan_cap_vuot(nguoi, set(body.quyen), "tạo vai trò")
    quyen = sorted(set(body.quyen))
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            try:
                vid = await conn.fetchval(
                    "INSERT INTO vai_tro (ten, mo_ta) VALUES ($1, $2) RETURNING id",
                    body.ten, body.mo_ta,
                )
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(409, f"Đã có vai trò tên “{body.ten}”.") from exc
            for ma in quyen:
                await conn.execute(
                    "INSERT INTO vai_tro_quyen (vai_tro_id, quyen) VALUES ($1,$2)",
                    vid, ma,
                )
            await ghi_lich_su(
                conn, "vai_tro.tao", nguoi=nguoi, ref_id=vid, ten=body.ten,
                truoc=None, sau={"ten": body.ten, "mo_ta": body.mo_ta, "quyen": quyen},
                them=quyen, bot=[])
    return {"id": str(vid), "ten": body.ten, "mo_ta": body.mo_ta,
            "quyen": quyen, "he_thong": False, "dang_dung": True}


@router.put("/vai-tro/{vai_tro_id}")
async def sua_vai_tro(
    vai_tro_id: UUID,
    body: VaiTroIn,
    nguoi: dict = Depends(can_quyen("nguoi_dung.sua")),
) -> dict[str, Any]:
    """
    Sửa tên, mô tả, tập quyền.

    Không cần "đẩy" thay đổi tới người đang mang vai trò: `doc_phien` nạp
    quyền từ CSDL ở MỌI request, không cache — lưu xong thì request kế tiếp
    của họ đã theo tập mới (mục 12.5; có test canh trên Postgres thật).
    """
    _kiem_ma_quyen(body.quyen)
    quyen = sorted(set(body.quyen))
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            cu = await conn.fetchrow(
                "SELECT ten, he_thong, dang_dung FROM vai_tro WHERE id = $1 FOR UPDATE",
                vai_tro_id,
            )
            if cu is None:
                raise HTTPException(404, "Không tìm thấy vai trò")
            # Cả quyền CŨ lẫn MỚI: sửa một vai trò mạnh hơn mình (kể cả chỉ
            # để bớt quyền của nó) là đụng tới cấp trên.
            quyen_cu = await quyen_cua_vai_tro(conn, [vai_tro_id])
            chan_cap_vuot(nguoi, quyen_cu | set(quyen), "sửa vai trò này")

            # Vai trò `Quản trị` lấy quyền TỪ MÃ, không từ `vai_tro_quyen` —
            # xem `xac_thuc.doc_phien`. Cho sửa tập quyền của nó là để người
            # quản trị bỏ tick, bấm Lưu, thấy báo thành công, và không có gì
            # thay đổi. Một thao tác không tác dụng mà vẫn báo thành công còn
            # tệ hơn một nút bị khoá: người ta tin là đã siết quyền rồi.
            if cu["he_thong"] and cu["ten"] == "Quản trị":
                if quyen != sorted(QUYEN):
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

            truoc = await _anh_vai_tro(conn, vai_tro_id)
            try:
                await conn.execute(
                    "UPDATE vai_tro SET ten = $2, mo_ta = $3, sua_luc = now() "
                    "WHERE id = $1", vai_tro_id, body.ten, body.mo_ta)
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(409, f"Đã có vai trò tên “{body.ten}”.") from exc
            await conn.execute(
                "DELETE FROM vai_tro_quyen WHERE vai_tro_id = $1", vai_tro_id)
            for ma in quyen:
                await conn.execute(
                    "INSERT INTO vai_tro_quyen (vai_tro_id, quyen) VALUES ($1,$2)",
                    vai_tro_id, ma,
                )

            # Ghi TRƯỚC rồi đếm — đọc trước ghi sau thì hai quản trị bấm cùng
            # lúc đều thấy "vẫn còn người khác" và cả hai đều chạy.
            if not await _con_nguoi_giu_quyen_song_con(conn):
                raise KhoaCungNgoaiHeThong()

            sau = await _anh_vai_tro(conn, vai_tro_id)
            so_nguoi = await conn.fetchval(
                "SELECT count(*) FROM nguoi_dung_vai_tro WHERE vai_tro_id = $1",
                vai_tro_id)
            await ghi_lich_su(
                conn, "vai_tro.sua", nguoi=nguoi, ref_id=vai_tro_id, ten=body.ten,
                truoc=truoc, sau=sau,
                them=sorted(set(sau["quyen"]) - set(truoc["quyen"])),
                bot=sorted(set(truoc["quyen"]) - set(sau["quyen"])),
                so_nguoi_anh_huong=int(so_nguoi or 0))

    return {"id": str(vai_tro_id), "ten": body.ten, "mo_ta": body.mo_ta,
            "quyen": quyen, "he_thong": cu["he_thong"],
            "dang_dung": cu["dang_dung"]}


@router.post("/vai-tro/{vai_tro_id}/trang-thai")
async def doi_trang_thai_vai_tro(
    vai_tro_id: UUID,
    body: TrangThaiVaiTroIn,
    nguoi: dict = Depends(can_quyen("nguoi_dung.sua")),
) -> dict[str, Any]:
    """
    Ngừng dùng / dùng lại một vai trò (mục 13.9).

    Ngừng dùng: mọi người đang mang nó MẤT các quyền nó cấp ngay ở request
    kế tiếp (trừ quyền còn được vai trò khác cấp); không gán mới được; vẫn
    hiện trong danh sách và trong lịch sử. Đây là đường thay cho Xoá khi
    vai trò đã có lịch sử.
    """
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            cu = await conn.fetchrow(
                "SELECT ten, he_thong, dang_dung FROM vai_tro WHERE id = $1 FOR UPDATE",
                vai_tro_id,
            )
            if cu is None:
                raise HTTPException(404, "Không tìm thấy vai trò")
            # Dùng lại một vai trò mạnh = cấp lại các quyền ấy cho mọi người
            # đang mang nó; ngừng dùng nó = hạ cấp những người ấy. Cả hai
            # chiều đều là đụng tới quyền mình có thể không có.
            chan_cap_vuot(nguoi, await quyen_cua_vai_tro(conn, [vai_tro_id]),
                          "đổi trạng thái vai trò này")
            if cu["he_thong"]:
                raise HTTPException(409, (
                    f"“{cu['ten']}” là vai trò dựng sẵn, không ngừng dùng được. "
                    "Muốn thu quyền thì gỡ vai trò khỏi từng người."
                ))
            if cu["dang_dung"] == body.dang_dung:
                return {"id": str(vai_tro_id), "ten": cu["ten"],
                        "dang_dung": cu["dang_dung"], "doi": False}

            await conn.execute(
                "UPDATE vai_tro SET dang_dung = $2, sua_luc = now() WHERE id = $1",
                vai_tro_id, body.dang_dung)
            if not await _con_nguoi_giu_quyen_song_con(conn):
                raise KhoaCungNgoaiHeThong()

            nguoi_mang = [r["ten_dang_nhap"] for r in await conn.fetch(
                "SELECT nd.ten_dang_nhap FROM nguoi_dung_vai_tro x "
                "JOIN nguoi_dung nd ON nd.id = x.nguoi_dung_id "
                "WHERE x.vai_tro_id = $1 ORDER BY nd.ten_dang_nhap", vai_tro_id)]
            anh = await _anh_vai_tro(conn, vai_tro_id)
            await ghi_lich_su(
                conn, "vai_tro.dung_lai" if body.dang_dung else "vai_tro.ngung_dung",
                nguoi=nguoi, ref_id=vai_tro_id, ten=cu["ten"],
                truoc={"dang_dung": cu["dang_dung"]},
                sau={"dang_dung": body.dang_dung},
                # Quyền những người đang mang vai trò vừa được/mất (trừ khi
                # vai trò khác của họ cũng cấp) — chính là "điều gì đã đổi".
                them=anh["quyen"] if body.dang_dung else [],
                bot=[] if body.dang_dung else anh["quyen"],
                nguoi_anh_huong=nguoi_mang)
    return {"id": str(vai_tro_id), "ten": cu["ten"], "dang_dung": body.dang_dung,
            "doi": True, "so_nguoi_anh_huong": len(nguoi_mang)}


@router.delete("/vai-tro/{vai_tro_id}", status_code=204)
async def xoa_vai_tro(
    vai_tro_id: UUID,
    nguoi: dict = Depends(can_quyen("nguoi_dung.sua")),
) -> None:
    """
    Xoá HẲN — chỉ cho vai trò CHƯA TỪNG được gán cho ai (mục 13.9).

    Vai trò đã từng có người mang là một phần lịch sử nghiệp vụ: xoá nó thì
    ON DELETE CASCADE cuốn luôn dòng gán, và câu "tháng trước vì sao người
    này duyệt được đơn" mất câu trả lời. Những vai trò ấy chỉ NGỪNG DÙNG
    được. Vai trò tạo nhầm, chưa gán ai thì xoá thoải mái — giữ nó lại chỉ
    làm danh sách rác.
    """
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            cu = await conn.fetchrow(
                "SELECT ten, he_thong, tung_gan_luc FROM vai_tro "
                "WHERE id = $1 FOR UPDATE",
                vai_tro_id,
            )
            if cu is None:
                raise HTTPException(404, "Không tìm thấy vai trò")
            chan_cap_vuot(nguoi, await quyen_cua_vai_tro(conn, [vai_tro_id]),
                          "xoá vai trò này")
            if cu["he_thong"]:
                raise HTTPException(409, (
                    f"“{cu['ten']}” là vai trò dựng sẵn, không xoá được. "
                    "Muốn thu quyền thì gỡ vai trò khỏi từng người."
                ))
            dang_mang = await conn.fetchval(
                "SELECT count(*) FROM nguoi_dung_vai_tro WHERE vai_tro_id = $1",
                vai_tro_id)
            if dang_mang or cu["tung_gan_luc"] is not None:
                raise HTTPException(409, (
                    f"Vai trò “{cu['ten']}” đã từng được gán cho nhân viên — xoá "
                    "là mất dấu vết ai từng có quyền gì. Bấm “Ngừng dùng”: vai "
                    "trò thôi cấp quyền ngay, không gán mới được, nhưng lịch "
                    "sử vẫn còn."
                ))
            truoc = await _anh_vai_tro(conn, vai_tro_id)
            await conn.execute("DELETE FROM vai_tro WHERE id = $1", vai_tro_id)
            if not await _con_nguoi_giu_quyen_song_con(conn):
                raise KhoaCungNgoaiHeThong()
            await ghi_lich_su(conn, "vai_tro.xoa", nguoi=nguoi, ref_id=vai_tro_id,
                              ten=cu["ten"], truoc=truoc, sau=None,
                              them=[], bot=truoc["quyen"])


@router.put("/nguoi-dung/{nguoi_dung_id}/vai-tro")
async def gan_vai_tro(
    nguoi_dung_id: UUID,
    body: GanVaiTroIn,
    nguoi: dict = Depends(can_quyen("nguoi_dung.sua")),
) -> dict[str, Any]:
    """
    Đặt TOÀN BỘ tập vai trò của một người (mục 13.5–13.7).

    Ghi theo HIỆU (gỡ cái bị bỏ, thêm cái mới), không xoá hết rồi chèn lại:
    xoá-chèn-lại đánh mất `gan_luc`/`gan_boi` của những vai trò không đổi —
    tức là dấu vết "ai cấp vai trò này, từ bao giờ" — và chèn lại một vai trò
    đã ngừng dùng thì trigger 0058 chặn, nên người đang mang một vai trò ngừng
    dùng không lưu được bất cứ thay đổi nào khác.
    """
    moi = {UUID(str(v)) for v in body.vai_tro}
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            nd = await conn.fetchrow(
                "SELECT id, ten_dang_nhap FROM nguoi_dung WHERE id = $1 FOR UPDATE",
                nguoi_dung_id)
            if not nd:
                raise HTTPException(404, "Không tìm thấy nhân viên")

            vt = {r["id"]: r for r in await conn.fetch(
                "SELECT id, ten, dang_dung FROM vai_tro WHERE id = ANY($1::uuid[])",
                list(moi))} if moi else {}
            if len(vt) != len(moi):
                raise HTTPException(422, "Có vai trò không tồn tại")

            cu = {r["vai_tro_id"] for r in await conn.fetch(
                "SELECT vai_tro_id FROM nguoi_dung_vai_tro WHERE nguoi_dung_id = $1",
                nguoi_dung_id)}
            them = moi - cu
            bot = cu - moi

            ngung = sorted(vt[v]["ten"] for v in them if not vt[v]["dang_dung"])
            if ngung:
                raise HTTPException(422, (
                    f"Vai trò đã ngừng dùng, không gán mới được: {', '.join(ngung)}. "
                    "Dùng lại vai trò ở tab Vai trò & Quyền nếu thật sự cần."))

            # Không hạ được người có quyền mình không có, không trao được
            # vai trò có quyền mình không có.
            chan_cap_vuot(nguoi, await quyen_cua_nguoi(conn, nguoi_dung_id),
                          "đổi vai trò của người này")
            chan_cap_vuot(nguoi, await quyen_cua_vai_tro(conn, moi),
                          "gán các vai trò này")

            truoc = await _ten_vai_tro_cua(conn, nguoi_dung_id)
            truoc_quyen = sorted(await quyen_cua_nguoi(conn, nguoi_dung_id))
            if bot:
                await conn.execute(
                    "DELETE FROM nguoi_dung_vai_tro "
                    "WHERE nguoi_dung_id = $1 AND vai_tro_id = ANY($2::uuid[])",
                    nguoi_dung_id, list(bot))
            for vid in sorted(them, key=str):
                await conn.execute(
                    "INSERT INTO nguoi_dung_vai_tro "
                    "(nguoi_dung_id, vai_tro_id, gan_boi) VALUES ($1,$2,$3)",
                    nguoi_dung_id, vid,
                    UUID(str(nguoi["id"])) if nguoi.get("id") else None,
                )
            if not await _con_nguoi_giu_quyen_song_con(conn):
                raise KhoaCungNgoaiHeThong()

            if them or bot:
                sau = await _ten_vai_tro_cua(conn, nguoi_dung_id)
                sau_quyen = sorted(await quyen_cua_nguoi(conn, nguoi_dung_id))
                await ghi_lich_su(
                    conn, "nguoi_dung.vai_tro", nguoi=nguoi, ref_id=nguoi_dung_id,
                    ten_dang_nhap=nd["ten_dang_nhap"],
                    # `vai_tro` (id) giữ đúng tên trường cũ: 0058 soi nó để
                    # biết vai trò nào từng được gán.
                    vai_tro=[str(v) for v in sorted(moi, key=str)],
                    truoc=truoc, sau=sau,
                    them=sorted(set(sau) - set(truoc)),
                    bot=sorted(set(truoc) - set(sau)),
                    # Quyền HIỆU LỰC được/mất — vai trò khác cũng cấp thì
                    # không tính là mất (mục 13.6).
                    quyen_them=sorted(set(sau_quyen) - set(truoc_quyen)),
                    quyen_bot=sorted(set(truoc_quyen) - set(sau_quyen)))

    return await giai_thich_quyen(nguoi_dung_id, _q=nguoi)
