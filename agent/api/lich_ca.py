"""
API lịch ca trực (bảng `ca_truc`, `ca_nghi`, hàm `dang_trong_ca` — 0034).

Quyền dùng lại `dinh_tuyen.doc` / `dinh_tuyen.sua`: lịch ca quyết định ai
được bộ định tuyến giao hội thoại, nên người sửa được định tuyến là người
xếp được ca. "Ca của tôi" chỉ cần `hoi_thoai.doc` — ai trả lời khách cũng
phải xem được mình trực khi nào.

"Đang trong ca hay không" CHỈ hỏi hàm SQL `dang_trong_ca`, không tính lại
ở Python: hai bản tính là sớm muộn lệch nhau, và màn hình nói "đang trong
ca" trong khi bộ định tuyến bỏ qua người đó.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agent import db

from .routes import can_quyen

router = APIRouter(prefix="/api/lich-ca", tags=["lich-ca"])

_GIO = re.compile(r"^([01]?\d|2[0-4]):([0-5]\d)$")
TEN_THU = {1: "Thứ 2", 2: "Thứ 3", 3: "Thứ 4", 4: "Thứ 5", 5: "Thứ 6", 6: "Thứ 7", 7: "Chủ nhật"}


def phut(chu: str) -> int:
    m = _GIO.match(str(chu or "").strip())
    if not m:
        raise ValueError(f"giờ phải dạng HH:MM, nhận {chu!r}")
    p = int(m[1]) * 60 + int(m[2])
    if p > 1440:
        raise ValueError(f"giờ quá 24:00: {chu!r}")
    return p


def gio(p: int) -> str:
    return f"{p // 60:02d}:{p % 60:02d}"


TUAN = 7 * 1440


def doan_tuan(thu: int, bat_dau: int, ket_thuc: int) -> list[tuple[int, int]]:
    """
    Ca → các đoạn [a, b) trên trục phút của TUẦN (0 = 00:00 thứ Hai).

    Ca qua đêm Chủ nhật (22:00 → 06:00) vắt sang sáng thứ Hai của tuần sau,
    nên bị cắt làm hai đoạn ở mép tuần — không cắt thì nó không bao giờ
    "chồng" lên ca sáng thứ Hai dù thật sự chồng.
    """
    dau = (thu - 1) * 1440 + bat_dau
    dai = ket_thuc - bat_dau if bat_dau < ket_thuc else 1440 - bat_dau + ket_thuc
    cuoi = dau + dai
    return [(dau, cuoi)] if cuoi <= TUAN else [(dau, TUAN), (0, cuoi - TUAN)]


class CaIn(BaseModel):
    thu: int = Field(ge=1, le=7)
    bat_dau: str
    ket_thuc: str


class LichIn(BaseModel):
    ca: list[CaIn] = Field(max_length=28)


def kiem_lich(ca: list[CaIn]) -> list[tuple[int, int, int]]:
    """
    Đổi sang phút và CHẶN ca chồng nhau. Chồng nhau không làm sai bộ định
    tuyến, nhưng là dấu hiệu gõ nhầm ("8:00–14:00" và "13:00–20:00" thay
    vì "14:00–20:00") — nói ra lúc lưu rẻ hơn để người quản lý tự phát hiện.
    """
    ra: list[tuple[int, int, int]] = []
    da_co: list[tuple[int, int, str]] = []
    for c in ca:
        try:
            a, b = phut(c.bat_dau), phut(c.ket_thuc)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if a == 1440:
            raise HTTPException(422, "ca không bắt đầu lúc 24:00 — dùng 00:00 của ngày sau")
        if b == 0:
            b = 1440  # "22:00 → 00:00" là ca tới hết ngày, không phải ca rỗng
        if a == b:
            raise HTTPException(422, f"{TEN_THU[c.thu]}: giờ bắt đầu trùng giờ kết thúc")
        nhan = f"{TEN_THU[c.thu]} {gio(a)}–{gio(b)}"
        for x, y in doan_tuan(c.thu, a, b):
            for u, v, ten in da_co:
                if x < v and u < y:
                    raise HTTPException(422, f"ca chồng nhau: {nhan} và {ten}")
        da_co += [(x, y, nhan) for x, y in doan_tuan(c.thu, a, b)]
        ra.append((c.thu, a, b))
    return ra


class NghiIn(BaseModel):
    nguoi_dung_id: UUID
    tu_luc: datetime
    den_luc: datetime
    ly_do: str = Field(default="", max_length=200)


def _ca(r) -> dict[str, Any]:
    return {"thu": r["thu"], "ten_thu": TEN_THU[r["thu"]], "bat_dau": gio(r["bat_dau"]),
            "ket_thuc": gio(r["ket_thuc"]), "qua_dem": r["bat_dau"] > r["ket_thuc"]}


def _nghi(r) -> dict[str, Any]:
    return {"id": str(r["id"]), "nguoi_dung_id": str(r["nguoi_dung_id"]),
            "tu_luc": r["tu_luc"].isoformat(), "den_luc": r["den_luc"].isoformat(),
            "ly_do": r["ly_do"]}


async def _canh_bao_doi_trong() -> list[dict[str, Any]]:
    """
    Đội có luật định tuyến đang chạy mà LÚC NÀY không ai sẵn sàng trong ca.

    Khi ấy bộ định tuyến không tìm được ai, hội thoại mới nằm chờ người tự
    nhận — đúng như trước khi có định tuyến, nhưng người quản lý tưởng nó
    đang chia việc. Nói ra ở đây, cạnh chỗ xếp ca, là chỗ sửa được.
    """
    rows = await db.fetch(
        "SELECT t.id, t.name, count(tm.user_id) FILTER ("
        "  WHERE tm.is_available AND NOT nd.khoa AND dang_trong_ca(tm.user_id, now())) AS so "
        "FROM teams t JOIN routing_rules r ON r.team_id = t.id AND r.active "
        "LEFT JOIN team_members tm ON tm.team_id = t.id "
        "LEFT JOIN nguoi_dung nd ON nd.id = tm.user_id "
        "WHERE t.status = 'active' GROUP BY t.id, t.name")
    return [{"doi": r["name"], "ghi": f"Đội «{r['name']}» có luật định tuyến nhưng lúc này "
             "không ai trong ca — hội thoại mới sẽ nằm chờ người tự nhận."}
            for r in rows if not r["so"]]


@router.get("")
async def xem(_q: dict = Depends(can_quyen("dinh_tuyen.doc"))) -> dict[str, Any]:
    nguoi = await db.fetch(
        "SELECT id, ho_ten, ten_dang_nhap, dang_trong_ca(id, now()) AS trong_ca, "
        "EXISTS (SELECT 1 FROM ca_nghi n WHERE n.nguoi_dung_id = nd.id "
        "        AND now() >= n.tu_luc AND now() < n.den_luc) AS dang_nghi "
        "FROM nguoi_dung nd WHERE NOT khoa ORDER BY ho_ten, ten_dang_nhap")
    ca = await db.fetch("SELECT * FROM ca_truc ORDER BY thu, bat_dau")
    nghi = await db.fetch("SELECT * FROM ca_nghi WHERE den_luc > now() ORDER BY tu_luc")
    theo: dict[str, list] = {}
    for c in ca:
        theo.setdefault(str(c["nguoi_dung_id"]), []).append(_ca(c))
    return {
        "nguoi": [{"id": str(n["id"]), "ten": n["ho_ten"] or n["ten_dang_nhap"],
                   "trong_ca": n["trong_ca"], "dang_nghi": n["dang_nghi"],
                   "ca": theo.get(str(n["id"]), [])} for n in nguoi],
        "nghi": [_nghi(n) for n in nghi],
        "canh_bao": await _canh_bao_doi_trong(),
    }


@router.get("/cua-toi")
async def cua_toi(nguoi: dict = Depends(can_quyen("hoi_thoai.doc"))) -> dict[str, Any]:
    uid = UUID(str(nguoi["id"]))
    r = await db.fetchrow("SELECT dang_trong_ca($1, now()) AS trong_ca", uid)
    ca = await db.fetch("SELECT * FROM ca_truc WHERE nguoi_dung_id = $1 ORDER BY thu, bat_dau", uid)
    nghi = await db.fetch("SELECT * FROM ca_nghi WHERE nguoi_dung_id = $1 AND den_luc > now() "
                          "ORDER BY tu_luc", uid)
    return {"trong_ca": bool(r and r["trong_ca"]), "ca": [_ca(c) for c in ca],
            "nghi": [_nghi(n) for n in nghi]}


@router.put("/{nguoi_dung_id}")
async def dat_lich(nguoi_dung_id: UUID, body: LichIn,
                   nguoi: dict = Depends(can_quyen("dinh_tuyen.sua"))) -> dict[str, Any]:
    ca = kiem_lich(body.ca)
    if await db.fetchrow("SELECT 1 FROM nguoi_dung WHERE id = $1", nguoi_dung_id) is None:
        raise HTTPException(404, "Không thấy nhân viên.")
    # Thay CẢ tuần trong một giao dịch: xoá xong mà chèn hỏng là người đó
    # thành "chưa xếp ca" = luôn trực — đúng chiều ngược lại ý người xếp.
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM ca_truc WHERE nguoi_dung_id = $1", nguoi_dung_id)
            for thu, a, b in ca:
                await conn.execute(
                    "INSERT INTO ca_truc (nguoi_dung_id, thu, bat_dau, ket_thuc) VALUES ($1,$2,$3,$4)",
                    nguoi_dung_id, thu, a, b)
    await db.log_event("lich_ca.dat", actor=nguoi.get("ten_dang_nhap") or "?",
                       nguoi_dung_id=str(nguoi_dung_id), so_ca=len(ca))
    r = await db.fetchrow("SELECT dang_trong_ca($1, now()) AS trong_ca", nguoi_dung_id)
    return {"so_ca": len(ca), "trong_ca": bool(r and r["trong_ca"])}


@router.post("/nghi", status_code=201)
async def them_nghi(body: NghiIn, nguoi: dict = Depends(can_quyen("dinh_tuyen.sua"))) -> dict[str, Any]:
    if body.tu_luc.tzinfo is None or body.den_luc.tzinfo is None:
        # Không đoán múi giờ: "08:00" không múi giờ trên máy chủ UTC là 15:00
        # giờ Việt Nam — lịch nghỉ lệch bảy tiếng.
        raise HTTPException(422, "thời gian nghỉ phải kèm múi giờ (ví dụ +07:00)")
    if body.den_luc <= body.tu_luc:
        raise HTTPException(422, "giờ kết thúc nghỉ phải sau giờ bắt đầu")
    if (body.den_luc - body.tu_luc).days > 366:
        raise HTTPException(422, "một lần nghỉ tối đa một năm")
    try:
        r = await db.fetchrow(
            "INSERT INTO ca_nghi (nguoi_dung_id, tu_luc, den_luc, ly_do, tao_boi) "
            "VALUES ($1,$2,$3,$4,$5) RETURNING *",
            body.nguoi_dung_id, body.tu_luc, body.den_luc, body.ly_do.strip(), UUID(str(nguoi["id"])))
    except Exception as exc:  # noqa: BLE001 — FK: nhân viên không tồn tại
        if "foreign key" in str(exc).lower():
            raise HTTPException(404, "Không thấy nhân viên.") from exc
        raise
    await db.log_event("lich_ca.nghi", actor=nguoi.get("ten_dang_nhap") or "?",
                       nguoi_dung_id=str(body.nguoi_dung_id))
    return _nghi(r)


@router.delete("/nghi/{nghi_id}", status_code=204)
async def xoa_nghi(nghi_id: UUID, nguoi: dict = Depends(can_quyen("dinh_tuyen.sua"))) -> None:
    r = await db.fetchrow("DELETE FROM ca_nghi WHERE id = $1 RETURNING nguoi_dung_id", nghi_id)
    if r is None:
        raise HTTPException(404, "Không thấy lịch nghỉ.")
    await db.log_event("lich_ca.xoa_nghi", actor=nguoi.get("ten_dang_nhap") or "?",
                       nguoi_dung_id=str(r["nguoi_dung_id"]))
